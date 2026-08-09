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
        } catch {
            errorMessage = error.localizedDescription
        }
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
