import Foundation
import Combine

/// Persistent settings for the thin client.
struct ClientSettings: Codable, Equatable {
    var baseURL: String = "http://127.0.0.1:8787"
    var apiKey: String = "dev-key-change-me"
    var speakReplies: Bool = false
}

/// One row in the chat transcript.
struct ChatItem: Identifiable, Equatable {
    enum Kind: Equatable {
        case user
        case assistant
        case tool
        case system
        case approval
    }

    let id: UUID
    var kind: Kind
    var text: String
    var approvalId: String? = nil
    var sessionId: String? = nil
    var resolved: Bool = false
}

/// Wire event from the harness SSE stream.
struct StreamEvent: Decodable {
    let kind: String
    let payload: AnyCodable?
}

/// Type-erased JSON value for flexible payloads.
struct AnyCodable: Decodable {
    let value: Any

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            value = NSNull()
        } else if let b = try? container.decode(Bool.self) {
            value = b
        } else if let i = try? container.decode(Int.self) {
            value = i
        } else if let d = try? container.decode(Double.self) {
            value = d
        } else if let s = try? container.decode(String.self) {
            value = s
        } else if let arr = try? container.decode([AnyCodable].self) {
            value = arr.map(\.value)
        } else if let dict = try? container.decode([String: AnyCodable].self) {
            value = dict.mapValues(\.value)
        } else {
            value = NSNull()
        }
    }

    var dict: [String: Any]? { value as? [String: Any] }
    var string: String? { value as? String }
}

@MainActor
final class AppState: ObservableObject {
    @Published var settings = ClientSettings()
    @Published var items: [ChatItem] = []
    @Published var sessionId: String?
    @Published var isStreaming = false
    @Published var isRunningTurn = false
    @Published var statusLine: String = "Idle"
    @Published var draft: String = ""
    @Published var errorMessage: String?

    let api = APIClient()
    let stream = EventStream()
    let speech = SpeechService()

    private let settingsKey = "chitti.client.settings"

    func loadSettings() {
        if let data = UserDefaults.standard.data(forKey: settingsKey),
           let decoded = try? JSONDecoder().decode(ClientSettings.self, from: data) {
            settings = decoded
        }
        api.configure(baseURL: settings.baseURL, apiKey: settings.apiKey)
    }

    func saveSettings() {
        if let data = try? JSONEncoder().encode(settings) {
            UserDefaults.standard.set(data, forKey: settingsKey)
        }
        api.configure(baseURL: settings.baseURL, apiKey: settings.apiKey)
    }

    func ensureSession() async throws {
        if sessionId != nil { return }
        statusLine = "Creating session…"
        let id = try await api.createSession(label: "ios")
        sessionId = id
        statusLine = "Session \(id.prefix(8))…"
        startStream(sessionId: id)
    }

    func startStream(sessionId: String) {
        isStreaming = true
        stream.connect(baseURL: settings.baseURL, apiKey: settings.apiKey, sessionId: sessionId) { [weak self] event in
            Task { @MainActor in
                self?.handle(event: event)
            }
        } onError: { [weak self] message in
            Task { @MainActor in
                self?.errorMessage = message
                self?.statusLine = "Stream error"
                self?.isStreaming = false
            }
        }
    }

    func sendDraft() async {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        draft = ""
        errorMessage = nil
        do {
            try await ensureSession()
            guard let sid = sessionId else { return }
            items.append(ChatItem(id: UUID(), kind: .user, text: text))
            isRunningTurn = true
            statusLine = "Thinking…"
            try await api.sendMessage(sessionId: sid, text: text)
        } catch {
            errorMessage = error.localizedDescription
            isRunningTurn = false
            statusLine = "Error"
        }
    }

    func approve(id: String, approved: Bool) async {
        guard let sid = sessionId else { return }
        do {
            try await api.resolveApproval(sessionId: sid, approvalId: id, approved: approved)
            if let idx = items.firstIndex(where: { $0.approvalId == id }) {
                items[idx].resolved = true
                items[idx].text += approved ? "\n✓ approved" : "\n✗ rejected"
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func handle(event: StreamEvent) {
        let kind = event.kind
        let payload = event.payload?.dict ?? [:]

        switch kind {
        case "hello", "session":
            statusLine = "Connected"
        case "assistant":
            let text = (payload["text"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            if !text.isEmpty {
                items.append(ChatItem(id: UUID(), kind: .assistant, text: text))
                if settings.speakReplies {
                    speech.speak(text)
                }
            }
            if let calls = payload["tool_calls"] as? [[String: Any]], !calls.isEmpty {
                for call in calls {
                    let name = call["name"] as? String ?? "?"
                    items.append(ChatItem(id: UUID(), kind: .tool, text: "→ \(name)"))
                }
            }
        case "tool_end":
            let call = payload["call"] as? [String: Any]
            let name = call?["name"] as? String ?? "tool"
            let result = String(describing: payload["result"] ?? "").prefix(280)
            items.append(ChatItem(id: UUID(), kind: .tool, text: "← \(name): \(result)"))
        case "approval_required":
            let aid = payload["id"] as? String ?? UUID().uuidString
            let reason = payload["reason"] as? String ?? "Approval needed"
            items.append(ChatItem(
                id: UUID(),
                kind: .approval,
                text: reason,
                approvalId: aid,
                sessionId: sessionId
            ))
            statusLine = "Waiting for approval"
        case "done":
            // Final text often already arrived as assistant; still surface if only here.
            if let text = payload["text"] as? String, !text.isEmpty {
                if items.last?.text != text {
                    items.append(ChatItem(id: UUID(), kind: .assistant, text: text))
                }
            }
            statusLine = "Done"
        case "turn_complete":
            isRunningTurn = false
            statusLine = "Idle"
        case "error":
            let msg = payload["message"] as? String ?? "Unknown error"
            errorMessage = msg
            items.append(ChatItem(id: UUID(), kind: .system, text: "Error: \(msg)"))
            isRunningTurn = false
            statusLine = "Error"
        default:
            break
        }
    }
}
