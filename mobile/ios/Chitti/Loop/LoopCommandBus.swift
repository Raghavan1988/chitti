import Foundation

// The on-device LoopCommandBus (plan.md §2). Every surface — SwiftUI, App
// Intents, Share, Widget — funnels intents through this one seam to the
// LoopEngine (POST /v1/commands). Planning and policy live server-side in the
// engine, never in adapters.
//
// This file is core: it must NOT import AppIntents.

/// Thin, typed view over a command result JSON.
struct LoopCommandResult {
    let raw: [String: Any]
    var ok: Bool { (raw["ok"] as? Bool) ?? true }
    var loopId: String? { raw["loop_id"] as? String }
    var evidenceId: String? { raw["evidence_id"] as? String }
    var draftId: String? { raw["draft_id"] as? String }
    var reviewId: String? { raw["review_id"] as? String }
    var reviewToken: String? { raw["review_token"] as? String }
    var externalized: Bool { (raw["externalized"] as? Bool) ?? false }
    var reason: String? { raw["reason"] as? String }
    var idempotent: Bool { (raw["idempotent"] as? Bool) ?? false }
}

/// Submits commands to the server LoopEngine and reads loop state.
final class LoopCommandBus {
    private let api: APIClient

    init(api: APIClient) {
        self.api = api
    }

    /// Build a bus from saved client settings. Used by surfaces without an
    /// AppState (e.g. App Intents the system invokes in the background).
    static func fromDefaults() -> LoopCommandBus {
        let api = APIClient()
        if let data = UserDefaults.standard.data(forKey: "chitti.client.settings"),
           let s = try? JSONDecoder().decode(ClientSettings.self, from: data) {
            api.configure(baseURL: s.baseURL, apiKey: s.apiKey)
        }
        return LoopCommandBus(api: api)
    }

    // Every command carries source + a fresh idempotency_key so repeats (retry,
    // double-tap, re-issued Siri phrase) never duplicate effects.
    @discardableResult
    private func send(
        _ type: String,
        _ payload: [String: Any],
        source: CommandSource
    ) async throws -> LoopCommandResult {
        let body: [String: Any] = [
            "type": type,
            "payload": payload,
            "source": source.rawValue,
            "idempotency_key": UUID().uuidString,
        ]
        let raw = try await api.postJSON(path: "/v1/commands", body: body)
        return LoopCommandResult(raw: raw)
    }

    // -- commands (each has an in-app twin AND an App Intent) --

    @discardableResult
    func newLoop(title: String, domain: LoopDomain = .career, why: String = "",
                 text: String = "", source: CommandSource = .app) async throws -> LoopCommandResult {
        var p: [String: Any] = ["title": title, "domain": domain.rawValue]
        if !why.isEmpty { p["why_it_matters"] = why }
        if !text.isEmpty { p["text"] = text }
        return try await send("new_loop", p, source: source)
    }

    @discardableResult
    func logEvidence(loopId: String, text: String? = nil, url: String? = nil,
                     kind: String = "note", pointer: String? = nil,
                     source: CommandSource = .app) async throws -> LoopCommandResult {
        var p: [String: Any] = ["loop_id": loopId, "kind": kind]
        if let text { p["text"] = text }
        if let url { p["url"] = url }
        if let pointer { p["pointer"] = pointer }
        return try await send("log_evidence", p, source: source)
    }

    @discardableResult
    func pause(loopId: String, source: CommandSource = .app) async throws -> LoopCommandResult {
        try await send("pause", ["loop_id": loopId], source: source)
    }

    @discardableResult
    func resume(loopId: String, source: CommandSource = .app) async throws -> LoopCommandResult {
        try await send("resume", ["loop_id": loopId], source: source)
    }

    @discardableResult
    func approvePlan(loopId: String, source: CommandSource = .app) async throws -> LoopCommandResult {
        try await send("approve_plan", ["loop_id": loopId], source: source)
    }

    @discardableResult
    func markComplete(loopId: String, outcome: String? = nil,
                      source: CommandSource = .app) async throws -> LoopCommandResult {
        var p: [String: Any] = ["loop_id": loopId]
        if let outcome { p["outcome"] = outcome }
        return try await send("mark_complete", p, source: source)
    }

    @discardableResult
    func addDraft(loopId: String, kind: String, content: String,
                  source: CommandSource = .app) async throws -> LoopCommandResult {
        try await send("add_draft", ["loop_id": loopId, "kind": kind, "content": content], source: source)
    }

    @discardableResult
    func deleteDraft(loopId: String, draftId: String,
                     source: CommandSource = .app) async throws -> LoopCommandResult {
        try await send("delete_draft", ["loop_id": loopId, "draft_id": draftId], source: source)
    }

    @discardableResult
    func requestReview(loopId: String, action: String, draftId: String? = nil,
                       source: CommandSource = .app) async throws -> LoopCommandResult {
        var p: [String: Any] = ["loop_id": loopId, "action": action]
        if let draftId { p["draft_id"] = draftId }
        return try await send("request_review", p, source: source)
    }

