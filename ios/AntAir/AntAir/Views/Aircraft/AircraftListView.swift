import SwiftUI
import SwiftData

struct AircraftListView: View {
    @Query(sort: \Aircraft.registration)
    private var aircraft: [Aircraft]

    @State private var searchText = ""

    var filteredAircraft: [Aircraft] {
        if searchText.isEmpty { return aircraft }
        let term = searchText.lowercased()
        return aircraft.filter { ac in
            ac.registration.lowercased().contains(term) ||
            (ac.type?.lowercased().contains(term) ?? false) ||
            (ac.manufacturer?.lowercased().contains(term) ?? false) ||
            (ac.registeredOwner?.lowercased().contains(term) ?? false)
        }
    }

    var body: some View {
        NavigationStack {
            List(filteredAircraft, id: \.id) { ac in
                NavigationLink(destination: AircraftDetailView(aircraft: ac)) {
                    AircraftRowView(aircraft: ac)
                }
            }
            .listStyle(.plain)
            .background(Theme.background)
            .scrollContentBackground(.hidden)
            .navigationTitle("Aircraft")
            .searchable(text: $searchText, prompt: "Search aircraft")
        }
    }
}

struct AircraftRowView: View {
    let aircraft: Aircraft

    var body: some View {
        HStack(spacing: Theme.Spacing.md) {
            if let photoURL = aircraft.urlPhotoThumbnail, let url = URL(string: photoURL) {
                AsyncImage(url: url) { image in
                    image.resizable().aspectRatio(contentMode: .fill)
                } placeholder: {
                    Image(systemName: "airplane.circle.fill")
                        .font(Theme.Font.xl())
                        .foregroundStyle(Theme.muted)
                }
                .frame(width: 60, height: 40)
                .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.sm))
            } else {
                Image(systemName: "airplane.circle.fill")
                    .font(Theme.Font.xl())
                    .foregroundStyle(Theme.muted)
                    .frame(width: 60, height: 40)
            }

            VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                Text(aircraft.registration)
                    .font(Theme.Font.base(.semibold))
                if let type = aircraft.type {
                    Text(type)
                        .font(Theme.Font.sm())
                        .foregroundStyle(Theme.muted)
                }
                if let owner = aircraft.registeredOwner {
                    Text(owner)
                        .font(Theme.Font.xs())
                        .foregroundStyle(Theme.muted)
                }
            }

            Spacer()

            if let manufacturer = aircraft.manufacturer {
                Text(manufacturer)
                    .font(Theme.Font.sm())
                    .foregroundStyle(Theme.summaryLabel)
            }
        }
        .padding(.vertical, Theme.Spacing.xxs)
    }
}

struct AircraftDetailView: View {
    let aircraft: Aircraft

    var body: some View {
        ScrollView {
            VStack(spacing: Theme.Spacing.lg) {
                // Photo
                if let photoURL = aircraft.urlPhoto, let url = URL(string: photoURL) {
                    AsyncImage(url: url) { image in
                        image.resizable().aspectRatio(contentMode: .fit)
                    } placeholder: {
                        ProgressView()
                    }
                    .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.lg))
                }

                // Details
                VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                    detailRow("Registration", aircraft.registration)
                    detailRow("Type", aircraft.type)
                    detailRow("ICAO Type", aircraft.icaoType)
                    detailRow("Manufacturer", aircraft.manufacturer)
                    detailRow("Mode S", aircraft.modeS)
                    detailRow("Owner", aircraft.registeredOwner)
                    detailRow("Country", aircraft.registeredOwnerCountryName)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .panelStyle()
            }
            .padding()
        }
        .background(Theme.background)
        .navigationTitle(aircraft.registration)
        .navigationBarTitleDisplayMode(.inline)
    }

    @ViewBuilder
    private func detailRow(_ label: String, _ value: String?) -> some View {
        if let value, !value.isEmpty {
            HStack {
                Text(label)
                    .foregroundStyle(Theme.summaryLabel)
                    .font(Theme.Font.base())
                Spacer()
                Text(value)
                    .font(Theme.Font.base())
            }
        }
    }
}
