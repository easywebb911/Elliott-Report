"""Wiedervorlagen im Digest (Easy-Entscheid 25.10.2026, Automatisierung von
Datenfehler-Erkennung, Auftrag 2 von 6).

Ziel: kein Termin hängt mehr an Easys Erinnerung. Ein eigener, maschinen-
lesbarer Block in ``SESSION_HANDOVER.md`` (zwischen ``MARKER_START``/
``MARKER_ENDE``) trägt die Termine; dieses Modul liest ihn fail-soft und
meldet, was am Lauftag fällig oder überfällig ist. ``health_check.py``
importiert dieses Modul (nicht umgekehrt) — ein abhängigkeitsfreies Blatt wie
``source_coverage.py``/``numeric.py``.

TAGESGRENZE: Europe/Berlin, nicht UTC — ein Lauf um 22:45 UTC ist in Berlin
(Sommerzeit +2h, Winterzeit +1h) oft schon der NÄCHSTE Kalendertag. Die
Zeitzonenwahl ist bewusst: SESSION_HANDOVER.md wird von einem Menschen in
Deutschland gepflegt, Fälligkeitstage sind Berliner Kalendertage.

FAIL-SOFT: ein unlesbarer Block, eine unlesbare Zeile oder ein doppelt
definierter Block dürfen ``health_check`` NIE abbrechen — sie erzeugen
höchstens ein zusätzliches, informatives Finding.
"""
from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import repo_path  # noqa: F401 — legt Repo-Root + scripts/ auf sys.path

REPO_ROOT = repo_path.REPO_ROOT

HANDOVER_PATH = "SESSION_HANDOVER.md"
BERLIN = ZoneInfo("Europe/Berlin")

MARKER_START = "<!-- WIEDERVORLAGEN-START -->"
MARKER_ENDE = "<!-- WIEDERVORLAGEN-ENDE -->"

# Eine Zeile: "- faellig_am: 2026-12-07 | status: offen | titel: ... | ref: #194"
_ZEILE_RE = re.compile(r"^\s*-\s*(.+)$")


def load_handover_text() -> Optional[str]:
    """Fail-soft: liefert ``None``, wenn die Datei selbst fehlt oder nicht
    lesbar ist (z. B. ein Test-Sandbox ohne eigenes ``SESSION_HANDOVER.md``
    — das ist kein Produktionsbefund, sondern Normalzustand außerhalb der
    echten Repo-Umgebung). Existiert die Datei, wird ihr Inhalt zurückgegeben
    (auch wenn leer) — NUR dann kann ``parse_block`` sinnvoll zwischen
    "Block fehlt im echten Dokument" (ein Finding wert) und "Datei gar nicht
    vorhanden" (kein Finding) unterscheiden."""
    try:
        return (REPO_ROOT / HANDOVER_PATH).read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001 — fail-soft
        return None


def _parse_zeile(inhalt: str) -> Optional[Dict[str, str]]:
    """Eine Termin-Zeile in ihre Felder zerlegen. ``None`` bei fehlenden
    Pflichtfeldern (faellig_am/status/titel) oder unparsbarem Datum."""
    felder: Dict[str, str] = {}
    for teil in inhalt.split("|"):
        if ":" not in teil:
            return None
        schluessel, wert = teil.split(":", 1)
        felder[schluessel.strip()] = wert.strip()
    if not {"faellig_am", "status", "titel"} <= felder.keys():
        return None
    try:
        _dt.date.fromisoformat(felder["faellig_am"])
    except ValueError:
        return None
    if not felder["titel"]:
        return None
    return felder


