# Kenny U-Pull Scanner

Scrapes the [Kenny U-Pull](https://kennyupull.com) inventory (St-Augustin and Lévis branches) and produces an HTML report with four sections:

1. **LaneWatch** — Honda vehicles whose trim likely includes the Honda LaneWatch passenger-mirror camera (~$54 at the yard, $220–380 CAD on eBay).
2. **Audi Xenon Headlights** — all Audi models 2013+ with Premium Plus or Prestige trim (bi-xenon + AFS adaptive headlights, ~$1800 CAD at resale).
3. **VW Xenon Headlights** — 2013+ Volkswagen; per-model trim rules (CC/Golf R/GLI/Touareg always flagged, others require SEL/Highline/Autobahn/R-Line).
4. **My Cars** — any vehicle of the same generation as your own, for sourcing personal replacement parts.

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
.venv/bin/python get_volkswagen_xenon.py
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

`generate_report.py` reads all four state files and produces a single HTML report.

### Trim classification

| Script | Good trim (confirmed) | Bad trim (skipped) | Notes |
|---|---|---|---|
| `get_lanewatch.py` | EX, EX-L, EX-T, Touring, Elite | DX, LX, SE, Sport, … | |
| `get_audi_xenon.py` | Premium Plus, Prestige | Premium | Premium has xenon but no AFS directional |
| `get_volkswagen_xenon.py` | per-model rules (see table below) | anything not matching a model rule | MODEL_RULES dict; CC/Golf R/GLI always flag; unknown only when target model has no NHTSA trim |
| `get_my_cars.py` | any trim | — | |

NHTSA is preferred. The full trim string is scanned — a phrase match anywhere counts, including within comma-separated ranges (e.g. `HIGHLINE` in `TRENDLINE, HIGHLINE` is a hit). Kenny's style string is used as a fallback only when NHTSA returns nothing. For VW specifically, Kenny's style field contains engine/body info rather than trim names, so the fallback rarely triggers.

---

## Xenon headlight knowledge

### Audi (all models, 2013+)

Trim hierarchy: **Premium < Premium Plus < Prestige**

- **Premium Plus / Prestige** → bi-xenon + AFS (adaptive, swivels in corners) — confirmed xenon
- **Premium** → xenon bulbs but no AFS directional system — excluded
- The AFS system is the valuable part; the headlight assemblies are worth ~$1800 CAD

### Volkswagen (all models, 2013+)

Rules are per-model — a phrase that qualifies one model may not qualify another.

| Model | Confirmed xenon when… |
|---|---|
| CC | always (regardless of trim) |
| Golf R | always (regardless of trim) |
| GLI | always (regardless of trim) |
| Touareg | always (regardless of trim) |
| Golf | Autobahn, SEL, or R-Line trim |
| Jetta | SEL, Autobahn, GLI, or R-Line trim |
| Passat | Highline, SEL, or R-Line trim |
| Tiguan | Highline, SEL, or R-Line trim |

Models not in the table (Beetle, Rabbit, etc.) go straight to the wrong bucket.

**CA/US trim naming:** Trendline ≈ S (base), Comfortline ≈ SE (mid), Highline ≈ SEL (top). NHTSA uses either system depending on the VIN origin; the scanner checks for both names where relevant.

Kenny's style field for VW contains engine/body info (e.g. `4DR SDN 2.5L MANUAL SE`), not the marketing trim name — the NHTSA VIN decoder is the only reliable source. When NHTSA returns only a drivetrain descriptor like `4MOTION` with no trim info, the vehicle lands in "unknown".

---

## Kenny API quirks

- **Page size parameter is `nb_items`, not `nb_items_per_page`.** The site silently ignores `nb_items_per_page` and defaults to 14 results. Always send `nb_items=99` (or higher) to get all inventory in one page.
- **Fetching by make only:** passing `model=""` to `fetch_inventory` returns all models for a brand (e.g. all Volkswagen regardless of model). The VW scanner uses this since we want any model.
- **The `model` field in vehicle dicts comes from what you pass in,** not from the page — Kenny's inventory cards don't expose the model as a separate field. For the VW scanner, model is extracted from the slug (`volkswagen_passat_2013_kup-st-aug_123` → `Passat`).
- **NHTSA rate:** the decoder is free with no auth; 0.3–0.4 s sleeps between calls are enough to avoid issues.

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

| Models | Years | Notes |
|---|---|---|
| All models | 2013+ | Premium Plus or Prestige; model not filtered at fetch time |

## VW xenon coverage

| Models | Years | Notes |
|---|---|---|
| All models | 2013+ | Per-model rules; see xenon knowledge table above |

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
| `volkswagen_xenon_state.json` | Last VW scan result |

---

## Cron job (Pi2)

Runs daily at 8 AM via `run_alert.sh`. Sends an HTML email to `simoncoulombe@protonmail.com` only when at least one ★ NEW vehicle is found. Always writes `report.html`.

```cron
0 8 * * * /home/simon/kenny/run_alert.sh
```

The latest report is also served at **http://192.168.2.14:8080/report.html** via a systemd HTTP server (`kenny-report.service`).
