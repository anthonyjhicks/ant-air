import SwiftUI
import SwiftData

@main
struct AntAirApp: App {
    let container: ModelContainer

    @StateObject private var appState = AppState()

    init() {
        do {
            let schema = Schema([
                Flight.self,
                Trip.self,
                TripLeg.self,
                Aircraft.self,
                AchievementBadge.self,
                SyncMetadata.self,
                PendingChange.self,
                SyncConflictLog.self,
            ])
            let config = ModelConfiguration(schema: schema, isStoredInMemoryOnly: false)
            container = try ModelContainer(for: schema, configurations: [config])
        } catch {
            fatalError("Failed to create ModelContainer: \(error)")
        }
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appState)
        }
        .modelContainer(container)
    }
}