def parse_block(text: str) -> Tuple[List[Dict[str, str]], List[Dict]]:
    """Liefert ``(termine, befunde)``. ``termine`` sind erfolgreich gelesene
    Zeilen (inkl. ``_zeile`` = 1-basierte Zeilennummer), ``befunde`` sind
    bereits vollständige Finding-Dicts (Block fehlt/doppelt, Zeile unlesbar).
    Reine Funktion, nichts wird geschrieben.

    Die Marker werden als EIGENE, GETRIMMTE ZEILE erkannt (nicht als
    bloßes Substring irgendwo im Text) — sonst zählt jede Erwähnung der
    Marker-Literale in Prosa (z. B. eine Arbeitsregel, die den Marker
    beschreibt) fälschlich als zusätzliches Vorkommen."""
    zeilen_liste = text.split("\n")
    start_n = sum(1 for z in zeilen_liste if z.strip() == MARKER_START)
    ende_n = sum(1 for z in zeilen_liste if z.strip() == MARKER_ENDE)
    if start_n == 0 and ende_n == 0:
        return [], [{
            "rule": "wiedervorlagen_block_fehlt", "severity": "info",
            "market": None,
            "message": ("ℹ️ Kein Wiedervorlagen-Block in SESSION_HANDOVER.md "
                       "gefunden — keine Termine können geprüft werden."),
            "detail": {},
        }]
    if start_n != 1 or ende_n != 1:
        return [], [{
            "rule": "wiedervorlagen_block_mehrfach", "severity": "info",
            "market": None,
            "message": (f"ℹ️ Wiedervorlagen-Block nicht eindeutig "
                       f"(ANFANG={start_n}x, ENDE={ende_n}x) — wird "
                       f"übersprungen, bis er eindeutig ist."),
            "detail": {"start_n": start_n, "ende_n": ende_n},
        }]
    zeile_start = next(i for i, z in enumerate(zeilen_liste)
                       if z.strip() == MARKER_START)
    zeile_ende = next(i for i, z in enumerate(zeilen_liste)
                      if z.strip() == MARKER_ENDE)
    if zeile_start >= zeile_ende:
        return [], [{
            "rule": "wiedervorlagen_block_mehrfach", "severity": "info",
            "market": None,
            "message": "ℹ️ Wiedervorlagen-Block: ANFANG liegt nicht vor ENDE.",
            "detail": {},
        }]

    block_zeilen = zeilen_liste[zeile_start + 1:zeile_ende]
    zeilen_vor_block = zeile_start + 1

    termine: List[Dict[str, str]] = []
    befunde: List[Dict] = []
    for offset, zeile in enumerate(block_zeilen):
        if not zeile.strip():
            continue
        m = _ZEILE_RE.match(zeile)
        if not m:
            continue
        zeilennummer = zeilen_vor_block + offset + 1
        felder = _parse_zeile(m.group(1))
        if felder is None:
            befunde.append({
                "rule": f"wiedervorlage_unlesbar_{zeilennummer}",
                "severity": "info", "market": None,
                "message": f"ℹ️ Wiedervorlage unlesbar: Zeile {zeilennummer}",
                "detail": {"zeile": zeilennummer, "inhalt": zeile.strip()},
            })
            continue
        felder["_zeile"] = str(zeilennummer)
        termine.append(felder)
    return termine, befunde


def _slug(titel: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", titel.lower()).strip("_")
    return s[:40] or "termin"


def faelligkeits_findings(text: Optional[str],
                          jetzt: _dt.datetime) -> List[Dict]:
    """Alle Befunde für den aktuellen Lauf: Fälligkeits-Meldungen + etwaige
    Lese-Befunde (Block fehlt/doppelt, Zeile unlesbar). ``jetzt`` muss
    tz-aware sein (UTC oder beliebig) — die Tagesgrenze wird in
    Europe/Berlin gezogen, nicht in der Zeitzone von ``jetzt``.

    ``text=None`` (Datei selbst fehlt, s. ``load_handover_text``) -> **kein
    Befund** — anders als ein lesbares Dokument ohne Block (das IST ein
    Befund, s. ``parse_block``). Verhindert, dass jede Test-Sandbox ohne
    eigenes ``SESSION_HANDOVER.md`` ein Störsignal erzeugt."""
    if text is None:
        return []
    termine, befunde = parse_block(text)
    heute = jetzt.astimezone(BERLIN).date()

    for t in termine:
        if t.get("status") == "erledigt":
            continue
        faellig_am = _dt.date.fromisoformat(t["faellig_am"])
        titel = t["titel"]
        ref = t.get("ref", "")
        rule = f"wiedervorlage_{faellig_am.isoformat()}_{_slug(titel)}"
        detail = {"faellig_am": t["faellig_am"], "titel": titel, "ref": ref,
                  "zeile": t.get("_zeile")}
        if faellig_am == heute:
            befunde.append({
                "rule": rule, "severity": "info", "market": None,
                "message": f"📅 Heute fällig: {titel}",
                "detail": detail,
            })
        elif faellig_am < heute:
            tage = (heute - faellig_am).days
            befunde.append({
                "rule": rule, "severity": "warn", "market": None,
                "message": (f"⏰ Überfällig seit {tage} "
                           f"Tag{'en' if tage != 1 else ''}: {titel}"),
                "detail": {**detail, "tage_ueberfaellig": tage},
            })
        # faellig_am > heute: keine Meldung ("bald fällig" ist bewusst kein
        # eigener Zustand, s. PR-Text).
    return befunde
