import Foundation

enum APIError: LocalizedError {
    case badURL
    case http(Int, String)
    case decode

    var errorDescription: String? {
        switch self {
        case .badURL: return "Invalid server URL"
        case .http(let code, let body): return "HTTP \(code): \(body)"
        case .decode: return "Could not decode server response"
        }
    }
}

/// REST client for the Chitti mobile harness.
final class APIClient {
    private var baseURL: URL = URL(string: "http://127.0.0.1:8787")!
    private var apiKey: String = "dev-key-change-me"
    private let session: URLSession = .shared

    func configure(baseURL: String, apiKey: String) {
        if let url = URL(string: baseURL.trimmingCharacters(in: .whitespacesAndNewlines)) {
            self.baseURL = url
        }
        self.apiKey = apiKey
    }

    func createSession(label: String) async throws -> String {
        let body = try JSONSerialization.data(withJSONObject: ["label": label])
        let data = try await request(path: "/v1/sessions", method: "POST", body: body)
        guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let id = json["id"] as? String else {
            throw APIError.decode
        }
        return id
    }

    func sendMessage(sessionId: String, text: String) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["text": text])
        _ = try await request(path: "/v1/sessions/\(sessionId)/messages", method: "POST", body: body)
    }

    func resolveApproval(sessionId: String, approvalId: String, approved: Bool) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["approved": approved])
        _ = try await request(
            path: "/v1/sessions/\(sessionId)/approvals/\(approvalId)",
            method: "POST",
            body: body
        )
    }

    func fetchMemory() async throws -> String {
        let data = try await request(path: "/v1/memory", method: "GET", body: nil)
        guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let text = json["text"] as? String else {
            throw APIError.decode
        }
        return text
    }

    /// Generic JSON POST used by the LoopCommandBus (reuses the auth header).
    func postJSON(path: String, body: [String: Any]) async throws -> [String: Any] {
        let data = try JSONSerialization.data(withJSONObject: body)
        let out = try await request(path: path, method: "POST", body: data)
        let obj = try JSONSerialization.jsonObject(with: out)
        return (obj as? [String: Any]) ?? [:]
    }

    /// Generic JSON GET returning raw data for Codable decoding.
    func getData(path: String) async throws -> Data {
        try await request(path: path, method: "GET", body: nil)
    }

    /// Generic JSON POST returning raw data for Codable decoding.
    func postData(path: String, body: [String: Any], timeout: TimeInterval = 60) async throws -> Data {
        let data = try JSONSerialization.data(withJSONObject: body)
        return try await request(path: path, method: "POST", body: data, timeout: timeout)
    }

    private func request(path: String, method: String, body: Data?, timeout: TimeInterval = 60) async throws -> Data {
        guard let url = URL(string: path, relativeTo: baseURL)?.absoluteURL else {
            throw APIError.badURL
        }
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.timeoutInterval = timeout
        req.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = body
        let (data, resp) = try await session.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw APIError.http(-1, "no response") }
        guard (200..<300).contains(http.statusCode) else {
            let text = String(data: data, encoding: .utf8) ?? ""
            throw APIError.http(http.statusCode, text)
        }
        return data
    }
}
