import SwiftUI
import PhotosUI
import UIKit

// Loop detail: in-app twins for LogEvidence, Pause/Resume, ApprovePlan,
// MarkComplete, add-draft, and the authenticated foreground Review & Send
// (the only path that externalizes a draft).

struct LoopDetailView: View {
    @EnvironmentObject var store: LoopStore
    let loopId: String

    @State private var newEvidence = ""
    @State private var showingCompose = false
    @State private var reviewDraft: Draft?
    @State private var photoItem: PhotosPickerItem?
    @State private var showCamera = false
    @State private var showClearConfirm = false

    private var loop: Loop? { store.loops.first(where: { $0.id == loopId }) }

    // The most recent AI suggestion draft — surfaced prominently so tapping
    // "Suggest actions" / "New suggestion" produces a visible result instead of
    // a silently-appended draft buried at the bottom of the form.
    private var latestSuggestion: Draft? {
        loop?.drafts.last(where: { $0.kind == "suggestion" })
    }

    var body: some View {
        Group {
            if let loop {
                Form {
                    header(loop)
                    suggestionSection(loop)
                    actions(loop)
                    evidenceSection(loop)
                    draftsSection(loop)
                }
            } else {
                ProgressView()
            }
        }
        .navigationTitle(loop?.domainEnum.label ?? "Loop")
        .navigationBarTitleDisplayMode(.inline)
        .task { await store.refresh() }
        .sheet(isPresented: $showingCompose) {
            ComposeDraftSheet(loopId: loopId).environmentObject(store)
        }
        .sheet(item: $reviewDraft) { draft in
            ReviewSheet(loopId: loopId, draft: draft).environmentObject(store)
        }
        .onChange(of: photoItem) { _, newItem in
            guard let newItem else { return }
            Task {
                let pointer = newItem.itemIdentifier
                await store.logPhoto(loopId: loopId, label: "[photo] attached", pointer: pointer)
                photoItem = nil
            }
        }
        .sheet(isPresented: $showCamera) {
            CameraPicker { _ in
                Task { await store.logPhoto(loopId: loopId, label: "[camera photo]", pointer: nil) }
            }
        }
        .confirmationDialog(
            "Clear all suggested actions for this loop?",
            isPresented: $showClearConfirm,
            titleVisibility: .visible
        ) {
            Button("Clear suggestions", role: .destructive) {
                Task { await store.clearSuggestions(loopId: loopId) }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Removes the AI suggestions and resets today's suggested action. You can generate a new one anytime.")
        }
    }

    @ViewBuilder
    private func suggestionSection(_ loop: Loop) -> some View {
        if let suggestion = latestSuggestion {
            Section {
                SuggestionContent(text: suggestion.content)
                Button(role: .destructive) {
                    showClearConfirm = true
                } label: {
                    Label("Clear suggestions", systemImage: "trash")
                }
            } header: {
                Label("Suggested actions", systemImage: "sparkles")
            }
        }
    }

    @ViewBuilder
    private func header(_ loop: Loop) -> some View {
        Section {
            Text(loop.title).font(.headline)
            HStack {
                Badge(text: loop.domainEnum.label, tint: .blue)
                Badge(text: loop.status, tint: statusTint(loop.status))
                if loop.plan_approved { Badge(text: "plan approved", tint: .green) }
            }
            if !loop.why_it_matters.isEmpty {
                Text(loop.why_it_matters).font(.subheadline).foregroundStyle(.secondary)
            }
            if !loop.next_action.isEmpty {
                Label(loop.next_action, systemImage: "arrow.right.circle")
                    .font(.subheadline)
            }
            if let outcome = loop.outcome, !outcome.isEmpty {
                Label(outcome, systemImage: "flag.checkered").font(.subheadline)
            }
        }
    }

    @ViewBuilder
    private func actions(_ loop: Loop) -> some View {
        Section("Actions") {
            Button {
                Task { await store.suggest(loopId: loop.id) }
            } label: {
                if store.isSuggesting {
                    HStack(spacing: 8) { ProgressView(); Text("Suggesting…") }
                } else {
                    Label("Suggest actions", systemImage: "sparkles")
                }
            }
            .disabled(store.isSuggesting)
            if !loop.next_action.isEmpty {
                Button {
                    Task { await store.suggest(loopId: loop.id, force: true) }
                } label: {
                    Label("New suggestion", systemImage: "arrow.clockwise")
                }
                .disabled(store.isSuggesting)
            }
            if loop.isPaused {
                Button { Task { await store.resume(loopId: loop.id) } } label: {
                    Label("Resume", systemImage: "play.circle")
                }
            } else if !loop.isDone {
                Button { Task { await store.pause(loopId: loop.id) } } label: {
                    Label("Pause", systemImage: "pause.circle")
                }
            }
            if !loop.plan_approved {
                Button { Task { await store.approvePlan(loopId: loop.id) } } label: {
                    Label("Approve plan", systemImage: "checkmark.seal")
                }
            }
            if !loop.isDone {
                Button { Task { await store.markComplete(loopId: loop.id) } } label: {
                    Label("Mark complete", systemImage: "checkmark.circle")
                }
            }
            Button { showingCompose = true } label: {
                Label("Add draft", systemImage: "square.and.pencil")
            }
        }
    }

    @ViewBuilder
    private func evidenceSection(_ loop: Loop) -> some View {
        Section("Evidence") {
            ForEach(loop.evidence) { ev in
                VStack(alignment: .leading, spacing: 2) {
                    Text(ev.text ?? ev.url ?? ev.pointer ?? "(evidence)")
                        .font(.subheadline)
                    Text(ev.kind).font(.caption2).foregroundStyle(.secondary)
                }
            }
            HStack {
                TextField("Log evidence…", text: $newEvidence, axis: .vertical)
                Button {
                    let text = newEvidence.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !text.isEmpty else { return }
                    newEvidence = ""
                    Task { await store.logEvidence(loopId: loop.id, text: text) }
                } label: {
                    Image(systemName: "plus.circle.fill")
                }
                .disabled(newEvidence.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            HStack {
                PhotosPicker(selection: $photoItem, matching: .images) {
                    Label("Attach photo", systemImage: "photo")
                }
                if UIImagePickerController.isSourceTypeAvailable(.camera) {
                    Spacer()
                    Button { showCamera = true } label: {
                        Label("Camera", systemImage: "camera")
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func draftsSection(_ loop: Loop) -> some View {
        // Suggestions render in their own "Suggested actions" section above;
        // this section is only for reviewable/sendable drafts (email/post/note).
        let sendable = loop.drafts.filter { $0.kind != "suggestion" }
        if !sendable.isEmpty {
            Section("Drafts") {
                ForEach(sendable) { draft in
                    VStack(alignment: .leading, spacing: 6) {
                        Text(draft.content).font(.subheadline).lineLimit(4)
                        HStack {
                            Badge(text: draft.kind, tint: .purple)
                            if draft.externalized {
                                Badge(text: "sent", tint: .green)
                            } else {
                                Spacer()
                                Button("Review & Send") { reviewDraft = draft }
                                    .buttonStyle(.borderedProminent)
                                    .controlSize(.small)
                            }
                        }
                    }
                }
            }
        }
    }
}

// Renders a suggestion draft's content — a short "Suggested actions" list plus
// an optional "Why:" line — as a readable, non-sendable recommendation. Falls
// back to plain lines for any non-bulleted model output.
struct SuggestionContent: View {
    let text: String

    private var lines: [String] {
        text.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(Array(lines.enumerated()), id: \.offset) { _, raw in
                let line = raw.trimmingCharacters(in: .whitespaces)
                if line.isEmpty || line.lowercased().hasPrefix("suggested actions") {
                    EmptyView()
                } else if line.hasPrefix("- ") || line.hasPrefix("• ") {
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: "checkmark.circle")
                            .foregroundStyle(.blue)
                        Text(line.dropFirst(2)).font(.subheadline)
                    }
                } else if line.lowercased().hasPrefix("why:") {
                    Text(line).font(.caption).foregroundStyle(.secondary)
                } else {
                    Text(line).font(.subheadline)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 2)
    }
}

// Add a draft (safe — never externalizes on creation).
struct ComposeDraftSheet: View {
    @EnvironmentObject var store: LoopStore
    @Environment(\.dismiss) private var dismiss
    let loopId: String

    @State private var kind = "email"
    @State private var content = ""

    var body: some View {
        NavigationStack {
            Form {
                Picker("Kind", selection: $kind) {
                    Text("Email").tag("email")
                    Text("Post").tag("post")
                    Text("Note").tag("note")
                }
                Section("Content") {
                    TextField("Draft…", text: $content, axis: .vertical)
                        .frame(minHeight: 120, alignment: .top)
                }
            }
            .navigationTitle("New Draft")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        Task {
                            await store.addDraft(loopId: loopId, kind: kind, content: content)
                            dismiss()
                        }
                    }
                    .disabled(content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
    }
}

// Authenticated foreground review. The user reads the exact draft and taps
// "Approve & Send" — which mints a review token and externalizes. There is no
// Siri or background path to this action.
struct ReviewSheet: View {
    @EnvironmentObject var store: LoopStore
    @Environment(\.dismiss) private var dismiss
    let loopId: String
    let draft: Draft

    @State private var sending = false

    var body: some View {
        NavigationStack {
            Form {
                Section("This will send") {
                    Text(draft.content)
                    Badge(text: draft.kind, tint: .purple)
                }
                Section {
                    Text("Sending, posting, or committing happens only after this explicit review. It is never triggered by voice or in the background.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                Section {
                    Button {
                        sending = true
                        Task {
                            await store.reviewAndExternalize(
                                loopId: loopId,
                                draftId: draft.id,
                                action: "send \(draft.kind)"
                            )
                            sending = false
                            dismiss()
                        }
                    } label: {
                        if sending {
                            ProgressView()
                        } else {
                            Label("Approve & Send", systemImage: "paperplane.fill")
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(sending)
                }
            }
            .navigationTitle("Review Action")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }
}

// In-app camera capture (the "camera → LogEvidence" twin). Guarded by camera
// availability at the call site, so it is hidden on Simulator. We log a photo
// evidence entry; byte upload is future work once the server exposes a blob
// endpoint.
struct CameraPicker: UIViewControllerRepresentable {
    let onCapture: (UIImage?) -> Void

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(onCapture: onCapture) }

    final class Coordinator: NSObject, UINavigationControllerDelegate, UIImagePickerControllerDelegate {
        let onCapture: (UIImage?) -> Void
        init(onCapture: @escaping (UIImage?) -> Void) { self.onCapture = onCapture }

        func imagePickerController(_ picker: UIImagePickerController,
                                   didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            onCapture(info[.originalImage] as? UIImage)
            picker.dismiss(animated: true)
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            onCapture(nil)
            picker.dismiss(animated: true)
        }
    }
}
