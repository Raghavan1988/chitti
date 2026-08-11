import SwiftUI
import PhotosUI
import UIKit

// Loop detail: in-app twins for LogEvidence, Pause/Resume, ApprovePlan,
// MarkComplete, add-draft, and the authenticated foreground Review & Send
// (the only path that externalizes a draft).

struct LoopDetailView: View {
    @EnvironmentObject var store: LoopStore
    @EnvironmentObject var appState: AppState
    let loopId: String

    @State private var newEvidence = ""
    @State private var showingCompose = false
    @State private var reviewDraft: Draft?
    @State private var photoItem: PhotosPickerItem?
    @State private var showCamera = false
    @State private var showClearConfirm = false
    @State private var briefingPostText = ""
    @State private var audioLoading = false

    private var loop: Loop? { store.loops.first(where: { $0.id == loopId }) }

    // The most recent AI suggestion draft — surfaced prominently so tapping
    // "Suggest actions" / "New suggestion" produces a visible result instead of
    // a silently-appended draft buried at the bottom of the form.
    private var latestSuggestion: Draft? {
        loop?.drafts.last(where: { $0.kind == "suggestion" })
    }

    // The most recent web-grounded deep-research report (key insights),
    // surfaced in its own section like suggestions.
    private var latestResearch: Draft? {
        loop?.drafts.last(where: { $0.kind == "research" })
    }

