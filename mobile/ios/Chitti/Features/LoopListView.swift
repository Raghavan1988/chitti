import SwiftUI

// SignalLoop in-app surface: the loop list + status header (twins of the
// Status and NewLoop intents). Loop-centric UI, not a chat.

struct LoopListView: View {
    @EnvironmentObject var store: LoopStore
    @State private var showingNew = false

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
