"""Agent-Kommentar v1 — Offline-Tests mit gemockter Anthropic-API.

Belegt: Parse (inkl. Codefence-Toleranz), Retry bei Parse-Fehler, null-Pfad,
no-op ohne Key, Token-/Kosten-Zähler, das Einfrieren bei Episoden-Anlage — und
die harte Grenze: der Schritt berührt Score/Ranking/Filter NICHT (rein additives
Feld, nur auf den finalen Markt-Top-5, Watchlist ausgenommen).
"""
import copy
import json

import agent_comment as ac
import elliott_pipeline as pipe
import forward_collection as fc

NOW = "2026-07-26T22:00:00Z"


def _entry(ticker="AMAT", **kw):
    e = {
        "ticker": ticker, "company_name": "Applied Materials", "sector": "Semis",
        "close": 232.4, "change_pct": 1.6, "score_heuristic": 71.0,
        "count_label": "Impuls 1–5 · Long-Setup am Ende W4 (W5 erwartet)",
        "invalidation_price": 205.0,
        "target_zone": {"low": 250.0, "high": 265.0},
        "target_zone_extended": {"low": 275.0, "high": 290.0},
        "valid_count_total": 1, "alt_count": None,
        "valid_count_total_v2": 2,
        "alt_count_v2": {"count_label": "Ende W2 (W3 erwartet)", "kind": "correction"},
        "vol_ratio_w3_w1": 0.7, "confluence": {"target": ["round"], "invalidation": []},
        "appearance_count": 3, "chart_points": [], "count_wave_labels": [],
    }
    e.update(kw)
    return e


def _reply(text, tin=900, tout=120):
    return {"content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": tin, "output_tokens": tout}}


