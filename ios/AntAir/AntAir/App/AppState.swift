import SwiftUI
import Combine

@MainActor
final class AppState: ObservableObject {
    @Published var isAuthenticated = false
    @Published var isSyncing = false
    @Published var lastSyncDate: Date?
    @Published var pendingChangesCount = 0
    @Published var syncError: String?
    @Published var distanceUnit: DistanceUnit = .miles

    enum DistanceUnit: String, CaseIterable {
        case miles, kilometres

        var label: String {
            switch self {
            case .miles: return "Miles"
            case .kilometres: return "Kilometres"
            }
        }

        func convert(_ miles: Double) -> Double {
            switch self {
            case .miles: return miles
            case .kilometres: return miles * 1.60934
            }
        }

        var abbreviation: String {
            switch self {
            case .miles: return "mi"
            case .kilometres: return "km"
            }
        }
    }

    init() {
        if let stored = UserDefaults.standard.string(forKey: "distanceUnit"),
           let unit = DistanceUnit(rawValue: stored) {
            distanceUnit = unit
        }
        isAuthenticated = AuthManager.shared.hasValidToken
    }

    func setDistanceUnit(_ unit: DistanceUnit) {
        distanceUnit = unit
        UserDefaults.standard.set(unit.rawValue, forKey: "distanceUnit")
    }
}
