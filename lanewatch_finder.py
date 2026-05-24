#!/usr/bin/env python3
"""
Kenny U-Pull Scanner
Two jobs in one script:

1. LaneWatch Finder — Honda vehicles whose trim likely has the LaneWatch
   passenger-mirror camera (EX / EX-L / Touring on specific year ranges).
   These sell for ~$220-380 CAD on eBay vs ~$54 at the yard.

2. My Cars — alerts when a car of the same generation as your own vehicles
   arrives at the yard (useful for sourcing personal replacement parts).

Usage:
    python lanewatch_finder.py                   # scan both branches, all results
    python lanewatch_finder.py --check-trim      # fetch each page to confirm trim
    python lanewatch_finder.py --new-only        # only vehicles not seen before
    python lanewatch_finder.py --branch st-aug   # one branch only
    python lanewatch_finder.py --show-wrong      # also list confirmed wrong trims
    python lanewatch_finder.py --show-saved      # replay last full scan (no network)
"""

import argparse
import json
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Branches
# ---------------------------------------------------------------------------

BRANCHES: dict[str, str] = {
    "st-aug": "1457197",
    "levis":  "1457186",
}

BASE_URL      = "https://kennyupull.com"
INVENTORY_URL = f"{BASE_URL}/auto-parts/our-inventory/"
SEEN_FILE     = Path(__file__).parent / "seen_vehicles.json"
STATE_FILE    = Path(__file__).parent / "lanewatch_state.json"

# ---------------------------------------------------------------------------
# LaneWatch targets
# good_trims: trim tokens that carry LaneWatch on THIS specific model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Target:
    model: str
    year_min: int
    year_max: int
    good_trims: frozenset[str]


TARGETS: list[Target] = [
    Target("accord",  2013, 2017, frozenset({"EX", "EX-L", "EX-T", "TOURING"})),
    Target("civic",   2012, 2021, frozenset({"EX", "EX-L", "EX-T", "TOURING"})),
    # CR-V 2017+ dropped LaneWatch
    Target("cr-v",    2015, 2016, frozenset({"EX", "EX-L", "TOURING"})),
    Target("fit",     2015, 2020, frozenset({"EX", "EX-L"})),
    Target("hr-v",    2016, 2021, frozenset({"EX", "EX-L", "TOURING"})),
    # Odyssey only had LaneWatch 2015-2017 (not the earlier 4th-gen years)
    Target("odyssey", 2015, 2017, frozenset({"EX", "EX-L", "TOURING", "ELITE"})),
    # Pilot plain EX does NOT have LaneWatch
    Target("pilot",   2016, 2022, frozenset({"EX-L", "TOURING", "ELITE"})),
]

NON_LANEWATCH_TRIMS: frozenset[str] = frozenset({
    "DX", "LX", "LX-P", "SE", "SPORT", "VP", "CX", "HF", "BASE", "CARGO",
})

# ---------------------------------------------------------------------------
# Personal-vehicle targets (any trim — just want to know when one arrives)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PersonalTarget:
    make: str
    model: str
    year_min: int
    year_max: int
    label: str


PERSONAL_TARGETS: list[PersonalTarget] = [
    # 2nd-gen Leaf (user owns 2020)
    PersonalTarget("nissan", "leaf",    2018, 2022, "Nissan Leaf  2nd gen (2018–2022)"),
    # 4th-gen Odyssey (user owns 2015); LaneWatch years are a subset already in TARGETS
    PersonalTarget("honda",  "odyssey", 2011, 2017, "Honda Odyssey 4th gen (2011–2017)"),
]

# ---------------------------------------------------------------------------
# Trim classification
# ---------------------------------------------------------------------------

