# Ant Air, hosted and self-hosted

Status: proposal, November 2026. Nothing here is built yet.

One codebase, two editions:

- **Self-hosted** (the default) is Ant Air as it runs today: one person's flight log, one database, deployed by whoever runs it (Docker Compose, a cluster, a VPS), optionally behind Cloudflare Access. Every integration its owner configures is available. Nothing on this page changes it except where [5](#5-self-hosted-changes) says so.
- **Hosted** (`EDITION=hosted`) is Ant Air for the public at a hosted domain (to be chosen): many accounts, each in its own Postgres schema, signed in with passkeys, on Fly.io with Neon Postgres, behind Cloudflare's proxy. Anything that is one owner's own set-up is switched off.

`EDITION=hosted` is the whole switch. Unset, or any other value, means self-hosted.

The phone app ([mobile.md](mobile.md)) signs in to the hosted edition by default and to a self-hosted server through "Use your own server".

Contents: [1 What differs](#1-what-differs) · [2 The shape](#2-the-shape) · [3 An account is a schema](#3-an-account-is-a-schema) · [4 Who is asking](#4-who-is-asking) · [5 Self-hosted changes](#5-self-hosted-changes) · [6 The phone app's way in](#6-the-phone-apps-way-in) · [7 Plans and billing](#7-plans-and-billing) · [8 Deploying](#8-deploying) · [9 Delivery](#9-delivery) · [10 Decisions for the owner](#10-decisions-for-the-owner)

---

## 1 What differs

Three kinds of difference, each in one place, each pinned by a test (`tests/test_edition.py`).

### 1.1 Configuration (`app/config.py`)

`hosted_only()` blanks, on the hosted edition, every setting that is one owner's arrangement, whatever the environment holds, so no code path can reach it through a leftover variable. `self_hosted_only()` does the reverse.

**Blanked on hosted** (one owner's set-up):

| Setting | Why |
|---|---|
| `CF_ACCESS_TEAM_DOMAIN`, `CF_ACCESS_AUD`, `ACCESS_SERVICE_TOKENS` | Access is the self-hosted door. On hosted, a person is whoever holds the passkey. |
| `APP_NAME`, `DEFAULT_TRAVELLER`, `HOME_CITY`, `HOME_COUNTRY`, `HOME_AIRPORTS` | On hosted these are each account's own settings, stored in its schema and set during onboarding ([3](#3-an-account-is-a-schema)). The hosted product is always called Ant Air. |
| `N8N_WEBHOOK_TOKEN` | One owner's automation feeding one inbox. |
| `GEOCODE_ON_IMPORT` | Nominatim's usage policy does not allow a public service's bulk geocoding. The bundled airports data supplies coordinates. |
| `JWT_SECRET_KEY` and the `ApiUser` password login | The legacy SwiftUI app's door. Hosted has passkeys and app sessions ([4](#4-who-is-asking)). |

**Blanked on self-hosted** (the hosted edition's alone):

| Setting | What |
|---|---|
| `PUBLIC_ORIGIN` | The hosted origin, the passkey relying-party ID and the OAuth issuer |
| `SIGNUP_MODE`, `SIGNUP_CODES`, `TRIAL_DAYS` | Who may sign up, and the phone app's "try it first" ([6](#6-the-phone-apps-way-in)) |
| `APP_APPLE_TEAM_ID`, `APP_IOS_BUNDLE_ID`, `APP_ANDROID_PACKAGE`, `APP_ANDROID_CERT_SHA256` | Which phone app the association files vouch for |
| `RESEND_API_KEY`, `RESEND_FROM`, `RESEND_REPLY_TO` | Email: confirming an address, recovery, notices to every account |
| `OPERATOR_EMAIL` | Where failures are reported |
| `BILLING_MODE`, `STRIPE_*`, `APPLE_IAP_*` | Plans ([7](#7-plans-and-billing)). Self-hosted is always `off`: every entitlement is yes. |

**Kept on both, with a per-account cap on hosted** (an operator can offer them to everyone from one key):

| Setting | Hosted cap |
|---|---|
| `FLIGHTAWARE_API_KEY` | `LOOKUP_ACCOUNT_DAILY_CAP`: AeroAPI is billed per query, so registration lookups and flight-history refreshes are counted per account, in the account's own `usage_ledger` |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | `AI_ACCOUNT_DAILY_TOKEN_CAP`: boarding-pass and registration scans, insights and codeshare checks |
| `MAP_TILES_URL`, `MAP_TILES_KEY` (new) | The web map. OpenStreetMap's own tile servers do not permit a public service's traffic, so hosted needs a tile provider; self-hosted keeps OSM tiles as the default. |

ADSBDB needs no key and stays on both. Hosted caches its answers across accounts (registrations are public data), which also spares ADSBDB.

### 1.2 Pages, API routes, MCP tools and jobs (`app/edition.py`, one pure file)

| List | Contents | On the other edition |
|---|---|---|
| `SELF_HOSTED_ONLY_PATHS` | `/utilities/scripts*` (runs server-side scripts), `/webhooks/n8n`, `/admin/badges*` (on hosted the badge catalogue is the operator's), `/api/v1/auth/token` and `/api/v1/auth/refresh` (legacy password login) | 404 (an API path answers the JSON error envelope) |
| `HOSTED_ONLY_PATHS` | `/signin`, `/signup`, `/recover`, `/verify`, `/onboarding`, `/signout`, `/settings/account`, `/settings/plan`, `/auth/app/*`, `/oauth/*`, `/.well-known/oauth-*`, `/.well-known/apple-app-site-association`, `/.well-known/assetlinks.json`, `/webhooks/stripe`, `/webhooks/apple` | 404 |
| `SELF_HOSTED_TOOLS` | `create_badge`, `update_badge`, `delete_badge` | Withheld from the hosted MCP tool list (withheld, not refused) |
| `SELF_HOSTED_JOBS` | None today. Anything that later needs one owner's credentials goes here. | Never started |

A form action on a page both editions share but that only self-hosted supports calls `self_hosted_only()` and answers 404 on hosted. Hiding the button is not enough; the route behind it is closed too.

### 1.3 Words

Nothing a hosted account reads may name the people who run a self-hosted Ant Air, a home network, a cluster, a runbook section or an environment variable. A test scans the templates and API messages for a deny-list. The public repository already follows this rule.

## 2 The shape

```
                      ┌──────────── one Neon database ─────────────┐
 browser ──passkey──▶ │ platform.*  accounts, users, passkeys,     │
 session cookie ────▶ │             sessions, oauth_*, plans,      │
 app session ───────▶ │             aircraft_cache                 │
 API key aa_….a12 ──▶ │ a_1.*       every Ant Air table            │
 OAuth (MCP) ───────▶ │ a_2.*       every Ant Air table            │
                      │ a_3.*       …                              │
                      └────────────────────────────────────────────┘
```

- `app/platform/` holds everything hosted adds: `models.py` (the `platform` tables), `tenant.py` (an account's database handle), `accounts.py`, `sessions.py`, `passkeys.py` (WebAuthn via `webauthn`), `oauth/`, `email.py`, `billing.py`, `hook.py` (the request hook).
- **No service changes.** A route or service reads `db.session` as today. On hosted the session is already pinned to the account's schema, so it cannot tell the difference.

## 3 An account is a schema

Each account's flight log lives in its own Postgres schema, `a_<id>`, holding exactly the tables self-hosted has in `public`: flights, trips, legs, aircraft, badges, flight history, insights cache, sync state, API keys, settings.

**Why a schema** and not an `account_id` column: every query, unique index and singleton row (`SyncState`, settings) assumes one log. A column would mean changing all of them, migrating every self-hosted database, and one missed filter would show someone else's flights. With a schema, the boundary is Postgres's. Ant Air has about a dozen tables, so the catalogue stays small even with many thousands of accounts.

**The handle** (`tenant.py`). The request hook resolves the account, then pins the request's connection with `SET search_path TO "a_12"`, the schema **alone** and never `public` after it, so a missing table is an error rather than another account's row. Before anyone is signed in, the connection is pinned to `a_0`, which never exists, so a route that forgets to check reads nothing. The hook resets the path when the connection returns to the pool.

**A direct connection, never a transaction pooler.** `search_path` is session state; Neon's `-pooler` host or PgBouncer would hand it to the next client. Boot refuses a pooler host.

**Migrations.** The same Alembic revisions run once per schema, under an advisory lock named for the schema, with each schema's own `alembic_version` table. A test keeps a new schema's columns equal to `public`'s and fails a migration that names a schema explicitly. The `platform` tables have their own Alembic branch.

**Per-account settings.** `APP_NAME`, `DEFAULT_TRAVELLER` and the `HOME_*` values move into a `settings` table read through `app/services/personalisation.py`, which today reads the environment. Self-hosted keeps the environment as the default, so nothing changes for an existing install.

**Badges.** Each new schema is seeded with the standard catalogue (`seed_badges.py`, `seed_rare_aircraft_badges.py`), and deploys add new standard badges to every schema. Editing the catalogue is self-hosted only.

## 4 Who is asking

A request reaches an account in one of these ways, each naming the account before anything in it is read.

| Credential | Hosted | Self-hosted |
|---|---|---|
| **Session cookie** (`aa_session`, HttpOnly, SameSite=Lax) | After a passkey sign-in. 30 days, slid by use, at most 90 from sign-in. | Not used: Cloudflare Access is the door. With Access off, the web app is open, as today (LAN-only installs). |
| **App session** (`aa_app_…` as `Authorization: Bearer`) | After a passkey sign-in in the phone app ([6](#6-the-phone-apps-way-in)). Opens `/api/v1` and its own sign-out only. | Not used |
| **API key** | `aa_<40>.a12`: the tag names the schema, and the key is checked against the hash in that schema's `api_keys`. Issued on Settings → API keys. | `aa_<40>`, issued on the same page. The credential for scripts, the MCP server and the phone app's "own server" mode. |
| **Cloudflare Access JWT** (`Cf-Access-Jwt-Assertion`) | Blanked | Verified on every request when `CF_ACCESS_*` is set (extends today's MCP-only check in `app/mcp_access.py` to the web app and `/api/v1`) |
| **Access service token** | Blanked | The phone reaches `/api/v1` through Access with a service token on a Service Auth policy, plus an API key ([mobile.md 6.2](mobile.md#62-your-own-server)) |
| **OAuth access token** (`aa_at_…`) on `/mcp` | Ant Air's own authorization server, so a claude.ai or ChatGPT connector can be added by signing in | Cloudflare Access's Managed OAuth, as today |

A refused `/api/v1` request gets a JSON 401. A refused `/mcp` request gets OAuth's challenge (`WWW-Authenticate` with `resource_metadata`), so a connector given only the address finds the sign-in.

## 5 Self-hosted changes

What self-hosted gains so the phone app and the shared code work the same on both editions:

1. **API keys** (Settings → API keys): issue, name, list by prefix, revoke. They replace the `ApiUser` username and password, which is kept until the SwiftUI app is retired and then removed.
2. **Access JWT on every request** when `CF_ACCESS_*` is set, not only on `/mcp`.
3. **`GET /api/v1/me`**: who the credential is (`{kind: "member" | "key", name, edition}`). The app calls it to check an "own server" sign-in before keeping anything.
4. **`GET /api/v1/config`**: edition, features (`lookups`, `ai`, `map_tiles`), the account's personal settings, the airline-logo URL template, plan entitlements, minimum app version.
5. **`/api/v1/openapi.yaml`**: the API described once, so the phone app's client is generated from it ([mobile.md 4](mobile.md#4-stack)).
6. **One error envelope**: `{"error": {"code", "message", "details"}}` everywhere under `/api/v1`. The app shows the server's message as written.

## 6 The phone app's way in

Hosted only. On self-hosted every path here is a 404.

- **Association files**, served before authentication, 200 and `application/json`, never a redirect: `/.well-known/apple-app-site-association` (`webcredentials` for passkeys; `applinks` for any links the app should open) and `/.well-known/assetlinks.json` (`get_login_creds` and `handle_all_urls`). With no app configured both are 404. A malformed team ID or fingerprint stops the boot.
- **Ceremonies** under `/auth/app/*`: the site's own sign-up and sign-in ceremonies, with the challenge handle in the body instead of a cookie. A finished ceremony returns an **app session** token once, in the response body. Only an app may call them: a request carrying `Origin` or `Sec-Fetch-*` gets 403.
- **App sessions** are rows in `platform.sessions` with `kind = app` and a device model for display. Settings → Account lists every session and can end any of them.
- **Trying it first**: `POST /auth/app/trial` creates a real account with no passkey, pre-filled with the demo log (`seed_demo_data.py`), valid for `TRIAL_DAYS`. Creating a passkey keeps it; *Start my own log* clears the demo flights. Rate-limited like sign-up.

## 7 Plans and billing

`BILLING_MODE` is `off` (default), `monitor` or `enforce`. Self-hosted is always `off`.

A plan switches only what costs the operator money per account:

| Feature | With it | Without it |
|---|---|---|
| `lookups` | Aircraft registration and flight-history lookups (FlightAware) | Registration typed by hand; history not fetched. Everything else works. |
| `ai` | Boarding-pass and registration scans, AI insights, codeshare checks (Gemini) | Those buttons explain they need a plan; manual entry and imports work |

Logging flights, imports, every page, stats, achievements, the map, the MCP server, export and account deletion belong to every plan. On the web, plans are sold through **Stripe**. On iPhone they are sold through **In-App Purchase** (Apple's rules for in-app subscriptions), with the same entitlements. The Android app sells nothing until Play Billing is built.

## 8 Deploying

**Hosted:** a Fly.io app in the same region as a Neon project (direct connection string), behind Cloudflare's proxy, with `EDITION=hosted`. Secrets via `fly secrets`. Deploys run `migrate` for the platform branch, then each account schema. A second machine, and electing one machine to run scheduled jobs, come later.

**Self-hosted:** unchanged: the Docker image, `docker-compose.yml`, or a cluster. Put Cloudflare Access in front to use the phone app away from home.

## 9 Delivery

| Step | What | Depends on |
|---|---|---|
| H1 | `app/edition.py`, `hosted_only` / `self_hosted_only` in config, the tests | — |
| H2 | Self-hosted changes ([5](#5-self-hosted-changes)): API keys, `/me`, `/config`, OpenAPI document, error envelope, Access on every request | H1 |
| H3 | Tenancy: `platform` tables, schema per account, the request hook, per-schema migrations, per-account settings | H1 |
| H4 | Passkeys, sessions, sign-up and onboarding (home airports, traveller name, units), recovery, email | H3 |
| H5 | Phone app's way in ([6](#6-the-phone-apps-way-in)), trial accounts | H4 |
| H6 | OAuth for MCP | H4 |
| H7 | Caps and usage ledgers, then plans and Stripe, then In-App Purchase | H4 |
| H8 | Fly.io, Neon and Cloudflare set-up, monitoring, privacy policy and terms | H3 |

The phone app needs only H2 to work against a self-hosted server, and H5 to sign in to hosted ([mobile.md 10](mobile.md#10-phased-delivery)).

## 10 Decisions for the owner

1. **The hosted domain and the store identity.** The bundle ID and Android package can never change once the app is in a store. `ai.antcodelabs.antair` is what `ios/` uses today; reuse it only if that ID is not already tied to another listing.
2. **Free and paid plans**: what the free plan includes and the prices. Suggested: free includes manual logging, imports and everything computed; paid adds lookups and AI.
3. **Sign-up at launch**: open, by invitation code, or waitlist (`SIGNUP_MODE`).
4. **Shared logs**: whether one log can have two members (a couple's or family's travel). The schema design allows it; v1 could be one person per log.
5. **Map tile provider** for the hosted web map.
