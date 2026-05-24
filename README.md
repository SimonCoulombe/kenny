# Kenny U-Pull Scanner

Scrapes the [Kenny U-Pull](https://kennyupull.com) inventory (St-Augustin and Lévis branches) and prints two reports each run:

1. **LaneWatch Finder** — Honda vehicles whose trim level likely includes the Honda LaneWatch passenger-mirror camera. These go for ~$54 at the yard and sell for $220–380 CAD on eBay.
2. **My Cars** — any vehicle of the same generation as your own cars, so you can source personal replacement parts.

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Usage

```bash
# Full scan, both branches, no trim verification (fast)
python lanewatch_finder.py

# Fetch each vehicle's detail page to confirm the trim (slower, more accurate)
python lanewatch_finder.py --check-trim

# Only show vehicles that weren't present on the last run (for daily alerts)
python lanewatch_finder.py --new-only --check-trim

# One branch only
python lanewatch_finder.py --branch st-aug

# Include confirmed wrong-trim vehicles in the output
python lanewatch_finder.py --show-wrong

# Replay the last full scan instantly (no network requests)
python lanewatch_finder.py --show-saved
```

---

## How trim detection works

Without `--check-trim`, all in-range vehicles are listed as **trim unknown** — you have to verify in person.

With `--check-trim`, the script fetches each vehicle's detail page and reads the "Style" field (e.g. `5DR HB CVT EX-L W/NAVI`). It tokenises the string and matches against known trim sets:

| Result | Meaning |
|--------|---------|
| ✓ CONFIRMED LANEWATCH | Token matched a known good trim (EX, EX-L, Touring, etc.) |
| ✗ CONFIRMED WRONG TRIM | Token matched a known bad trim (LX, SE, Sport, etc.) |
| ? TRIM UNKNOWN | Style field missing or unrecognised token |

---

## LaneWatch model coverage

| Model | Years | Trims with LaneWatch |
|-------|-------|----------------------|
| Accord | 2013–2017 | EX, EX-L, EX-T, Touring |
| Civic | 2012–2021 | EX, EX-L, EX-T, Touring |
| CR-V | 2015–2016 | EX, EX-L, Touring (2017+ dropped it) |
| Fit | 2015–2020 | EX, EX-L |
| HR-V | 2016–2021 | EX, EX-L, Touring |
| Odyssey | 2015–2017 | EX, EX-L, Touring, Elite |
| Pilot | 2016–2022 | EX-L, Touring, Elite (plain EX excluded) |

---

## My Cars coverage

Alerts whenever a car of the same generation arrives, regardless of trim:

| Vehicle | Generation tracked |
|---------|--------------------|
| Nissan Leaf | 2018–2022 (2nd gen) |
| Honda Odyssey | 2011–2017 (4th gen) |

A 2015–2017 Odyssey EX-L will appear in **both** sections — it's a LaneWatch candidate *and* your generation.

---

## Data files

| File | Purpose |
|------|---------|
| `seen_vehicles.json` | All slugs ever seen; drives `--new-only` deduplication |
| `lanewatch_state.json` | Last full LaneWatch scan result; drives `--show-saved` |

`seen_vehicles.json` is shared between the LaneWatch and My Cars scans, so a vehicle is only ever flagged as "new" on the first run that encounters it.

---

## Cron job (Oracle VM)

Run daily at 8 AM and log output:

```cron
0 8 * * * cd /home/simon/kenny && .venv/bin/python lanewatch_finder.py --check-trim --new-only >> lanewatch.log 2>&1
```

Add to crontab with `crontab -e`.
