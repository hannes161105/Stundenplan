#!/usr/bin/env python3
"""
Baut deinen persönlichen Stundenplan aus dem Veranstaltungsplan der FH Westküste.

Aufruf:
    python3 build.py                        # lädt den Originalplan aus dem Netz, schreibt index.html
    python3 build.py --file plan.html       # liest eine lokal gespeicherte Kopie des Originalplans
    python3 build.py --out seite.html       # anderer Ausgabename

Nur die Standardbibliothek von Python wird benötigt (ab Python 3.9).
Deine Regeln stehen im Abschnitt "DEINE REGELN" direkt unter dieser Beschreibung.
Schlägt etwas fehl (Seite nicht erreichbar, Aufbau geändert), bricht das Skript mit einer
Fehlermeldung ab und lässt die bisherige index.html unverändert.
"""
import datetime as dt
import html
import json
import re
import sys
import urllib.request
from zoneinfo import ZoneInfo

# ----------------------------------------------------------------------------
# DEINE REGELN
# ----------------------------------------------------------------------------
SOURCE_URL = ("https://moodle.fh-westkueste.de/sked/jahrg%C3%A4ngefbw/"
              "Green%20Technology%20(B.Eng.)%202026.html")

# Das Physik-Tutorium beginnt laut Physik-Terminliste erst am 19.10.2026.
TUTORIUM_AB = "2026-10-19"

# Das Praktikum Bautechnik und Mechanik beginnt am 30.10.2026 (davor ausgeblendet).
BAUTECHNIK_PRAKTIKUM_AB = "2026-10-30"

# Informatik-Praktikum: Du bist in Gruppe 2, also nur der Termin, der um 14:00 beginnt.
INFORMATIK_GRUPPE = "Gruppe 2"
INFORMATIK_PRAKTIKUM_START = "14:00"

# Physik-Labor: deine festen Termine (Datum -> Versuchsnummer). Beide Blöcke des Tages gelten.
PHYSIK_LABOR = {
    "2026-10-19": 3,
    "2026-11-02": 4,
    "2026-11-16": 6,
    "2026-11-30": 7,
    "2026-12-14": 8,
    "2027-01-11": 1,
}

# Elektrotechnik-Praktikum GET I, Gruppe AB6 (Datum -> Versuch). Beide Blöcke des Tages gelten.
ET_PRAKTIKUM = {
    "2026-10-12": "4/05",
    "2026-11-02": "3/05",
    "2026-11-16": "2/05",
    "2026-11-30": "1/05",
}
ET_VERSUCHE = {
    "1/05": "Oszilloskop",
    "2/05": "Ohmsche Widerstände",
    "3/05": "Leistungsmessung",
    "4/05": "Gleichstromnetzwerke",
}

# Freiwillige Veranstaltungen (werden dezent angezeigt).
FREIWILLIG = {("T", "Physik Praktikumsbericht Tutorium"), ("Ü", "Lernwerkstatt online")}

# Titel, die bei der Einrichtung bekannt waren. Taucht ein anderer Titel auf, wird die
# Veranstaltung trotzdem angezeigt und mit "Neu im Plan, bitte prüfen" markiert.
BEKANNTE_TITEL = {
    ("P", "Bautechnik und Mechanik"), ("P", "Grundlagen Elektrotechnik I EI"),
    ("P", "Grundlagen Informatik"), ("P", "Grundlagen Physik"), ("SV", "Mentoring Program"),
    ("T", "Physik Praktikumsbericht Tutorium"), ("V", "Bautechnik und Mechanik"),
    ("V", "Grundlagen Elektrotechnik I"), ("V", "Grundlagen Informatik"),
    ("V", "Grundlagen Mathematik"), ("V", "Grundlagen Physik"),
    ("Ü", "Bautechnik und Mechanik (MG4)"), ("Ü", "Englisch I"),
    ("Ü", "Grundlagen Elektrotechnik I EI/GT/GPE"), ("Ü", "Grundlagen Mathematik EI/GT/GPE"),
    ("Ü", "Grundlagen Physik EI"), ("Ü", "Lernwerkstatt online"),
}

# Fachfarben: erster Treffer im Titel entscheidet.
FAECHER = [("Physik", "physik"), ("Mathematik", "mathe"), ("Informatik", "info"),
           ("Elektrotechnik", "et"), ("Bautechnik", "bau"), ("Englisch", "englisch")]


