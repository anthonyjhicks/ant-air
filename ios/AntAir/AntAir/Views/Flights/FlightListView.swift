import SwiftUI
import SwiftData

struct FlightListView: View {
    @Environment(\.modelContext) private var modelContext
    @EnvironmentObject private var appState: AppState

    @Query(sort: \Flight.startDate, order: .reverse)
    private var allFlights: [Flight]

    private var flights: [Flight] {
        allFlights.filter { $0.status == "approved" && $0.deletedAt == nil }
    }

    @State private var searchText = ""
    @State private var showingForm = false
    @State private var selectedFilter: FlightFilter = .all

    enum FlightFilter: String, CaseIterable {
        case all = "All"
        case upcoming = "Upcoming"
        case past = "Past"
    }

    var filteredFlights: [Flight] {
        var result = flights

        let now = Date()
        switch selectedFilter {
        case .all: break
        case .upcoming: result = result.filter { $0.startDate >= now }
        case .past: result = result.filter { $0.startDate < now }
        }

        if !searchText.isEmpty {
            let term = searchText.lowercased()
            result = result.filter { flight in
                (flight.flightNumber?.lowercased().contains(term) ?? false) ||
                (flight.airlineCode?.lowercased().contains(term) ?? false) ||
                (flight.startAirport?.lowercased().contains(term) ?? false) ||
                (flight.endAirport?.lowercased().contains(term) ?? false) ||
                (flight.startCityName?.lowercased().contains(term) ?? false) ||
                (flight.endCityName?.lowercased().contains(term) ?? false) ||
                (flight.aircraft?.lowercased().contains(term) ?? false) ||
                (flight.aircraftRegistration?.lowercased().contains(term) ?? false)
            }
        }

        return result
    }

    var body: some View {
        NavigationStack {
            List {
                Picker("Filter", selection: $selectedFilter) {
                    ForEach(FlightFilter.allCases, id: \.self) { filter in
                        Text(filter.rawValue).tag(filter)
                    }
                }
                .pickerStyle(.segmented)
                .listRowBackground(Color.clear)
                .listRowInsets(EdgeInsets())
                .padding(.horizontal)

                ForEach(filteredFlights, id: \.id) { flight in
                    NavigationLink(destination: FlightDetailView(flight: flight)) {
                        FlightRowView(flight: flight)
                    }
                    .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                        Button(role: .destructive) {
                            deleteFlight(flight)
                        } label: {
                            Label("Delete", systemImage: "trash")
                        }

                        Button {
                            toggleFollowUp(flight)
                        } label: {
                            Label(
                                flight.followUp ? "Unflag" : "Flag",
                                systemImage: flight.followUp ? "flag.slash" : "flag"
                            )
                        }
                        .tint(.orange)
                    }
                }
            }
            .listStyle(.plain)
            .background(Theme.background)
            .scrollContentBackground(.hidden)
            .navigationTitle("Flights")
            .searchable(text: $searchText, prompt: "Search flights")
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button(action: { showingForm = true }) {
                        Image(systemName: "plus")
                    }
                    .tint(Theme.primary)
                }
            }
            .sheet(isPresented: $showingForm) {
                FlightFormView()
            }
        }
    }

    private func deleteFlight(_ flight: Flight) {
        ChangeTracker.trackFlightDelete(flight, modelContext: modelContext)
        try? modelContext.save()
    }

    private func toggleFollowUp(_ flight: Flight) {
        flight.followUp.toggle()
        ChangeTracker.trackFlightUpdate(
            flight,
            changedFields: ["follow_up": flight.followUp],
            modelContext: modelContext
        )
        try? modelContext.save()
    }
}

// MARK: - Flight Row

struct FlightRowView: View {
    let flight: Flight
    @EnvironmentObject private var appState: AppState

    var body: some View {
        HStack(spacing: Theme.Spacing.md) {
            VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                Text(flight.startDate, format: .dateTime.day().month(.abbreviated).year())
                    .font(Theme.Font.sm())
                    .foregroundStyle(Theme.muted)
                HStack(spacing: Theme.Spacing.xs) {
                    Text(flight.startAirport ?? "???")
                        .font(Theme.Font.base(.semibold))
                    Image(systemName: "arrow.right")
                        .font(Theme.Font.xs())
                        .foregroundStyle(Theme.muted)
                    Text(flight.endAirport ?? "???")
                        .font(Theme.Font.base(.semibold))
                }
            }

            Spacer()

            VStack(alignment: .trailing, spacing: Theme.Spacing.xxs) {
                if let fn = flight.flightNumber {
                    Text(fn)
                        .font(Theme.Font.sm())
                        .foregroundStyle(Theme.muted)
                }
                if let dist = flight.distance {
                    let converted = appState.distanceUnit.convert(dist)
                    Text("\(Int(converted)) \(appState.distanceUnit.abbreviation)")
                        .font(Theme.Font.xs())
                        .foregroundStyle(Theme.muted)
                }
            }

            if flight.followUp {
                Image(systemName: "flag.fill")
                    .font(Theme.Font.sm())
                    .foregroundStyle(Theme.warning)
            }

            if flight.locallyModified {
                Image(systemName: "arrow.triangle.2.circlepath")
                    .font(Theme.Font.sm())
                    .foregroundStyle(Theme.primary)
            }
        }
        .padding(.vertical, Theme.Spacing.xxs)
    }
}
