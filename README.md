# Ant Air

A self-hosted personal flight log. Import your booking history, enrich it with
aircraft and flight data, and turn it into maps, charts, an aircraft registry,
achievement badges and AI-written insights.

Ant Air is a single Flask application backed by PostgreSQL, with a vanilla
JavaScript front end, an MCP server so AI assistants can read and edit your
log, and an optional native iOS companion app.

---

## Highlights

- **Dashboard** with a boarding-pass style next-flight card, headline stats,
  monthly and yearly charts, top destinations / airlines / aircraft / tail
  numbers, a great-circle route map, and filters that reshape everything
  client-side without a reload.
- **Flights** list with advanced filters, duplicate and missing-leg highlighting,
  follow-up and exclude-from-stats flags, quick edit, merge and grouping tools.
- **Aircraft registry** built automatically from the registrations you have
  flown on, with photos, type, owner and Mode S data from ADSBDB, plus a camera
  scanner that reads a registration off a photo.
- **Trips and timeline**: group legs (flight, rail, road, sea) into trips and
  browse them chronologically.
- **Achievements**: configurable badges for milestones, geography, aircraft
  diversity, red-eyes, rare types and more.
- **AI insights**: Gemini analyses the whole log and writes a personality
  profile, records, fun comparisons and predictions.
- **Audits** for duplicates, missing data, missing return legs and city pairs,
  with one-click fixes.
- **Imports** from TripIt (CSV or HAR), Google Flights and BA Flightpath, a
  webhook inbox for automation tools such as n8n, and boarding-pass OCR.
- **Search** across everything with a `/` shortcut and registration lookup.
- **MCP server** exposing every flight, trip, aircraft and statistic as tools
  for Claude Code, Claude Desktop or any MCP client.
- Light and dark themes, responsive down to phone width, zero front-end build
  step.

---

## Quick start

### Docker Compose (recommended)

```bash
git clone https://github.com/<you>/ant-air.git
cd ant-air
cp .env.example .env            # set SECRET_KEY, HOME_CITY and any API keys
docker compose up --build
```

Open <http://localhost:8000>. The `web` service runs the database migrations
before starting. To try the app with fictional data:

```bash
docker compose exec web python scripts/seed_demo_data.py
```

### Local Python

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # point DATABASE_URL at your Postgres
createdb ant_air                # or however you create databases
flask --app wsgi db upgrade
./run.sh                        # http://127.0.0.1:5000
```

The app loads `.env` itself, so the Flask CLI, Gunicorn, the MCP server and
every script in `scripts/` see the same configuration. `run.sh` activates
`.venv` if present and passes extra arguments to `flask run`
(`./run.sh --port 8000`). Seed badges with `python scripts/seed_badges.py`,
or load the full demo set with `python scripts/seed_demo_data.py`.

---

## Configuration

Everything is read from environment variables (or `.env`). See
[`.env.example`](.env.example) for the complete list.

### Required

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL URI. `postgresql://` is rewritten to `postgresql+psycopg://` automatically. |
| `SECRET_KEY` | Flask session secret. Defaults to `dev-secret`; set a real value. |

### Personalisation (optional)

| Variable | Description |
|---|---|
| `APP_NAME` | Name shown in the navbar, page titles and MCP description. Default `Ant Air`. |
| `DEFAULT_TRAVELLER` | Traveller name used when an import or webhook does not supply one. |
| `HOME_CITY` | Your home city. Used by the missing-leg audit, skipped when picking top destinations, and pre-fills the city-pair audit. |
| `HOME_COUNTRY` | Your home country, skipped when picking the top country / flag row. |
| `HOME_AIRPORTS` | Comma-separated IATA codes that count as home (e.g. `LHR,LGW,LCY`). |

### Integrations (optional)

| Variable | Description | Default |
|---|---|---|
| `FLIGHTAWARE_API_KEY` | FlightAware AeroAPI key for flight history and aircraft registration lookups | — |
| `FLIGHTAWARE_API_BASE_URL` | AeroAPI base URL | `https://aeroapi.flightaware.com/aeroapi` |
| `FLIGHT_DATA_PROVIDER` | Provider behind lookups (`app/services/flight_lookup.py`); only `flightaware` is implemented | `flightaware` |
| `GEMINI_API_KEY` | Google Gemini key for insights, codeshare detection, registration and boarding-pass OCR | — |
| `GEMINI_API_BASE_URL` | Gemini API base URL | `https://generativelanguage.googleapis.com/v1beta` |
| `GEMINI_MODEL` / `GEMINI_FALLBACK_MODEL` | Model names | `gemini-3-flash-preview` / — |
| `N8N_WEBHOOK_TOKEN` | Bearer token required by `POST /webhooks/n8n` | — |
| `GEOCODE_ON_IMPORT` | Geocode airports and cities with Nominatim during imports | `false` |
| `MISSING_LEG_WINDOW_DAYS` | Days a return leg may lag before the audit flags it | `30` |
| `JWT_SECRET_KEY` | Signing key for the REST API / iOS app tokens | `SECRET_KEY` |
| `DUPLICATE_MATCH_RULES` | JSON override for the weighted duplicate detector | see `app/config.py` |