def fach_von(titel):
    for wort, fach in FAECHER:
        if wort in titel:
            return fach
    return ""


# Gruppenkürzel am Titelende, die auf der Seite weggelassen werden.
GRUPPEN_SUFFIX = re.compile(r"\s+(?:EI|GT|GPE|WING)(?:/(?:EI|GT|GPE|WING))*$")


def entscheide(ev):
    """Gibt (Art, Titel, Hinweis) zurück oder None, wenn die Veranstaltung ausgeblendet wird.
    Arten: V Vorlesung, U Übung, P Praktikum, T Tutorium, L Lernwerkstatt, X sonstiges."""
    pre, titel, datum = ev["prefix"], ev["title"], ev["date"]
    key = (pre, titel)
    hinweis = ""

    if key == ("T", "Physik Praktikumsbericht Tutorium"):
        return ("T", titel, "") if datum >= TUTORIUM_AB else None
    if key == ("Ü", "Lernwerkstatt online"):
        return ("L", titel, "")
    if key == ("P", "Bautechnik und Mechanik"):
        return ("P", "Bautechnik und Mechanik, Praktikum", "") if datum >= BAUTECHNIK_PRAKTIKUM_AB else None
    if key == ("P", "Grundlagen Physik"):
        if datum not in PHYSIK_LABOR:
            return None
        return ("P", "Grundlagen Physik, Praktikum", "Versuch %s" % PHYSIK_LABOR[datum])
    if key == ("P", "Grundlagen Elektrotechnik I EI"):
        if datum not in ET_PRAKTIKUM:
            return None
        v = ET_PRAKTIKUM[datum]
        return ("P", "Grundlagen Elektrotechnik I, Praktikum", "GET I %s · %s" % (v, ET_VERSUCHE.get(v, "")))
    if key == ("P", "Grundlagen Informatik"):
        if ev["s"] != INFORMATIK_PRAKTIKUM_START:
            return None
        return ("P", "Grundlagen Informatik, Praktikum", INFORMATIK_GRUPPE)
    if pre == "Ü" and titel.startswith("Grundlagen Mathematik") and "Vertiefung" in ev["remark"]:
        return ("W", "Grundlagen Mathematik, Vertiefung", "")
    if key == ("SV", "Mentoring Program"):
        return ("X", "SV Mentoring Program", "")

    if key not in BEKANNTE_TITEL:
        hinweis = "Neu im Plan, bitte prüfen"
    art = {"V": "V", "Ü": "U", "P": "P", "T": "T"}.get(pre, "X")
    return (art, GRUPPEN_SUFFIX.sub("", titel), hinweis)


# ----------------------------------------------------------------------------
# Originalplan einlesen
# ----------------------------------------------------------------------------
def text_of(fragment):
    fragment = re.sub(r"<[^>]+>", "", fragment)
    return re.sub(r"\s+", " ", html.unescape(fragment)).strip()


def parse_plan(src):
    """Liest alle Wochen und Veranstaltungen aus dem sked-HTML."""
    m = re.search(r"Stand:\s*([0-9.]+,\s*[0-9:]+\s*Uhr)", src)
    stand = m.group(1) if m else "unbekannt"

    # Der Plan besteht aus Wochenblöcken, jeder beginnt mit <div class='w1'>.
    parts = re.split(r"<div class=['\"]w1['\"]", src)[1:]
    weeks, raw_events = [], []
    for part in parts:
        h = re.search(r"<div class=['\"]w2['\"]>(.*?)</div>", part, flags=re.S)
        if not h:
            continue
        heading = text_of(h.group(1))
        hm = re.match(r"^(\d+)\. Studienwoche, (\d+)\. KW: .*?(\d{2})\.(\d{2})\.(\d{4})$", heading)
        if not hm:
            raise ValueError("Unbekannte Wochenüberschrift: %r" % heading)
        ende = dt.date(int(hm.group(5)), int(hm.group(4)), int(hm.group(3)))
        start = ende - dt.timedelta(days=6)
        notes = [text_of(x) for x in re.findall(r"class=['\"]fnft['\"][^>]*>(.*?)</td>", part, flags=re.S)]
        weeks.append({"s": start.isoformat(), "nr": int(hm.group(1)), "kw": int(hm.group(2)), "notes": notes})

        for body in re.findall(r"<td [^>]*class=['\"]v['\"][^>]*>(.*?)</td>", part, flags=re.S):
            lines = [text_of(x) for x in re.split(r"<br\s*/?>", body)]
            raw_events.append(parse_cell(lines))
    return stand, weeks, raw_events


