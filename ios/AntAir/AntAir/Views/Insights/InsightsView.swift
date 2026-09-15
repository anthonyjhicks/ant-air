import SwiftUI

// MARK: - Response types

struct InsightsResponse: Decodable {
    let ok: Bool
    let insights: InsightsData?
    let error: String?
}

struct InsightsData: Codable {
    let travelPersonality: TravelPersonality?
    let geographic: GeographicInsights?
    let aircraftAviation: AircraftInsights?
    let airline: AirlineInsights?
    let temporal: TemporalInsights?
    let superlatives: [Superlative]?
    let funComparisons: [FunComparison]?
    let predictions: Predictions?
}

struct TravelPersonality: Codable {
    let title: String?
    let subtitle: String?
    let description: String?
    let traits: [Trait]?

    struct Trait: Codable, Identifiable {
        var id: String { name ?? UUID().uuidString }
        let name: String?
        let description: String?
    }
}

struct GeographicInsights: Codable {
    let highlights: [InsightHighlight]?
    let mapCompletion: MapCompletion?
    let missingDestinations: [String]?

    struct MapCompletion: Codable {
        let visitedCountries: Int?
        let percentage: Double?
        let detail: String?
    }
}

struct AircraftInsights: Codable {
    let highlights: [InsightHighlight]?
    let diversityScore: Int?
    let planeSpotterScore: Int?
    let manufacturerLoyalty: String?
    let widebodyRatio: String?
}

struct AirlineInsights: Codable {
    let highlights: [InsightHighlight]?
    let loyaltyIndex: Int?
    let allianceAnalysis: String?
    let fscLccRatio: String?
}

struct TemporalInsights: Codable {
    let highlights: [InsightHighlight]?
    let peakSeason: String?
    let rhythmDescription: String?
    let busiestPeriod: String?
    let yearOverYear: String?
}

struct InsightHighlight: Codable, Identifiable {
    var id: String { (title ?? "") + (value ?? "") }
    let title: String?
    let value: String?
    let detail: String?
    let icon: String?
}

struct Superlative: Codable, Identifiable {
    var id: String { (title ?? "") + (value ?? "") }
    let title: String?
    let value: String?
    let detail: String?
    let icon: String?
    let category: String?
}

struct FunComparison: Codable, Identifiable {
    var id: String { comparison ?? UUID().uuidString }
    let comparison: String?
    let value: String?
    let icon: String?
}

struct Predictions: Codable {
    let nextDestination: NextDestination?
    let travelTwin: TravelTwin?
    let growthTrend: String?

    struct NextDestination: Codable {
        let destination: String?
        let reasoning: String?
    }
    struct TravelTwin: Codable {
        let archetype: String?
        let reasoning: String?
    }
}

// MARK: - View

struct InsightsView: View {
    @State private var insightsData: InsightsData?
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var generatedAt: Date?