FlightAware's free tier only returns flights from 10 days in the past to 2 days
ahead; older lookups are rejected with a clear message instead of a wasted call.

---

## Importing your data

Drop exports into `import/` (gitignored) or use the **Import** page.

| Source | Format | How |
|---|---|---|
| TripIt | CSV export | Import page, or `python scripts/import_csv.py <file>` |
| TripIt | HAR capture of the trip pages | `python scripts/import_tripit_har.py <file>` |
| Google Flights | CSV | `python scripts/import_sources.py --import-dir import/` |
| BA Flightpath | CSV | `python scripts/import_flightpath_csv.py <file>` |
| Boarding passes | Photos, read with Gemini | `python scripts/import_boarding_pass_scans.py` |
| Anything else | JSON | `POST /webhooks/n8n` (drafts land in the Inbox) |

`import/samples/` holds small, entirely fictional files in each CSV layout.
Recognised TripIt columns are listed on the Import page. Dates may be
`DD/MM/YYYY`, `MM/DD/YYYY` or `YYYY-MM-DD`.

**Duplicates.** The same flight often arrives from several sources. The
duplicates audit groups records with a weighted score; confirming a group keeps
every record but reports the group once everywhere, through its newest record.
The rule lives in `app/services/flight_groups.py`.

---

## Pages

| Route | Description |
|---|---|
| `/` | Dashboard |
| `/flights`, `/flights/new`, `/flights/<id>/edit` | Flight list and forms |
| `/aircraft` | Aircraft registry |
| `/trips`, `/trips/<id>` | Trips |
| `/timeline` | Chronological timeline |
| `/achievements` | Badges |
| `/insights` | AI insights |
| `/inbox` | Draft flights awaiting approval |
| `/import` | CSV upload |
| `/audit/duplicates`, `/audit/duplicates/exact` | Duplicate detection |
| `/audit/missing/...` | Missing airline, aircraft, registration or airport codes |
| `/audit/missing-legs` | Outbound flights from `HOME_CITY` with no return |
| `/audit/routes/pair?a=&b=` | Every flight between two cities |
| `/audit/gemini/...` | Review AI-guessed aircraft types and codeshares |
| `/admin/badges` | Badge editor |
| `/utilities/scripts` | In-app runner for the scripts in `scripts/` |

### JSON endpoints

| Route | Description |
|---|---|
| `GET /api/search?q=` | Full-text search across flights and aircraft |
| `GET /api/aircraft/<registration>` | Aircraft details with your flights and tracked history |
| `POST /api/scan-registration` | Read a registration from a photo |
| `POST /api/insights/generate` | Regenerate AI insights |
| `POST /api/refresh-today-history` | Refresh today's flights from FlightAware |
| `POST /webhooks/n8n` | Create draft flights (`Authorization: Bearer <N8N_WEBHOOK_TOKEN>`) |
| `GET /health` | Health check |
| `/api/v1/...` | Authenticated REST + sync API used by the iOS app (`scripts/create_api_user.py` creates a login) |

---

## MCP server

`app/mcp_server.py` exposes the log as MCP tools so an AI assistant can query
and maintain it conversationally. It uses the same models as the web app, so
validation, normalisation and duplicate-group behaviour match.

| Group | Tools |
|---|---|
| Flights | `list_flights`, `get_flight`, `search_flights`, `create_flight`, `update_flight`, `delete_flight`, `restore_flight`, `set_follow_up`, `set_exclude_from_stats`, `bulk_create_flights`, `bulk_update_flights`, `describe_flight_fields`, `flight_field_values` |
| Trips | `list_trips`, `get_trip`, `create_trip`, `update_trip`, `delete_trip`, `restore_trip`, `create_trip_leg`, `update_trip_leg`, `delete_trip_leg` |
| Aircraft | `list_aircraft`, `get_aircraft`, `upsert_aircraft`, `delete_aircraft` |
| Badges | `list_badges`, `get_badge`, `create_badge`, `update_badge`, `delete_badge` |
| Flight history | `list_airnav_history`, `get_airnav_history`, `create_airnav_history`, `update_airnav_history`, `delete_airnav_history`, `list_flight_history`, `get_flight_history` |
| Lookups | `lookup_flight_registration` |
| Stats | `stats_summary`, `flights_by_year`, `flights_by_month`, `top_routes`, `top_airlines`, `top_aircraft`, `top_destinations`, `top_origins`, `distance_summary` |
| Sync | `get_sync_revision`, `changes_since` |

`create_flight` and `bulk_create_flights` ask the flight-data provider which
aircraft operated each new flight and fill in the registration and type;
`lookup_flight_registration` retries for an existing flight.

**Local (stdio).** `run_mcp.sh` starts the server with the project's virtualenv:

```bash
claude mcp add --scope user ant-air /absolute/path/to/ant-air/run_mcp.sh
```

