import SwiftUI
import SwiftData
import Charts

struct DashboardView: View {
    @EnvironmentObject private var appState: AppState
    @Environment(\.modelContext) private var modelContext
    @ObservedObject private var syncEngine = SyncEngine.shared

    @Query(sort: \Flight.startDate, order: .reverse)
    private var allFlights: [Flight]

    private var flights: [Flight] {
        allFlights.filter { $0.status == "approved" && $0.deletedAt == nil && !$0.excludeFromStats }
    }

    /// Grouped flights for reporting — matches web UI's merged_flights_for_reporting().
    private var reportingFlights: [Flight] {
        FlightReporting.mergedForReporting(flights)
    }

    private var stats: DashboardStats {
        DashboardStats.compute(from: reportingFlights)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: Theme.Spacing.lg) {
                    // Sync status banner
                    if syncEngine.isSyncing {
                        HStack {
                            ProgressView()
                                .scaleEffect(0.8)
                            Text("Syncing...")
                                .font(Theme.Font.sm())
                                .foregroundStyle(Theme.muted)
                        }
                        .padding(.horizontal)
                    }

                    if !NetworkMonitor.shared.isConnected {
                        HStack(spacing: Theme.Spacing.sm) {
                            Image(systemName: "wifi.slash")
                            Text("Offline \u{2014} changes will sync when connected")
                        }
                        .font(Theme.Font.sm())
                        .foregroundStyle(Theme.warning)
                        .padding(.horizontal)
                    }

                    // Stats cards
                    StatsCardsView(flights: reportingFlights)

                    // Highlight cards
                    HighlightCardsView(stats: stats)

                    // Next flight
                    if let nextFlight = nextUpcomingFlight {
                        NextFlightCard(flight: nextFlight)
                    }

                    // First & Last flight
                    FirstLastFlightCards(stats: stats)

                    // Charts
                    MonthlyChart(data: stats.monthlyFlights)

                    YearlyFlightsChart(data: stats.yearlyFlights)

                    YearlyMilesChart(data: stats.yearlyMiles)

                    // Top N breakdowns
                    TopNBarChart(
                        title: "Top Countries",
                        icon: "flag",
                        data: Array(stats.topCountries.prefix(10)),
                        totalLabel: "\(stats.topCountries.count) countries"
                    )

                    TopNBarChart(
                        title: "Top Cities",
                        icon: "building.2",
                        data: Array(stats.topCities.prefix(10)),
                        totalLabel: "\(stats.topCities.count) cities"
                    )

                    TopNBarChart(
                        title: "Top Airlines",
                        icon: "ticket",
                        data: Array(stats.topAirlines.prefix(10)),
                        totalLabel: "\(stats.topAirlines.count) airlines"
                    )

                    TopNBarChart(
                        title: "Top Aircraft Types",
                        icon: "airplane.circle",
                        data: Array(stats.topAircraftTypes.prefix(10)),
                        totalLabel: "\(stats.topAircraftTypes.count) types"
                    )

                    TopNMilesChart(
                        title: "Top Aircraft by \(appState.distanceUnit.label)",
                        icon: "globe",
                        data: Array(stats.topAircraftMiles.prefix(10)),
                        distanceUnit: appState.distanceUnit,
                        totalLabel: "\(stats.topAircraftMiles.count) types"
                    )

                    TopNBarChart(
                        title: "Top Tail Numbers",
                        icon: "number",
                        data: Array(stats.topTailNumbers.prefix(10)),
                        totalLabel: "\(stats.topTailNumbers.count) registrations"
                    )

                    TopNBarChart(
                        title: "Top Routes",
                        icon: "arrow.right",
                        data: Array(stats.topRoutes.prefix(10)),
                        totalLabel: "\(stats.topRoutes.count) routes"
                    )

                    // Recent flights
                    RecentFlightsSection(flights: Array(reportingFlights.prefix(10)))
                }
                .padding()
            }
            .background(Theme.background)
            .navigationTitle("Dashboard")
            .refreshable {
                await syncEngine.sync(modelContext: modelContext)
            }
            .task {
                await syncEngine.sync(modelContext: modelContext)
            }
        }
    }

    private var nextUpcomingFlight: Flight? {
        let now = Date()
        return reportingFlights.first { $0.startDate >= now }
    }
}

