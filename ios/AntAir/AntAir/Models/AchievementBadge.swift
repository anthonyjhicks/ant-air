import Foundation
import SwiftData

@Model
final class AchievementBadge {
    @Attribute(.unique) var id: Int
    var syncRevision: Int64 = 0

    var name: String
    var descriptionText: String?
    var category: String?
    var badgeType: String
    var thresholdValue: Int
    var iconEmoji: String?
    var iconUrl: String?
    var displayOrder: Int = 0
    var isActive: Bool = true

    // Computed locally from flight stats
    var earned: Bool = false
    var progress: Double = 0

    var createdAt: Date
    var updatedAt: Date

    init(id: Int = 0, name: String, badgeType: String, thresholdValue: Int) {
        self.id = id
        self.name = name
        self.badgeType = badgeType
        self.thresholdValue = thresholdValue
        self.createdAt = Date()
        self.updatedAt = Date()
    }
}
