#!/usr/bin/env python3
"""
Kenny U-Pull Profit Scout
Scrapes inventory for target vehicles and flags high-margin parts.

Usage:
    python kenny_scout.py                  # scan both branches, all targets
    python kenny_scout.py --branch st-aug  # St-Augustin only
    python kenny_scout.py --branch levis   # Levis only
    python kenny_scout.py --make honda     # filter by make
    python kenny_scout.py --new-only       # skip already-seen vehicles
    python kenny_scout.py --min-profit 100 # minimum net profit threshold
"""

import argparse
import json
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Branch configuration
# To find the Levis branch ID: open kennyupull.com/auto-parts/our-inventory/
# in your browser, select Levis in the branch dropdown, click Search, then
# open DevTools → Network → look for the inventory request and copy the
# branch[] parameter value.
# ---------------------------------------------------------------------------
BRANCHES: dict[str, str] = {
    "st-aug": "1457197",
    "levis": "1457186",
}

BASE_URL = "https://kennyupull.com"
INVENTORY_URL = f"{BASE_URL}/auto-parts/our-inventory/"
SEEN_FILE = Path(__file__).parent / "seen_vehicles.json"

# ---------------------------------------------------------------------------
# Parts catalog: what to look for and why it's valuable
# kenny_price: what you pay at the yard (CAD)
# ebay_low / ebay_high: realistic sold price range on eBay.ca (CAD)
# ship_cost: estimated cost to ship this part (CAD)
# quick_pull: True = can pull in under 30 min with basic tools
# trim_required: these trims carry this part; lower trims may not have it
# ---------------------------------------------------------------------------
@dataclass
class Part:
    name: str
    kenny_price: float
    ebay_low: float
    ebay_high: float
    ship_cost: float
    quick_pull: bool = True
    notes: str = ""
    trim_keywords: list[str] = field(default_factory=list)


