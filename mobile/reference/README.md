# What the app must look like

These are the web app's own pages at a phone's size (390 × 844, light and dark), taken on
2026-11-21 from Ant Air 1.1.0 with the demo log (`scripts/seed_demo_data.py`, the fictional
traveller "Sam Rivers"). **A screen in the app is judged against its picture here**
([docs/mobile.md §3](../../docs/mobile.md#3-how-it-looks)): the same header, cards, pills, type and
order of things. Where the web is wrong at phone width, the app does not copy it
([§3.2](../../docs/mobile.md#32-where-the-web-is-wrong-on-a-phone)).

Light pictures have no suffix; dark ones end `-dark`. Full-page pictures are the whole page except
Timeline and Aircraft, which are cut to their first three screens (the rest repeats).

| App screen | Its web page | Pictures |
|---|---|---|
| Every screen at a glance | — | `web-overview`, `web-overview-dark` (the top of each page below) |
| Home | `/` | `web-dashboard`, `web-dashboard-dark` (the whole page: hero, next flight, quick add, stat tiles, filters, every chart card, route map, recent flights) |
| Home, on a computer | `/` at 1440 px | `web-dashboard-desktop`, `web-dashboard-desktop-dark` (how the same cards sit side by side) |
| Flights | `/flights` | `web-flights`, `web-flights-dark` (filters, then the admin table that the app does not copy) |
| Add a flight | `/flights/new` | `web-flight-new`, `web-flight-new-dark` |
| Trips | `/trips` | `web-trips`, `web-trips-dark` |
| A trip | `/trips/19` | `web-trip`, `web-trip-dark` (Vancouver and the Rockies: tiles, then legs) |
| Timeline | `/timeline` | `web-timeline`, `web-timeline-dark` |
| Aircraft | `/aircraft` | `web-aircraft`, `web-aircraft-dark` |
| An aircraft | the registration lookup, `CS-TVA` | `web-aircraft-lookup`, `web-aircraft-lookup-dark` |
| Achievements | `/achievements` | `web-achievements`, `web-achievements-dark` |
| AI Insights | `/insights` | `web-insights`, `web-insights-dark` (before anything is generated) |
| Search | the navbar search, typed `LIS` | `web-search`, `web-search-dark` (grouped results and actions) |
| The menu | the phone navbar's menu, open | `web-menu`, `web-menu-dark` (what the tab bar replaces) |

**Not here yet**: the hosted edition's front door (sign in, sign up, onboarding) and account pages,
which do not exist on the web yet ([docs/hosted.md](../../docs/hosted.md)). Take them when they do.

Aircraft photos in these pictures come from the registration lookup provider and belong to their
photographers; they are here only as part of the page being shown.

## Taking them again

Run the web app on a fresh database seeded with `scripts/seed_demo_data.py`, open `/` once so the
aircraft lookups are cached, then capture each page with headless Chrome over the DevTools
protocol: `Emulation.setDeviceMetricsOverride` at width 390, height 844, scale 2, `mobile: false`
(with `mobile: true` Chrome widens the layout to about 590 px);
`Emulation.setEmulatedMedia` with `prefers-color-scheme` for the theme, and `localStorage.theme` set
to match before loading; then `Page.captureScreenshot` with `captureBeyondViewport` and a clip of
the page's full height. Save at 1× as JPEG, quality 82.
