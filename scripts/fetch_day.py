#!/usr/bin/env python3
"""Stap 1 van de nieuwsproductie: haal de ruwe gebeurtenissen van één dag op.

Bron: de maandpagina's van Engelstalige Wikipedia (bijv. "November 1939"),
tekst onder CC BY-SA 4.0. Het script schrijft data/raw/JJJJ-MM-DD.json.

Gebruik:
    python scripts/fetch_day.py              # vandaag min 87 jaar
    python scripts/fetch_day.py 1939-11-21   # een vaste historische datum
"""
import datetime
import json
import pathlib
import re
import sys

import requests
from bs4 import BeautifulSoup

API = "https://en.wikipedia.org/w/api.php"
UA = "WarChronicleBot/0.1 (https://github.com/prumNL/war-chronicle; hobbyproject)"
OFFSET_YEARS = 87
WAR_START = datetime.date(1939, 9, 1)
WAR_END = datetime.date(1945, 9, 2)
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
HEADING = re.compile(r"^([A-Z][a-z]+) (\d{1,2}), (\d{4})")


def historical_date(today):
    """Dezelfde dag, 87 jaar eerder. 29 februari wordt 28 februari als dat jaar geen schrikkeljaar is."""
    try:
        return today.replace(year=today.year - OFFSET_YEARS)
    except ValueError:
        return today.replace(year=today.year - OFFSET_YEARS, day=28)


def fetch_month(year, month):
    page = f"{MONTHS[month - 1]}_{year}"
    r = requests.get(
        API,
        params={"action": "parse", "page": page, "prop": "text|revid",
                "format": "json", "formatversion": 2, "redirects": 1},
        headers={"User-Agent": UA},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if "parse" not in data:
        raise RuntimeError(f"Wikipedia gaf geen pagina terug voor {page}: {data.get('error')}")
    p = data["parse"]
    return p["title"], p["revid"], p["text"]


def parse_li(li):
    for junk in li.select("sup.reference, span.mw-editsection, style"):
        junk.decompose()
    links, seen = [], set()
    for a in li.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("/wiki/") or ":" in href[6:] or href in seen:
            continue
        seen.add(href)
        links.append({"title": a.get("title") or a.get_text(strip=True),
                      "url": "https://en.wikipedia.org" + href})
    text = re.sub(r"\s+", " ", li.get_text()).strip()
    kind = "born" if text.startswith("Born:") else "died" if text.startswith("Died:") else "event"
    return {"kind": kind, "text": text, "links": links}


def parse_day(html, d):
    """Geeft de lijst gebeurtenissen van datum d, of None als de dag niet op de pagina staat."""
    soup = BeautifulSoup(html, "html.parser")
    for h in soup.find_all(["h2", "h3"]):
        m = HEADING.match(h.get_text(" ", strip=True))
        if not m or m.group(1) not in MONTHS:
            continue
        if (MONTHS.index(m.group(1)) + 1, int(m.group(2)), int(m.group(3))) != (d.month, d.day, d.year):
            continue
        start = h.find_parent("div", class_="mw-heading") or h
        events = []
        for sib in start.next_siblings:
            if getattr(sib, "name", None) is None:
                continue
            if sib.name in ("h2", "h3") or (sib.name == "div" and "mw-heading" in (sib.get("class") or [])):
                break
            if sib.name == "ul":
                events += [parse_li(li) for li in sib.find_all("li", recursive=False)]
        return events
    return None


def main():
    if len(sys.argv) > 1 and sys.argv[1].strip():
        d = datetime.date.fromisoformat(sys.argv[1].strip())
    else:
        d = historical_date(datetime.datetime.now(datetime.timezone.utc).date())
    if not (WAR_START <= d <= WAR_END):
        print(f"{d} valt buiten 1 sep 1939 - 2 sep 1945. Geen nieuwe editie.")
        return 0
    title, revid, html = fetch_month(d.year, d.month)
    events = parse_day(html, d)
    if events is None:
        print(f"FOUT: de dag {d} staat niet op de pagina '{title}'.")
        return 1
    out = {
        "date": d.isoformat(),
        "edition_number": (d - WAR_START).days + 1,
        "source": {
            "title": f"Wikipedia: {title}",
            "url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
            "permalink": f"https://en.wikipedia.org/w/index.php?title={title.replace(' ', '_')}&oldid={revid}",
            "revid": revid,
            "license": "CC BY-SA 4.0",
            "fetched": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        },
        "events": events,
    }
    path = pathlib.Path("data/raw") / f"{d.isoformat()}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    n = sum(1 for e in events if e["kind"] == "event")
    print(f"{d}: {len(events)} regels ({n} gebeurtenissen) opgeslagen in {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