PARTS_CATALOG: dict[str, Part] = {
    # --- Mirrors ---
    "mirror_lanewatch": Part(
        name="Mirror - Passenger (LaneWatch camera)",
        kenny_price=53.99,
        ebay_low=220,
        ebay_high=380,
        ship_cost=30,
        notes="Honda EX/EX-L+ only. Verify camera is present before pulling. Fits in a 12x10x8 box.",
        trim_keywords=["EX-L", "EX ", "EX-T", "TOURING", "ELITE", "SPORT"],
    ),
    "mirror_electric": Part(
        name="Mirror - Passenger (electric, no camera)",
        kenny_price=53.99,
        ebay_low=70,
        ebay_high=140,
        ship_cost=25,
        notes="Worth grabbing on high-volume models. Much lower ceiling than LaneWatch version.",
    ),
    "auto_dim_mirror": Part(
        name="Mirror - Inside Rear View (auto-dim)",
        kenny_price=24.79,
        ebay_low=55,
        ebay_high=120,
        ship_cost=12,
        notes="30-second pull. Ships in padded envelope. High-trim only.",
        trim_keywords=["EX-L", "TOURING", "ELITE", "XLE", "LIMITED"],
    ),
    # --- Sliding door motors ---
    "sliding_door_motor": Part(
        name="Door Motor - Power Sliding",
        kenny_price=36.79,
        ebay_low=130,
        ebay_high=200,
        ship_cost=20,
        notes="L and R are different parts — pull both per car. Common failure on Odyssey/Sienna. Ships in a shoebox.",
    ),
    # --- Electronics (small, easy ship) ---
    "ecm": Part(
        name="Engine Control Module (ECM)",
        kenny_price=99.99,
        ebay_low=120,
        ebay_high=300,
        ship_cost=12,
        notes="Pre-2015 Hondas: year-range compatible (not VIN-locked). Check eBay sold for exact year first.",
    ),
    "tcm": Part(
        name="Transmission Control Module (TCM)",
        kenny_price=57.79,
        ebay_low=100,
        ebay_high=250,
        ship_cost=12,
        notes="Honda CVT TCMs especially in demand. Year-range compatible.",
    ),
    "bcm": Part(
        name="Body Control Module (BCM)",
        kenny_price=43.79,
        ebay_low=80,
        ebay_high=200,
        ship_cost=12,
        notes="Quick pull. Year-range plug-and-play on most Hondas.",
    ),
    "abs_module": Part(
        name="ABS Controller Module",
        kenny_price=95.79,
        ebay_low=120,
        ebay_high=280,
        ship_cost=15,
        notes="Small box. Check for corrosion on connectors.",
    ),
    "maf_sensor": Part(
        name="Mass Airflow Sensor (MAF / Air Flow Meter)",
        kenny_price=33.00,
        ebay_low=70,
        ebay_high=150,
        ship_cost=12,
        notes="2-min pull (2 clips). Honda 2.4L K24 MAF fits Accord/CR-V/Odyssey same years. Verify OEM sold price — aftermarket undercuts used OEM.",
    ),
    "honda_sensing_camera": Part(
        name="Honda Sensing Camera (forward-collision, windshield-mounted)",
        kenny_price=21.99,
        ebay_low=200,
        ebay_high=480,
        ship_cost=12,
        notes="⚠ UNVALIDATED PRICE: Kenny likely prices this as 'Rear Camera' $21.99. If true, enormous margin. 2017+ Accord/Civic/CR-V/HR-V. Pull one, list it, confirm market before scaling.",
        trim_keywords=["EX", "EX-L", "EX-T", "SPORT", "TOURING", "ELITE"],
    ),
    "rear_camera": Part(
        name="Rear Backup Camera (standalone OEM)",
        kenny_price=21.99,
        ebay_low=50,
        ebay_high=110,
        ship_cost=10,
        notes="One bolt, one connector. Ships in padded envelope. Honda OEM cameras sell well.",
    ),
    # --- Infotainment / interior ---
    "nav_radio": Part(
        name="Navigation / Infotainment Screen",
        kenny_price=59.79,
        ebay_low=150,
        ebay_high=380,
        ship_cost=20,
        notes="Model-year-specific — always check eBay sold before pulling. High-trim units command best prices.",
        trim_keywords=["EX-L", "TOURING", "ELITE", "XLE", "LIMITED"],
    ),
    "instrument_cluster": Part(
        name="Instrument Cluster",
        kenny_price=67.79,
        ebay_low=100,
        ebay_high=260,
        ship_cost=18,
        notes="4 screws, 1 connector. Check for cracked LCD or burned pixels before pulling.",
    ),
    "hvac_panel": Part(
        name="HVAC Control Panel (digital)",
        kenny_price=42.79,
        ebay_low=90,
        ebay_high=200,
        ship_cost=15,
        notes="Flat, ships in a small box. Dual-zone units (higher trims) sell better.",
        trim_keywords=["EX-L", "TOURING", "ELITE", "XLE", "LIMITED"],
    ),
    # --- Lighting ---
    "headlight_led": Part(
        name="Headlight Assembly (LED / projector)",
        kenny_price=86.79,
        ebay_low=150,
        ebay_high=350,
        ship_cost=35,
        notes="Check for cracks and moisture. Sell as a pair when possible. Bulkier to box.",
        trim_keywords=["EX-L", "TOURING", "ELITE", "SPORT"],
    ),
}

EBAY_FEE_RATE = 0.1325  # 13.25% eBay final value fee (Canada auto parts)
PACKAGING_COST = 8.0


# ---------------------------------------------------------------------------
# Target vehicles: what to look for in the yard
# ---------------------------------------------------------------------------
@dataclass
class TargetVehicle:
    make: str
    model: str
    year_min: int
    year_max: int
    target_parts: list[str]  # keys into PARTS_CATALOG
    preferred_trims: list[str] = field(default_factory=list)
    notes: str = ""


