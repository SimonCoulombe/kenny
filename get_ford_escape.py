#!/usr/bin/env python3
"""
Ford Escape Titanium / Limited scanner — 2008+ Escape, top trims only.

Limited was the top trim of the 2008–2012 generation; Titanium replaced it
from the 2013 redesign onward. Both NHTSA and Kenny's style field carry the
trim for the Escape (they agree), so this scanner checks both — NHTSA first,
style as fallback — unlike the Ford F-series scanner where NHTSA is useless.

Only the Escape model is fetched in detail; other Ford models are dropped from
the slug before any detail/NHTSA call. Saves to ford_escape_state.json.
"""

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

from kenny_lib import (
    BRANCHES, fetch_inventory, fill_vehicle_detail,
    get_session, load_seen, save_seen, load_detail_cache, save_detail_cache,
)

STATE_FILE = Path(__file__).parent / "ford_escape_state.json"

YEAR_MIN = 2008
YEAR_MAX = 9999

# Model token as it appears in the Kenny slug.
TARGET_MODEL = "escape"

# Trims we want.
GOOD_PHRASES = ["TITANIUM", "LIMITED"]
# Other recognizable Escape trims — their presence means "not our trim" rather
# than "couldn't read it", so the vehicle goes to the wrong bucket, not unknown.
OTHER_TRIMS = ["XLT", "XLS", "SEL", "SE", "S"]


def classify(nhtsa_trim: str, style: str) -> str:
    """
    Returns 'match', 'not_match', or 'unknown'.
    Both NHTSA and Kenny's style string are scanned (they agree for the Escape);
    a phrase match anywhere in either counts.
    """
    text = f"{nhtsa_trim or ''} {style or ''}".upper()
    if not text.strip():
        return "unknown"
    for phrase in GOOD_PHRASES:
        if phrase in text:
            return "match"
    for phrase in OTHER_TRIMS:
        if phrase in text:
            return "not_match"
    return "unknown"  # has style/NHTSA text but no recognizable trim


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
        print(f"  [escape] {branch_name} ({YEAR_MIN}+) ...", end=" ", flush=True, file=sys.stderr)
        try:
            vehicles = fetch_inventory(session, branch_id, "", YEAR_MIN, YEAR_MAX, brand="ford")
            time.sleep(0.4)
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            continue

        targets = [v for v in vehicles if v["slug"].split("_")[1].lower() == TARGET_MODEL]
        uncached = sum(1 for v in targets if v["slug"] not in cache)
        print(f"{len(vehicles)} ford, {len(targets)} escape, {uncached} new (fetching details+NHTSA)",
              file=sys.stderr)

        for v in targets:
            v["is_new"]      = v["slug"] not in seen
            v["branch_name"] = branch_name
            v["model"]       = "Escape"
            new_slugs.add(v["slug"])

            fill_vehicle_detail(session, v, cache)
            status = classify(v["trim_nhtsa"], v["trim_raw"])
            if status == "match":
                confirmed.append(v)
            elif status == "not_match":
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
    p = argparse.ArgumentParser(description="Kenny Ford Escape Titanium/Limited scanner")
    p.add_argument("--branch", choices=list(BRANCHES))
    args = p.parse_args()

    branches = {args.branch: BRANCHES[args.branch]} if args.branch else BRANCHES
    print(f"[ford_escape] {date.today()} | branches: {', '.join(branches)}", file=sys.stderr)

    seen  = load_seen()
    cache = load_detail_cache()
    confirmed, unknown, wrong, new_slugs = scan(branches, seen, cache)
    save_state(confirmed, unknown, wrong)
    save_seen(seen | new_slugs)
    save_detail_cache(cache)

    new = sum(1 for v in confirmed + unknown if v["is_new"])
    print(f"[ford_escape] confirmed={len(confirmed)} unknown={len(unknown)} wrong={len(wrong)} new={new}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
