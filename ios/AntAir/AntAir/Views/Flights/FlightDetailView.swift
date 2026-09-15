import SwiftUI
import MapKit

struct FlightDetailView: View {
    let flight: Flight
    @EnvironmentObject private var appState: AppState
    @Environment(\.modelContext) private var modelContext
    @State private var showingEdit = false

    var body: some View {
        ScrollView {
            VStack(spacing: Theme.Spacing.lg) {
                // Route header
                routeHeader

                // Map snippet
                if let startLat = flight.startLat, let startLon = flight.startLong,
                   let endLat = flight.endLat, let endLon = flight.endLong {
                    FlightRouteMap(
                        startLat: startLat, startLon: startLon,
                        endLat: endLat, endLon: endLon
                    )
                    .frame(height: 200)
                    .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.lg))
                }

                // Flight info
                detailSection("Flight Info") {
                    detailRow("Flight Number", flight.flightNumber)
                    detailRow("Airline", flight.airlineCode)
                    detailRow("Operating Airline", flight.operatingAirlineCode)
                    detailRow("Aircraft", flight.aircraft)
                    detailRow("Registration", flight.aircraftRegistration)
                    detailRow("Service Class", flight.serviceClass)
                    if let dist = flight.distance {
                        let converted = appState.distanceUnit.convert(dist)
                        detailRow("Distance", "\(Int(converted)) \(appState.distanceUnit.abbreviation)")
                    }
                    detailRow("Stops", flight.stops.map { "\($0)" })
                }

                // Route info
                detailSection("Route") {
                    detailRow("Origin", [flight.startAirport, flight.startCityName, flight.startCountry].compactMap { $0 }.joined(separator: " \u{2014} "))
                    detailRow("Origin Terminal", flight.startTerminal)
                    detailRow("Departure", formatDateTime(date: flight.startDate, time: flight.startTime))
                    detailRow("Destination", [flight.endAirport, flight.endCityName, flight.endCountry].compactMap { $0 }.joined(separator: " \u{2014} "))
                    detailRow("Destination Terminal", flight.endTerminal)
                    detailRow("Arrival", formatDateTime(date: flight.endDate, time: flight.endTime))
                }

                // Booking info
                detailSection("Booking") {
                    detailRow("Trip", flight.tripName)
                    detailRow("Traveller", flight.traveller)
                    detailRow("Booking Site", flight.bookingSite)
                    detailRow("Confirmation", flight.supplierConfirmation)
                    detailRow("Ticket Number", flight.ticketNumber)
                    if let cost = flight.activityCost {
                        detailRow("Cost", String(format: "%.2f", cost))
                    }
                }
            }
            .padding()
        }
        .background(Theme.background)
        .navigationTitle(routeTitle)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button("Edit") { showingEdit = true }
                    .tint(Theme.primary)
            }
        }
        .sheet(isPresented: $showingEdit) {
            FlightFormView(editing: flight)
        }
    }

    private var routeTitle: String {
        [flight.startAirport, flight.endAirport].compactMap { $0 }.joined(separator: " \u{2192} ")
    }

    private var routeHeader: some View {
        HStack {
            VStack(alignment: .leading) {
                Text(flight.startAirport ?? "???")
                    .font(Theme.Font.xxl())
                Text(flight.startCityName ?? "")
                    .font(Theme.Font.sm())
                    .foregroundStyle(Theme.muted)
            }

            Spacer()

            VStack {
                Image(systemName: "airplane")
                    .font(Theme.Font.xl())
                    .foregroundStyle(Theme.primary)
                if let fn = flight.flightNumber {
                    Text(fn)
                        .font(Theme.Font.sm())
                        .foregroundStyle(Theme.muted)
                }
            }

            Spacer()

            VStack(alignment: .trailing) {
                Text(flight.endAirport ?? "???")
                    .font(Theme.Font.xxl())
                Text(flight.endCityName ?? "")
                    .font(Theme.Font.sm())
                    .foregroundStyle(Theme.muted)
            }
        }
        .panelStyle()
    }

    // MARK: - Helpers

    @ViewBuilder
    private func detailSection(_ title: String, @ViewBuilder content: () -> some View) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            Text(title)
                .font(Theme.Font.md(.semibold))
            content()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .panelStyle()
    }

    @ViewBuilder
    private func detailRow(_ label: String, _ value: String?) -> some View {
        if let value, !value.isEmpty {
            HStack {
                Text(label)
                    .foregroundStyle(Theme.summaryLabel)
                    .font(Theme.Font.base())
                Spacer()
                Text(value)
                    .font(Theme.Font.base())
            }
        }
    }

    private func formatDateTime(date: Date?, time: Date?) -> String? {
        guard let date else { return nil }
        let df = DateFormatter()
        df.dateStyle = .medium
        var result = df.string(from: date)
        if let time {
            let tf = DateFormatter()
            tf.dateFormat = "HH:mm"
            result += " " + tf.string(from: time)
        }
        return result
    }
}

// MARK: - Mini route map

struct FlightRouteMap: View {
    let startLat: Double
    let startLon: Double
    let endLat: Double
    let endLon: Double

    var body: some View {
        Map {
            Annotation("", coordinate: CLLocationCoordinate2D(latitude: startLat, longitude: startLon)) {
                Circle().fill(Theme.primary).frame(width: 8, height: 8)
            }
            Annotation("", coordinate: CLLocationCoordinate2D(latitude: endLat, longitude: endLon)) {
                Circle().fill(Theme.danger).frame(width: 8, height: 8)
            }
            MapPolyline(coordinates: [
                CLLocationCoordinate2D(latitude: startLat, longitude: startLon),
                CLLocationCoordinate2D(latitude: endLat, longitude: endLon),
            ])
            .stroke(Theme.primary, lineWidth: 2)
        }
    }
}
