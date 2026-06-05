#!/usr/bin/env python3
"""
My-cars scanner — alerts when a vehicle of the same generation as my own arrives.
Saves results to my_cars_state.json.
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

STATE_FILE = Path(__file__).parent / "my_cars_state.json"


@dataclass(frozen=True)
class PersonalTarget:
    make:     str
    model:    str
    year_min: int
    year_max: int
    label:    str


TARGETS: list[PersonalTarget] = [
    PersonalTarget("nissan", "leaf",    2018, 2022, "Nissan Leaf 2nd gen (2018–2022)"),
    # 4th-gen Odyssey; user owns 2015
    PersonalTarget("honda",  "odyssey", 2011, 2017, "Honda Odyssey 4th gen (2011–2017)"),
]


def scan(
    branches: dict[str, str],
    seen:     set[str],
    cache:    dict,
) -> tuple[dict[str, list[dict]], set[str]]:
    session   = get_session()
    new_slugs: set[str] = set()
    results: dict[str, list[dict]] = {t.label: [] for t in TARGETS}

    for branch_name, branch_id in branches.items():
        for target in TARGETS:
            print(f"  [my cars] {branch_name} / {target.model} ({target.year_min}–{target.year_max}) ...",
                  end=" ", flush=True, file=sys.stderr)
            try:
                vehicles = fetch_inventory(session, branch_id, target.model,
                                           target.year_min, target.year_max, brand=target.make)
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
                results[target.label].append(v)

    return results, new_slugs


def save_state(results: dict[str, list[dict]]) -> None:
    keys = ("url", "slug", "year", "make", "model", "row", "date_added",
            "branch_name", "trim_raw", "vin", "trim_nhtsa", "is_new")
    STATE_FILE.write_text(json.dumps({
        "date": str(date.today()),
        **{
            label: [{k: v[k] for k in keys if k in v} for v in vehicles]
            for label, vehicles in results.items()
        },
    }, indent=2))


def main() -> None:
    p = argparse.ArgumentParser(description="Kenny my-cars scanner")
    p.add_argument("--branch", choices=list(BRANCHES))
    args = p.parse_args()

    branches = {args.branch: BRANCHES[args.branch]} if args.branch else BRANCHES
    print(f"[my_cars] {date.today()} | branches: {', '.join(branches)}", file=sys.stderr)

    seen  = load_seen()
    cache = load_detail_cache()
    results, new_slugs = scan(branches, seen, cache)
    save_state(results)
    save_seen(seen | new_slugs)
    save_detail_cache(cache)

    new   = sum(1 for vlist in results.values() for v in vlist if v["is_new"])
    total = sum(len(vlist) for vlist in results.values())
    print(f"[my_cars] total={total} new={new}", file=sys.stderr)


if __name__ == "__main__":
    main()
