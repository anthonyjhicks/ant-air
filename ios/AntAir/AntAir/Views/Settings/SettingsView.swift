import SwiftUI
import SwiftData

struct SettingsView: View {
    @EnvironmentObject private var appState: AppState
    @Environment(\.modelContext) private var modelContext
    @ObservedObject private var syncEngine = SyncEngine.shared

    @Query private var pendingChanges: [PendingChange]
    @Query private var syncMeta: [SyncMetadata]
    @Query private var conflicts: [SyncConflictLog]

    var body: some View {
        NavigationStack {
            List {
                // Account
                Section("Account") {
                    if let url = UserDefaults.standard.string(forKey: "server_url") {
                        HStack {
                            Text("Server")
                            Spacer()
                            Text(url)
                                .font(Theme.Font.sm())
                                .foregroundStyle(Theme.muted)
                                .lineLimit(1)
                        }
                    }

                    Button("Sign Out", role: .destructive) {
                        Task {
                            await AuthManager.shared.clearTokens()
                            appState.isAuthenticated = false
                        }
                    }
                    .foregroundStyle(Theme.danger)
                }

                // Sync
                Section("Sync") {
                    HStack {
                        Text("Last Sync")
                        Spacer()
                        if let date = syncMeta.first?.lastSyncDate {
                            Text(date, style: .relative)
                                .font(Theme.Font.sm())
                                .foregroundStyle(Theme.muted)
                        } else {
                            Text("Never")
                                .font(Theme.Font.sm())
                                .foregroundStyle(Theme.muted)
                        }
                    }

                    HStack {
                        Text("Server Revision")
                        Spacer()
                        Text("\(syncMeta.first?.lastPulledRevision ?? 0)")
                            .font(Theme.Font.sm())
                            .foregroundStyle(Theme.muted)
                    }

                    HStack {
                        Text("Pending Changes")
                        Spacer()
                        Text("\(pendingChanges.count)")
                            .font(Theme.Font.sm())
                            .foregroundColor(pendingChanges.isEmpty ? Theme.muted : Theme.warning)
                    }

                    if syncEngine.isSyncing {
                        HStack {
                            ProgressView()
                                .scaleEffect(0.8)
                            Text("Syncing...")
                                .font(Theme.Font.sm())
                        }
                    }

                    if let error = syncEngine.lastError {
                        Text(error)
                            .font(Theme.Font.sm())
                            .foregroundStyle(Theme.danger)
                    }

                    Button("Sync Now") {
                        Task {
                            await syncEngine.sync(modelContext: modelContext)
                        }
                    }
                    .disabled(syncEngine.isSyncing)
                    .tint(Theme.primary)

                    Button("Force Full Re-sync") {
                        Task {
                            if let meta = syncMeta.first {
                                meta.lastPulledRevision = 0
                                try? modelContext.save()
                            }
                            await syncEngine.sync(modelContext: modelContext)
                        }
                    }
                    .disabled(syncEngine.isSyncing)
                    .tint(Theme.primary)
                }

                // Conflicts
                if !conflicts.isEmpty {
                    Section("Sync Conflicts (\(conflicts.filter { !$0.reviewed }.count) unreviewed)") {
                        ForEach(conflicts.filter { !$0.reviewed }, id: \.conflictId) { conflict in
                            VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                                Text("\(conflict.entityType) #\(conflict.entityId)")
                                    .font(Theme.Font.base())
                                Text(conflict.resolution)
                                    .font(Theme.Font.sm())
                                    .foregroundStyle(Theme.muted)
                                Text(conflict.conflictDate, style: .relative)
                                    .font(Theme.Font.xs())
                                    .foregroundStyle(Theme.muted)
                            }
                        }
                    }
                }

                // Display
                Section("Display") {
                    Picker("Distance Unit", selection: Binding(
                        get: { appState.distanceUnit },
                        set: { appState.setDistanceUnit($0) }
                    )) {
                        ForEach(AppState.DistanceUnit.allCases, id: \.self) { unit in
                            Text(unit.label).tag(unit)
                        }
                    }
                }

                // Data
                Section("Data") {
                    let flightCount = (try? modelContext.fetchCount(FetchDescriptor<Flight>())) ?? 0
                    let aircraftCount = (try? modelContext.fetchCount(FetchDescriptor<Aircraft>())) ?? 0
                    let tripCount = (try? modelContext.fetchCount(FetchDescriptor<Trip>())) ?? 0

                    HStack {
                        Text("Flights")
                        Spacer()
                        Text("\(flightCount)").foregroundStyle(Theme.muted)
                    }
                    HStack {
                        Text("Aircraft")
                        Spacer()
                        Text("\(aircraftCount)").foregroundStyle(Theme.muted)
                    }
                    HStack {
                        Text("Trips")
                        Spacer()
                        Text("\(tripCount)").foregroundStyle(Theme.muted)
                    }
                }

                // About
                Section("About") {
                    HStack {
                        Text("App Version")
                        Spacer()
                        Text("1.0.0")
                            .foregroundStyle(Theme.muted)
                    }
                }
            }
            .background(Theme.background)
            .scrollContentBackground(.hidden)
            .navigationTitle("Settings")
        }
    }
}
