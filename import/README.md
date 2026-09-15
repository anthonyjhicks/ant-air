# Import files

Drop the CSV or HAR exports you want to import into this directory. Everything
here except `samples/` is ignored by git, so your personal flight data never
ends up in a commit.

`samples/` contains small, entirely fictional files that show the three CSV
layouts the app understands:

| File | Source format | Import with |
|---|---|---|
| `samples/tripit-sample.csv` | TripIt CSV export | Import page, or `scripts/import_csv.py` |
| `samples/gflights-sample.csv` | Google Flights CSV | `scripts/import_sources.py` |
| `samples/baflightpath-sample.csv` | BA Flightpath CSV | `scripts/import_flightpath_csv.py` |

To load a full demo data set (flights, trips and badges) into an empty
database, run `python scripts/seed_demo_data.py` instead.
