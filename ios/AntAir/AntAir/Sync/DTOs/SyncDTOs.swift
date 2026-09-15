import Foundation

// MARK: - Pull response

struct SyncPullResponse: Decodable {
    let currentRevision: Int64
    let flights: [FlightDTO]
    let trips: [TripDTO]
    let tripLegs: [TripLegDTO]
    let aircraft: [AircraftDTO]
    let badges: [BadgeDTO]
    let hasMore: Bool
    let nextCursor: Int?
}

struct FlightDTO: Decodable {
    let id: Int
    let status: String?
    let tripName: String?
    let tripId: String?
    let tripType: String?
    let tripLegId: Int?
    let activityId: String?
    let activityCost: Double?
    let url: String?
    let bookingSite: String?
    let supplierConfirmation: String?
    let bookingDate: String?
    let bookingSitePhone: String?
    let traveller: String?
    let ticketNumber: String?
    let airlineCode: String?
    let operatingAirlineCode: String?
    let aircraft: String?
    let aircraftTypeNormalized: String?
    let aircraftRegistration: String?
    let serviceClass: String?
    let flightNumber: String?
    let operatingFlightNumber: String?
    let startCountry: String?
    let startCityName: String?
    let startAirport: String?
    let startTerminal: String?
    let startLat: Double?
    let startLong: Double?
    let startDate: String?
    let startTime: String?
    let endCountry: String?
    let endCityName: String?
    let endAirport: String?
    let endTerminal: String?
    let endLat: Double?
    let endLong: Double?
    let endDate: String?
    let endTime: String?
    let stops: Int?
    let distance: Double?
    let routeDirection: String?
    let sourceFile: String?
    let groupingId: String?
    let auditMissingLegIgnored: Bool?
    let followUp: Bool?
    let excludeFromStats: Bool?
    let syncRevision: Int64
    let deletedAt: String?
    let createdAt: String?
    let updatedAt: String?
}

struct TripDTO: Decodable {
    let id: Int
    let name: String?
    let tripCode: String?
    let tripType: String?
    let notes: String?
    let startDate: String?
    let startDatePrecision: String?
    let startDateYear: Int?
    let startDateMonth: Int?
    let startDateDay: Int?
    let endDate: String?
    let endDatePrecision: String?
    let endDateYear: Int?
    let endDateMonth: Int?
    let endDateDay: Int?
    let syncRevision: Int64
    let deletedAt: String?
    let createdAt: String?
    let updatedAt: String?
}

struct TripLegDTO: Decodable {
    let id: Int
    let tripId: Int
    let sequence: Int?
    let mode: String?
    let carrierName: String?
    let carrierCode: String?
    let serviceClass: String?
    let flightNumber: String?
    let aircraftType: String?
    let aircraftRegistration: String?
    let startCountry: String?
    let startCityName: String?
    let startAirport: String?
    let endCountry: String?
    let endCityName: String?
    let endAirport: String?
    let startDate: String?
    let startDatePrecision: String?
    let startDateYear: Int?
    let startDateMonth: Int?
    let startDateDay: Int?
    let endDate: String?
    let endDatePrecision: String?
    let endDateYear: Int?
    let endDateMonth: Int?
    let endDateDay: Int?
    let notes: String?
    let syncRevision: Int64
    let deletedAt: String?
    let createdAt: String?
    let updatedAt: String?
}

struct AircraftDTO: Decodable {
    let id: Int
    let registration: String
    let type: String?
    let icaoType: String?
    let manufacturer: String?
    let modeS: String?
    let registeredOwnerCountryIsoName: String?
    let registeredOwnerCountryName: String?
    let registeredOwnerOperatorFlagCode: String?
    let registeredOwner: String?
    let urlPhoto: String?
    let urlPhotoThumbnail: String?
    let sourceUrl: String?
    let syncRevision: Int64
    let createdAt: String?
    let updatedAt: String?
}

struct BadgeDTO: Decodable {
    let id: Int
    let name: String
    let description: String?
    let category: String?
    let badgeType: String
    let thresholdValue: Int
    let iconEmoji: String?
    let iconUrl: String?
    let displayOrder: Int?
    let isActive: Bool?
    let syncRevision: Int64
    let createdAt: String?
    let updatedAt: String?
}

// MARK: - Push request/response

struct SyncPushRequest: Encodable {
    let clientId: String
    let changes: [SyncChange]
}

struct SyncChange: Encodable {
    let entityType: String
    let entityId: Int?
    let tempId: String?
    let changeType: String
    let baseRevision: Int64
    let fields: [String: AnyCodable]
}

struct SyncPushResponse: Decodable {
    let results: [SyncResult]
    let currentRevision: Int64
}

struct SyncResult: Decodable {
    let status: String
    let entityId: Int?
    let tempId: String?
    let revision: Int64?
    let message: String?
    let conflictingFields: [String]?
    let resolution: String?
}

// MARK: - Stats

struct StatsSummaryResponse: Decodable {
    let totalFlights: Int
    let totalMiles: Double
    let countries: Int
    let cities: Int
    let airlines: Int
    let aircraftTypes: Int
}

// MARK: - AnyCodable helper for encoding arbitrary JSON

struct AnyCodable: Encodable {
    let value: Any?

    init(_ value: Any?) {
        self.value = value
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        if value == nil {
            try container.encodeNil()
        } else if let v = value as? String {
            try container.encode(v)
        } else if let v = value as? Int {
            try container.encode(v)
        } else if let v = value as? Double {
            try container.encode(v)
        } else if let v = value as? Bool {
            try container.encode(v)
        } else {
            try container.encodeNil()
        }
    }
}
