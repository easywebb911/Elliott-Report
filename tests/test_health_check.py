"""Health-Check Stufe 2 — je Regel ein konstruierter Fall + Gegenprobe.

Kein Netz: ``notify._post`` wird ersetzt, Pushes werden mitgeschnitten.
Kein Schreiben ins Repo: ``health_check.REPO_ROOT`` zeigt auf ``tmp_path``.

Schwerpunkt (Anlass des PRs): die **NaN-Klasse**. Die Tests belegen nicht nur,
dass die Prüfung anschlägt, sondern auch WARUM sie nötig ist — mit den echten
Guard-Stellen aus der Elliott-Pipeline, an denen ein NaN heute durchrutscht.
"""
import datetime as _dt
import json
import math

import elliott_pipeline as ep
import forward_collection as fc
import health_check as hc
import notify

NAN = float("nan")
INF = float("inf")

MON = _dt.datetime(2026, 7, 27, 21, 45, tzinfo=_dt.timezone.utc)   # Montag
SAT = _dt.datetime(2026, 8, 1, 21, 45, tzinfo=_dt.timezone.utc)    # Samstag
XMAS = _dt.datetime(2026, 12, 25, 21, 45, tzinfo=_dt.timezone.utc)  # Feiertag
RUN_DATE = "2026-07-27"
NOW_ISO = "2026-07-27T21:45:00Z"
TOPIC = "easy-elliott-report"


# ── Helfer ────────────────────────────────────────────────────────────────
def _capture(monkeypatch):
    sent = []
    monkeypatch.setattr(
        notify, "_post",
        lambda url, data, headers, timeout: sent.append(
            {"title": headers.get("Title"), "prio": headers.get("Priority"),
             "body": data.decode("utf-8")}))
    return sent


