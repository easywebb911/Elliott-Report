"""Heartbeat-Push (28.07.2026) — der OK-Push als HERZSCHLAG.

Zweck ist nicht das Lob: bleibt der Puls aus, ist der Lauf ausgefallen. Damit
das Signal etwas wert ist, muss er **exakt** dann kommen, wenn ein echter
Produktionslauf sauber durchgelaufen ist — und sonst nie.

HARTE REGEL, die hier festgenagelt wird: **genau ein Push pro Lauf.** Entweder
die Befund-Meldung (prio high) ODER der Herzschlag (prio low), nie beides.
"""
import datetime as _dt
import json

import health_check as hc
import notify

MON = _dt.datetime(2026, 7, 27, 21, 45, tzinfo=_dt.timezone.utc)   # Montag
TUE = _dt.datetime(2026, 7, 28, 21, 45, tzinfo=_dt.timezone.utc)   # Dienstag
SAT = _dt.datetime(2026, 8, 1, 21, 45, tzinfo=_dt.timezone.utc)    # Samstag
XMAS = _dt.datetime(2026, 12, 25, 21, 45, tzinfo=_dt.timezone.utc)
RUN_DATE = "2026-07-27"
NOW_ISO = "2026-07-27T21:45:00Z"
TOPIC = "easy-elliott-report"


def _capture(monkeypatch):
    sent = []
    monkeypatch.setattr(
        notify, "_post",
        lambda url, data, headers, timeout: sent.append(
            {"title": headers.get("Title"), "prio": headers.get("Priority"),
             "tags": headers.get("Tags"), "body": data.decode("utf-8")}))
    return sent


def _sandbox(tmp_path, monkeypatch, *, on_main=True):
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(hc, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main" if on_main
                       else "refs/heads/claude/testbranch")
    return tmp_path


def _cand(ticker, score):
    return {"ticker": ticker, "score_heuristic": score, "close": 100.0,
            "invalidation_price": 90.0,
            "target_zone": {"low": 110.0, "high": 120.0},
            "target_zone_extended": {"low": 125.0, "high": 140.0}}


def _report(us=5, de=5, us_top=85.7, de_top=77.1, **over):
    def market(prefix, n, top):
        cands = [_cand(f"{prefix}{i}", top - i) for i in range(n)]
        return {"label": prefix, "universe_size": 200, "skipped": 0,
                "candidates_found": 39 if prefix == "US" else 26,
                "candidates": cands,
                "diag": {"reason_counts": {"fetch_error": 0, "empty_data": 0},
                         "dead_tickers": [], "dropped_bars": 0,
                         "invalid_volume_bars": 0, "bad_bar_tickers": []}}
    r = {"schema_version": 1, "run_timestamp_utc": NOW_ISO,
         "markets": {"US": market("US", us, us_top),
                     "DE": market("DE", de, de_top)},
         "watchlist": {"entries": [], "diag": {}}}
    r.update(over)
    return r


COUNTS = {"collected": 27, "matured": 0, "evaluable": 0}


