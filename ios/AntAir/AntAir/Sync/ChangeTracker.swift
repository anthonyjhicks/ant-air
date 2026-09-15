import Foundation
import SwiftData

/// Records local mutations as PendingChange entries for later sync.
@MainActor
struct ChangeTracker {

    static func trackFlightCreate(_ flight: Flight, modelContext: ModelContext) {
        flight.locallyCreated = true
        flight.locallyModified = true
        let fields = flightFields(flight)
        let payload = (try? JSONSerialization.data(withJSONObject: fields)) ?? Data()
        let change = PendingChange(
            entityType: "flight",
            tempId: UUID(),
            changeType: "create",
            payload: payload
        )
        modelContext.insert(change)
    }

    static func trackFlightUpdate(_ flight: Flight, changedFields: [String: Any], modelContext: ModelContext) {
        flight.locallyModified = true
        flight.updatedAt = Date()
        let payload = (try? JSONSerialization.data(withJSONObject: changedFields)) ?? Data()
        let change = PendingChange(
            entityType: "flight",
            entityId: flight.id,
            changeType: "update",
            payload: payload,
            baseRevision: flight.syncRevision
        )
        modelContext.insert(change)
    }

    static func trackFlightDelete(_ flight: Flight, modelContext: ModelContext) {
        flight.locallyDeleted = true
        flight.locallyModified = true
        let change = PendingChange(
            entityType: "flight",
            entityId: flight.id,
            changeType: "delete",
            payload: Data(),
            baseRevision: flight.syncRevision
        )
        modelContext.insert(change)
        modelContext.delete(flight)
    }

    static func trackTripCreate(_ trip: Trip, modelContext: ModelContext) {
        trip.locallyCreated = true
        trip.locallyModified = true
        let fields = tripFields(trip)
        let payload = (try? JSONSerialization.data(withJSONObject: fields)) ?? Data()
        let change = PendingChange(
            entityType: "trip",
            tempId: UUID(),
            changeType: "create",
            payload: payload
        )
        modelContext.insert(change)
    }

    static func trackTripUpdate(_ trip: Trip, changedFields: [String: Any], modelContext: ModelContext) {
        trip.locallyModified = true
        trip.updatedAt = Date()
        let payload = (try? JSONSerialization.data(withJSONObject: changedFields)) ?? Data()
        let change = PendingChange(
            entityType: "trip",
            entityId: trip.id,
            changeType: "update",
            payload: payload,
            baseRevision: trip.syncRevision
        )
        modelContext.insert(change)
    }

    static func trackTripDelete(_ trip: Trip, modelContext: ModelContext) {
        trip.locallyDeleted = true
        trip.locallyModified = true
        let change = PendingChange(
            entityType: "trip",
            entityId: trip.id,
            changeType: "delete",
            payload: Data(),
            baseRevision: trip.syncRevision
        )
        modelContext.insert(change)
        modelContext.delete(trip)
    }

    // MARK: - Field serialisers

    private static let df: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()
    private static let tf: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss"
        return f
    }()

    private static func flightFields(_ flight: Flight) -> [String: Any] {
        var d: [String: Any] = [
            "start_date": df.string(from: flight.startDate),
            "status": flight.status,
        ]
        if let v = flight.tripName { d["trip_name"] = v }
        if let v = flight.airlineCode { d["airline_code"] = v }
        if let v = flight.flightNumber { d["flight_number"] = v }
        if let v = flight.aircraft { d["aircraft"] = v }
        if let v = flight.startAirport { d["start_airport"] = v }
        if let v = flight.endAirport { d["end_airport"] = v }
        if let v = flight.startCityName { d["start_city_name"] = v }
        if let v = flight.endCityName { d["end_city_name"] = v }
        if let v = flight.startCountry { d["start_country"] = v }
        if let v = flight.endCountry { d["end_country"] = v }
        if let v = flight.traveller { d["traveller"] = v }
        if let v = flight.serviceClass { d["service_class"] = v }
        if let v = flight.distance { d["distance"] = v }
        if let v = flight.endDate { d["end_date"] = df.string(from: v) }
        if let v = flight.startTime { d["start_time"] = tf.string(from: v) }
        if let v = flight.endTime { d["end_time"] = tf.string(from: v) }
        if let v = flight.bookingSite { d["booking_site"] = v }
        if let v = flight.aircraftRegistration { d["aircraft_registration"] = v }
        d["follow_up"] = flight.followUp
        d["exclude_from_stats"] = flight.excludeFromStats
        return d
    }

    private static func tripFields(_ trip: Trip) -> [String: Any] {
        var d: [String: Any] = [:]
        if let v = trip.name { d["name"] = v }
        if let v = trip.tripCode { d["trip_code"] = v }
        if let v = trip.tripType { d["trip_type"] = v }
        if let v = trip.notes { d["notes"] = v }
        if let v = trip.startDate { d["start_date"] = df.string(from: v) }
        if let v = trip.endDate { d["end_date"] = df.string(from: v) }
        if let v = trip.startDatePrecision { d["start_date_precision"] = v }
        if let v = trip.endDatePrecision { d["end_date_precision"] = v }
        return d
    }
}