def parse_cell(lines):
    tm = re.match(r"^(\d{1,2}):(\d{2}) - (\d{1,2}):(\d{2}) Uhr$", lines[0])
    dm = re.match(r"^(?:Mo|Di|Mi|Do|Fr|Sa|So), (\d{2})\.(\d{2})\.(\d{4})(?: \[(\d+)\])?$", lines[-1])
    if not tm or not dm:
        raise ValueError("Unerwarteter Zellaufbau: %r" % (lines,))
    mitte = lines[1:-1]
    idx = next((i for i, l in enumerate(mitte) if re.match(r"^(?:V|Ü|P|T|SV) \S", l)), None)
    if idx is None:
        raise ValueError("Keine Veranstaltungsart gefunden: %r" % (lines,))
    prefix, titel = mitte[idx].split(" ", 1)
    rest = mitte[idx + 1:]
    remark = ""
    if dm.group(4) and rest:          # eine Fußnote verweist auf die letzte Zeile (Bemerkung)
        remark = rest[-1]
        rest = rest[:-1]
    if len(rest) >= 2:
        lecturer, room = rest[0], ", ".join(rest[1:])
    elif len(rest) == 1:
        lecturer, room = "", rest[0]
    else:
        lecturer, room = "", ""
    return {
        "date": "%s-%s-%s" % (dm.group(3), dm.group(2), dm.group(1)),
        "s": "%02d:%s" % (int(tm.group(1)), tm.group(2)),
        "e": "%02d:%s" % (int(tm.group(3)), tm.group(4)),
        "prefix": prefix, "title": titel, "lecturer": lecturer, "room": room, "remark": remark,
    }


def build_plan(stand, weeks, raw_events):
    order = {"V": 0, "U": 1, "P": 2, "X": 3, "T": 4, "L": 5, "W": 4}
    events = {}
    for ev in raw_events:
        res = entscheide(ev)
        if res is None:
            continue
        art, titel, hinweis = res
        note, warn, lecturer = hinweis, "", ev["lecturer"]
        if ev["remark"]:
            if art == "W":
                pass
            elif art == "L":
                lecturer = ev["remark"]
            elif "!" in ev["remark"]:
                warn = ev["remark"]
            else:
                note = (note + " · " if note else "") + ev["remark"]
        events.setdefault(ev["date"], []).append(
            {"s": ev["s"], "e": ev["e"], "k": art, "t": titel, "r": ev["room"],
             "w": lecturer, "n": note, "x": warn, "f": fach_von(titel)})
    for day in events.values():
        day.sort(key=lambda x: (x["s"], order[x["k"]], x["t"]))
    return {"weeks": weeks, "events": events}