def classify_trim(trim_raw: str, target: Target) -> str:
    """
    "lanewatch"    — confirmed trim has LaneWatch
    "no_lanewatch" — confirmed trim does not
    "unknown"      — style field empty or unrecognised token
    """
    if not trim_raw:
        return "unknown"
    tokens = set(trim_raw.upper().split())
    if tokens & target.good_trims:
        return "lanewatch"
    if tokens & NON_LANEWATCH_TRIMS:
        return "no_lanewatch"
    return "unknown"

# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------

def get_session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"]      = "Mozilla/5.0 (personal research script)"
    s.headers["Accept-Language"] = "en-CA,en;q=0.9"
    return s


def _inventory_url(page: int) -> str:
    return INVENTORY_URL if page <= 1 else f"{INVENTORY_URL}page/{page}/"


def fetch_inventory(
    session:  requests.Session,
    branch_id: str,
    model:    str,
    year_min: int,
    year_max: int,
    brand:    str = "honda",
) -> list[dict]:
    """Return all vehicles matching make/model/year-range from all pages."""
    params = {
        "brand":             brand,
        "model":             model,
        "nb_items_per_page": 50,
        "branch[]":          branch_id,
    }
    vehicles: list[dict] = []
    page = 1

    while True:
        resp = session.get(_inventory_url(page), params=params, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("div.single-product")

        if not cards:
            break

        for card in cards:
            link = card.select_one("div.col--car-specs a[href]")
            if not link:
                continue
            href = link["href"]
            url  = href if href.startswith("http") else BASE_URL + href
            slug = href.split("/part/")[-1].strip("/")

            year_tag = card.select_one("span.year")
            row_tag  = card.select_one("p.row-no")
            date_tag = card.select_one("p.date")

            year_str = year_tag.get_text(strip=True) if year_tag else "0"
            year = int(year_str) if year_str.isdigit() else 0

            if year_min <= year <= year_max:
                vehicles.append({
                    "url":        url,
                    "slug":       slug,
                    "year":       year,
                    "make":       brand,
                    "model":      model,
                    "row":        row_tag.get_text(strip=True) if row_tag else "?",
                    "date_added": date_tag.get_text(strip=True) if date_tag else "?",
                    "trim_raw":   "",
                })

        if not soup.select_one("a.next.page-numbers") or page >= 10:
            break
        page += 1
        time.sleep(0.4)

    return vehicles


def fetch_trim(session: requests.Session, url: str) -> str:
    """Return the raw style string from a vehicle detail page, or ''."""
    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for subtitle in soup.select("p.subtitle"):
            if subtitle.get_text(strip=True).lower() == "style":
                nxt = subtitle.find_next_sibling("p")
                if nxt:
                    return nxt.get_text(strip=True).upper()
    except Exception:
        pass
    return ""

# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def load_seen() -> set[str]:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def save_seen(seen: set[str]) -> None:
    SEEN_FILE.write_text(json.dumps(sorted(seen), indent=2))


def save_state(confirmed: list[dict], unknown: list[dict], wrong: list[dict]) -> None:
    """Persist the last full LaneWatch scan so --show-saved can replay it."""
    def strip(vehicles: list[dict]) -> list[dict]:
        keep = ("url", "slug", "year", "make", "model", "row", "date_added", "branch_name", "trim_raw")
        return [{k: v[k] for k in keep if k in v} for v in vehicles]

    STATE_FILE.write_text(json.dumps({
        "date":      str(date.today()),
        "confirmed": strip(confirmed),
        "unknown":   strip(unknown),
        "wrong":     strip(wrong),
    }, indent=2))


def load_state() -> tuple[list[dict], list[dict], list[dict], str]:
    """Load the last saved LaneWatch state. Returns (confirmed, unknown, wrong, date_str)."""
    if not STATE_FILE.exists():
        return [], [], [], ""
    data = json.loads(STATE_FILE.read_text())
    for group in ("confirmed", "unknown", "wrong"):
        for v in data.get(group, []):
            v["is_new"] = False
    return data.get("confirmed", []), data.get("unknown", []), data.get("wrong", []), data.get("date", "?")

# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def fmt_vehicle(v: dict, show_trim: bool) -> str:
    star  = "★ NEW  " if v["is_new"] else "       "
    trim  = f"  [{v['trim_raw']}]" if show_trim and v["trim_raw"] else ""
    make  = v.get("make", "honda").title()
    model = v["model"].title()
    return (
        f"  {star}{v['year']} {make} {model}{trim}\n"
        f"         Row {v['row']} | {v['date_added']} | {v['branch_name']}\n"
        f"         {v['url']}"
    )


def print_lanewatch_report(
    confirmed:  list[dict],
    unknown:    list[dict],
    wrong:      list[dict],
    show_wrong: bool,
    check_trim: bool,
) -> None:
    def by_new_then_date(v: dict):
        return (not v["is_new"], v["date_added"])

    print(f"\n{'═' * 68}")
    print(f"  KENNY U-PULL — LANEWATCH FINDER — {date.today()}")
    if not check_trim:
        print("  Tip: add --check-trim to verify trims automatically (slower)")
    print(f"{'═' * 68}\n")

    if confirmed:
        print(f"✓  CONFIRMED LANEWATCH  ({len(confirmed)} vehicle{'s' if len(confirmed)!=1 else ''})")
        print()
        for v in sorted(confirmed, key=by_new_then_date):
            print(fmt_vehicle(v, show_trim=True))
            print()

    if unknown:
        print(f"?  TRIM UNKNOWN — check in person  ({len(unknown)} vehicle{'s' if len(unknown)!=1 else ''})")
        print()
        for v in sorted(unknown, key=by_new_then_date):
            print(fmt_vehicle(v, show_trim=False))
            print()

    if show_wrong and wrong:
        print(f"✗  CONFIRMED WRONG TRIM  ({len(wrong)} vehicle{'s' if len(wrong)!=1 else ''})")
        print()
        for v in sorted(wrong, key=by_new_then_date):
            print(fmt_vehicle(v, show_trim=True))
            print()
    elif wrong:
        print(f"   ({len(wrong)} confirmed wrong-trim — use --show-wrong to list them)")

    if not confirmed and not unknown and not (show_wrong and wrong):
        print("   No LaneWatch candidates found.")
        print("   Use --show-saved to see the last full scan, or drop --new-only.")

    total = len(confirmed) + len(unknown) + len(wrong)
    print(f"\n{'═' * 68}")
    print(f"   {total} vehicle{'s' if total!=1 else ''} shown  |  --show-saved to replay last full scan")
    print(f"{'═' * 68}\n")


def print_personal_report(results: dict[str, list[dict]]) -> None:
    def by_new_then_date(v: dict):
        return (not v["is_new"], v["date_added"])

    print(f"\n{'═' * 68}")
    print(f"  MY CARS — PARTS AVAILABILITY")
    print(f"{'═' * 68}\n")

    for label, vehicles in results.items():
        count = len(vehicles)
        print(f"  {label}  —  {count} at yard{'s' if count != 1 else ''}\n")
        if vehicles:
            for v in sorted(vehicles, key=by_new_then_date):
                print(fmt_vehicle(v, show_trim=False))
                print()
        else:
            print("    (none found)\n")

    print(f"{'═' * 68}\n")

# ---------------------------------------------------------------------------
# Scans  (both return the set of slugs encountered, for shared seen tracking)
# ---------------------------------------------------------------------------

def scan_lanewatch(
    branches:   dict[str, str],
    check_trim: bool,
    new_only:   bool,
    show_wrong: bool,
    seen:       set[str],
) -> set[str]:
    session = get_session()
    all_seen_slugs: set[str] = set()

    confirmed: list[dict] = []
    unknown:   list[dict] = []
    wrong:     list[dict] = []

    for branch_name, branch_id in branches.items():
        for target in TARGETS:
            print(f"  {branch_name} / {target.model} ({target.year_min}–{target.year_max}) ...",
                  end=" ", flush=True)
            try:
                vehicles = fetch_inventory(
                    session, branch_id, target.model, target.year_min, target.year_max
                )
                time.sleep(0.4)
            except Exception as e:
                print(f"ERROR: {e}")
                continue

            print(f"{len(vehicles)} found")

            for v in vehicles:
                is_new = v["slug"] not in seen
                v["is_new"]      = is_new
                v["branch_name"] = branch_name
                all_seen_slugs.add(v["slug"])

                if new_only and not is_new:
                    continue

                if check_trim:
                    v["trim_raw"] = fetch_trim(session, v["url"])
                    time.sleep(0.4)

                status = classify_trim(v["trim_raw"], target)
                if status == "lanewatch":
                    confirmed.append(v)
                elif status == "no_lanewatch":
                    wrong.append(v)
                else:
                    unknown.append(v)

    if not new_only:
        save_state(confirmed, unknown, wrong)
    print_lanewatch_report(confirmed, unknown, wrong, show_wrong, check_trim)
    return all_seen_slugs


def scan_personal(
    branches: dict[str, str],
    new_only: bool,
    seen:     set[str],
) -> set[str]:
    session = get_session()
    all_seen_slugs: set[str] = set()
    results: dict[str, list[dict]] = {pt.label: [] for pt in PERSONAL_TARGETS}

    for branch_name, branch_id in branches.items():
        for pt in PERSONAL_TARGETS:
            print(f"  [my cars] {branch_name} / {pt.model} ({pt.year_min}–{pt.year_max}) ...",
                  end=" ", flush=True)
            try:
                vehicles = fetch_inventory(
                    session, branch_id, pt.model, pt.year_min, pt.year_max, brand=pt.make
                )
                time.sleep(0.4)
            except Exception as e:
                print(f"ERROR: {e}")
                continue

            print(f"{len(vehicles)} found")

            for v in vehicles:
                is_new = v["slug"] not in seen
                v["is_new"]      = is_new
                v["branch_name"] = branch_name
                all_seen_slugs.add(v["slug"])
                if new_only and not is_new:
                    continue
                results[pt.label].append(v)

    print_personal_report(results)
    return all_seen_slugs

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description="Kenny U-Pull scanner — LaneWatch + my cars")
    p.add_argument("--branch", choices=list(BRANCHES),
                   help="Scan one branch only (default: both)")
    p.add_argument("--check-trim", action="store_true",
                   help="Fetch each vehicle page to confirm trim (slower but definitive)")
    p.add_argument("--new-only", action="store_true",
                   help="Only show vehicles not seen on a previous run")
    p.add_argument("--show-wrong", action="store_true",
                   help="Also show vehicles with confirmed wrong trim")
    p.add_argument("--show-saved", action="store_true",
                   help="Print last saved LaneWatch scan without network requests")
    args = p.parse_args()

    if args.show_saved:
        confirmed, unknown, wrong, saved_date = load_state()
        if not saved_date:
            print("No saved state found. Run without --show-saved first.")
            return
        print(f"LaneWatch Finder | saved on {saved_date} | (no network requests)")
        print_lanewatch_report(confirmed, unknown, wrong, args.show_wrong, check_trim=True)
        return

    branches = {args.branch: BRANCHES[args.branch]} if args.branch else BRANCHES
    print(f"Kenny U-Pull Scanner | {date.today()} | branches: {', '.join(branches)}")
    print(f"check-trim: {args.check_trim} | new-only: {args.new_only}\n")

    seen = load_seen()

    lw_slugs = scan_lanewatch(
        branches=branches,
        check_trim=args.check_trim,
        new_only=args.new_only,
        show_wrong=args.show_wrong,
        seen=seen,
    )
    personal_slugs = scan_personal(
        branches=branches,
        new_only=args.new_only,
        seen=seen,
    )

    save_seen(seen | lw_slugs | personal_slugs)


if __name__ == "__main__":
    main()
