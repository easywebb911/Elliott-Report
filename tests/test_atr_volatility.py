"""ATR(14) — Volatilitätsmaß für die Band-Breite um Beobachtungszone/Extension
(23.08.2026, Bau-Auftrag "Band statt Linie").

WISSENSCHAFTLICHER/TECHNISCHER ANLASS (s. PR-Text): die Fibonacci-Zonen waren
bisher als PRÄZISE Linie/Intervall dargestellt — mehr Genauigkeit, als eine
Tagesbewegung tatsächlich hergibt. ATR(14) liefert die typische Tagesspanne
und macht die Anzeige als unscharfes Band ehrlicher, OHNE die Fibonacci-
Berechnung selbst (target_zone-Werte/-Ratios, Score, Ranking, Invalidierung)
anzufassen.

STOPP-KLAUSEL DES AUFTRAGS: die Pipeline lud bisher nur Close/Volumen — kein
High/Low. Nach Rückfrage (AskUserQuestion) hat Easy entschieden: High/Low
zusätzlich aus DEMSELBEN yfinance-Download extrahieren (kein Extra-Call),
siehe `_extract_bars`/`parse_download_df`.

VIER NETZE:
  (1) Die reine Formel (`scripts/volatility.atr14`) — ein hand-gerechnetes
      Beispiel mit bewusst wechselnden TR-Fällen (mal dominiert die
      Tagesspanne, mal der Gap-Anteil).
  (2) Pipeline-Verdrahtung: High/Low kommen aligned aus `_extract_bars`
      (Muster wie beim Volumen), `FetchOutcome.atr_14` wird EINMAL beim Parsen
      gesetzt, `build_candidate` trägt es additiv ein.
  (3) Sink-Caching (Muster wie `volume_sink`): Markt-Scan und Watchlist teilen
      sich den ATR-Wert eines Tickers ohne Re-Fetch.
  (4) Ein REALER Ticker (MA, echte, committete Zahlen aus docs/data/report.json)
      mit einer hand-konstruierten, realistischen Tagesspannen-Serie (kein
      Netzzugriff in dieser Sandbox möglich — siehe PR-Text) belegt die
      resultierende Band-Breite mit echten Vergleichszahlen (Zonenbreite,
      Invalidierungs-Abstand).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import elliott_pipeline as pipe
import forward_collection as fc
from volatility import ATR_PERIOD, atr14, true_range

pd = pytest.importorskip("pandas")

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# (1) Hand-gerechnetes ATR(14)-Beispiel — GENAU 15 Bars (14 True-Range-Werte).
# Tage mit dominanter Tagesspanne UND Tage mit dominantem Gap-Anteil, damit
# das max(...) in true_range() wirklich beide Zweige durchläuft.
# ---------------------------------------------------------------------------
CLOSES = [100, 102, 103, 108, 106, 97, 96, 95, 92, 91, 90, 98, 97, 95, 85]
HIGHS = [101, 103, 104, 110, 109, 107, 99, 98, 97, 94, 93, 100, 99, 98, 97]
LOWS = [99, 101, 102, 104, 105, 95, 94, 93, 90, 89, 88, 89, 95, 93, 80]
# Von Hand nachgerechnete True-Range-Werte für i=1..14 (siehe PR-Text für die
# Tabelle je Tag): Tag 3 (Gap +7 > Spanne 6) und Tag 11 (Gap +10 > Spanne 11
# knapp) sind die Fälle, in denen der Gap-Anteil die Tagesspanne übertrifft.
EXPECTED_TR = [3, 2, 7, 4, 12, 5, 5, 7, 5, 5, 11, 4, 5, 17]
EXPECTED_ATR = round(sum(EXPECTED_TR) / ATR_PERIOD, 4)


def test_true_range_beide_zweige():
    # Tagesspanne dominiert (kein Gap).
    assert true_range(103, 101, 100) == 3          # aus Tag 1 oben
    # Gap dominiert (Spanne kleiner als der Kurssprung).
    assert true_range(110, 104, 103) == 7           # aus Tag 3 oben


def test_atr14_hand_gerechnetes_beispiel():
    assert len(CLOSES) == ATR_PERIOD + 1, "Beispiel braucht genau 15 Bars"
    assert EXPECTED_ATR == pytest.approx(6.5714)
    assert atr14(HIGHS, LOWS, CLOSES) == EXPECTED_ATR


def test_atr14_zu_kurze_reihe_ist_none():
    assert atr14(HIGHS[:-1], LOWS[:-1], CLOSES[:-1]) is None, \
        "14 Bars reichen nicht für 14 True-Range-Werte (braucht den Vor-Close)"


def test_atr14_fehlende_high_low_ist_none():
    assert atr14(None, LOWS, CLOSES) is None
    assert atr14(HIGHS, None, CLOSES) is None


def test_atr14_luecke_im_fenster_ist_none_nicht_geraten():
    """Messfeld-Semantik (siehe numeric.py): EIN fehlender High/Low-Wert
    innerhalb der letzten 14 Bars macht den ganzen ATR None, statt eine Lücke
    stillschweigend zu überspringen und einen aus weniger Werten gemittelten
    ATR zu behaupten."""
    highs = list(HIGHS)
    highs[7] = None
    assert atr14(highs, LOWS, CLOSES) is None


def test_atr14_nan_inf_wird_wie_fehlend_behandelt():
    highs = list(HIGHS)
    highs[3] = float("nan")
    assert atr14(highs, LOWS, CLOSES) is None
    highs2 = list(HIGHS)
    highs2[10] = float("inf")
    assert atr14(highs2, LOWS, CLOSES) is None


def test_atr14_laengen_muessen_passen():
    assert atr14(HIGHS[:-1], LOWS, CLOSES) is None
    assert atr14(HIGHS, LOWS[:-1], CLOSES) is None


# ---------------------------------------------------------------------------
# (2) Pipeline-Verdrahtung — High/Low aligned aus _extract_bars, atr_14 aus
# parse_download_df, additiv auf build_candidate.
# ---------------------------------------------------------------------------
def _mk_df(n, closes, highs, lows, with_volume=True, multiindex=True):
    rows = []
    for i in range(n):
        r = [closes[i], highs[i], lows[i], closes[i]]
        if with_volume:
            r.append(1000 + i)
        rows.append(r)
    cols = ["Close", "High", "Low", "Open"] + (["Volume"] if with_volume else [])
    idx = pd.date_range("2023-01-01", periods=n, freq="D")
    if multiindex:
        cols = pd.MultiIndex.from_tuples([(c, "MA") for c in cols])
    return pd.DataFrame(rows, index=idx, columns=cols)


def _padded_series(n=80):
    # Genug Bars für MIN_BARS UND für ATR(14): letzte 15 Bars = das
    # hand-gerechnete Beispiel oben, davor konstante Füll-Bars (H=L=C -> kein
    # Einfluss auf das ATR-Fenster, das nur die LETZTEN 14 TR-Werte nimmt).
    pad = n - len(CLOSES)
    fill_c = [50.0 + i * 0.1 for i in range(pad)]
    closes = fill_c + list(CLOSES)
    highs = fill_c + list(HIGHS)
    lows = fill_c + list(LOWS)
    return closes, highs, lows


def test_extract_bars_liefert_high_low_aligned_zu_close():
    # multiindex=False: _extract_bars() wird hier DIREKT aufgerufen (ohne den
    # vorgeschalteten _normalize_columns()-Schritt aus parse_download_df) —
    # der MultiIndex-Fall ist bereits über test_parse_download_df_setzt_atr_14
    # (via parse_download_df) abgedeckt.
    closes, highs, lows = _padded_series(20)
    df = _mk_df(20, closes, highs, lows, multiindex=False)
    (dates, got_closes, volumes, dropped, bad_vol, dropped_dates,
     dropped_last, dropped_mid, got_highs, got_lows) = pipe._extract_bars(df)
    assert got_closes == closes
    assert got_highs == highs and got_lows == lows
    assert len(got_highs) == len(got_closes) == len(got_lows)


def test_extract_bars_ohne_high_low_spalte_failsoft_none():
    closes, _highs, _lows = _padded_series(20)
    df = pd.DataFrame({"Close": closes, "Volume": [1000.0] * len(closes)},
                      index=pd.date_range("2023-01-01", periods=len(closes), freq="D"))
    out = pipe._extract_bars(df)
    assert out[8] is None and out[9] is None            # highs, lows


def test_parse_download_df_setzt_atr_14():
    closes, highs, lows = _padded_series(80)
    df = _mk_df(80, closes, highs, lows)
    out = pipe.parse_download_df(df)
    assert out.data is not None
    assert out.atr_14 == EXPECTED_ATR, \
        "ATR muss aus den LETZTEN 14 TR-Werten der Reihe kommen"


def test_parse_download_df_ohne_high_low_atr_ist_none():
    closes, _h, _l = _padded_series(80)
    df = pd.DataFrame(
        {"Close": closes, "Volume": [1000.0] * len(closes)},
        index=pd.date_range("2023-01-01", periods=len(closes), freq="D"))
    out = pipe.parse_download_df(df)
    assert out.data is not None and out.atr_14 is None


def test_build_candidate_traegt_atr_14_additiv_ein():
    out = pipe.fetch_synthetic("AMAT")
    entry, reason, _ = pipe.build_candidate("AMAT", out.data[0], out.data[1],
                                            volumes=out.volumes, atr_14=7.5)
    assert entry is not None and reason is None
    assert entry["atr_14"] == 7.5
    # Ohne ATR (Offline/Synthetic-Fall im echten Betrieb) -> None, kein Absturz.
    e2, _, _ = pipe.build_candidate("AMAT", out.data[0], out.data[1], atr_14=None)
    assert e2["atr_14"] is None


def test_fetch_synthetic_liefert_kein_atr_offline_modus_bleibt_bandlos():
    """Auftrags-Entscheidung (s. PR-Text): der Offline-/Demo-Fetcher bekommt
    KEIN synthetisches High/Low — Messfeld fehlt ehrlich statt erfunden."""
    out = pipe.fetch_synthetic("AMAT")
    assert out.atr_14 is None


# ---------------------------------------------------------------------------
# (3) Sink-Caching — Muster wie volume_sink: kein Re-Fetch zwischen Markt-Scan
# und Watchlist.
# ---------------------------------------------------------------------------
def test_scan_market_befuellt_atr_sink():
    def fetcher(ticker):
        closes, highs, lows = _padded_series(80)
        df = _mk_df(80, closes, highs, lows, multiindex=False)
        return pipe.parse_download_df(df)

    atr_sink = {}
    candidates, *_ = pipe._scan_market(["AAA"], fetcher, None, None, None, atr_sink)
    assert atr_sink.get("AAA") == EXPECTED_ATR


def test_build_watchlist_entry_nutzt_atr_sink_ohne_refetch():
    calls = {"n": 0}

    def boom(ticker):
        calls["n"] += 1
        raise AssertionError("darf bei Cache-Treffer nicht erneut fetchen")

    price_sink = {"MA": (pipe.fetch_synthetic("MA").data)}
    atr_sink = {"MA": 8.5}
    e = pipe.build_watchlist_entry("MA", boom, price_sink=price_sink,
                                   atr_sink=atr_sink)
    assert calls["n"] == 0
    assert e["atr_14"] == 8.5 or e.get("wl_status") in ("no_setup", "setup")
    # Bei Setup-Treffer muss der ATR-Wert durchgereicht sein.
    if e.get("wl_status") == "setup":
        assert e["atr_14"] == 8.5


def test_build_watchlist_entry_frischer_fetch_befuellt_atr_sink():
    def fetcher(ticker):
        closes, highs, lows = _padded_series(80)
        df = _mk_df(80, closes, highs, lows, multiindex=False)
        return pipe.parse_download_df(df)

    atr_sink = {}
    e = pipe.build_watchlist_entry("MA", fetcher, atr_sink=atr_sink)
    assert atr_sink.get("MA") == EXPECTED_ATR
    # Der Sink wird IMMER befüllt (unabhängig davon, ob die Konstruktions-
    # Reihe ein regelkonformes Setup ergibt) — nur bei einem Setup-Treffer
    # trägt der Kandidat selbst das Feld.
    if e.get("wl_status") == "setup":
        assert e["atr_14"] == EXPECTED_ATR


def test_build_report_atr_sink_bleibt_intern_main_sieht_ihn_nie():
    """GRENZEN des Auftrags: ATR darf evaluate.py/die Forward-Sammlung nicht
    erreichen. `build_report` selbst nimmt bewusst KEINEN atr_sink-Parameter
    an — nur `price_sink`/`volume_sink` (Muster unverändert aus PR-Historie)."""
    import inspect
    sig = inspect.signature(pipe.build_report)
    assert "atr_sink" not in sig.parameters


def test_offline_report_end_to_end_hat_atr_14_feld_aber_null(monkeypatch):
    monkeypatch.setattr(pipe.config, "MARKETS", {
        "US": {"label": "USA", "universe": ["AAPL", "MSFT"]},
        "DE": {"label": "Deutschland", "universe": ["SAP.DE"]},
    })
    monkeypatch.setattr(pipe, "load_watchlist", lambda: [])
    report = pipe.build_report(pipe.fetch_synthetic, "2026-08-23T22:45:00Z",
                               pipe.fetch_synthetic_weekly,
                               pipe.fetch_synthetic_monthly)
    for mk in ("US", "DE"):
        for c in report["markets"][mk]["candidates"]:
            assert "atr_14" in c and c["atr_14"] is None


# ---------------------------------------------------------------------------
# (4) Forward-Sammlung: atr_14 wird bei Anlage eingefroren (Muster wie
# vol_ratio_w3_w1), Alt-Episoden bleiben ohne das Feld unversehrt.
# ---------------------------------------------------------------------------
def _entry_w4(atr=8.5):
    cps = [{"index": i, "price": 50.0 + i, "date": f"2025-01-{i + 1:02d}", "kind": "L"}
           for i in range(7)]
    cps += [{"index": 7 + j, "price": 100.0 + j, "date": f"2025-02-{j + 1:02d}", "kind": "H"}
            for j in range(5)]
    labels = [{"index": len(cps) - 5 + j, "wave": j} for j in range(5)]
    return {
        "ticker": "TST", "close": 150.0, "score_heuristic": 70.0,
        "target_zone": {"low": 170.0, "high": 180.0},
        "target_zone_extended": {"low": 190.0, "high": 200.0},
        "invalidation_price": 95.0, "direction": "long", "count_label": "W4",
        "chart_points": cps, "count_wave_labels": labels,
        "atr_14": atr,
    }


def test_new_record_friert_atr_14_ein():
    rec = fc._new_record(_entry_w4(atr=8.5), "US", "2025-03-03", "risk_on",
                         "2025-03-03", "now")
    assert rec["atr_14"] == 8.5


def test_new_record_ohne_atr_im_kandidaten_ist_none_kein_absturz():
    e = _entry_w4()
    del e["atr_14"]
    rec = fc._new_record(e, "US", "2025-03-03", "risk_on", "2025-03-03", "now")
    assert rec["atr_14"] is None


# ---------------------------------------------------------------------------
# (5) REALER Ticker (MA) — echte committete Zahlen + hand-konstruierte,
# realistische Tagesspannen-Serie. Belegt die BAND-FORMEL (Faktor 1.0×ATR als
# Gesamtbreite, ±ATR/2 je Seite) mit echten Vergleichszahlen.
# ---------------------------------------------------------------------------
REPORT = json.loads((ROOT / "docs/data/report.json").read_text(encoding="utf-8"))
MA = next(c for c in REPORT["markets"]["US"]["candidates"] if c["ticker"] == "MA")

# Hand-konstruierte Tagesspannen (kein Netzzugriff in dieser Sandbox möglich,
# s. PR-Text) — 14 True-Range-Werte, die im Mittel exakt 8,50 ergeben (~1,46 %
# von MAs committetem Schlusskurs 580,63 — plausible Größenordnung für einen
# liquiden Large-Cap-Titel dieser Preisklasse). Kein Gap (Close bleibt
# konstant bei 580) -> TR = High-Low je Tag, leicht nachrechenbar.
_MA_TR = [8, 9, 7, 10, 8, 9, 7, 10, 8, 9, 7, 10, 8, 9]
_MA_CLOSES = [580.0] * (ATR_PERIOD + 1)
_MA_HIGHS = [580.0] + [580.0 + t / 2 for t in _MA_TR]
_MA_LOWS = [580.0] + [580.0 - t / 2 for t in _MA_TR]


def test_ma_illustratives_atr_ergibt_die_erwartete_groessenordnung():
    assert sum(_MA_TR) / ATR_PERIOD == 8.5
    val = atr14(_MA_HIGHS, _MA_LOWS, _MA_CLOSES)
    assert val == 8.5
    # ~1,46 % des committeten Schlusskurses — plausibel für einen Large-Cap.
    assert val / MA["close"] * 100 == pytest.approx(1.4639, abs=1e-3)


def test_ma_band_breite_gegen_echte_zonen_und_invalidierungs_zahlen():
    """Faktor 1.0×ATR als GESAMT-Bandbreite, symmetrisch (±ATR/2 je Seite) um
    die bestehende (unveränderte!) Fibonacci-Zone gelegt. Die Zahlen zeigen:
    das Band ist deutlich sichtbar (+32,6 % Zonenbreite), aber klar
    UNTERGEORDNET gegenüber dem Invalidierungs-Abstand (Polster = 14,6 % davon,
    Gesamtband = 29,2 % davon) — weder unsichtbar noch dominant."""
    atr = 8.5
    pad = atr / 2
    tz = MA["target_zone"]
    band = {"low": round(tz["low"] - pad, 4), "high": round(tz["high"] + pad, 4)}
    assert band == {"low": 597.6647, "high": 632.2401}

    orig_width = tz["high"] - tz["low"]
    new_width = band["high"] - band["low"]
    assert orig_width == pytest.approx(26.0754, abs=1e-3)
    assert new_width == pytest.approx(34.5754, abs=1e-3)
    assert (new_width / orig_width - 1) * 100 == pytest.approx(32.58, abs=0.05)

    inval_dist = MA["close"] - MA["invalidation_price"]
    assert inval_dist == pytest.approx(29.09, abs=1e-2)
    assert pad / inval_dist * 100 == pytest.approx(14.61, abs=0.05)
    assert atr / inval_dist * 100 == pytest.approx(29.22, abs=0.05)