# ----------------------------------------------------------------------------
# Seite erzeugen
# ----------------------------------------------------------------------------
HEAD_PART = r'''<title>Mein Stundenplan GT</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: Kopfzeile mit Wochennavigation, darunter Tagesspalten Mo-Fr (auf dem Handy untereinander).
   Pflichttermine sind gefüllt und farbig nach Art, freiwillige Termine gestrichelt und leise. */
:root {
  --font-display: "Archivo", "Arial Narrow", Arial, sans-serif;
  --font-body: "Archivo", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, Menlo, Consolas, monospace;
  --bg: #0E1312; --surface: #161C1B; --ink: #E6ECEA; --muted: #9AA8A3; --line: #2B3633;
  --accent: #7FC8B4; --on-accent: #0E1312; --dashed: #44524D; --alert: #FF8F86;
  --on-k: #0E1312;
  color-scheme: dark;
}
[data-f="physik"]   { --k: #AEB7C0; --kbg: #272D32; }
[data-f="mathe"]    { --k: #6FD1A0; --kbg: #163A2C; }
[data-f="info"]     { --k: #8AD0F5; --kbg: #15354B; }
[data-f="et"]       { --k: #D9B65C; --kbg: #382E12; }
[data-f="bau"]      { --k: #D99A82; --kbg: #3D241B; }
[data-f="englisch"] { --k: #D79AB3; --kbg: #3E2230; }

* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 15px/1.45 var(--font-body);
}
.wrap {
  max-width: 1240px;
  margin: 0 auto;
  padding-inline: 16px;
  padding-block: 22px 40px;
}

.top { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: 12px 24px; }
.eyebrow { margin: 0 0 4px; font-size: 12px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
h1 { margin: 0; font: 800 clamp(28px, 6vw, 40px)/1.05 var(--font-display); letter-spacing: -.02em; text-wrap: balance; }
.toggle { display: inline-flex; align-items: center; gap: 8px; font-size: 14px; color: var(--muted); cursor: pointer; }
.toggle input { width: 18px; height: 18px; accent-color: var(--accent); }

.weeknav { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-block: 18px 6px; }
.btn {
  font: 600 14px/1 var(--font-body);
  min-width: 44px; min-height: 40px; padding: 0 14px;
  color: var(--ink); background: var(--surface);
  border: 1px solid var(--line); border-radius: 4px; cursor: pointer;
}
.btn:hover:not(:disabled) { border-color: var(--accent); }
.btn:disabled { opacity: .4; cursor: default; }
.btn.primary { background: var(--accent); border-color: var(--accent); color: var(--on-accent); }
.btn:focus-visible, .toggle input:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.weeklabel { display: flex; flex-direction: column; min-width: 0; padding-inline: 6px; flex: 1 1 200px; }
.weeklabel strong { font-size: 18px; font-weight: 700; }
.weeklabel span { font: 400 13px var(--font-mono); color: var(--muted); }
.weeknote { margin: 4px 0 0; font-size: 13px; color: var(--muted); }

.days { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); gap: 12px; margin-top: 14px; }
@media (min-width: 1100px) { .days { grid-template-columns: repeat(5, minmax(0, 1fr)); } }
.day { background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 10px; display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.day.is-today { border-color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent); }
.dayhead { display: flex; align-items: baseline; gap: 8px; padding-bottom: 6px; border-bottom: 1px solid var(--line); }
.dname { font: 800 18px var(--font-display); letter-spacing: -.01em; }
.ddate { font: 400 13px var(--font-mono); color: var(--muted); }
.badge { margin-left: auto; font-size: 11px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; background: var(--accent); color: var(--on-accent); padding: 2px 7px; border-radius: 3px; }
.free { margin: 6px 0; color: var(--muted); font-size: 14px; }

.ev { display: grid; gap: 3px; min-width: 0; padding: 9px 10px; border-radius: 4px; }
.ev[data-k="X"] { --k: var(--muted); --kbg: var(--surface); }
.ev.must { background: color-mix(in srgb, var(--kbg) 55%, var(--surface)); border: 1.5px solid transparent; }
.ev[data-k="U"] .chip { background: transparent; color: var(--k); box-shadow: inset 0 0 0 1.5px var(--k); }
.ev[data-k="P"] { border-color: color-mix(in srgb, var(--k) 42%, transparent); }
.ev[data-k="P"] .chip { border-radius: 50%; }
.ev.neutral { border: 1px solid var(--line); }
.ev .row { display: flex; align-items: center; gap: 8px; min-width: 0; }
.chip { flex: none; width: 22px; height: 22px; display: inline-grid; place-items: center; border-radius: 3px; font-size: 12px; font-weight: 800; font-style: normal; background: var(--k); color: var(--on-k); }
.time { font: 500 12.5px var(--font-mono); font-variant-numeric: tabular-nums; }
.title { font-weight: 700; overflow-wrap: anywhere; }
.meta { font-size: 13px; color: var(--muted); overflow-wrap: anywhere; }
.ev.must .meta { color: color-mix(in srgb, var(--ink) 70%, transparent); }
.note { font-size: 12.5px; font-weight: 600; color: var(--k); }
.warn { font-size: 12.5px; font-weight: 700; color: var(--alert); }

.ev.vol { border: 1px dashed var(--dashed); padding: 6px 10px; color: var(--muted); }
.ev.vol[data-f] { border-color: color-mix(in srgb, var(--k) 60%, transparent); background: color-mix(in srgb, var(--kbg) 45%, var(--surface)); }
.ev.vol[data-f] .tag, .ev.vol[data-f] .title { color: var(--k); }
.toggles { display: grid; gap: 6px; justify-items: end; }
.gap { display: grid; gap: 2px; padding: 5px 10px; border-radius: 4px; color: var(--muted); border-left: 2px solid var(--line); margin: 1px 0 1px 6px; }
.gap .gl { font: 600 11px var(--font-mono); letter-spacing: .06em; text-transform: uppercase; }
.gap .gt { font-size: 12.5px; }
.gap.live { border-left-color: var(--accent); color: var(--ink); }
.gap.live .gl { color: var(--accent); }
.gap.past { opacity: .5; }
.ev.past { opacity: .5; }
.ev.live { box-shadow: 0 0 0 1.5px var(--k, var(--accent)); }
.prog { display: grid; gap: 4px; margin-top: 6px; }
.prog > i { display: block; height: 5px; border-radius: 3px; background: var(--k, var(--accent)); }
.prog { grid-template-columns: 1fr; }
.prog::before { content: ""; grid-area: 1 / 1; height: 5px; border-radius: 3px; background: color-mix(in srgb, var(--k, var(--accent)) 22%, transparent); }
.prog > i { grid-area: 1 / 1; }
.prog > span { font-size: 12px; font-weight: 600; color: var(--k, var(--accent)); font-family: var(--font-mono); }
.nowline { display: flex; align-items: center; gap: 8px; font: 600 11px var(--font-mono); color: var(--alert); }
.nowline::before, .nowline::after { content: ""; height: 1.5px; background: var(--alert); flex: 1; opacity: .8; }
.nowline::after { flex: 3; }
.ev.vol .title { font-weight: 500; font-size: 13.5px; }
.ev.vol .time { font-size: 12px; }
.ev.vol .tag { margin-left: auto; font-size: 11px; letter-spacing: .05em; text-transform: uppercase; }

.legend { display: flex; flex-wrap: wrap; gap: 8px 18px; margin-top: 22px; font-size: 13px; color: var(--muted); }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.legend .chip { width: 20px; height: 20px; font-size: 11px; }
.legend .sw { width: 14px; height: 14px; border-radius: 3px; background: var(--k); }
.legend .dash { width: 20px; height: 20px; border: 1px dashed var(--dashed); border-radius: 3px; }
.foot { margin-top: 18px; font-size: 13px; color: var(--muted); max-width: 70ch; }
.foot a { color: var(--accent); }
@media (prefers-reduced-motion: no-preference) { .btn { transition: border-color .12s; } }
</style>
'''

