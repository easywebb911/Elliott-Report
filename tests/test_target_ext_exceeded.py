"""Lücken-Schluss beim `target_exceeded`-Filter: auch gegen die Extension-Zone
prüfen (26.08.2026, read-only-Diagnose vom selben Tag).

BEFUND (Diagnose, unverändert gültig): `build_candidate()` prüfte bislang
NUR `close >= target_zone.low` (Basiszone). Bei end_of_w4-Setups skaliert
`target_zone_extended` über die Netto-Strecke P0->P3 (`config.TARGET_EXTENSIONS
["w5_ext"]`), `target_zone` über W1 (`["w5"]`) — je nach Geometrie kann
`target_zone_extended.low` UNTER `target_zone.low` liegen. Ein Titel, dessen
Kurs zwischen beiden Schwellen liegt, rutschte so durch den Vor-Aufnahme-
Filter und wurde erst beim Reifungslauf über den #28-PRU-Guard
(`pre_reached_ext`) nachträglich als "ausgeschlossen" markiert — belegter
Anlassfall: JUN3.DE@2026-08-06 (entry_close 25,82, target_zone.low 25,9843,
target_zone_extended.low 25,8148).

GRENZEN dieses PRs (aus dem Diagnose-Auftrag): KEINE rückwirkende Änderung an
bereits gesammelten Episoden (auch nicht JUN3.DE selbst) — die neue Prüfung
wirkt nur auf NEU entstehende Kandidaten. Der `pre_reached_ext`-Marker-
Mechanismus in `forward_collection.py` bleibt UNVERÄNDERT bestehen
(Verteidigung in der Tiefe, auch wenn er seltener greifen sollte) — dieser
PR fasst diese Datei nicht an (s. `test_forward_collection_py_unangetastet`).
Der Watchlist-Aufruf (`exclude_target_reached=False`) bleibt unverändert.
"""
from __future__ import annotations

import io
import contextlib
from pathlib import Path

import elliott_pipeline as pipe
import config

ROOT = Path(__file__).resolve().parent.parent
W = config.ZIGZAG_WINDOW


# ---------------------------------------------------------------------------
# 1) Wert-Test mit JUN3.DE@2026-08-06s ECHTEN historischen Werten
# ---------------------------------------------------------------------------
def test_jun3de_reale_werte_werden_jetzt_vor_aufnahme_verworfen():
    """Nachrechnung mit den echten, in der Diagnose belegten Zahlen: der
    Kandidat wäre mit der NEUEN Logik VOR der Aufnahme verworfen worden."""
    close = 25.82
    target_zone = {"low": 25.9843, "high": 26.84}
    target_zone_extended = {"low": 25.8148, "high": 26.5652}

    grund = pipe._zone_bereits_erreicht_grund(close, target_zone, target_zone_extended)
    assert grund == pipe.TARGET_EXT_EXCEEDED


def test_grenzfall_exakt_auf_extension_zonen_schwelle_wird_verworfen():
    """Lehre aus #81 (>= vs. > an einer Schwelle): der Grenzfall selbst muss
    einen dedizierten Test haben, nicht nur der Normalfall. `close ==
    target_zone_extended.low` MUSS greifen (inklusiv, wie die bestehende
    Basiszonen-Schwelle es auch schon war)."""
    target_zone = {"low": 140.0, "high": 150.0}
    target_zone_extended = {"low": 130.0, "high": 138.0}
    grund = pipe._zone_bereits_erreicht_grund(130.0, target_zone, target_zone_extended)
    assert grund == pipe.TARGET_EXT_EXCEEDED


def test_grenzfall_knapp_unter_extension_zonen_schwelle_bleibt_zugelassen():
    """Gegenprobe zum Grenzfall: einen Tick UNTER der Schwelle darf NICHT
    verworfen werden (sonst wäre die Schwelle nicht wirklich `>=`)."""
    target_zone = {"low": 140.0, "high": 150.0}
    target_zone_extended = {"low": 130.0, "high": 138.0}
    grund = pipe._zone_bereits_erreicht_grund(129.9999, target_zone, target_zone_extended)
    assert grund is None


def test_jun3de_reale_werte_waeren_am_alten_basiszonen_check_vorbeigerutscht():
    """Gegenprobe, damit der Vorher/Nachher-Unterschied belegt ist, nicht nur
    behauptet: die ALTE Prüfung (nur target_zone.low) hätte NICHT gegriffen."""
    close = 25.82
    tlow = 25.9843
    assert not (close >= tlow), "sonst wäre die Lücke nie aufgetreten"


