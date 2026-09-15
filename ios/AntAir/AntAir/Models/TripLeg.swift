import Foundation
import SwiftData

@Model
final class TripLeg {
    @Attribute(.unique) var id: Int
    var syncRevision: Int64 = 0
    var locallyModified: Bool = false
    var locallyCreated: Bool = false
    var locallyDeleted: Bool = false

    var trip: Trip?
    var tripId: Int = 0
    var sequence: Int = 0
    var mode: String = "flight"
    var carrierName: String?
    var carrierCode: String?
    var serviceClass: String?
    var flightNumber: String?
    var aircraftType: String?
    var aircraftRegistration: String?
    var startCountry: String?
    var startCityName: String?
    var startAirport: String?
    var endCountry: String?
    var endCityName: String?
    var endAirport: String?
    var startDate: Date?
    var startDatePrecision: String?
    var startDateYear: Int?
    var startDateMonth: Int?
    var startDateDay: Int?
    var endDate: Date?
    var endDatePrecision: String?
    var endDateYear: Int?
    var endDateMonth: Int?
    var endDateDay: Int?
    var notes: String?

    var deletedAt: Date?
    var createdAt: Date
    var updatedAt: Date

    init(id: Int = 0, tripId: Int = 0) {
        self.id = id
        self.tripId = tripId
        self.createdAt = Date()
        self.updatedAt = Date()
    }
}