BODY_PART = r'''<div class="wrap">
  <header class="top">
    <div>
      <p class="eyebrow">Green Technology B.Eng. · 1. Semester · Gruppe GT</p>
      <h1>Mein Stundenplan</h1>
    </div>
    <div class="toggles">
      <label class="toggle"><input type="checkbox" id="vol" checked> Freiwillige Termine anzeigen</label>
      <label class="toggle"><input type="checkbox" id="gap" checked> Pausen anzeigen</label>
    </div>
  </header>

  <nav class="weeknav" aria-label="Woche wählen">
    <button class="btn" id="prev" type="button" aria-label="Vorherige Woche">&#8249;</button>
    <div class="weeklabel" aria-live="polite"><strong id="wk"></strong><span id="wrange"></span></div>
    <button class="btn" id="next" type="button" aria-label="Nächste Woche">&#8250;</button>
    <button class="btn primary" id="today" type="button">Heute</button>
  </nav>
  <p class="weeknote" id="wnote" hidden></p>

  <main class="days" id="days"></main>

  <section class="legend" aria-label="Fächer">
    <span><i class="sw" data-f="physik"></i> Physik</span>
    <span><i class="sw" data-f="mathe"></i> Mathematik</span>
    <span><i class="sw" data-f="info"></i> Informatik</span>
    <span><i class="sw" data-f="et"></i> Elektrotechnik</span>
    <span><i class="sw" data-f="bau"></i> Bautechnik und Mechanik</span>
    <span><i class="sw" data-f="englisch"></i> Englisch</span>
  </section>
  <section class="legend" aria-label="Terminarten">
    <span><i class="chip" style="--k:var(--muted)">V</i> Vorlesung (gefüllt)</span>
    <span><i class="chip" data-k="U" style="--k:var(--muted);background:transparent;color:var(--muted);box-shadow:inset 0 0 0 1.5px var(--muted)">Ü</i> Übung (Ring)</span>
    <span><i class="chip" style="--k:var(--muted);border-radius:50%">P</i> Praktikum (rund, mit Rahmen)</span>
    <span><i class="dash"></i> Freiwillig (Tutorium, Lernwerkstatt, Vertiefung)</span>
  </section>

  <p class="foot">
    Stand des Originalplans: __STAND__. Diese Seite wurde am __BUILT__ aus dem Originalplan erzeugt.
    Alle Angaben ohne Gewähr, maßgeblich ist der
    <a href="__SOURCE_URL__" target="_blank" rel="noopener">Originalplan</a>.
  </p>
</div>

<script>
var PLAN = __PLAN_JSON__;
(function () {
  var DAY = 86400000;
  var WEEKS = PLAN.weeks;
  var DNAMES = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"];
  var CHIP = { V: "V", U: "Ü", P: "P", X: "M", T: "T", L: "L", W: "W" };
  var VOLTAG = { T: "Tutorium", L: "Lernwerkstatt", W: "Vertiefung" };

  function parse(iso) { var p = iso.split("-"); return Date.UTC(+p[0], +p[1] - 1, +p[2]); }
  function pad(n) { return ("0" + n).slice(-2); }
  function isoOf(ms) { var d = new Date(ms); return d.getUTCFullYear() + "-" + pad(d.getUTCMonth() + 1) + "-" + pad(d.getUTCDate()); }
  function dm(ms) { var d = new Date(ms); return pad(d.getUTCDate()) + "." + pad(d.getUTCMonth() + 1) + "."; }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text) n.textContent = text;
    return n;
  }
  function defaultIdx(todayMs) {
    var ref = todayMs, wd = (new Date(ref).getUTCDay() + 6) % 7;
    if (wd >= 5) ref += (7 - wd) * DAY;
    for (var i = 0; i < WEEKS.length; i++) {
      var s = parse(WEEKS[i].s);
      if (ref >= s && ref < s + 7 * DAY) return i;
    }
    for (var j = 0; j < WEEKS.length; j++) { if (parse(WEEKS[j].s) > ref) return j; }
    return WEEKS.length - 1;
  }

  // Zum Testen: ?jetzt=2026-10-14T10:30 setzt eine feste Uhrzeit.
  function getNow() {
    try {
      var q = new URLSearchParams(location.search).get("jetzt");
      if (q) { var t = new Date(q); if (!isNaN(t)) return t; }
    } catch (e) {}
    return new Date();
  }
  function dayOf(d) { return Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()); }
  var todayMs = dayOf(getNow());
  var idx = WEEKS.length ? defaultIdx(todayMs) : 0;
  var showVol = true;
  try { showVol = localStorage.getItem("sp-vol") !== "0"; } catch (e) {}
  var $ = function (id) { return document.getElementById(id); };
  var volBox = $("vol");
  volBox.checked = showVol;
  var showGap = true;
  try { showGap = localStorage.getItem("sp-gap") !== "0"; } catch (e) {}
  var gapBox = $("gap");
  gapBox.checked = showGap;

  function renderEvent(ev) {
    var vol = ev.k === "T" || ev.k === "L" || ev.k === "W";
    var n = el("article", "ev " + (vol ? "vol" : ev.k === "X" ? "neutral" : "must"));
    n.setAttribute("data-k", ev.k);
    if (ev.f && (!vol || ev.k === "W")) n.setAttribute("data-f", ev.f);
    n.setAttribute("data-s", ev.s);
    n.setAttribute("data-e", ev.e);
    var row = el("div", "row");
    if (!vol) row.appendChild(el("span", "chip", CHIP[ev.k]));
    row.appendChild(el("span", "time", ev.s + "–" + ev.e));
    if (vol) row.appendChild(el("span", "tag", VOLTAG[ev.k]));
    n.appendChild(row);
    n.appendChild(el("div", "title", ev.t));
    var meta = [ev.r, ev.w].filter(Boolean).join(" · ");
    if (meta) n.appendChild(el("div", "meta", meta));
    if (ev.n) n.appendChild(el("div", "note", ev.n));
    if (ev.x) n.appendChild(el("div", "warn", ev.x));
    return n;
  }

  function hhmm(m) { return pad(Math.floor(m / 60)) + ":" + pad(m % 60); }
  function dauer(m) {
    var h = Math.floor(m / 60), r = m % 60;
    return h ? h + " Std." + (r ? " " + r + " Min." : "") : r + " Min.";
  }
  function renderGap(a, b) {
    var g = el("div", "gap");
    g.setAttribute("data-s", hhmm(a));
    g.setAttribute("data-e", hhmm(b));
    g.appendChild(el("span", "gl", "Pause"));
    g.appendChild(el("span", "gt", hhmm(a) + "–" + hhmm(b) + " · " + dauer(b - a)));
    return g;
  }

  function render() {
    var box = $("days");
    box.textContent = "";
    if (!WEEKS.length) { $("wk").textContent = "Keine Wochen im Plan"; return; }
    var w = WEEKS[idx], start = parse(w.s);
    $("wk").textContent = w.nr + ". Studienwoche · KW " + w.kw;
    $("wrange").textContent = dm(start) + " – " + dm(start + 6 * DAY) + new Date(start + 6 * DAY).getUTCFullYear();
    $("prev").disabled = idx === 0;
    $("next").disabled = idx === WEEKS.length - 1;

    var notes = [];
    (w.notes || []).forEach(function (t) { notes.push("Hinweis im Plan: " + t + "."); });
    if (idx > 0) {
      var prevEnd = parse(WEEKS[idx - 1].s) + 7 * DAY;
      if (start > prevEnd) notes.push("Davor: vom " + dm(prevEnd) + " bis " + dm(start - DAY) + " enthält der Plan keine Termine.");
    }
    var wn = $("wnote");
    wn.hidden = notes.length === 0;
    wn.textContent = notes.join(" ");

    for (var d = 0; d < 5; d++) {
      var ms = start + d * DAY, iso = isoOf(ms);
      var col = el("section", "day" + (ms === todayMs ? " is-today" : ""));
      var head = el("div", "dayhead");
      head.appendChild(el("span", "dname", DNAMES[d]));
      head.appendChild(el("span", "ddate", dm(ms)));
      if (ms === todayMs) head.appendChild(el("span", "badge", "Heute"));
      col.appendChild(head);
      var evs = (PLAN.events[iso] || []).filter(function (ev) { return showVol || (ev.k !== "T" && ev.k !== "L" && ev.k !== "W"); });
      if (!evs.length) col.appendChild(el("p", "free", "Keine Termine"));
      var maxEnd = null;
      evs.forEach(function (ev) {
        var s = mins(ev.s), e = mins(ev.e);
        if (showGap && maxEnd !== null && s - maxEnd >= 30) col.appendChild(renderGap(maxEnd, s));
        col.appendChild(renderEvent(ev));
        if (maxEnd === null || e > maxEnd) maxEnd = e;
      });
      box.appendChild(col);
    }
  }

  function mins(hhmm) { var a = hhmm.split(":"); return +a[0] * 60 + +a[1]; }

  // Zeigt in der Spalte von heute, wo der Tag gerade steht: Vergangenes blasser,
  // laufende Veranstaltung mit Fortschrittsbalken und Restzeit, sonst eine "Jetzt"-Linie.
  function tick() {
    var nw = getNow();
    var t = dayOf(nw);
    if (t !== todayMs) { todayMs = t; render(); return; }
    var old = document.querySelectorAll(".nowline, .prog");
    for (var i = 0; i < old.length; i++) old[i].parentNode.removeChild(old[i]);
    var col = document.querySelector(".day.is-today");
    if (!col) return;
    var nowMin = nw.getHours() * 60 + nw.getMinutes() + nw.getSeconds() / 60;
    var cards = col.querySelectorAll(".ev, .gap");
    var running = false, anchor = null, gapNow = null;
    for (var j = 0; j < cards.length; j++) {
      var c = cards[j], s = mins(c.getAttribute("data-s")), e = mins(c.getAttribute("data-e"));
      var isGap = c.classList.contains("gap");
      c.classList.remove("past", "live");
      if (nowMin >= e) { c.classList.add("past"); continue; }
      if (isGap) {
        if (nowMin >= s) {
          gapNow = c;
          c.classList.add("live");
          var gl = Math.max(1, Math.ceil(e - nowMin));
          var gp = el("div", "prog");
          var gb = el("i"); gb.style.width = Math.min(100, Math.max(0, (nowMin - s) / (e - s) * 100)) + "%";
          gp.appendChild(gb);
          gp.appendChild(el("span", "", gl >= 60 ? "noch " + Math.floor(gl / 60) + " Std. " + (gl % 60) + " Min." : "noch " + gl + " Min."));
          c.appendChild(gp);
        }
        continue;
      }
      if (nowMin >= s) {
        running = true;
        c.classList.add("live");
        var left = Math.max(1, Math.ceil(e - nowMin));
        var pr = el("div", "prog");
        var bar = el("i"); bar.style.width = Math.min(100, Math.max(0, (nowMin - s) / (e - s) * 100)) + "%";
        pr.appendChild(bar);
        var lab = el("span", "", left >= 60 ? "noch " + Math.floor(left / 60) + " Std. " + (left % 60) + " Min." : "noch " + left + " Min.");
        pr.appendChild(lab);
        c.appendChild(pr);
      } else if (!anchor) anchor = c;
    }
    if (!running && !gapNow && cards.length) {
      var line = el("div", "nowline", "Jetzt " + pad(nw.getHours()) + ":" + pad(nw.getMinutes()));
      if (anchor) col.insertBefore(line, anchor);
      else col.appendChild(line);
    }
  }

  gapBox.addEventListener("change", function () {
    showGap = gapBox.checked;
    try { localStorage.setItem("sp-gap", showGap ? "1" : "0"); } catch (e) {}
    render();
  });
  $("prev").addEventListener("click", function () { if (idx > 0) { idx--; render(); } });
  $("next").addEventListener("click", function () { if (idx < WEEKS.length - 1) { idx++; render(); } });
  $("today").addEventListener("click", function () { idx = defaultIdx(todayMs); render(); });
  volBox.addEventListener("change", function () {
    showVol = volBox.checked;
    try { localStorage.setItem("sp-vol", showVol ? "1" : "0"); } catch (e) {}
    render();
  });
  var _render = render;
  render = function () { _render(); tick(); };
  render();
  setInterval(tick, 30000);
})();
</script>
'''


