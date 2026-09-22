#!/usr/bin/env python3
"""Proaktiver Fehler-Wächter — Selbstwartung Stufe 4 (Vorschlag, 20.09.2026).

NÄCHSTE STUFE NACH #111 (Struktur-Wächter, nur MELDEN) UND der Selbst-Handlung
aus `auto_retry_watcher.py` (Stufe 3, aber dort nur EIN Aktionstyp: Retry-
Dispatch nach Fehlschlag). Dieser Wächter sucht AKTIV, ohne Anlass, nach
bekannten Fehlerklassen (Testdaten-Drift, veraltete Kommentare, fehlende
Registry-Einträge, Key-Exposure-Muster, Struktur-Inkonsistenz) und
klassifiziert jeden Fund gegen dieselbe rote Linie, die Guardian für
Manual-Merge-PRs bereits prüft.

WICHTIGE GRENZE (bewusst NICHT in diesem Modul enthalten): das eigentliche
AUTOMATISCHE FIXEN eines offenen, semantisch unklaren Fundes (z. B. "dieser
Kommentar widerspricht dem Code — wie soll der Text lauten?") braucht ein
Sprachmodell im Loop, nicht nur deterministische Heuristik. Dieses Modul
liefert die DETEKTION und die KLASSIFIKATION (rote Linie ja/nein) — beides
pure, deterministische, mutationsgeprüfte Funktionen. Die Orchestrierung
("Fix schreiben, testen, Guardian, mergen") lebt bewusst AUSSERHALB dieses
Moduls (Workflow-YAML + ggf. ein Modell-Aufruf) und ist in der Draft-PR-
Beschreibung als offener Entwurf markiert, nicht als fertig gebaut.

ROTE LINIE (siehe Auftrag 20.09.2026, deckungsgleich mit Guardians
Prüfliste): Score-Logik, Sammlungs-Gate, `evaluate.py`, die drei
Qualitäts-Marker (`mark_episode_splits.py`, `mark_in_session_creation.py`,
`mark_stale_market_records.py`), die Auswertungsregel (`EVAL_MIN_N` /
`eval_counts`). Bei Unklarheit gilt IMMER "ja, rote Linie" — nie raten
(Auftrags-Vorgabe, siehe `beruehrt_rote_linie`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

# ---------------------------------------------------------------------------
# Rote Linie — Klassifikation von Diffs (dieselbe Prüfung wie Guardian für
# Manual-Merge-Fälle: Score/Sammlungs-Gate/evaluate.py/Marker/Auswertungsregel)
# ---------------------------------------------------------------------------

# Pfade, die IMMER als rote Linie gelten — unabhängig davon, welche Zeile
# im Diff geändert wurde. Bewusst datei-, nicht zeilengranular: eine
# zeilengranulare Unterscheidung ("nur ein Kommentar in elliott_pipeline.py")
# würde Fehlklassifikation riskieren, wenn ein Kommentar direkt neben
# Score-Logik steht und das Tool die Grenze falsch zieht. Konservativ nach
# Auftrag ("bei Unklarheit: ja").
ROTE_LINIE_PFADE = frozenset({
    "scripts/elliott_pipeline.py",   # Score/Pipeline/Sammlungs-Gate-Aufruf
    "scripts/forward_collection.py",  # Sammlungs-Gate + Auswertungsregel
    "scripts/evaluate.py",
    "scripts/rules.py",              # die drei harten Elliott-Regeln (K.o.)
    "scripts/zigzag.py",             # Pivot-Engine, Basis der Score-Zählung
    "scripts/mark_episode_splits.py",
    "scripts/mark_in_session_creation.py",
    "scripts/mark_stale_market_records.py",
    "scripts/in_session.py",
    "config.py",                     # Schwellen/Parameter für alles Obige
})

# Pfade/Präfixe, die NIE rote Linie sind — reine Tests, Doku, Kosmetik.
# Bewusst eng gefasst (Allowlist, nicht Blockliste): alles außerhalb dieser
# Liste UND außerhalb ROTE_LINIE_PFADE fällt in den Default unten (= rote
# Linie), nicht in "sicher".
SICHERE_PFADE_PRAEFIXE = (
    "tests/",
    ".claude/agents/",
)
SICHERE_DATEIEN_SUFFIXE = (".md",)  # README.md, SESSION_*.md, validation_registry.md, …

# Explizit AUSGENOMMEN von der Doku-Sicherheit: docs/index.html ist Frontend-
# CODE (liest report.json-Felder direkt, keine reine Doku) und Workflow-YAML
# (.github/workflows/*) — beides braucht laut Guardians eigener Prüfliste
# ohnehin einen Zweitblick, hier zusätzlich konservativ als rote Linie
# behandelt (der Wächter darf sich nicht selbst die eigenen Leitplanken
# umschreiben und mergen).


def beruehrt_rote_linie(geaenderte_dateien: Sequence[str]) -> bool:
    """True, wenn IRGENDEINE der geänderten Dateien die rote Linie berührt.

    Konservativ nach Auftrag: jede Datei, die weder explizit als sicher
    (Test/Doku) noch explizit als rote Linie gelistet ist, gilt als rote
    Linie (Default-Fall unten). Eine leere Liste gilt als rote Linie
    (nichts geändert zu melden ist kein Fall, der hier vorkommen sollte —
    fail-soft in die sichere Richtung).
    """
    if not geaenderte_dateien:
        return True
    for pfad in geaenderte_dateien:
        p = pfad.replace("\\", "/").lstrip("/")
        if p in ROTE_LINIE_PFADE:
            return True
        if any(p.startswith(praefix) for praefix in SICHERE_PFADE_PRAEFIXE):
            continue
        if p.endswith(SICHERE_DATEIEN_SUFFIXE):
            continue
        # Default: unbekannter/nicht gelisteter Pfad -> rote Linie.
        return True
    return False


# ---------------------------------------------------------------------------
# Funde — gemeinsames Schema
# ---------------------------------------------------------------------------
@dataclass
class Fund:
    klasse: str              # eine der 5 Fehlerklassen (Kurzname, siehe unten)
    datei: str
    zeile: Optional[int]
    beschreibung: str
    betroffene_dateien: List[str] = field(default_factory=list)
    rote_linie: bool = True

    def __post_init__(self) -> None:
        # Wird IMMER aus betroffene_dateien neu berechnet, nie roh übergeben
        # -> ein Detektor kann rote_linie nicht versehentlich falsch setzen.
        #
        # AUSNAHME, FEST VERDRAHTET (21.09.2026, Easy): Key-/Secret-Exposure
        # ist NIE rote Linie — unabhängig davon, in welcher Datei der Fund
        # liegt. Begründung: ein gültiger Fix dieser Klasse ist per
        # Konstruktion eine reine Sicherheits-/Kosmetik-Änderung (ein
        # f-String-Literal wird in `_redact(..., key_var)` gewrappt,
        # `proactive_fixer.pruefe_fix_wirkung()` verlangt vorher/nachher
        # denselben Detektor-Beweis) — es gibt KEINEN Pfad, über den ein
        # solcher Fix Score-/Sammlungs-/Auswertungslogik verändern könnte,
        # selbst wenn die Fund-Datei (z. B. elliott_pipeline.py) sonst als
        # rote Linie gilt. Das ist eine Ausnahme nach FUND-KLASSE, nicht
        # nach Datei — `beruehrt_rote_linie()` selbst bleibt unverändert
        # dateibasiert und gilt für alle anderen 4 Klassen unverändert
        # konservativ (Auftrags-Grenze: nur diese eine Klasse ausnehmen,
        # nicht die Datei als Ganzes freigeben).
        if self.klasse == KLASSE_KEY_EXPOSURE:
            self.rote_linie = False
            return
        dateien = self.betroffene_dateien or [self.datei]
        self.rote_linie = beruehrt_rote_linie(dateien)

    def to_dict(self) -> Dict:
        return {
            "klasse": self.klasse, "datei": self.datei, "zeile": self.zeile,
            "beschreibung": self.beschreibung,
            "betroffene_dateien": self.betroffene_dateien or [self.datei],
            "rote_linie": self.rote_linie,
        }


KLASSE_TESTDATEN_DRIFT = "testdaten_drift"
KLASSE_VERALTETE_DOKU = "veraltete_doku"
KLASSE_FEHLENDE_REGISTRY = "fehlende_registry"
KLASSE_KEY_EXPOSURE = "key_exposure"
KLASSE_STRUKTUR_INKONSISTENZ = "struktur_inkonsistenz"


# ---------------------------------------------------------------------------
# 1) Testdaten-Drift — hartkodierte Werte, die mit der wachsenden Sammlung
#    altern (Muster #115/#117/#120). Heuristik: ein Test vergleicht eine
#    Variable, die aus einer PRODUKTIONS-Datendatei gelesen wurde (nicht aus
#    einer lokalen Fixture), gegen eine hartkodierte Zahl/ein hartkodiertes
#    Datum. Bewusst eng: lieber einen echten Fall verpassen als Fixtures
#    fälschlich als Drift markieren.
# ---------------------------------------------------------------------------
_PROD_LADE_MUSTER = re.compile(
    r"(json\.load\(open\([\"'][^\"']*(?:forward_collection|report)\.json|"
    r"fc\.load_collection\(\))"
)
_KOPIERT = re.compile(r"copy\.deepcopy|\.copy\(\)")
# Eng auf das ECHTE #115/#117/#120-Muster: eine LÄNGE/ANZAHL (nicht ein
# beliebiger Wert) wird gegen eine hartkodierte Zahl geprüft — genau das,
# was mit wachsender Sammlung altert. Ein einzelner fixer Feldwert
# (Score, Datum, Preis) in einer weiter unten selbst gebauten Fixture ist
# KEIN Drift-Kandidat und wird hier bewusst NICHT erfasst (sonst Rauschen,
# siehe Kalibrierungslauf 20.09.2026: 76 von 97 Funden waren das).
_HARTKODIERTE_ANZAHL = re.compile(r"\blen\([^)]*\)\s*==\s*(\d+)\b")
_LOOKBACK_ZEILEN = 6

# Zweites Muster (22.09.2026, AOF.DE-Diagnose): eine hartkodierte LISTE/
# MENGE, die per Namenskonvention dieses Repos ("ERWARTETE_...", siehe
# ERWARTETE_MARKIERUNGEN/ERWARTETE_SECRETS/ERWARTETE_FAELLE) einen
# vollständigen historischen/produktionsnahen Sollzustand behauptet, UND
# per `==`/`sorted(...) ==` direkt gegen sie geprüft wird. Bewusst NICHT an
# eine Produktionsdaten-Ladezeile in der gleichen Funktion gekoppelt (anders
# als die Längen-Prüfung oben): der reale Fall (`ERWARTETE_MARKIERUNGEN` in
# tests/test_sammlungs_schutz.py) lädt die Historie über eine PYTEST-FIXTURE
# (`replay`), nicht direkt im Testkörper — ein Zeilen-Fenster sähe diesen
# Zusammenhang nie. Die `ERWARTET*`-Namenskonvention selbst ist deshalb das
# Signal: eine Konstante, deren Name eine vollständige Erwartung behauptet
# UND als Liste/Tupel-Literal definiert ist (nicht ein einzelner Schwellwert
# wie `EVAL_MIN_N`), ist strukturell genau der Kandidat, der mit wachsender
# echter Historie veraltet. Guardian/Easy filtern verbleibende Fehlalarme
# (z. B. bewusst geschlossene Mengen wie ERWARTETE_SECRETS) beim Review —
# dieselbe Abwägung wie beim Rest der Klasse: lieber melden als schweigen.
_ERWARTET_LISTE_DEF = re.compile(r"^(ERWARTET\w*)\s*=\s*[\[\(]")
_ERWARTET_VERGLEICH = re.compile(
    r"assert\s+.+==\s*(?:sorted\(\s*)?(ERWARTET\w*)\s*\)?"
)


def erkenne_testdaten_drift(dateiinhalt: str, dateiname: str) -> List[Fund]:
    funde: List[Fund] = []
    zeilen = dateiinhalt.splitlines()
    for i, zeile in enumerate(zeilen):
        m = _HARTKODIERTE_ANZAHL.search(zeile)
        if not m or zeile.strip().startswith("#"):
            continue
        fenster_start = max(0, i - _LOOKBACK_ZEILEN)
        fenster = "\n".join(zeilen[fenster_start:i + 1])
        if not _PROD_LADE_MUSTER.search(fenster):
            continue
        if _KOPIERT.search(fenster):
            # Produktionsdaten wurden vor der Prüfung dedupliziert/kopiert
            # und typischerweise anschließend zu einer festen Fixture
            # zurechtgeschnitten -> kein Drift-Risiko mehr.
            continue
        funde.append(Fund(
            klasse=KLASSE_TESTDATEN_DRIFT, datei=dateiname, zeile=i + 1,
            beschreibung=(
                f"{dateiname}:{i + 1} prüft eine Länge/Anzahl direkt aus "
                f"unkopierten Produktionsdaten gegen eine hartkodierte "
                f"Zahl — Musterverdacht Testdaten-Drift (#115/#117/#120): "
                f"{zeile.strip()!r}"
            ),
            betroffene_dateien=[dateiname],
        ))

    listen_konstanten = {
        mm.group(1) for zeile in zeilen
        for mm in [_ERWARTET_LISTE_DEF.match(zeile)] if mm
    }
    for i, zeile in enumerate(zeilen):
        if zeile.strip().startswith("#"):
            continue
        m = _ERWARTET_VERGLEICH.search(zeile)
        if not m or m.group(1) not in listen_konstanten:
            continue
        funde.append(Fund(
            klasse=KLASSE_TESTDATEN_DRIFT, datei=dateiname, zeile=i + 1,
            beschreibung=(
                f"{dateiname}:{i + 1} vergleicht direkt gegen die "
                f"hartkodierte Liste `{m.group(1)}` — Musterverdacht "
                f"Testdaten-Drift (AOF.DE-Diagnose #22.09.2026, Muster wie "
                f"#115/#117/#120, hier als Listen- statt Längen-Vergleich): "
                f"{zeile.strip()!r}"
            ),
            betroffene_dateien=[dateiname],
        ))
    return funde


# ---------------------------------------------------------------------------
# 2) Veraltete Kommentare/Doku — ein Docstring/Kommentar behauptet, eine
#    Funktion lese Feld X oder Schwelle Y, das aktuelle Code liest aber ein
#    anderes Feld/Zahl. Eng geschnitten auf das Muster, das die 19.09.-
#    Diagnose real gezeigt hat: ein Kommentar referenziert ein Feld per
#    Namen (`diag.<feld>` o. ä.), die Funktion direkt darunter liest aber
#    ein ANDERES Feld.
# ---------------------------------------------------------------------------
_FELD_REFERENZ = re.compile(r"`?diag\.([a-z][a-z0-9_]*)`?")
_FELD_LESUNG = re.compile(r"\.get\([\"']([a-z_]+)[\"']\)")
# dict-Zugriffsmethoden, die KEIN Feldname sind (sonst matcht "diag.get(...)"
# sich selbst als Referenz auf ein Feld namens "get").
_KEINE_FELDNAMEN = frozenset({"get", "keys", "items", "values", "pop",
                               "setdefault", "update", "copy"})
# "diag" selbst ist der CONTAINER, kein Feld darin — `(x.get("diag") or {})
# .get("last_bar_date")` matcht `_FELD_LESUNG` sonst zweimal (Container +
# echtes Feld) und macht jede Fensterprüfung künstlich mehrdeutig, obwohl
# nur EIN echtes Feld gelesen wird. Ohne diesen Ausschluss hätte der
# Kalibrierungsfund health_check.py:269 (der reale, in Phase 1 gefundene
# Fall) als "mehrdeutig" gegolten und wäre in Phase 2 nie automatisch
# fixbar gewesen.
_CONTAINER_FELDER = frozenset({"diag"})


def erkenne_veraltete_feldreferenz(dateiinhalt: str, dateiname: str) -> List[Fund]:
    funde: List[Fund] = []
    zeilen = dateiinhalt.splitlines()
    for i, zeile in enumerate(zeilen):
        ref = _FELD_REFERENZ.search(zeile)
        if not ref:
            continue
        referenziertes_feld = ref.group(1)
        if referenziertes_feld in _KEINE_FELDNAMEN:
            continue
        # Suchfenster: die nächsten 15 Zeilen nach dem Kommentar (die
        # Funktion/den Codeblock, den der Kommentar beschreibt).
        fenster = "\n".join(zeilen[i:i + 15])
        gelesene_felder = set(_FELD_LESUNG.findall(fenster)) - _CONTAINER_FELDER
        if not gelesene_felder:
            continue
        if referenziertes_feld not in gelesene_felder:
            funde.append(Fund(
                klasse=KLASSE_VERALTETE_DOKU, datei=dateiname, zeile=i + 1,
                beschreibung=(
                    f"{dateiname}:{i + 1} referenziert `diag.{referenziertes_feld}`, "
                    f"der Code direkt darunter liest aber "
                    f"{sorted(gelesene_felder)} — Kommentar/Code könnten "
                    f"auseinandergelaufen sein (Muster: bar_lag_trading_days "
                    f"vs. bar_lag_session_days, siehe #131-Diagnose)."
                ),
                betroffene_dateien=[dateiname],
            ))
    return funde


# ---------------------------------------------------------------------------
# 3) Fehlende Registry-Einträge — Hausregel: Änderungen an Schwellen/Gate/
#    Score-Parametern brauchen einen Eintrag in validation_registry.md.
#    Heuristik: ein config.py-Konstanten-Name taucht im Registry-Dokument
#    NICHT auf, obwohl er zu den bekannten "brauchen-einen-Eintrag"-Namen
#    gehört (Schwellen/Gate-Parameter, an Großschreibung + bekanntem Suffix
#    erkennbar).
# ---------------------------------------------------------------------------
_REGISTRY_PFLICHT_MUSTER = re.compile(
    r"^([A-Z][A-Z0-9_]*(?:_CRIT|_MIN_N|_THRESHOLD|_MAX|_LIMIT))\s*="
)


def erkenne_fehlende_registry_eintraege(
    config_inhalt: str, registry_inhalt: str,
) -> List[Fund]:
    funde: List[Fund] = []
    for i, zeile in enumerate(config_inhalt.splitlines(), start=1):
        m = _REGISTRY_PFLICHT_MUSTER.match(zeile.strip())
        if not m:
            continue
        name = m.group(1)
        if name not in registry_inhalt:
            funde.append(Fund(
                klasse=KLASSE_FEHLENDE_REGISTRY, datei="config.py", zeile=i,
                beschreibung=(
                    f"config.py:{i} definiert Gate-/Schwellen-Parameter "
                    f"`{name}`, der laut Hausregel einen Eintrag in "
                    f"docs/validation_registry.md braucht — dort nicht "
                    f"gefunden."
                ),
                betroffene_dateien=["config.py", "docs/validation_registry.md"],
            ))
    return funde


# ---------------------------------------------------------------------------
# 4) Key-/Secret-Exposure — unredigierte Exception-Details bei API-Calls
#    (Muster #134/#136/#137: Twelve-Data-/Alpha-Vantage-API-Key landete
#    unredigiert im Log/Detail-Feld). Heuristik: eine Zeile baut einen
#    Log-/Detail-String aus einer Exception (`{exc}`) UND es existiert in
#    Reichweite eine BENANNTE Key-Variable (`<name> = os.environ...`) —
#    aber `_redact(` taucht NICHT in den letzten Zeilen davor auf.
#
# KALIBRIERUNGSFUND 21.09.2026: die vorige Fassung prüfte JEDE
# `os.environ`-Lesung mit „KEY" im Namen, auch eine, die NIE einer Variable
# zugewiesen wird (`os.environ.get("ANTHROPIC_API_KEY", "")` direkt als
# Funktionsargument, wie in `elliott_pipeline.py` für den Agent-Kommentar).
# Ergebnis: 8 Fehl-Funde in völlig unabhängigen `except`-Blöcken (Health-
# Check, Forward-Sammlung, In-Session-Marker, …) im 60-Zeilen-Radius um
# diese beiden Stellen — keiner davon transportiert überhaupt einen
# API-Key im Exception-Text (der Anthropic-Key geht als HTTP-Header,
# nicht als URL-Parameter wie bei Twelve Data/Alpha Vantage — strukturell
# ein anderes, sehr viel kleineres Risiko). Jetzt: nur eine ZUGEWIESENE
# Key-Variable zählt als Nähe-Anker — GENAU das, was ein Fix (`_redact(
# ..., key_var)`) überhaupt referenzieren könnte. Erkennung und Fixbarkeit
# sind damit strukturell dieselbe Bedingung, kein Auseinanderlaufen mehr.
# ---------------------------------------------------------------------------
_EXC_IN_STRING = re.compile(r"f[\"'].*\{(?:exc|e)\}")
_API_KEY_ZUWEISUNG = re.compile(r"^\s*\w*[Kk]ey\w*\s*=\s*os\.environ")
# Fenster um eine Key-VARIABLEN-Zuweisung, in dem eine unredigierte
# Exception als tatsächlich riskant gilt (dieselbe Fetch-Funktion).
_KEY_NAEHE_ZEILEN = 60


def erkenne_key_exposure(dateiinhalt: str, dateiname: str) -> List[Fund]:
    funde: List[Fund] = []
    zeilen = dateiinhalt.splitlines()
    key_zeilen = [i for i, z in enumerate(zeilen) if _API_KEY_ZUWEISUNG.search(z)]
    if not key_zeilen:
        return funde
    for i, zeile in enumerate(zeilen):
        in_naehe_einer_key_lesung = any(
            abs(i - k) <= _KEY_NAEHE_ZEILEN for k in key_zeilen)
        if not in_naehe_einer_key_lesung:
            continue
        # Mehrzeiliger Aufruf: `_redact(` kann auf einer VORHERGEHENDEN
        # Zeile stehen (`detail=_redact(\n    f"...",\n    api_key,\n)`),
        # nicht nur in derselben — sonst meldet der Detektor bereits
        # redigierten Code fälschlich (Kalibrierungsfund 20.09.2026: genau
        # die beiden echten #134/#137-Stellen sehen so aus).
        vorherige_zeilen = "\n".join(zeilen[max(0, i - 3):i + 1])
        if _EXC_IN_STRING.search(zeile) and "_redact(" not in vorherige_zeilen:
            funde.append(Fund(
                klasse=KLASSE_KEY_EXPOSURE, datei=dateiname, zeile=i + 1,
                beschreibung=(
                    f"{dateiname}:{i + 1} baut einen Log-/Detail-String direkt "
                    f"aus einer Exception in einer Datei, die einen API-Key "
                    f"aus der Umgebung liest, OHNE `_redact(...)` — "
                    f"Musterverdacht Key-Exposure (#134/#136/#137): "
                    f"{zeile.strip()!r}"
                ),
                betroffene_dateien=[dateiname],
            ))
    return funde


# ---------------------------------------------------------------------------
# 5) Struktur-Inkonsistenz zwischen ähnlichem Code — zwei Fallback-Pfade
#    (z. B. Twelve-Data vs. Alpha-Vantage), die strukturell dasselbe tun
#    sollten, aber an EINER Stelle abweichen (z. B. nur einer redigiert,
#    nur einer zählt den Fallback-Call). Heuristik: zwei Funktionen mit
#    ähnlichem Namensmuster (`_make_*_with_*_fallback`), bei denen die eine
#    einen der Marker-Aufrufe (`_redact(`, `calls["n"]`, `_log(`) enthält
#    und die andere NICHT.
# ---------------------------------------------------------------------------
_FALLBACK_FUNKTION = re.compile(
    r"def (_make_\w*_with_\w*_fallback)\b.*?(?=\ndef |\Z)", re.DOTALL,
)
_STRUKTUR_MARKER = ("_redact(", 'calls["n"]', "_log(")


def erkenne_struktur_inkonsistenz(dateiinhalt: str, dateiname: str) -> List[Fund]:
    funde: List[Fund] = []
    treffer = _FALLBACK_FUNKTION.findall(dateiinhalt)
    bloecke = {
        m.group(1): m.group(0)
        for m in _FALLBACK_FUNKTION.finditer(dateiinhalt)
    }
    if len(bloecke) < 2:
        return funde
    profile = {name: {mk: (mk in body) for mk in _STRUKTUR_MARKER}
               for name, body in bloecke.items()}
    namen = sorted(profile)
    referenz_name = namen[0]
    referenz = profile[referenz_name]
    for name in namen[1:]:
        abweichungen = [mk for mk in _STRUKTUR_MARKER
                        if profile[name][mk] != referenz[mk]]
        if abweichungen:
            funde.append(Fund(
                klasse=KLASSE_STRUKTUR_INKONSISTENZ, datei=dateiname, zeile=None,
                beschreibung=(
                    f"{referenz_name}() und {name}() sind strukturell "
                    f"parallele Fallback-Pfade, weichen aber ab bei: "
                    f"{', '.join(abweichungen)} — prüfen, ob das Absicht ist "
                    f"oder eine Lücke wie #134/#136/#137."
                ),
                betroffene_dateien=[dateiname],
            ))
    return funde


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
_SCAN_DATEIEN = (
    "scripts/elliott_pipeline.py",
    "scripts/forward_collection.py",
    "scripts/health_check.py",
    "scripts/auto_retry_watcher.py",
)


def scan_repo(repo_root: Path) -> List[Fund]:
    """Läuft alle 5 Detektoren über den aktuellen Stand des Repos.

    Rein lesend — keine Datei wird verändert. Gibt die rohe Fundliste
    zurück; die Aufteilung "rote Linie ja/nein" steht bereits an jedem
    einzelnen Fund (siehe ``Fund.__post_init__``)."""
    funde: List[Fund] = []

    tests_dir = repo_root / "tests"
    if tests_dir.is_dir():
        for pfad in sorted(tests_dir.glob("test_*.py")):
            inhalt = pfad.read_text(encoding="utf-8")
            rel = f"tests/{pfad.name}"
            funde += erkenne_testdaten_drift(inhalt, rel)

    for rel in _SCAN_DATEIEN:
        pfad = repo_root / rel
        if not pfad.is_file():
            continue
        inhalt = pfad.read_text(encoding="utf-8")
        funde += erkenne_veraltete_feldreferenz(inhalt, rel)
        funde += erkenne_key_exposure(inhalt, rel)
        funde += erkenne_struktur_inkonsistenz(inhalt, rel)

    config_pfad = repo_root / "config.py"
    registry_pfad = repo_root / "docs" / "validation_registry.md"
    if config_pfad.is_file() and registry_pfad.is_file():
        funde += erkenne_fehlende_registry_eintraege(
            config_pfad.read_text(encoding="utf-8"),
            registry_pfad.read_text(encoding="utf-8"),
        )

    return funde


def tagesbericht(funde: Sequence[Fund]) -> str:
    """EIN zusammenfassender Text für Push/Report-Panel (Auftrag Punkt 5) —
    keine Einzelmeldung pro Fund. Reine Formatierung, kein I/O."""
    if not funde:
        return "[proactive-watcher] Keine Funde in diesem Lauf."
    rote = [f for f in funde if f.rote_linie]
    gruene = [f for f in funde if not f.rote_linie]
    zeilen = [
        f"[proactive-watcher] {len(funde)} Fund(e): "
        f"{len(gruene)} ohne rote Linie (Kandidaten für Self-Merge-PR), "
        f"{len(rote)} mit roter Linie (Draft-PR, wartet auf Easy).",
    ]
    for f in gruene:
        zeilen.append(f"  [self-merge-kandidat] {f.klasse}: {f.beschreibung}")
    for f in rote:
        zeilen.append(f"  [draft/easy] {f.klasse}: {f.beschreibung}")
    return "\n".join(zeilen)


def main() -> int:
    import os

    repo_root = Path(__file__).resolve().parent.parent
    funde = scan_repo(repo_root)
    bericht = tagesbericht(funde)
    print(bericht)

    ntfy_topic = os.environ.get("NTFY_TOPIC", "")
    if ntfy_topic:
        # Kein sys.path.insert nötig: dieses Modul importiert `config` nicht
        # (siehe repo_path.py) und liegt selbst in scripts/ — beim Start als
        # Skript (`python scripts/proactive_watcher.py`) ist scripts/ bereits
        # sys.path[0], `notify` also direkt importierbar.
        import notify  # noqa: WPS433 — lazy wie in auto_retry_watcher.py

        rote = sum(1 for f in funde if f.rote_linie)
        gruene = len(funde) - rote
        titel = (
            "Elliott: proaktiver Wächter — keine Funde" if not funde
            else f"Elliott: proaktiver Wächter — {gruene} Self-Merge-"
                 f"Kandidat(en), {rote} für Easy"
        )
        # EIN Push für den GESAMTEN Lauf (Auftrag Punkt 5) — keine
        # Einzelmeldung pro Fund. Push nur, wenn es überhaupt etwas zu
        # berichten gibt; ein Lauf ohne Funde ist kein Alarm.
        if funde:
            notify.send_ntfy(ntfy_topic, titel, bericht, priority="default",
                              tags="mag_right")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
