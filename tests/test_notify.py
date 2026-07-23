"""Push-Paket Stufe 1: jeden Anlass offline durchgespielt + Stumm-Beweis +
Drosseln + Topic-Handhabung (kein Leak) + Fail-soft.

Kein Netz: `notify._post` wird ersetzt und die Pushes werden mitgeschnitten.
"""
import datetime as _dt
import json

import notify


TOPIC = "easy-elliott-report"
MON = _dt.datetime(2026, 7, 27, 21, 45, tzinfo=_dt.timezone.utc)   # Montag
TUE = _dt.datetime(2026, 7, 28, 21, 45, tzinfo=_dt.timezone.utc)   # Dienstag


def _capture(monkeypatch):
    sent = []
    monkeypatch.setattr(
        notify, "_post",
        lambda url, data, headers, timeout: sent.append(
            {"url": url, "title": headers.get("Title"),
             "prio": headers.get("Priority"), "body": data.decode("utf-8")}))
    return sent


def _fixture_repo(tmp_path, monkeypatch, *, report_ts=None, matured=0, marker=False):
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    if report_ts is not None:
        (tmp_path / "data/report.json").write_text(
            json.dumps({"run_timestamp_utc": report_ts, "markets": {}}), encoding="utf-8")
    recs = [{"matured": True} for _ in range(matured)]
    (tmp_path / "data/forward_collection.json").write_text(
        json.dumps({"records": recs}), encoding="utf-8")
    if marker:
        (tmp_path / "data/validation_milestone_fired.flag").write_text("x", encoding="utf-8")
    monkeypatch.setattr(notify, "REPO_ROOT", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Pure Checks
# ---------------------------------------------------------------------------
def test_milestone_check():
    assert notify.milestone_reached(100, False) is True
    assert notify.milestone_reached(150, False) is True
    assert notify.milestone_reached(99, False) is False
    assert notify.milestone_reached(100, True) is False   # Marker -> schon gemeldet


def test_review_due_check():
    assert notify.review_due("2026-01-01", MON) is True        # überfällig + Montag
    assert notify.review_due("2027-01-01", MON) is False       # Zukunft
    assert notify.review_due("2026-01-01", TUE) is False       # nicht Montag
    assert notify.review_due(None, MON) is False               # abgeschaltet
    assert notify.review_due("nonsense", MON) is False         # fail-soft


# ---------------------------------------------------------------------------
# Anlass 1: Staleness (separater Cron)
# ---------------------------------------------------------------------------
def test_staleness_push_on_old_report(tmp_path, monkeypatch):
    _fixture_repo(tmp_path, monkeypatch, report_ts="2026-07-01T00:00:00Z")
    sent = _capture(monkeypatch)
    assert notify.run_staleness(TOPIC, MON) is True
    assert len(sent) == 1 and "veraltet" in sent[0]["title"].lower()


def test_staleness_silent_on_fresh_report(tmp_path, monkeypatch):
    _fixture_repo(tmp_path, monkeypatch, report_ts="2026-07-27T18:00:00Z")
    sent = _capture(monkeypatch)
    assert notify.run_staleness(TOPIC, MON) is False
    assert sent == []


def test_staleness_push_when_report_missing(tmp_path, monkeypatch):
    # „Lauf fand gar nicht statt" / report.json fehlt -> Staleness-Signal.
    _fixture_repo(tmp_path, monkeypatch, report_ts=None)  # keine report.json
    sent = _capture(monkeypatch)
    assert notify.run_staleness(TOPIC, MON) is True
    assert len(sent) == 1


# ---------------------------------------------------------------------------
# Anlass 2: Meilenstein n>=100 (einmalig, Marker gegen Wiederholung)
# ---------------------------------------------------------------------------
def test_milestone_push_and_marker_written(tmp_path, monkeypatch):
    _fixture_repo(tmp_path, monkeypatch, report_ts="2026-07-27T18:00:00Z", matured=100)
    monkeypatch.setattr(notify, "SCORE_REVIEW_BY", "2027-01-01")  # Review aus
    sent = _capture(monkeypatch)
    out = notify.run_daily(TOPIC, TUE)
    assert out["milestone"] is True and len(sent) == 1
    assert "Auswertung" in sent[0]["title"]
    assert (tmp_path / "data/validation_milestone_fired.flag").exists()  # Marker gesetzt


def test_milestone_throttled_by_marker(tmp_path, monkeypatch):
    _fixture_repo(tmp_path, monkeypatch, report_ts="2026-07-27T18:00:00Z",
                  matured=120, marker=True)
    monkeypatch.setattr(notify, "SCORE_REVIEW_BY", "2027-01-01")
    sent = _capture(monkeypatch)
    out = notify.run_daily(TOPIC, TUE)
    assert out["milestone"] is False and sent == []   # Marker -> kein Doppel-Push


# ---------------------------------------------------------------------------
# Anlass 3: Review-Wecker (überfällig, ~1x/Woche)
# ---------------------------------------------------------------------------
def test_review_push_on_monday_when_overdue(tmp_path, monkeypatch):
    _fixture_repo(tmp_path, monkeypatch, report_ts="2026-07-27T18:00:00Z", matured=5)
    monkeypatch.setattr(notify, "SCORE_REVIEW_BY", "2026-01-01")   # überfällig
    sent = _capture(monkeypatch)
    out = notify.run_daily(TOPIC, MON)                             # Montag
    assert out["review"] is True and len(sent) == 1
    assert "Review" in sent[0]["title"]


def test_review_silent_midweek(tmp_path, monkeypatch):
    _fixture_repo(tmp_path, monkeypatch, report_ts="2026-07-27T18:00:00Z", matured=5)
    monkeypatch.setattr(notify, "SCORE_REVIEW_BY", "2026-01-01")
    sent = _capture(monkeypatch)
    out = notify.run_daily(TOPIC, TUE)                             # Dienstag
    assert out["review"] is False and sent == []                  # Drossel greift


# ---------------------------------------------------------------------------
# STUMM-BEWEIS: Normal-Lauf erzeugt NULL Pushes
# ---------------------------------------------------------------------------
def test_normal_run_is_silent(tmp_path, monkeypatch):
    _fixture_repo(tmp_path, monkeypatch, report_ts="2026-07-27T18:00:00Z", matured=12)
    monkeypatch.setattr(notify, "SCORE_REVIEW_BY", "2027-12-31")   # Review in Zukunft
    sent = _capture(monkeypatch)
    out = notify.run_daily(TOPIC, TUE)     # kein Meilenstein, kein Review, Dienstag
    assert out == {"milestone": False, "review": False}
    # und der Staleness-Cron ist bei frischem Report ebenfalls stumm:
    assert notify.run_staleness(TOPIC, TUE) is False
    assert sent == []                       # NULL Pushes im Normalbetrieb


# ---------------------------------------------------------------------------
# Topic-Handhabung (kein Leak) + Fail-soft
# ---------------------------------------------------------------------------
def test_empty_topic_never_posts(tmp_path, monkeypatch):
    _fixture_repo(tmp_path, monkeypatch, report_ts="2026-07-01T00:00:00Z", matured=100)
    monkeypatch.setattr(notify, "SCORE_REVIEW_BY", "2026-01-01")
    sent = _capture(monkeypatch)
    # Trotz aller Anlässe: leeres Topic -> KEIN Netzaufruf.
    assert notify.send_ntfy("", "t", "b") is False
    notify.run_staleness("", MON)
    notify.run_daily("", MON)
    assert sent == []


def test_send_is_failsoft(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("ntfy down")
    monkeypatch.setattr(notify, "_post", boom)
    # Fehler beim Senden -> False, kein Crash.
    assert notify.send_ntfy(TOPIC, "t", "b") is False


def test_main_always_returns_zero(tmp_path, monkeypatch):
    # Selbstüberwachung darf den Workflow NIE rot färben.
    _fixture_repo(tmp_path, monkeypatch, report_ts="2026-07-27T18:00:00Z", matured=5)
    monkeypatch.setattr(notify, "_post", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setenv("NTFY_TOPIC", TOPIC)
    assert notify.main(["--mode", "daily"]) == 0
    assert notify.main(["--mode", "staleness"]) == 0