# ---------------------------------------------------------------------------
# 2) Integrations-Test über build_candidate (echte Pivot-/ZigZag-Pipeline,
#    kein isolierter Funktionsaufruf) — konstruierter end_of_w4-Fall mit
#    derselben strukturellen Lücke wie JUN3.DE (extended.low < target.low).
# ---------------------------------------------------------------------------
def _w4_luecke(tail_close):
    """end_of_w4-Setup P0=100, P1=120, P2=110, P3=124, P4=122 -> target_zone
    [134.36, 142.0], target_zone_extended [131.168, 136.832] (extended.low <
    target.low, echte Lücke wie bei JUN3.DE) — per zigzag/classify_setup
    nachgerechnet, nicht angenommen (s. Kommentar unten)."""
    seg = [(108.0, 100.0, W + 2), (100.0, 120.0, W + 4), (120.0, 110.0, W + 3),
           (110.0, 124.0, W + 3), (124.0, 122.0, W + 3), (122.0, tail_close, W + 2)]
    closes = []
    for s, e, n in seg:
        rng = range(n + 1) if not closes else range(1, n + 1)
        for k in rng:
            closes.append(s + (e - s) * (k / n))
    return [f"d{i}" for i in range(len(closes))], closes


def test_luecken_fixture_hat_tatsaechlich_extended_low_unter_target_low():
    """Voraussetzung des ganzen Tests belegen, nicht annehmen: die Fixture
    muss wirklich die Lücke reproduzieren, sonst testet der Rest nichts."""
    d, c = _w4_luecke(133.0)
    pivots = pipe.zigzag(c, config.ZIGZAG_WINDOW, d)
    setup = pipe.classify_setup(pivots, c[-1])
    assert setup["setup"] == "end_of_w4"
    assert setup["target_zone_extended"]["low"] < setup["target_zone"]["low"]


def test_kandidat_in_der_luecke_wird_jetzt_vor_aufnahme_verworfen():
    d, c = _w4_luecke(133.0)  # zwischen ext.low (131.168) und target.low (134.36)
    entry, reason, detail = pipe.build_candidate("T", d, c)
    assert entry is None
    assert reason == pipe.TARGET_EXT_EXCEEDED
    assert "target_zone_extended.low=131.168" in detail


def test_derselbe_kandidat_waere_am_alten_filter_vorbeigerutscht():
    """Vorher/Nachher am selben Fall: close < target_zone.low -> der ALTE
    Filter hätte NICHT gegriffen (das ist die geschlossene Lücke)."""
    d, c = _w4_luecke(133.0)
    pivots = pipe.zigzag(c, config.ZIGZAG_WINDOW, d)
    setup = pipe.classify_setup(pivots, c[-1])
    assert not (c[-1] >= setup["target_zone"]["low"])


# ---------------------------------------------------------------------------
# 3) Regressionstests (Auftrags-Vorgabe: bestehendes Verhalten unverändert)
# ---------------------------------------------------------------------------
def test_regression_unter_beiden_zonen_bleibt_zugelassen():
    """Kein Overblocking: ein Kandidat unter BEIDEN Schwellen bleibt weiterhin
    unverworfen."""
    d, c = _w4_luecke(128.0)  # < ext.low (131.168) UND < target.low (134.36)
    entry, reason, _ = pipe.build_candidate("T", d, c)
    assert entry is not None and reason is None


def test_regression_ueber_basiszone_bleibt_target_exceeded():
    """Ein Fall, der schon vorher korrekt über die Basiszone verworfen wurde,
    bleibt mit demselben Grund verworfen (Basiszonen-Prüfung zuerst)."""
    d, c = _w4_luecke(145.0)  # deutlich über target_zone.low (134.36)
    entry, reason, _ = pipe.build_candidate("T", d, c)
    assert entry is None and reason == pipe.TARGET_EXCEEDED


def test_regression_watchlist_aufruf_zeigt_luecken_fall_weiterhin():
    """Watchlist (`exclude_target_reached=False`) bleibt unverändert — auch
    der neue Lücken-Fall bleibt dort sichtbar, keine neue Verwerfung."""
    d, c = _w4_luecke(133.0)
    entry, reason, _ = pipe.build_candidate("T", d, c, exclude_target_reached=False)
    assert entry is not None and reason is None


