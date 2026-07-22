"""JSON-Schema-Check des erzeugten Reports (mit synthetischem Fetcher, ohne
Netz) plus grundlegende Invarianten & Determinismus."""
import json

import jsonschema

import config
import elliott_pipeline as pipe


FIXED_TS = "2024-01-01T00:00:00Z"


# Erwartetes Schema (bewusst streng auf den Kernfeldern, additiv erweiterbar).
REPORT_SCHEMA = {
    "type": "object",
    "required": ["schema_version", "run_timestamp_utc", "markets"],
    "properties": {
        "schema_version": {"type": "integer"},
        "run_timestamp_utc": {"type": "string"},
        "generator": {"type": "string"},
        "markets": {
            "type": "object",
            "required": ["US", "DE"],
            "additionalProperties": {
                "type": "object",
                "required": ["label", "universe_size", "candidates"],
                "properties": {
                    "label": {"type": "string"},
                    "universe_size": {"type": "integer"},
                    "candidates": {
                        "type": "array",
                        "maxItems": config.TOP_N,
                        "items": {
                            "type": "object",
                            "required": [
                                "ticker",
                                "name",
                                "close",
                                "count_label",
                                "invalidation_price",
                                "target_zone",
                                "target_zone_extended",
                                "score_heuristic",
                                "chart_points",
                                "status",
                                "direction",
                                "company_name",
                                "sector",
                                "change_pct",
                                "change_abs",
                                "count_wave_labels",
                                "higher_degree",
                            ],
                            "properties": {
                                "ticker": {"type": "string"},
                                "name": {"type": "string"},
                                "company_name": {"type": "string"},
                                "sector": {"type": "string"},
                                "change_pct": {"type": "number"},
                                "change_abs": {"type": "number"},
                                "close": {"type": "number"},
                                "direction": {"type": "string", "enum": ["long"]},
                                "count_label": {"type": "string"},
                                "invalidation_price": {"type": "number"},
                                "target_zone": {
                                    "type": "object",
                                    "required": ["low", "high"],
                                    "properties": {
                                        "low": {"type": "number"},
                                        "high": {"type": "number"},
                                    },
                                },
                                "target_zone_extended": {
                                    "type": "object",
                                    "required": ["low", "high"],
                                    "properties": {
                                        "low": {"type": "number"},
                                        "high": {"type": "number"},
                                    },
                                },
                                "score_heuristic": {"type": "number"},
                                "chart_points": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "required": ["index", "price", "kind"],
                                    },
                                },
                                "status": {"type": "string"},
                                "count_wave_labels": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "required": ["index", "wave"],
                                        "properties": {
                                            "index": {"type": "integer"},
                                            "wave": {"type": "integer"},
                                        },
                                    },
                                },
                                "higher_degree": {
                                    "type": ["object", "null"],
                                    "properties": {
                                        "count_label": {"type": "string"},
                                        "invalidation_price": {"type": "number"},
                                        "target_zone": {"type": "object"},
                                        "target_zone_extended": {"type": "object"},
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    },
}


def _build():
    return pipe.build_report(pipe.fetch_synthetic, FIXED_TS)


def test_report_matches_schema():
    report = _build()
    jsonschema.validate(report, REPORT_SCHEMA)


def test_two_markets_with_candidates():
    report = _build()
    assert set(report["markets"].keys()) == {"US", "DE"}
    for m in report["markets"].values():
        # Synthetischer Fetcher liefert für jeden Ticker ein valides Setup.
        assert 1 <= len(m["candidates"]) <= config.TOP_N


def test_all_candidates_are_long():
    # Long-only-Report: jeder Kandidat trägt direction "long" und kein
    # count_label enthält "Short".
    report = _build()
    for m in report["markets"].values():
        for c in m["candidates"]:
            assert c["direction"] == "long"
            assert "Short" not in c["count_label"]


def test_no_probability_language():
    # Sicherheitsnetz: keine Wahrscheinlichkeits-Sprache im JSON.
    blob = json.dumps(_build(), ensure_ascii=False).lower()
    for banned in ("wahrscheinlich", "probability", "confidence", "trefferquote"):
        assert banned not in blob


def test_candidates_sorted_by_score_desc():
    report = _build()
    for m in report["markets"].values():
        scores = [c["score_heuristic"] for c in m["candidates"]]
        assert scores == sorted(scores, reverse=True)


def test_determinism_same_input_same_output():
    a = json.dumps(_build(), sort_keys=True)
    b = json.dumps(_build(), sort_keys=True)
    assert a == b


def test_extension_zone_present_and_ordered():
    # Feld ist immer vorhanden und min/max-geordnet (auch degeneriert).
    report = _build()
    seen = 0
    for m in report["markets"].values():
        for c in m["candidates"]:
            ext = c["target_zone_extended"]
            assert set(ext) == {"low", "high"}
            assert ext["low"] <= ext["high"]  # min/max-Ordnung abgesichert
            seen += 1
    assert seen > 0


def test_extension_above_base_for_w2_standard_case():
    # Standard-Fall: die synthetischen Kandidaten sind W2-Setups. Dort ist die
    # W3-Extension (1.618–2.618 × W1) IMMER über der Basis (1.0–1.618 × W1).
    # (Für W4/W5 gilt das nicht garantiert — siehe PR-Text: kurze Netto-Strecke
    #  P0->P3 kann die Ext unter die Basis drücken; das Frontend blendet sie
    #  dann aus.)
    report = _build()
    for m in report["markets"].values():
        for c in m["candidates"]:
            assert "W2" in c["count_label"]  # Synthetik erzeugt W2-Setups
            assert c["target_zone_extended"]["high"] > c["target_zone"]["high"]


def test_score_is_neutral_to_extension_field():
    # BEWEIS Score-Neutralität: score_setup liest target_zone_extended NICHT.
    # Derselbe Setup-Zustand ergibt denselben Score, egal ob/welche Extension
    # gesetzt ist.
    setup = {"base_points": 45.0, "fib_bonus": 12.0, "inval_bonus": 9.0}
    s0 = pipe.score_setup(setup)
    setup["target_zone"] = {"low": 10.0, "high": 20.0}
    setup["target_zone_extended"] = {"low": 25.0, "high": 40.0}
    s1 = pipe.score_setup(setup)
    setup["target_zone_extended"] = {"low": 999.0, "high": 9999.0}
    s2 = pipe.score_setup(setup)
    assert s0 == s1 == s2


def test_change_pct_from_last_two_closes():
    # change_pct/change_abs = Tagesveränderung aus den letzten ZWEI Closes.
    dates, closes = pipe.fetch_synthetic("AAPL").data
    entry, reason, _ = pipe.build_candidate("AAPL", dates, closes)
    assert entry is not None and reason is None
    prev, last = closes[-2], closes[-1]
    assert entry["change_abs"] == round(last - prev, 4)
    assert entry["change_pct"] == round((last / prev - 1.0) * 100.0, 4)


def test_company_meta_loaded_and_failsoft():
    # Bekannter Ticker -> kuratierter Name/Sektor; unbekannter -> Fallback.
    assert pipe._meta_name("AAPL") == "Apple Inc."
    assert pipe._meta_sector("AAPL") == "Technology"
    assert pipe._meta_name("ZZ_UNKNOWN") == "ZZ_UNKNOWN"  # fail-soft -> Ticker
    assert pipe._meta_sector("ZZ_UNKNOWN") == ""


def test_new_header_fields_score_neutral():
    # company_name/sector/change_* fließen NICHT in den Score.
    setup = {"base_points": 55.0, "fib_bonus": 5.0, "inval_bonus": 10.0}
    s0 = pipe.score_setup(setup)
    setup.update({"company_name": "X AG", "sector": "Tech", "change_pct": 3.1, "change_abs": 2.0})
    assert pipe.score_setup(setup) == s0


def test_ranking_unchanged_when_extension_stripped():
    # BEWEIS Ranking-Neutralität: Entfernt man das Extension-Feld, bleibt die
    # Reihenfolge (Score desc, Ticker asc) je Markt identisch.
    report = _build()
    for m in report["markets"].values():
        with_ext = [(c["ticker"], c["score_heuristic"]) for c in m["candidates"]]
        stripped = []
        for c in m["candidates"]:
            c2 = {k: v for k, v in c.items() if k != "target_zone_extended"}
            stripped.append(c2)
        stripped.sort(key=lambda e: (-e["score_heuristic"], e["ticker"]))
        assert [(c["ticker"], c["score_heuristic"]) for c in stripped] == with_ext


# --- Großer Wellengrad (higher_degree, Wochen) + Wellen-Ziffern ---
def _build_weekly():
    return pipe.build_report(pipe.fetch_synthetic, FIXED_TS, pipe.fetch_synthetic_weekly)


def test_higher_degree_populated_with_weekly_fetcher():
    report = _build_weekly()
    seen = 0
    for m in report["markets"].values():
        for c in m["candidates"]:
            hd = c["higher_degree"]
            assert hd is not None, "Wochen-Fetcher liefert -> higher_degree gesetzt"
            for key in ("count_label", "invalidation_price", "target_zone", "target_zone_extended"):
                assert key in hd
            assert set(hd["target_zone"]) == {"low", "high"}
            assert "Short" not in hd["count_label"]  # long-only
            seen += 1
    assert seen > 0


def test_higher_degree_none_without_weekly_fetcher():
    # Ohne Wochen-Fetcher (Default) ist higher_degree null (Feld existiert).
    report = _build()
    for m in report["markets"].values():
        for c in m["candidates"]:
            assert c["higher_degree"] is None


def test_higher_degree_failsoft_on_empty_and_none():
    # Fail-soft: leere Quelle bzw. kein Fetcher -> None (kein Absturz).
    empty = lambda t: pipe.FetchOutcome(reason=pipe.EMPTY_DATA, detail="leer")
    assert pipe.higher_degree_for("AAPL", empty) is None
    assert pipe.higher_degree_for("AAPL", None) is None
    boom = lambda t: (_ for _ in ()).throw(RuntimeError("net down"))
    assert pipe.higher_degree_for("AAPL", boom) is None  # Exception -> None


def test_higher_degree_ranking_neutral():
    # higher_degree wird NACH dem Ranking gesetzt -> Reihenfolge/Scores gleich.
    a = _build()
    b = _build_weekly()
    for mk in ("US", "DE"):
        ra = [(c["ticker"], c["score_heuristic"]) for c in a["markets"][mk]["candidates"]]
        rb = [(c["ticker"], c["score_heuristic"]) for c in b["markets"][mk]["candidates"]]
        assert ra == rb


def test_count_wave_labels_map_last_k_pivots():
    # Ziffern sitzen auf den letzten k Pivots (k=3 bei W2, 5 bei W4), wave 0..k-1.
    report = _build()
    for m in report["markets"].values():
        for c in m["candidates"]:
            cwl = c["count_wave_labels"]
            k = 5 if "W4" in c["count_label"] else 3
            ncp = len(c["chart_points"])
            assert [x["wave"] for x in cwl] == list(range(k))
            assert [x["index"] for x in cwl] == list(range(ncp - k, ncp))
            # letzter Index ist der aktuelle Pivot
            assert cwl[-1]["index"] == ncp - 1