TARGETS: list[TargetVehicle] = [
    # ---- Honda Odyssey ----
    # 2015-2017: LaneWatch camera mirror on EX-L+
    TargetVehicle(
        make="honda",
        model="odyssey",
        year_min=2015,
        year_max=2017,
        target_parts=["mirror_lanewatch", "sliding_door_motor", "nav_radio", "bcm", "ecm", "auto_dim_mirror", "instrument_cluster"],
        preferred_trims=["EX-L", "TOURING", "ELITE"],
        notes="LaneWatch mirror on EX-L+. Both sliding door motors are separate SKUs — pull both.",
    ),
    # 2011-2014: no LaneWatch, door motors still high-value
    TargetVehicle(
        make="honda",
        model="odyssey",
        year_min=2011,
        year_max=2014,
        target_parts=["mirror_electric", "sliding_door_motor", "nav_radio", "bcm", "ecm"],
        preferred_trims=["EX-L", "TOURING", "ELITE"],
        notes="No LaneWatch before 2015. Door motors still great margin.",
    ),
    # 2018+: newer gen, LaneWatch continued
    TargetVehicle(
        make="honda",
        model="odyssey",
        year_min=2018,
        year_max=2023,
        target_parts=["mirror_lanewatch", "sliding_door_motor", "nav_radio", "bcm"],
        preferred_trims=["EX-L", "TOURING", "ELITE"],
    ),
    # ---- Honda Fit ----
    # LaneWatch on EX/EX-L 2015-2020
    TargetVehicle(
        make="honda",
        model="fit",
        year_min=2015,
        year_max=2020,
        target_parts=["mirror_lanewatch", "nav_radio", "bcm", "maf_sensor", "rear_camera"],
        preferred_trims=["EX", "EX-L"],
        notes="EX trim has LaneWatch. Mirror is smaller than Odyssey but still commands good prices.",
    ),
    # ---- Honda Civic ----
    # 9th gen (2012-2015): LaneWatch on EX+
    TargetVehicle(
        make="honda",
        model="civic",
        year_min=2012,
        year_max=2015,
        target_parts=["mirror_lanewatch", "instrument_cluster", "maf_sensor", "bcm", "nav_radio"],
        preferred_trims=["EX", "EX-L"],
        notes="9th gen EX has LaneWatch. Very common at junkyards — good chance of finding one.",
    ),
    # 10th gen (2016-2021): LaneWatch on EX+, Honda Sensing on 2017+
    TargetVehicle(
        make="honda",
        model="civic",
        year_min=2016,
        year_max=2021,
        target_parts=["mirror_lanewatch", "nav_radio", "honda_sensing_camera", "bcm", "instrument_cluster"],
        preferred_trims=["EX", "EX-L", "EX-T", "SPORT", "TOURING"],
        notes="2017+ also has Honda Sensing camera — investigate that price point.",
    ),
    # ---- Honda Accord ----
    # 9th gen (2013-2017): LaneWatch on EX, EX-L, and Sport
    TargetVehicle(
        make="honda",
        model="accord",
        year_min=2013,
        year_max=2017,
        target_parts=["mirror_lanewatch", "nav_radio", "instrument_cluster", "hvac_panel", "maf_sensor", "bcm", "ecm"],
        preferred_trims=["EX", "EX-L", "SPORT", "TOURING"],
        notes="Very common in junkyards. EX and Sport both have LaneWatch. High demand for nav and clusters.",
    ),
    # ---- Honda CR-V ----
    # 4th gen (2015-2016): LaneWatch on EX+
    TargetVehicle(
        make="honda",
        model="cr-v",
        year_min=2015,
        year_max=2016,
        target_parts=["mirror_lanewatch", "nav_radio", "maf_sensor", "bcm", "rear_camera"],
        preferred_trims=["EX", "EX-L"],
    ),
    # 5th gen (2017-2022): no LaneWatch but Honda Sensing from 2017+
    TargetVehicle(
        make="honda",
        model="cr-v",
        year_min=2017,
        year_max=2022,
        target_parts=["honda_sensing_camera", "nav_radio", "maf_sensor", "bcm", "ecm"],
        preferred_trims=["EX", "EX-L", "TOURING"],
        notes="No LaneWatch on 5th gen. Honda Sensing camera is the prize here — unvalidated price.",
    ),
    # ---- Honda HR-V ----
    # LaneWatch on EX/EX-L 2016-2021
    TargetVehicle(
        make="honda",
        model="hr-v",
        year_min=2016,
        year_max=2021,
        target_parts=["mirror_lanewatch", "nav_radio", "bcm", "rear_camera"],
        preferred_trims=["EX", "EX-L"],
        notes="Less common at junkyards but starting to appear. EX has LaneWatch.",
    ),
    # ---- Honda Pilot ----
    # 3rd gen (2016+): LaneWatch on EX-L+
    TargetVehicle(
        make="honda",
        model="pilot",
        year_min=2016,
        year_max=2022,
        target_parts=["mirror_lanewatch", "nav_radio", "headlight_led", "abs_module", "auto_dim_mirror"],
        preferred_trims=["EX-L", "TOURING", "ELITE", "BLACK EDITION"],
        notes="Premium pricing on all parts. LaneWatch on EX-L+.",
    ),
    # ---- Toyota Sienna ----
    # No LaneWatch (Toyota system), but sliding door motors are the main play
    TargetVehicle(
        make="toyota",
        model="sienna",
        year_min=2011,
        year_max=2020,
        target_parts=["mirror_electric", "sliding_door_motor", "nav_radio", "instrument_cluster"],
        preferred_trims=["XLE", "LIMITED", "PLATINUM"],
        notes="Sliding door motors same failure pattern as Odyssey. No LaneWatch — Toyota had BSM instead.",
    ),
    # ---- Acura MDX ----
    # No LaneWatch (Acura uses different ADAS), premium pricing on everything else
    TargetVehicle(
        make="acura",
        model="mdx",
        year_min=2014,
        year_max=2021,
        target_parts=["mirror_electric", "headlight_led", "abs_module", "ecm", "bcm", "nav_radio"],
        preferred_trims=["TECH", "ADVANCE", "ELITE"],
        notes="No LaneWatch on Acura. Everything else commands premium prices — Acura OEM parts are expensive new.",
    ),
]


