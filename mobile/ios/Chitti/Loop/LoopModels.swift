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