def render_page(plan, stand, standalone=True):
    built = dt.datetime.now(ZoneInfo("Europe/Berlin")).strftime("%d.%m.%Y, %H:%M Uhr")
    data = json.dumps(plan, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    body = (BODY_PART.replace("__PLAN_JSON__", data).replace("__STAND__", html.escape(stand))
            .replace("__BUILT__", built).replace("__SOURCE_URL__", SOURCE_URL))
    if standalone:
        return ('<!doctype html>\n<html lang="de">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                + HEAD_PART + '</head>\n<body>\n' + body + '</body>\n</html>\n')
    return HEAD_PART + body


def load_source(args):
    if "--file" in args:
        with open(args[args.index("--file") + 1], encoding="utf-8") as f:
            return f.read()
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "Mozilla/5.0 (Stundenplan-Build)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


def main():
    args = sys.argv[1:]
    out = args[args.index("--out") + 1] if "--out" in args else "index.html"
    try:
        src = load_source(args)
        stand, weeks, raw = parse_plan(src)
        if not weeks or len(raw) < 50:
            raise ValueError("Zu wenige Daten gefunden (%d Wochen, %d Veranstaltungen). "
                             "Hat sich der Aufbau des Originalplans geändert?" % (len(weeks), len(raw)))
        plan = build_plan(stand, weeks, raw)
    except Exception as e:  # bewusst breit: jede Störung bricht ab, index.html bleibt unverändert
        sys.exit("FEHLER: %s" % e)

    n = sum(len(v) for v in plan["events"].values())
    with open(out, "w", encoding="utf-8") as f:
        f.write(render_page(plan, stand))
    if "--artifact" in args:
        with open(args[args.index("--artifact") + 1], "w", encoding="utf-8") as f:
            f.write(render_page(plan, stand, standalone=False))
    print("Fertig: %d Wochen, %d Veranstaltungen im Original, %d davon in deinem Plan (Stand %s)."
          % (len(weeks), len(raw), n, stand))


if __name__ == "__main__":
    main()