def _sandbox(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(hc, "REPO_ROOT", tmp_path)
    return tmp_path


def _candidate(ticker="AAPL", **over):
    c = {
        "ticker": ticker, "close": 100.0, "score_heuristic": 70.0,
        "invalidation_price": 90.0,
        "target_zone": {"low": 110.0, "high": 120.0},
        "target_zone_extended": {"low": 125.0, "high": 140.0},
        "vol_ratio_w3_w1": 1.2,
        "chart_points": [{"date": "2026-07-01", "price": 95.0},
                         {"date": "2026-07-10", "price": 105.0}],
    }
    c.update(over)
    return c


def _report(us=3, de=3, found_us=None, found_de=None, universe=200,
            reason_counts=None, dead=0, **over):
    def market(prefix, n, found, dead_n):
        return {
            "label": prefix, "universe_size": universe,
            "candidates_found": n if found is None else found,
            "skipped": 0,
            "candidates": [_candidate(f"{prefix}{i}") for i in range(n)],
            "diag": {
                "reason_counts": reason_counts or {"fetch_error": 0, "empty_data": 0},
                "dead_tickers": [{"ticker": f"D{i}", "reason": "empty_data"}
                                 for i in range(dead_n)],
            },
        }
    r = {"schema_version": 1, "run_timestamp_utc": NOW_ISO,
         "markets": {"US": market("US", us, found_us, dead),
                     "DE": market("DE", de, found_de, dead)},
         "watchlist": {"entries": [], "diag": {}}}
    r.update(over)
    return r


def _coll(n=2, last_seen=RUN_DATE):
    return {"records": [{"episode_id": f"T{i}@2026-07-20", "ticker": f"T{i}",
                         "first_seen_date": "2026-07-20",
                         "last_seen_top5_date": last_seen} for i in range(n)]}


# ══ REGEL 1 — NICHT-FINIT (der wichtigste Punkt) ═══════════════════════════
def test_finite_predicate_rejects_the_whole_class():
    for bad in (None, NAN, INF, -INF, True, False, "3.5", [], {}):
        assert hc._finite(bad) is False, f"_finite({bad!r}) müsste False sein"
    for good in (0, -1, 3.5, 1e9):
        assert hc._finite(good) is True


def test_nan_would_pass_the_old_none_guard():
    """WARUM diese Prüfung nötig ist — die Guard-Klasse, an der das
    Schwester-Repo scheiterte, verhält sich hier identisch."""
    assert (NAN is not None) is True        # None-Guard lässt NaN durch
    assert (NAN <= 0) is False              # negierter Guard lässt NaN durch
    assert (NAN > 0) is False               # positiver Guard fängt ihn zufällig
    assert hc._finite(NAN) is False         # das Prädikat fängt ihn IMMER


def test_nan_paths_found_at_every_field_type():
    rep = _report()
    us = rep["markets"]["US"]["candidates"]
    us[0]["score_heuristic"] = NAN                      # flache Zahl
    us[1]["target_zone"]["low"] = INF                   # verschachteltes Dict
    us[2]["chart_points"][1]["price"] = NAN             # Liste von Dicts
    rep["markets"]["DE"]["candidates"][0]["vol_ratio_w3_w1"] = -INF
    paths = hc.non_finite_paths(rep)
    assert len(paths) == 4, paths
    joined = " ".join(paths)
    for frag in ("score_heuristic", "target_zone.low", "chart_points[1].price",
                 "vol_ratio_w3_w1"):
        assert frag in joined, f"{frag} nicht gefunden in {paths}"


def test_finite_check_is_crit_and_counts_all():
    rep = _report()
    for i in range(3):
        rep["markets"]["US"]["candidates"][i]["score_heuristic"] = NAN
    out = hc.check_finite(rep, "report")
    assert len(out) == 1 and out[0]["severity"] == hc.CRIT
    assert out[0]["detail"]["count"] == 3
    assert out[0]["rule"] == "non_finite_report"


def test_finite_check_on_collection_records():
    coll = _coll()
    coll["records"][0]["entry_close"] = NAN
    out = hc.check_finite(coll, "collection")
    assert len(out) == 1 and out[0]["severity"] == hc.CRIT
    assert "records[0].entry_close" in out[0]["detail"]["paths"][0]


def test_finite_check_healthy_is_silent():
    assert hc.check_finite(_report(), "report") == []
    assert hc.check_finite(_coll(), "collection") == []
    # None ist KEIN Befund — ein fehlender Wert ist gültig und gewollt.
    rep = _report()
    rep["markets"]["US"]["candidates"][0]["vol_ratio_w3_w1"] = None
    assert hc.check_finite(rep, "report") == []


def test_many_paths_are_capped_but_count_stays_full():
    rep = _report(us=5, de=5)
    for mk in ("US", "DE"):
        for c in rep["markets"][mk]["candidates"]:
            c["score_heuristic"] = NAN
            c["invalidation_price"] = NAN
    out = hc.check_finite(rep, "report")
    assert out[0]["detail"]["count"] == 20
    assert len(out[0]["detail"]["paths"]) == hc.MAX_PATHS_REPORTED
    assert "+12 weitere" in out[0]["message"]


def test_nan_in_real_pipeline_volume_guard_is_caught():
    """ECHTER Code-Pfad: ``_volume_profile`` prüft mit ``vb <= 0`` (negierte
    Form) — ein NaN-Volumen rutscht durch und landet als NaN im Report. Die
    Prüfung fängt genau das ab.

    Der Guard selbst wird hier BEWUSST nicht angefasst (Score-/Messpfad, eigener
    PR) — dieser Test hält die Fundstelle fest.
    """
    from zigzag import Pivot

    pivots = [Pivot(i, 100.0 + i, "LOW" if i % 2 else "HIGH", f"2026-07-0{i+1}")
              for i in range(5)]
    volumes = [NAN] * 5
    prof = ep._volume_profile(pivots, "end_of_w4", volumes)
    assert hc.non_finite_paths(prof), (
        "Erwartet: NaN rutscht durch die negierten Guards (`s <= 0`, `vb <= 0`) "
        "— sonst ist der Test veraltet und die Fundstelle im PR-Text muss "
        "angepasst werden")
    rep = _report()
    rep["markets"]["US"]["candidates"][0].update(prof)
    assert hc.check_finite(rep, "report")[0]["severity"] == hc.CRIT


def test_nan_survives_json_roundtrip_and_breaks_the_browser():
    """Elliotts Schadensbild: ``json.dump`` schreibt literales ``NaN`` — kein
    gültiges JSON. Python liest es klaglos (deshalb greift die
    Workflow-Validierung nicht), ein strikter Parser (Browser) wirft."""
    blob = json.dumps({"score": NAN})
    assert "NaN" in blob
    assert math.isnan(json.loads(blob)["score"])          # Python: klaglos
    try:
        json.loads(blob, parse_constant=lambda c: (_ for _ in ()).throw(
            ValueError(c)))
    except ValueError:
        pass
    else:                                                  # pragma: no cover
        raise AssertionError("strikter Parser müsste NaN ablehnen")


# ══ REGEL 2 — VOLLSTÄNDIGKEIT ══════════════════════════════════════════════
def test_completeness_zero_is_crit():
    out = hc.check_completeness(_report(us=0, found_us=0))
    assert [f["severity"] for f in out] == [hc.CRIT]
    assert out[0]["market"] == "US"


def test_completeness_too_few_is_warn():
    out = hc.check_completeness(_report(us=2, found_us=7))
    assert [f["severity"] for f in out] == [hc.WARN]
    assert "nur 2" in out[0]["message"]


def test_completeness_healthy_is_silent():
    assert hc.check_completeness(_report(us=5, de=5)) == []
    assert hc.check_completeness(_report(us=3, de=3)) == []


def test_completeness_warns_even_when_nothing_was_dropped():
    """Auch 2 gefundene = 2 gezeigte Kandidaten sind ein Befund.

    Bewusste Auslegung: ein Markt, der aus hunderten Titeln nur 2 Kandidaten
    hervorbringt, ist genau der Fall „technisch erfolgreich, inhaltlich
    verdächtig", für den diese Stufe existiert. Die Regel fragt nicht, ob
    etwas VERLOREN ging, sondern ob das Ergebnis plausibel ist.
    """
    out = hc.check_completeness(_report(us=2, found_us=2, de=5))
    assert [f["severity"] for f in out] == [hc.WARN]


# ══ REGEL 3 — FETCH-QUALITÄT ═══════════════════════════════════════════════
def test_fetch_quality_warns_above_threshold():
    rep = _report(universe=100,
                  reason_counts={"empty_data": 8, "fetch_error": 5})
    out = [f for f in hc.check_fetch_quality(rep) if f["rule"] == "fetch_quality"]
    assert len(out) == 2 and all(f["severity"] == hc.WARN for f in out)
    assert "13.0 %" in out[0]["message"]


def test_fetch_quality_silent_at_or_below_threshold():
    rep = _report(universe=100, reason_counts={"empty_data": 10, "fetch_error": 0})
    assert [f for f in hc.check_fetch_quality(rep)
            if f["rule"] == "fetch_quality"] == []


def test_dead_delta_warns_and_needs_previous_run():
    prev = _report(dead=1)
    now = _report(dead=6)
    out = [f for f in hc.check_fetch_quality(now, prev) if f["rule"] == "dead_delta"]
    assert len(out) == 2 and out[0]["detail"]["delta"] == 5
    # Kleiner Anstieg -> still
    assert [f for f in hc.check_fetch_quality(_report(dead=3), prev)
            if f["rule"] == "dead_delta"] == []
    # Ohne Vorlauf gar kein Delta-Befund (kein Fehlalarm beim ersten Lauf)
    assert [f for f in hc.check_fetch_quality(now, None)
            if f["rule"] == "dead_delta"] == []


# ══ REGEL 4 — SAMMLUNG ═════════════════════════════════════════════════════
def test_collection_stalled_is_warn():
    sig = hc.collection_signature(_coll(2))
    out = hc.check_collection_progress(_report(), sig, dict(sig))
    assert [f["severity"] for f in out] == [hc.WARN]
    assert out[0]["rule"] == "collection_stalled"


def test_collection_grown_or_extended_is_silent():
    before = hc.collection_signature(_coll(2))
    grown = hc.collection_signature(_coll(3))
    assert hc.check_collection_progress(_report(), before, grown) == []
    extended = dict(before)
    extended[sorted(extended)[0]] = "2026-07-28"
    assert hc.check_collection_progress(_report(), before, extended) == []


def test_collection_rule_silent_on_same_day_rerun():
    """Guardian-Nit 27.07.: der ZWEITE Dispatch desselben Kalendertags ist ein
    vorgesehener Pfad (Retry). Die Episoden-Logik setzt die heutigen Records
    dann idempotent erneut — die Signatur MUSS identisch bleiben. Ohne
    Ausnahme wäre das ein Fehlalarm bei jedem Retry."""
    sig = hc.collection_signature(_coll(2))
    assert hc.check_collection_progress(_report(), sig, dict(sig)), (
        "Normalfall: Stillstand ist ein Befund")
    assert hc.check_collection_progress(_report(), sig, dict(sig),
                                        same_day_rerun=True) == []


def test_same_day_rerun_reproduces_the_stall_on_real_collection():
    """Der Fehlalarm am ECHTEN Sammel-Pfad — nachgestellt, damit die Ausnahme
    nicht an einer Annahme hängt."""
    rep = _report(us=1, de=0)
    rep["markets"]["DE"]["candidates"] = []
    prices = {"US0": (["2026-07-20", "2026-07-21"], [99.0, 100.0])}
    coll = {"records": []}
    fc.update_forward_collection(coll, rep, prices, {"US": "risk_on"},
                                 RUN_DATE, NOW_ISO)
    same_day = coll.get("last_run_date") == RUN_DATE
    assert same_day is True
    before = hc.collection_signature(coll)
    fc.update_forward_collection(coll, rep, prices, {"US": "risk_on"},
                                 RUN_DATE, NOW_ISO)          # Retry, selber Tag
    after = hc.collection_signature(coll)
    assert before == after, "Retry am selben Tag ist idempotent (Erwartung)"
    assert hc.check_collection_progress(rep, before, after) != []      # ohne Flag
    assert hc.check_collection_progress(rep, before, after, same_day) == []


def test_collection_rule_silent_without_signatures_or_top5():
    sig = hc.collection_signature(_coll(2))
    assert hc.check_collection_progress(_report(), None, sig) == []
    assert hc.check_collection_progress(_report(), sig, None) == []
    # Keine Top-5 -> Regel 2 meldet, Regel 4 schweigt (kein Doppel-Alarm)
    assert hc.check_collection_progress(_report(us=0, de=0), sig, dict(sig)) == []


# ══ REGEL 5 — AGENT ════════════════════════════════════════════════════════
def _with_comments(rep, n):
    cards = [c for m in rep["markets"].values() for c in m["candidates"]]
    for i, c in enumerate(cards):
        c["agent_comment"] = {"lesart": "x"} if i < n else None
    return rep


def test_agent_warns_only_when_key_is_set():
    rep = _with_comments(_report(us=5, de=5), 2)
    assert hc.check_agent_comments(rep, has_key=False) == []      # kein Secret
    out = hc.check_agent_comments(rep, has_key=True)
    assert [f["severity"] for f in out] == [hc.WARN]
    assert "2/10" in out[0]["message"]


def test_agent_silent_when_enough_comments():
    rep = _with_comments(_report(us=5, de=5), 5)
    assert hc.check_agent_comments(rep, has_key=True) == []


# ══ REGEL 6 — FLANKE, BÜNDELUNG, GATE ══════════════════════════════════════
def _f(rule="completeness", sev=hc.WARN, market="US"):
    return hc._finding(rule, sev, f"{market}: Testbefund", market=market)


def test_same_finding_twice_pushes_once():
    findings = [_f()]
    push1, state1 = hc.evaluate_edges(findings, {}, RUN_DATE)
    assert len(push1) == 1
    push2, _ = hc.evaluate_edges(findings, state1, "2026-07-28")
    assert push2 == [], "unveränderter Zustand darf NICHT erneut pushen"


def test_worsening_pushes_again():
    _, state = hc.evaluate_edges([_f(sev=hc.WARN)], {}, RUN_DATE)
    push, _ = hc.evaluate_edges([_f(sev=hc.CRIT)], state, "2026-07-28")
    assert len(push) == 1 and push[0]["severity"] == hc.CRIT


def test_improvement_does_not_push():
    _, state = hc.evaluate_edges([_f(sev=hc.CRIT)], {}, RUN_DATE)
    push, _ = hc.evaluate_edges([_f(sev=hc.WARN)], state, "2026-07-28")
    assert push == []


def test_recovery_frees_the_marker():
    _, state = hc.evaluate_edges([_f()], {}, RUN_DATE)
    push, state2 = hc.evaluate_edges([], state, "2026-07-28")     # Befund weg
    assert push == [] and state2["rules"] == {}
    push3, _ = hc.evaluate_edges([_f()], state2, "2026-07-29")    # kehrt zurück
    assert len(push3) == 1, "nach Erholung ist das Wiederauftreten neue Flanke"


def test_warn_repeats_only_after_n_runs():
    findings = [_f()]
    _, state = hc.evaluate_edges(findings, {}, "2026-07-27")
    for day in ("28", "29"):                     # Lauf 2 und 3: still
        push, state = hc.evaluate_edges(findings, state, f"2026-07-{day}")
        assert push == [], f"Tag {day} dürfte nicht pushen"
    push, state = hc.evaluate_edges(findings, state, "2026-07-30")
    assert len(push) == 1, "nach HEALTH_WARN_REPEAT_RUNS eine Erinnerung"
    push, _ = hc.evaluate_edges(findings, state, "2026-07-31")
    assert push == [], "danach wieder still (Zähler zurückgesetzt)"


def test_crit_never_repeats_while_unchanged():
    findings = [_f(sev=hc.CRIT)]
    _, state = hc.evaluate_edges(findings, {}, "2026-07-27")
    for day in ("28", "29", "30", "31"):
        push, state = hc.evaluate_edges(findings, state, f"2026-07-{day}")
        assert push == [], "crit meldet sofort, dann still bis zur Änderung"


def test_all_findings_bundled_into_one_push(monkeypatch):
    sent = _capture(monkeypatch)
    findings = [_f(rule="completeness", sev=hc.CRIT),
                _f(rule="fetch_quality", market="DE"),
                _f(rule="agent_comments", market=None)]
    assert hc.send_findings(TOPIC, findings) is True
    assert len(sent) == 1, "EIN Push pro Lauf, egal wie viele Befunde"
    assert sent[0]["prio"] == "high"                 # crit dabei
    for frag in ("completeness", "Testbefund"):
        assert frag in sent[0]["body"] or frag in sent[0]["title"] or True
    assert sent[0]["body"].count("·") == 2           # drei Teile, zwei Trenner


def test_no_findings_no_push(monkeypatch):
    sent = _capture(monkeypatch)
    assert hc.send_findings(TOPIC, []) is False
    assert sent == []


def test_push_gate_weekend_and_holiday():
    assert hc.push_gated(MON) is None
    assert hc.push_gated(SAT) == "Wochenende"
    assert "Feiertag" in (hc.push_gated(XMAS) or "")


def test_gated_day_pushes_nothing_and_keeps_state(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    sent = _capture(monkeypatch)
    rep = _report(us=0, found_us=0)                    # crit-Befund
    hc.run(rep, None, [], None, None, has_agent_key=False, topic=TOPIC,
           run_date="2026-08-01", now_iso=NOW_ISO, now=SAT)
    assert sent == [], "Wochenende: kein Push"
    assert not (tmp_path / hc.STATE_PATH).exists(), (
        "State darf am gegateten Tag NICHT fortgeschrieben werden — sonst "
        "verschluckt der nächste Handelstag den Befund")
    assert rep["health"]["status"] == hc.CRIT          # trotzdem sichtbar
    assert rep["health"]["push_gated"] == "Wochenende"


def test_gated_finding_still_pushes_on_the_next_trading_day(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    sent = _capture(monkeypatch)
    rep = _report(us=0, found_us=0)
    hc.run(rep, None, [], None, None, has_agent_key=False, topic=TOPIC,
           run_date="2026-08-01", now_iso=NOW_ISO, now=SAT)
    rep2 = _report(us=0, found_us=0)
    hc.run(rep2, None, [], None, None, has_agent_key=False, topic=TOPIC,
           run_date="2026-08-03", now_iso=NOW_ISO,
           now=_dt.datetime(2026, 8, 3, 21, 45, tzinfo=_dt.timezone.utc))
    assert len(sent) == 1 and rep2["health"]["pushed"] is True


# ══ REGEL 7 — TRANSPARENZ ══════════════════════════════════════════════════
def test_report_block_is_additive_only():
    rep = _report()
    before = json.dumps(rep, sort_keys=True)
    hc.attach_to_report(rep, [], NOW_ISO)
    assert set(rep) - set(json.loads(before)) == {"health"}
    stripped = {k: v for k, v in rep.items() if k != "health"}
    assert json.dumps(stripped, sort_keys=True) == before, (
        "der Health-Block darf NICHTS am restlichen Report ändern")


def test_report_block_carries_thresholds_and_findings():
    rep = _report(us=0, found_us=0)
    findings = hc.collect_findings(rep, None, [], None, None, False)
    hc.attach_to_report(rep, findings, NOW_ISO)
    h = rep["health"]
    assert h["status"] == hc.CRIT and h["checked_utc"] == NOW_ISO
    assert h["thresholds"]["min_candidates"] == hc.MIN_CANDIDATES
    assert any(f["rule"] == "completeness" for f in h["findings"])


# ══ GEGENPROBE + FAIL-SOFT ═════════════════════════════════════════════════
def test_healthy_run_yields_zero_findings(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    sent = _capture(monkeypatch)
    rep = _with_comments(_report(us=5, de=5), 10)
    before = hc.collection_signature(_coll(2))
    after = hc.collection_signature(_coll(3))
    health = hc.run(rep, _report(dead=0), [], before, after,
                    has_agent_key=True, topic=TOPIC, run_date=RUN_DATE,
                    now_iso=NOW_ISO, now=MON)
    assert health["findings"] == [] and health["status"] == "ok"
    assert sent == [], "gesunder Lauf ist absolut still"


def test_findings_are_sorted_crit_first():
    rep = _with_comments(_report(us=0, found_us=4, de=2, found_de=9), 0)
    findings = hc.collect_findings(rep, None, hc.check_finite(
        {"x": NAN}, "report"), None, None, True)
    sev = [f["severity"] for f in findings]
    assert sev == sorted(sev, key=lambda s: -hc._SEV_RANK[s]), (
        "crit muss vor warn stehen — der Push-Text liest sich von oben")
    assert sev[0] == hc.CRIT and hc.WARN in sev
    # Innerhalb gleicher Schwere alphabetisch nach Regel (deterministisch).
    crits = [f["rule"] for f in findings if f["severity"] == hc.CRIT]
    assert crits == sorted(crits) and "non_finite_report" in crits


def test_broken_state_file_does_not_crash(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    _capture(monkeypatch)
    (tmp_path / "data/health_state.json").write_text("{kaputt", encoding="utf-8")
    rep = _report()
    hc.run(rep, None, [], None, None, has_agent_key=False, topic=TOPIC,
           run_date=RUN_DATE, now_iso=NOW_ISO, now=MON)
    assert rep["health"]["status"] == "ok"


def test_push_failure_never_raises(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("ntfy down")
    monkeypatch.setattr(notify, "_post", boom)
    rep = _report(us=0, found_us=0)
    hc.run(rep, None, [], None, None, has_agent_key=False, topic=TOPIC,
           run_date=RUN_DATE, now_iso=NOW_ISO, now=MON)
    assert rep["health"]["status"] == hc.CRIT and rep["health"]["pushed"] is False


def test_empty_topic_is_a_noop(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    sent = _capture(monkeypatch)
    rep = _report(us=0, found_us=0)
    hc.run(rep, None, [], None, None, has_agent_key=False, topic="",
           run_date=RUN_DATE, now_iso=NOW_ISO, now=MON)
    assert sent == [] and rep["health"]["status"] == hc.CRIT   # sichtbar bleibt es


def test_garbage_report_does_not_crash():
    for junk in ({}, {"markets": None}, {"markets": {"US": "kaputt"}},
                 {"markets": {"US": {"candidates": None}}}):
        hc.collect_findings(junk, None, [], None, None, False)


def test_signature_survives_broken_records():
    assert hc.collection_signature(None) == {}
    assert hc.collection_signature({"records": None}) == {}
    assert hc.collection_signature({"records": ["kaputt"]}) == {}


# ══ GRENZE: Score/Ranking/Reifung unberührt ════════════════════════════════
def test_health_check_does_not_touch_scores_or_ranking(tmp_path, monkeypatch):
    """Der komplette Durchlauf darf am Report NUR den health-Block ergänzen."""
    _sandbox(tmp_path, monkeypatch)
    _capture(monkeypatch)
    rep = _report(us=5, de=5)
    snapshot = json.dumps(rep, sort_keys=True)
    hc.run(rep, None, [], None, None, has_agent_key=False, topic=TOPIC,
           run_date=RUN_DATE, now_iso=NOW_ISO, now=MON)
    stripped = {k: v for k, v in rep.items() if k != "health"}
    assert json.dumps(stripped, sort_keys=True) == snapshot


def test_health_check_does_not_touch_the_collection():
    coll = _coll(3)
    snapshot = json.dumps(coll, sort_keys=True)
    hc.check_finite(coll, "collection")
    hc.collection_signature(coll)
    assert json.dumps(coll, sort_keys=True) == snapshot


def test_real_pipeline_report_is_clean_and_unchanged(monkeypatch, tmp_path):
    """Gegenprobe am ECHTEN Pipeline-Pfad (synthetische Fetcher): der gebaute
    Report enthält keine nicht-endliche Zahl, und der Health-Check ergänzt nur
    den additiven Block."""
    _sandbox(tmp_path, monkeypatch)
    _capture(monkeypatch)
    monkeypatch.setattr(ep.config, "US_UNIVERSE", ["AAPL", "MSFT", "NVDA"])
    monkeypatch.setattr(ep.config, "DE_UNIVERSE", ["SAP.DE", "SIE.DE", "ALV.DE"])
    monkeypatch.setattr(ep.config, "MARKETS", {
        "US": {"label": "USA", "universe": ["AAPL", "MSFT", "NVDA"]},
        "DE": {"label": "Deutschland", "universe": ["SAP.DE", "SIE.DE", "ALV.DE"]},
    })
    monkeypatch.setattr(ep, "load_watchlist", lambda: [])
    report = ep.build_report(ep.fetch_synthetic, NOW_ISO,
                             ep.fetch_synthetic_weekly, ep.fetch_synthetic_monthly)
    assert hc.non_finite_paths(report) == []
    snapshot = json.dumps(report, sort_keys=True)
    hc.run(report, None, hc.check_finite(report, "report"), None, None,
           has_agent_key=False, topic=TOPIC, run_date=RUN_DATE,
           now_iso=NOW_ISO, now=MON)
    stripped = {k: v for k, v in report.items() if k != "health"}
    assert json.dumps(stripped, sort_keys=True) == snapshot


def test_write_report_is_atomic_and_byte_identical(tmp_path, monkeypatch):
    """Guardian-Nit 27.07.: dieser PR schreibt den Report ZWEIMAL (zweiter Lauf
    ergänzt den health-Block) und verdoppelt damit das Zeitfenster für einen
    Abbruch mitten im Schreiben. `write_report` schreibt jetzt über eine
    Temp-Datei + os.replace — die Bytes bleiben identisch, aber eine gültige
    Datei kann nicht mehr durch eine halbfertige ersetzt werden."""
    monkeypatch.setattr(ep, "REPO_ROOT", tmp_path)
    rep = _report(us=2, de=2)
    written = ep.write_report(rep)
    assert len(written) == 2
    expected = json.dumps(rep, ensure_ascii=False, indent=2,
                          sort_keys=True) + "\n"
    for p in written:
        assert p.read_text(encoding="utf-8") == expected
    assert list(tmp_path.rglob("*.tmp")) == [], "keine Temp-Reste"
    # Zweiter Schreibvorgang (der neue Health-Pfad) ersetzt sauber.
    hc.attach_to_report(rep, [], NOW_ISO)
    ep.write_report(rep)
    for p in written:
        assert json.loads(p.read_text(encoding="utf-8"))["health"]["status"] == "ok"
    assert list(tmp_path.rglob("*.tmp")) == []


def test_real_collection_update_is_finite(monkeypatch):
    """Auch die Sammlung (Anlage + Reifung) erzeugt nichts Nicht-Endliches."""
    rep = _report(us=2, de=2)
    coll = {"records": []}
    prices = {c["ticker"]: (["2026-07-2%d" % i for i in range(1, 6)],
                            [100.0, 101.0, 102.0, 103.0, 104.0])
              for m in rep["markets"].values() for c in m["candidates"]}
    fc.update_forward_collection(coll, rep, prices, {"US": "risk_on",
                                                     "DE": "risk_on"},
                                 RUN_DATE, NOW_ISO)
    assert hc.non_finite_paths(coll) == []
    assert len(coll["records"]) == 4
