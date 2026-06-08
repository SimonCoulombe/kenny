#!/usr/bin/env python3
"""
Reads state files from the three scanner scripts and generates a combined HTML report.
Prints HTML to stdout (redirect to report.html or pipe to mail).
"""

import json
from datetime import date
from pathlib import Path

from kenny_lib import html_vehicle_card, html_wrap

LANEWATCH_STATE = Path(__file__).parent / "lanewatch_state.json"
MY_CARS_STATE   = Path(__file__).parent / "my_cars_state.json"
AUDI_STATE      = Path(__file__).parent / "audi_xenon_state.json"
VW_STATE        = Path(__file__).parent / "volkswagen_xenon_state.json"
FORD_STATE      = Path(__file__).parent / "ford_lariat_state.json"
ESCAPE_STATE    = Path(__file__).parent / "ford_escape_state.json"

HR = '<hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0;">'
H2_STYLE = "font-size:16px;color:#1a1a2e;margin:0 0 12px;border-bottom:2px solid #e2e8f0;padding-bottom:8px;"
NONE_FOUND = '<p style="color:#888;font-size:14px;">None found.</p>'


def _cards(vehicles: list[dict], accent: str, show_trim: bool) -> str:
    by_new_then_date = lambda v: (not v.get("is_new"), v.get("date_added", ""))
    return "".join(html_vehicle_card(v, accent, show_trim)
                   for v in sorted(vehicles, key=by_new_then_date))


def _subsection(heading: str, color: str, vehicles: list[dict], accent: str, show_trim: bool) -> str:
    n = len(vehicles)
    count = f' — {n} vehicle{"s" if n != 1 else ""}'
    return (
        f'<h3 style="font-size:14px;color:{color};margin:12px 0 8px;">{heading}{count}</h3>'
        + _cards(vehicles, accent, show_trim)
    )


def lanewatch_section() -> str:
    data = json.loads(LANEWATCH_STATE.read_text()) if LANEWATCH_STATE.exists() else {}
    confirmed = data.get("confirmed", [])
    unknown   = data.get("unknown",   [])

    content = ""
    if confirmed:
        content += _subsection("✓ Confirmed LaneWatch", "#16a34a", confirmed, "#16a34a", True)
    if unknown:
        content += _subsection("? Trim unknown — check in person", "#d97706", unknown, "#d97706", False)
    if not content:
        content = NONE_FOUND

    return f'<h2 style="{H2_STYLE}">LaneWatch</h2>' + content


def audi_section() -> str:
    data = json.loads(AUDI_STATE.read_text()) if AUDI_STATE.exists() else {}
    confirmed = data.get("confirmed", [])
    unknown   = data.get("unknown",   [])

    content = ""
    if confirmed:
        content += _subsection("✓ Confirmed — Premium Plus / Prestige", "#16a34a", confirmed, "#16a34a", True)
    if unknown:
        content += _subsection("? Trim unknown — check VIN at yard", "#d97706", unknown, "#d97706", True)
    if not content:
        content = NONE_FOUND

    return f'<h2 style="{H2_STYLE}">Audi Xenon Headlights</h2>' + content


def vw_section() -> str:
    data = json.loads(VW_STATE.read_text()) if VW_STATE.exists() else {}
    confirmed = data.get("confirmed", [])

    content = ""
    if confirmed:
        content += _subsection("✓ Confirmed Highline", "#16a34a", confirmed, "#16a34a", True)
    if not content:
        content = NONE_FOUND

    return f'<h2 style="{H2_STYLE}">VW Xenon Headlights</h2>' + content


def ford_section() -> str:
    data = json.loads(FORD_STATE.read_text()) if FORD_STATE.exists() else {}
    confirmed = data.get("confirmed", [])
    unknown   = data.get("unknown",   [])

    content = ""
    if confirmed:
        content += _subsection("✓ Confirmed Lariat", "#16a34a", confirmed, "#16a34a", True)
    if unknown:
        content += _subsection("? Trim unknown — check in person", "#d97706", unknown, "#d97706", True)
    if not content:
        content = NONE_FOUND

    return f'<h2 style="{H2_STYLE}">Ford F-Series Lariat</h2>' + content


def escape_section() -> str:
    data = json.loads(ESCAPE_STATE.read_text()) if ESCAPE_STATE.exists() else {}
    confirmed = data.get("confirmed", [])
    unknown   = data.get("unknown",   [])

    content = ""
    if confirmed:
        content += _subsection("✓ Confirmed Titanium / Limited", "#16a34a", confirmed, "#16a34a", True)
    if unknown:
        content += _subsection("? Trim unknown — check in person", "#d97706", unknown, "#d97706", True)
    if not content:
        content = NONE_FOUND

    return f'<h2 style="{H2_STYLE}">Ford Escape Titanium / Limited</h2>' + content


def my_cars_section() -> str:
    data   = json.loads(MY_CARS_STATE.read_text()) if MY_CARS_STATE.exists() else {}
    labels = [k for k in data if k != "date"]

    content = ""
    for label in labels:
        vehicles = data.get(label, [])
        if vehicles:
            content += _subsection(label, "#1d4ed8", vehicles, "#2563eb", True)
        else:
            content += (
                f'<h3 style="font-size:14px;color:#1d4ed8;margin:12px 0 4px;">{label}</h3>'
                + NONE_FOUND
            )
    if not content:
        content = NONE_FOUND

    return f'<h2 style="{H2_STYLE}">My Cars</h2>' + content


def generate() -> str:
    sections = [lanewatch_section(), audi_section(), vw_section(),
                ford_section(), escape_section(), my_cars_section()]
    return html_wrap(str(date.today()), HR.join(sections))


if __name__ == "__main__":
    print(generate())
