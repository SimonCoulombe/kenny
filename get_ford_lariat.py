#!/usr/bin/env python3
"""
Ford F-series Lariat scanner — F-150 / F-250 / F-350 in Lariat trim, 2011+.

Unlike the Audi/VW scanners, the trim is read from Kenny's *style* field, not
from NHTSA. Ford does not VIN-encode the marketing trim (Lariat/XLT/XL/King
Ranch/...): the NHTSA decoder returns body-style descriptors like "Styleside"
or nothing at all. Kenny's style string, however, carries the trim name
(e.g. `4WD SUPERCREW 145" LARIAT`), so that is the only reliable source here.

Only F-150/F-250/F-350 are fetched in detail; other Ford models are filtered
out from the slug before any detail/NHTSA call. Saves to ford_lariat_state.json.
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

STATE_FILE = Path(__file__).parent / "ford_lariat_state.json"

YEAR_MIN = 2011
YEAR_MAX = 9999

# Models we care about, as they appear in the Kenny slug (lowercase).
TARGET_MODELS = {"f-150", "f-250", "f-350"}

# Trim phrase to match within Kenny's style string.
GOOD_PHRASE = "LARIAT"


def model_from_slug(slug: str) -> str:
    """Extract model from slug like 'ford_f-150_2013_kup-st-augustin_123'."""
    parts = slug.split("_")
    try:
        year_idx = next(i for i, p in enumerate(parts) if p.isdigit() and len(p) == 4)
        return " ".join(parts[1:year_idx]).title()
    except StopIteration:
        return ""


def model_slug_key(slug: str) -> str:
    """Return the raw model token from the slug (e.g. 'f-150'), lowercased."""
    parts = slug.split("_")
    return parts[1].lower() if len(parts) > 1 else ""


def classify(style: str) -> str:
    """
    Classify on Kenny's style string. Returns 'lariat', 'not_lariat', or 'unknown'.
    NHTSA trim is deliberately ignored — it does not carry Ford's marketing trim.
    """
    if not style:
        return "unknown"  # target model but no style text to read
    if GOOD_PHRASE in style.upper():
        return "lariat"
    return "not_lariat"


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
        print(f"  [ford] {branch_name} ({YEAR_MIN}+) ...", end=" ", flush=True, file=sys.stderr)
        try:
            vehicles = fetch_inventory(session, branch_id, "", YEAR_MIN, YEAR_MAX, brand="ford")
            time.sleep(0.4)
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            continue

        targets = [v for v in vehicles if model_slug_key(v["slug"]) in TARGET_MODELS]
        uncached = sum(1 for v in targets if v["slug"] not in cache)
        print(f"{len(vehicles)} ford, {len(targets)} F-series, {uncached} new (fetching details)",
              file=sys.stderr)

        for v in targets:
            v["is_new"]      = v["slug"] not in seen
            v["branch_name"] = branch_name
            if not v.get("model"):
                v["model"] = model_from_slug(v["slug"])
            new_slugs.add(v["slug"])

            fill_vehicle_detail(session, v, cache)
            # NHTSA trim is meaningless for Ford F-series; drop it so the report
            # card falls back to the style string (which carries the real trim).
            v["trim_nhtsa"] = ""

            status = classify(v["trim_raw"])
            if status == "lariat":
                confirmed.append(v)
            elif status == "not_lariat":
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
    p = argparse.ArgumentParser(description="Kenny Ford F-series Lariat scanner")
    p.add_argument("--branch", choices=list(BRANCHES))
    args = p.parse_args()

    branches = {args.branch: BRANCHES[args.branch]} if args.branch else BRANCHES
    print(f"[ford_lariat] {date.today()} | branches: {', '.join(branches)}", file=sys.stderr)

    seen  = load_seen()
    cache = load_detail_cache()
    confirmed, unknown, wrong, new_slugs = scan(branches, seen, cache)
    save_state(confirmed, unknown, wrong)
    save_seen(seen | new_slugs)
    save_detail_cache(cache)

    new = sum(1 for v in confirmed + unknown if v["is_new"])
    print(f"[ford_lariat] confirmed={len(confirmed)} unknown={len(unknown)} wrong={len(wrong)} new={new}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
