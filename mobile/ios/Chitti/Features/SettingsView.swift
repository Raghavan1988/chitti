import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var appState: AppState
    @State private var memoryPreview = ""
    @State private var busy = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Server") {
                    TextField("Base URL", text: $appState.settings.baseURL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                    SecureField("API key", text: $appState.settings.apiKey)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    Button("Save connection") {
                        appState.saveSettings()
                        appState.statusLine = "Settings saved"
                    }
                    Text("Physical iPhone: use http://<mac-lan-ip>:8787 from ./scripts/run-server.sh — not 127.0.0.1. Simulator may use 127.0.0.1.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section("Voice") {
                    Toggle("Speak final replies", isOn: $appState.settings.speakReplies)
                        .onChange(of: appState.settings.speakReplies) { _, _ in
                            appState.saveSettings()
                        }
                }

                Section("Session") {
                    LabeledContent("Session") {
                        Text(appState.sessionId?.prefix(8).description ?? "—")
                            .foregroundStyle(.secondary)
                    }
                    Button("Reset session", role: .destructive) {
                        appState.stream.stop()
                        appState.sessionId = nil
                        appState.items.removeAll()
                        appState.isRunningTurn = false
                        appState.statusLine = "Session cleared"
                    }
                }

                Section("Memory (server CHITTI.md)") {
                    if memoryPreview.isEmpty {
                        Text("Tap refresh to load")
                            .foregroundStyle(.secondary)
                    } else {
                        Text(memoryPreview)
                            .font(.footnote.monospaced())
                    }
                    Button(busy ? "Loading…" : "Refresh memory") {
                        Task {
                            busy = true
                            defer { busy = false }
                            do {
                                appState.saveSettings()
                                memoryPreview = try await appState.api.fetchMemory()
                                if memoryPreview.isEmpty { memoryPreview = "(empty)" }
                            } catch {
                                memoryPreview = error.localizedDescription
                            }
                        }
                    }
                    .disabled(busy)
                }

                Section("About") {
                    Text("Chitti is a personal ops agent. Siri can launch it; Chitti does multi-step work with approvals.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Settings")
        }
    }
}