# ---------------------------------------------------------------------------
# Scraping helpers
# ---------------------------------------------------------------------------

def get_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; personal research script)",
        "Accept-Language": "en-CA,en;q=0.9",
    })
    return s


def _inventory_url(page: int) -> str:
    """Build path-based paginated inventory URL (Kenny uses /page/N/ segments)."""
    if page <= 1:
        return INVENTORY_URL
    return f"{INVENTORY_URL}page/{page}/"


def _parse_cards(soup: BeautifulSoup, make: str, model: str, branch_id: str) -> list[dict]:
    """Extract vehicle records from a parsed inventory page."""
    vehicles = []
    for card in soup.select("div.single-product"):
        link = card.select_one("div.col--car-specs a[href]")
        if not link:
            continue
        href = link["href"]
        url = href if href.startswith("http") else BASE_URL + href
        slug = href.split("/part/")[-1].strip("/")

        year_tag = card.select_one("span.year")
        row_tag = card.select_one("p.row-no")
        date_tag = card.select_one("p.date")

        year_str = year_tag.get_text(strip=True) if year_tag else "0"
        year = int(year_str) if year_str.isdigit() else 0

        vehicles.append({
            "url": url,
            "slug": slug,
            "year": year,
            "make": make,
            "model": model,
            "row": row_tag.get_text(strip=True) if row_tag else "",
            "date_added": date_tag.get_text(strip=True) if date_tag else "",
            "branch_id": branch_id,
        })
    return vehicles


