import Foundation

/// Local badge progress calculation matching the web UI's calculate_badge_progress().
enum BadgeCalculator {

    struct Progress {
        let earned: Bool
        let current: Int
        let target: Int
        let progressPercent: Int
    }

    /// Calculate progress for a single badge against the given flights.
    static func progress(for badge: AchievementBadge, flights: [Flight]) -> Progress {
        let threshold = badge.thresholdValue
        var current = 0

        switch badge.badgeType {

        // ── Milestones ──────────────────────────────────────────
        case "flight_count":
            current = flights.count

        // ── Distance ────────────────────────────────────────────
        case "total_miles":
            current = Int(flights.compactMap(\.distance).reduce(0, +))

        // ── Geographic ──────────────────────────────────────────
        case "countries_visited":
            let countries = Set(
                flights.compactMap(\.startCountry) + flights.compactMap(\.endCountry)
            )
            current = countries.count

        case "continents_visited":
            let countries = Set(
                flights.compactMap(\.startCountry) + flights.compactMap(\.endCountry)
            )
            let continents = Set(countries.compactMap { mapCountryToContinent($0) })
            current = continents.count

        // ── Equipment ───────────────────────────────────────────
        case "aircraft_types":
            current = Set(flights.compactMap(\.aircraft)).count

        case "unique_registrations":
            current = Set(flights.compactMap(\.aircraftRegistration)).count

        case "airline_count":
            current = Set(flights.compactMap(\.airlineCode)).count

        // ── Temporal ────────────────────────────────────────────
        case "red_eye_count":
            var count = 0
            let calendar = Calendar.current
            for flight in flights {
                guard let startTime = flight.startTime,
                      let endDate = flight.endDate else { continue }
                let hour = calendar.component(.hour, from: startTime)
                let daysDiff = calendar.dateComponents([.day], from: flight.startDate, to: endDate).day ?? 0
                if hour >= 18 && daysDiff >= 1 {
                    count += 1
                }
            }
            current = count

        case "single_year_flights":
            let calendar = Calendar.current
            var yearCounts: [Int: Int] = [:]
            for flight in flights {
                let year = calendar.component(.year, from: flight.startDate)
                yearCounts[year, default: 0] += 1
            }
            current = yearCounts.values.max() ?? 0

        // ── Rare aircraft ───────────────────────────────────────
        case "rare_aircraft":
            let regCounts = Dictionary(
                flights.compactMap(\.aircraftRegistration).map { ($0.lowercased(), 1) },
                uniquingKeysWith: +
            )
            var count = 0
            for flight in flights {
                if let reg = flight.aircraftRegistration?.lowercased(),
                   let c = regCounts[reg], c > 0 && c <= 5 {
                    count += 1
                }
            }
            current = count

        default:
            // Handle rare_aircraft_* types
            if badge.badgeType.hasPrefix("rare_aircraft_") {
                let icaoType = String(badge.badgeType.dropFirst("rare_aircraft_".count)).uppercased()
                let patterns = Self.icaoToPatterns[icaoType] ?? [icaoType.lowercased()]
                for flight in flights {
                    if let normalized = flight.aircraftTypeNormalized?.lowercased(),
                       patterns.contains(where: { normalized.contains($0) }) {
                        current = 1
                        break
                    }
                }
            } else {
                current = 0
            }
        }

        let earned = current >= threshold
        let percent = threshold > 0 ? min(current * 100 / threshold, 100) : 0
        return Progress(earned: earned, current: current, target: threshold, progressPercent: percent)
    }

    // MARK: - Continent mapping

    private static func mapCountryToContinent(_ country: String) -> String? {
        let mapping: [String: String] = [
            // North America
            "United States": "North America", "Canada": "North America", "Mexico": "North America",
            // Europe
            "United Kingdom": "Europe", "France": "Europe", "Germany": "Europe",
            "Italy": "Europe", "Spain": "Europe", "Netherlands": "Europe",
            "Switzerland": "Europe", "Austria": "Europe", "Belgium": "Europe",
            "Greece": "Europe", "Portugal": "Europe", "Ireland": "Europe",
            "Poland": "Europe", "Czech Republic": "Europe", "Hungary": "Europe",
            "Denmark": "Europe", "Sweden": "Europe", "Norway": "Europe", "Finland": "Europe",
            // Asia
            "China": "Asia", "Japan": "Asia", "India": "Asia",
            "South Korea": "Asia", "Thailand": "Asia", "Singapore": "Asia",
            "Malaysia": "Asia", "Indonesia": "Asia", "Vietnam": "Asia",
            "Philippines": "Asia", "United Arab Emirates": "Asia",
            "Israel": "Asia", "Turkey": "Asia", "Qatar": "Asia",
            // South America
            "Brazil": "South America", "Argentina": "South America",
            "Chile": "South America", "Peru": "South America", "Colombia": "South America",
            // Africa
            "South Africa": "Africa", "Egypt": "Africa", "Morocco": "Africa", "Kenya": "Africa",
            // Oceania
            "Australia": "Oceania", "New Zealand": "Oceania",
        ]
        return mapping[country]
    }

    // MARK: - ICAO rare aircraft patterns

    private static let icaoToPatterns: [String: [String]] = [
        "B748": ["747-8", "747-8i", "747-800"],
        "A388": ["a380", "a-380"],
        "A346": ["a340-600", "a346", "340-600", "340-6"],
        "A343": ["a340-300", "a343", "340-300", "340-3"],
        "IL96": ["il-96", "il96", "ilyushin 96"],
        "B744": ["747-400", "747-4", "b744", "747-436", "747-438", "747-422"],
        "A338": ["a330-800", "a330-8", "a338", "330-800neo"],
        "B77L": ["777-200lr", "777-2lr", "b77l"],
        "A359": ["a350-900ulr", "a350-9ulr", "a359ulr"],
        "B712": ["717", "b717"],
        "MD82": ["md-82", "md82", "mcdonnell douglas 82"],
        "MD83": ["md-83", "md83", "mcdonnell douglas 83"],
        "MD88": ["md-88", "md88", "mcdonnell douglas 88"],
        "F70": ["fokker 70", "f70"],
        "F100": ["fokker 100", "f100"],
        "B732": ["737-200", "737-2", "b732"],
        "B733": ["737-300", "737-3", "b733"],
        "B734": ["737-400", "737-4", "b734"],
        "B735": ["737-500", "737-5", "b735"],
        "AJ27": ["arj21", "arj-21", "c909", "comac"],
        "SU95": ["superjet", "ssj100", "ssj-100", "su95", "sukhoi"],
        "T204": ["tu-204", "tu204", "tu-214", "tupolev 204"],
        "AN24": ["an-24", "an24", "antonov 24"],
        "L410": ["l-410", "l410", "let 410", "turbolet"],
        "DHC6": ["dhc-6", "dhc6", "twin otter", "de havilland 6"],
        "DHC7": ["dhc-7", "dhc7", "dash 7", "dash-7"],
        "D328": ["dornier 328", "d328", "do328"],
        "D228": ["dornier 228", "d228", "do228"],
        "SB20": ["saab 2000", "sb20"],
        "B463": ["bae 146", "bae146", "avro rj", "rj85", "rj100", "b463"],
    ]
}
