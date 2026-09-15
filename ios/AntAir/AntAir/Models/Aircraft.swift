import Foundation
import SwiftData

@Model
final class Aircraft {
    @Attribute(.unique) var id: Int
    var registration: String
    var syncRevision: Int64 = 0

    var type: String?
    var icaoType: String?
    var manufacturer: String?
    var modeS: String?
    var registeredOwnerCountryIsoName: String?
    var registeredOwnerCountryName: String?
    var registeredOwnerOperatorFlagCode: String?
    var registeredOwner: String?
    var urlPhoto: String?
    var urlPhotoThumbnail: String?
    var sourceUrl: String?

    var createdAt: Date
    var updatedAt: Date

    init(id: Int = 0, registration: String) {
        self.id = id
        self.registration = registration
        self.createdAt = Date()
        self.updatedAt = Date()
    }
}
