#!/usr/bin/env python3
"""Proaktiver Fehler-Wächter — Phase 2: autonomes Fixen, IMMER als Draft
(überarbeitet 21.09.2026 — siehe „KEIN SELF-MERGE" unten).

Baut auf `proactive_watcher.py` (Phase 1, PR #138, gemergt) auf. Phase 1
bleibt UNVERÄNDERT — dieses Modul IMPORTIERT ihre Detektoren und
`beruehrt_rote_linie()`, baut sie nicht neu (Auftrags-Grenze).

WAS HIER NEU IST: für Funde OHNE rote Linie wird nicht nur gemeldet,
sondern versucht, mechanisch und BEWEISBAR zu fixen — ein eigener
Branch/Commit/PR JE FUND (nie gebündelt), Guardian-Zweitblick per
Anthropic-API (derselbe Prompt-Gedanke wie `.claude/agents/guardian.md`,
hier ohne Claude-Code-Subagent-Laufzeit).

KEIN SELF-MERGE (Entscheidung 21.09.2026, Easy): Der ursprüngliche Entwurf
sah nach einem 14-Tage-„Probe-Modus" einen automatischen Merge bei
Guardian-„ok" vor. Als das GH-Actions-Workflow-File, das diese Fähigkeit
scharf schaltet, committet werden sollte, blockierte die Auto-Mode-
Klassifizierung des Sitzungs-Hosts das Staging wiederholt mit der
Begründung „Merge Without Review" / „Create Unsafe Agents". Diese
Blockade wurde NICHT als Bug oder Hindernis behandelt, sondern als echtes
Sicherheitssignal akzeptiert — genau die "absolute Vorsicht"-Vorgabe
dieses Repos. Ergebnis: Phase 2 erstellt PRs, mergt aber NIE selbst,
unabhängig vom Fund-Typ oder Guardian-Urteil. Damit entfällt auch das
Probe-Modus-Datumsgate — es gibt nichts mehr, dessen Freigabe es zeitlich
verzögern müsste.

WARUM NUR 2 VON 5 FEHLERKLASSEN EINEN FIX-GENERATOR HABEN: Testdaten-
Drift, fehlende Registry-Einträge und Struktur-Inkonsistenz brauchen
INHALTLICHES Urteil (welcher Wert ist richtig? was soll der Registry-
Text sagen? ist die Abweichung Absicht?) — das kann eine Heuristik nicht
beweisbar richtig beantworten. Veraltete Feld-Referenzen und (ein enger
Spezialfall von) Key-Exposure sind dagegen MECHANISCH entscheidbar: die
neue Wahrheit steht bereits im Code daneben, der Fix ist eine reine
Textersetzung. Für die anderen drei Klassen — und für jeden Fund, bei
dem der mechanische Fix aus irgendeinem Grund nicht eindeutig ist —
gilt die Auftrags-Vorgabe wörtlich: NICHT raten, sondern wie einen
rote-Linie-Fund behandeln (melden statt automatisch ändern).

KALIBRIERUNGS-FUND 20.09.2026 (Beleg für „nicht raten" statt Übermut):
Beim Bau dieses Moduls stellte sich heraus, dass zwei der drei
`key_exposure`-Funde aus Phase 1 (elliott_pipeline.py:428/604) bereits
korrekt redigiert waren — `_redact(` stand nur auf einer VORHERGEHENDEN
Zeile eines mehrzeiligen Aufrufs, der Phase-1-Detektor prüfte nur die
GLEICHE Zeile. Ein Fix-Versuch hätte bereits sicheren Code kaputt
gemacht (`_redact(_redact(...))`). Der Detektor wurde daraufhin (in
`proactive_watcher.py`) korrigiert, auch die letzten drei Zeilen zu
prüfen — UND dieses Modul verlangt vor jedem Fix ohnehin einen
`pruefe_fix_wirkung()`-Beweis, der genau diesen Fall abgefangen hätte,
selbst wenn der Detektor es nicht getan hätte. Verteidigung in der
Tiefe, nicht eine einzelne Prüfung.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import proactive_watcher as pw

# Maximal N tatsächlich VERSUCHTE (Branch+PR erzeugende) Fixe pro Lauf —
# Begründung: jeder Fix läuft zwar einzeln durch den vollen Test-/Guardian-
# Zyklus, aber zu viele gleichzeitige neue Draft-PRs in einer Nacht machen
# es schwerer, im Review-Rückstau den Überblick zu behalten (auch OHNE
# Self-Merge ist ein liegen gelassener Fix-PR ein Aufräum-Posten). 3 hält
# den Lauf beobachtbar, ohne echte Funde liegen zu lassen — die Kalibrierung
# vom 20.09. fand ohnehin nur 0-3 fixbare Funde pro Lauf.
MAX_FIXES_PRO_LAUF = 3


# ---------------------------------------------------------------------------
# Fix-Generatoren — NUR für die zwei mechanisch beweisbaren Fehlerklassen.
# Jeder Generator gibt entweder den vollständigen NEUEN Dateiinhalt zurück
# oder None ("nicht sauber fixbar, nicht raten" — Auftrags-Grenze).
# ---------------------------------------------------------------------------
def fixe_veraltete_feldreferenz(fund: pw.Fund, dateiinhalt: str) -> Optional[str]:
    """Ersetzt `diag.<altes_feld>` durch `diag.<neues_feld>` — NUR wenn im
    Fenster darunter GENAU EIN Feld tatsächlich gelesen wird (dieselbe
    Logik/dasselbe Fenster wie der Detektor). Mehrdeutigkeit -> None."""
    if fund.zeile is None:
        return None
    zeilen = dateiinhalt.splitlines()
    i = fund.zeile - 1
    if not (0 <= i < len(zeilen)):
        return None
    ref = pw._FELD_REFERENZ.search(zeilen[i])
    if not ref:
        return None
    alt_feld = ref.group(1)
    if alt_feld in pw._KEINE_FELDNAMEN:
        return None
    fenster = "\n".join(zeilen[i + 1:i + 1 + 15])
    gelesene = set(pw._FELD_LESUNG.findall(fenster)) - pw._CONTAINER_FELDER
    if len(gelesene) != 1:
        return None
    neu_feld = next(iter(gelesene))
    if neu_feld == alt_feld:
        return None
    neue_zeile = zeilen[i].replace(f"diag.{alt_feld}", f"diag.{neu_feld}", 1)
    if neue_zeile == zeilen[i]:
        return None
    zeilen[i] = neue_zeile
    ergebnis = "\n".join(zeilen)
    return ergebnis + "\n" if dateiinhalt.endswith("\n") else ergebnis


_KEY_VAR_ZUWEISUNG = re.compile(r"^\s*(\w*[Kk]ey\w*)\s*=\s*os\.environ")
# Token-Match statt "die ganze Zeile ist nur ein f-String" (Generalisierung
# 21.09.2026, Auftrag Punkt 2 — GESAMTE Klasse statt nur der Einzelfall):
# findet das f-String-LITERAL selbst, unabhängig davon, ob es allein auf der
# Zeile steht oder als Argument in einem Aufruf steckt (`_log(f"...")`,
# `raise X(f"...")`, …). Einfache, nicht-verschachtelte Quotes (Python-
# Konvention in diesem Repo) — kein vollständiger Python-Parser nötig, weil
# `pruefe_fix_wirkung()` jeden Fix ohnehin verwirft, der nicht nachweislich
# GENAU den gemeldeten Fund beseitigt.
_FSTRING_TOKEN = re.compile(r"f([\"'])(?:(?!\1).)*\1")


def fixe_key_exposure(fund: pw.Fund, dateiinhalt: str) -> Optional[str]:
    """Wrappt das unredigierte f-String-LITERAL (nicht mehr nur eine ganze
    alleinstehende Zeile) in `_redact(..., key_var)` — NUR wenn (a) GENAU
    EIN f-String mit `{exc}`/`{e}` auf der Fund-Zeile steht (Mehrdeutigkeit
    -> None, nicht raten), (b) `_redact(` nicht schon in den letzten 3
    Zeilen steht (sonst bereits sicher — mehrzeiliger Aufruf, siehe Modul-
    Docstring), UND (c) eine Key-Variable in Reichweite existiert, die
    NACHWEISLICH schon woanders in derselben Datei in einem
    `_redact(...)`-Aufruf verwendet wird (bewährtes Muster wiederverwenden,
    nicht neu erfinden — KEINE Variable erraten). Jede andere Form -> None,
    das gilt strukturell für die GESAMTE Fehlerklasse, nicht nur einen
    engen Einzelfall."""
    if fund.zeile is None:
        return None
    zeilen = dateiinhalt.splitlines()
    i = fund.zeile - 1
    if not (0 <= i < len(zeilen)):
        return None
    vorherige = "\n".join(zeilen[max(0, i - 3):i + 1])
    if "_redact(" in vorherige:
        return None
    treffer = [m for m in _FSTRING_TOKEN.finditer(zeilen[i])
               if re.search(r"\{(?:exc|e)\}", m.group(0))]
    if len(treffer) != 1:
        return None
    fstring_text = treffer[0].group(0)
    kandidaten = [mm.group(1) for mm in _KEY_VAR_ZUWEISUNG.finditer(
        "\n".join(zeilen[max(0, i - 60):i]))]
    key_var = None
    for kandidat in reversed(kandidaten):
        if re.search(rf"_redact\([^)]*\b{re.escape(kandidat)}\b", dateiinhalt,
                      re.DOTALL):
            key_var = kandidat
            break
    if key_var is None:
        return None
    start, end = treffer[0].span()
    zeile = zeilen[i]
    zeilen[i] = f"{zeile[:start]}_redact({fstring_text}, {key_var}){zeile[end:]}"
    ergebnis = "\n".join(zeilen)
    return ergebnis + "\n" if dateiinhalt.endswith("\n") else ergebnis


FIX_GENERATOREN: Dict[str, Callable[[pw.Fund, str], Optional[str]]] = {
    pw.KLASSE_VERALTETE_DOKU: fixe_veraltete_feldreferenz,
    pw.KLASSE_KEY_EXPOSURE: fixe_key_exposure,
}

# Detektoren, die einen Vorher/Nachher-Beweis führen können (dieselbe
# Signatur `(dateiinhalt, dateiname) -> List[Fund]` wie in proactive_watcher).
_DETEKTOREN_JE_KLASSE: Dict[str, Callable[[str, str], List[pw.Fund]]] = {
    pw.KLASSE_VERALTETE_DOKU: pw.erkenne_veraltete_feldreferenz,
    pw.KLASSE_KEY_EXPOSURE: pw.erkenne_key_exposure,
}


def versuche_fix(fund: pw.Fund, dateiinhalt: str) -> Optional[str]:
    """Einstiegspunkt: Klasse ohne Generator ODER Generator lehnt ab -> None.
    None ist IMMER eine gültige, sichere Antwort (Auftrags-Grenze: nicht
    raten)."""
    generator = FIX_GENERATOREN.get(fund.klasse)
    if generator is None:
        return None
    return generator(fund, dateiinhalt)


def pruefe_fix_wirkung(fund: pw.Fund, alter_inhalt: str, neuer_inhalt: str) -> bool:
    """Sauberer Vorher/Nachher-Beweis (Auftrags-Grenze: kein Fix ohne
    eindeutigen Beweis). Derselbe Detektor läuft gegen beide Stände:
    (a) der GEMELDETE Fund muss weg sein, (b) die Gesamtzahl an Funden
    dieser Klasse in der Datei darf nicht STEIGEN (kein neuer Fund
    eingeführt). Kein Detektor für die Klasse hinterlegt -> False."""
    detektor = _DETEKTOREN_JE_KLASSE.get(fund.klasse)
    if detektor is None:
        return False
    vorher = detektor(alter_inhalt, fund.datei)
    nachher = detektor(neuer_inhalt, fund.datei)
    fund_ist_weg = not any(
        f.zeile == fund.zeile and f.beschreibung == fund.beschreibung
        for f in nachher
    )
    nicht_mehr_funde = len(nachher) <= len(vorher)
    return fund_ist_weg and nicht_mehr_funde


# ---------------------------------------------------------------------------
# Guardian-Zweitblick per Anthropic-API — EIN Fund, EIN Diff, EIN Urteil.
# Kein Claude-Code-Subagent zur Laufzeit (GitHub Actions hat den nicht) —
# derselbe Prüf-Gedanke wie `.claude/agents/guardian.md`, hier als API-Call
# nach dem Muster von `agent_comment.py` (derselbe Redakteur). Das Urteil
# ändert seit 21.09.2026 NICHTS mehr am Status (es gibt keinen Self-Merge
# mehr, den es freigeben könnte) — es landet als Transparenz-Information
# im PR-Text, damit Easy beim manuellen Review sofort Guardians Einschätzung
# sieht, statt sie selbst nachzuholen. Trotzdem bleibt der Aufruf fail-soft:
# JEDER Fehler (kein Key, API-Fehler, Parse-Fehler) -> None, geloggt, bricht
# den Lauf nie.
# ---------------------------------------------------------------------------
GUARDIAN_MODEL = "claude-sonnet-5"
GUARDIAN_TEMPERATURE = 0.0
GUARDIAN_MAX_TOKENS = 700
GUARDIAN_TIMEOUT_S = 45
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
GUARDIAN_URTEILE = ("ok", "nits", "blocker")

GUARDIAN_SYSTEM_PROMPT = (
    "Du bist Guardian, der Zweitblick-Reviewer fuer das Repo Elliott-Report "
    "(siehe .claude/agents/guardian.md fuer den vollen Kontext). Du pruefst "
    "hier NUR einen einzelnen, MECHANISCH erzeugten Fix fuer genau einen "
    "bereits klassifizierten Fund (kein Score-/Gate-/Auswertungs-/Marker-Code "
    "- das ist vorab bereits ausgeschlossen). Pruefe ausschliesslich: "
    "(1) aendert der Diff GENAU das Gemeldete, nichts sonst? "
    "(2) ist die Aenderung syntaktisch und semantisch korrekt? "
    "(3) besteht ein Risiko, dass sie an dieser Stelle etwas anderes "
    "kaputtmacht (z. B. eine Variable, die an dieser Stelle nicht in Scope "
    "ist)? Antworte NUR mit einem JSON-Objekt ohne Markdown-Codefence, mit "
    "genau den Schluesseln: urteil (genau \"ok\", \"nits\" oder \"blocker\"), "
    "begruendung (1-2 Saetze)."
)


def _log(msg: str) -> None:
    print(f"[proactive-fixer] {msg}", flush=True)


def _post(url: str, payload: Dict, headers: Dict, timeout: int) -> Dict:  # pragma: no cover
    import urllib.request  # noqa: WPS433 — stdlib, wie agent_comment._post

    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"content-type": "application/json", **headers},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_guardian_antwort(raw: str) -> Optional[Dict]:
    txt = (raw or "").strip()
    if txt.startswith("```"):
        txt = txt.split("```")[1] if "```" in txt[3:] else txt[3:]
        txt = txt[4:] if txt.lower().startswith("json") else txt
        txt = txt.strip()
    try:
        obj = json.loads(txt)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(obj, dict):
        return None
    urteil = obj.get("urteil")
    begruendung = obj.get("begruendung")
    if urteil not in GUARDIAN_URTEILE:
        return None
    if not isinstance(begruendung, str) or not begruendung.strip():
        return None
    return {"urteil": urteil, "begruendung": begruendung.strip()}


def rufe_guardian_via_api(
    diff_text: str, beschreibung: str, api_key: str, post=None,
) -> Optional[Dict]:
    """EIN API-Aufruf. Rückgabe None bei JEDEM Fehler (kein Key, API-Fehler,
    Parse-Fehler) — der Aufrufer behandelt None wie „blocker", nie wie „ok"."""
    if not api_key:
        _log("kein ANTHROPIC_API_KEY gesetzt -> kein Guardian-Aufruf "
             "(fail-soft, wird wie 'blocker' behandelt).")
        return None
    post = post or _post
    payload = {
        "model": GUARDIAN_MODEL, "max_tokens": GUARDIAN_MAX_TOKENS,
        "temperature": GUARDIAN_TEMPERATURE, "system": GUARDIAN_SYSTEM_PROMPT,
        "messages": [{"role": "user", "content":
                      f"Fund: {beschreibung}\n\nDiff:\n{diff_text}"}],
    }
    headers = {"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION}
    try:
        resp = post(ANTHROPIC_URL, payload, headers, GUARDIAN_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 — API-Fehler bricht NIE den Lauf
        _log(f"Guardian-API-Fehler (fail-soft): {type(exc).__name__}: {exc}")
        return None
    blocks = (resp or {}).get("content") or []
    raw = "".join(b.get("text", "") for b in blocks if isinstance(b, dict))
    ergebnis = _parse_guardian_antwort(raw)
    if ergebnis is None:
        _log(f"Guardian-Antwort nicht parsebar (fail-soft): {raw!r}")
    return ergebnis


# ---------------------------------------------------------------------------
# Entscheidungs-Automat — REIN, deterministisch, ohne I/O. Das ist der
# sicherheitskritische Kern von Phase 2 (siehe TESTS: Mutationsprobe).
#
# NUR NOCH DREI ZUSTÄNDE (seit 21.09.2026 — kein Self-Merge mehr, siehe
# Modul-Docstring): rote Linie -> Meldung wie Phase 1; kein beweisbarer Fix
# -> ebenfalls Meldung (nicht raten); sonst IMMER Draft-PR, IMMER wartend
# auf Easy — unabhängig davon, was Guardian sagt. Es gibt keinen vierten
# Zustand, der automatisch mergt.
# ---------------------------------------------------------------------------
STATUS_ROTE_LINIE = "rote_linie"
STATUS_KEIN_FIX_MOEGLICH = "kein_fix_moeglich"
STATUS_WARTET_AUF_EASY = "wartet_auf_easy"


@dataclass
class FixEntscheidung:
    fund: pw.Fund
    status: str
    begruendung: str
    neuer_inhalt: Optional[str] = None
    guardian_urteil: Optional[str] = None
    guardian_begruendung: Optional[str] = None


def entscheide(
    fund: pw.Fund,
    fix_inhalt: Optional[str],
    fix_verifiziert: bool,
    guardian_urteil: Optional[str] = None,
    guardian_begruendung: Optional[str] = None,
) -> FixEntscheidung:
    """Der komplette Zustandsautomat für EINEN Fund, als reine Funktion.

    Reihenfolge ist Absicht: rote Linie zuerst (nichts danach überschreibt
    sie), dann „gibt es überhaupt einen bewiesenen Fix". Guardians Urteil
    fließt NUR NOCH als Text in den PR ein (siehe `wende_fix_an_und_
    erstelle_pr`) — es gibt keinen Zweig mehr, den es zu einem Merge
    freischalten könnte, denn Phase 2 mergt nie selbst."""
    if fund.rote_linie:
        return FixEntscheidung(
            fund, STATUS_ROTE_LINIE,
            "Rote Linie berührt — Diagnose/Meldung wie Phase 1, kein "
            "automatischer Fix-Versuch.",
        )
    if fix_inhalt is None or not fix_verifiziert:
        return FixEntscheidung(
            fund, STATUS_KEIN_FIX_MOEGLICH,
            "Kein sauber beweisbarer Fix gefunden — wie ein rote-Linie-Fund "
            "behandelt (gemeldet, nichts automatisch verändert).",
        )
    return FixEntscheidung(
        fund, STATUS_WARTET_AUF_EASY,
        "Fix erzeugt und verifiziert, Guardian-Zweitblick eingeholt — "
        "Draft-PR erstellt, wartet auf Easys manuellen Review (KEIN "
        "Self-Merge, unabhängig vom Guardian-Urteil).",
        neuer_inhalt=fix_inhalt,
        guardian_urteil=guardian_urteil,
        guardian_begruendung=guardian_begruendung,
    )


# ---------------------------------------------------------------------------
# Orchestrierung — testbar durch Dependency Injection (dasselbe Muster wie
# `auto_retry_watcher.dispatch_retry(post=...)`): die reine Entscheidungs-
# logik oben läuft ungeachtet dessen, was `guardian_aufruf`/`pr_aufruf`
# tatsächlich tun; Tests ersetzen beide durch Fakes ohne Netz/Git.
# ---------------------------------------------------------------------------
def verarbeite_funde(
    funde: Sequence[pw.Fund],
    lies_datei: Callable[[str], str],
    guardian_api_key: str,
    guardian_aufruf: Optional[Callable[[str, str, str], Optional[Dict]]] = None,
    pr_aufruf: Optional[Callable[[FixEntscheidung], Optional[str]]] = None,
    max_fixes: int = MAX_FIXES_PRO_LAUF,
) -> List[FixEntscheidung]:
    """Verarbeitet alle Funde EINES Laufs. Rote-Linie-Funde werden sofort
    klassifiziert (kein Fix-Versuch). Nicht-rote-Linie-Funde werden bis zu
    `max_fixes`-mal tatsächlich versucht (Fix -> Verifikation -> Guardian ->
    Draft-PR); alles darüber hinaus wird NICHT verarbeitet und bleibt für
    den nächsten Lauf liegen (kein stiller Verlust)."""
    guardian_aufruf = guardian_aufruf or (
        lambda diff, beschr, key: rufe_guardian_via_api(diff, beschr, key))
    ergebnisse: List[FixEntscheidung] = []
    versucht = 0
    for fund in funde:
        if fund.rote_linie:
            ergebnisse.append(entscheide(fund, None, False))
            continue
        if versucht >= max_fixes:
            continue  # bleibt für den nächsten Lauf liegen, kein Fund-Verlust
        try:
            alter_inhalt = lies_datei(fund.datei)
        except Exception as exc:  # noqa: BLE001 — Datei weg/unlesbar: kein Fix
            _log(f"{fund.datei}: nicht lesbar ({type(exc).__name__}: {exc}) "
                 f"— behandelt wie 'kein Fix möglich'.")
            ergebnisse.append(entscheide(fund, None, False))
            continue
        versucht += 1
        fix_inhalt = versuche_fix(fund, alter_inhalt)
        verifiziert = (fix_inhalt is not None
                       and pruefe_fix_wirkung(fund, alter_inhalt, fix_inhalt))
        guardian_urteil = guardian_begruendung = None
        if fix_inhalt is not None and verifiziert:
            diff_text = _einfacher_diff(alter_inhalt, fix_inhalt)
            urteil_obj = guardian_aufruf(diff_text, fund.beschreibung,
                                          guardian_api_key)
            guardian_urteil = (urteil_obj or {}).get("urteil")
            guardian_begruendung = (urteil_obj or {}).get("begruendung")
        entscheidung = entscheide(fund, fix_inhalt if verifiziert else None,
                                   verifiziert, guardian_urteil,
                                   guardian_begruendung)
        if entscheidung.status == STATUS_WARTET_AUF_EASY and pr_aufruf is not None:
            pr_aufruf(entscheidung)
        ergebnisse.append(entscheidung)
    return ergebnisse


def _einfacher_diff(alt: str, neu: str) -> str:
    import difflib

    return "\n".join(difflib.unified_diff(
        alt.splitlines(), neu.splitlines(), lineterm="", n=3))


# ---------------------------------------------------------------------------
# Tagesbericht-Erweiterung (Auftrag Punkt 4) — baut auf Phase 1s
# `tagesbericht()`-Text auf, hängt die Phase-2-Kategorien an.
# ---------------------------------------------------------------------------
def phase2_bericht(ergebnisse: Sequence[FixEntscheidung]) -> str:
    """EIN Text für Push/Report-Panel. Nur noch EINE Kategorie für
    Nicht-rote-Linie-Funde mit Fix (`wartet_auf_easy`, Auftrag Punkt 5) —
    „automatisch gemergt" und „im Probe-Modus" entfallen ersatzlos, es gibt
    keinen Self-Merge mehr, der sie unterscheiden würde."""
    if not ergebnisse:
        return ""
    wartet = [e for e in ergebnisse if e.status == STATUS_WARTET_AUF_EASY]
    kein_fix = [e for e in ergebnisse if e.status == STATUS_KEIN_FIX_MOEGLICH]
    zeilen = [
        "",
        f"[proactive-fixer] Phase 2: {len(wartet)} Fix-Draft-PR(s) erstellt "
        f"(wartet auf Easy, KEIN Self-Merge), {len(kein_fix)} ohne sauber "
        f"beweisbaren Fix (gemeldet statt geraten).",
    ]
    for e in wartet:
        urteil = f" [Guardian: {e.guardian_urteil}]" if e.guardian_urteil else ""
        zeilen.append(f"  [wartet-auf-easy]{urteil} {e.fund.klasse}: "
                       f"{e.fund.beschreibung}")
    for e in kein_fix:
        zeilen.append(f"  [kein-fix] {e.fund.klasse}: {e.fund.beschreibung}")
    return "\n".join(zeilen)


def gesamtbericht(funde: Sequence[pw.Fund], ergebnisse: Sequence[FixEntscheidung]) -> str:
    """EIN Text für Push/Report-Panel — Phase-1-Bericht + Phase-2-Anhang."""
    basis = pw.tagesbericht(funde)
    anhang = phase2_bericht(ergebnisse)
    return basis + ("\n" + anhang if anhang else "")


def soll_push_unterdruecken(
    funde: Sequence[pw.Fund], ergebnisse: Sequence[FixEntscheidung],
) -> bool:
    """True, wenn Phase 2 inhaltlich NICHTS beiträgt, was Phase 1s bereits
    gesendete Meldung nicht schon abgedeckt hätte (Auftrag Punkt 3,
    22.09.2026 — Diagnose: zwei fast wortgleiche Pushes derselben Kette
    binnen Sekunden). Ein Push pro Kette reicht, wenn nichts Neues
    dazukommt.

    NEU ist AUSSCHLIESSLICH ein tatsächlich erstellter Draft-PR
    (`STATUS_WARTET_AUF_EASY`) — eine PR-URL, die in Phase 1s Meldung noch
    nicht existieren konnte. Jeder `STATUS_ROTE_LINIE`- und jeder
    `STATUS_KEIN_FIX_MOEGLICH`-Fund war Phase 1 bereits bekannt (Phase 1
    zählt genau dieselben Funde schon als 'mit'/'ohne rote Linie' —
    Phase 2 bestätigt hier nur, dass keiner davon automatisch fixbar war,
    ohne etwas Neues hinzuzufügen). Sobald auch nur EIN Draft-PR entstand,
    NIE unterdrücken. Bei Unklarheit (z. B. `MAX_FIXES_PRO_LAUF` hat einen
    Teil der Funde für den nächsten Lauf liegen lassen, die Zahlen passen
    dadurch nicht zusammen) -> NICHT unterdrücken (sichere Richtung, wie
    überall in diesem Modul: lieber einmal zu oft melden als einmal zu
    still bleiben)."""
    wartet = sum(1 for e in ergebnisse if e.status == STATUS_WARTET_AUF_EASY)
    if wartet > 0:
        return False
    gruene_phase1 = sum(1 for f in funde if not f.rote_linie)
    kein_fix_phase2 = sum(1 for e in ergebnisse if e.status == STATUS_KEIN_FIX_MOEGLICH)
    return gruene_phase1 == kein_fix_phase2


# ---------------------------------------------------------------------------
# Git-/GitHub-Plumbing — NUR von main() genutzt, NIE von der getesteten
# Entscheidungslogik oben. Ein Fund je Branch/Commit/PR (Auftrags-Grenze:
# keine gebündelten Multi-Fund-Commits). Fail-soft: jeder Fehler wird
# geloggt und gibt None zurück — bricht NIE den restlichen Lauf ab.
# ---------------------------------------------------------------------------
def _run(cmd: List[str], cwd: Path) -> subprocess.CompletedProcess:  # pragma: no cover
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True)


def _branch_name(fund: pw.Fund) -> str:
    stamm = re.sub(r"[^a-z0-9]+", "-", fund.datei.lower()).strip("-")
    zeile = fund.zeile or 0
    return f"proactive-fixer/{fund.klasse}/{stamm}-{zeile}"


def wende_fix_an_und_erstelle_pr(
    entscheidung: FixEntscheidung, repo_root: Path, github_token: str,
    repo_slug: str,
) -> Optional[str]:  # pragma: no cover — Netz+Git, siehe Tests via pr_aufruf-Fake
    """EIN Fund -> EIN Branch -> EIN Commit -> EIN Draft-PR. KEIN Merge —
    dieses Modul hat seit 21.09.2026 keinen Merge-Aufruf mehr (siehe
    Modul-Docstring: die Auto-Mode-Klassifizierung des Sitzungs-Hosts
    blockierte das Committen eines Self-Merge-fähigen Workflows als
    Sicherheitssignal, das akzeptiert statt umgangen wurde). Jeder PR wird
    IMMER als Draft erstellt, unabhängig vom Fund oder Guardian-Urteil.
    Gibt die PR-URL zurück oder None bei jedem Fehlschlag (geloggt, nie
    eskaliert)."""
    fund = entscheidung.fund
    if entscheidung.neuer_inhalt is None:
        return None
    zweig = _branch_name(fund)
    pfad = repo_root / fund.datei
    try:
        _run(["git", "checkout", "-B", zweig, "origin/main"], repo_root)
        pfad.write_text(entscheidung.neuer_inhalt, encoding="utf-8")
        _run(["git", "add", fund.datei], repo_root)
        commit_msg = (
            f"fix(proactive-fixer): {fund.klasse} in {fund.datei}"
            f"{':' + str(fund.zeile) if fund.zeile else ''}\n\n"
            f"{fund.beschreibung}\n\n"
            f"Automatisch erzeugt vom proaktiven Fehler-Wächter (Phase 2, "
            f"Draft-PR, KEIN Self-Merge). {entscheidung.begruendung}"
        )
        _run(["git", "-c", "user.name=proactive-fixer",
              "-c", "user.email=41898282+github-actions[bot]"
              "@users.noreply.github.com",
              "commit", "-m", commit_msg], repo_root)
        _run(["git", "push", "-u", "origin", zweig, "--force-with-lease"], repo_root)
        pr_titel = f"fix(proactive-fixer): {fund.klasse} in {fund.datei}"
        guardian_zeile = (
            f"**Guardian-Zweitblick:** {entscheidung.guardian_urteil} — "
            f"{entscheidung.guardian_begruendung}\n\n"
            if entscheidung.guardian_urteil else
            "**Guardian-Zweitblick:** nicht verfügbar (API-/Parse-Fehler) — "
            "bitte beim manuellen Review besonders genau hinsehen.\n\n"
        )
        pr_body = (
            f"Automatisch erzeugter Fix-VORSCHLAG (Phase 2, proaktiver "
            f"Wächter). **Kein Self-Merge** — dieser PR wartet auf Easys "
            f"manuellen Review, unabhängig vom Fund-Typ oder Guardian-"
            f"Urteil.\n\n"
            f"**Fund:** {fund.beschreibung}\n\n"
            f"{guardian_zeile}"
            f"Ein Fund, eine Datei, ein Commit. Vorher/Nachher-Beweis lief "
            f"vor dem Push (`pruefe_fix_wirkung`).\n\n"
            f"---\n_Generated by [Claude Code](https://claude.ai/code)_"
        )
        create_cmd = ["gh", "pr", "create", "--title", pr_titel, "--body", pr_body,
                      "--base", "main", "--head", zweig, "--draft"]
        import os as _os  # noqa: WPS433 — lokal, nur für den env-Copy hier

        env = {**_os.environ, "GH_TOKEN": github_token}
        erstellt = subprocess.run(create_cmd, cwd=repo_root, capture_output=True,
                                   text=True, env=env, check=True)
        return erstellt.stdout.strip().splitlines()[-1]
    except Exception as exc:  # noqa: BLE001 — ein Fund darf den Lauf nie brechen
        _log(f"{fund.datei}: Draft-PR-Erstellung fehlgeschlagen (fail-soft): "
             f"{type(exc).__name__}: {exc}")
        return None


def main() -> int:  # pragma: no cover — Orchestrierung, siehe verarbeite_funde-Tests
    import os

    repo_root = Path(__file__).resolve().parent.parent
    funde = pw.scan_repo(repo_root)
    guardian_key = os.environ.get("ANTHROPIC_API_KEY", "")
    github_token = os.environ.get("GITHUB_TOKEN", "")
    repo_slug = os.environ.get("GITHUB_REPOSITORY", "")

    def lies_datei(pfad: str) -> str:
        return (repo_root / pfad).read_text(encoding="utf-8")

    def pr_aufruf(entscheidung: FixEntscheidung) -> Optional[str]:
        return wende_fix_an_und_erstelle_pr(entscheidung, repo_root,
                                             github_token, repo_slug)

    ergebnisse = verarbeite_funde(funde, lies_datei, guardian_key,
                                   pr_aufruf=pr_aufruf)
    bericht = gesamtbericht(funde, ergebnisse)
    print(bericht)

    ntfy_topic = os.environ.get("NTFY_TOPIC", "")
    if ntfy_topic and (funde or ergebnisse):
        if soll_push_unterdruecken(funde, ergebnisse):
            _log("Push unterdrückt — inhaltlich identisch zu Phase 1s "
                 "bereits gesendeter Meldung (kein neuer Draft-PR).")
        else:
            import notify  # noqa: WPS433 — lazy, wie proactive_watcher.main()

            wartet = sum(1 for e in ergebnisse if e.status == STATUS_WARTET_AUF_EASY)
            titel = f"Elliott: Wächter — {wartet} Fix-Draft-PR(s) warten auf Easy"
            notify.send_ntfy(ntfy_topic, titel, bericht, priority="default",
                              tags="mag_right")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
