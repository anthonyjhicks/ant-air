import Foundation
import SwiftData

@Model
final class Trip {
    @Attribute(.unique) var id: Int
    var syncRevision: Int64 = 0
    var locallyModified: Bool = false
    var locallyCreated: Bool = false
    var locallyDeleted: Bool = false

    var name: String?
    var tripCode: String?
    var tripType: String?
    var notes: String?
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

    @Relationship(deleteRule: .cascade, inverse: \TripLeg.trip)
    var legs: [TripLeg] = []

    var deletedAt: Date?
    var createdAt: Date
    var updatedAt: Date

    init(id: Int = 0) {
        self.id = id
        self.createdAt = Date()
        self.updatedAt = Date()
    }
}
