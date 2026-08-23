#!/usr/bin/env python3
"""Wartungs-Cron Stufe 2 — prüft die STRUKTUR, nicht die Betriebsdaten.

ABGRENZUNG ZUM HEALTH-CHECK (der Grund, warum es zwei Wächter gibt):
``health_check`` läuft IM Tageslauf und prüft, was der Lauf gerade produziert
hat — Kandidatenzahl, Kurs-Stand, Fetch-Qualität, Sammlungs-Fortschritt. Das
sind **Betriebsdaten**: sie ändern sich jeden Tag, also braucht es einen
täglichen Wächter.

Was hier geprüft wird, ändert sich **nur, wenn jemand Code anfasst** — und
genau darin liegt die Lücke: die Testsuite und die statischen Wächter laufen
ausschließlich in der CI, also nur bei PR oder Push. Rührt monatelang niemand
das Repo an, prüft **nichts** mehr die Struktur. Termine laufen ab, Konstanten
laufen auseinander, Spiegel divergieren — lautlos.

DIESER WÄCHTER HANDELT NIE. Er meldet. Keine Selbst-Reparatur, keine
Selbst-Löschung, keine Schwellen-Anpassung. Ein System, das seine eigenen
Schwellen nachzieht, weil sie „zu oft warnen", hört auf, Probleme zu melden,
statt sie zu lösen.

WER WACHT ÜBER DIESEN WÄCHTER: der Tageslauf. ``health_check`` hat seit dem
09.08.2026 die Regel ``maintenance_stale`` — fehlt ``data/maintenance_state.json``
oder ist ``last_run_utc`` älter als 10 Tage, gibt es ein ``warn``. Damit ist die
Kette geschlossen, ohne einen dritten Cron: Staleness-Cron bewacht den
Tageslauf, Tageslauf bewacht den Wartungs-Cron.

FLANKEN-LOGIK NICHT NACHGEBAUT: ``evaluate_edges`` wird aus ``health_check``
IMPORTIERT. Zwei Fassungen derselben Push-Drossel würden auseinanderlaufen,
ohne dass es auffällt — und diese Drossel entscheidet, ob ein Alarm noch
gelesen wird.

EIN PARSER, DER NICHTS FINDET, MELDET DAS. Jede Prüfung hier, die ihren Anker
im Quelltext nicht findet, erzeugt einen **Befund** statt still durchzugehen.
Ein Wächter, der bei fehlendem Anker schweigt, ist schlimmer als keiner: er
sieht aus wie ein grüner Haken.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import repo_path  # noqa: F401,E402 — EIN Pfad-Baustein (Repo-Root + scripts/)

REPO_ROOT = repo_path.REPO_ROOT

# Import-Fehler MERKEN statt verschlucken (Muster aus #69/#88). Anders als dort
# gibt es hier KEINE Rückfall-Literale: ohne `config` und `market_calendar` ist
# dieser Wächter blind, und blind soll er nicht so tun, als sei alles gut.
_IMPORT_FEHLER: Dict[str, str] = {}

try:
    import config  # noqa: E402
except Exception as exc:  # pragma: no cover — defensiv
    config = None
    _IMPORT_FEHLER["config"] = f"{type(exc).__name__}: {exc}"

try:
    import market_calendar as cal  # noqa: E402
except Exception as exc:  # pragma: no cover — defensiv
    cal = None
    _IMPORT_FEHLER["market_calendar"] = f"{type(exc).__name__}: {exc}"

import health_check as hc  # noqa: E402 — EINE Flanken-Logik, kein Nachbau
import notify  # noqa: E402 — EINE ntfy-Schicht

STATE_PATH = "data/maintenance_state.json"
WORKFLOW_DIR = ".github/workflows"
FRONTEND = "docs/index.html"

CRIT = hc.CRIT
WARN = hc.WARN

#: Vorlauf, mit dem die auslaufende Feiertagsliste gemeldet wird.
#:
#: HERGELEITET, nicht gegriffen. Die Liste ``market_calendar.FULL_CLOSURE``
#: endet mit dem letzten eingetragenen Schließtag; **ab dem Tag danach ist sie
#: blind** — ``is_trading_day`` hält dann jeden Werktag für einen Handelstag.
#: Konkret heute: letzter Eintrag 25.12.2027, erste falsche Antwort damit
#: **01.01.2028** (Neujahr gälte als Handelstag; der Erwartungs-Anker und mit
#: ihm das #72-Gate rechneten gegen einen Tag, den es nicht gibt).
#:
#: 90 Tage, weil der Vorlauf DREI Dinge überleben muss: (1) die wöchentliche
#: Taktung dieses Crons, (2) die Warn-Drossel von ``HEALTH_WARN_REPEAT_RUNS``
#: (3 Läufe = 3 Wochen zwischen Wiederholungen) und (3) die Feiertage selbst —
#: der Ablauf fällt naturgemäß in die Zeit, in der niemand am Rechner sitzt.
#: 90 Tage ergeben ~13 Wochenläufe und damit mindestens vier Pushes vor dem
#: ersten blinden Tag. Bei 30 Tagen wären es zwei, beide mitten in den
#: Weihnachtstagen.
VORLAUF_FEIERTAGSLISTE_TAGE = 90

#: Die Secrets, die in den Workflows referenziert werden DÜRFEN. Bewusst eine
#: geschlossene Liste: ein neu auftauchendes Secret ist eine Änderung, die
#: jemand bemerken soll, und ein VERSCHWUNDENES ist der Defekt vom 27.07.2026
#: (das Secret war gesetzt, aber der Step reichte es nicht durch — Score-Alert
#: und Health-Check waren dadurch still).
ERWARTETE_SECRETS = {"NTFY_TOPIC", "ANTHROPIC_API_KEY"}

#: Konstanten, die in `config.py` UND als Literal im Frontend stehen.
#: Verankert über den benannten `const`-Namen, NIE über die nackte Zahl — sonst
#: prüfte man „steht irgendwo eine 30" statt „stimmen die beiden Werte überein".
KONSTANTEN_PAARE = (
    ("STALENESS_HOURS", "STALENESS_HOURS"),
    ("WATCHLIST_MAX", "WL_MAX"),
)

#: Spiegel-Paare: der Kern schreibt links, das Frontend liest rechts.
SPIEGEL_PAARE = (
    ("data/report.json", "docs/data/report.json"),
    ("data/forward_collection.json", "docs/data/forward_collection.json"),
)


def _log(msg: str) -> None:
    print(f"[wartung] {msg}", flush=True)


def _warne(msg: str) -> None:
    print(f"[wartung] WARNUNG: {msg}", flush=True)


def warne_bei_import_fehler() -> bool:
    """Gescheiterte Importe LAUT melden. True = es gab welche."""
    if not _IMPORT_FEHLER:
        return False
    for modul, grund in sorted(_IMPORT_FEHLER.items()):
        _warne(f"`import {modul}` ist fehlgeschlagen ({grund}) — die davon "
               f"abhängigen Prüfungen melden das als eigenen Befund und "
               f"gehen NICHT still durch.")
    return True


def _finding(rule, severity, message, detail=None) -> Dict:
    """Gleiche Form wie ``health_check._finding`` — dieselbe Flanken-Logik
    verarbeitet beides, und der Push-Text bleibt einheitlich."""
    return {"rule": rule, "severity": severity, "market": None,
            "message": message, "detail": detail or {}}


# ---------------------------------------------------------------------------
# 1) TERMIN-HORIZONTE
# ---------------------------------------------------------------------------
def blind_ab() -> Optional[_dt.date]:
    """Erster Tag, an dem die Feiertagsliste **blind** ist (= Tag nach dem
    letzten Eintrag), oder None wenn nicht bestimmbar.

    ABGELEITET statt hartkodiert: verlängert jemand die Liste, wandert der
    Horizont automatisch mit. Ein eingetragenes Datum hier wäre genau die
    Sorte Zahl, die still veraltet.
    """
    if cal is None:
        return None
    eintraege = getattr(cal, "FULL_CLOSURE", None)
    if not isinstance(eintraege, dict) or not eintraege:
        return None
    try:
        letzter = max(_dt.date.fromisoformat(k) for k in eintraege)
    except Exception:  # noqa: BLE001 — unlesbarer Schlüssel: nicht bestimmbar
        return None
    return letzter + _dt.timedelta(days=1)


def check_feiertagsliste(heute: _dt.date,
                         vorlauf: int = VORLAUF_FEIERTAGSLISTE_TAGE
                         ) -> List[Dict]:
    """Feiertagsliste läuft aus → warn mit Vorlauf, crit ab dem blinden Tag."""
    if cal is None:
        return [_finding(
            "feiertagsliste", WARN,
            f"Feiertagsliste nicht prüfbar — {_IMPORT_FEHLER.get('market_calendar', 'market_calendar fehlt')}")]
    blind = blind_ab()
    if blind is None:
        return [_finding(
            "feiertagsliste", WARN,
            "Feiertagsliste nicht auswertbar: FULL_CLOSURE fehlt, ist leer "
            "oder trägt ein unlesbares Datum — der Erwartungs-Anker rechnet "
            "dann gegen eine Liste, die niemand geprüft hat.")]
    if heute < blind - _dt.timedelta(days=vorlauf):
        return []
    tage = (blind - heute).days
    sev = CRIT if heute >= blind else WARN
    lage = (f"seit {-tage} Tag(en) BLIND" if tage <= 0
            else f"noch {tage} Tag(e) gedeckt")
    return [_finding(
        "feiertagsliste", sev,
        f"Feiertagsliste {lage} — letzter Eintrag "
        f"{(blind - _dt.timedelta(days=1)).isoformat()}, danach hält "
        f"`is_trading_day` jeden Werktag für einen Handelstag. Erneuern: "
        f"scripts/market_calendar.py, FULL_CLOSURE.",
        detail={"blind_ab": blind.isoformat(), "tage_bis_blind": tage,
                "vorlauf_tage": vorlauf})]


#: Regeln, die nach dem ERSTEN Push dauerhaft schweigen. Aktuell leer: die
#: einzige einmalige Regel (`sonde_abgelaufen`, Hinweis auf die abgelaufene
#: Mess-Sonde) hat ihren Zweck erfüllt — der Löschweg wurde am 23.08.2026
#: gegangen (Workflow, Skript, Testdatei, Rohdaten entfernt, siehe PR-Text).
#: Der Mechanismus selbst bleibt für künftige einmalige Hinweise bestehen.
EINMALIG: Tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# 2) KONSTANTEN-DRIFT
# ---------------------------------------------------------------------------
def frontend_konstante(html: str, name: str) -> Optional[str]:
    """Wert einer `const NAME = <wert>;`-Zeile, oder None wenn der Anker fehlt."""
    m = re.search(rf"^\s*const\s+{re.escape(name)}\s*=\s*([^;]+);",
                  html, re.M)
    return m.group(1).strip() if m else None


def check_konstanten_drift(html: Optional[str] = None,
                           paare: Sequence[Tuple[str, str]] = KONSTANTEN_PAARE
                           ) -> List[Dict]:
    """`config.py`-Wert gegen das Frontend-Literal — über den NAMEN verankert."""
    if config is None:
        return [_finding(
            "konstanten_drift", WARN,
            f"Konstanten nicht prüfbar — {_IMPORT_FEHLER.get('config', 'config fehlt')}")]
    if html is None:
        try:
            html = (REPO_ROOT / FRONTEND).read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            return [_finding("konstanten_drift", WARN,
                             f"{FRONTEND} nicht lesbar: "
                             f"{type(exc).__name__}: {exc}")]
    out: List[Dict] = []
    for cfg_name, js_name in paare:
        soll = getattr(config, cfg_name, None)
        if soll is None:
            out.append(_finding(
                "konstanten_drift", WARN,
                f"config.{cfg_name} existiert nicht mehr — das Frontend-"
                f"Literal `{js_name}` hat damit keine Gegenprobe.",
                detail={"config": cfg_name, "frontend": js_name}))
            continue
        ist = frontend_konstante(html, js_name)
        if ist is None:
            # ANKER WEG = BEFUND. Stillschweigen hieße: „geprüft, alles gut" —
            # obwohl gar nichts geprüft wurde.
            out.append(_finding(
                "konstanten_drift", WARN,
                f"Anker `const {js_name}` steht nicht mehr in {FRONTEND} — "
                f"die Drift-Prüfung gegen config.{cfg_name} ({soll}) ist "
                f"damit WIRKUNGSLOS, nicht etwa bestanden.",
                detail={"config": cfg_name, "frontend": js_name,
                        "anker_fehlt": True}))
            continue
        if ist != str(soll):
            out.append(_finding(
                "konstanten_drift", WARN,
                f"Drift: config.{cfg_name} = {soll}, aber {FRONTEND} hat "
                f"`const {js_name} = {ist}`. Kern und Anzeige rechnen "
                f"verschieden.",
                detail={"config": cfg_name, "config_wert": str(soll),
                        "frontend": js_name, "frontend_wert": ist}))
    return out


# ---------------------------------------------------------------------------
# 3) SPIEGEL-GLEICHHEIT
# ---------------------------------------------------------------------------
def check_spiegel(paare: Sequence[Tuple[str, str]] = SPIEGEL_PAARE,
                  base: Optional[Path] = None) -> List[Dict]:
    """`data/` gegen `docs/data/` — BYTE-Vergleich, nicht JSON-Vergleich.

    Byte, weil das Frontend die Datei liest, nicht ihren geparsten Inhalt: eine
    abweichende Formatierung wäre zwar inhaltsgleich, aber sie beweist, dass
    die beiden Dateien NICHT aus demselben Schreibvorgang stammen — und genau
    das ist der Befund.
    """
    root = base or REPO_ROOT
    out: List[Dict] = []
    for links, rechts in paare:
        pl, pr = root / links, root / rechts
        if not pl.is_file() or not pr.is_file():
            fehlt = [p for p, x in ((links, pl), (rechts, pr)) if not x.is_file()]
            out.append(_finding(
                "spiegel_ungleich", WARN,
                f"Spiegel unvollständig: {', '.join(fehlt)} fehlt — das "
                f"Frontend liest dann einen anderen Stand als der Kern "
                f"schreibt.",
                detail={"links": links, "rechts": rechts, "fehlt": fehlt}))
            continue
        if pl.read_bytes() != pr.read_bytes():
            out.append(_finding(
                "spiegel_ungleich", WARN,
                f"Spiegel-Drift: {links} und {rechts} sind nicht "
                f"byte-identisch — die PWA zeigt einen anderen Stand als der "
                f"Kern gerechnet hat.",
                detail={"links": links, "rechts": rechts}))
    return out


# ---------------------------------------------------------------------------
# 4) WORKFLOW-STRUKTUR
# ---------------------------------------------------------------------------
# BEWUSST OHNE PyYAML: die Laufzeit-Abhängigkeiten sind auf das Nötigste
# beschränkt (yfinance/pandas/numpy/requests), und ein Wartungs-Wächter ist ein
# schlechter Grund, eine weitere hinzuzufügen. Geparst wird deshalb zeilenweise
# gegen den Hausstil — und JEDE Stelle, an der der Anker nicht greift, ist ein
# BEFUND, nie ein stilles Bestanden.

def workflow_dateien(base: Optional[Path] = None) -> List[Path]:
    root = base or REPO_ROOT
    return sorted((root / WORKFLOW_DIR).glob("*.yml"))


def ohne_kommentare(text: str) -> str:
    """Workflow-Text ohne Kommentarzeilen.

    GUARDIAN-NIT 09.08.2026, und ein verdienter: die Lesson „eine Zusicherung
    darf nicht an etwas hängen, das ein Kommentar erfüllt" hatte ich in den
    TEST eingebaut — und im Produktionscode direkt daneben denselben Fehler
    stehen lassen. ``check_secret_referenzen`` suchte ``"NTFY_TOPIC"`` im
    ROHTEXT des Steps; ein Kommentar wie ``# NTFY_TOPIC wird hier NICHT
    durchgereicht`` erfüllte die Bedingung und stellte genau die Prüfung still,
    die den Defekt vom 27.07.2026 verhindern soll. Nachgestellt und bestätigt,
    bevor es hier steht.

    In diesem Repo ist das kein Randfall: der Hausstil begründet fast jede
    Zeile im Kommentar, und diese Begründungen nennen die betroffenen Namen
    naturgemäß wörtlich.
    """
    return "\n".join(z for z in text.splitlines()
                     if not z.lstrip().startswith("#"))


def _job_namen(text: str) -> List[str]:
    """Job-Schlüssel unterhalb von `jobs:` (Hausstil: zwei Leerzeichen)."""
    zeilen = text.splitlines()
    try:
        start = zeilen.index("jobs:")
    except ValueError:
        return []
    out = []
    for z in zeilen[start + 1:]:
        if z and not z.startswith(" "):          # nächster Top-Level-Block
            break
        m = re.match(r"^  ([A-Za-z_][\w-]*):\s*$", z)
        if m:
            out.append(m.group(1))
    return out


def _concurrency_gruppe(text: str) -> Optional[str]:
    m = re.search(r"^concurrency:\n(?:\s+.*\n)*?\s+group:\s*(.+)$", text, re.M)
    return m.group(1).strip() if m else None


def check_workflow_struktur(base: Optional[Path] = None) -> List[Dict]:
    dateien = workflow_dateien(base)
    out: List[Dict] = []
    if not dateien:
        return [_finding("workflow_struktur", WARN,
                         f"Keine Workflow-Datei unter {WORKFLOW_DIR} gefunden "
                         f"— die Struktur-Prüfung ist wirkungslos.")]
    gruppen: Dict[str, List[str]] = {}
    for pfad in dateien:
        text = pfad.read_text(encoding="utf-8")
        name = pfad.name

        jobs = _job_namen(text)
        if not jobs:
            out.append(_finding(
                "workflow_struktur", WARN,
                f"{name}: kein Job erkannt — der Zeilen-Parser greift nicht "
                f"mehr (Hausstil geändert?). Die Timeout-Prüfung für diese "
                f"Datei ist damit WIRKUNGSLOS.",
                detail={"datei": name, "parser": "jobs"}))
        else:
            # JOB-Ebene = genau vier Leerzeichen (Hausstil, wie `_job_namen`
            # zwei nimmt). GUARDIAN-NIT 09.08.2026: `\s+` zaehlte auch
            # STEP-Timeouts mit (in Actions gueltig, acht Leerzeichen) — ein
            # Step-Deckel haette damit einen fehlenden JOB-Deckel maskiert.
            timeouts = len(re.findall(r"^    timeout-minutes: *\d+ *$",
                                      text, re.M))
            if timeouts < len(jobs):
                out.append(_finding(
                    "workflow_struktur", WARN,
                    f"{name}: {len(jobs)} Job(s), aber nur {timeouts} × "
                    f"`timeout-minutes` — ein Job ohne Deckel blockiert im "
                    f"Hängefall bis zum GitHub-Default von 6 Stunden.",
                    detail={"datei": name, "jobs": jobs,
                            "timeouts": timeouts}))

        gruppe = _concurrency_gruppe(text)
        if gruppe is None:
            out.append(_finding(
                "workflow_struktur", WARN,
                f"{name}: keine `concurrency`-Gruppe — zwei gleichzeitige "
                f"Läufe könnten sich in die Quere kommen.",
                detail={"datei": name, "parser": "concurrency"}))
        else:
            gruppen.setdefault(gruppe, []).append(name)

    for gruppe, wo in sorted(gruppen.items()):
        if len(wo) > 1:
            out.append(_finding(
                "workflow_struktur", WARN,
                f"Concurrency-Gruppe `{gruppe}` doppelt vergeben: "
                f"{', '.join(wo)} — die Läufe blockieren einander "
                f"gegenseitig, obwohl sie nichts miteinander zu tun haben.",
                detail={"gruppe": gruppe, "dateien": wo}))
    return out


def check_secret_referenzen(base: Optional[Path] = None,
                            erwartet: Optional[set] = None) -> List[Dict]:
    """Referenzierte Secrets gegen die geschlossene Erwartungsliste.

    Prüfbar ist statisch nur die REFERENZ, nie der Wert — ob das Secret im
    Repo gesetzt ist, weiß erst der Lauf (`daily.yml` prüft das dort mit
    `[ -z "$NTFY_TOPIC" ]`). Genau deshalb ist die zweite Prüfung hier die
    wichtigere: **jeder Step, der `notify.py` startet, muss `NTFY_TOPIC` im
    eigenen `env` haben.** Das ist der Defekt vom 27.07.2026 — das Secret war
    gesetzt und funktionierte, der Step reichte es nur nicht durch, und
    Score-Alert wie Health-Check waren dadurch still.
    """
    erwartet = ERWARTETE_SECRETS if erwartet is None else erwartet
    dateien = workflow_dateien(base)
    out: List[Dict] = []
    gefunden: set = set()
    for pfad in dateien:
        # OHNE Kommentare — sonst genügt eine Erwähnung im Fließtext, um die
        # Prüfung zu erfüllen (Guardian-Nit 09.08.2026, siehe `ohne_kommentare`).
        text = ohne_kommentare(pfad.read_text(encoding="utf-8"))
        gefunden |= set(re.findall(r"secrets\.([A-Z_][A-Z0-9_]*)", text))
        for step in re.split(r"\n      - name:", text):
            if "scripts/notify.py" not in step:
                continue
            if "NTFY_TOPIC" not in step:
                out.append(_finding(
                    "secret_durchreichung", WARN,
                    f"{pfad.name}: ein Step startet `scripts/notify.py`, hat "
                    f"aber kein `NTFY_TOPIC` im eigenen `env` — GitHub Actions "
                    f"vererbt Secrets NICHT in Steps. Der Push wäre still "
                    f"(Befund 27.07.2026).",
                    detail={"datei": pfad.name}))
    unerwartet = gefunden - erwartet
    if unerwartet:
        out.append(_finding(
            "secret_referenzen", WARN,
            f"Unbekannte Secret-Referenz(en): {', '.join(sorted(unerwartet))} "
            f"— neu hinzugekommen, ohne dass die Erwartungsliste "
            f"nachgezogen wurde.",
            detail={"unerwartet": sorted(unerwartet)}))
    fehlend = erwartet - gefunden
    if fehlend:
        out.append(_finding(
            "secret_referenzen", WARN,
            f"Erwartete Secret-Referenz(en) verschwunden: "
            f"{', '.join(sorted(fehlend))} — der zugehörige Pfad ist damit "
            f"stumm, ohne dass irgendwo ein Fehler auftritt.",
            detail={"fehlend": sorted(fehlend)}))
    return out


# ---------------------------------------------------------------------------
# 5) ZUSAMMENFÜHREN, STATE, PUSH
# ---------------------------------------------------------------------------
def sammle_befunde(heute: _dt.date, base: Optional[Path] = None,
                   bereits_gemeldet: Sequence[str] = ()) -> List[Dict]:
    """Alle Prüfungen. ``bereits_gemeldet`` unterdrückt EINMALIGE Hinweise."""
    out: List[Dict] = []
    out.extend(check_feiertagsliste(heute))
    out.extend(check_konstanten_drift())
    out.extend(check_spiegel(base=base))
    out.extend(check_workflow_struktur(base))
    out.extend(check_secret_referenzen(base))
    # Einmalige Hinweise, die schon draußen waren, gar nicht erst durchreichen.
    out = [f for f in out
           if not (f["rule"] in EINMALIG and f["rule"] in bereits_gemeldet)]
    out.sort(key=lambda f: (-hc._SEV_RANK.get(f["severity"], 0), f["rule"],
                            f["message"]))
    return out


def load_state(base: Optional[Path] = None) -> Dict:
    try:
        with ((base or REPO_ROOT) / STATE_PATH).open(encoding="utf-8") as fh:
            st = json.load(fh)
        return st if isinstance(st, dict) else {}
    except Exception:  # noqa: BLE001 — fehlend/unlesbar = leerer State
        return {}


def write_state(state: Dict, now_iso: str, base: Optional[Path] = None) -> bool:
    try:
        pfad = (base or REPO_ROOT) / STATE_PATH
        pfad.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(state)
        payload["last_run_utc"] = now_iso
        payload["updated_utc"] = now_iso
        with pfad.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        return True
    except Exception as exc:  # noqa: BLE001
        _warne(f"State nicht schreibbar: {type(exc).__name__}: {exc}")
        return False


def puls_faellig(now: _dt.datetime, state: Optional[Dict]) -> bool:
    """Ein Lebenszeichen pro KALENDERMONAT, auch wenn nichts zu melden ist.

    Ohne ihn wäre Stille doppeldeutig: „nichts gefunden" sähe genauso aus wie
    „Cron seit Wochen tot". Der Tageslauf fängt den toten Cron zwar über
    ``maintenance_stale`` ab — aber ein Wächter, dessen Lebenszeichen
    ausschließlich von einem anderen Wächter kommt, ist eine Kette mit einem
    Glied zu wenig.
    """
    puls = (state or {}).get("puls")
    # GUARDIAN-NIT 09.08.2026: ein kaputter `puls`-Wert (String statt Dict) gab
    # einen AttributeError. Der wurde zwar fail-soft gefangen — aber VOR
    # `write_state`, `last_run_utc` waere also dauerhaft nicht mehr
    # fortgeschrieben worden. Der `maintenance_stale`-Backstop haette das nach
    # zehn Tagen gemeldet, den GRUND aber nie genannt.
    if not isinstance(puls, dict):
        if puls is not None:
            _warne(f"`puls` im State ist kein Objekt ({type(puls).__name__}) — "
                   f"behandelt wie ein fehlendes Lebenszeichen.")
        puls = {}
    return str(puls.get("last_month") or "") != now.strftime("%Y-%m")


def push_text(befunde: Sequence[Dict]) -> Tuple[str, str, str]:
    """(Titel, Text, Priorität) für den Befund-Push."""
    crit = [f for f in befunde if f["severity"] == CRIT]
    titel = ("Elliott-Wartung: Handlungsbedarf" if crit
             else "Elliott-Wartung: Befund")
    zeilen = [f"[{f['severity']}] {f['message']}" for f in befunde]
    return titel, " · ".join(zeilen), ("high" if crit else "default")


def run(topic: str, now: _dt.datetime, base: Optional[Path] = None,
        schreiben: bool = True) -> Dict:
    """Ein kompletter Wartungslauf. Gibt eine Zusammenfassung zurück."""
    warne_bei_import_fehler()
    state = load_state(base)
    gemeldet = list((state.get("einmalig") or []))
    heute = now.date()
    lauf_datum = heute.isoformat()

    befunde = sammle_befunde(heute, base=base, bereits_gemeldet=gemeldet)
    to_push, neuer_state = hc.evaluate_edges(befunde, state, lauf_datum)

    gepusht = False
    if to_push:
        titel, text, prio = push_text(to_push)
        gepusht = notify.send_ntfy(topic, titel, text, priority=prio,
                                   tags="wrench")
        for f in to_push:
            if f["rule"] in EINMALIG and f["rule"] not in gemeldet:
                gemeldet.append(f["rule"])
    else:
        _log(f"{len(befunde)} Befund(e), davon 0 auf der Flanke → kein Push.")

    # GENAU EIN PUSH PRO LAUF, wie beim Health-Check: der Puls kommt nur, wenn
    # es sonst nichts zu sagen gab. Zwei Pushes für denselben Lauf machen den
    # leisen wertlos.
    #
    # BEDINGUNG IST ``not befunde``, NICHT ``not to_push`` — der Unterschied ist
    # der Punkt (gefunden von `test_unveraenderter_befund_pusht_nicht_erneut`,
    # 09.08.2026): ein stehender Befund wird von der Warn-Drossel zwei Läufe
    # lang nicht gepusht. Hinge der Puls an ``to_push``, ginge in genau diesen
    # Läufen ein „alles sauber" raus, WÄHREND ein Warn-Befund steht. Ein
    # Lebenszeichen, das über einen offenen Befund hinwegmeldet, ist schlimmer
    # als keins.
    puls = False
    if not befunde and puls_faellig(now, state):
        puls = notify.send_ntfy(
            topic, "Elliott-Wartung: alles sauber",
            f"Wöchentliche Wartung {lauf_datum}: keine Befunde. Nächstes "
            f"Lebenszeichen im Folgemonat.",
            priority="low", tags="wrench,white_check_mark")

    neuer_state["einmalig"] = sorted(gemeldet)
    neuer_state["puls"] = ({"last_month": now.strftime("%Y-%m"),
                            "last_run_date": lauf_datum} if puls
                           else (state.get("puls") or {}))
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    if schreiben:
        write_state(neuer_state, now_iso, base)

    for f in befunde:
        _log(f"[{f['severity']}] {f['rule']}: {f['message']}")
    _log(f"Wartung {lauf_datum}: {len(befunde)} Befund(e), "
         f"{len(to_push)} auf der Flanke, Push "
         f"{'gesendet' if gepusht else 'nein'}, Puls "
         f"{'gesendet' if puls else 'nein'}.")
    return {"befunde": befunde, "gepusht": bool(gepusht), "puls": bool(puls),
            "state": neuer_state}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true",
                   help="Prüfen und melden, aber keinen State schreiben.")
    a = p.parse_args(argv)
    now = _dt.datetime.now(_dt.timezone.utc)
    topic = os.environ.get("NTFY_TOPIC", "")
    try:
        run(topic, now, schreiben=not a.dry_run)
    except Exception as exc:  # noqa: BLE001
        # Fail-soft wie überall — ABER laut, und der Rückgabewert bleibt 0,
        # damit der `if: failure()`-Push des Workflows die einzige rote Stelle
        # bleibt und nicht doppelt meldet.
        _warne(f"Wartungslauf abgebrochen: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
