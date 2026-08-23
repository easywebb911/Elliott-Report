"""Guardian-Nit aus #101 behoben: ATR(14)-Band auch für No-Setup-Watchlist-
Titel (23.08.2026, Folge-Auftrag "Bau-Auftrag klein").

ANLASS (Guardian-Zweitblick, PR #101, dokumentiert als Nit, kein Blocker):
No-Setup-Watchlist-Titel (`wl_status != 'setup'`, kein regelkonformer
Long-Count auf TAGESBASIS) können bei `timeframes.week`/`.month` durchaus
einen validen Long-Count MIT `target_zone` tragen (`_analyze_from_fetch`
läuft unabhängig vom Tages-Setup) — `_wl_no_setup_entry` bekam `atr_14`
bisher aber NIE zugewiesen. Ergebnis: `watchlistCard()`s `tfPanel(...)`-
Aufruf zeigte für diese Zeilen eine ungepolsterte (scharfe) Zone, während
Setup-Karten (`card()`) dieselbe Zone seit #101 gepolstert (als Band) zeigen
— eine optische Inkonsistenz, kein Datenfehler (Score/Ranking/Fibonacci-
Berechnung unberührt).

VORHER/NACHHER (am selben konstruierten Beispiel-Titel, s. u.):
  vorher:  "atr_14" in e            -> False  (Schlüssel existierte gar nicht,
                                                weder in `_wl_base_entry` noch
                                                in `_wl_no_setup_entry`)
  nachher: e["atr_14"] == 8.5       -> dieselbe ATR(14)-Formel/Quelle wie bei
                                        Setup-Einträgen seit #101
                                        (scripts/volatility.py, unverändert).

KEINE NEUE BERECHNUNG: `atr_14` wird in `build_watchlist_entry` bereits VOR
dieser Änderung berechnet (Fetch/Sink, s. #101) — dieser Auftrag reicht den
bereits vorhandenen Wert nur zusätzlich in `_wl_no_setup_entry` UND den
`tfPanel(...)`-Aufruf in `watchlistCard()` durch.
"""
from __future__ import annotations

from pathlib import Path

import elliott_pipeline as pipe
import volatility

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "docs/index.html").read_text(encoding="utf-8")

# Hand-gerechnete True-Range-Werte (identisch zur MA-Illustration aus #101,
# tests/test_atr_volatility.py) — Mittel exakt 8,5. Closes bleiben FLACH
# (garantiert NULL Pivots -> garantiert kein Tages-Setup, s. bestehender Test
# `test_watchlist_no_setup_entry_shows_state`); nur High/Low variieren in den
# letzten 14 Bars, damit ATR trotzdem einen echten, nachrechenbaren Wert hat.
_TR = [8, 9, 7, 10, 8, 9, 7, 10, 8, 9, 7, 10, 8, 9]
_N = 80
_DATES = [f"d{i}" for i in range(_N)]
_CLOSES = [100.0] * _N
_HIGHS = [100.0] * (_N - 14) + [100.0 + t / 2 for t in _TR]
_LOWS = [100.0] * (_N - 14) + [100.0 - t / 2 for t in _TR]
_DAY_ATR = volatility.atr14(_HIGHS, _LOWS, _CLOSES)


def test_hand_gerechneter_atr_fuer_die_flache_reihe():
    assert sum(_TR) / 14 == 8.5
    assert _DAY_ATR == 8.5


# ---------------------------------------------------------------------------
# (1) _wl_no_setup_entry — additiv, mit explizitem Vorher/Nachher
# ---------------------------------------------------------------------------
def test_wl_no_setup_entry_vorher_kein_schluessel_nachher_gesetzt():
    e_ohne = pipe._wl_no_setup_entry("FLATX", _DATES, _CLOSES, pipe.NO_VALID_COUNT, "")
    assert e_ohne["atr_14"] is None, "Default (kein atr_14 übergeben) bleibt None"

    e_mit = pipe._wl_no_setup_entry("FLATX", _DATES, _CLOSES, pipe.NO_VALID_COUNT, "",
                                    atr_14=_DAY_ATR)
    assert e_mit["atr_14"] == 8.5


def test_wl_base_entry_traegt_atr_14_feld_fail_soft():
    """`_wl_base_entry` (Fehler-Karten-Gerüst) trägt das Feld jetzt IMMER,
    Default None — dieselbe Semantik wie target_zone/invalidation_price."""
    e = pipe._wl_error_entry("BADX", pipe.FETCH_ERROR, "boom")
    assert e["atr_14"] is None