def test_regression_watchlist_aufruf_zeile_unveraendert():
    """Der Watchlist-Aufruf selbst (Zeile im Quelltext) bleibt exakt so, wie
    er vor dieser Änderung war — GRENZEN-Vorgabe wörtlich geprüft."""
    quelle = (ROOT / "scripts/elliott_pipeline.py").read_text(encoding="utf-8")
    assert "exclude_target_reached=False," in quelle


# ---------------------------------------------------------------------------
# 4) Struktur: Reason-Code, SKIP_REASONS, Zähler, Log, Determinismus
# ---------------------------------------------------------------------------
def test_target_ext_exceeded_in_skip_reasons():
    assert pipe.TARGET_EXT_EXCEEDED in pipe.SKIP_REASONS
    assert pipe.TARGET_EXT_EXCEEDED != pipe.TARGET_EXCEEDED


def _mixed_fetcher(mapping):
    ok_d, ok_c = _w4_luecke(128.0)
    ext_d, ext_c = _w4_luecke(133.0)
    base_d, base_c = _w4_luecke(145.0)

    def fetcher(ticker):
        kind = mapping[ticker]
        if kind == "ext_exceeded":
            return pipe.FetchOutcome(data=(list(ext_d), list(ext_c)))
        if kind == "exceeded":
            return pipe.FetchOutcome(data=(list(base_d), list(base_c)))
        return pipe.FetchOutcome(data=(list(ok_d), list(ok_c)))

    return fetcher


def test_scan_market_zaehlt_beide_gruende_getrennt():
    universe = ["A", "B", "X1", "EXT1", "EXT2"]
    mapping = {"A": "ok", "B": "ok", "X1": "exceeded",
               "EXT1": "ext_exceeded", "EXT2": "ext_exceeded"}
    candidates, reason_counts, _s, _d, _b, _lb = pipe._scan_market(
        universe, _mixed_fetcher(mapping))
    assert len(candidates) == 2
    assert reason_counts[pipe.TARGET_EXCEEDED] == 1
    assert reason_counts[pipe.TARGET_EXT_EXCEEDED] == 2


def test_log_zeile_enthaelt_neuen_zaehler(monkeypatch):
    """`_scan_market` selbst loggt bewusst NICHT (s. eigener Docstring "ohne
    I/O/Logging") — das Diag-Log sitzt in `build_market`, das den Zähler
    hier bezieht."""
    mapping = {"EXT1": "ext_exceeded"}
    monkeypatch.setitem(config.MARKETS, "US",
                         {**config.MARKETS["US"], "universe": ["EXT1"]})
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        pipe.build_market("US", _mixed_fetcher(mapping))
    ausgabe = buf.getvalue()
    assert "target_ext_exceeded=1" in ausgabe


def test_scan_market_deterministic_mit_beiden_gruenden():
    universe = ["A", "X1", "EXT1"]
    mapping = {"A": "ok", "X1": "exceeded", "EXT1": "ext_exceeded"}
    import json
    a = pipe._scan_market(universe, _mixed_fetcher(mapping))[0]
    b = pipe._scan_market(universe, _mixed_fetcher(mapping))[0]
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# ---------------------------------------------------------------------------
# 5) Konsumenten (Exzellenz-Selbstprüfung Punkt 4): Frontend-Label, keine
#    Änderung am unabhängigen PRU-Guard-Marker-Mechanismus.
# ---------------------------------------------------------------------------
def test_frontend_rlabel_kennt_den_neuen_grund():
    html = (ROOT / "docs/index.html").read_text(encoding="utf-8")
    start = html.index("const RLABEL = {")
    block = html[start:html.index("};", start)]
    assert "target_ext_exceeded:" in block
    assert "target_exceeded:" in block  # bestehender Eintrag bleibt


def test_forward_collection_py_unangetastet():
    """GRENZEN: der #28-PRU-Guard (pre_reached_ext-Marker) bleibt exakt so
    bestehen wie vor dieser Änderung — dieser PR rührt die Datei nicht an."""
    quelle = (ROOT / "scripts/forward_collection.py").read_text(encoding="utf-8")
    assert "pre_reached_ext = entry >= elow" in quelle
    assert "pre_reached_target = entry >= tlow" in quelle
