import AppIntents
import Foundation

// App Intents = thin Siri/Shortcuts adapters (plan.md §4, AGENTS.md).
//
// THIS IS THE ONLY FILE THAT IMPORTS AppIntents. Each intent only translates a
// request into a LoopCommand on the shared LoopCommandBus (source: .siri). No
// planning, policy, memory writes, or tool choice live here — those are in the
// server LoopEngine. Every intent below has a first-class in-app twin.
//
// Safety: Status speaks only a privacy-safe projection; ReviewAction opens the
// app for authenticated foreground review and never sends from voice.

enum LoopDomainAppEnum: String, AppEnum {
    case career, life, both

    static var typeDisplayRepresentation: TypeDisplayRepresentation { "Loop Domain" }
    static var caseDisplayRepresentations: [LoopDomainAppEnum: DisplayRepresentation] {
        [.career: "Career", .life: "Life", .both: "Both"]
    }

    var domain: LoopDomain { LoopDomain(rawValue: rawValue) ?? .career }
}

/// A loop exposed to Siri/Shortcuts for parameter resolution.
struct LoopEntity: AppEntity, Identifiable {
    let id: String
    var title: String
    var domain: String
    var status: String

    static var typeDisplayRepresentation: TypeDisplayRepresentation { "Loop" }
    static var defaultQuery = LoopEntityQuery()

    var displayRepresentation: DisplayRepresentation {
        DisplayRepresentation(title: "\(title)", subtitle: "\(domain) · \(status)")
    }

    init(id: String, title: String, domain: String, status: String) {
        self.id = id
        self.title = title
        self.domain = domain
        self.status = status
    }

    init(_ loop: Loop) {
        self.init(id: loop.id, title: loop.title, domain: loop.domain, status: loop.status)
    }
}

struct LoopEntityQuery: EntityQuery {
    func entities(for identifiers: [String]) async throws -> [LoopEntity] {
        let loops = try await LoopCommandBus.fromDefaults().listLoops()
        return loops.filter { identifiers.contains($0.id) }.map(LoopEntity.init)
    }

    func suggestedEntities() async throws -> [LoopEntity] {
        let loops = try await LoopCommandBus.fromDefaults().listLoops()
        return loops.filter { $0.status != "done" }.map(LoopEntity.init)
    }
}

// MARK: - Intents (each is a thin adapter over LoopCommandBus)

struct NewLoopIntent: AppIntent {
    static var title: LocalizedStringResource = "New Loop"
    static var description = IntentDescription("Create a career or life loop.")

    @Parameter(title: "Title") var loopTitle: String
    @Parameter(title: "Domain") var domain: LoopDomainAppEnum?
    @Parameter(title: "Note") var note: String?

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let dom = domain ?? .career
        _ = try await LoopCommandBus.fromDefaults().newLoop(
            title: loopTitle, domain: dom.domain, text: note ?? "", source: .siri
        )
        return .result(dialog: "Created your \(dom.rawValue) loop.")
    }
}

struct LogEvidenceIntent: AppIntent {
    static var title: LocalizedStringResource = "Log Evidence"
    static var description = IntentDescription("Add a note or evidence to a loop.")

    @Parameter(title: "Loop") var loop: LoopEntity
    @Parameter(title: "Note") var text: String

    func perform() async throws -> some IntentResult & ProvidesDialog {
        _ = try await LoopCommandBus.fromDefaults().logEvidence(
            loopId: loop.id, text: text, source: .siri
        )
        return .result(dialog: "Logged to \(loop.title).")
    }
}

/// Quick Note = the compliant "note after a call/meeting" adapter. It writes a
/// durable fact to global memory (a local, reversible operation). SignalLoop
/// never auto-detects calls or reads their content — the user speaks the note.
struct QuickNoteIntent: AppIntent {
    static var title: LocalizedStringResource = "Quick Note"
    static var description = IntentDescription("Save a quick note to SignalLoop's memory.")

