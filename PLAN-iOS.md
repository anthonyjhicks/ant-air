# Ant Air — iOS App Plan

Full offline-capable iOS client with two-way sync against the existing Flask/PostgreSQL backend.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Backend Changes Required](#2-backend-changes-required)
3. [iOS App Structure](#3-ios-app-structure)
4. [Data Model (SwiftData)](#4-data-model-swiftdata)
5. [Offline Storage Strategy](#5-offline-storage-strategy)
6. [Two-Way Sync Engine](#6-two-way-sync-engine)
7. [Conflict Resolution](#7-conflict-resolution)
8. [Authentication](#8-authentication)
9. [Feature Map](#9-feature-map)
10. [Screen-by-Screen Breakdown](#10-screen-by-screen-breakdown)
11. [Networking Layer](#11-networking-layer)
12. [External API Proxying](#12-external-api-proxying)
13. [Testing Strategy](#13-testing-strategy)
14. [Phased Delivery](#14-phased-delivery)
15. [Open Questions and Risks](#15-open-questions-and-risks)

---

## 1. Architecture Overview

```
┌──────────────────────────────────────────────────┐
│                   iOS App                        │
│                                                  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  │
│  │  SwiftUI   │  │ SwiftData  │  │   Sync     │  │
│  │  Views     │──│ (SQLite)   │──│   Engine   │  │
│  │            │  │            │  │            │  │
│  └────────────┘  └────────────┘  └────────────┘  │
│                                       │          │
└───────────────────────────────────────┼──────────┘
                                        │
                              HTTPS (REST API)
                                        │
┌───────────────────────────────────────┼──────────┐
│              Flask Backend            │          │
│                                       ▼          │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  │
│  │ Existing   │  │  New REST  │  │  Sync      │  │
│  │ Web Routes │  │  API Layer │  │  Endpoints │  │
│  │            │  │ /api/v1/*  │  │            │  │
│  └────────────┘  └────────────┘  └────────────┘  │
│                       │                          │
│                  PostgreSQL                      │
└──────────────────────────────────────────────────┘
```

**iOS stack:**
- **Language:** Swift 6
- **UI:** SwiftUI (iOS 17+)
- **Local persistence:** SwiftData (backed by SQLite)
- **Networking:** URLSession + async/await
- **Charts:** Swift Charts
- **Maps:** MapKit

**Why SwiftData over Core Data:**
- Native Swift concurrency support
- Simpler model declarations with `@Model` macro
- Automatic schema migration
- Better SwiftUI integration with `@Query`
- iOS 17+ is acceptable for a personal-use app

---

## 2. Backend Changes Required

The existing web app is server-rendered (Jinja2). The iOS app needs a proper REST API. The existing `/api/*` endpoints cover search and aircraft lookup but not CRUD operations.

### 2.1 New REST API Blueprint: `/api/v1/`

A new `api_v1_bp` Flask Blueprint providing JSON-only endpoints:

#### Authentication
| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/auth/token` | POST | Exchange credentials for JWT |
| `/api/v1/auth/refresh` | POST | Refresh an expiring JWT |

#### Flights
| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/flights` | GET | List flights (paginated, filterable) |
| `/api/v1/flights` | POST | Create a flight |
| `/api/v1/flights/<id>` | GET | Get a single flight |
| `/api/v1/flights/<id>` | PUT | Update a flight |
| `/api/v1/flights/<id>` | DELETE | Delete a flight |
| `/api/v1/flights/<id>/follow-up` | PATCH | Toggle follow-up |
| `/api/v1/flights/<id>/exclude` | PATCH | Toggle exclude from stats |

#### Trips
| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/trips` | GET | List trips with legs |
| `/api/v1/trips` | POST | Create a trip |
| `/api/v1/trips/<id>` | GET | Get trip with legs |
| `/api/v1/trips/<id>` | PUT | Update trip |
| `/api/v1/trips/<id>` | DELETE | Delete trip |
| `/api/v1/trips/<id>/legs` | POST | Add a leg |
| `/api/v1/trips/<id>/legs/<leg_id>` | PUT | Update a leg |
| `/api/v1/trips/<id>/legs/<leg_id>` | DELETE | Delete a leg |

#### Aircraft
| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/aircraft` | GET | List aircraft |
| `/api/v1/aircraft/<registration>` | GET | Get aircraft detail |

#### Achievements
| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/achievements` | GET | Get all badges with earned status |

#### Dashboard / Stats
| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/stats/summary` | GET | Dashboard summary numbers |
| `/api/v1/stats/charts` | GET | Chart data (monthly, top airlines, etc.) |

#### Insights
| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/insights` | GET | Get cached insights |
| `/api/v1/insights/generate` | POST | Generate fresh insights |

#### Devices (Push Notifications)
| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/devices/register` | POST | Register/update APNs device token |
| `/api/v1/devices/unregister` | POST | Remove device token (on logout) |

#### Sync (see Section 6)
| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/sync/changes` | GET | Pull changes since timestamp |
| `/api/v1/sync/push` | POST | Push local changes |
| `/api/v1/sync/status` | GET | Get server sync state |

### 2.2 Database Schema Additions

Add to the existing PostgreSQL schema:

```sql
-- Track server-side changes for sync
ALTER TABLE flight ADD COLUMN sync_revision BIGINT NOT NULL DEFAULT 0;
ALTER TABLE flight ADD COLUMN deleted_at TIMESTAMPTZ;
ALTER TABLE trip ADD COLUMN sync_revision BIGINT NOT NULL DEFAULT 0;
ALTER TABLE trip ADD COLUMN deleted_at TIMESTAMPTZ;
ALTER TABLE trip_leg ADD COLUMN sync_revision BIGINT NOT NULL DEFAULT 0;
ALTER TABLE trip_leg ADD COLUMN deleted_at TIMESTAMPTZ;
ALTER TABLE aircraft ADD COLUMN sync_revision BIGINT NOT NULL DEFAULT 0;
ALTER TABLE achievement_badge ADD COLUMN sync_revision BIGINT NOT NULL DEFAULT 0;

-- Global monotonic revision counter
CREATE TABLE sync_state (
    id INTEGER PRIMARY KEY DEFAULT 1,
    current_revision BIGINT NOT NULL DEFAULT 0,
    CHECK (id = 1)
);

-- Authentication
CREATE TABLE api_user (
    id SERIAL PRIMARY KEY,
    username VARCHAR(64) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    last_login TIMESTAMPTZ
);

-- Push notification device registration
CREATE TABLE apns_device (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES api_user(id) ON DELETE CASCADE,
    client_id UUID NOT NULL,
    device_token VARCHAR(255) NOT NULL,
    platform VARCHAR(16) DEFAULT 'ios',  -- future: ipados, watchos
    last_seen TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (client_id, device_token)
);
```

### 2.3 Sync Revision Trigger

Every INSERT or UPDATE on synced tables bumps `sync_state.current_revision` and stamps the row's `sync_revision` with the new value. This can be done as a PostgreSQL trigger or in the SQLAlchemy event hooks.

### 2.4 Soft Deletes

Change existing DELETE operations to set `deleted_at` instead of removing rows. The sync pull endpoint returns deleted records so the iOS client can remove them locally. A periodic cleanup job hard-deletes records where `deleted_at` is older than 90 days.

---

## 3. iOS App Structure

```
AntAir/
├── App/
│   ├── AntAirApp.swift          # @main entry, SwiftData container setup
│   ├── AppState.swift               # Global app state (sync status, connectivity)
│   └── ContentView.swift            # Tab-based root navigation
├── Models/
│   ├── Flight.swift                 # @Model
│   ├── Trip.swift                   # @Model
│   ├── TripLeg.swift                # @Model
│   ├── Aircraft.swift               # @Model
│   ├── AchievementBadge.swift       # @Model
│   ├── InsightCache.swift           # @Model
│   ├── SyncMetadata.swift           # @Model (tracks last sync revision)
│   └── PendingChange.swift          # @Model (offline change queue)
├── Views/
│   ├── Dashboard/
│   │   ├── DashboardView.swift
│   │   ├── StatsCardsView.swift
│   │   ├── NextFlightCard.swift
│   │   └── ChartsSection.swift
│   ├── Flights/
│   │   ├── FlightListView.swift
│   │   ├── FlightDetailView.swift
│   │   ├── FlightFormView.swift
│   │   └── FlightFilterSheet.swift
│   ├── Trips/
│   │   ├── TripListView.swift
│   │   ├── TripDetailView.swift
│   │   └── TripFormView.swift
│   ├── Aircraft/
│   │   ├── AircraftListView.swift
│   │   └── AircraftDetailView.swift
│   ├── Timeline/
│   │   └── TimelineView.swift
│   ├── Achievements/
│   │   └── AchievementsView.swift
│   ├── Insights/
│   │   └── InsightsView.swift
│   ├── Map/
│   │   └── RouteMapView.swift
│   ├── Search/
│   │   └── SearchView.swift
│   ├── Settings/
│   │   ├── SettingsView.swift
│   │   └── SyncStatusView.swift
│   └── Common/
│       ├── AirlineLogoView.swift
│       ├── AircraftPhotoView.swift
│       └── EmptyStateView.swift
├── Sync/
│   ├── SyncEngine.swift             # Orchestrates pull/push cycles
│   ├── SyncScheduler.swift          # Background refresh + connectivity monitor
│   ├── ConflictResolver.swift       # Handles merge conflicts
│   ├── ChangeTracker.swift          # Records local mutations
│   └── DTOs/                        # Codable structs for API responses
│       ├── FlightDTO.swift
│       ├── TripDTO.swift
│       ├── SyncPullResponse.swift
│       └── SyncPushRequest.swift
├── Network/
│   ├── APIClient.swift              # URLSession wrapper, auth, retry
│   ├── AuthManager.swift            # JWT storage (Keychain), refresh
│   ├── Endpoints.swift              # Endpoint definitions
│   └── NetworkMonitor.swift         # NWPathMonitor wrapper
└── Utilities/
    ├── DistanceCalculator.swift     # Haversine distance
    ├── DateFormatting.swift
    └── AirlineData.swift            # Bundled airline lookup data
```

---

## 4. Data Model (SwiftData)

### 4.1 Flight

```swift
@Model
final class Flight {
    // Identity & sync
    @Attribute(.unique) var id: Int
    var syncRevision: Int64 = 0
    var locallyModified: Bool = false
    var locallyCreated: Bool = false
    var locallyDeleted: Bool = false

    // Status
    var status: String = "approved"  // approved | draft
    var excludeFromStats: Bool = false
    var followUp: Bool = false

    // Trip
    var tripName: String?
    var tripId: String?
    var tripType: String?

    // Booking
    var bookingSite: String?
    var supplierConfirmation: String?
    var bookingDate: Date?
    var ticketNumber: String?
    var activityCost: Decimal?
    var url: String?

    // Passenger
    var traveller: String?
    var serviceClass: String?

    // Flight
    var airlineCode: String?
    var operatingAirlineCode: String?
    var flightNumber: String?
    var operatingFlightNumber: String?

    // Aircraft
    var aircraft: String?
    var aircraftTypeNormalized: String?
    var aircraftRegistration: String?

    // Origin
    var startCountry: String?
    var startCityName: String?
    var startAirport: String?
    var startTerminal: String?
    var startLat: Double?
    var startLong: Double?
    var startDate: Date
    var startTime: Date?   // Time-only stored as Date

    // Destination
    var endCountry: String?
    var endCityName: String?
    var endAirport: String?
    var endTerminal: String?
    var endLat: Double?
    var endLong: Double?
    var endDate: Date?
    var endTime: Date?

    // Metadata
    var stops: Int?
    var distance: Double?
    var routeDirection: String?
    var sourceFile: String?
    var groupingId: String?

    var createdAt: Date
    var updatedAt: Date
}
```

### 4.2 Trip & TripLeg

```swift
@Model
final class Trip {
    @Attribute(.unique) var id: Int
    var syncRevision: Int64 = 0
    var locallyModified: Bool = false

    var name: String?
    var tripCode: String?
    var tripType: String?
    var notes: String?
    var startDate: Date?
    var startDatePrecision: String?
    var endDate: Date?
    var endDatePrecision: String?

    @Relationship(deleteRule: .cascade, inverse: \TripLeg.trip)
    var legs: [TripLeg] = []

    var createdAt: Date
    var updatedAt: Date
}

@Model
final class TripLeg {
    @Attribute(.unique) var id: Int
    var syncRevision: Int64 = 0
    var locallyModified: Bool = false

    var trip: Trip?
    var sequence: Int = 0
    var mode: String = "flight"
    var carrierName: String?
    var carrierCode: String?
    var flightNumber: String?
    var aircraftType: String?
    var startCityName: String?
    var startAirport: String?
    var endCityName: String?
    var endAirport: String?
    var startDate: Date?
    var endDate: Date?
    var notes: String?

    var createdAt: Date
    var updatedAt: Date
}
```

### 4.3 Aircraft

```swift
@Model
final class Aircraft {
    @Attribute(.unique) var registration: String
    var syncRevision: Int64 = 0

    var type: String?
    var icaoType: String?
    var manufacturer: String?
    var modeS: String?
    var registeredOwner: String?
    var registeredOwnerCountryName: String?
    var urlPhoto: String?
    var urlPhotoThumbnail: String?

    var createdAt: Date
    var updatedAt: Date
}
```

### 4.4 Sync Tracking

```swift
@Model
final class SyncMetadata {
    @Attribute(.unique) var id: Int = 1
    var lastPulledRevision: Int64 = 0
    var lastSyncDate: Date?
    var lastSyncError: String?
}

@Model
final class PendingChange {
    var id: UUID = UUID()
    var entityType: String      // "flight", "trip", "trip_leg"
    var entityId: Int?          // nil for creates (use tempId)
    var tempId: UUID?           // local ID for new records
    var changeType: String      // "create", "update", "delete"
    var payload: Data           // JSON-encoded changed fields
    var createdAt: Date = Date()
    var retryCount: Int = 0
    var lastError: String?
}
```

---

## 5. Offline Storage Strategy

### 5.1 Principles

1. **Local-first**: All reads come from SwiftData. The UI never waits for network.
2. **Full dataset**: The complete flight/trip/aircraft database is stored locally (the dataset is personal and bounded — likely hundreds to low thousands of records).
3. **Optimistic writes**: Creates, updates, and deletes apply to SwiftData immediately and queue a `PendingChange` for sync.
4. **Bundled reference data**: Airline names/logos and airport codes ship as bundled JSON files in the app so lookups work offline.

### 5.2 Initial Sync (First Launch)

1. User logs in (JWT obtained and stored in Keychain).
2. Full pull: `GET /api/v1/sync/changes?since=0` returns all records.
3. Records are inserted into SwiftData in a background `ModelActor`.
4. `SyncMetadata.lastPulledRevision` is set to the server's `current_revision`.
5. A progress indicator shows download status.

### 5.3 Storage Sizing

Estimated per the current data model:
- ~1,000 flights x ~2 KB each = ~2 MB
- ~100 trips x ~1 KB = ~100 KB
- ~500 aircraft x ~500 B = ~250 KB
- Total: < 5 MB for a heavy user. Easily fits on any device.

### 5.4 Image Caching

Aircraft photos and airline logos are cached separately using `URLCache` with a 100 MB disk limit. Photos are fetched on demand and not part of the sync payload.

---

## 6. Two-Way Sync Engine

### 6.1 Overview

The sync follows a **push-then-pull** pattern:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   1. PUSH   │────▶│  2. SERVER  │────▶│   3. PULL   │
│ Local queue  │     │  Process    │     │ New changes  │
│ → server     │     │  + respond  │     │ → local DB   │
└─────────────┘     └─────────────┘     └─────────────┘
```

### 6.2 Push Phase

1. Read all `PendingChange` records ordered by `createdAt`.
2. Batch into a single `POST /api/v1/sync/push` request:
   ```json
   {
     "client_id": "uuid-of-this-device",
     "changes": [
       {
         "entity_type": "flight",
         "entity_id": 42,
         "change_type": "update",
         "base_revision": 15,
         "fields": { "aircraft": "Boeing 787-9", "distance": 5461.2 }
       },
       {
         "entity_type": "flight",
         "temp_id": "a1b2c3d4-...",
         "change_type": "create",
         "fields": { "start_airport": "LHR", "end_airport": "JFK", ... }
       }
     ]
   }
   ```
3. Server processes each change:
   - **Create**: Insert row, assign server ID, bump revision. Return `{ temp_id, server_id, revision }`.
   - **Update**: If `base_revision` matches current row revision, apply and bump. If not, return conflict.
   - **Delete**: Soft-delete (set `deleted_at`), bump revision.
4. Server responds with results per change:
   ```json
   {
     "results": [
       { "status": "ok", "entity_id": 42, "new_revision": 16 },
       { "status": "created", "temp_id": "a1b2c3d4-...", "entity_id": 99, "revision": 17 },
       { "status": "conflict", "entity_id": 50, "server_fields": {...}, "server_revision": 18 }
     ],
     "current_revision": 18
   }
   ```
5. For each successful result, delete the corresponding `PendingChange`.
6. For conflicts, invoke the conflict resolver (Section 7).

### 6.3 Pull Phase

1. `GET /api/v1/sync/changes?since=<lastPulledRevision>`
2. Server returns all rows with `sync_revision > since`, including soft-deleted ones:
   ```json
   {
     "current_revision": 25,
     "flights": [
       { "id": 42, "sync_revision": 16, "deleted_at": null, ... },
       { "id": 10, "sync_revision": 20, "deleted_at": "2026-02-20T...", ... }
     ],
     "trips": [...],
     "trip_legs": [...],
     "aircraft": [...],
     "badges": [...]
   }
   ```
3. For each record:
   - If locally modified (`locallyModified == true`): skip — it will be resolved on next push.
   - If not locally modified: upsert into SwiftData. If `deleted_at` is set, delete locally.
4. Update `SyncMetadata.lastPulledRevision`.

### 6.4 Sync Triggers

| Trigger | Behaviour |
|---|---|
| App launch (foreground) | Full push-then-pull cycle |
| Pull-to-refresh on any list | Full push-then-pull cycle |
| After a local write (debounced 5s) | Push only, then pull |
| Network restored after offline | Full push-then-pull cycle |
| Background app refresh (iOS) | Full push-then-pull cycle (via `BGAppRefreshTask`) |
| Manual "Sync Now" button | Full push-then-pull cycle with progress UI |

### 6.5 Pagination for Large Pulls

If a pull would return more than 500 records (e.g., initial sync), the server paginates:

```
GET /api/v1/sync/changes?since=0&limit=500
→ { ..., "has_more": true, "next_cursor": 500 }

GET /api/v1/sync/changes?since=0&limit=500&cursor=500
→ { ..., "has_more": false }
```

---

## 7. Conflict Resolution

### 7.1 When Conflicts Occur

A conflict occurs when:
- The client pushes an update with `base_revision = N`
- The server's current revision for that row is `M` where `M > N`
- Meaning someone (or the web app) modified the row after the client last saw it

### 7.2 Strategy: Field-Level Last-Write-Wins with Notification

Since this is a single-user personal app, true concurrent editing is rare. The most common scenario is: user edits a flight on the web, then edits a different field on iOS before syncing.

**Resolution algorithm:**

1. Compare the client's changed fields against the server's changed fields (since the common base revision).
2. If the changed field sets are **disjoint** (no overlap): merge automatically — apply client's fields to server, bump revision. No user action needed.
3. If the changed field sets **overlap**: apply last-write-wins based on `updated_at` timestamp, but flag the record and show a notification to the user:
   - "Flight LHR→JFK was also modified on the web. The most recent change was kept."
   - The user can open a "Sync Conflicts" view in Settings to review resolved conflicts.

### 7.3 Conflict Log

```swift
@Model
final class SyncConflictLog {
    var id: UUID = UUID()
    var entityType: String
    var entityId: Int
    var conflictDate: Date = Date()
    var clientFields: Data     // JSON of what the client tried to set
    var serverFields: Data     // JSON of what the server had
    var resolution: String     // "auto_merged", "server_wins", "client_wins"
    var reviewed: Bool = false
}
```

---

## 8. Authentication

The current web app has no built-in auth. The iOS app requires it.

### 8.1 Approach: API Key + JWT

1. **Setup**: A single API user is created via a CLI command (`flask create-api-user`).
2. **Login**: The iOS app sends `POST /api/v1/auth/token` with username/password. The server returns a JWT (30-day expiry) and a refresh token (90-day expiry).
3. **Storage**: JWT and refresh token stored in iOS Keychain.
4. **Request auth**: Every API request includes `Authorization: Bearer <jwt>`.
5. **Refresh**: When a request returns 401, the client automatically attempts a token refresh. If refresh fails, the user is prompted to re-enter credentials.
6. **Web app unchanged**: The web app continues to work without auth (protected at the network/ingress level as today).

### 8.2 JWT Implementation

Use `PyJWT` on the backend. The JWT payload contains:

```json
{
  "sub": "username",
  "iat": 1708700000,
  "exp": 1711292000,
  "client_id": "device-uuid"
}
```

The `client_id` enables per-device tracking for sync conflict attribution.

---

## 9. Feature Map

Mapping of current web features to iOS implementation:

| Web Feature | iOS Phase | iOS Approach |
|---|---|---|
| Dashboard stats & charts | Phase 1 | Swift Charts, computed from local SwiftData |
| Route map | Phase 1 | MapKit with `MKPolyline` great-circle arcs |
| Next flight card | Phase 1 | Local query, countdown widget |
| Flight list + filtering | Phase 1 | `@Query` with predicates, `.searchable` |
| Flight CRUD | Phase 1 | SwiftUI forms with offline queue |
| Flight detail | Phase 1 | Native detail view |
| Aircraft list + detail | Phase 2 | `@Query`, AsyncImage for photos |
| Trip list + CRUD | Phase 2 | SwiftUI forms |
| Timeline | Phase 2 | `LazyVStack` with date sections |
| Achievements | Phase 2 | Grid layout with progress indicators |
| Search (global) | Phase 1 | `.searchable` across flights + aircraft |
| Dark mode | Phase 1 | Automatic (SwiftUI native) |
| AI Insights | Phase 3 | Pull from server; display cached results |
| Audit tools | Not planned | Keep on web — admin/power-user feature |
| CSV Import | Not planned | Keep on web — file-based workflow |
| Script runner | Not planned | Keep on web — admin feature |
| Inbox / Webhooks | Phase 3 | View and approve drafts |
| Boarding pass scan | Phase 3 | Use device camera + server-side Gemini |
| Registration OCR | Phase 3 | Use device camera + server-side Gemini |
| Data enrichment (AirNav, etc.) | Not planned | Keep on web — triggers external API calls |
| Distance unit toggle | Phase 1 | Local setting stored in `UserDefaults` |
| Traveller/booking site filters | Phase 1 | SwiftUI picker filters |

---

## 10. Screen-by-Screen Breakdown

### 10.1 Tab Bar

```
┌───────┬────────┬──────┬──────────┬──────────┐
│  Home │Flights │ Map  │ Aircraft │ Settings │
└───────┴────────┴──────┴──────────┴──────────┘
```

### 10.2 Home (Dashboard)

- Summary stat cards row (scrollable): total flights, total miles, countries, cities, airlines, aircraft types
- Next flight card (if future flight exists): airline logo, route, countdown, aircraft photo
- Monthly flights/miles chart (Swift Charts bar chart, last 12 months)
- Top 5 airlines horizontal bar chart
- Top 5 routes
- Recent flights list (last 10)

### 10.3 Flights Tab

- Segmented control: All | Upcoming | Past
- Search bar (`.searchable`)
- Sort options: date, distance, airline
- Filter sheet: traveller, airline, booking site, date range, has follow-up
- List rows show: date, origin→destination airports, airline logo, flight number, aircraft type
- Tap → Flight detail view
- Toolbar "+" button → Create flight form
- Swipe actions: delete, toggle follow-up, toggle exclude

### 10.4 Flight Detail

- Header: route with airport codes and city names
- Map snippet showing the route arc
- Sections: Flight info, Booking info, Aircraft info, Trip info
- Edit button → Flight form
- If aircraft registration is set: tap to view Aircraft detail

### 10.5 Flight Form

- Sections matching the web form: Flight details, Route (origin/destination), Booking, Aircraft
- Airport code fields with bundled autocomplete
- Airline code field with bundled autocomplete
- Date and time pickers
- Save writes to SwiftData + queues PendingChange

### 10.6 Map Tab

- Full-screen MapKit view
- Great-circle arcs for all flight routes
- Colour scheme picker: direction / airline / aircraft type
- Tap an arc → flight detail
- Airport pins at endpoints
- Clustering for dense areas

### 10.7 Aircraft Tab

- Grid or list of aircraft by registration
- Each cell: photo thumbnail, registration, type, manufacturer
- Search bar
- Tap → Aircraft detail: full photo, owner info, type/manufacturer/ICAO, Mode S, list of flights on this aircraft

### 10.8 Settings Tab

- **Account**: Server URL, logged-in user, log out
- **Sync**: Last sync time, sync status, pending changes count, "Sync Now" button, conflict log
- **Display**: Distance units (miles/km)
- **About**: App version, data stats (flight count, last sync)

---

## 11. Networking Layer

### 11.1 APIClient

```swift
actor APIClient {
    let baseURL: URL
    let authManager: AuthManager
    let session: URLSession

    func request<T: Decodable>(
        _ endpoint: Endpoint,
        body: (any Encodable)? = nil
    ) async throws -> T

    // Automatic retry with exponential backoff (3 attempts)
    // Automatic 401 → refresh token → retry
    // Throws APIError.offline when no connectivity
}
```

### 11.2 Connectivity Handling

```swift
@Observable
final class NetworkMonitor {
    var isConnected: Bool = true
    // Uses NWPathMonitor
    // Posts notifications on status change
    // SyncScheduler listens for "became connected" → triggers sync
}
```

### 11.3 Offline Queueing

When `NetworkMonitor.isConnected == false`:
- All writes are saved to SwiftData and `PendingChange` only
- No network requests are attempted
- A banner shows "Offline — changes will sync when connected"
- When connectivity returns, `SyncScheduler` triggers a full sync cycle

---

## 12. External API Proxying

The iOS app does NOT call external aviation APIs directly. All enrichment (AirNav, Aviation Edge, ADSBDB, Gemini) stays server-side. The iOS app can:

1. **View** enrichment data that's already been fetched (FlightHistory, AirNavRadar history records sync down).
2. **Trigger** enrichment via server endpoints (e.g., `POST /api/v1/flights/<id>/airnav-lookup`) — but only when online.

This keeps API keys server-side and avoids embedding third-party credentials in the app.

---

## 13. Testing Strategy

### 13.1 Backend (Python)

- Unit tests for all `/api/v1/` endpoints using `pytest` + Flask test client
- Sync endpoint tests: push, pull, conflict detection, pagination
- Auth tests: token generation, refresh, expiry

### 13.2 iOS

- **Unit tests**: SwiftData model logic, sync engine, conflict resolver, distance calculator
- **Integration tests**: APIClient against a mock server (using `URLProtocol`)
- **UI tests**: Critical flows — login, view flights, create flight, sync
- **Sync scenario tests**:
  - Create offline → sync → verify server has record
  - Edit on server → pull → verify local updated
  - Concurrent edits → conflict resolution
  - Delete on server → pull → verify local deleted
  - Large initial sync with pagination

---

## 14. Phased Delivery

### Phase 1 — Core Offline App

**Backend work:**
- Add `sync_revision`, `deleted_at` columns to Flight, Trip, TripLeg, Aircraft
- Create `sync_state` and `api_user` tables
- Implement JWT auth endpoints
- Implement `/api/v1/sync/changes` (pull) and `/api/v1/sync/push` (push)
- Implement basic Flight CRUD REST endpoints
- Implement stats/summary endpoint

**iOS work:**
- Project setup: SwiftData container, model definitions, tab navigation
- Auth flow: login screen, Keychain storage, token refresh
- Sync engine: push/pull, change tracking, `PendingChange` queue
- Network monitor: offline detection, banner, auto-sync on reconnect
- Dashboard: stat cards, charts (Swift Charts), next flight card
- Flight list: query, search, filter, sort
- Flight detail and form (create/edit)
- Route map (MapKit with great-circle arcs)
- Settings: sync status, distance units

**Deliverable:** A fully functional offline-first flights app with two-way sync.

### Phase 2 — Extended Features

- Aircraft list and detail views
- Trip list, detail, and CRUD
- Timeline view
- Achievements view
- Global search across all entities
- Background app refresh (`BGAppRefreshTask`)
- Push notifications (APNs): device registration, server-side dispatch on data changes, notification categories (new flight, draft ready, enrichment complete)
- Widgets: next flight countdown (WidgetKit)

### Phase 3 — Advanced Features

- Inbox: view and approve draft flights
- AI Insights: view and trigger generation
- Camera-based boarding pass scan (photos sent to server Gemini endpoint)
- Camera-based registration OCR
- Share sheet integration (export flight data)
- Spotlight integration (flight search from iOS Spotlight)
- Siri Shortcuts ("How many flights have I taken this year?")

---

## 15. Decisions and Risks

### Resolved Decisions

1. **Multi-device iOS**: **Yes — multi-device supported.** iPhone and iPad can sync independently. The server tracks per-device revision state via `client_id` in the JWT. Conflict resolution handles concurrent edits from different devices.

2. **Web app auth**: **API auth only.** Only `/api/v1/` endpoints require JWT authentication. The web app continues to work without auth, protected at the network/ingress level as today. This avoids a breaking change to the existing setup.

3. **Push notifications**: **Yes — implement APNs.** The iOS app will receive push notifications when data changes on the server (new flights imported, drafts approved, enrichment completed). This requires:
   - APNs certificate/key configuration on the backend
   - Device token registration endpoint: `POST /api/v1/devices/register`
   - Server-side notification dispatch after relevant data mutations
   - Notification categories: new flight, draft ready for review, enrichment complete
   - Added to **Phase 2** delivery (after core sync is stable)

4. **Offline create IDs**: **UUIDs via `temp_id`** (as designed in Section 6.2). The server assigns real integer IDs on push and returns the `temp_id → server_id` mapping so the client can update local references.

5. **Historical sync data**: **On-demand only.** FlightHistory and FlightHistoryAirNavRadar records are NOT included in the sync payload. They are fetched from the server only when the user views a specific flight's history detail. This keeps the local database small (~5 MB) and sync cycles fast.

### Risks

| Risk | Impact | Mitigation |
|---|---|---|
| SwiftData maturity | SwiftData is relatively new; edge cases with complex relationships | Wrap SwiftData access in a repository layer; fall back to Core Data if critical bugs arise |
| Large initial sync | First sync with hundreds of flights could be slow on cellular | Paginate, show progress, allow background download |
| Schema drift | Backend model changes could break the iOS client | Version the API (`/api/v1/`), support graceful handling of unknown fields |
| Soft delete cleanup | Hard-deleting old soft-deleted records before iOS syncs could cause missed deletes | Track per-client last-sync revision on the server; warn if a client is too far behind |
| Timestamp-based conflict resolution | Clock skew between server and device | All conflict resolution uses server-side `sync_revision` (monotonic counter), not wall-clock time. `updated_at` is only a tiebreaker within same-revision conflicts |