GOOD = json.dumps({"lesart": "Die Zählung sieht den Titel am Ende der vierten Welle.",
                   "gegenargument": "Das W3-Volumen liegt unter dem der W1.",
                   "concern_level": "high"}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def test_parse_plain_json():
    p = ac._parse_reply(GOOD)
    assert p["concern_level"] == "high" and p["lesart"].startswith("Die Zählung")


def test_parse_tolerates_codefence():
    assert ac._parse_reply(f"```json\n{GOOD}\n```") is not None


def test_parse_rejects_garbage_and_bad_level():
    assert ac._parse_reply("kein json") is None
    assert ac._parse_reply(json.dumps({"lesart": "a", "gegenargument": "b",
                                       "concern_level": "kritisch"})) is None
    assert ac._parse_reply(json.dumps({"lesart": "", "gegenargument": "b",
                                       "concern_level": "low"})) is None


# ---------------------------------------------------------------------------
# Aufruf: Erfolg, Retry, Fehler
# ---------------------------------------------------------------------------
def test_comment_for_success_and_tokens(monkeypatch):
    monkeypatch.setattr(ac, "_post", lambda *a, **k: _reply(GOOD))
    c, tin, tout = ac.comment_for(_entry(), "key", NOW)
    assert c["concern_level"] == "high"
    assert c["model"] == ac.AGENT_MODEL and c["generated_at"] == NOW
    assert (tin, tout) == (900, 120)


def test_comment_for_retries_once_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake(*a, **k):
        calls["n"] += 1
        return _reply("kaputt" if calls["n"] == 1 else GOOD)

    monkeypatch.setattr(ac, "_post", fake)
    c, _, _ = ac.comment_for(_entry(), "key", NOW)
    assert calls["n"] == 2 and c is not None


def test_comment_for_gives_up_after_retry(monkeypatch):
    calls = {"n": 0}

    def fake(*a, **k):
        calls["n"] += 1
        return _reply("immer kaputt")

    monkeypatch.setattr(ac, "_post", fake)
    c, _, _ = ac.comment_for(_entry(), "key", NOW)
    assert c is None and calls["n"] == ac.AGENT_PARSE_RETRIES + 1


def test_api_error_is_failsoft(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("kein Netz")

    monkeypatch.setattr(ac, "_post", boom)
    c, tin, tout = ac.comment_for(_entry(), "key", NOW)
    assert c is None and (tin, tout) == (0, 0)


# ---------------------------------------------------------------------------
# Annotation über den Report
# ---------------------------------------------------------------------------
def _report():
    return {"markets": {"US": {"candidates": [_entry("AMAT"), _entry("CVS")]},
                        "DE": {"candidates": [_entry("SAP.DE")]}},
            "watchlist": {"entries": [_entry("PANW")]}}


def test_no_op_without_key(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("darf ohne Key NICHT aufgerufen werden")

    monkeypatch.setattr(ac, "_post", boom)
    rep = _report()
    diag = ac.annotate_agent_comments(rep, "", NOW)
    assert diag == {"kandidaten": 0, "kommentare": 0, "input_tokens": 0, "output_tokens": 0}
    # Feld gar nicht gesetzt -> Frontend blendet die Sektion aus.
    assert "agent_comment" not in rep["markets"]["US"]["candidates"][0]


def test_annotates_only_market_top5_not_watchlist(monkeypatch):
    monkeypatch.setattr(ac, "_post", lambda *a, **k: _reply(GOOD))
    rep = _report()
    diag = ac.annotate_agent_comments(rep, "key", NOW)
    assert diag["kandidaten"] == 3 and diag["kommentare"] == 3
    assert diag["input_tokens"] == 2700 and diag["output_tokens"] == 360
    for mk in ("US", "DE"):
        for c in rep["markets"][mk]["candidates"]:
            assert c["agent_comment"]["concern_level"] == "high"
    # Watchlist bleibt ausdrücklich unberührt.
    assert "agent_comment" not in rep["watchlist"]["entries"][0]


def test_failed_comment_sets_null(monkeypatch):
    monkeypatch.setattr(ac, "_post", lambda *a, **k: _reply("kaputt"))
    rep = _report()
    ac.annotate_agent_comments(rep, "key", NOW)
    assert rep["markets"]["US"]["candidates"][0]["agent_comment"] is None


# ---------------------------------------------------------------------------
# HARTE GRENZE: kein Score-/Ranking-/Filter-Effekt
# ---------------------------------------------------------------------------
def test_ranking_and_scores_byte_identical(monkeypatch):
    monkeypatch.setattr(ac, "_post", lambda *a, **k: _reply(GOOD))
    rep = _report()
    before = copy.deepcopy(rep)
    ac.annotate_agent_comments(rep, "key", NOW)
    for mk in ("US", "DE"):
        b, a = before["markets"][mk]["candidates"], rep["markets"][mk]["candidates"]
        assert [c["ticker"] for c in b] == [c["ticker"] for c in a]        # Reihenfolge
        assert [c["score_heuristic"] for c in b] == [c["score_heuristic"] for c in a]
        for cb, ca in zip(b, a):
            # Einziger Unterschied ist das additive Feld.
            assert set(ca) - set(cb) == {"agent_comment"}
            assert {k: v for k, v in ca.items() if k != "agent_comment"} == cb


def test_facts_contain_only_own_pipeline_fields():
    f = ac.build_facts(_entry())
    assert f["ticker"] == "AMAT" and f["zaehlung"].startswith("Impuls")
    assert f["volumen_w3_zu_w1"] == 0.7 and f["valide_zaehlungen_v2"] == 2
    # Keine externen/erfundenen Schlüssel.
    allowed = {"ticker", "name", "sektor", "kurs", "tagesveraenderung_pct", "zaehlung",
               "invalidierung", "zielzone", "extension", "score_heuristisch",
               "valide_zaehlungen_v2", "alternative_zaehlung", "volumen_w3_zu_w1",
               "volumen_w4_zu_w3", "volumen_w2_zu_w1", "konfluenz",
               "top5_erscheinungen", "w2_retrace_pct", "w4_retrace_pct",
               "alternation_beobachtet"}
    assert set(f) <= allowed


# ---------------------------------------------------------------------------
# Messung: Einfrieren bei Anlage
# ---------------------------------------------------------------------------
def _fc_entry(**kw):
    e = {"ticker": "TST", "close": 100.0, "score_heuristic": 70.0,
         "target_zone": {"low": 120.0, "high": 130.0},
         "target_zone_extended": {"low": 140.0, "high": 150.0},
         "invalidation_price": 90.0, "direction": "long", "count_label": "W4",
         "chart_points": [], "count_wave_labels": []}
    e.update(kw)
    return e


def test_freeze_agent_level_and_model():
    e = _fc_entry(agent_comment={"lesart": "x", "gegenargument": "y",
                                 "concern_level": "high", "model": ac.AGENT_MODEL,
                                 "generated_at": NOW})
    rec = fc._new_record(e, "US", "2026-07-26", "risk_on", "2026-07-26", NOW)
    assert rec["agent_concern_level"] == "high"
    assert rec["agent_model"] == ac.AGENT_MODEL


def test_freeze_null_without_comment_and_on_null_field():
    rec = fc._new_record(_fc_entry(), "US", "2026-07-26", "risk_on", "2026-07-26", NOW)
    assert rec["agent_concern_level"] is None and rec["agent_model"] is None
    rec2 = fc._new_record(_fc_entry(agent_comment=None), "US", "2026-07-26",
                          "risk_on", "2026-07-26", NOW)
    assert rec2["agent_concern_level"] is None


# ---------------------------------------------------------------------------
# Kein Key-Leak
# ---------------------------------------------------------------------------
def test_key_never_logged(monkeypatch, capsys):
    def boom(*a, **k):
        raise RuntimeError("401 unauthorized")

    monkeypatch.setattr(ac, "_post", boom)
    rep = _report()
    ac.annotate_agent_comments(rep, "sk-ant-GEHEIM-123", NOW)
    out = capsys.readouterr().out
    assert "sk-ant-GEHEIM-123" not in out and "GEHEIM" not in out