# ══ 1) Gesunder Lauf → GENAU EIN leiser Push mit echten Zahlen ═════════════
def test_healthy_run_sends_exactly_one_quiet_push(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    sent = _capture(monkeypatch)
    rep = _report()
    health = hc.run(rep, None, [], None, None, has_agent_key=False,
                    topic=TOPIC, run_date=RUN_DATE, now_iso=NOW_ISO, now=MON,
                    counts=COUNTS)
    assert health["status"] == "ok" and health["findings"] == []
    assert len(sent) == 1, "genau EIN Push pro Lauf"
    assert sent[0]["title"] == "Elliott: Lauf ok"
    assert sent[0]["prio"] == "low", "der Herzschlag darf nie vibrieren"
    assert health["heartbeat"] is True


def test_heartbeat_numbers_match_the_report(tmp_path, monkeypatch):
    """Gegen den ECHTEN Report gegengerechnet: Kandidatenzahl, Top-Ticker,
    Top-Score und die Sammlungs-Zähler stehen wörtlich drin."""
    _sandbox(tmp_path, monkeypatch)
    sent = _capture(monkeypatch)
    rep = _report(us_top=85.7, de_top=77.1)
    hc.run(rep, None, [], None, None, has_agent_key=False, topic=TOPIC,
           run_date=RUN_DATE, now_iso=NOW_ISO, now=MON, counts=COUNTS)
    body = sent[0]["body"]
    assert "39 Kandidaten" in body and "26 Kandidaten" in body
    assert "Top US0 86" in body          # höchster Score im US-Markt
    assert "Top DE0 77" in body
    assert "Sammlung 27 / 0 gereift / 0 auswertbar" in body
    assert "heuristisch · unvalidiert" in body, (
        "im ganzen Projekt darf keine Zahl ohne diesen Vorbehalt nach außen")


def test_top_candidate_picks_the_highest_score():
    m = {"candidates": [_cand("A", 50.0), _cand("B", 88.2), _cand("C", 70.0)]}
    assert hc._top_candidate(m) == ("B", 88.2)
    # Kaputte/fehlende Scores werden übersprungen, nicht geraten.
    m = {"candidates": [{"ticker": "X"}, {"ticker": "Y", "score_heuristic": None},
                        {"ticker": "Z", "score_heuristic": float("nan")},
                        _cand("OK", 12.0)]}
    assert hc._top_candidate(m) == ("OK", 12.0)
    assert hc._top_candidate({"candidates": []}) is None
    assert hc._top_candidate({}) is None


def test_body_without_collection_counts_stays_readable():
    """Sammel-Schritt gescheitert → die Sammlung wird schlicht nicht genannt."""
    body = hc.heartbeat_body(_report(), None)
    assert "Sammlung" not in body and "Kandidaten" in body


# ══ 2) Befund → NUR die Befund-Meldung, kein OK-Push ═══════════════════════
def test_findings_replace_the_heartbeat(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    sent = _capture(monkeypatch)
    rep = _report(us=0)                       # 0 Top-Kandidaten -> crit
    rep["markets"]["US"]["candidates_found"] = 0
    health = hc.run(rep, None, [], None, None, has_agent_key=False,
                    topic=TOPIC, run_date=RUN_DATE, now_iso=NOW_ISO, now=MON,
                    counts=COUNTS)
    assert health["status"] == hc.CRIT
    assert len(sent) == 1, "nie zwei Pushes pro Lauf"
    assert sent[0]["prio"] == "high" and "ok" not in sent[0]["title"].lower()
    assert health["heartbeat"] is False


def test_even_a_single_warn_replaces_the_heartbeat(tmp_path, monkeypatch):
    """Auch ein reines `warn` ersetzt den Puls — sonst käme neben der Warnung
    ein „alles in Ordnung", das ihr widerspricht."""
    _sandbox(tmp_path, monkeypatch)
    sent = _capture(monkeypatch)
    rep = _report(us=2)                       # < HEALTH_MIN_CANDIDATES -> warn
    health = hc.run(rep, None, [], None, None, has_agent_key=False,
                    topic=TOPIC, run_date=RUN_DATE, now_iso=NOW_ISO, now=MON,
                    counts=COUNTS)
    assert health["status"] == hc.WARN
    assert len(sent) == 1 and sent[0]["prio"] == "default"
    assert health["heartbeat"] is False


def test_silent_finding_run_still_sends_no_heartbeat(tmp_path, monkeypatch):
    """Zweiter Lauf mit demselben Befund: die Flanke schweigt (kein Push) —
    der Herzschlag springt trotzdem NICHT ein. Sonst käme ausgerechnet bei
    einem anhaltenden Problem ein „Lauf ok"."""
    _sandbox(tmp_path, monkeypatch)
    sent = _capture(monkeypatch)
    for day in (RUN_DATE, "2026-07-28"):
        rep = _report(us=2)
        hc.run(rep, None, [], None, None, has_agent_key=False, topic=TOPIC,
               run_date=day, now_iso=NOW_ISO, now=MON, counts=COUNTS)
    assert len(sent) == 1, "erster Lauf meldet, zweiter schweigt — kein OK-Push"


# ══ 3) Gates: Wochenende / Feiertag / Branch-Dispatch ══════════════════════
def test_no_heartbeat_on_weekend(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    sent = _capture(monkeypatch)
    rep = _report()
    health = hc.run(rep, None, [], None, None, has_agent_key=False,
                    topic=TOPIC, run_date="2026-08-01", now_iso=NOW_ISO,
                    now=SAT, counts=COUNTS)
    assert sent == [] and health["heartbeat"] is False
    assert health["push_gated"] == "Wochenende"


def test_no_heartbeat_on_holiday(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    sent = _capture(monkeypatch)
    rep = _report()
    hc.run(rep, None, [], None, None, has_agent_key=False, topic=TOPIC,
           run_date="2026-12-25", now_iso=NOW_ISO, now=XMAS, counts=COUNTS)
    assert sent == []


def test_no_heartbeat_from_a_feature_branch(tmp_path, monkeypatch):
    """Ein Test-Dispatch von einem Branch darf keinen Puls erzeugen — sonst
    ist „kein Push = Lauf ausgefallen" nichts mehr wert."""
    _sandbox(tmp_path, monkeypatch, on_main=False)
    sent = _capture(monkeypatch)
    rep = _report()
    health = hc.run(rep, None, [], None, None, has_agent_key=False,
                    topic=TOPIC, run_date=RUN_DATE, now_iso=NOW_ISO, now=MON,
                    counts=COUNTS)
    assert sent == [] and health["heartbeat"] is False
    assert health["status"] == "ok", "der Lauf war trotzdem in Ordnung"


def test_no_heartbeat_locally_without_github_ref(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    monkeypatch.delenv("GITHUB_REF", raising=False)
    sent = _capture(monkeypatch)
    hc.run(_report(), None, [], None, None, has_agent_key=False, topic=TOPIC,
           run_date=RUN_DATE, now_iso=NOW_ISO, now=MON, counts=COUNTS)
    assert sent == []


def test_is_main_run_predicate(monkeypatch):
    for ref, want in (("refs/heads/main", True),
                      ("refs/heads/claude/x", False),
                      ("refs/tags/v1", False), ("", False)):
        monkeypatch.setenv("GITHUB_REF", ref)
        assert hc.is_main_run() is want


# ══ 4) Ohne Secret: sauberer no-op ═════════════════════════════════════════
def test_without_topic_no_push_no_error(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    sent = _capture(monkeypatch)
    rep = _report()
    health = hc.run(rep, None, [], None, None, has_agent_key=False, topic="",
                    run_date=RUN_DATE, now_iso=NOW_ISO, now=MON, counts=COUNTS)
    assert sent == [] and health["status"] == "ok"
    assert health["heartbeat"] is False


def test_push_failure_never_raises(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("ntfy down")
    monkeypatch.setattr(notify, "_post", boom)
    health = hc.run(_report(), None, [], None, None, has_agent_key=False,
                    topic=TOPIC, run_date=RUN_DATE, now_iso=NOW_ISO, now=MON,
                    counts=COUNTS)
    assert health["status"] == "ok" and health["heartbeat"] is False


# ══ 5) Frequenz-Wahl ═══════════════════════════════════════════════════════
def test_frequency_daily_and_weekly():
    assert hc.heartbeat_due(MON, "daily") is True
    assert hc.heartbeat_due(TUE, "daily") is True
    assert hc.heartbeat_due(MON, "weekly", weekday=0) is True    # Montag
    assert hc.heartbeat_due(TUE, "weekly", weekday=0) is False
    assert hc.heartbeat_due(TUE, "weekly", weekday=1) is True


def test_disabled_switch(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    sent = _capture(monkeypatch)
    monkeypatch.setattr(hc, "HEARTBEAT_ENABLED", False)
    hc.run(_report(), None, [], None, None, has_agent_key=False, topic=TOPIC,
           run_date=RUN_DATE, now_iso=NOW_ISO, now=MON, counts=COUNTS)
    assert sent == []


# ══ 6) Meilensteine ════════════════════════════════════════════════════════
def test_milestone_fires_only_on_crossing():
    step = 25
    assert hc.milestone_note({"collected": 25}, {"collected": 24}, step) == \
        "25 gesammelt"
    assert hc.milestone_note({"collected": 26}, {"collected": 25}, step) is None
    assert hc.milestone_note({"collected": 51}, {"collected": 49}, step) == \
        "50 gesammelt"
    # Mehrere Zähler zugleich
    note = hc.milestone_note({"collected": 50, "matured": 25},
                             {"collected": 49, "matured": 24}, step)
    assert "50 gesammelt" in note and "25 gereift" in note


def test_milestone_silent_without_previous_state():
    """Erster Herzschlag darf kein Meilenstein-Fehlalarm sein."""
    assert hc.milestone_note({"collected": 27}, None) is None
    assert hc.milestone_note(None, {"collected": 0}) is None
    assert hc.milestone_note({"collected": 5}, {"collected": 0}) is None  # < step


def test_milestone_appears_in_the_push_and_is_not_repeated(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    sent = _capture(monkeypatch)
    # Lauf 1 legt den Zähler-Stand an (kein Meilenstein, kein Vorstand).
    hc.run(_report(), None, [], None, None, has_agent_key=False, topic=TOPIC,
           run_date=RUN_DATE, now_iso=NOW_ISO, now=MON,
           counts={"collected": 24, "matured": 0, "evaluable": 0})
    assert "Meilenstein" not in sent[0]["body"]
    # Lauf 2 überschreitet 25 -> Hinweis.
    hc.run(_report(), None, [], None, None, has_agent_key=False, topic=TOPIC,
           run_date="2026-07-28", now_iso=NOW_ISO, now=TUE,
           counts={"collected": 26, "matured": 0, "evaluable": 0})
    assert "Meilenstein: 25 gesammelt" in sent[1]["body"]
    # Lauf 3 nicht mehr.
    hc.run(_report(), None, [], None, None, has_agent_key=False, topic=TOPIC,
           run_date="2026-07-29", now_iso=NOW_ISO, now=TUE,
           counts={"collected": 27, "matured": 0, "evaluable": 0})
    assert "Meilenstein" not in sent[2]["body"]


def test_state_carries_heartbeat_counts(tmp_path, monkeypatch):
    """Der Zähler-Stand muss persistiert werden, sonst wäre jeder Lauf ein
    Meilenstein — und er darf die Flanken-Regeln nicht überschreiben."""
    _sandbox(tmp_path, monkeypatch)
    _capture(monkeypatch)
    hc.run(_report(), None, [], None, None, has_agent_key=False, topic=TOPIC,
           run_date=RUN_DATE, now_iso=NOW_ISO, now=MON, counts=COUNTS)
    state = json.loads((tmp_path / hc.STATE_PATH).read_text(encoding="utf-8"))
    assert state["heartbeat"]["counts"] == COUNTS
    assert state["heartbeat"]["last_run_date"] == RUN_DATE
    assert "rules" in state, "die Flanken-Regeln bleiben im selben State"


def test_skipped_heartbeat_does_not_swallow_a_milestone(tmp_path, monkeypatch):
    """Wird ein Herzschlag unterdrückt (Wochenende/Branch), darf der
    Zähler-Stand NICHT fortgeschrieben werden — sonst verschluckt der
    übersprungene Lauf den Meilenstein für immer."""
    _sandbox(tmp_path, monkeypatch)
    sent = _capture(monkeypatch)
    hc.run(_report(), None, [], None, None, has_agent_key=False, topic=TOPIC,
           run_date=RUN_DATE, now_iso=NOW_ISO, now=MON,
           counts={"collected": 24, "matured": 0, "evaluable": 0})
    # Branch-Dispatch mit uebersprungenem Meilenstein
    _sandbox(tmp_path, monkeypatch, on_main=False)
    hc.run(_report(), None, [], None, None, has_agent_key=False, topic=TOPIC,
           run_date="2026-07-28", now_iso=NOW_ISO, now=TUE,
           counts={"collected": 26, "matured": 0, "evaluable": 0})
    assert len(sent) == 1, "Branch-Lauf sendet nicht"
    # Naechster echter main-Lauf holt den Meilenstein nach.
    _sandbox(tmp_path, monkeypatch, on_main=True)
    hc.run(_report(), None, [], None, None, has_agent_key=False, topic=TOPIC,
           run_date="2026-07-29", now_iso=NOW_ISO, now=TUE,
           counts={"collected": 27, "matured": 0, "evaluable": 0})
    assert "Meilenstein: 25 gesammelt" in sent[1]["body"]


# ══ 7) Robustheit ══════════════════════════════════════════════════════════
def test_garbage_report_does_not_crash(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    _capture(monkeypatch)
    for junk in ({}, {"markets": None}, {"markets": {"US": "kaputt"}},
                 {"markets": {"US": {"candidates": None}}}):
        hc.heartbeat_body(junk, COUNTS)


def test_milestone_note_survives_broken_counts():
    assert hc.milestone_note({"collected": "x"}, {"collected": 1}) is None
    assert hc.milestone_note({}, {}) is None
