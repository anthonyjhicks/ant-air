import Foundation
import SwiftData

@Model
final class SyncMetadata {
    @Attribute(.unique) var id: Int = 1
    var lastPulledRevision: Int64 = 0
    var lastSyncDate: Date?
    var lastSyncError: String?

    init() {
        self.id = 1
    }
}

@Model
final class PendingChange {
    var changeId: UUID = UUID()
    var entityType: String
    var entityId: Int?
    var tempId: UUID?
    var changeType: String  // "create", "update", "delete"
    var payload: Data       // JSON-encoded changed fields
    var baseRevision: Int64 = 0
    var createdAt: Date = Date()
    var retryCount: Int = 0
    var lastError: String?

    init(entityType: String, entityId: Int? = nil, tempId: UUID? = nil,
         changeType: String, payload: Data, baseRevision: Int64 = 0) {
        self.entityType = entityType
        self.entityId = entityId
        self.tempId = tempId
        self.changeType = changeType
        self.payload = payload
        self.baseRevision = baseRevision
    }
}

@Model
final class SyncConflictLog {
    var conflictId: UUID = UUID()
    var entityType: String
    var entityId: Int
    var conflictDate: Date = Date()
    var clientFields: Data
    var serverFields: Data
    var resolution: String  // "auto_merged", "server_wins", "client_wins"
    var reviewed: Bool = false

    init(entityType: String, entityId: Int, clientFields: Data,
         serverFields: Data, resolution: String) {
        self.entityType = entityType
        self.entityId = entityId
        self.clientFields = clientFields
        self.serverFields = serverFields
        self.resolution = resolution
    }
}
