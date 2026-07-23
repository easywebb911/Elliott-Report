"""Handelskalender: Voll-Schließtag-Gate, Ablauf-Warnung und — kritisch — die
kalenderbewusste Staleness ohne Wochenend-/Feiertags-Fehlalarm (Querbezug #22).
"""
import datetime as _dt

import market_calendar as cal

UTC = _dt.timezone.utc


def _at(y, m, d, h=6, mi=0):
    return _dt.datetime(y, m, d, h, mi, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Gate / Feiertagsliste
# ---------------------------------------------------------------------------
def test_full_closure_common_holidays():
    assert cal.is_full_closure(_dt.date(2026, 1, 1)) == "Neujahr"
    assert cal.is_full_closure(_dt.date(2026, 4, 3)) == "Karfreitag"     # Good Friday
    assert cal.is_full_closure(_dt.date(2026, 12, 25)) == "1. Weihnachtstag"
    assert cal.is_full_closure(_dt.date(2027, 3, 26)) == "Karfreitag"
    # Einzelmarkt-Feiertage sind NICHT gelistet (Lauf läuft dann normal):
    assert cal.is_full_closure(_dt.date(2026, 7, 3)) is None    # US July-4-Umfeld
    assert cal.is_full_closure(_dt.date(2026, 5, 1)) is None    # DE Tag der Arbeit
    assert cal.is_full_closure(_dt.date(2026, 7, 27)) is None   # normaler Mo


def test_holiday_list_expiry_warning():
    assert cal.holiday_list_expiring(_dt.date(2027, 11, 30)) is False
    assert cal.holiday_list_expiring(_dt.date(2027, 12, 1)) is True     # ab Ablauf
    assert cal.holiday_list_expiring(_dt.date(2028, 1, 1)) is True


def test_is_trading_day():
    assert cal.is_trading_day(_dt.date(2026, 7, 24)) is True    # Freitag
    assert cal.is_trading_day(_dt.date(2026, 7, 25)) is False   # Samstag
    assert cal.is_trading_day(_dt.date(2026, 7, 26)) is False   # Sonntag
    assert cal.is_trading_day(_dt.date(2026, 4, 3)) is False    # Karfreitag


# ---------------------------------------------------------------------------
# last_expected_run — Wochenende/Feiertag überspringen
# ---------------------------------------------------------------------------
def test_last_expected_run_skips_weekend():
    # 2026-07-24 = Freitag. Am Sonntag/Montag früh ist der letzte erwartete
    # Lauf der Freitag (kein Sa/So-Lauf).
    assert cal.last_expected_run(_at(2026, 7, 26)) == _at(2026, 7, 24, 21, 45)  # So
    assert cal.last_expected_run(_at(2026, 7, 27)) == _at(2026, 7, 24, 21, 45)  # Mo früh


def test_last_expected_run_skips_holiday(monkeypatch):
    # Montag als Voll-Schließtag → am Dienstag früh ist der Freitag der letzte
    # erwartete Lauf (Montag zählt nicht).
    monkeypatch.setitem(cal.FULL_CLOSURE, "2026-07-27", "TestFeiertag")
    assert cal.last_expected_run(_at(2026, 7, 28)) == _at(2026, 7, 24, 21, 45)


# ---------------------------------------------------------------------------
# Staleness — die 4 Punkt-4-Szenarien (KEIN Fehlalarm bei Kalenderlücke)
# ---------------------------------------------------------------------------
def test_no_alarm_monday_after_normal_weekend():
    # Report vom Freitag, Montag früh → NICHT stale.
    assert cal.is_stale("2026-07-24T21:45:00Z", _at(2026, 7, 27)) is False


def test_no_alarm_sunday():
    assert cal.is_stale("2026-07-24T21:45:00Z", _at(2026, 7, 26)) is False


def test_alarm_on_real_monday_outage():
    # Dienstag früh, Montags-Lauf fehlte (Report noch vom Freitag) → STALE.
    assert cal.is_stale("2026-07-24T21:45:00Z", _at(2026, 7, 28)) is True


def test_no_alarm_after_holiday_monday(monkeypatch):
    # Montag war Voll-Schließtag, Report vom Freitag, Dienstag früh → NICHT stale.
    monkeypatch.setitem(cal.FULL_CLOSURE, "2026-07-27", "TestFeiertag")
    assert cal.is_stale("2026-07-24T21:45:00Z", _at(2026, 7, 28)) is False


def test_stale_on_unreadable_or_missing_ts():
    assert cal.is_stale(None, _at(2026, 7, 28)) is True
    assert cal.is_stale("kaputt", _at(2026, 7, 28)) is True


def test_fresh_report_same_day_not_stale():
    # Report von heute 21:45, Prüfung am nächsten Morgen → frisch.
    assert cal.is_stale("2026-07-28T21:45:00Z", _at(2026, 7, 29)) is False


# ---------------------------------------------------------------------------
# Pipeline-Gate: an Feiertagen return 0, NICHTS geschrieben (echter Modus)
# ---------------------------------------------------------------------------
def test_pipeline_gate_skips_on_holiday(monkeypatch):
    import elliott_pipeline as pipe

    # Echter Modus (nicht fetch_synthetic) erzwingen + heutigen Tag als
    # Voll-Schließtag markieren.
    monkeypatch.setattr(pipe, "get_fetcher", lambda: (lambda t: None))
    monkeypatch.setattr(cal, "is_full_closure", lambda d: "TestFeiertag")
    monkeypatch.setattr(cal, "holiday_list_expiring", lambda d: False)
    wrote = {"report": False}
    monkeypatch.setattr(pipe, "write_report",
                        lambda r: wrote.__setitem__("report", True) or [])

    rc = pipe.main()
    assert rc == 0
    assert wrote["report"] is False   # Feiertag -> nichts geschrieben


def test_pipeline_gate_logs_expiry_but_runs_when_list_ok(monkeypatch):
    # Kein Feiertag -> Gate lässt durch (kein return 0 durch das Gate selbst).
    # Wir prüfen nur, dass is_full_closure=None NICHT zum frühen Ausstieg führt,
    # indem wir bis zur Probe kommen (Probe fail-soft gemockt).
    import elliott_pipeline as pipe
    monkeypatch.setattr(pipe, "get_fetcher", lambda: (lambda t: None))
    monkeypatch.setattr(cal, "is_full_closure", lambda d: None)
    monkeypatch.setattr(cal, "holiday_list_expiring", lambda d: True)  # Warnung
    reached = {"probe": False}
    monkeypatch.setattr(pipe, "probe_ticker",
                        lambda t="AAPL": reached.__setitem__("probe", True))
    # build_report abkürzen, damit kein Netz nötig ist.
    monkeypatch.setattr(pipe, "build_report", lambda *a, **k: (_ for _ in ()).throw(
        SystemExit("stop-after-gate")))
    try:
        pipe.main()
    except SystemExit:
        pass
    assert reached["probe"] is True   # kein Feiertag -> Probe wurde erreicht
