import Foundation

// SignalLoop core data model (plan.md §3). Codable mirrors of the server JSON.
// This file is core: it must NOT import AppIntents.

/// A loop's life domain.
enum LoopDomain: String, CaseIterable, Codable, Identifiable {
    case career, life, both
    var id: String { rawValue }
    var label: String {
        switch self {
        case .career: return "Career"
        case .life: return "Life"
        case .both: return "Both"
        }
    }
}

/// Where a command originated. Adapters set this; the engine treats them equally.
enum CommandSource: String, Codable {
    case app, siri, share, widget, notification, cloud_wake
}

/// One piece of evidence attached to a loop.
struct Evidence: Codable, Identifiable, Equatable {
    let id: String
    var kind: String
    var text: String?
    var url: String?
    var pointer: String?
}

/// A draft (email/post/note). Safe until externalized via a reviewed action.
struct Draft: Codable, Identifiable, Equatable {
    let id: String
    var kind: String
    var content: String
    var externalized: Bool
}

/// A loop the user is trying to advance.
struct Loop: Codable, Identifiable, Equatable {
    let id: String
    var title: String
    var domain: String
    var status: String
    var why_it_matters: String
    var next_action: String
    var waiting_until: String?
    var outcome: String?
    var plan_approved: Bool
    var evidence: [Evidence]
    var drafts: [Draft]

    var domainEnum: LoopDomain { LoopDomain(rawValue: domain) ?? .career }
    var isDone: Bool { status == "done" }
    var isPaused: Bool { status == "paused" }
}

/// A pending consequential-action review that gates externalization.
struct Review: Codable, Identifiable, Equatable {
    let id: String
    var loop_id: String
    var action: String
    var status: String
    var draft_id: String?
    var token: String?
}

/// Status projection from GET /v1/status. `spoken` is the privacy-safe,
/// lock-screen-safe summary used by the Siri Status intent.
struct StatusBoard: Codable, Equatable {
    var locked: Bool
    var open: Int
    var total: Int?
    var spoken: String?
}

// Response envelopes.
struct LoopsResponse: Codable { let loops: [Loop] }
struct ReviewsResponse: Codable { let reviews: [Review] }

/// One loop's result from POST /v1/suggest.
struct SuggestResult: Codable {
    let loop_id: String
    var next_action: String
    var draft_id: String?
    var cached: Bool?
}

/// POST /v1/suggest response (one or all active loops).
struct SuggestResponse: Codable {
    let date: String
    let count: Int
    let suggested: [SuggestResult]
}

/// One loop's result from POST /v1/research.
struct ResearchResult: Codable {
    let loop_id: String
    var draft_id: String?
    var cached: Bool?
    var web_used: Bool?
    var sources: Int?
}

/// POST /v1/research response (one or all active loops).
struct ResearchResponse: Codable {
    let date: String
    let count: Int
    let researched: [ResearchResult]
}

/// One entry in GET /v1/suggestions/today (a loop suggested today).
struct TodaySuggestion: Codable, Identifiable {
    let loop_id: String
    var title: String?
    var next_action: String
    var draft_id: String?
    var id: String { loop_id }
}

/// GET /v1/suggestions/today response — the feed the phone polls to decide
/// whether to raise a local notification about fresh suggestions.
struct TodayFeed: Codable {
    let date: String
    let count: Int
    let loops: [TodaySuggestion]
}

// -- Daily Briefing (PRD §4): audio digest + editable X post + person-to-know.

/// Spoken recap of the loop's fresh research (grounded in `Briefing.sources`).
struct BriefingDigest: Codable, Equatable {
    var transcript: String
    var key_points: [String]
}

/// One editable X/Twitter post the user reviews before publishing.
struct BriefingPost: Codable, Equatable {
    var text: String
}

/// A relevant public figure to learn from — discovered public info, kept
/// distinct from the source-grounded digest. Never messaged automatically.
struct BriefingPerson: Codable, Equatable {
    var name: String
    var platform: String
    var profile_url: String
    var context: String
    var why_relevant: String
    var engagement_tips: [String]
}

/// One loop's Daily Briefing (server sidecar). `feedback`/`dismissed` are keyed
/// by item ("digest"|"post"|"person").
struct Briefing: Codable, Equatable, Identifiable {
    var loop_id: String
    var title: String?
    var date: String
    var digest: BriefingDigest
    var post: BriefingPost
    var person: BriefingPerson
    var sources: [String]
    var feedback: [String: String]?
    var dismissed: [String: Bool]?
    var cached: Bool?
    var has_audio: Bool?
    var id: String { loop_id }
}

/// POST /v1/briefing response (one or all active loops).
struct BriefingRunResponse: Codable {
    let date: String
    let count: Int
    let briefings: [Briefing]
}
