import Foundation
import Combine

// Observable in-app loop state (plan.md §2: iPhone holds authoritative state).
// SwiftUI surfaces bind to this; every mutation goes through the LoopCommandBus,
// then re-reads. This file is core: it must NOT import AppIntents.

@MainActor
final class LoopStore: ObservableObject {
    @Published var loops: [Loop] = []
    @Published var board: StatusBoard?
    @Published var reviews: [Review] = []
    @Published var errorMessage: String?
    @Published var isLoading = false
    @Published var isSuggesting = false

    // A fresh bus per call reads current settings (base URL / key may change).
    private func bus() -> LoopCommandBus { .fromDefaults() }

    func refresh() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let b = bus()
            async let loopsCall = b.listLoops()
            async let boardCall = b.statusBoard()
            async let reviewsCall = b.pendingReviews()
            loops = try await loopsCall
            board = try await boardCall
            reviews = try await reviewsCall
            errorMessage = nil
            await checkTodaySuggestions()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    /// Ask the server to draft today's suggested next action(s), then refresh
    /// the loop list so the new `next_action` + suggestion draft appear. Pass a
    /// `loopId` for one loop or nil for every active loop; `force` refreshes an
    /// existing same-day suggestion. This is the in-app twin of the daily
    /// cloud-wake job — it only drafts, never externalizes.
    func suggest(loopId: String? = nil, force: Bool = false) async {
        // Coalesce overlapping triggers: rapid repeat taps (or a foreground
        // refresh racing a tap) must not fan out into concurrent POST /v1/suggest
        // calls. The buttons are also `.disabled` while suggesting, but this is
        // the authoritative guard.
        guard !isSuggesting else { return }
        isSuggesting = true
        defer { isSuggesting = false }
        do {
            _ = try await bus().suggest(loopId: loopId, force: force)
            await refresh()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    /// Poll the "suggested today" feed and raise a local notification for any
    /// fresh suggestion the user hasn't been told about yet. Best-effort: a
    /// failure here never surfaces as a loop error.
    func checkTodaySuggestions() async {
        guard let feed = try? await bus().todaysSuggestions() else { return }
        await NotificationManager.shared.notifyFreshSuggestions(feed)
    }

    // -- in-app twins of the App Intents --

    func newLoop(title: String, domain: LoopDomain, why: String, text: String) async {
        await run { _ = try await self.bus().newLoop(title: title, domain: domain, why: why, text: text) }
    }

    func logEvidence(loopId: String, text: String) async {
        await run { _ = try await self.bus().logEvidence(loopId: loopId, text: text) }
    }

    func logPhoto(loopId: String, label: String, pointer: String?) async {
        await run { _ = try await self.bus().logEvidence(loopId: loopId, text: label, kind: "photo", pointer: pointer) }
    }

    /// Save a durable global note/fact — the in-app twin of the Quick Note
    /// intent. Goes through the `remember` command (global memory); it never
    /// externalizes. Use for quick after-a-call/meeting capture.
    func remember(text: String) async {
        await run { _ = try await self.bus().remember(text: text) }
    }

    /// Remove all AI suggestion drafts for a loop and reset its suggested
    /// action. In-app twin of `clear_suggestions`; local and reversible (the
    /// user can regenerate). Never externalizes.
    func clearSuggestions(loopId: String) async {
        await run { _ = try await self.bus().clearSuggestions(loopId: loopId) }
    }

    func pause(loopId: String) async {
        await run { _ = try await self.bus().pause(loopId: loopId) }
    }

    func resume(loopId: String) async {
        await run { _ = try await self.bus().resume(loopId: loopId) }
    }

    func approvePlan(loopId: String) async {
        await run { _ = try await self.bus().approvePlan(loopId: loopId) }
    }

    func markComplete(loopId: String) async {
        await run { _ = try await self.bus().markComplete(loopId: loopId) }
    }

    func addDraft(loopId: String, kind: String, content: String) async {
        await run { _ = try await self.bus().addDraft(loopId: loopId, kind: kind, content: content) }
    }

    /// Authenticated foreground review + externalize. The user has explicitly
    /// tapped "Approve & Send" in the app, which mints a one-time review token
    /// and then externalizes. This is the ONLY path that sends — never Siri,
    /// never background.
    func reviewAndExternalize(loopId: String, draftId: String, action: String) async {
        await run {
            let b = self.bus()
            let req = try await b.requestReview(loopId: loopId, action: action, draftId: draftId)
            guard let rid = req.reviewId else { return }
            let res = try await b.resolveReview(reviewId: rid, approved: true)
            guard let token = res.reviewToken else { return }
            _ = try await b.externalize(loopId: loopId, draftId: draftId, reviewToken: token)
        }
    }

    private func run(_ op: @escaping () async throws -> Void) async {
        do {
            try await op()
            await refresh()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
