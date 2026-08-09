import SwiftUI

// SignalLoop in-app surface: the loop list + status header (twins of the
// Status and NewLoop intents). Loop-centric UI, not a chat.

struct LoopListView: View {
    @EnvironmentObject var store: LoopStore
    @State private var showingNew = false
    @State private var showingCapture = false

    var body: some View {
        NavigationStack {
            List {
                if let board = store.board {
                    Section {
                        HStack {
                            Label("\(board.open) open", systemImage: "circle.dashed")
                            Spacer()
                            if let total = board.total {
                                Text("\(total) total").foregroundStyle(.secondary)
                            }
                        }
                        .font(.subheadline)
                    }
                }

                if store.loops.isEmpty {
                    ContentUnavailableView(
                        "No loops yet",
                        systemImage: "arrow.triangle.2.circlepath",
                        description: Text("Create a career or life loop to start tracking progress.")
                    )
                } else {
                    Section("Loops") {
                        ForEach(store.loops) { loop in
                            NavigationLink(value: loop.id) {
                                LoopRow(loop: loop)
                            }
                        }
                    }
                }

                if let err = store.errorMessage {
                    Section {
                        Label(err, systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.red)
                            .font(.footnote)
                    }
                }
            }
            .navigationTitle("SignalLoop")
            .navigationDestination(for: String.self) { id in
                LoopDetailView(loopId: id)
            }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button {
                        Task { await store.suggest() }
                    } label: {
                        if store.isSuggesting {
                            ProgressView()
                        } else {
                            Image(systemName: "sparkles")
                        }
                    }
                    .accessibilityLabel("Suggest actions for all active loops")
                    .disabled(store.isSuggesting || store.loops.isEmpty)
                }
                ToolbarItem(placement: .topBarLeading) {
                    Button {
                        showingCapture = true
                    } label: {
                        Image(systemName: "square.and.pencil")
                    }
                    .accessibilityLabel("Quick capture a note")
                }
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        showingNew = true
                    } label: {
                        Image(systemName: "plus")
                    }
                    .accessibilityLabel("New loop")
                }
            }
            .refreshable { await store.refresh() }
            .task { await store.refresh() }
            .sheet(isPresented: $showingNew) {
                NewLoopSheet().environmentObject(store)
            }
            .sheet(isPresented: $showingCapture) {
                QuickCaptureSheet().environmentObject(store)
            }
            .onReceive(NotificationCenter.default.publisher(for: .chittiOpenQuickCapture)) { _ in
                showingCapture = true
            }
        }
    }
}

private struct LoopRow: View {
    let loop: Loop

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(loop.title).font(.headline).lineLimit(2)
            HStack(spacing: 8) {
                Badge(text: loop.domainEnum.label, tint: .blue)
                Badge(text: loop.status, tint: statusTint(loop.status))
                if !loop.next_action.isEmpty {
                    Text(loop.next_action)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
        }
        .padding(.vertical, 2)
    }
}

func statusTint(_ status: String) -> Color {
    switch status {
    case "active": return .green
    case "waiting": return .orange
    case "blocked": return .red
    case "paused": return .gray
    case "done": return .secondary
    default: return .secondary
    }
}

struct Badge: View {
    let text: String
    let tint: Color
    var body: some View {
        Text(text)
            .font(.caption2).bold()
            .padding(.horizontal, 6).padding(.vertical, 2)
            .background(tint.opacity(0.15), in: Capsule())
            .foregroundStyle(tint)
    }
}

// Quick Capture in-app twin (of the Quick Note intent): a one-tap note that
// lands in global memory or a chosen loop's evidence. Tap the keyboard mic to
// dictate. Capture is always user-initiated — never scraped from calls/apps.
struct QuickCaptureSheet: View {
    @EnvironmentObject var store: LoopStore
    @Environment(\.dismiss) private var dismiss

    @State private var note = ""
    @State private var targetId = ""   // "" == global memory
    @State private var submitting = false

    private var activeLoops: [Loop] {
        store.loops.filter { $0.status != "done" }
    }

    private var trimmed: String {
        note.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Quick note") {
                    TextField("What happened? Tap the mic to dictate.", text: $note, axis: .vertical)
                        .lineLimit(3...8)
                }
                Section("Save to") {
                    Picker("Destination", selection: $targetId) {
                        Text("Global memory").tag("")
                        ForEach(activeLoops) { loop in
                            Text(loop.title).tag(loop.id)
                        }
                    }
                }
            }
            .navigationTitle("Quick Capture")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        Task {
                            submitting = true
                            if targetId.isEmpty {
                                await store.remember(text: trimmed)
                            } else {
                                await store.logEvidence(loopId: targetId, text: trimmed)
                            }
                            submitting = false
                            dismiss()
                        }
                    }
                    .disabled(trimmed.isEmpty || submitting)
                }
            }
        }
    }
}

// NewLoop in-app twin.
struct NewLoopSheet: View {
    @EnvironmentObject var store: LoopStore
    @Environment(\.dismiss) private var dismiss

    @State private var title = ""
    @State private var domain: LoopDomain = .career
    @State private var why = ""
    @State private var note = ""
    @State private var submitting = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Loop") {
                    TextField("Title", text: $title, axis: .vertical)
                    Picker("Domain", selection: $domain) {
                        ForEach(LoopDomain.allCases) { d in
                            Text(d.label).tag(d)
                        }
                    }
                }
                Section("Why it matters (optional)") {
                    TextField("Motivation", text: $why, axis: .vertical)
                }
                Section("First note (optional)") {
                    TextField("Evidence / context", text: $note, axis: .vertical)
                }
            }
            .navigationTitle("New Loop")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Create") {
                        Task {
                            submitting = true
                            await store.newLoop(title: title, domain: domain, why: why, text: note)
                            submitting = false
                            dismiss()
                        }
                    }
                    .disabled(title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || submitting)
                }
            }
        }
    }
}
