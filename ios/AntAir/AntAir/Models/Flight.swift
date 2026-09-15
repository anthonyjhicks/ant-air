import Foundation
import SwiftData

@Model
final class Flight {
    @Attribute(.unique) var id: Int
    var syncRevision: Int64 = 0
    var locallyModified: Bool = false
    var locallyCreated: Bool = false
    var locallyDeleted: Bool = false

    // Status
    var status: String = "approved"
    var excludeFromStats: Bool = false
    var followUp: Bool = false

    // Trip
    var tripName: String?
    var tripId: String?
    var tripType: String?
    var tripLegId: Int?

    // Booking
    var activityId: String?
    var activityCost: Double?
    var url: String?
    var bookingSite: String?
    var supplierConfirmation: String?
    var bookingDate: Date?
    var bookingSitePhone: String?
    var traveller: String?
    var ticketNumber: String?

    // Flight info
    var airlineCode: String?
    var operatingAirlineCode: String?
    var aircraft: String?
    var aircraftTypeNormalized: String?
    var aircraftRegistration: String?
    var serviceClass: String?
    var flightNumber: String?
    var operatingFlightNumber: String?

    // Origin
    var startCountry: String?
    var startCityName: String?
    var startAirport: String?
    var startTerminal: String?
    var startLat: Double?
    var startLong: Double?
    var startDate: Date
    var startTime: Date?

    // Destination
    var endCountry: String?
    var endCityName: String?
    var endAirport: String?
    var endTerminal: String?
    var endLat: Double?
    var endLong: Double?
    var endDate: Date?
    var endTime: Date?

    // Metadata
    var stops: Int?
    var distance: Double?
    var routeDirection: String?
    var sourceFile: String?
    var groupingId: String?
    var auditMissingLegIgnored: Bool = false

    var deletedAt: Date?
    var createdAt: Date
    var updatedAt: Date

    var originName: String {
        startCityName ?? startAirport ?? startCountry ?? "-"
    }

    var destinationName: String {
        endCityName ?? endAirport ?? endCountry ?? "-"
    }

    init(
        id: Int = 0,
        startDate: Date,
        status: String = "approved"
    ) {
        self.id = id
        self.startDate = startDate
        self.status = status
        self.createdAt = Date()
        self.updatedAt = Date()
    }
}
