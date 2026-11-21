#!/usr/bin/env python3
"""Stap 2: maak uit de ruwe Wikipedia-regels een Nederlandstalige krant-editie.

Gebruik:
    python scripts/build_edition.py                  # vandaag min 87 jaar
    python scripts/build_edition.py 1939-11-23       # een dag
    python scripts/build_edition.py 1939-09-01 1939-11-20   # een reeks (terugwerkend aanmaken)
Met FORCE=1 worden bestaande edities overschreven (anders blijven ze staan).

Alles is automatisch: kiezen, indelen, vertalen (Argos Translate, gratis en open)
en bronvermelding. Elk bericht draagt het label 'Automatisch vertaald' en toont de
Engelse originele regel, zodat lezers kunnen controleren.
"""
import datetime
import json
import os
import pathlib
import re
import sys
import time

import requests

import fetch_day as fd

DATA = pathlib.Path("data")
MAX_ARTICLES = 5
MAX_DEATHS = 3
UA = {"User-Agent": fd.UA}

# ---- indeling in rubrieken (eerste treffer wint) -------------------------------------------
SECTIONS = [
    ("Nederland en de bezetting", r"\b(Dutch|Netherlands|Holland|Wilhelmina|Amsterdam|Rotterdam|The Hague)\b"),
    ("Pacific", r"\b(Japan\w*|China|Chinese|Pacific|Philippines|Manchuria|Nanning|Guangxi|Pearl Harbor)\b"),
    ("Noord-Afrika en Italië", r"\b(Italy|Italian|Libya|Egypt|Mussolini|Africa\w*)\b"),
    ("Westfront en Oostfront", r"\b(Soviet|Red Army|Finland|Finnish|Winter War|Western Front|Maginot|Gamelin|Wehrmacht)\b"),
    ("Politiek en diplomatie", r"\b(Prime Minister|Parliament|House of Commons|government|ambassador|diplomat\w*|treaty|pact|mediation|Chancellor|President|blockade)\b"),
    ("Duitsland en de Asmogendheden", r"\b(German\w*|Nazi\w*|Hitler|Reich|Gestapo|Luftwaffe|U-\d+)\b"),
    ("Geallieerden", r"\b(British|Britain|French|France|Royal Navy|RAF|HMS|Allied|Chamberlain|Churchill|Polish|Poland)\b"),
]
DEFAULT_SECTION = "Internationale ontwikkelingen"

# ---- relevantie: wat is oorlogsnieuws? ---------------------------------------------------
WAR_WORDS = re.compile(
    r"\b(killed|sunk|sank|invad\w*|massacre\w*|execut\w*|bomb\w*|attack\w*|declared|surrender\w*|occupied|occupation|"
    r"mine[sd]?|torpedo\w*|offensive|arrest\w*|deport\w*|blockade|Hitler|Churchill|Chamberlain|Stalin|Roosevelt|"
    r"army|navy|fleet|destroyer|cruiser|submarine|U-\d+|German\w*|British|Soviet|Polish|Dutch|French|Japan\w*|"
    r"war|troops|forces|mobili[sz]\w*|ghetto|Jews|Jewish|concentration camp|resistance|government|treaty|"
    r"ultimatum|negotiations|mediation|directive|crew|lives)\b", re.I)
NOT_WAR = re.compile(r"\b(film|comics?|Heisman|Opry|baseball|football|basketball|stadium|married actress|Flash Comics)\b", re.I)
CASUALTIES = re.compile(r"\b\d[\d,]*\s+(people|crew|lives|killed|died|Poles|Jews|Czechs|civilians|soldiers)\b", re.I)
GENERIC_CONTEXT = {"Germany", "Nazi_Germany", "United_Kingdom", "France", "Poland", "Soviet_Union", "Netherlands",
                   "United_States", "Japan", "China", "Finland", "Italy", "Belgium", "Europe", "London", "Paris",
                   "Berlin", "Moscow", "Prime_Minister_of_the_United_Kingdom"}


def score(text):
    if NOT_WAR.search(text):
        return -10
    return 2 * len(set(m.lower() for m in WAR_WORDS.findall(text))) + (3 if CASUALTIES.search(text) else 0)


def section_of(text):
    for name, rx in SECTIONS:
        if re.search(rx, text, re.I):
            return name
    return DEFAULT_SECTION


# ---- vertalen -----------------------------------------------------------------------------
class Translator:
    def __init__(self):
        self.ok = False
        try:
            import argostranslate.package as pkg
            import argostranslate.translate as tr
            self._tr = tr
            langs = tr.get_installed_languages()
            en = next((l for l in langs if l.code == "en"), None)
            nl = next((l for l in langs if l.code == "nl"), None)
            if not (en and nl and en.get_translation(nl)):
                pkg.update_package_index()
                cand = next(p for p in pkg.get_available_packages() if p.from_code == "en" and p.to_code == "nl")
                pkg.install_from_path(cand.download())
            self.ok = True
        except Exception as e:  # geen vertaling beschikbaar: ga door met Engelse tekst
            print(f"WAARSCHUWING: vertalen niet beschikbaar ({e}). Teksten blijven Engels.")

    def __call__(self, text):
        if not self.ok or not text.strip():
            return text
        parts = re.split(r'(?<=[.!?])\s+(?=[A-Z"“])', text.strip())
        try:
            return " ".join(self._tr.translate(p, "en", "nl") for p in parts)
        except Exception as e:
            print(f"WAARSCHUWING: vertaling mislukt ({e}).")
            return text


