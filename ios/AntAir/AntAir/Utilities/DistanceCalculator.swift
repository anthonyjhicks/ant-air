import Foundation
import CoreLocation

struct DistanceCalculator {
    /// Calculate great-circle distance in miles between two coordinates.
    static func distanceMiles(
        fromLat: Double, fromLon: Double,
        toLat: Double, toLon: Double
    ) -> Double {
        let from = CLLocation(latitude: fromLat, longitude: fromLon)
        let to = CLLocation(latitude: toLat, longitude: toLon)
        let meters = from.distance(from: to)
        return meters / 1609.344  // meters to miles
    }
}