    @discardableResult
    func resolveReview(reviewId: String, approved: Bool,
                       source: CommandSource = .app) async throws -> LoopCommandResult {
        try await send("resolve_review", ["review_id": reviewId, "approved": approved], source: source)
    }

    @discardableResult
    func externalize(loopId: String, draftId: String, reviewToken: String,
                     source: CommandSource = .app) async throws -> LoopCommandResult {
        try await send("externalize",
                       ["loop_id": loopId, "draft_id": draftId, "review_token": reviewToken],
                       source: source)
    }

    @discardableResult
    func remember(text: String, source: CommandSource = .app) async throws -> LoopCommandResult {
        try await send("remember", ["text": text], source: source)
    }

    @discardableResult
    func clearSuggestions(loopId: String, source: CommandSource = .app) async throws -> LoopCommandResult {
        try await send("clear_suggestions", ["loop_id": loopId], source: source)
    }

    // -- reads --

    func listLoops() async throws -> [Loop] {
        let data = try await api.getData(path: "/v1/loops")
        return try JSONDecoder().decode(LoopsResponse.self, from: data).loops
    }

    func getLoop(_ id: String) async throws -> Loop {
        let data = try await api.getData(path: "/v1/loops/\(id)")
        return try JSONDecoder().decode(Loop.self, from: data)
    }

    func statusBoard(locked: Bool = false) async throws -> StatusBoard {
        let path = locked ? "/v1/status?locked=1" : "/v1/status"
        let data = try await api.getData(path: path)
        return try JSONDecoder().decode(StatusBoard.self, from: data)
    }

    func pendingReviews() async throws -> [Review] {
        let data = try await api.getData(path: "/v1/reviews")
        return try JSONDecoder().decode(ReviewsResponse.self, from: data).reviews
    }

    // -- suggestions (server-layer "give me next action(s)"; still command-bus
    //    backed writes, so the engine stays the source of truth) --

    /// Ask the server to draft today's suggested next action(s). Pass a
    /// `loopId` to target one loop, or nil for every active loop. `force`
    /// refreshes even if a suggestion already exists for today.
    @discardableResult
    func suggest(loopId: String? = nil, force: Bool = false) async throws -> SuggestResponse {
        var body: [String: Any] = [:]
        if let loopId { body["loop_id"] = loopId }
        if force { body["force"] = true }
        let data = try await api.postData(path: "/v1/suggest", body: body)
        return try JSONDecoder().decode(SuggestResponse.self, from: data)
    }

    /// Ask the server to run web-grounded deep research for a loop and write a
    /// reviewable ``research`` draft of key insights. Uses a longer timeout
    /// since the live web search can take a while. `force` refreshes even if a
    /// report already exists for today.
    @discardableResult
    func research(loopId: String, force: Bool = false) async throws -> ResearchResponse {
        var body: [String: Any] = ["loop_id": loopId]
        if force { body["force"] = true }
        let data = try await api.postData(path: "/v1/research", body: body, timeout: 180)
        return try JSONDecoder().decode(ResearchResponse.self, from: data)
    }

    /// Active loops that received a suggestion draft today (for notifications).
    func todaysSuggestions() async throws -> TodayFeed {
        let data = try await api.getData(path: "/v1/suggestions/today")
        return try JSONDecoder().decode(TodayFeed.self, from: data)
    }

    // -- Daily Briefing (server-layer; the unit the daily cloud-wake job runs).
    //    Generation only drafts a reviewable briefing — it never externalizes.

    /// Generate today's Daily Briefing (audio-digest transcript, editable X
    /// post, person-to-know) for a loop. Long timeout: it runs a live web
    /// research pass plus a model call. `force` regenerates today's briefing.
    @discardableResult
    func generateBriefing(loopId: String, force: Bool = false) async throws -> BriefingRunResponse {
        var body: [String: Any] = ["loop_id": loopId]
        if force { body["force"] = true }
        let data = try await api.postData(path: "/v1/briefing", body: body, timeout: 180)
        return try JSONDecoder().decode(BriefingRunResponse.self, from: data)
    }

    /// Today's stored briefing for a loop, or nil if none exists yet.
    func getBriefing(loopId: String) async throws -> Briefing? {
        let data = try await api.getData(path: "/v1/loops/\(loopId)/briefing")
        return try? JSONDecoder().decode(Briefing.self, from: data)
    }

    /// The digest audio (mp3 bytes), synthesized lazily on the server.
    func briefingAudio(loopId: String) async throws -> Data {
        try await api.getData(path: "/v1/loops/\(loopId)/briefing/audio")
    }

    /// Rate/dismiss one briefing item ("digest"|"post"|"person"); returns the
    /// updated briefing.
    @discardableResult
    func briefingFeedback(loopId: String, item: String, rating: String? = nil,
                          dismissed: Bool? = nil) async throws -> Briefing? {
        var body: [String: Any] = ["item": item]
        if let rating { body["rating"] = rating }
        if let dismissed { body["dismissed"] = dismissed }
        let data = try await api.postData(
            path: "/v1/loops/\(loopId)/briefing/feedback", body: body)
        return try? JSONDecoder().decode(Briefing.self, from: data)
    }
}