def summary(url):
    """Eerste twee zinnen van het Wikipedia-artikel achter een link (als historische context)."""
    slug = url.split("/wiki/", 1)[1]
    if slug in GENERIC_CONTEXT or re.fullmatch(r"\d{4}", slug):
        return None
    try:
        r = requests.get("https://en.wikipedia.org/api/rest_v1/page/summary/" + slug, headers=UA, timeout=30)
        if r.status_code != 200:
            return None
        j = r.json()
        if j.get("type") != "standard" or len(j.get("extract", "")) < 40:
            return None
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', j["extract"])
        return " ".join(sentences[:2]), j.get("title", slug.replace("_", " "))
    except Exception:
        return None


# ---- ruwe data ----------------------------------------------------------------------------
def get_raw(d):
    path = DATA / "raw" / f"{d.isoformat()}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    title, revid, events, lines = fd.fetch_day(d)
    if events is None:
        return None
    t = title.replace(" ", "_")
    raw = {"date": d.isoformat(), "edition_number": (d - fd.WAR_START).days + 1,
           "source": {"title": f"Wikipedia: {title}", "url": f"https://en.wikipedia.org/wiki/{t}",
                      "permalink": f"https://en.wikipedia.org/w/index.php?title={t}&oldid={revid}",
                      "revid": revid, "license": "CC BY-SA 4.0",
                      "fetched": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")},
           "events": events}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    return raw


# ---- editie bouwen ------------------------------------------------------------------------
def headline(body):
    first = re.split(r"(?<=[.!?])\s(?=[A-Z\"“])", body.strip())[0].rstrip(".!? ")
    if len(first) > 95:
        first = first[:95].rsplit(" ", 1)[0] + "…"
    return first[:1].upper() + first[1:]


def build(raw, translate):
    src = raw["source"]
    day_source = {"title": f"{src['title']} (CC BY-SA 4.0)", "url": src["permalink"]}
    events = [e for e in raw["events"] if e["kind"] == "event"]
    ranked = sorted(((score(e["text"]), i, e) for i, e in enumerate(events)), key=lambda t: (-t[0], t[1]))
    chosen = [t for t in ranked if t[0] >= 2][:MAX_ARTICLES]
    chosen.sort(key=lambda t: (-t[0], t[1]))  # sterkste bericht eerst = voorpagina

    articles = []
    for sc, _, e in chosen:
        body_nl = translate(e["text"])
        context, sources = "", [day_source]
        for link in e["links"]:
            res = summary(link["url"])
            if res:
                text, title = res
                context = translate(text)
                sources.append({"title": f"Wikipedia: {title} (CC BY-SA 4.0)", "url": link["url"]})
                break
        articles.append({"section": section_of(e["text"]), "headline": headline(body_nl), "location": "",
                         "body": [body_nl], "context": context, "status": "auto", "auto": True,
                         "translated": getattr(translate, "ok", False), "original": e["text"], "sources": sources})

    deaths = [e for e in raw["events"] if e["kind"] == "died"]
    deaths.sort(key=lambda e: -score(e["text"]))
    lines = []
    for e in deaths[:MAX_DEATHS]:
        txt = e["text"].removeprefix("Died:").strip()
        m = re.match(r"^(.*?), (\d{1,3}), (.*)$", txt)
        lines.append(f"{m.group(1)} ({m.group(2)}), {translate(m.group(3))}" if m else translate(txt))
    if lines:
        articles.append({"section": "Overleden", "headline": "Overleden op deze dag", "location": "",
                         "body": lines, "context": "", "status": "auto", "auto": True,
                         "translated": getattr(translate, "ok", False),
                         "original": "; ".join(e["text"] for e in deaths[:MAX_DEATHS]),
                         "sources": [day_source]})
    return {"date": raw["date"], "number": raw["edition_number"], "articles": articles}


def update_index(ed):
    path = DATA / "index.json"
    idx = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"editions": []}
    idx["editions"] = [e for e in idx["editions"] if e["date"] != ed["date"]]
    idx["editions"].append({"date": ed["date"], "number": ed["number"], "headline": ed["articles"][0]["headline"],
                            "topics": sorted({a["section"] for a in ed["articles"]})})
    idx["editions"].sort(key=lambda e: e["date"])
    path.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")


def parse_dates(argv):
    args = [a.strip() for a in argv if a.strip()]
    if not args:
        d = fd.historical_date(datetime.datetime.now(datetime.timezone.utc).date())
        return [d]
    start = datetime.date.fromisoformat(args[0])
    end = datetime.date.fromisoformat(args[1]) if len(args) > 1 else start
    return [start + datetime.timedelta(days=i) for i in range((end - start).days + 1)]


def main():
    force = os.environ.get("FORCE", "").lower() in ("1", "ja", "true")
    translate = None
    made = 0
    for d in parse_dates(sys.argv[1:]):
        if not (fd.WAR_START <= d <= fd.WAR_END):
            print(f"{d}: buiten 1 sep 1939 - 2 sep 1945, overgeslagen.")
            continue
        out = DATA / "editions" / f"{d.isoformat()}.json"
        if out.exists() and not force:
            print(f"{d}: editie bestaat al, overgeslagen (FORCE=1 om te overschrijven).")
            continue
        raw = get_raw(d)
        if raw is None:
            print(f"{d}: dag niet gevonden bij Wikipedia, overgeslagen.")
            continue
        translate = translate or Translator()
        ed = build(raw, translate)
        if not ed["articles"]:
            print(f"{d}: geen betrouwbare berichten gevonden, geen editie gemaakt.")
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(ed, ensure_ascii=False, indent=2), encoding="utf-8")
        update_index(ed)
        made += 1
        print(f"{d}: editie {ed['number']} met {len(ed['articles'])} berichten.")
        time.sleep(1)
    print(f"Klaar: {made} edities gemaakt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
