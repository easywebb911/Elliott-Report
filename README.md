# Elliott-Report

Tägliche **Top-5-Elliott-Wellen-Kandidaten je Markt** (USA + Deutschland) als
GitHub-Pages-PWA. Der Report ist eine **heuristische, unvalidierte**
Wellen-Auszählung — **keine Anlageberatung, keine Wahrscheinlichkeitsaussage.**

> Status: **Skelett / Grundgerüst.** Pipeline läuft end-to-end, Frontend zeigt
> Karten, Tests grün. Forward-Ergebnis-Sammlung, Kalibrierung und
> Wahrscheinlichkeits-Anzeige sind bewusst **noch nicht** enthalten.

## Struktur

```
config.py                     # Universum (US/DE) + alle Parameter zentral
scripts/
  elliott_pipeline.py         # Pipeline: Daten → ZigZag → Regeln → Score → JSON
  zigzag.py                   # Pivot-Engine (symmetrisches Fenster, alternierend)
  rules.py                    # 3 harte Elliott-Regeln als K.o.-Validator
data/report.json              # kanonischer Output (vom Workflow committet)
docs/                         # GitHub-Pages-Root (Settings → Pages → main /docs)
  index.html                  # minimale, dunkle PWA
  manifest.webmanifest        # PWA-Manifest (kein Service Worker — iOS-Lesson)
  icon.svg
  data/report.json            # gespiegelter Report (siehe Pfad-Hinweis unten)
tests/                        # pytest: ZigZag, Regeln, JSON-Schema, Determinismus
.github/workflows/daily.yml   # Cron 21:45 UTC + manueller Tap-Start
requirements.txt              # Versions-Ranges (keine harten Pins)
```

## Pipeline (deterministisch, fail-soft)

1. **Universum** aus `config.py` — statische Startlisten (US ~50 liquide
   Large/Mid Caps, DE = DAX+MDAX mit `.DE`-Suffix). Kein Scraping.
2. **Kursdaten** via yfinance (2 J. Tageskerzen). Ticker ohne Daten werden
   übersprungen und gezählt (fail-soft).
3. **ZigZag** — bestätigte, alternierende Pivots (Fenster `ZIGZAG_WINDOW`,
   Default **5**).
4. **Regel-Validator** — die drei harten Regeln als K.o.:
   W2-Retracement ≤ 100 % · W3 nie die kürzeste von 1/3/5 · W4 überlappt W1
   nicht.
5. **Score** (`score_heuristic`, v0, **HEURISTISCH**) = Setup-Basis
   (Ende W2/W4) + Fibonacci-Nähe (weicher Bonus) + Abstand zum
   Invalidierungslevel. **Keine** Wahrscheinlichkeits-Sprache.
6. **Output** `data/report.json` (+ Spiegel nach `docs/data/`).

### Lokal ausführen

```bash
pip install -r requirements.txt
python scripts/elliott_pipeline.py            # echte Kursdaten (yfinance)

# Offline-/Dev-Demo ohne Netz (deterministischer synthetischer Kurs-Generator):
ELLIOTT_OFFLINE=1 python scripts/elliott_pipeline.py
```

### Tests

```bash
pip install -r requirements.txt
python -m pytest -q
```

## Frontend / GitHub Pages

> **Einmalig nach dem Merge von Easy zu aktivieren:**
> **Settings → Pages → Source: `Deploy from a branch` → Branch `main` `/docs`.**
> Ohne diesen Schritt ist die PWA nicht erreichbar.

**Pfad-Hinweis (wichtiger, bewusst gelöster Widerspruch):** GitHub Pages wird
aus `/docs` bedient. Dateien **außerhalb** `/docs` — also das kanonische
`data/report.json` im Repo-Root — sind über Pages **nicht** erreichbar. Deshalb
schreibt die Pipeline den Report zusätzlich nach `docs/data/report.json`, und
das Frontend probiert mehrere Pfade (`data/report.json` zuerst, dann
`../data/report.json`). So funktioniert sowohl die Live-Seite als auch die
lokale Vorschau. (Dieser Widerspruch wurde nicht still umgebogen, sondern
explizit über die Spiegelung gelöst.)

Das Frontend zeigt zwei Sektionen (USA / Deutschland) mit je bis zu 5 Karten,
ein **Staleness-Banner**, wenn der Report älter als 30 h ist, und auf jeder
Karte den Status **„heuristisch · unvalidiert“**. **Kein Service Worker**
(bewusst, wegen iOS-Caching-Problemen).

## Automatisierung

`.github/workflows/daily.yml` läuft täglich **21:45 UTC** (nach US-Close) und
zusätzlich manuell (`workflow_dispatch`). Er baut den Report, validiert das
JSON und committet Änderungen auf `main` (fail-soft: ein fehlerhafter Lauf
committet nichts).

## Rückweg (Revert)

Ein **kompletter PR-Revert genügt.** Es gibt keine Daten-Migration und kein
Schema in einer externen DB — `data/report.json` ist die einzige
Zustandsdatei und wird bei jedem Lauf neu geschrieben. Revert des PR entfernt
Pipeline, Frontend und Workflow vollständig; das Repo fällt auf den Zustand
davor zurück.

## Bewusst (noch) NICHT enthalten

Forward-Ergebnis-Sammlung · Kalibrierung · Intraday · Push ·
Wahrscheinlichkeits-Anzeige. Kommt in späteren Schritten.
