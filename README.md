# Kenny U-Pull Scanner

Scrapes the [Kenny U-Pull](https://kennyupull.com) inventory (St-Augustin and Lévis branches) and produces an HTML report with three sections:

1. **LaneWatch** — Honda vehicles whose trim likely includes the Honda LaneWatch passenger-mirror camera (~$54 at the yard, $220–380 CAD on eBay).
2. **Audi Xenon Headlights** — Q5 and A4 with Premium Plus or Prestige trim (bi-xenon + AFS adaptive headlights, ~$1800 CAD at resale).
3. **My Cars** — any vehicle of the same generation as your own, for sourcing personal replacement parts.

Trim is confirmed via the [NHTSA VIN decoder](https://vpic.nhtsa.dot.gov/api/) — more reliable than Kenny's style field. Detail pages are fetched once and cached in `detail_cache.json` so re-runs don't repeat network calls.

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Usage

### Full scan + generate report

```bash
.venv/bin/python get_lanewatch.py
.venv/bin/python get_my_cars.py
.venv/bin/python get_audi_xenon.py
.venv/bin/python generate_report.py > report.html
```

### Single branch (faster for testing)

```bash
.venv/bin/python get_lanewatch.py --branch st-aug
```

### Run the cron script manually (scans + email if new)

```bash
bash run_alert.sh
```

---

## How it works

Each scanner script:
1. Fetches the Kenny inventory for its target vehicles
2. Looks up the VIN on each vehicle's detail page (cached after first fetch)
3. Decodes the VIN via NHTSA to get the actual trim level
4. Classifies the vehicle and saves results to its state file

`generate_report.py` reads all three state files and produces a single HTML report.

### Trim classification

| Script | Good trim (confirmed) | Bad trim (skipped) |
|---|---|---|
| `get_lanewatch.py` | EX, EX-L, EX-T, Touring, Elite | DX, LX, SE, Sport, … |
| `get_audi_xenon.py` | Premium Plus, Prestige | Premium |
| `get_my_cars.py` | any trim | — |

NHTSA is tried first; Kenny's style string is the fallback. When NHTSA returns a comma-separated range (ambiguous VIN batch), it is ignored and only Kenny's string is used.

---

## LaneWatch model coverage

| Model | Years | Trims with LaneWatch |
|---|---|---|
| Accord | 2013–2017 | EX, EX-L, EX-T, Touring |
| Civic | 2012–2021 | EX, EX-L, EX-T, Touring |
| CR-V | 2015–2016 | EX, EX-L, Touring (2017+ dropped it) |
| Fit | 2015–2020 | EX, EX-L |
| HR-V | 2016–2021 | EX, EX-L, Touring |
| Odyssey | 2015–2017 | EX, EX-L, Touring, Elite |
| Pilot | 2016–2022 | EX-L, Touring, Elite (plain EX excluded) |

## Audi xenon coverage

| Model | Years | Notes |
|---|---|---|
| Q5 | 2013–2017 | B8.5 facelift; Premium Plus standard xenon + AFS |
| A4 | 2013–2016 | B8 facelift; same trim logic |

## My Cars coverage

| Vehicle | Generation |
|---|---|
| Nissan Leaf | 2018–2022 (2nd gen) |
| Honda Odyssey | 2011–2017 (4th gen) |

---

## Data files

| File | Purpose |
|---|---|
| `seen_vehicles.json` | All slugs ever seen; drives ★ NEW detection |
| `detail_cache.json` | Cached trim/VIN/NHTSA per slug; avoids re-fetching daily |
| `lanewatch_state.json` | Last LaneWatch scan result |
| `my_cars_state.json` | Last My Cars scan result |
| `audi_xenon_state.json` | Last Audi scan result |

---

## Cron job (Pi2)

Runs daily at 8 AM via `run_alert.sh`. Sends an HTML email to `simoncoulombe@protonmail.com` only when at least one ★ NEW vehicle is found. Always writes `report.html`.

```cron
0 8 * * * /home/simon/kenny/run_alert.sh
```

The latest report is also served at **http://192.168.2.14:8080/report.html** via a systemd HTTP server (`kenny-report.service`).
