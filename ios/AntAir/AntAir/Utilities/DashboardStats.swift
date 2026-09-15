import Foundation

/// Pre-computed dashboard statistics matching the web UI's summarize_flights().
struct DashboardStats {
    let totalFlights: Int
    let totalMiles: Double

    let topCities: [(label: String, count: Int)]
    let topCountries: [(label: String, count: Int)]
    let topAirlines: [(label: String, count: Int)]
    let topAircraftTypes: [(label: String, count: Int)]
    let topAircraftMiles: [(label: String, miles: Double)]
    let topTailNumbers: [(label: String, count: Int)]
    let topRoutes: [(label: String, count: Int)]

    let monthlyFlights: [(month: Date, count: Int)]
    let yearlyFlights: [(year: Int, count: Int)]
    let yearlyMiles: [(year: Int, miles: Double)]

    let firstFlight: Flight?
    let lastFlight: Flight?

    static func compute(from flights: [Flight]) -> DashboardStats {
        let calendar = Calendar.current
        let totalMiles = flights.compactMap(\.distance).reduce(0, +)

        // ── Top Cities (by destination) ─────────────────────────
        var cityCounts: [String: Int] = [:]
        for f in flights {
            let city = (f.endCityName ?? f.endAirport ?? "Unknown").trimmingCharacters(in: .whitespaces)
            if !city.isEmpty { cityCounts[city, default: 0] += 1 }
        }
        let topCities = cityCounts.sorted { $0.value > $1.value }.map { ($0.key, $0.value) }

        // ── Top Countries (by destination) ──────────────────────
        var countryCounts: [String: Int] = [:]
        for f in flights {
            let country = (f.endCountry ?? "Unknown").trimmingCharacters(in: .whitespaces)
            if !country.isEmpty { countryCounts[country, default: 0] += 1 }
        }
        let topCountries = countryCounts.sorted { $0.value > $1.value }.map { ($0.key, $0.value) }

        // ── Top Airlines ────────────────────────────────────────
        var airlineCounts: [String: Int] = [:]
        for f in flights {
            let airline = (f.airlineCode ?? "Unknown").trimmingCharacters(in: .whitespaces)
            if !airline.isEmpty { airlineCounts[airline, default: 0] += 1 }
        }
        let topAirlines = airlineCounts.sorted { $0.value > $1.value }.map { ($0.key, $0.value) }

        // ── Top Aircraft Types ──────────────────────────────────
        var aircraftCounts: [String: Int] = [:]
        var aircraftMilesMap: [String: Double] = [:]
        for f in flights {
            let ac = (f.aircraft ?? "Unknown").trimmingCharacters(in: .whitespaces)
            if !ac.isEmpty {
                aircraftCounts[ac, default: 0] += 1
                aircraftMilesMap[ac, default: 0] += f.distance ?? 0
            }
        }
        let topAircraftTypes = aircraftCounts.sorted { $0.value > $1.value }.map { ($0.key, $0.value) }
        let topAircraftMiles = aircraftMilesMap.sorted { $0.value > $1.value }.map { ($0.key, $0.value) }

        // ── Top Tail Numbers ────────────────────────────────────
        var tailCounts: [String: Int] = [:]
        for f in flights {
            if let reg = f.aircraftRegistration?.trimmingCharacters(in: .whitespaces).uppercased(),
               !reg.isEmpty {
                tailCounts[reg, default: 0] += 1
            }
        }
        let topTailNumbers = tailCounts.sorted { $0.value > $1.value }.map { ($0.key, $0.value) }

        // ── Top Routes ──────────────────────────────────────────
        var routeCounts: [String: Int] = [:]
        for f in flights {
            let origin = f.originName
            let dest = f.destinationName
            let key = "\(origin) → \(dest)"
            routeCounts[key, default: 0] += 1
        }
        let topRoutes = routeCounts.sorted { $0.value > $1.value }.map { ($0.key, $0.value) }

        // ── Monthly ─────────────────────────────────────────────
        var monthMap: [Date: Int] = [:]
        for f in flights {
            if let start = calendar.dateInterval(of: .month, for: f.startDate)?.start {
                monthMap[start, default: 0] += 1
            }
        }
        let monthlyFlights = monthMap.sorted { $0.key < $1.key }.map { ($0.key, $0.value) }

        // ── Yearly ──────────────────────────────────────────────
        var yearCountMap: [Int: Int] = [:]
        var yearMilesMap: [Int: Double] = [:]
        for f in flights {
            let year = calendar.component(.year, from: f.startDate)
            yearCountMap[year, default: 0] += 1
            yearMilesMap[year, default: 0] += f.distance ?? 0
        }
        let yearlyFlights = yearCountMap.sorted { $0.key < $1.key }.map { ($0.key, $0.value) }
        let yearlyMiles = yearMilesMap.sorted { $0.key < $1.key }.map { ($0.key, $0.value) }

        // ── First / Last ────────────────────────────────────────
        let sorted = flights.sorted { $0.startDate < $1.startDate }
        let firstFlight = sorted.first
        let lastFlight = sorted.last

        return DashboardStats(
            totalFlights: flights.count,
            totalMiles: totalMiles,
            topCities: topCities,
            topCountries: topCountries,
            topAirlines: topAirlines,
            topAircraftTypes: topAircraftTypes,
            topAircraftMiles: topAircraftMiles,
            topTailNumbers: topTailNumbers,
            topRoutes: topRoutes,
            monthlyFlights: monthlyFlights,
            yearlyFlights: yearlyFlights,
            yearlyMiles: yearlyMiles,
            firstFlight: firstFlight,
            lastFlight: lastFlight
        )
    }
}
