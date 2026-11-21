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


def api_parse(page, **extra):
    params = {"action": "parse", "page": page, "format": "json",
              "formatversion": 2, "redirects": 1}
    params.update(extra)
    r = requests.get(API, params=params, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "parse" not in data:
        raise RuntimeError(f"Wikipedia gaf geen pagina terug voor {page}: {data.get('error')}")
    return data["parse"]


def clean(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text).replace("\xa0", " ")).strip()


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
    text = re.sub(r"\s+", " ", li.get_text().replace("\xa0", " ")).strip()
    kind = "born" if text.startswith("Born:") else "died" if text.startswith("Died:") else "event"
    return {"kind": kind, "text": text, "links": links}


def parse_day_html(html):
    """Haal de gebeurtenissen uit de HTML van het stukje van één dag."""
    soup = BeautifulSoup(html, "html.parser")
    events = []
    for li in soup.find_all("li"):
        if li.find_parent("li") or li.find_parent(class_=re.compile("reflist|references|navbox")):
            continue
        if li.parent.name != "ul":
            continue
        events.append(parse_li(li))
    return events


def fetch_day(d):
    """Geeft (titel, revid, gebeurtenissen, gevonden_koppen). Gebeurtenissen is None als de dag ontbreekt."""
    page = f"{MONTHS[d.month - 1]}_{d.year}"
    info = api_parse(page, prop="sections|revid")
    wanted = re.compile(rf"^{MONTHS[d.month - 1]} {d.day}, {d.year}\b")
    lines = [clean(sec.get("line", "")) for sec in info["sections"]]
    for sec, line in zip(info["sections"], lines):
        if wanted.match(line):
            part = api_parse(page, prop="text", section=sec["index"])
            return info["title"], info["revid"], parse_day_html(part["text"]), lines
    return info["title"], info["revid"], None, lines


def main():
    if len(sys.argv) > 1 and sys.argv[1].strip():
        d = datetime.date.fromisoformat(sys.argv[1].strip())
    else:
        d = historical_date(datetime.datetime.now(datetime.timezone.utc).date())
    if not (WAR_START <= d <= WAR_END):
        print(f"{d} valt buiten 1 sep 1939 - 2 sep 1945. Geen nieuwe editie.")
        return 0
    title, revid, events, lines = fetch_day(d)
    if events is None:
        print(f"FOUT: de dag {d} staat niet op de pagina '{title}'.")
        print(f"Gevonden koppen ({len(lines)}): {lines[:12]}")
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