// MARK: - Stats Cards

struct StatsCardsView: View {
    let flights: [Flight]
    @EnvironmentObject private var appState: AppState

    var body: some View {
        LazyVGrid(columns: [
            GridItem(.flexible()),
            GridItem(.flexible()),
            GridItem(.flexible()),
        ], spacing: Theme.Spacing.md) {
            StatCard(title: "Flights", value: "\(flights.count)", icon: "airplane")
            StatCard(
                title: appState.distanceUnit.label,
                value: formattedDistance,
                icon: "globe"
            )
            StatCard(title: "Countries", value: "\(uniqueCountries)", icon: "flag")
            StatCard(title: "Cities", value: "\(uniqueCities)", icon: "building.2")
            StatCard(title: "Airlines", value: "\(uniqueAirlines)", icon: "ticket")
            StatCard(title: "Aircraft", value: "\(uniqueAircraftTypes)", icon: "airplane.circle")
        }
    }

    private var totalMiles: Double {
        flights.compactMap(\.distance).reduce(0, +)
    }

    private var formattedDistance: String {
        let value = appState.distanceUnit.convert(totalMiles)
        if value >= 1_000_000 {
            return String(format: "%.1fM", value / 1_000_000)
        } else if value >= 1000 {
            return String(format: "%.0fK", value / 1000)
        }
        return String(format: "%.0f", value)
    }

    private var uniqueCountries: Int {
        Set(flights.compactMap(\.startCountry) + flights.compactMap(\.endCountry)).count
    }

    private var uniqueCities: Int {
        Set(flights.compactMap(\.startCityName) + flights.compactMap(\.endCityName)).count
    }

    private var uniqueAirlines: Int {
        Set(flights.compactMap(\.airlineCode)).count
    }

    private var uniqueAircraftTypes: Int {
        Set(flights.compactMap(\.aircraft)).count
    }
}

struct StatCard: View {
    let title: String
    let value: String
    let icon: String

    var body: some View {
        VStack(spacing: Theme.Spacing.xs) {
            Image(systemName: icon)
                .font(Theme.Font.md())
                .foregroundStyle(Theme.primary)
            Text(value)
                .font(Theme.Font.lg(.bold))
            Text(title)
                .font(Theme.Font.xs())
                .foregroundStyle(Theme.summaryLabel)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, Theme.Spacing.md)
        .panelStyle()
    }
}

// MARK: - Highlight Cards

struct HighlightCardsView: View {
    let stats: DashboardStats

    var body: some View {
        LazyVGrid(columns: [
            GridItem(.flexible()),
            GridItem(.flexible()),
        ], spacing: Theme.Spacing.md) {
            if let top = stats.topCities.first {
                HighlightCard(title: "Top City", value: top.label, detail: "\(top.count) flights", icon: "building.2")
            }
            if let top = stats.topCountries.first {
                HighlightCard(title: "Top Country", value: top.label, detail: "\(top.count) flights", icon: "flag")
            }
            if let top = stats.yearlyFlights.max(by: { $0.count < $1.count }) {
                HighlightCard(title: "Busiest Year", value: "\(top.year)", detail: "\(top.count) flights", icon: "calendar")
            }
            if let top = stats.topAirlines.first {
                HighlightCard(title: "Top Airline", value: top.label, detail: "\(top.count) flights", icon: "ticket")
            }
            if let top = stats.topAircraftTypes.first {
                HighlightCard(title: "Top Aircraft", value: top.label, detail: "\(top.count) flights", icon: "airplane.circle")
            }
            if let top = stats.topTailNumbers.first {
                HighlightCard(title: "Top Tail No.", value: top.label, detail: "\(top.count) flights", icon: "number")
            }
        }
    }
}

struct HighlightCard: View {
    let title: String
    let value: String
    let detail: String
    let icon: String

