import SwiftUI

@main
struct ChittiApp: App {
    @StateObject private var appState = AppState()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appState)
        }
    }
}

struct ContentView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        TabView {
            ChatView()
                .tabItem { Label("Chat", systemImage: "bubble.left.and.bubble.right") }
            SettingsView()
                .tabItem { Label("Settings", systemImage: "gear") }
        }
        .task {
            appState.loadSettings()
        }
    }
}