    private let api = APIClient.shared

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: Theme.Spacing.lg) {
                    // Generate button
                    Button {
                        Task { await generateInsights() }
                    } label: {
                        HStack {
                            if isLoading {
                                ProgressView()
                                    .scaleEffect(0.8)
                                    .tint(.white)
                            }
                            Text(isLoading ? "Generating..." : (insightsData != nil ? "Regenerate Insights" : "Generate Insights"))
                                .font(Theme.Font.md(.semibold))
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, Theme.Spacing.md)
                        .background(Theme.primary)
                        .foregroundStyle(.white)
                        .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.md))
                    }
                    .disabled(isLoading)

                    if let error = errorMessage {
                        Text(error)
                            .font(Theme.Font.sm())
                            .foregroundStyle(Theme.danger)
                            .panelStyle()
                    }

                    if let data = insightsData {
                        insightsContent(data)
                    } else if !isLoading {
                        emptyState
                    }
                }
                .padding()
            }
            .background(Theme.background)
            .navigationTitle("AI Insights")
        }
    }

    // MARK: - Empty state

    private var emptyState: some View {
        VStack(spacing: Theme.Spacing.md) {
            Image(systemName: "sparkles")
                .font(.system(size: 40))
                .foregroundStyle(Theme.muted)
            Text("No insights yet")
                .font(Theme.Font.md())
                .foregroundStyle(Theme.muted)
            Text("Generate AI-powered insights from your flight history.")
                .font(Theme.Font.sm())
                .foregroundStyle(Theme.muted)
                .multilineTextAlignment(.center)
        }
        .padding(.top, Theme.Spacing.xxxl)
    }

    // MARK: - Insights content

    @ViewBuilder
    private func insightsContent(_ data: InsightsData) -> some View {
        // Timestamp
        if let date = generatedAt {
            Text("Generated \(date, style: .relative) ago")
                .font(Theme.Font.xs())
                .foregroundStyle(Theme.muted)
        }

        // Travel Personality
        if let personality = data.travelPersonality {
            personalitySection(personality)
        }

        // Geographic
        if let geo = data.geographic {
            highlightSection(title: "Geographic", icon: "globe", highlights: geo.highlights)
            if let completion = geo.mapCompletion {
                mapCompletionCard(completion)
            }
        }

        // Aircraft & Aviation
        if let aircraft = data.aircraftAviation {
            highlightSection(title: "Aircraft & Aviation", icon: "airplane", highlights: aircraft.highlights)
            scoresRow(items: [
                ("Diversity", aircraft.diversityScore),
                ("Plane Spotter", aircraft.planeSpotterScore),
            ])
        }

        // Airline
        if let airline = data.airline {
            highlightSection(title: "Airlines", icon: "ticket", highlights: airline.highlights)
            if let loyalty = airline.loyaltyIndex {
                scoreCard(title: "Loyalty Index", value: loyalty)
            }
        }

        // Temporal
        if let temporal = data.temporal {
            highlightSection(title: "Temporal Patterns", icon: "calendar", highlights: temporal.highlights)
        }

        // Superlatives
        if let superlatives = data.superlatives, !superlatives.isEmpty {
            superlativesSection(superlatives)
        }

        // Fun comparisons
        if let comparisons = data.funComparisons, !comparisons.isEmpty {
            comparisonsSection(comparisons)
        }

        // Predictions
        if let predictions = data.predictions {
            predictionsSection(predictions)
        }
    }

    // MARK: - Section builders

    private func personalitySection(_ personality: TravelPersonality) -> some View {
        VStack(spacing: Theme.Spacing.md) {
            if let title = personality.title {
                Text(title)
                    .font(Theme.Font.xl())
                    .multilineTextAlignment(.center)
            }
            if let subtitle = personality.subtitle {
                Text(subtitle)
                    .font(Theme.Font.base())
                    .foregroundStyle(Theme.muted)
                    .multilineTextAlignment(.center)
            }
            if let desc = personality.description {
                Text(desc)
                    .font(Theme.Font.sm())
                    .foregroundStyle(Theme.muted)
                    .multilineTextAlignment(.center)
            }
            if let traits = personality.traits, !traits.isEmpty {
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: Theme.Spacing.sm) {
                    ForEach(traits) { trait in
                        VStack(spacing: Theme.Spacing.xs) {
                            Text(trait.name ?? "")
                                .font(Theme.Font.sm(.semibold))
                            Text(trait.description ?? "")
                                .font(Theme.Font.xs())
                                .foregroundStyle(Theme.muted)
                                .multilineTextAlignment(.center)
                        }
                        .padding(Theme.Spacing.sm)
                        .frame(maxWidth: .infinity)
                        .background(Theme.background)
                        .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.sm))
                    }
                }
            }
        }
        .panelStyle()
    }

    private func highlightSection(title: String, icon: String, highlights: [InsightHighlight]?) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.md) {
            HStack(spacing: Theme.Spacing.sm) {
                Image(systemName: icon)
                    .foregroundStyle(Theme.primary)
                Text(title)
                    .font(Theme.Font.md(.semibold))
            }

            if let highlights, !highlights.isEmpty {
                ForEach(highlights) { h in
                    HStack(alignment: .top) {
                        VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                            Text(h.title ?? "")
                                .font(Theme.Font.sm(.semibold))
                            if let detail = h.detail {
                                Text(detail)
                                    .font(Theme.Font.xs())
                                    .foregroundStyle(Theme.muted)
                            }
                        }
                        Spacer()
                        Text(h.value ?? "")
                            .font(Theme.Font.base(.semibold))
                            .foregroundStyle(Theme.primary)
                    }
                    .padding(.vertical, Theme.Spacing.xs)
                }
            }
        }
        .panelStyle()
    }

    private func mapCompletionCard(_ completion: GeographicInsights.MapCompletion) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                Text("Map Completion")
                    .font(Theme.Font.sm(.semibold))
                if let detail = completion.detail {
                    Text(detail)
                        .font(Theme.Font.xs())
                        .foregroundStyle(Theme.muted)
                }
            }
            Spacer()
            if let countries = completion.visitedCountries {
                Text("\(countries) countries")
                    .font(Theme.Font.base(.semibold))
                    .foregroundStyle(Theme.primary)
            }
        }
        .panelStyle()
    }

    private func scoresRow(items: [(String, Int?)]) -> some View {
        HStack(spacing: Theme.Spacing.md) {
            ForEach(items.indices, id: \.self) { i in
                if let value = items[i].1 {
                    scoreCard(title: items[i].0, value: value)
                }
            }
        }
    }

    private func scoreCard(title: String, value: Int) -> some View {
        VStack(spacing: Theme.Spacing.xs) {
            Text("\(value)")
                .font(Theme.Font.xl())
                .foregroundStyle(Theme.primary)
            Text(title)
                .font(Theme.Font.xs())
                .foregroundStyle(Theme.muted)
            ProgressView(value: Double(value), total: 100)
                .tint(Theme.primary)
        }
        .frame(maxWidth: .infinity)
        .panelStyle()
    }

    private func superlativesSection(_ superlatives: [Superlative]) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.md) {
            HStack(spacing: Theme.Spacing.sm) {
                Image(systemName: "trophy")
                    .foregroundStyle(Theme.primary)
                Text("Records & Superlatives")
                    .font(Theme.Font.md(.semibold))
            }

            ForEach(superlatives) { s in
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                        Text(s.title ?? "")
                            .font(Theme.Font.sm(.semibold))
                        if let detail = s.detail {
                            Text(detail)
                                .font(Theme.Font.xs())
                                .foregroundStyle(Theme.muted)
                        }
                    }
                    Spacer()
                    Text(s.value ?? "")
                        .font(Theme.Font.base(.semibold))
                        .foregroundStyle(Theme.primary)
                }
                .padding(.vertical, Theme.Spacing.xs)
            }
        }
        .panelStyle()
    }

    private func comparisonsSection(_ comparisons: [FunComparison]) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.md) {
            HStack(spacing: Theme.Spacing.sm) {
                Image(systemName: "lightbulb")
                    .foregroundStyle(Theme.primary)
                Text("Fun Comparisons")
                    .font(Theme.Font.md(.semibold))
            }

            ForEach(comparisons) { c in
                HStack {
                    Text(c.comparison ?? "")
                        .font(Theme.Font.sm())
                    Spacer()
                    Text(c.value ?? "")
                        .font(Theme.Font.sm(.semibold))
                        .foregroundStyle(Theme.primary)
                }
                .padding(.vertical, Theme.Spacing.xs)
            }
        }
        .panelStyle()
    }

    private func predictionsSection(_ predictions: Predictions) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.md) {
            HStack(spacing: Theme.Spacing.sm) {
                Image(systemName: "sparkles")
                    .foregroundStyle(Theme.primary)
                Text("Predictions")
                    .font(Theme.Font.md(.semibold))
            }

            if let next = predictions.nextDestination {
                VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                    Text("Next Destination")
                        .font(Theme.Font.sm(.semibold))
                    if let dest = next.destination {
                        Text(dest)
                            .font(Theme.Font.base(.semibold))
                            .foregroundStyle(Theme.primary)
                    }
                    if let reasoning = next.reasoning {
                        Text(reasoning)
                            .font(Theme.Font.xs())
                            .foregroundStyle(Theme.muted)
                    }
                }

                Divider()
            }

            if let twin = predictions.travelTwin {
                VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                    Text("Travel Twin")
                        .font(Theme.Font.sm(.semibold))
                    if let archetype = twin.archetype {
                        Text(archetype)
                            .font(Theme.Font.base(.semibold))
                            .foregroundStyle(Theme.primary)
                    }
                    if let reasoning = twin.reasoning {
                        Text(reasoning)
                            .font(Theme.Font.xs())
                            .foregroundStyle(Theme.muted)
                    }
                }

                Divider()
            }

            if let trend = predictions.growthTrend {
                VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                    Text("Growth Trend")
                        .font(Theme.Font.sm(.semibold))
                    Text(trend)
                        .font(Theme.Font.sm())
                        .foregroundStyle(Theme.muted)
                }
            }
        }
        .panelStyle()
    }

    // MARK: - API call

    private func generateInsights() async {
        isLoading = true
        errorMessage = nil

        do {
            let response: InsightsResponse = try await api.request(
                path: "/api/insights/generate",
                method: "POST"
            )
            if response.ok, let data = response.insights {
                insightsData = data
                generatedAt = Date()
            } else {
                errorMessage = response.error ?? "Failed to generate insights."
            }
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }
}
