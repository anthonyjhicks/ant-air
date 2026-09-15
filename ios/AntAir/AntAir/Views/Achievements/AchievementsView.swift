import SwiftUI
import SwiftData

struct AchievementsView: View {
    @Query(sort: \Flight.startDate, order: .reverse)
    private var allFlights: [Flight]

    @Query(sort: [SortDescriptor(\AchievementBadge.displayOrder), SortDescriptor(\AchievementBadge.id)])
    private var allBadges: [AchievementBadge]

    private var reportingFlights: [Flight] {
        let filtered = allFlights.filter {
            $0.status == "approved" && $0.deletedAt == nil && !$0.excludeFromStats
        }
        return FlightReporting.mergedForReporting(filtered)
    }

    private var activeBadges: [AchievementBadge] {
        allBadges.filter(\.isActive)
    }

    private var badgeProgress: [(badge: AchievementBadge, progress: BadgeCalculator.Progress)] {
        activeBadges.map { badge in
            (badge, BadgeCalculator.progress(for: badge, flights: reportingFlights))
        }
    }

    private var earned: [(badge: AchievementBadge, progress: BadgeCalculator.Progress)] {
        badgeProgress.filter(\.progress.earned)
    }

    private var locked: [(badge: AchievementBadge, progress: BadgeCalculator.Progress)] {
        badgeProgress.filter { !$0.progress.earned }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: Theme.Spacing.lg) {
                    // Summary header
                    HStack {
                        Text("\(earned.count) earned")
                            .font(Theme.Font.md(.semibold))
                        Text("/")
                            .foregroundStyle(Theme.muted)
                        Text("\(badgeProgress.count) total")
                            .font(Theme.Font.md())
                            .foregroundStyle(Theme.muted)
                    }
                    .padding(.top, Theme.Spacing.sm)

                    // Earned section
                    if !earned.isEmpty {
                        VStack(alignment: .leading, spacing: Theme.Spacing.md) {
                            Text("Earned")
                                .font(Theme.Font.md(.semibold))
                                .padding(.horizontal, Theme.Spacing.xs)

                            LazyVGrid(columns: [
                                GridItem(.flexible()),
                                GridItem(.flexible()),
                            ], spacing: Theme.Spacing.md) {
                                ForEach(earned, id: \.badge.id) { item in
                                    BadgeCard(badge: item.badge, progress: item.progress)
                                }
                            }
                        }
                    }

                    // Locked section
                    if !locked.isEmpty {
                        VStack(alignment: .leading, spacing: Theme.Spacing.md) {
                            Text("Locked")
                                .font(Theme.Font.md(.semibold))
                                .padding(.horizontal, Theme.Spacing.xs)

                            LazyVGrid(columns: [
                                GridItem(.flexible()),
                                GridItem(.flexible()),
                            ], spacing: Theme.Spacing.md) {
                                ForEach(locked, id: \.badge.id) { item in
                                    BadgeCard(badge: item.badge, progress: item.progress)
                                }
                            }
                        }
                    }

                    if badgeProgress.isEmpty {
                        VStack(spacing: Theme.Spacing.md) {
                            Image(systemName: "trophy")
                                .font(.system(size: 40))
                                .foregroundStyle(Theme.muted)
                            Text("No achievements yet")
                                .font(Theme.Font.md())
                                .foregroundStyle(Theme.muted)
                            Text("Sync to load badges from the server.")
                                .font(Theme.Font.sm())
                                .foregroundStyle(Theme.muted)
                        }
                        .padding(.top, Theme.Spacing.xxxl)
                    }
                }
                .padding()
            }
            .background(Theme.background)
            .navigationTitle("Achievements")
        }
    }
}

// MARK: - Badge Card

struct BadgeCard: View {
    let badge: AchievementBadge
    let progress: BadgeCalculator.Progress

    var body: some View {
        VStack(spacing: Theme.Spacing.sm) {
            // Icon
            Text(badge.iconEmoji ?? "🏆")
                .font(.system(size: 32))
                .opacity(progress.earned ? 1 : 0.3)

            // Name
            Text(badge.name)
                .font(Theme.Font.sm(.semibold))
                .multilineTextAlignment(.center)
                .lineLimit(2)

            // Description
            if let desc = badge.descriptionText {
                Text(desc)
                    .font(Theme.Font.xs())
                    .foregroundStyle(Theme.muted)
                    .multilineTextAlignment(.center)
                    .lineLimit(3)
            }

            // Progress
            if progress.earned {
                HStack(spacing: Theme.Spacing.xs) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(Theme.success)
                        .font(Theme.Font.sm())
                    Text("\(progress.current) / \(progress.target)")
                        .font(Theme.Font.xs())
                        .foregroundStyle(Theme.success)
                }
            } else {
                VStack(spacing: Theme.Spacing.xs) {
                    ProgressView(value: Double(progress.progressPercent), total: 100)
                        .tint(Theme.primary)
                    Text("\(progress.current) / \(progress.target)")
                        .font(Theme.Font.xs())
                        .foregroundStyle(Theme.muted)
                }
            }
        }
        .frame(maxWidth: .infinity)
        .padding(Theme.Spacing.md)
        .panelStyle()
    }
}