    @Parameter(title: "Note") var note: String

    func perform() async throws -> some IntentResult & ProvidesDialog {
        _ = try await LoopCommandBus.fromDefaults().remember(text: note, source: .siri)
        return .result(dialog: "Saved your note.")
    }
}

struct StatusIntent: AppIntent {
    static var title: LocalizedStringResource = "Loop Status"
    static var description = IntentDescription("Speak a privacy-safe summary of open loops.")

    func perform() async throws -> some IntentResult & ProvidesDialog {
        // Locked projection: no titles, evidence, or draft content spoken.
        let board = try await LoopCommandBus.fromDefaults().statusBoard(locked: true)
        return .result(dialog: "\(board.spoken ?? "No open loops.")")
    }
}

struct PauseLoopIntent: AppIntent {
    static var title: LocalizedStringResource = "Pause Loop"
    @Parameter(title: "Loop") var loop: LoopEntity

    func perform() async throws -> some IntentResult & ProvidesDialog {
        _ = try await LoopCommandBus.fromDefaults().pause(loopId: loop.id, source: .siri)
        return .result(dialog: "Paused \(loop.title).")
    }
}

struct ResumeLoopIntent: AppIntent {
    static var title: LocalizedStringResource = "Resume Loop"
    @Parameter(title: "Loop") var loop: LoopEntity

    func perform() async throws -> some IntentResult & ProvidesDialog {
        _ = try await LoopCommandBus.fromDefaults().resume(loopId: loop.id, source: .siri)
        return .result(dialog: "Resumed \(loop.title).")
    }
}

struct ApprovePlanIntent: AppIntent {
    static var title: LocalizedStringResource = "Approve Plan"
    static var description = IntentDescription("Approve an internal, reversible plan — never a send or post.")

    @Parameter(title: "Loop") var loop: LoopEntity

    func perform() async throws -> some IntentResult & ProvidesDialog {
        _ = try await LoopCommandBus.fromDefaults().approvePlan(loopId: loop.id, source: .siri)
        return .result(dialog: "Approved the plan for \(loop.title).")
    }
}

struct MarkCompleteIntent: AppIntent {
    static var title: LocalizedStringResource = "Mark Complete"
    @Parameter(title: "Loop") var loop: LoopEntity

    func perform() async throws -> some IntentResult & ProvidesDialog {
        _ = try await LoopCommandBus.fromDefaults().markComplete(loopId: loop.id, source: .siri)
        return .result(dialog: "Marked \(loop.title) complete.")
    }
}

/// Consequential actions never send from voice. This opens the app so the user
/// can review and approve in an authenticated foreground screen.
struct ReviewActionIntent: AppIntent {
    static var title: LocalizedStringResource = "Review Action"
    static var description = IntentDescription("Open SignalLoop to review a pending action before sending.")
    static var openAppWhenRun = true

    @Parameter(title: "Loop") var loop: LoopEntity

    func perform() async throws -> some IntentResult & ProvidesDialog {
        return .result(dialog: "Opening \(loop.title) for review in SignalLoop.")
    }
}

// MARK: - Shortcuts phrases

struct SignalLoopShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: StatusIntent(),
            phrases: [
                "Check my \(.applicationName) status",
                "\(.applicationName) status",
            ],
            shortTitle: "Status",
            systemImageName: "list.bullet.rectangle"
        )
        AppShortcut(
            intent: NewLoopIntent(),
            phrases: [
                "New \(.applicationName) loop",
                "Start a loop in \(.applicationName)",
            ],
            shortTitle: "New Loop",
            systemImageName: "plus.circle"
        )
        AppShortcut(
            intent: QuickNoteIntent(),
            phrases: [
                "Save a note in \(.applicationName)",
                "Note this in \(.applicationName)",
            ],
            shortTitle: "Quick Note",
            systemImageName: "square.and.pencil"
        )
    }
}
