import SwiftUI

struct ChatView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 10) {
                            ForEach(appState.items) { item in
                                row(item)
                                    .id(item.id)
                            }
                        }
                        .padding()
                    }
                    .onChange(of: appState.items.count) { _, _ in
                        if let last = appState.items.last {
                            withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                        }
                    }
                }

                if let err = appState.errorMessage {
                    Text(err)
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal)
                }

                Text(appState.statusLine)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal)

                Divider()
                composer
            }
            .navigationTitle("Chitti")
        }
    }

    @ViewBuilder
    private func row(_ item: ChatItem) -> some View {
        switch item.kind {
        case .user:
            bubble(item.text, align: .trailing, color: Color.blue.opacity(0.15))
        case .assistant:
            bubble(item.text, align: .leading, color: Color.gray.opacity(0.12))
        case .tool:
            Text(item.text)
                .font(.caption.monospaced())
                .foregroundStyle(.secondary)
        case .system:
            Text(item.text)
                .font(.footnote)
                .foregroundStyle(.orange)
        case .approval:
            ApprovalCard(item: item) { approved in
                if let id = item.approvalId {
                    Task { await appState.approve(id: id, approved: approved) }
                }
            }
        }
    }

    private func bubble(_ text: String, align: HorizontalAlignment, color: Color) -> some View {
        HStack {
            if align == .trailing { Spacer(minLength: 40) }
            Text(text)
                .padding(10)
                .background(color)
                .clipShape(RoundedRectangle(cornerRadius: 12))
            if align == .leading { Spacer(minLength: 40) }
        }
    }

    private var composer: some View {
        VStack(spacing: 8) {
            if appState.speech.isRecording {
                Text(appState.speech.liveTranscript.isEmpty
                      ? "Listening…"
                      : appState.speech.liveTranscript)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal)
            }
            HStack(alignment: .bottom, spacing: 8) {
                TextField("Message Chitti…", text: $appState.draft, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                    .lineLimit(1...5)

                Button {
                    Task { await toggleVoice() }
                } label: {
                    Image(systemName: appState.speech.isRecording ? "stop.circle.fill" : "mic.circle.fill")
                        .font(.system(size: 32))
                        .foregroundStyle(appState.speech.isRecording ? .red : .primary)
                }
                .accessibilityLabel(appState.speech.isRecording ? "Stop recording" : "Push to talk")

                Button {
                    Task { await appState.sendDraft() }
                } label: {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.system(size: 32))
                }
                .disabled(appState.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                          || appState.isRunningTurn)
            }
            .padding()
        }
    }

    private func toggleVoice() async {
        if appState.speech.isRecording {
            appState.speech.stop()
            if !appState.speech.liveTranscript.isEmpty {
                appState.draft = appState.speech.liveTranscript
            }
        } else {
            let ok = await appState.speech.requestPermissions()
            guard ok else {
                appState.errorMessage = "Mic / speech permission denied"
                return
            }
            do {
                try appState.speech.start()
            } catch {
                appState.errorMessage = error.localizedDescription
            }
        }
    }
}