# ---------------------------------------------------------------------------
# (2) End-to-end über build_watchlist_entry — der von Guardian beschriebene
# Fall: kein Tages-Setup, aber valider Wochen-Long-Count mit target_zone.
# ---------------------------------------------------------------------------
def _flat_day_fetcher(ticker):
    return pipe.FetchOutcome(data=(_DATES, _CLOSES), atr_14=_DAY_ATR)


def test_no_setup_titel_mit_validem_wochen_count_bekommt_jetzt_atr_band():
    e = pipe.build_watchlist_entry("FLATW", _flat_day_fetcher,
                                   weekly_fetcher=pipe.fetch_synthetic_weekly)
    assert e["wl_status"] == "no_setup", "flache Tagesreihe -> kein Tages-Setup"
    week = e["timeframes"]["week"]
    assert week is not None and week.get("target_zone") is not None, (
        "der Wochen-Count muss unabhängig vom Tages-Setup ein valides "
        "Long-Setup mit target_zone liefern — sonst testet dies nicht den "
        "von Guardian beschriebenen Fall")
    assert e["atr_14"] == 8.5, "NACHHER: derselbe ATR wie bei Setup-Einträgen"


def test_no_setup_titel_ohne_high_low_bleibt_fail_soft_none():
    """Gegenprobe: fehlt High/Low (z. B. Offline-/Demo-Fetcher), bleibt
    atr_14 ehrlich None — kein erfundener Band-Wert."""
    def fetcher(ticker):
        return pipe.FetchOutcome(data=(_DATES, _CLOSES), atr_14=None)
    e = pipe.build_watchlist_entry("FLATN", fetcher,
                                   weekly_fetcher=pipe.fetch_synthetic_weekly)
    assert e["wl_status"] == "no_setup"
    assert e["atr_14"] is None


# ---------------------------------------------------------------------------
# (3) Regression: Setup-Titel-Pfad aus #101 unverändert (ruft
# `_wl_no_setup_entry` strukturell nie auf, ist also unberührt — hier
# trotzdem direkt nachgewiesen statt nur behauptet).
# ---------------------------------------------------------------------------
def test_setup_titel_pfad_unveraendert():
    e = pipe.build_watchlist_entry("AAPL", pipe.fetch_synthetic,
                                   pipe.fetch_synthetic_weekly)
    assert e["wl_status"] == "setup"
    # fetch_synthetic liefert bewusst kein High/Low (Offline-/Demo-Fetcher,
    # unverändert seit #101) -> atr_14 bleibt None, wie vor diesem Auftrag.
    assert e["atr_14"] is None


def test_setup_titel_mit_echtem_atr_unveraendert():
    """Derselbe Setup-Pfad, aber MIT einem echten ATR-Wert im Outcome (wie
    beim realen yfinance-Fetch seit #101) — muss weiterhin unverändert
    durchgereicht werden."""
    def fetcher(ticker):
        out = pipe.fetch_synthetic(ticker)
        dates, closes = out.data
        return pipe.FetchOutcome(data=(dates, closes), volumes=out.volumes,
                                 atr_14=8.5)
    e = pipe.build_watchlist_entry("AMAT", fetcher, pipe.fetch_synthetic_weekly)
    assert e["wl_status"] == "setup"
    assert e["atr_14"] == 8.5


# ---------------------------------------------------------------------------
# (4) Frontend: watchlistCard() reicht c.atr_14 jetzt an tfPanel durch.
# ---------------------------------------------------------------------------
def _fn(name: str, tiefe: str = "    ") -> str:
    marke = f"{tiefe}function {name}("
    start = HTML.index(marke)
    return HTML[start:HTML.index(f"\n{tiefe}}}", start) + len(f"\n{tiefe}}}")]


def test_watchlistcard_reicht_atr_14_an_tfpanel_durch():
    koerper = _fn("watchlistCard")
    assert "tfPanel(c.timeframes, c.structure, c.close, c.market_key, c.atr_14)" in koerper


def test_card_aufruf_von_tfpanel_bleibt_unveraendert():
    """Regression: der ANDERE tfPanel-Aufruf (in `card()`, Setup-Karten aus
    #101) bleibt exakt wie vorher — keine Doppel-Änderung, kein Versehen."""
    koerper = _fn("card")
    assert "tfPanel(c.timeframes, c.structure, c.close, market, c.atr_14)" in koerper
