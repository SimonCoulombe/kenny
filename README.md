# Kenny U-Pull Scanner

Scrapes the [Kenny U-Pull](https://kennyupull.com) inventory (St-Augustin and Lévis branches) and produces an HTML report with four sections:

1. **LaneWatch** — Honda vehicles whose trim likely includes the Honda LaneWatch passenger-mirror camera (~$54 at the yard, $220–380 CAD on eBay).
2. **Audi Xenon Headlights** — all Audi models 2013+ with Premium Plus or Prestige trim (bi-xenon + AFS adaptive headlights, ~$1800 CAD at resale).
3. **VW Xenon Headlights** — 2014+ Volkswagen; CC and Golf R always flagged, Touareg Highline only.
4. **Ford F-Series Lariat** — F-150 / F-250 / F-350 in Lariat trim, 2011+.
5. **Ford Escape Titanium / Limited** — Escape in its top trim, 2008+ (Limited pre-2013, Titanium 2013+).
6. **My Cars** — any vehicle of the same generation as your own, for sourcing personal replacement parts.

Trim is confirmed via the [NHTSA VIN decoder](https://vpic.nhtsa.dot.gov/api/) — more reliable than Kenny's style field — **except for Ford F-series, where NHTSA does not VIN-encode the marketing trim and Kenny's style field is the only source** (see below). Detail pages are fetched once and cached in `detail_cache.json` so re-runs don't repeat network calls.

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
.venv/bin/python get_ford_lariat.py
.venv/bin/python get_ford_escape.py
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

`generate_report.py` reads all the scanner state files and produces a single HTML report. Only **confirmed** matches are shown — vehicles whose trim couldn't be read ("unknown") are saved to state but kept out of the report, so you never chase a maybe.

### Trim classification

| Script | Good trim (confirmed) | Bad trim (skipped) | Notes |
|---|---|---|---|
| `get_lanewatch.py` | EX, EX-L, EX-T, Touring, Elite | DX, LX, SE, Sport, … | |
| `get_audi_xenon.py` | Premium Plus, Prestige | Premium | Premium has xenon but no AFS directional |
| `get_volkswagen_xenon.py` | CC/Golf R (any trim), Touareg Highline | anything not matching | Unknowns saved to state but not shown in report |
| `get_ford_lariat.py` | Lariat (F-150/F-250/F-350) | any other trim | **Classifies on Kenny's style field, not NHTSA** — see below |
| `get_ford_escape.py` | Titanium, Limited (Escape) | XLT, XLS, SEL, SE, S | NHTSA and style agree; both are checked |
| `get_my_cars.py` | any trim | — | |

NHTSA is preferred (except Ford F-series). The full trim string is scanned — a phrase match anywhere counts, including within comma-separated ranges (e.g. `HIGHLINE` in `TRENDLINE, HIGHLINE` is a hit). Kenny's style string is used as a fallback only when NHTSA returns nothing. For VW specifically, Kenny's style field contains engine/body info rather than trim names, so the fallback rarely triggers.

---

## Xenon headlight knowledge

### Audi (all models, 2013+)

Trim hierarchy: **Premium < Premium Plus < Prestige**

- **Premium Plus / Prestige** → bi-xenon + AFS (adaptive, swivels in corners) — confirmed xenon
- **Premium** → xenon bulbs but no AFS directional system — excluded
- The AFS system is the valuable part; the headlight assemblies are worth ~$1800 CAD

### Volkswagen (2014+)

| Model | Confirmed xenon when… |
|---|---|
| CC | always (regardless of trim) |
| Golf R | always (regardless of trim) |
| Touareg | Highline trim only |

Models not in the table go straight to the wrong bucket. Unknowns (target model but NHTSA trim unreadable) are saved to state but not shown in the report.

**CA/US trim naming:** Trendline ≈ S (base), Comfortline ≈ SE (mid), Highline ≈ SEL (top). NHTSA uses either system depending on the VIN origin; the scanner checks for both names where relevant.

Kenny's style field for VW contains engine/body info (e.g. `4DR SDN 2.5L MANUAL SE`), not the marketing trim name — the NHTSA VIN decoder is the only reliable source. When NHTSA returns only a drivetrain descriptor like `4MOTION` with no trim info, the vehicle lands in "unknown".

### Ford F-Series (2011+)

| Model | Confirmed when… |
|---|---|
| F-150, F-250, F-350 | Kenny style field contains `LARIAT` |

**Ford is the opposite of VW/Audi:** the NHTSA VIN decoder does *not* carry the marketing trim (Lariat/XLT/XL/King Ranch/Platinum). For Ford trucks NHTSA's `Trim` field returns body-style descriptors like `Styleside` / `Flare Side`, or nothing — Ford simply doesn't VIN-encode the trim line. Kenny's **style field** is the only reliable source: it reads e.g. `4WD SUPERCREW 145" LARIAT`, where the last token is the actual trim. So `get_ford_lariat.py` classifies on `trim_raw` (style) and discards `trim_nhtsa`. Only F-150/F-250/F-350 are fetched in detail; other Ford models are dropped from the slug before any detail call. A target truck with an empty style string lands in "unknown" and is kept out of the report.

**Note this is truck-specific.** The Ford *Escape* — unlike the F-series — *does* have its trim in NHTSA, and NHTSA agrees with Kenny's style field (both read `TITANIUM` / `LIMITED`). So `get_ford_escape.py` checks both sources rather than relying on style alone.

### Ford Escape (2008+)

| Trim | Years | Notes |
|---|---|---|
| Limited | 2008–2012 | top trim of the pre-redesign generation |
| Titanium | 2013+ | top trim, replaced Limited |

`get_ford_escape.py` flags either trim. It scans both NHTSA and Kenny's style string (they agree for the Escape); a phrase match in either confirms. Other recognizable trims (`XLT`, `XLS`, `SEL`, `SE`, `S`) send the vehicle to the wrong bucket; an Escape with no readable trim in either source lands in "unknown".

---

## Kenny API quirks

- **Page size parameter is `nb_items`, not `nb_items_per_page`.** The site silently ignores `nb_items_per_page` and defaults to 14 results. Always send `nb_items=99` (or higher) to get all inventory in one page.
- **Fetching by make only:** passing `model=""` to `fetch_inventory` returns all models for a brand (e.g. all Volkswagen regardless of model). The VW scanner uses this since we want any model.
- **The `model` field in vehicle dicts comes from what you pass in,** not from the page — Kenny's inventory cards don't expose the model as a separate field. For the VW scanner, model is extracted from the slug (`volkswagen_passat_2013_kup-st-aug_123` → `Passat`).
- **NHTSA rate:** the decoder is free with no auth; 0.3–0.4 s sleeps between calls are enough to avoid issues.
- **NHTSA has no Ford truck trim:** for F-series VINs the `Trim`/`Series` fields return body-style words (`Styleside`) or nothing — Ford doesn't VIN-encode Lariat/XLT/XL. Use Kenny's style field instead.

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
| CC, Golf R | 2014+ | Any trim |
| Touareg | 2014+ | Highline only |

## Ford Lariat coverage

| Models | Years | Notes |
|---|---|---|
| F-150, F-250, F-350 | 2011+ | Lariat trim; matched on Kenny style field, not NHTSA |

## Ford Escape coverage

| Models | Years | Notes |
|---|---|---|
| Escape | 2008+ | Titanium or Limited; NHTSA and style both checked |

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
| `ford_lariat_state.json` | Last Ford Lariat scan result |
| `ford_escape_state.json` | Last Ford Escape scan result |

---

## Cron job (Pi2)

Runs daily at 8 AM via `run_alert.sh`. Sends an HTML email to `simoncoulombe@protonmail.com` only when at least one ★ NEW vehicle is found. Always writes `report.html`.

```cron
0 8 * * * /home/simon/kenny/run_alert.sh
```

The latest report is also served at **http://192.168.2.14:8080/report.html** via a systemd HTTP server (`kenny-report.service`).
