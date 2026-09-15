import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var appState: AppState

    var body: some View {
        Group {
            if appState.isAuthenticated {
                MainTabView()
            } else {
                LoginView()
            }
        }
    }
}

struct MainTabView: View {
    var body: some View {
        TabView {
            DashboardView()
                .tabItem {
                    Label("Home", systemImage: "house")
                }

            FlightListView()
                .tabItem {
                    Label("Flights", systemImage: "airplane")
                }

            RouteMapView()
                .tabItem {
                    Label("Map", systemImage: "map")
                }

            AircraftListView()
                .tabItem {
                    Label("Aircraft", systemImage: "airplane.circle")
                }

            AchievementsView()
                .tabItem {
                    Label("Achievements", systemImage: "trophy")
                }

            InsightsView()
                .tabItem {
                    Label("Insights", systemImage: "sparkles")
                }

            SettingsView()
                .tabItem {
                    Label("Settings", systemImage: "gear")
                }
        }
        .tint(Theme.primary)
    }
}
