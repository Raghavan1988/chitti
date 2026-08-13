import SwiftUI
import UserNotifications

@main
struct ChittiApp: App {
    @StateObject private var appState = AppState()
    @StateObject private var loopStore = LoopStore()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appState)
                .environmentObject(loopStore)
        }
    }
}

struct ContentView: View {
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var loopStore: LoopStore
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        TabView {
            LoopListView()
                .tabItem { Label("Loops", systemImage: "arrow.triangle.2.circlepath") }
            SettingsView()
                .tabItem { Label("Settings", systemImage: "gear") }
        }
        .task {
            appState.loadSettings()
            NotificationManager.shared.bootstrap(reminderHour: appState.settings.briefingHour)
        }
        // Re-check for fresh suggestions whenever we return to the foreground.
        .onChange(of: scenePhase) { _, phase in
            if phase == .active { Task { await loopStore.refresh() } }
        }
        // The permission alert doesn't background us, so re-check the moment
        // the user grants notifications — otherwise the first banner waits for
        // the next manual refresh.
        .onReceive(NotificationCenter.default.publisher(for: .chittiNotificationsAuthorized)) { _ in
            Task { await loopStore.refresh() }
        }
    }
}

extension Notification.Name {
    /// Posted once the user grants notification permission, so views can
    /// immediately re-check for suggestions instead of waiting for a refresh.
    static let chittiNotificationsAuthorized = Notification.Name("chitti.notifications.authorized")
    /// Posted when the capture nudge is tapped, so the list can present Quick
    /// Capture directly.
    static let chittiOpenQuickCapture = Notification.Name("chitti.open.quickcapture")
}

/// Local-notification hub for SignalLoop's proactive UX.
///
/// iOS gives a third-party app no reliable way to be woken by the server, so
/// until the cloud wake plane + APNs exist this is the honest stand-in:
/// (1) a daily reminder the system delivers even when the app is closed, and
/// (2) an immediate banner when a foreground refresh discovers a *fresh*
/// suggestion (deduped by draft id). It only nudges — it never sends or acts.
final class NotificationManager: NSObject, UNUserNotificationCenterDelegate {
    static let shared = NotificationManager()

    private let seenKey = "chitti.notified.drafts"
    private let reminderId = "chitti.daily.reminder"
    private let captureReminderId = "chitti.capture.reminder"

    /// Wire up the delegate, request permission, and schedule the daily nudge.
    func bootstrap(reminderHour: Int = 7) {
        let center = UNUserNotificationCenter.current()
        center.delegate = self
        center.requestAuthorization(options: [.alert, .sound, .badge]) { granted, _ in
            if granted {
                NotificationCenter.default.post(name: .chittiNotificationsAuthorized, object: nil)
            }
        }
        scheduleDailyReminder(hour: reminderHour)
        scheduleCaptureNudge()
    }

    /// A once-a-day nudge to open the app and review suggested actions.
    func scheduleDailyReminder(hour: Int) {
        let content = UNMutableNotificationContent()
        content.title = "SignalLoop"
        content.body = "Good time to review today's suggested actions for your loops."
        content.sound = .default

        var when = DateComponents()
        when.hour = hour
        let trigger = UNCalendarNotificationTrigger(dateMatching: when, repeats: true)
        let req = UNNotificationRequest(identifier: reminderId, content: content, trigger: trigger)
        let center = UNUserNotificationCenter.current()
        center.removePendingNotificationRequests(withIdentifiers: [reminderId])
        center.add(req)
    }

    /// An end-of-day nudge to jot a quick note (e.g., after a call or meeting)
    /// into memory or a loop. This only *reminds*; capture stays user-initiated
    /// — SignalLoop never scrapes calls, messages, or other apps.
    func scheduleCaptureNudge(hour: Int = 20) {
        let content = UNMutableNotificationContent()
        content.title = "SignalLoop"
        content.body = "Anything from today's calls or meetings? Tap to capture a quick note."
        content.sound = .default

        var when = DateComponents()
        when.hour = hour
        let trigger = UNCalendarNotificationTrigger(dateMatching: when, repeats: true)
        let req = UNNotificationRequest(identifier: captureReminderId, content: content, trigger: trigger)
        let center = UNUserNotificationCenter.current()
        center.removePendingNotificationRequests(withIdentifiers: [captureReminderId])
        center.add(req)
    }

    /// Raise one banner for suggestions we haven't announced yet (dedup by
    /// draft id, persisted across launches).
    func notifyFreshSuggestions(_ feed: TodayFeed) async {
        // Only announce (and consume the dedup slot) once the user has actually
        // allowed notifications. A first-launch refresh runs while the
        // permission prompt is still up; without this guard those suggestions
        // would be marked "seen" and their banner silently swallowed.
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        guard settings.authorizationStatus == .authorized
            || settings.authorizationStatus == .provisional else { return }

        let defaults = UserDefaults.standard
        var seen = Set(defaults.stringArray(forKey: seenKey) ?? [])
        let fresh = feed.loops.filter { s in
            guard let id = s.draft_id else { return false }
            return !seen.contains(id)
        }
        guard !fresh.isEmpty else { return }

        let content = UNMutableNotificationContent()
        content.title = "SignalLoop suggestions"
        if fresh.count == 1, let one = fresh.first {
            let action = one.next_action.isEmpty ? "New suggested action ready." : one.next_action
            content.body = "\(one.title ?? "A loop"): \(action)"
        } else {
            content.body = "\(fresh.count) loops have new suggested actions."
        }
        content.sound = .default

        let req = UNNotificationRequest(
            identifier: "chitti.suggestions.\(feed.date).\(fresh.count)",
            content: content,
            trigger: nil
        )
        try? await UNUserNotificationCenter.current().add(req)

        for s in fresh { if let id = s.draft_id { seen.insert(id) } }
        defaults.set(Array(seen), forKey: seenKey)
    }

    // Show banners even when the app is in the foreground.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .sound])
    }

    // A tap on the capture nudge deep-links straight to Quick Capture.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        if response.notification.request.identifier == captureReminderId {
            NotificationCenter.default.post(name: .chittiOpenQuickCapture, object: nil)
        }
        completionHandler()
    }
}
