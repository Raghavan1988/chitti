import SwiftUI

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

    var body: some View {
        TabView {
            LoopListView()
                .tabItem { Label("Loops", systemImage: "arrow.triangle.2.circlepath") }
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
