"""Sitzungs-Gate für manuelle Dispatches (daily.yml, 09.09.2026).

ANLASS: Diagnose vom selben Tag belegte, dass die Betriebsregel „keine
Hand-Dispatches während der Sitzungen" (docs/validation_registry.md,
seit 07.08.2026) bislang NUR Dokumentation war und trotzdem real und
regelmäßig verletzt wurde — 24 von 55 `in_session_creation`-Episoden nach
Regel-Einführung, zuletzt OXY/MRK (2026-09-08T18:54:35Z) und FCX
(2026-09-09T17:08:50Z), alle per Hand-Dispatch, alle innerhalb der
US-Sitzung.

GEWÄHLT: Option (a) HARTES GATE (statt reiner Warnung) — Begründung im
Workflow-Kommentar (`.github/workflows/daily.yml`) und im PR-Text: eine
reine Dokumentations-Regel IST bereits eine dauerhafte Warnung und wurde
trotzdem 24 Mal übergangen.

DIESE TESTS FÜHREN DAS ECHTE, EINGEBETTETE PYTHON-SKRIPT AUS dem neuen
Workflow-Schritt aus (per Extraktion + `exec`), nicht eine Nachbildung
davon — dieselbe Lehre wie an anderer Stelle in diesem Repo: Quelltext-
Nähe allein beweist kein Verhalten. Nur `datetime.datetime.now()` wird
eingefroren (per `sys.modules`-Tausch, ausschließlich für die Dauer des
`exec`); `in_session.py`/`market_calendar.py` selbst bleiben unverändert
und werden UNVERÄNDERT importiert (GRENZEN dieses Auftrags).
"""
from __future__ import annotations

import datetime as _echt_dt
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import in_session as ins  # noqa: E402

DAILY = (ROOT / ".github/workflows/daily.yml").read_text(encoding="utf-8")
MIDDAY = (ROOT / ".github/workflows/midday_report_refresh.yml").read_text(encoding="utf-8")
WATCHER = (ROOT / ".github/workflows/daily_retry_watcher.yml").read_text(encoding="utf-8")


def _extrahiere_gate_skript() -> str:
    """Holt den exakten Python-Quelltext aus dem `run:`-Heredoc des neuen
    Schritts — kein Nachbau, derselbe Text, der in der CI läuft."""
    start = DAILY.index("- name: Sitzungs-Gate (nur bei manuellem Dispatch)")
    heredoc_start = DAILY.index("<<'PY'\n", start) + len("<<'PY'\n")
    heredoc_ende = DAILY.index("\n          PY", heredoc_start)
    roh = DAILY[heredoc_start:heredoc_ende]
    # Die YAML-Einrückung (10 Leerzeichen vor jeder Heredoc-Zeile) entfernen —
    # tiefere Einrückung (Python-Blöcke/Fortsetzungszeilen) bleibt erhalten,
    # weil nur genau das feste Präfix abgeschnitten wird.
    praefix = " " * 10
    zeilen = [z[len(praefix):] if z.startswith(praefix) else z
             for z in roh.splitlines()]
    return "\n".join(zeilen)


GATE_SKRIPT = _extrahiere_gate_skript()


class _EingefrorenesDatetime(_echt_dt.datetime):
    """`datetime.datetime`-Unterklasse mit fest verdrahtetem `now()` — der
    Rest der Klasse (Parsing, Arithmetik, Zeitzonen) bleibt die echte
    Implementierung."""
    _fest: _echt_dt.datetime

    @classmethod
    def now(cls, tz=None):
        wert = cls._fest
        return wert.astimezone(tz) if tz is not None else wert


