#!/usr/bin/env python3
"""
Audi xenon headlight scanner — Q5 and A4, Premium Plus or Prestige trim.
These have bi-xenon + AFS adaptive headlights worth ~$1800 CAD at resale.
Classification relies on NHTSA VIN decoder, not Kenny's style string.
Saves results to audi_xenon_state.json.
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

STATE_FILE = Path(__file__).parent / "audi_xenon_state.json"

# NHTSA trim phrases that confirm bi-xenon + AFS
GOOD_PHRASES = ["PREMIUM PLUS", "PRESTIGE"]
# NHTSA trim phrases that confirm no AFS (base Premium has xenon but no directional)
BAD_PHRASES  = ["PREMIUM"]


@dataclass(frozen=True)
class Target:
    model:    str
    year_min: int
    year_max: int


TARGETS: list[Target] = [
    Target("q5", 2013, 2017),
    Target("a4", 2013, 2016),
]


def classify(nhtsa_trim: str) -> str:
    """
    Returns 'xenon', 'no_xenon', or 'unknown'.
    Only trusts unambiguous single-value NHTSA trims (skips comma-separated ranges).
    Checks GOOD_PHRASES before BAD_PHRASES so "PREMIUM PLUS" isn't caught by "PREMIUM".
    """
    if not nhtsa_trim or "," in nhtsa_trim:
        return "unknown"
    t = nhtsa_trim.upper()
    for phrase in GOOD_PHRASES:
        if phrase in t:
            return "xenon"
    for phrase in BAD_PHRASES:
        if phrase in t:
            return "no_xenon"
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
            print(f"  [audi] {branch_name} / {target.model} ({target.year_min}–{target.year_max}) ...",
                  end=" ", flush=True, file=sys.stderr)
            try:
                vehicles = fetch_inventory(session, branch_id, target.model,
                                           target.year_min, target.year_max, brand="audi")
                time.sleep(0.4)
            except Exception as e:
                print(f"ERROR: {e}", file=sys.stderr)
                continue

            print(f"{len(vehicles)} found", file=sys.stderr)

            for v in vehicles:
                v["is_new"]      = v["slug"] not in seen
                v["branch_name"] = branch_name
                new_slugs.add(v["slug"])

                fill_vehicle_detail(session, v, cache)
                status = classify(v["trim_nhtsa"])
                if status == "xenon":
                    confirmed.append(v)
                elif status == "no_xenon":
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
    p = argparse.ArgumentParser(description="Kenny Audi xenon headlight scanner")
    p.add_argument("--branch", choices=list(BRANCHES))
    args = p.parse_args()

    branches = {args.branch: BRANCHES[args.branch]} if args.branch else BRANCHES
    print(f"[audi_xenon] {date.today()} | branches: {', '.join(branches)}", file=sys.stderr)

    seen  = load_seen()
    cache = load_detail_cache()
    confirmed, unknown, wrong, new_slugs = scan(branches, seen, cache)
    save_state(confirmed, unknown, wrong)
    save_seen(seen | new_slugs)
    save_detail_cache(cache)

    new = sum(1 for v in confirmed + unknown if v["is_new"])
    print(f"[audi_xenon] confirmed={len(confirmed)} unknown={len(unknown)} wrong={len(wrong)} new={new}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
