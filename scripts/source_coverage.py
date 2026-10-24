"""Daten-Abdeckungs-Wächter (Easy-Entscheid 24.10.2026, Automatisierung von
Datenfehler-Erkennung, Auftrag 1 von 6).

Persistiert je Lauf und externer Datenquelle drei Zahlen: ERWARTET /
BEANTWORTET / MIT DATEN (nicht leer). Schließt die gefährlichste Lücke der
bestehenden Wächter (``health_check.py``, ``proactive_watcher.py``): eine
Antwort OHNE Fehler, aber LEER — yfinance liefert für viele/alle Ticker
leere Frames ohne Exception, die KI liefert leere Kommentare ohne Fehler.
Beides wird heute nur EINZELLAUF-weise sichtbar (``reason_counts.empty_data``
bzw. ``check_agent_comments``); eine Quelle, die über mehrere Läufe hinweg
durchgängig 0 Daten liefert, fällt bisher nirgends zusammengefasst auf.

REIN ADDITIV: keine Score-/Ranking-/Filter-/Sammlungs-Wirkung, kein Eingriff
in bestehende Dateien außer der eigenen (``data/source_coverage.json``).
``health_check.py`` importiert dieses Modul (nicht umgekehrt) — dieses Modul
bleibt ein abhängigkeitsfreies Blatt wie ``numeric.py``/``zigzag.py``.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Dict, List, Tuple

import repo_path  # noqa: F401 — legt Repo-Root + scripts/ auf sys.path
import config  # noqa: E402

REPO_ROOT = repo_path.REPO_ROOT

COVERAGE_PATH = "data/source_coverage.json"
SCHEMA_VERSION = 1

# Ringpuffer: genug Läufe, um das längste Fenster (7 Tage * 2 Läufe/Tag = 14
# Einträge) komfortabel zu überdecken, ohne die Datei unbegrenzt wachsen zu
# lassen — großzügig bemessen (500 Einträge ≈ 250 Tage bei 2 Läufen/Tag).
RING_MAX = getattr(config, "SOURCE_COVERAGE_RING_MAX", 500)

# Fenster je Quelle. Kurse (US/DE) laufen an jedem Handelstag praktisch IMMER
# — ein Ausfall soll binnen 24 h auffallen. Die KI-Kommentare hängen vom
# gesetzten Secret/Tagesbudget ab, ein leerer Tag ist dort normaler — dafür
# das großzügigere 7-Tage-Fenster. Eine Quelle ohne Eintrag in BEIDEN Dicts
# bekommt den Default (24 h) — "praktisch immer liefern" ist die sicherere
# Annahme für eine neue, noch nicht eingeordnete Quelle.
WINDOW_HOURS: Dict[str, int] = dict(getattr(
    config, "SOURCE_COVERAGE_WINDOW_HOURS", {"kurse_us": 24, "kurse_de": 24}))
WINDOW_DAYS: Dict[str, int] = dict(getattr(
    config, "SOURCE_COVERAGE_WINDOW_DAYS", {"ki_kommentare": 7}))
DEFAULT_WINDOW_HOURS = 24

# Bekannt tote, BEWUSST nicht reparierte Quellen: Digest-Zeile "ℹ️ bekannt
# tot" statt "⚠️" — gekoppelt über diese Konstante, mit Verweis auf den
# offenen Punkt in SESSION_HANDOVER.md, der die Entscheidung dokumentiert
# (Name der Quelle dort eintragen, WENN eine Quelle hier eingetragen wird).
# AKTUELL LEER: keine der drei Quellen (kurse_us, kurse_de, ki_kommentare)
# ist bewusst stillgelegt — eine Quelle OHNE Eintrag hier bleibt immer "⚠️".
KNOWN_DEAD_SOURCES: Tuple[str, ...] = ()


def _leer() -> Dict:
    return {"schema_version": SCHEMA_VERSION, "entries": []}


def load_coverage() -> Dict:
    """Fail-soft: fehlende/kaputte Datei -> leere Struktur, kein Absturz
    (identisches Prinzip wie ``forward_collection.load_collection``)."""
    try:
        path = REPO_ROOT / COVERAGE_PATH
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict) or "entries" not in data:
            return _leer()
        return data
    except Exception:  # noqa: BLE001 — fail-soft
        return _leer()


def write_coverage(state: Dict) -> Path:
    """Schreibt NUR diese eine Datei — kein Spiegel nach docs/ (die Datei
    wird vom Frontend nicht gelesen, rein backend-intern für health_check)."""
    path = REPO_ROOT / COVERAGE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    return path


def _entry_key(run_date: str, run_hour: int, workflow: str) -> str:
    return f"{run_date}T{run_hour:02d}|{workflow}"


def upsert_entry(state: Dict, run_date: str, run_hour: int, workflow: str,
                 now_iso: str,
                 sources: Dict[str, Tuple[int, int, int]]) -> Dict:
    """Fügt einen Lauf-Eintrag hinzu oder ÜBERSCHREIBT den bestehenden mit
    demselben Idempotenz-Schlüssel (Datum + STUNDE + Workflow) — zwei
    Schreibversuche derselben Stunde ergeben EINEN Eintrag, kein Duplikat.
    Die Stunde ist Teil des Schlüssels, weil mehr als ein Lauf pro Tag
    existiert (``daily.yml`` abends, ``midday_report_refresh.yml`` mittags) —
    ohne sie würden beide Läufe eines Tages denselben Eintrag überschreiben.

    ``sources``: {name: (erwartet, beantwortet, mit_daten)}. Trimmt danach
    auf die letzten ``RING_MAX`` Einträge (chronologisch älteste zuerst
    entfernt). Reine Funktion — der Aufrufer lädt/schreibt die Datei."""
    key = _entry_key(run_date, run_hour, workflow)
    entries = [e for e in state.get("entries", []) if e.get("key") != key]
    neu = {
        "key": key, "run_date": run_date, "run_hour": run_hour,
        "workflow": workflow, "recorded_utc": now_iso,
        "sources": {name: {"erwartet": int(e), "beantwortet": int(b),
                           "mit_daten": int(d)}
                   for name, (e, b, d) in sources.items()},
    }
    entries.append(neu)
    entries.sort(key=lambda e: (e["run_date"], e["run_hour"], e["workflow"]))
    if len(entries) > RING_MAX:
        entries = entries[-RING_MAX:]
    return {"schema_version": SCHEMA_VERSION, "entries": entries}


def _window_cutoff(quelle: str, jetzt: _dt.datetime) -> _dt.datetime:
    if quelle in WINDOW_HOURS:
        return jetzt - _dt.timedelta(hours=WINDOW_HOURS[quelle])
    if quelle in WINDOW_DAYS:
        return jetzt - _dt.timedelta(days=WINDOW_DAYS[quelle])
    return jetzt - _dt.timedelta(hours=DEFAULT_WINDOW_HOURS)


def _fenster_text(quelle: str) -> str:
    if quelle in WINDOW_HOURS:
        return f"{WINDOW_HOURS[quelle]} h"
    if quelle in WINDOW_DAYS:
        return f"{WINDOW_DAYS[quelle]} Tage"
    return f"{DEFAULT_WINDOW_HOURS} h"


def silent_source_findings(state: Dict, jetzt: _dt.datetime) -> List[Dict]:
    """Quellen, die INNERHALB ihres Fensters in JEDEM dort erfassten Lauf 0
    Daten lieferten, obwohl mindestens einmal Daten erwartet wurden — die
    stillste Ausfallklasse (Antwort ohne Fehler, aber leer). Ein einzelner
    leerer Lauf unter mehreren genügt NICHT (die Summe über alle Läufe im
    Fenster entscheidet, nicht ein einzelner).

    Grenzfall per Konstruktion EINGESCHLOSSEN (``<``, nicht ``<=`` als
    Ausschluss-Operator): ein Lauf exakt am Fensterrand zählt noch mit.

    Liefert Finding-Dicts im Format von ``health_check._finding``
    (rule/severity/market/message/detail) — bewusst hier als Literal
    dupliziert statt importiert, damit dieses Modul ein abhängigkeitsfreies
    Blatt bleibt (``health_check.py`` importiert dieses Modul, nicht
    umgekehrt — sonst Zirkelimport-Risiko wie bei
    ``forward_collection``/``elliott_pipeline``)."""
    summen: Dict[str, List[int]] = {}  # name -> [erwartet_summe, mit_daten_summe]
    for e in state.get("entries", []):
        try:
            recorded = _dt.datetime.fromisoformat(
                str(e.get("recorded_utc", "")).replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            continue
        for name, zahlen in (e.get("sources") or {}).items():
            if not isinstance(zahlen, dict):
                continue
            cutoff = _window_cutoff(name, jetzt)
            if recorded < cutoff or recorded > jetzt:
                continue
            erw = int(zahlen.get("erwartet", 0) or 0)
            mit = int(zahlen.get("mit_daten", 0) or 0)
            paar = summen.setdefault(name, [0, 0])
            paar[0] += erw
            paar[1] += mit

    befunde: List[Dict] = []
    for name, (erw_summe, mit_summe) in sorted(summen.items()):
        if erw_summe <= 0 or mit_summe > 0:
            continue
        bekannt_tot = name in KNOWN_DEAD_SOURCES
        icon = "ℹ️ bekannt tot" if bekannt_tot else "⚠️"
        befunde.append({
            "rule": "source_coverage_silent",
            "severity": "info" if bekannt_tot else "warn",
            "market": None,
            "message": (f"{icon}: Quelle '{name}' lieferte in ALLEN Läufen "
                       f"der letzten {_fenster_text(name)} 0 Daten "
                       f"(erwartet {erw_summe}, keine Antwort mit Daten)."),
            "detail": {"source": name, "erwartet": erw_summe,
                      "mit_daten": mit_summe, "bekannt_tot": bekannt_tot},
        })
    return befunde