def _gate_ausfuehren(monkeypatch, iso_utc: str, capsys):
    """Führt GATE_SKRIPT mit eingefrorener Zeit `iso_utc` aus.

    `datetime.datetime.now()` wird NUR für die Dauer dieses `exec`-Aufrufs
    ersetzt (per `sys.modules`-Tausch — `monkeypatch` macht das automatisch
    rückgängig). `in_session`/`market_calendar` bleiben die echten,
    unveränderten Module — sie lesen `now()` nirgends selbst, sondern
    bekommen den Stempel als Parameter durchgereicht.
    """
    fest = _echt_dt.datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))

    class _Eingefroren(_EingefrorenesDatetime):
        _fest = fest

    fake_datetime_modul = types.ModuleType("datetime")
    for name in dir(_echt_dt):
        if not name.startswith("__"):
            setattr(fake_datetime_modul, name, getattr(_echt_dt, name))
    fake_datetime_modul.datetime = _Eingefroren

    monkeypatch.setitem(sys.modules, "datetime", fake_datetime_modul)
    monkeypatch.chdir(ROOT)  # `sys.path.insert(0, "scripts")` im Skript ist relativ

    exit_code = None
    try:
        exec(compile(GATE_SKRIPT, "<sitzungs-gate>", "exec"), {"__name__": "__main__"})
    except SystemExit as exc:
        exit_code = exc.code
    ausgabe = capsys.readouterr().out
    return exit_code, ausgabe


# ---------------------------------------------------------------------------
# (a) Wert-Test — echte OXY/MRK/FCX-Zeitpunkte aus der Diagnose
# ---------------------------------------------------------------------------
def test_gate_blockiert_den_echten_oxy_mrk_dispatch(monkeypatch, capsys):
    """OXY/MRK @ 2026-09-08T18:54:35Z — laut `forward_collection.json` der
    reale, in_session_creation-markierte Dispatch aus der Diagnose."""
    # Gegenprobe an der echten, unveränderten Funktion (Beleg, dass der
    # gewählte Zeitpunkt wirklich in der US-Sitzung liegt, nicht nur
    # behauptet wird):
    assert ins.im_sitzungsfenster("US", "2026-09-08T18:54:35Z") is True

    exit_code, ausgabe = _gate_ausfuehren(monkeypatch, "2026-09-08T18:54:35Z", capsys)
    assert exit_code == 1, "Gate haette den echten OXY/MRK-Dispatch blockieren muessen"
    assert "US: Sitzung läuft" in ausgabe
    assert "::error::" in ausgabe


def test_gate_blockiert_den_echten_fcx_dispatch(monkeypatch, capsys):
    """FCX @ 2026-09-09T17:08:50Z — derselbe Beleg für den dritten Fall."""
    assert ins.im_sitzungsfenster("US", "2026-09-09T17:08:50Z") is True

    exit_code, ausgabe = _gate_ausfuehren(monkeypatch, "2026-09-09T17:08:50Z", capsys)
    assert exit_code == 1, "Gate haette den echten FCX-Dispatch blockieren muessen"
    assert "US: Sitzung läuft" in ausgabe


# ---------------------------------------------------------------------------
# (b) Regressionstest — Dispatch AUSSERHALB der Sitzung bleibt erlaubt
# ---------------------------------------------------------------------------
def test_gate_erlaubt_dispatch_ausserhalb_der_sitzung(monkeypatch, capsys):
    """03:00 UTC liegt vor NYSE-Oeffnung (09:30 ET = fruehestens 13:30 UTC im
    Sommer) UND vor Xetra-Oeffnung (09:00 CEST = 07:00 UTC) — die meisten
    bisherigen ERFOLGREICHEN Hand-Dispatches liefen ausserhalb der Sitzung;
    dieses Verhalten darf sich nicht aendern."""
    assert ins.im_sitzungsfenster("US", "2026-09-08T03:00:00Z") is False
    assert ins.im_sitzungsfenster("DE", "2026-09-08T03:00:00Z") is False

    exit_code, ausgabe = _gate_ausfuehren(monkeypatch, "2026-09-08T03:00:00Z", capsys)
    assert exit_code is None, "ein Dispatch ausserhalb der Sitzung darf NICHT blockiert werden"
    assert "Dispatch erlaubt" in ausgabe


