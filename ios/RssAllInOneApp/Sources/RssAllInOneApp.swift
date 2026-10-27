import SwiftUI

@main
struct RssAllInOneApp: App {
    @StateObject private var store = AppStore()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(store)
                .preferredColorScheme(nil)
        }
    }
}
