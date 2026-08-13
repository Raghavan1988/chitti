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

                Section("Daily briefing") {
                    Picker("Reminder time", selection: $appState.settings.briefingHour) {
                        ForEach(0..<24, id: \.self) { h in
                            Text(hourLabel(h)).tag(h)
                        }
                    }
                    .onChange(of: appState.settings.briefingHour) { _, newHour in
                        appState.saveSettings()
                        NotificationManager.shared.scheduleDailyReminder(hour: newHour)
                    }
                    Text("Each morning SignalLoop reminds you to open today's briefing (audio digest, an editable X post, and a person to know). Generation runs on the server; open a loop to see and review it.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
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

    private func hourLabel(_ h: Int) -> String {
        let ampm = h < 12 ? "AM" : "PM"
        let base = h % 12 == 0 ? 12 : h % 12
        return "\(base):00 \(ampm)"
    }
}