    var body: some View {
        Group {
            if let loop {
                Form {
                    header(loop)
                    briefingSection(loop)
                    suggestionSection(loop)
                    researchSection(loop)
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
        .task {
            await store.refresh()
            await store.loadBriefing(loopId: loopId)
            if briefingPostText.isEmpty, let t = store.briefings[loopId]?.post.text {
                briefingPostText = t
            }
        }
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

    // -- Daily Briefing (PRD §4): audio digest + editable X post + person.

    @ViewBuilder
    private func briefingSection(_ loop: Loop) -> some View {
        Section {
            if let b = store.briefings[loopId] {
                briefingBody(loop, b)
            } else {
                Button {
                    Task {
                        await store.generateBriefing(loopId: loop.id)
                        if let t = store.briefings[loopId]?.post.text { briefingPostText = t }
                    }
                } label: {
                    if store.isBriefing {
                        HStack(spacing: 8) { ProgressView(); Text("Preparing briefing…") }
                    } else {
                        Label("Generate today's briefing", systemImage: "sun.max")
                    }
                }
                .disabled(store.isBriefing)
                Text("A morning digest you can listen to, an editable X post, and a person worth knowing — grounded in fresh research.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        } header: {
            Label("Daily Briefing", systemImage: "sunrise")
        }
    }

    @ViewBuilder
    private func briefingBody(_ loop: Loop, _ b: Briefing) -> some View {
        digestBlock(b)
        postBlock(loop, b)
        personBlock(loop, b)
        Button {
            Task {
                await store.generateBriefing(loopId: loop.id, force: true)
                if let t = store.briefings[loopId]?.post.text { briefingPostText = t }
            }
        } label: {
            if store.isBriefing {
                HStack(spacing: 8) { ProgressView(); Text("Refreshing…") }
            } else {
                Label("Refresh briefing", systemImage: "arrow.clockwise")
            }
        }
        .disabled(store.isBriefing)
    }

    @ViewBuilder
    private func digestBlock(_ b: Briefing) -> some View {
        if !(b.dismissed?["digest"] ?? false) {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Label("Audio digest", systemImage: "waveform").font(.subheadline.bold())
                    Spacer()
                    Text(b.date).font(.caption2).foregroundStyle(.secondary)
                    dismissButton(item: "digest")
                }
                Button {
                    Task { await playDigest(b) }
                } label: {
                    if audioLoading {
                        HStack(spacing: 6) { ProgressView(); Text("Loading…") }
                    } else if appState.speech.isPlaying {
                        Label("Stop", systemImage: "stop.fill")
                    } else {
                        Label("Listen", systemImage: "play.fill")
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(audioLoading || b.digest.transcript.isEmpty)

                if !b.digest.transcript.isEmpty {
                    Text(b.digest.transcript).font(.subheadline)
                }
                ForEach(Array(b.digest.key_points.enumerated()), id: \.offset) { _, p in
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: "circle.fill")
                            .font(.system(size: 5)).foregroundStyle(.blue).padding(.top, 6)
                        Text(p).font(.subheadline)
                    }
                }
                if !b.sources.isEmpty {
                    Text("SOURCES").font(.caption).bold().foregroundStyle(.secondary).padding(.top, 2)
                    ForEach(Array(b.sources.enumerated()), id: \.offset) { _, s in
                        if let url = URL(string: s) {
                            HStack(alignment: .top, spacing: 8) {
                                Image(systemName: "link").font(.caption).foregroundStyle(.blue)
                                Link(hostFor(url), destination: url).font(.caption)
                            }
                        }
                    }
                }
            }
            .padding(.vertical, 2)
        }
    }

    @ViewBuilder
    private func postBlock(_ loop: Loop, _ b: Briefing) -> some View {
        if !(b.dismissed?["post"] ?? false) {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Label("Suggested X post", systemImage: "text.bubble").font(.subheadline.bold())
                    Spacer()
                    dismissButton(item: "post")
                }
                TextEditor(text: $briefingPostText)
                    .frame(minHeight: 92)
                    .font(.subheadline)
                    .overlay(RoundedRectangle(cornerRadius: 6).stroke(.quaternary))
                HStack {
                    Text("\(briefingPostText.count) chars")
                        .font(.caption2)
                        .foregroundStyle(briefingPostText.count > 280 ? .red : .secondary)
                    Spacer()
                    Button("Reset") { briefingPostText = b.post.text }
                        .font(.caption)
                        .disabled(briefingPostText == b.post.text)
                }
                Button {
                    Task {
                        let text = briefingPostText.trimmingCharacters(in: .whitespacesAndNewlines)
                        guard !text.isEmpty else { return }
                        if let id = await store.createDraft(loopId: loop.id, kind: "post", content: text),
                           let d = store.loops.first(where: { $0.id == loop.id })?
                               .drafts.first(where: { $0.id == id }) {
                            reviewDraft = d
                        }
                    }
                } label: {
                    Label("Review & post to X", systemImage: "paperplane")
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(briefingPostText.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            .padding(.vertical, 2)
        }
    }

    @ViewBuilder
    private func personBlock(_ loop: Loop, _ b: Briefing) -> some View {
        let p = b.person
        if !(b.dismissed?["person"] ?? false) && !p.name.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Label("Person to know", systemImage: "person.crop.circle")
                        .font(.subheadline.bold())
                    Spacer()
                    Badge(text: "discovered", tint: .orange)
                    dismissButton(item: "person")
                }
                Text(p.name).font(.subheadline.bold())
                if let url = URL(string: p.profile_url), !p.profile_url.isEmpty {
                    Link(destination: url) {
                        Label(p.platform.isEmpty ? "profile" : p.platform.uppercased(),
                              systemImage: "link").font(.caption)
                    }
                } else if !p.platform.isEmpty {
                    Text(p.platform.uppercased()).font(.caption).foregroundStyle(.secondary)
                }
                if !p.context.isEmpty { Text(p.context).font(.subheadline) }
                if !p.why_relevant.isEmpty {
                    Text("Why relevant: \(p.why_relevant)")
                        .font(.caption).foregroundStyle(.secondary)
                }
                if !p.engagement_tips.isEmpty {
                    Text("HOW TO ENGAGE").font(.caption).bold()
                        .foregroundStyle(.secondary).padding(.top, 2)
                    ForEach(Array(p.engagement_tips.enumerated()), id: \.offset) { _, t in
                        HStack(alignment: .top, spacing: 8) {
                            Image(systemName: "hand.wave").font(.caption).foregroundStyle(.blue)
                            Text(t).font(.caption)
                        }
                    }
                }
                Text("Public professional info only — verify before engaging. SignalLoop never messages people for you.")
                    .font(.caption2).foregroundStyle(.secondary).padding(.top, 2)
                Button {
                    Task {
                        var note = "Person to know for \(loop.title): \(p.name)"
                        if !p.profile_url.isEmpty { note += " (\(p.profile_url))" }
                        if !p.context.isEmpty { note += " — \(p.context)" }
                        await store.remember(text: note)
                    }
                } label: { Label("Save", systemImage: "bookmark") }
                    .buttonStyle(.bordered).controlSize(.small)
            }
            .padding(.vertical, 2)
        }
    }

    // A per-item close/dismiss control. Local and reversible — dismissing hides
    // the item until the next briefing (or a Refresh regenerates it).
    @ViewBuilder
    private func dismissButton(item: String) -> some View {
        Button {
            Task { await store.briefingFeedback(loopId: loopId, item: item, dismissed: true) }
        } label: {
            Image(systemName: "xmark.circle.fill")
                .imageScale(.large)
                .foregroundStyle(.secondary)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Dismiss \(item)")
    }

    private func playDigest(_ b: Briefing) async {
        if appState.speech.isPlaying {
            appState.speech.stopPlayback()
            return
        }
        audioLoading = true
        defer { audioLoading = false }
        if let data = await store.briefingAudio(loopId: loopId), appState.speech.play(data) {
            return
        }
        // Fall back to on-device speech if the server audio is unavailable.
        appState.speech.speak(b.digest.transcript)
    }

    private func hostFor(_ url: URL) -> String {
        guard let host = url.host else { return url.absoluteString }
        let path = url.path
        return host + (path == "/" || path.isEmpty ? "" : path)
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
    private func researchSection(_ loop: Loop) -> some View {
        if let research = latestResearch {
            Section {
                ResearchContent(text: research.content)
                Button(role: .destructive) {
                    Task { await store.deleteDraft(loopId: loopId, draftId: research.id) }
                } label: {
                    Label("Clear research", systemImage: "trash")
                }
            } header: {
                Label("Key insights", systemImage: "lightbulb")
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
            Button {
                Task { await store.deepResearch(loopId: loop.id) }
            } label: {
                if store.isResearching {
                    HStack(spacing: 8) { ProgressView(); Text("Researching…") }
                } else {
                    Label("Deep research", systemImage: "magnifyingglass")
                }
            }
            .disabled(store.isResearching)
            if latestResearch != nil {
                Button {
                    Task { await store.deepResearch(loopId: loop.id, force: true) }
                } label: {
                    Label("Refresh research", systemImage: "arrow.clockwise")
                }
                .disabled(store.isResearching)
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
        // Suggestions and research render in their own sections above; this
        // section is only for reviewable/sendable drafts (email/post/note).
        let sendable = loop.drafts.filter { $0.kind != "suggestion" && $0.kind != "research" }
        if !sendable.isEmpty {
            Section("Drafts") {
                ForEach(sendable) { draft in
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(alignment: .top) {
                            Text(draft.content).font(.subheadline).lineLimit(4)
                            Spacer(minLength: 8)
                            Button {
                                Task { await store.deleteDraft(loopId: loopId, draftId: draft.id) }
                            } label: {
                                Image(systemName: "xmark.circle.fill")
                                    .imageScale(.large)
                                    .foregroundStyle(.secondary)
                            }
                            .buttonStyle(.plain)
                            .accessibilityLabel("Delete draft")
                        }
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
                    .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                        Button(role: .destructive) {
                            Task { await store.deleteDraft(loopId: loopId, draftId: draft.id) }
                        } label: {
                            Label("Delete", systemImage: "trash")
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

// Renders a deep-research report: section labels (e.g. "Key insights:") as
// small headers, "- " items as bullets, and any bare URL (the "Sources:" list)
// as a tappable link. Non-sendable — research is for reading, not externalizing.
struct ResearchContent: View {
    let text: String

    private var lines: [String] {
        text.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(lines.enumerated()), id: \.offset) { _, raw in
                let line = raw.trimmingCharacters(in: .whitespaces)
                if line.isEmpty {
                    EmptyView()
                } else if line.hasSuffix(":") && !line.hasPrefix("-") && !line.hasPrefix("•") {
                    Text(line.dropLast())
                        .font(.caption).bold()
                        .foregroundStyle(.secondary)
                        .textCase(.uppercase)
                        .padding(.top, 2)
                } else if line.hasPrefix("- ") || line.hasPrefix("• ") {
                    let item = String(line.dropFirst(2))
                    if let url = bareURL(item) {
                        HStack(alignment: .top, spacing: 8) {
                            Image(systemName: "link").font(.caption).foregroundStyle(.blue)
                            Link(displayHost(url), destination: url).font(.caption)
                        }
                    } else {
                        HStack(alignment: .top, spacing: 8) {
                            Image(systemName: "circle.fill")
                                .font(.system(size: 5)).foregroundStyle(.blue)
                                .padding(.top, 6)
                            Text(item).font(.subheadline)
                        }
                    }
                } else {
                    Text(line).font(.subheadline)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 2)
    }

    private func bareURL(_ s: String) -> URL? {
        guard s.hasPrefix("http://") || s.hasPrefix("https://") else { return nil }
        return URL(string: s)
    }

    private func displayHost(_ url: URL) -> String {
        guard let host = url.host else { return url.absoluteString }
        let path = url.path
        return host + (path == "/" || path.isEmpty ? "" : path)
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