    var body: some View {
        VStack(spacing: Theme.Spacing.xs) {
            Image(systemName: icon)
                .font(Theme.Font.sm())
                .foregroundStyle(Theme.primary)
            Text(value)
                .font(Theme.Font.base(.semibold))
                .lineLimit(1)
                .minimumScaleFactor(0.7)
            Text(detail)
                .font(Theme.Font.xs())
                .foregroundStyle(Theme.muted)
            Text(title)
                .font(Theme.Font.xs())
                .foregroundStyle(Theme.summaryLabel)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, Theme.Spacing.md)
        .panelStyle()
    }
}

// MARK: - First & Last Flight

struct FirstLastFlightCards: View {
    let stats: DashboardStats

    var body: some View {
        if stats.firstFlight != nil || stats.lastFlight != nil {
            HStack(spacing: Theme.Spacing.md) {
                if let first = stats.firstFlight {
                    flightCard(title: "First Flight", flight: first)
                }
                if let last = stats.lastFlight {
                    flightCard(title: "Last Flight", flight: last)
                }
            }
        }
    }

    private func flightCard(title: String, flight: Flight) -> some View {
        VStack(spacing: Theme.Spacing.xs) {
            Text(title)
                .font(Theme.Font.xs())
                .foregroundStyle(Theme.summaryLabel)
            Text(flight.startDate, format: .dateTime.day().month(.abbreviated).year())
                .font(Theme.Font.sm(.semibold))
            HStack(spacing: Theme.Spacing.xs) {
                Text(flight.startAirport ?? "???")
                    .font(Theme.Font.base(.semibold))
                Image(systemName: "arrow.right")
                    .font(Theme.Font.xs())
                    .foregroundStyle(Theme.muted)
                Text(flight.endAirport ?? "???")
                    .font(Theme.Font.base(.semibold))
            }
            if let reg = flight.aircraftRegistration {
                Text(reg)
                    .font(Theme.Font.xs())
                    .foregroundStyle(Theme.muted)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, Theme.Spacing.md)
        .panelStyle()
    }
}

// MARK: - Next Flight

struct NextFlightCard: View {
    let flight: Flight

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            HStack {
                Image(systemName: "airplane.departure")
                    .foregroundStyle(Theme.primary)
                Text("Next Flight")
                    .font(Theme.Font.md(.semibold))
                Spacer()
                Text(flight.startDate, style: .relative)
                    .font(Theme.Font.sm())
                    .foregroundStyle(Theme.muted)
            }

            HStack {
                VStack(alignment: .leading) {
                    Text(flight.startAirport ?? "")
                        .font(Theme.Font.xl())
                    Text(flight.startCityName ?? "")
                        .font(Theme.Font.sm())
                        .foregroundStyle(Theme.muted)
                }

                Spacer()

                Image(systemName: "arrow.right")
                    .foregroundStyle(Theme.muted)

                Spacer()

                VStack(alignment: .trailing) {
                    Text(flight.endAirport ?? "")
                        .font(Theme.Font.xl())
                    Text(flight.endCityName ?? "")
                        .font(Theme.Font.sm())
                        .foregroundStyle(Theme.muted)
                }
            }

            HStack {
                if let fn = flight.flightNumber {
                    Text(fn)
                        .font(Theme.Font.sm())
                        .foregroundStyle(Theme.muted)
                }
                if let ac = flight.aircraft {
                    Text(ac)
                        .font(Theme.Font.sm())
                        .foregroundStyle(Theme.muted)
                }
            }
        }
        .panelStyle()
    }
}

// MARK: - Monthly Chart (fixed x-axis labels)

struct MonthlyChart: View {
    let data: [(month: Date, count: Int)]

    private var last12: [(month: Date, count: Int)] {
        Array(data.suffix(12))
    }

