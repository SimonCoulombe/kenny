#!/usr/bin/env python3
"""
LaneWatch scanner — Honda vehicles with the passenger-mirror camera.
EX / EX-L / Touring on specific models/years. ~$54 at the yard, $220-380 on eBay.ca.
Saves results to lanewatch_state.json.
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from kenny_lib import (
    BRANCHES, fetch_inventory, fill_vehicle_detail,
    get_session, load_seen, save_seen, load_detail_cache, save_detail_cache,
)

STATE_FILE = Path(__file__).parent / "lanewatch_state.json"


@dataclass(frozen=True)
class Target:
    model:      str
    year_min:   int
    year_max:   int
    good_trims: frozenset[str]


TARGETS: list[Target] = [
    Target("accord",  2013, 2017, frozenset({"EX", "EX-L", "EX-T", "TOURING"})),
    Target("civic",   2012, 2021, frozenset({"EX", "EX-L", "EX-T", "TOURING"})),
    # CR-V 2017+ dropped LaneWatch
    Target("cr-v",    2015, 2016, frozenset({"EX", "EX-L", "TOURING"})),
    Target("fit",     2015, 2020, frozenset({"EX", "EX-L"})),
    Target("hr-v",    2016, 2021, frozenset({"EX", "EX-L", "TOURING"})),
    # Odyssey only had LaneWatch 2015-2017 (not earlier 4th-gen years)
    Target("odyssey", 2015, 2017, frozenset({"EX", "EX-L", "TOURING", "ELITE"})),
    # Pilot plain EX does NOT have LaneWatch
    Target("pilot",   2016, 2022, frozenset({"EX-L", "TOURING", "ELITE"})),
]

NON_LANEWATCH_TRIMS: frozenset[str] = frozenset({
    "DX", "LX", "LX-P", "SE", "SPORT", "VP", "CX", "HF", "BASE", "CARGO",
})


def classify(trim_raw: str, target: Target, nhtsa_trim: str = "") -> str:
    """
    Tries nhtsa_trim first (more reliable), falls back to Kenny's style string.
    Skips NHTSA when it returns multiple comma-separated trims — ambiguous VIN range.
    """
    nhtsa_single = nhtsa_trim if nhtsa_trim and "," not in nhtsa_trim else ""
    for source in (nhtsa_single, trim_raw):
        if not source:
            continue
        tokens = set(source.upper().split())
        if tokens & target.good_trims:
            return "lanewatch"
        if tokens & NON_LANEWATCH_TRIMS:
            return "no_lanewatch"
    return "unknown"


def scan(
    branches: dict[str, str],
    seen:     set[str],
    cache:    dict,
) -> tuple[list[dict], list[dict], list[dict], set[str]]:
    session   = get_session()
    new_slugs: set[str] = set()
    confirmed: list[dict] = []
    unknown:   list[dict] = []
    wrong:     list[dict] = []

    for branch_name, branch_id in branches.items():
        for target in TARGETS:
            print(f"  {branch_name} / {target.model} ({target.year_min}–{target.year_max}) ...",
                  end=" ", flush=True, file=sys.stderr)
            try:
                vehicles = fetch_inventory(session, branch_id, target.model,
                                           target.year_min, target.year_max)
                time.sleep(0.4)
            except Exception as e:
                print(f"ERROR: {e}", file=sys.stderr)
                continue

            uncached = sum(1 for v in vehicles if v["slug"] not in cache)
            if uncached:
                print(f"{len(vehicles)} found, {uncached} new (fetching details+NHTSA)", file=sys.stderr)
            else:
                print(f"{len(vehicles)} found, 0 new (skipping details)", file=sys.stderr)

            for v in vehicles:
                v["is_new"]      = v["slug"] not in seen
                v["branch_name"] = branch_name
                new_slugs.add(v["slug"])

                fill_vehicle_detail(session, v, cache)
                status = classify(v["trim_raw"], target, v["trim_nhtsa"])
                if status == "lanewatch":
                    confirmed.append(v)
                elif status == "no_lanewatch":
                    wrong.append(v)
                else:
                    unknown.append(v)

    return confirmed, unknown, wrong, new_slugs


def save_state(confirmed: list[dict], unknown: list[dict], wrong: list[dict]) -> None:
    keys = ("url", "slug", "year", "make", "model", "row", "date_added",
            "branch_name", "trim_raw", "vin", "trim_nhtsa", "is_new")
    STATE_FILE.write_text(json.dumps({
        "date":      str(date.today()),
        "confirmed": [{k: v[k] for k in keys if k in v} for v in confirmed],
        "unknown":   [{k: v[k] for k in keys if k in v} for v in unknown],
        "wrong":     [{k: v[k] for k in keys if k in v} for v in wrong],
    }, indent=2))


def main() -> None:
    p = argparse.ArgumentParser(description="Kenny LaneWatch scanner")
    p.add_argument("--branch", choices=list(BRANCHES))
    args = p.parse_args()

    branches = {args.branch: BRANCHES[args.branch]} if args.branch else BRANCHES
    print(f"[lanewatch] {date.today()} | branches: {', '.join(branches)}", file=sys.stderr)

    seen  = load_seen()
    cache = load_detail_cache()
    confirmed, unknown, wrong, new_slugs = scan(branches, seen, cache)
    save_state(confirmed, unknown, wrong)
    save_seen(seen | new_slugs)
    save_detail_cache(cache)

    new = sum(1 for v in confirmed + unknown if v["is_new"])
    print(f"[lanewatch] confirmed={len(confirmed)} unknown={len(unknown)} wrong={len(wrong)} new={new}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
