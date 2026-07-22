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
                                "score_heuristic",
                                "chart_points",
                                "status",
                            ],
                            "properties": {
                                "ticker": {"type": "string"},
                                "name": {"type": "string"},
                                "close": {"type": "number"},
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
                                "score_heuristic": {"type": "number"},
                                "chart_points": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "required": ["index", "price", "kind"],
                                    },
                                },
                                "status": {"type": "string"},
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