    var body: some View {
        if !last12.isEmpty {
            VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                Text("Flights by Month")
                    .font(Theme.Font.md(.semibold))

                Chart(last12, id: \.month) { item in
                    BarMark(
                        x: .value("Month", item.month, unit: .month),
                        y: .value("Flights", item.count)
                    )
                    .foregroundStyle(
                        .linearGradient(
                            colors: [Theme.primary, Theme.primary.opacity(0.5)],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )
                }
                .frame(height: 200)
                .chartXAxis {
                    AxisMarks(values: .stride(by: .month, count: xAxisStride)) { value in
                        AxisGridLine()
                        AxisValueLabel(format: xAxisFormat, centered: true)
                    }
                }
                .chartYAxis {
                    AxisMarks(position: .leading) { value in
                        AxisGridLine()
                        AxisValueLabel()
                    }
                }
            }
            .panelStyle()
        }
    }

    /// Show fewer labels when there are many months to prevent overlap.
    private var xAxisStride: Int {
        if last12.count <= 6 { return 1 }
        return 2
    }

    /// Use narrow month format for tight spaces.
    private var xAxisFormat: Date.FormatStyle {
        if last12.count <= 6 {
            return .dateTime.month(.abbreviated)
        }
        return .dateTime.month(.narrow)
    }
}

// MARK: - Flights by Year

struct YearlyFlightsChart: View {
    let data: [(year: Int, count: Int)]

    var body: some View {
        if !data.isEmpty {
            VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                Text("Flights by Year")
                    .font(Theme.Font.md(.semibold))

                Chart(data, id: \.year) { item in
                    BarMark(
                        x: .value("Year", String(item.year)),
                        y: .value("Flights", item.count)
                    )
                    .foregroundStyle(
                        .linearGradient(
                            colors: [Theme.primary, Theme.primary.opacity(0.5)],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )
                }
                .frame(height: 200)
                .chartXAxis {
                    AxisMarks { value in
                        AxisGridLine()
                        if let label = value.as(String.self) {
                            // Show short year for tight spaces
                            AxisValueLabel {
                                Text(data.count > 8 ? String(label.suffix(2)) : label)
                                    .font(Theme.Font.xs())
                            }
                        }
                    }
                }
                .chartYAxis {
                    AxisMarks(position: .leading) { _ in
                        AxisGridLine()
                        AxisValueLabel()
                    }
                }
            }
            .panelStyle()
        }
    }
}

// MARK: - Miles by Year

struct YearlyMilesChart: View {
    let data: [(year: Int, miles: Double)]
    @EnvironmentObject private var appState: AppState

    var body: some View {
        if !data.isEmpty {
            VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                Text("\(appState.distanceUnit.label) by Year")
                    .font(Theme.Font.md(.semibold))

                Chart(data, id: \.year) { item in
                    let converted = appState.distanceUnit.convert(item.miles)
                    BarMark(
                        x: .value("Year", String(item.year)),
                        y: .value(appState.distanceUnit.label, converted)
                    )
                    .foregroundStyle(
                        .linearGradient(
                            colors: [Theme.success, Theme.success.opacity(0.5)],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )
                }
                .frame(height: 200)
                .chartXAxis {
                    AxisMarks { value in
                        AxisGridLine()
                        if let label = value.as(String.self) {
                            AxisValueLabel {
                                Text(data.count > 8 ? String(label.suffix(2)) : label)
                                    .font(Theme.Font.xs())
                            }
                        }
                    }
                }
                .chartYAxis {
                    AxisMarks(position: .leading) { value in
                        AxisGridLine()
                        AxisValueLabel {
                            if let v = value.as(Double.self) {
                                Text(abbreviateNumber(v))
                                    .font(Theme.Font.xs())
                            }
                        }
                    }
                }
            }
            .panelStyle()
        }
    }
}

// MARK: - Top N Horizontal Bar Chart (counts)

struct TopNBarChart: View {
    let title: String
    let icon: String
    let data: [(label: String, count: Int)]
    let totalLabel: String