def fetch_inventory_page(
    session: requests.Session,
    branch_id: str,
    make: str,
    model: str,
    page: int = 1,
) -> list[dict]:
    params = {
        "brand": make,
        "model": model,
        "nb_items_per_page": 50,
        "branch[]": branch_id,
    }
    resp = session.get(_inventory_url(page), params=params, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    return _parse_cards(soup, make, model, branch_id)


def get_total_pages(session: requests.Session, branch_id: str, make: str, model: str) -> int:
    """Fetch page 1 to find total page count from pagination links."""
    params = {
        "brand": make,
        "model": model,
        "nb_items_per_page": 50,
        "branch[]": branch_id,
    }
    resp = session.get(INVENTORY_URL, params=params, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    nums = []
    for a in soup.select("a.page-numbers"):
        txt = a.get_text(strip=True)
        if txt.isdigit():
            nums.append(int(txt))
    return max(nums) if nums else 1


def get_vehicle_trim(session: requests.Session, url: str) -> str:
    """Fetch vehicle detail page and return trim string (may be empty)."""
    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # Trim is in a <p class="detail"> immediately following <p class="subtitle">Style</p>
        for subtitle in soup.select("p.subtitle"):
            if subtitle.get_text(strip=True).lower() == "style":
                nxt = subtitle.find_next_sibling("p")
                if nxt:
                    return nxt.get_text(strip=True).upper()
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Profit calculation
# ---------------------------------------------------------------------------

def net_profit(part: Part) -> tuple[float, float]:
    """Return (net_low, net_high) after eBay fees, shipping, and packaging."""
    def calc(sell_price: float) -> float:
        ebay_fee = sell_price * EBAY_FEE_RATE
        return sell_price - ebay_fee - part.ship_cost - PACKAGING_COST - part.kenny_price

    return calc(part.ebay_low), calc(part.ebay_high)


# ---------------------------------------------------------------------------
# Seen-vehicle persistence
# ---------------------------------------------------------------------------

def load_seen() -> set[str]:
    if SEEN_FILE.exists():
        data = json.loads(SEEN_FILE.read_text())
        return set(data)
    return set()


def save_seen(seen: set[str]) -> None:
    SEEN_FILE.write_text(json.dumps(sorted(seen), indent=2))


# ---------------------------------------------------------------------------
# Main scan logic
# ---------------------------------------------------------------------------

@dataclass
class Opportunity:
    vehicle: dict
    target: TargetVehicle
    trim: str
    parts: list[tuple[str, Part]]  # (key, Part) pairs
    trim_match: bool


def scan(
    branches: dict[str, str],
    make_filter: str | None,
    min_profit: float,
    check_trim: bool,
    new_only: bool,
) -> list[Opportunity]:
    session = get_session()
    seen = load_seen()
    opportunities: list[Opportunity] = []
    new_seen: set[str] = set()

    active_targets = [
        t for t in TARGETS
        if make_filter is None or t.make == make_filter.lower()
    ]

    for branch_name, branch_id in branches.items():
        print(f"\n→ Scanning branch: {branch_name} (ID {branch_id})")

        for target in active_targets:
            print(f"  {target.make} {target.model} ({target.year_min}–{target.year_max})...", end=" ", flush=True)

            try:
                total_pages = get_total_pages(session, branch_id, target.make, target.model)
            except Exception as e:
                print(f"ERROR fetching page count: {e}")
                continue

            all_vehicles: list[dict] = []
            for page in range(1, total_pages + 1):
                try:
                    vehicles = fetch_inventory_page(session, branch_id, target.make, target.model, page)
                    all_vehicles.extend(vehicles)
                    time.sleep(0.5)  # be polite
                except Exception as e:
                    print(f"ERROR on page {page}: {e}")
                    break

            # Filter by year range
            in_range = [
                v for v in all_vehicles
                if target.year_min <= v["year"] <= target.year_max
            ]
            print(f"{len(in_range)} in year range", end="")

            new_in_range = [v for v in in_range if v["slug"] not in seen]
            new_seen.update(v["slug"] for v in in_range)

            if new_only and not new_in_range:
                print(" (all seen, skipping)")
                continue
            candidates = new_in_range if new_only else in_range
            print(f", {len(candidates)} to evaluate")

            for vehicle in candidates:
                trim = ""
                if check_trim:
                    trim = get_vehicle_trim(session, vehicle["url"])
                    time.sleep(0.5)

                trim_match = (
                    not target.preferred_trims
                    or any(t in trim for t in target.preferred_trims)
                )

                # Collect parts that clear the profit threshold
                good_parts: list[tuple[str, Part]] = []
                for part_key in target.target_parts:
                    part = PARTS_CATALOG[part_key]
                    _, net_high = net_profit(part)
                    if net_high >= min_profit:
                        good_parts.append((part_key, part))

                if good_parts:
                    opportunities.append(Opportunity(
                        vehicle=vehicle,
                        target=target,
                        trim=trim,
                        parts=good_parts,
                        trim_match=trim_match,
                    ))

    # Persist newly seen slugs
    save_seen(seen | new_seen)
    return opportunities


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_report(opportunities: list[Opportunity], check_trim: bool) -> None:
    if not opportunities:
        print("\nNo opportunities found matching your criteria.")
        return

    # Sort: trim matches first, then by best-case net profit on top part
    def sort_key(opp: Opportunity) -> tuple:
        best = max(net_profit(p)[1] for _, p in opp.parts)
        return (not opp.trim_match, -best)

    opportunities.sort(key=sort_key)

    print(f"\n{'='*72}")
    print(f"  KENNY U-PULL PROFIT REPORT — {date.today()}")
    print(f"{'='*72}")

    for opp in opportunities:
        v = opp.vehicle
        trim_label = f"  trim: {opp.trim}" if check_trim and opp.trim else ""
        trim_flag = "" if opp.trim_match else "  ⚠ TRIM UNCONFIRMED"
        print(f"\n{'─'*72}")
        print(f"  {v['year']} {v['make'].title()} {v['model'].title()}{trim_label}{trim_flag}")
        print(f"  Row {v['row']}  |  Added {v['date_added']}  |  Branch {v['branch_id']}")
        print(f"  {v['url']}")
        if opp.target.notes:
            print(f"  Note: {opp.target.notes}")
        print()
        print(f"  {'Part':<42} {'Buy':>7}  {'eBay low':>9}  {'Net (low–high)':>16}")
        print(f"  {'-'*42} {'-'*7}  {'-'*9}  {'-'*16}")
        for _, part in opp.parts:
            low, high = net_profit(part)
            print(
                f"  {part.name:<42} ${part.kenny_price:>6.2f}  "
                f"${part.ebay_low:>7.0f}+  "
                f"${low:>6.0f} – ${high:>5.0f}"
            )
            if part.notes:
                print(f"    → {part.notes}")

    print(f"\n{'='*72}")
    print(f"  {len(opportunities)} vehicle(s) flagged")
    print(f"  Net profit = eBay sale − {EBAY_FEE_RATE*100:.2f}% fee − shipping − $8 packaging − Kenny price")
    print(f"{'='*72}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Kenny U-Pull profit scanner")
    p.add_argument(
        "--branch",
        choices=list(BRANCHES.keys()),
        default=None,
        help="Scan a single branch (default: all configured branches)",
    )
    p.add_argument("--make", default=None, help="Filter targets by make (e.g. honda)")
    p.add_argument(
        "--min-profit",
        type=float,
        default=80.0,
        help="Minimum net profit (high estimate) to flag a part (default: $80)",
    )
    p.add_argument(
        "--check-trim",
        action="store_true",
        help="Fetch each vehicle's detail page to verify trim level (slower)",
    )
    p.add_argument(
        "--new-only",
        action="store_true",
        help="Only report vehicles not seen in a previous run",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    branches = {args.branch: BRANCHES[args.branch]} if args.branch else BRANCHES

    if not branches:
        print("No branches configured. Add at least one branch ID to BRANCHES.")
        return

    print(f"Kenny U-Pull Scout  |  {date.today()}")
    print(f"Branches: {list(branches.keys())}  |  min profit: ${args.min_profit:.0f}")
    print(f"Trim check: {'yes (slow)' if args.check_trim else 'no (fast)'}")
    print(f"New-only mode: {args.new_only}")

    opportunities = scan(
        branches=branches,
        make_filter=args.make,
        min_profit=args.min_profit,
        check_trim=args.check_trim,
        new_only=args.new_only,
    )
    print_report(opportunities, check_trim=args.check_trim)


if __name__ == "__main__":
    main()