# ---------------------------------------------------------------------------
# (c) None = nicht berechenbar -> LAUT behandeln (Vertrag von
#     `im_sitzungsfenster`, s. Docstring in_session.py) — NIE still
#     durchlassen.
# ---------------------------------------------------------------------------
def test_gate_blockiert_bei_nicht_berechenbarem_sitzungsfenster(monkeypatch, capsys):
    monkeypatch.setattr(ins, "im_sitzungsfenster", lambda markt, stempel: None)
    exit_code, ausgabe = _gate_ausfuehren(monkeypatch, "2026-09-08T03:00:00Z", capsys)
    assert exit_code == 1, (
        "None (nicht berechenbar) muss blockieren, nicht still als "
        "'nicht in Sitzung' durchgehen — sonst waere das Gate ausgerechnet "
        "dann wirkungslos, wenn es am wenigsten vertrauenswuerdig ist")
    assert "nicht berechenbar" in ausgabe


# ---------------------------------------------------------------------------
# (d) Struktur: schedule-Läufe strukturell ausgeschlossen, Positionierung
#     vor "Run pipeline"
# ---------------------------------------------------------------------------
def test_gate_schritt_nur_bei_workflow_dispatch():
    start = DAILY.index("- name: Sitzungs-Gate (nur bei manuellem Dispatch)")
    naechster_schritt = DAILY.index("- name:", start + 1)
    block = DAILY[start:naechster_schritt]
    assert "if: github.event_name == 'workflow_dispatch'" in block, (
        "das Gate muss strukturell (per `if:`) auf workflow_dispatch "
        "beschraenkt sein — ein schedule-Lauf darf es NIE erreichen, "
        "nicht nur zufaellig nie waehrend einer Sitzung laufen")


def test_gate_schritt_steht_vor_run_pipeline():
    """Bedingung fuer Option (a): kein Kandidat/keine Episode darf entstehen,
    BEVOR das Gate entschieden hat."""
    gate_pos = DAILY.index("- name: Sitzungs-Gate (nur bei manuellem Dispatch)")
    pipeline_pos = DAILY.index("- name: Run pipeline")
    assert gate_pos < pipeline_pos


def test_gate_ruft_die_unveraenderte_sitzungsfenster_funktion_auf():
    assert "ins.im_sitzungsfenster(markt, jetzt)" in DAILY
    assert 'for markt in ("US", "DE")' in DAILY


def test_schedule_cron_unveraendert():
    """Reine Gegenprobe: der bestehende 22:45-UTC-Cron (nie waehrend einer
    Sitzung) bleibt unangetastet — GRENZEN dieses Auftrags."""
    assert 'cron: "45 22 * * 1-5"' in DAILY
    assert DAILY.count("- cron:") == 1


# ---------------------------------------------------------------------------
# (e) Der neue Mittagslauf (#124) ist vom Gate nicht betroffen
# ---------------------------------------------------------------------------
def test_midday_workflow_bleibt_von_diesem_auftrag_unangetastet():
    """GRENZEN: keine Aenderung an midday_report_refresh.yml — nur
    sicherstellen, dass das neue Gate (das ausschliesslich in daily.yml
    lebt) ihn strukturell gar nicht erreichen kann."""
    assert "Sitzungs-Gate" not in MIDDAY
    assert "im_sitzungsfenster" not in MIDDAY
    # Eigene, unabhaengige Datei — kein `workflow_run`/`needs`-Bezug zu
    # daily.yml (eine reine Kommentar-Erwaehnung des Namens, z. B. beim
    # Cron-Zeitvergleich, ist harmlos und bleibt unbeanstandet).
    assert "workflow_run" not in MIDDAY
    assert "needs:" not in MIDDAY


def test_retry_watcher_111_unveraendert():
    """GRENZEN: keine Aenderung an #111 selbst."""
    assert 'workflows: ["Daily Elliott Report"]' in WATCHER
    assert "types: [completed]" in WATCHER


# ---------------------------------------------------------------------------
# (f) Determinismus — kein Netzzugriff, kein Zufall im Gate-Skript selbst
# ---------------------------------------------------------------------------
def test_gate_skript_ist_deterministisch_kein_netz_kein_zufall():
    for verboten in ("requests", "yfinance", "random", "urllib", "socket"):
        assert verboten not in GATE_SKRIPT, (
            f"Gate-Skript importiert/nutzt '{verboten}' — muss rein lokal "
            "und deterministisch bleiben (nur die Stempel-Uhrzeit selbst)")
