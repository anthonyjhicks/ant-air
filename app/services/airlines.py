from .analytics import normalize_airline_code

LOGO_URL_TEMPLATE = (
    "https://images.daisycon.io/airline/?width=200&height=200&color=ffffff&iata={code}"
)
LOGO_URL_TEMPLATE_ICAO = (
    "https://images.daisycon.io/airline/?width=200&height=200&color=ffffff&icao={code}"
)

AIRLINE_LOOKUP = {
    "AA": "American Airlines",
    "AC": "Air Canada",
    "AF": "Air France",
    "AS": "Alaska Airlines",
    "AY": "Finnair",
    "BA": "British Airways",
    "CJ": "BA Cityflyer",
    "CX": "Cathay Pacific",
    "D8": "Norwegian Air Shuttle",
    "DY": "Norwegian Air Shuttle",
    "DL": "Delta Air Lines",
    "EW": "Eurowings",
    "BD": "BMI",
    "EZS": "easyJet Switzerland",
    "FI": "Icelandair",
    "EI": "Aer Lingus",
    "EK": "Emirates",
    "EY": "Etihad Airways",
    "G3": "GOL Linhas Aereas",
    "IB": "Iberia",
    "JL": "Japan Airlines",
    "KL": "KLM",
    "LA": "LATAM Airlines",
    "LG": "Luxair",
    "LH": "Lufthansa",
    "LX": "SWISS",
    "4U": "Germanwings",
    "NH": "All Nippon Airways",
    "NM": "Mount Cook Airline",
    "NZ": "Air New Zealand",
    "OU": "Croatia Airlines",
    "OS": "Austrian Airlines",
    "QF": "Qantas",
    "QR": "Qatar Airways",
    "SQ": "Singapore Airlines",
    "SK": "SAS (Scandinavian Airlines)",
    "TOM": "Thomson Airways",
    "UA": "United Airlines",
    "VS": "Virgin Atlantic",
    "WN": "Southwest Airlines",
    "BY": "TUI Airways (formerly Thomson Airways)",
    "ZB": "Monarch Airlines",
    "AB": "Air Berlin",
    "AR": "Aerolineas Argentinas",
    "AN": "Ansett",
    "KM": "Air Malta",
    "YM": "Montenegro Airlines",
    "U2": "easyJet",
    "9F": "Eurostar",
}


def build_airline_logo_url(code):
    normalized = normalize_airline_code(code)
    if not normalized:
        return None
    template = LOGO_URL_TEMPLATE_ICAO if len(normalized) == 3 else LOGO_URL_TEMPLATE
    return template.format(code=normalized)


def lookup_airline_name(code):
    normalized = normalize_airline_code(code)
    if not normalized:
        return None
    return AIRLINE_LOOKUP.get(normalized)
