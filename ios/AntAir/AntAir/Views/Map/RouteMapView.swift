import SwiftUI
import SwiftData
import MapKit

struct RouteMapView: View {
    @Query(sort: \Flight.startDate, order: .reverse)
    private var allFlights: [Flight]

    private var flights: [Flight] {
        allFlights.filter { $0.status == "approved" && $0.deletedAt == nil && !$0.excludeFromStats }
    }

    /// Grouped flights for reporting — matches web UI's merged_flights_for_reporting().
    private var reportingFlights: [Flight] {
        FlightReporting.mergedForReporting(flights)
    }

    var routeFlights: [Flight] {
        reportingFlights.filter { f in
            f.startLat != nil && f.startLong != nil &&
            f.endLat != nil && f.endLong != nil
        }
    }

    var body: some View {
        NavigationStack {
            Map {
                ForEach(routeFlights, id: \.id) { flight in
                    if let startLat = flight.startLat, let startLon = flight.startLong,
                       let endLat = flight.endLat, let endLon = flight.endLong {
                        MapPolyline(coordinates: [
                            CLLocationCoordinate2D(latitude: startLat, longitude: startLon),
                            CLLocationCoordinate2D(latitude: endLat, longitude: endLon),
                        ])
                        .stroke(Theme.primary.opacity(0.5), lineWidth: 1.5)
                    }
                }

                // Airport pins
                ForEach(airportPins, id: \.code) { pin in
                    Annotation(pin.code, coordinate: pin.coordinate) {
                        Circle()
                            .fill(Theme.primary)
                            .frame(width: 6, height: 6)
                    }
                }
            }
            .navigationTitle("Route Map")
        }
    }

    private struct AirportPin {
        let code: String
        let coordinate: CLLocationCoordinate2D
    }

    private var airportPins: [AirportPin] {
        var seen = Set<String>()
        var pins: [AirportPin] = []
        for flight in routeFlights {
            if let code = flight.startAirport, let lat = flight.startLat, let lon = flight.startLong,
               !seen.contains(code) {
                seen.insert(code)
                pins.append(AirportPin(code: code, coordinate: CLLocationCoordinate2D(latitude: lat, longitude: lon)))
            }
            if let code = flight.endAirport, let lat = flight.endLat, let lon = flight.endLong,
               !seen.contains(code) {
                seen.insert(code)
                pins.append(AirportPin(code: code, coordinate: CLLocationCoordinate2D(latitude: lat, longitude: lon)))
            }
        }
        return pins
    }
}
