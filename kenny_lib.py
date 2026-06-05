import json
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BRANCHES: dict[str, str] = {
    "st-aug": "1457197",
    "levis":  "1457186",
}

BASE_URL         = "https://kennyupull.com"
INVENTORY_URL    = f"{BASE_URL}/auto-parts/our-inventory/"
SEEN_FILE         = Path(__file__).parent / "seen_vehicles.json"
DETAIL_CACHE_FILE = Path(__file__).parent / "detail_cache.json"
NHTSA_DECODE_URL  = "https://vpic.nhtsa.dot.gov/api/vehicles/decodevin/{}?format=json"


def get_session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"]      = "Mozilla/5.0 (personal research script)"
    s.headers["Accept-Language"] = "en-CA,en;q=0.9"
    return s


def _inventory_url(page: int) -> str:
    return INVENTORY_URL if page <= 1 else f"{INVENTORY_URL}page/{page}/"


def fetch_inventory(
    session:   requests.Session,
    branch_id: str,
    model:     str,
    year_min:  int,
    year_max:  int,
    brand:     str = "honda",
) -> list[dict]:
    """Return all vehicles matching make/model/year-range from all pages."""
    params = {
        "brand":    brand,
        "model":    model,
        "nb_items": 99,
        "branch[]": branch_id,
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
                    "vin":        "",
                    "trim_nhtsa": "",
                })

        if not soup.select_one("a.next.page-numbers") or page >= 10:
            break
        page += 1
        time.sleep(0.4)

    return vehicles


def fetch_vehicle_detail(session: requests.Session, url: str) -> tuple[str, str]:
    """Return (kenny_style, vin) from a vehicle detail page, or ('', '')."""
    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        style = ""
        vin   = ""
        for subtitle in soup.select("p.subtitle"):
            label = subtitle.get_text(strip=True).lower()
            nxt   = subtitle.find_next_sibling("p")
            if not nxt:
                continue
            if label == "style":
                style = nxt.get_text(strip=True).upper()
            elif label == "vin":
                vin = nxt.get_text(strip=True).upper()
        return style, vin
    except Exception:
        return "", ""


def fetch_nhtsa_trim(vin: str) -> str:
    """Return the Trim field from the NHTSA VIN decoder, or '' on failure."""
    if len(vin) != 17:
        return ""
    try:
        resp = requests.get(
            NHTSA_DECODE_URL.format(vin), timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (personal research script)"}
        )
        resp.raise_for_status()
        for item in resp.json().get("Results", []):
            if item.get("Variable") == "Trim" and item.get("Value"):
                return item["Value"].upper()
    except Exception:
        pass
    return ""


def load_seen() -> set[str]:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def save_seen(seen: set[str]) -> None:
    SEEN_FILE.write_text(json.dumps(sorted(seen), indent=2))


def load_detail_cache() -> dict[str, dict]:
    if DETAIL_CACHE_FILE.exists():
        return json.loads(DETAIL_CACHE_FILE.read_text())
    return {}


def save_detail_cache(cache: dict[str, dict]) -> None:
    DETAIL_CACHE_FILE.write_text(json.dumps(cache, indent=2))


def fill_vehicle_detail(session: requests.Session, v: dict, cache: dict[str, dict]) -> None:
    """Populate trim_raw, vin, trim_nhtsa on v — from cache or by fetching."""
    slug = v["slug"]
    if slug in cache:
        v.update(cache[slug])
        return

    v["trim_raw"], v["vin"] = fetch_vehicle_detail(session, v["url"])
    time.sleep(0.4)
    if v["vin"]:
        v["trim_nhtsa"] = fetch_nhtsa_trim(v["vin"])
        time.sleep(0.3)

    if v["trim_raw"] or v["vin"]:
        cache[slug] = {"trim_raw": v["trim_raw"], "vin": v["vin"], "trim_nhtsa": v["trim_nhtsa"]}


def html_vehicle_card(v: dict, accent: str, show_trim: bool) -> str:
    new_badge = (
        '<span style="background:#f59e0b;color:#fff;font-size:11px;font-weight:bold;'
        'padding:2px 7px;border-radius:3px;margin-right:6px;">★ NEW</span>'
        if v.get("is_new") else ""
    )
    trim_display = v.get("trim_nhtsa") or v.get("trim_raw", "")
    trim_str = (
        f' <span style="color:#666;font-size:13px;">[{trim_display}]</span>'
        if show_trim and trim_display else ""
    )
    branch_label = v.get("branch_name", "").replace("st-aug", "St-Augustin").replace("levis", "Lévis")
    return (
        f'<div style="border:1px solid #e2e8f0;border-left:4px solid {accent};'
        f'border-radius:4px;padding:12px 16px;margin-bottom:8px;">'
        f'<div style="margin-bottom:4px;">{new_badge}'
        f'<strong style="font-size:15px;">{v["year"]} {v["make"].title()} {v["model"].title()}</strong>'
        f'{trim_str}</div>'
        f'<div style="font-size:13px;color:#555;margin-bottom:6px;">'
        f'Row {v["row"]} &nbsp;·&nbsp; {v["date_added"]} &nbsp;·&nbsp; {branch_label}</div>'
        f'<a href="{v["url"]}" style="font-size:13px;color:#2563eb;text-decoration:none;">'
        f'View on Kenny U-Pull →</a>'
        f'</div>'
    )


def html_wrap(date_str: str, body: str) -> str:
    return (
        '<!DOCTYPE html><html><head><meta charset="UTF-8"></head>'
        '<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,Helvetica,sans-serif;">'
        '<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:20px 10px;">'
        '<table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:8px;'
        'overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">'
        '<tr><td style="background:#1a1a2e;padding:20px 24px;">'
        '<h1 style="margin:0;font-size:20px;color:#fff;">🔍 Kenny U-Pull Scanner</h1>'
        f'<p style="margin:4px 0 0;color:#8888aa;font-size:13px;">{date_str}</p>'
        '</td></tr>'
        f'<tr><td style="padding:20px 24px;">{body}</td></tr>'
        '</table></td></tr></table>'
        '</body></html>'
    )
