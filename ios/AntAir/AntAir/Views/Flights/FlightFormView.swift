import SwiftUI
import SwiftData

struct FlightFormView: View {
    @Environment(\.modelContext) private var modelContext
    @Environment(\.dismiss) private var dismiss

    var editing: Flight?

    @State private var startDate = Date()
    @State private var endDate = Date()
    @State private var startAirport = ""
    @State private var endAirport = ""
    @State private var startCityName = ""
    @State private var endCityName = ""
    @State private var startCountry = ""
    @State private var endCountry = ""
    @State private var flightNumber = ""
    @State private var airlineCode = ""
    @State private var aircraft = ""
    @State private var aircraftRegistration = ""
    @State private var serviceClass = ""
    @State private var traveller = ""
    @State private var bookingSite = ""
    @State private var tripName = ""
    @State private var distance = ""

    var isEditing: Bool { editing != nil }

    var body: some View {
        NavigationStack {
            Form {
                Section("Route") {
                    HStack {
                        TextField("Origin (IATA)", text: $startAirport)
                            .textCase(.uppercase)
                        Image(systemName: "arrow.right")
                            .foregroundStyle(Theme.muted)
                        TextField("Destination (IATA)", text: $endAirport)
                            .textCase(.uppercase)
                    }
                    TextField("Origin City", text: $startCityName)
                    TextField("Destination City", text: $endCityName)
                    TextField("Origin Country", text: $startCountry)
                    TextField("Destination Country", text: $endCountry)
                    DatePicker("Departure Date", selection: $startDate, displayedComponents: .date)
                    DatePicker("Arrival Date", selection: $endDate, displayedComponents: .date)
                }

                Section("Flight Details") {
                    TextField("Flight Number", text: $flightNumber)
                    TextField("Airline Code", text: $airlineCode)
                        .textCase(.uppercase)
                    TextField("Aircraft Type", text: $aircraft)
                    TextField("Registration", text: $aircraftRegistration)
                        .textCase(.uppercase)
                    TextField("Service Class", text: $serviceClass)
                    TextField("Distance (miles)", text: $distance)
                        .keyboardType(.decimalPad)
                }

                Section("Booking") {
                    TextField("Trip Name", text: $tripName)
                    TextField("Traveller", text: $traveller)
                    TextField("Booking Site", text: $bookingSite)
                }
            }
            .navigationTitle(isEditing ? "Edit Flight" : "New Flight")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { save() }
                        .disabled(startAirport.isEmpty && endAirport.isEmpty)
                }
            }
            .onAppear { loadExistingData() }
        }
    }

    private func loadExistingData() {
        guard let flight = editing else { return }
        startDate = flight.startDate
        endDate = flight.endDate ?? Date()
        startAirport = flight.startAirport ?? ""
        endAirport = flight.endAirport ?? ""
        startCityName = flight.startCityName ?? ""
        endCityName = flight.endCityName ?? ""
        startCountry = flight.startCountry ?? ""
        endCountry = flight.endCountry ?? ""
        flightNumber = flight.flightNumber ?? ""
        airlineCode = flight.airlineCode ?? ""
        aircraft = flight.aircraft ?? ""
        aircraftRegistration = flight.aircraftRegistration ?? ""
        serviceClass = flight.serviceClass ?? ""
        traveller = flight.traveller ?? ""
        bookingSite = flight.bookingSite ?? ""
        tripName = flight.tripName ?? ""
        distance = flight.distance.map { String(format: "%.1f", $0) } ?? ""
    }

    private func save() {
        if let flight = editing {
            var changed: [String: Any] = [:]
            if flight.startAirport != nilIfEmpty(startAirport) { changed["start_airport"] = startAirport }
            if flight.endAirport != nilIfEmpty(endAirport) { changed["end_airport"] = endAirport }
            if flight.startCityName != nilIfEmpty(startCityName) { changed["start_city_name"] = startCityName }
            if flight.endCityName != nilIfEmpty(endCityName) { changed["end_city_name"] = endCityName }
            if flight.flightNumber != nilIfEmpty(flightNumber) { changed["flight_number"] = flightNumber }
            if flight.airlineCode != nilIfEmpty(airlineCode) { changed["airline_code"] = airlineCode }
            if flight.aircraft != nilIfEmpty(aircraft) { changed["aircraft"] = aircraft }
            if flight.aircraftRegistration != nilIfEmpty(aircraftRegistration) { changed["aircraft_registration"] = aircraftRegistration }
            if flight.traveller != nilIfEmpty(traveller) { changed["traveller"] = traveller }

            flight.startDate = startDate
            flight.endDate = endDate
            flight.startAirport = nilIfEmpty(startAirport)
            flight.endAirport = nilIfEmpty(endAirport)
            flight.startCityName = nilIfEmpty(startCityName)
            flight.endCityName = nilIfEmpty(endCityName)
            flight.startCountry = nilIfEmpty(startCountry)
            flight.endCountry = nilIfEmpty(endCountry)
            flight.flightNumber = nilIfEmpty(flightNumber)
            flight.airlineCode = nilIfEmpty(airlineCode)
            flight.aircraft = nilIfEmpty(aircraft)
            flight.aircraftRegistration = nilIfEmpty(aircraftRegistration)
            flight.serviceClass = nilIfEmpty(serviceClass)
            flight.traveller = nilIfEmpty(traveller)
            flight.bookingSite = nilIfEmpty(bookingSite)
            flight.tripName = nilIfEmpty(tripName)
            flight.distance = Double(distance)

            if !changed.isEmpty {
                ChangeTracker.trackFlightUpdate(flight, changedFields: changed, modelContext: modelContext)
            }
        } else {
            let flight = Flight(startDate: startDate)
            flight.endDate = endDate
            flight.startAirport = nilIfEmpty(startAirport)
            flight.endAirport = nilIfEmpty(endAirport)
            flight.startCityName = nilIfEmpty(startCityName)
            flight.endCityName = nilIfEmpty(endCityName)
            flight.startCountry = nilIfEmpty(startCountry)
            flight.endCountry = nilIfEmpty(endCountry)
            flight.flightNumber = nilIfEmpty(flightNumber)
            flight.airlineCode = nilIfEmpty(airlineCode)
            flight.aircraft = nilIfEmpty(aircraft)
            flight.aircraftRegistration = nilIfEmpty(aircraftRegistration)
            flight.serviceClass = nilIfEmpty(serviceClass)
            flight.traveller = nilIfEmpty(traveller)
            flight.bookingSite = nilIfEmpty(bookingSite)
            flight.tripName = nilIfEmpty(tripName)
            flight.distance = Double(distance)

            modelContext.insert(flight)
            ChangeTracker.trackFlightCreate(flight, modelContext: modelContext)
        }

        try? modelContext.save()
        dismiss()
    }

    private func nilIfEmpty(_ s: String) -> String? {
        s.trimmingCharacters(in: .whitespaces).isEmpty ? nil : s.trimmingCharacters(in: .whitespaces)
    }
}
