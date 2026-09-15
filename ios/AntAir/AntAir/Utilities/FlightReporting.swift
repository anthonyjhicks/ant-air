import Foundation

/// Matches the web UI's `merged_flights_for_reporting()` logic:
/// groups flights by `groupingId`, picks one primary per group,
/// and returns a de-duplicated list for stats/reporting.
enum FlightReporting {

    /// Returns one flight per grouping_id group, sorted most-recent-first.
    /// Flights sharing a `groupingId` are collapsed into the primary
    /// (most recent start_date, highest id as tiebreaker).
    static func mergedForReporting(_ flights: [Flight]) -> [Flight] {
        var groups: [String: [Flight]] = [:]

        for flight in flights {
            let key = flight.groupingId ?? "single-\(flight.id)"
            groups[key, default: []].append(flight)
        }

        let primaries: [Flight] = groups.values.compactMap { items in
            items.sorted { a, b in
                if a.startDate != b.startDate {
                    return a.startDate > b.startDate
                }
                return a.id > b.id
            }.first
        }

        return primaries.sorted { $0.startDate > $1.startDate }
    }
}