    var body: some View {
        if !data.isEmpty {
            VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                HStack {
                    Image(systemName: icon)
                        .foregroundStyle(Theme.primary)
                    Text(title)
                        .font(Theme.Font.md(.semibold))
                    Spacer()
                    Text(totalLabel)
                        .font(Theme.Font.xs())
                        .foregroundStyle(Theme.muted)
                }

                Chart(Array(data.enumerated()), id: \.offset) { _, item in
                    BarMark(
                        x: .value("Count", item.count),
                        y: .value("Name", item.label)
                    )
                    .foregroundStyle(Theme.primary.opacity(0.8))
                    .annotation(position: .trailing, spacing: 4) {
                        Text("\(item.count)")
                            .font(Theme.Font.xs())
                            .foregroundStyle(Theme.muted)
                    }
                }
                .frame(height: CGFloat(data.count) * 28 + 20)
                .chartYAxis {
                    AxisMarks(preset: .aligned) { value in
                        AxisValueLabel {
                            if let label = value.as(String.self) {
                                Text(truncateLabel(label, maxLength: 18))
                                    .font(Theme.Font.xs())
                                    .lineLimit(1)
                            }
                        }
                    }
                }
                .chartXAxis {
                    AxisMarks { value in
                        AxisGridLine()
                        AxisValueLabel {
                            if let v = value.as(Int.self) {
                                Text("\(v)")
                                    .font(Theme.Font.xs())
                            }
                        }
                    }
                }
            }
            .panelStyle()
        }
    }
}

// MARK: - Top N Horizontal Bar Chart (miles)

struct TopNMilesChart: View {
    let title: String
    let icon: String
    let data: [(label: String, miles: Double)]
    let distanceUnit: AppState.DistanceUnit
    let totalLabel: String

    var body: some View {
        if !data.isEmpty {
            VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                HStack {
                    Image(systemName: icon)
                        .foregroundStyle(Theme.primary)
                    Text(title)
                        .font(Theme.Font.md(.semibold))
                    Spacer()
                    Text(totalLabel)
                        .font(Theme.Font.xs())
                        .foregroundStyle(Theme.muted)
                }

                Chart(Array(data.enumerated()), id: \.offset) { _, item in
                    let converted = distanceUnit.convert(item.miles)
                    BarMark(
                        x: .value(distanceUnit.label, converted),
                        y: .value("Name", item.label)
                    )
                    .foregroundStyle(Theme.success.opacity(0.8))
                    .annotation(position: .trailing, spacing: 4) {
                        Text(abbreviateNumber(converted))
                            .font(Theme.Font.xs())
                            .foregroundStyle(Theme.muted)
                    }
                }
                .frame(height: CGFloat(data.count) * 28 + 20)
                .chartYAxis {
                    AxisMarks(preset: .aligned) { value in
                        AxisValueLabel {
                            if let label = value.as(String.self) {
                                Text(truncateLabel(label, maxLength: 18))
                                    .font(Theme.Font.xs())
                                    .lineLimit(1)
                            }
                        }
                    }
                }
                .chartXAxis {
                    AxisMarks { value in
                        AxisGridLine()
                        AxisValueLabel {
                            if let v = value.as(Double.self) {
                                Text(abbreviateNumber(v))
                                    .font(Theme.Font.xs())
                            }
                        }
                    }
                }
            }
            .panelStyle()
        }
    }
}

// MARK: - Recent Flights

struct RecentFlightsSection: View {
    let flights: [Flight]

    var body: some View {
        if !flights.isEmpty {
            VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                Text("Recent Flights")
                    .font(Theme.Font.md(.semibold))

                ForEach(flights, id: \.id) { flight in
                    NavigationLink(destination: FlightDetailView(flight: flight)) {
                        FlightRowView(flight: flight)
                    }
                    .buttonStyle(.plain)
                }
            }
            .panelStyle()
        }
    }
}

// MARK: - Helpers

private func truncateLabel(_ label: String, maxLength: Int) -> String {
    if label.count <= maxLength { return label }
    return String(label.prefix(maxLength - 1)) + "…"
}

private func abbreviateNumber(_ value: Double) -> String {
    if value >= 1_000_000 {
        return String(format: "%.1fM", value / 1_000_000)
    } else if value >= 1000 {
        return String(format: "%.0fK", value / 1000)
    }
    return String(format: "%.0f", value)
}