**Over HTTP.** Set `MCP_TRANSPORT=streamable-http` (plus `MCP_HOST`, `MCP_PORT`,
`MCP_PATH`, `MCP_STATELESS`, `MCP_JSON_RESPONSE`) and the server listens on
`http://<host>:8001/mcp` with a `/healthz` probe. Set `MCP_AUTH_TOKEN` to require
`Authorization: Bearer <token>` on every request, and keep the endpoint on a
private network: it exposes your entire flight history.

```bash
claude mcp add --transport http --scope user ant-air http://<host>:8001/mcp \
  --header "Authorization: Bearer <token>"
```

Claude Desktop only launches stdio servers, so bridge with `mcp-remote`:

```json
{
  "mcpServers": {
    "ant-air": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://<host>:8001/mcp", "--allow-http",
               "--header", "Authorization: Bearer <token>"]
    }
  }
}
```

---

## Deployment

Ant Air is a plain Docker container. The image runs migrations on start
(`AUTO_MIGRATE=false` skips them) and serves Gunicorn as a non-root user on
port 8000; `/health` reports the running version.

```bash
docker build -t ant-air .
docker run -d -p 8000:8000 --env-file .env ant-air
```

`docker-compose.yml` is the reference setup: Postgres plus the app, and an
optional `mcp` profile that serves the MCP server on port 8001 from the same
image. Tune `GUNICORN_WORKERS` / `GUNICORN_THREADS` through the environment.

Anything specific to where *you* run it (Kubernetes manifests, registry
credentials, load-balancer addresses, a secrets operator) belongs in your own
private deploy repository that checks out a tag of this one, builds the image,
and applies your manifests. This repository deliberately holds no deploy
secrets, self-hosted runners or infrastructure details.

### Continuous integration and releases

`.github/workflows/ci.yml` runs on GitHub-hosted runners for every push and
pull request: byte-compiles the Python, syntax-checks `app.js`, runs the
smoke tests in `tests/` against the demo data, and builds the Docker image
without pushing it. Run the tests locally with:

```bash
pip install -r requirements-dev.txt
pytest -q
```

Releases are git tags (`v1.0.0`, `v1.1.0`, ...). Bump `VERSION` to match and
tag; the version is what `/health` and the page footer report.

---

## Project layout

```
ant-air/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── config.py            # Environment-driven configuration
│   ├── models.py            # SQLAlchemy models
│   ├── routes.py            # Web routes
│   ├── api_v1.py            # REST + sync API (JWT)
│   ├── mcp_server.py        # MCP server
│   ├── services/            # Analytics, imports, ADSBDB, FlightAware, Gemini, personalisation
│   ├── templates/           # Jinja2 templates
│   └── static/              # styles.css, app.js, airport + airline data
├── migrations/              # Alembic migrations
├── scripts/                 # Import, backfill, cleanup and seed scripts
├── import/samples/          # Fictional example CSVs
├── ios/                     # SwiftUI companion app (AntAir.xcodeproj)
├── Dockerfile               # Production image (migrations + Gunicorn)
├── docker-compose.yml       # Postgres + app, optional MCP profile
└── .env.example             # Every configuration variable
```

### Scripts

| Script | Purpose |
|---|---|
| `seed_demo_data.py` | Fictional demo flights, trips and badges (`--reset` to replace) |
| `seed_badges.py`, `seed_rare_aircraft_badges.py` | Standard and rare-aircraft badges |
| `import_csv.py`, `import_flightpath_csv.py`, `import_sources.py`, `import_tripit_har.py`, `import_boarding_pass_scans.py` | Imports |
| `backfill_flight_history.py` | Fetch FlightAware history for recent flights |
| `backfill_flight_aircraft_from_history.py`, `backfill_flight_aircraft_from_airnav_history.py` | Copy aircraft data from stored history onto flights |
| `backfill_flight_stats.py`, `backfill_geo_data.py` | Distances, coordinates, geocoding |
| `backfill_trips.py`, `backfill_group_primaries.py`, `ungroup_singleton_flights.py`, `validate_duplicate_groups.py` | Trip and duplicate-group maintenance |
| `backfill_gemini_codeshare.py`, `cleanup_airnav_gemini_*.py`, `cleanup_gemini_guess_registrations.py` | Gemini enrichment and cleanup |
| `normalize_flight_numbers.py`, `normalize_aircraft_type_names.py`, `sync_airnavradar_history_aircraft_type.py` | Normalisation |
| `create_api_user.py` | Create a login for the REST API / iOS app |
| `init_sync_state.py` | Initialise sync revisions |

All scripts are also available from the in-app **Utilities** page.

---

## iOS app

`ios/AntAir` is a SwiftUI app that syncs with the REST API for offline access
to flights, trips, aircraft and badges. Create a user with
`scripts/create_api_user.py`, then enter the server URL and credentials in the
app's settings. See [`PLAN-iOS.md`](PLAN-iOS.md) for the design.

---

## Security notes

- The web UI has **no authentication**. Run it behind your own login (a VPN,
  an authenticating reverse proxy, Tailscale, etc.). Only the REST API and the
  webhook are token-protected.
- Never commit `.env` or anything under `import/`; both are
  gitignored.
- The MCP endpoint can read and write your whole log. Keep it private or set
  `MCP_AUTH_TOKEN`.

## License

[MIT](LICENSE).
