import Combine
import Foundation
import SwiftData

@MainActor
final class SyncEngine: ObservableObject {
    static let shared = SyncEngine()

    @Published var isSyncing = false
    @Published var lastError: String?

    private let api = APIClient.shared
    private let dateFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()
    private let timeFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss"
        return f
    }()

    // MARK: - Full sync cycle: push then pull

    func sync(modelContext: ModelContext) async {
        guard !isSyncing else { return }
        isSyncing = true
        lastError = nil

        do {
            try await pushChanges(modelContext: modelContext)
            try await pullChanges(modelContext: modelContext)
        } catch {
            lastError = error.localizedDescription
        }

        isSyncing = false
    }

    // MARK: - Push local changes to server

    func pushChanges(modelContext: ModelContext) async throws {
        let descriptor = FetchDescriptor<PendingChange>(
            sortBy: [SortDescriptor(\.createdAt)]
        )
        let pending = try modelContext.fetch(descriptor)
        guard !pending.isEmpty else { return }

        let clientId = deviceClientId()
        var changes: [SyncChange] = []

        for change in pending {
            let fields = (try? JSONSerialization.jsonObject(with: change.payload) as? [String: Any]) ?? [:]
            let encodableFields = fields.mapValues { AnyCodable($0) }

            changes.append(SyncChange(
                entityType: change.entityType,
                entityId: change.entityId,
                tempId: change.tempId?.uuidString,
                changeType: change.changeType,
                baseRevision: change.baseRevision,
                fields: encodableFields
            ))
        }

        let pushRequest = SyncPushRequest(clientId: clientId, changes: changes)
        let response: SyncPushResponse = try await api.request(
            path: "/api/v1/sync/push",
            method: "POST",
            body: pushRequest
        )

        // Process results
        for (i, result) in response.results.enumerated() {
            guard i < pending.count else { break }
            let change = pending[i]

            switch result.status {
            case "ok", "created", "deleted", "conflict_resolved":
                // Success — remove from pending queue
                modelContext.delete(change)

                // For creates, update the local record with the server-assigned ID
                if result.status == "created",
                   let tempId = change.tempId,
                   let serverId = result.entityId {
                    updateLocalIdAfterCreate(
                        modelContext: modelContext,
                        entityType: change.entityType,
                        tempId: tempId,
                        serverId: serverId
                    )
                }
            case "error":
                change.retryCount += 1
                change.lastError = result.message
            default:
                break
            }
        }

        try modelContext.save()
    }

    // MARK: - Pull changes from server

    func pullChanges(modelContext: ModelContext) async throws {
        let metaDescriptor = FetchDescriptor<SyncMetadata>()
        let metas = try modelContext.fetch(metaDescriptor)
        let meta = metas.first ?? {
            let m = SyncMetadata()
            modelContext.insert(m)
            return m
        }()

        // Capture since value before loop — updating it mid-pagination
        // would change the query filter and skip remaining pages.
        let sinceRevision = meta.lastPulledRevision
        var cursor: Int? = nil
        var hasMore = true
        var latestRevision: Int64 = sinceRevision

        while hasMore {
            var path = "/api/v1/sync/changes?since=\(sinceRevision)&limit=500"
            if let c = cursor {
                path += "&cursor=\(c)"
            }

            let response: SyncPullResponse = try await api.request(path: path)

            applyFlights(response.flights, modelContext: modelContext)
            applyTrips(response.trips, modelContext: modelContext)
            applyTripLegs(response.tripLegs, modelContext: modelContext)
            applyAircraft(response.aircraft, modelContext: modelContext)
            applyBadges(response.badges, modelContext: modelContext)

            hasMore = response.hasMore
            cursor = response.nextCursor
            latestRevision = response.currentRevision
        }

        meta.lastPulledRevision = latestRevision

        meta.lastSyncDate = Date()
        meta.lastSyncError = nil
        try modelContext.save()
    }

    // MARK: - Apply pulled data

    private func applyFlights(_ dtos: [FlightDTO], modelContext: ModelContext) {
        for dto in dtos {
            let targetId = dto.id
            let descriptor = FetchDescriptor<Flight>(
                predicate: #Predicate { $0.id == targetId }
            )
            let existing = try? modelContext.fetch(descriptor).first

            // Skip locally modified records
            if let existing, existing.locallyModified { continue }

            if dto.deletedAt != nil {
                if let existing {
                    modelContext.delete(existing)
                }
                continue
            }

            let flight = existing ?? Flight(id: dto.id, startDate: Date())
            if existing == nil {
                modelContext.insert(flight)
            }

            flight.id = dto.id
            flight.syncRevision = dto.syncRevision
            flight.status = dto.status ?? "approved"
            flight.tripName = dto.tripName
            flight.tripId = dto.tripId
            flight.tripType = dto.tripType
            flight.tripLegId = dto.tripLegId
            flight.activityId = dto.activityId
            flight.activityCost = dto.activityCost
            flight.url = dto.url
            flight.bookingSite = dto.bookingSite
            flight.supplierConfirmation = dto.supplierConfirmation
            flight.bookingDate = parseDate(dto.bookingDate)
            flight.bookingSitePhone = dto.bookingSitePhone
            flight.traveller = dto.traveller
            flight.ticketNumber = dto.ticketNumber
            flight.airlineCode = dto.airlineCode
            flight.operatingAirlineCode = dto.operatingAirlineCode
            flight.aircraft = dto.aircraft
            flight.aircraftTypeNormalized = dto.aircraftTypeNormalized
            flight.aircraftRegistration = dto.aircraftRegistration
            flight.serviceClass = dto.serviceClass
            flight.flightNumber = dto.flightNumber
            flight.operatingFlightNumber = dto.operatingFlightNumber
            flight.startCountry = dto.startCountry
            flight.startCityName = dto.startCityName
            flight.startAirport = dto.startAirport
            flight.startTerminal = dto.startTerminal
            flight.startLat = dto.startLat
            flight.startLong = dto.startLong
            flight.startDate = parseDate(dto.startDate) ?? Date()
            flight.startTime = parseTime(dto.startTime)
            flight.endCountry = dto.endCountry
            flight.endCityName = dto.endCityName
            flight.endAirport = dto.endAirport
            flight.endTerminal = dto.endTerminal
            flight.endLat = dto.endLat
            flight.endLong = dto.endLong
            flight.endDate = parseDate(dto.endDate)
            flight.endTime = parseTime(dto.endTime)
            flight.stops = dto.stops
            flight.distance = dto.distance
            flight.routeDirection = dto.routeDirection
            flight.sourceFile = dto.sourceFile
            flight.groupingId = dto.groupingId
            flight.auditMissingLegIgnored = dto.auditMissingLegIgnored ?? false
            flight.followUp = dto.followUp ?? false
            flight.excludeFromStats = dto.excludeFromStats ?? false
            flight.createdAt = parseDateTime(dto.createdAt) ?? Date()
            flight.updatedAt = parseDateTime(dto.updatedAt) ?? Date()
            flight.locallyModified = false
            flight.locallyCreated = false
        }
    }

    private func applyTrips(_ dtos: [TripDTO], modelContext: ModelContext) {
        for dto in dtos {
            let targetId = dto.id
            let descriptor = FetchDescriptor<Trip>(
                predicate: #Predicate { $0.id == targetId }
            )
            let existing = try? modelContext.fetch(descriptor).first

            if let existing, existing.locallyModified { continue }

            if dto.deletedAt != nil {
                if let existing { modelContext.delete(existing) }
                continue
            }

            let trip = existing ?? Trip(id: dto.id)
            if existing == nil { modelContext.insert(trip) }

            trip.syncRevision = dto.syncRevision
            trip.name = dto.name
            trip.tripCode = dto.tripCode
            trip.tripType = dto.tripType
            trip.notes = dto.notes
            trip.startDate = parseDate(dto.startDate)
            trip.startDatePrecision = dto.startDatePrecision
            trip.startDateYear = dto.startDateYear
            trip.startDateMonth = dto.startDateMonth
            trip.startDateDay = dto.startDateDay
            trip.endDate = parseDate(dto.endDate)
            trip.endDatePrecision = dto.endDatePrecision
            trip.endDateYear = dto.endDateYear
            trip.endDateMonth = dto.endDateMonth
            trip.endDateDay = dto.endDateDay
            trip.createdAt = parseDateTime(dto.createdAt) ?? Date()
            trip.updatedAt = parseDateTime(dto.updatedAt) ?? Date()
            trip.locallyModified = false
        }
    }

    private func applyTripLegs(_ dtos: [TripLegDTO], modelContext: ModelContext) {
        for dto in dtos {
            let targetId = dto.id
            let descriptor = FetchDescriptor<TripLeg>(
                predicate: #Predicate { $0.id == targetId }
            )
            let existing = try? modelContext.fetch(descriptor).first

            if let existing, existing.locallyModified { continue }

            if dto.deletedAt != nil {
                if let existing { modelContext.delete(existing) }
                continue
            }

            let leg = existing ?? TripLeg(id: dto.id, tripId: dto.tripId)
            if existing == nil { modelContext.insert(leg) }

            leg.syncRevision = dto.syncRevision
            leg.tripId = dto.tripId
            leg.sequence = dto.sequence ?? 0
            leg.mode = dto.mode ?? "flight"
            leg.carrierName = dto.carrierName
            leg.carrierCode = dto.carrierCode
            leg.serviceClass = dto.serviceClass
            leg.flightNumber = dto.flightNumber
            leg.aircraftType = dto.aircraftType
            leg.aircraftRegistration = dto.aircraftRegistration
            leg.startCountry = dto.startCountry
            leg.startCityName = dto.startCityName
            leg.startAirport = dto.startAirport
            leg.endCountry = dto.endCountry
            leg.endCityName = dto.endCityName
            leg.endAirport = dto.endAirport
            leg.startDate = parseDate(dto.startDate)
            leg.startDatePrecision = dto.startDatePrecision
            leg.startDateYear = dto.startDateYear
            leg.startDateMonth = dto.startDateMonth
            leg.startDateDay = dto.startDateDay
            leg.endDate = parseDate(dto.endDate)
            leg.endDatePrecision = dto.endDatePrecision
            leg.endDateYear = dto.endDateYear
            leg.endDateMonth = dto.endDateMonth
            leg.endDateDay = dto.endDateDay
            leg.notes = dto.notes
            leg.createdAt = parseDateTime(dto.createdAt) ?? Date()
            leg.updatedAt = parseDateTime(dto.updatedAt) ?? Date()
            leg.locallyModified = false
        }
    }

    private func applyAircraft(_ dtos: [AircraftDTO], modelContext: ModelContext) {
        for dto in dtos {
            let targetId = dto.id
            let descriptor = FetchDescriptor<Aircraft>(
                predicate: #Predicate { $0.id == targetId }
            )
            let existing = try? modelContext.fetch(descriptor).first

            let ac = existing ?? Aircraft(id: dto.id, registration: dto.registration)
            if existing == nil { modelContext.insert(ac) }

            ac.syncRevision = dto.syncRevision
            ac.registration = dto.registration
            ac.type = dto.type
            ac.icaoType = dto.icaoType
            ac.manufacturer = dto.manufacturer
            ac.modeS = dto.modeS
            ac.registeredOwnerCountryIsoName = dto.registeredOwnerCountryIsoName
            ac.registeredOwnerCountryName = dto.registeredOwnerCountryName
            ac.registeredOwnerOperatorFlagCode = dto.registeredOwnerOperatorFlagCode
            ac.registeredOwner = dto.registeredOwner
            ac.urlPhoto = dto.urlPhoto
            ac.urlPhotoThumbnail = dto.urlPhotoThumbnail
            ac.sourceUrl = dto.sourceUrl
            ac.createdAt = parseDateTime(dto.createdAt) ?? Date()
            ac.updatedAt = parseDateTime(dto.updatedAt) ?? Date()
        }
    }

    private func applyBadges(_ dtos: [BadgeDTO], modelContext: ModelContext) {
        for dto in dtos {
            let targetId = dto.id
            let descriptor = FetchDescriptor<AchievementBadge>(
                predicate: #Predicate { $0.id == targetId }
            )
            let existing = try? modelContext.fetch(descriptor).first

            let badge = existing ?? AchievementBadge(
                id: dto.id, name: dto.name,
                badgeType: dto.badgeType, thresholdValue: dto.thresholdValue
            )
            if existing == nil { modelContext.insert(badge) }

            badge.syncRevision = dto.syncRevision
            badge.name = dto.name
            badge.descriptionText = dto.description
            badge.category = dto.category
            badge.badgeType = dto.badgeType
            badge.thresholdValue = dto.thresholdValue
            badge.iconEmoji = dto.iconEmoji
            badge.iconUrl = dto.iconUrl
            badge.displayOrder = dto.displayOrder ?? 0
            badge.isActive = dto.isActive ?? true
            badge.createdAt = parseDateTime(dto.createdAt) ?? Date()
            badge.updatedAt = parseDateTime(dto.updatedAt) ?? Date()
        }
    }

    // MARK: - Helpers

    private func updateLocalIdAfterCreate(
        modelContext: ModelContext,
        entityType: String,
        tempId: UUID,
        serverId: Int
    ) {
        // For now this is a placeholder — proper implementation needs
        // a local temp ID tracking system in the models
    }

    private func deviceClientId() -> String {
        if let stored = UserDefaults.standard.string(forKey: "device_client_id") {
            return stored
        }
        let id = UUID().uuidString
        UserDefaults.standard.set(id, forKey: "device_client_id")
        return id
    }

    private func parseDate(_ string: String?) -> Date? {
        guard let string, !string.isEmpty else { return nil }
        return dateFormatter.date(from: string)
    }

    private func parseTime(_ string: String?) -> Date? {
        guard let string, !string.isEmpty else { return nil }
        return timeFormatter.date(from: string)
    }

    private func parseDateTime(_ string: String?) -> Date? {
        guard let string, !string.isEmpty else { return nil }
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = f.date(from: string) { return d }
        f.formatOptions = [.withInternetDateTime]
        return f.date(from: string)
    }
}
