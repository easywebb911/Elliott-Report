"""Intraday-MFE/MAE (mfe_high_10d/mae_low_10d) — additiv, ab 26.09.2026.

Analog zu max_gain_10d/max_drawdown_10d (Close-Basis), aber aus dem
Tages-Hoch/-Tief statt dem Schlusskurs. Betrifft NUR mature_record()/
update_forward_collection() mit optional übergebenen highs/lows — bestehende
Aufrufer (kein highs/lows) bleiben unverändert (s. tests/test_forward_collection.py).

Deckt zusätzlich die historisch bekannte Fehlerklasse ab (Datums-/Index-
Versatz bei parallel gefilterten Reihen, s. mature_record()-Docstring zu
#51): ein nicht-finiter Close MITTEN im Fenster darf die High/Low-Zuordnung
der NACHFOLGENDEN, gültigen Bars nicht verschieben.
"""
import math

import forward_collection as fc


NOW = "2026-07-22T00:00:00Z"
LABEL_W4 = "Impuls 1–5 · Long-Setup am Ende W4 (W5 erwartet)"


def _entry(ticker, close=100.0, score=70.0, tlow=120.0, thigh=130.0,
           elow=140.0, ehigh=150.0, inval=90.0, label=LABEL_W4):
    return {
        "ticker": ticker,
        "close": close,
        "count_label": label,
        "score_heuristic": score,
        "target_zone": {"low": tlow, "high": thigh},
        "target_zone_extended": {"low": elow, "high": ehigh},
        "invalidation_price": inval,
        "direction": "long",
    }


def _series(first_seen, forward_closes, entry_close=100.0):
    dates = [first_seen] + [f"d{i}" for i in range(len(forward_closes))]
    closes = [entry_close] + list(forward_closes)
    return dates, closes


def _new(tlow=120.0, elow=140.0, inval=90.0):
    return fc._new_record(_entry("AAPL", tlow=tlow, elow=elow, inval=inval),
                          "US", "s", "risk_on", "2026-07-22", NOW)


def test_mfe_mae_basic_hand_computed():
    rec = _new()
    dates, closes = _series("s", [102, 105, 108, 112, 116, 121, 123, 124, 125, 125])
    # Entry-Tag-Werte (Position 0) sind irrelevant (mature_record beginnt bei
    # idx+1) -- bewusst als 100.0 belassen, um das nicht zu verschleiern.
    highs = [100.0, 104, 108, 112, 118, 130, 124, 126, 127, 128, 127]
    lows = [100.0, 99, 101, 104, 108, 112, 118, 120, 121, 95, 122]
    fc.mature_record(rec, dates, closes, NOW, highs=highs, lows=lows)
    assert rec["matured"] is True
    assert rec["bars_elapsed"] == 10
    # Hoechstes High ueber die 10 Folgetage: 130 (Tag 5, Index 4).
    assert rec["mfe_high_10d"] == 30.0   # (130-100)/100*100
    # Tiefstes Low ueber die 10 Folgetage: 95 (Tag 9, Index 8).
    assert rec["mae_low_10d"] == -5.0    # (95-100)/100*100
    # Close-basierte Felder bleiben von High/Low unberuehrt (Eingefrorene-
    # Dimensionen-Regel -- KEINE Umdefinition bestehender Felder). Die Reihe
    # steigt durchgehend ueber Entry (100) -> max_drawdown_10d bleibt 0.0.
    assert rec["max_gain_10d"] == 25.0
    assert rec["max_drawdown_10d"] == 0.0


def test_mfe_mae_none_without_hilo_data():
    # Bestehende Aufrufer (kein highs/lows -- z.B. Alt-Quelle ohne High/Low-
    # Spalte) bleiben fail-soft: neue Felder None, alles andere unveraendert.
    rec = _new(inval=90.0)
    dates, closes = _series("s", [102, 105, 108, 112, 116, 121, 123, 124, 125, 125])
    fc.mature_record(rec, dates, closes, NOW)
    assert rec["mfe_high_10d"] is None
    assert rec["mae_low_10d"] is None
    assert rec["max_gain_10d"] == 25.0   # unveraendert vom fehlenden High/Low


def test_mfe_partial_missing_high_excludes_only_that_day():
    # Messfeld-Semantik wie beim Volumen: EIN fehlender High-Wert (None)
    # verwirft nur den betroffenen Tag, nicht den ganzen Bar.
    rec = _new()
    dates, closes = _series("s", [102, 105, 108, 112, 116, 121, 123, 124, 125, 125])
    # Der eigentliche Maximal-Tag (Index 4, High=130) wird auf None gesetzt --
    # das naechsthoechste (128, Index 8) muss greifen.
    highs = [100.0, 104, 108, 112, 118, None, 124, 126, 127, 128, 127]
    fc.mature_record(rec, dates, closes, NOW, highs=highs, lows=None)
    assert rec["bars_elapsed"] == 10     # der Tag bleibt ein gueltiger Bar
    assert rec["mfe_high_10d"] == 28.0   # (128-100)/100*100
    assert rec["mae_low_10d"] is None    # lows komplett fehlend -> fail-soft


def test_mfe_all_highs_missing_value_none_stays_none():
    # Jeder einzelne Tages-Wert None (z.B. Quelle lieferte die Spalte, aber
    # keinen einzigen brauchbaren Wert) -> kein Crash, Feld bleibt None statt
    # eines aus 0 Werten geratenen Ergebnisses.
    rec = _new()
    dates, closes = _series("s", [102, 105, 108, 112, 116, 121, 123, 124, 125, 125])
    highs = [None] * 11
    fc.mature_record(rec, dates, closes, NOW, highs=highs, lows=None)
    assert rec["mfe_high_10d"] is None


def test_mfe_alignment_survives_dropped_close_bar_mid_window():
    # Wiederkehrende Fehlerklasse (s. #51, Datums-/Index-Versatz): ein nicht
    # endlicher Close MITTEN im Fenster wird verworfen (kein Bar) -- die
    # High/Low-Zuordnung der NACHFOLGENDEN, gueltigen Bars darf sich dadurch
    # NICHT verschieben.
    #
    # Diskriminierender Aufbau (Mutationsprobe bestaetigt, s. PR-Text): ein
    # Alignment-Bug, der die laufende ANZAHL gueltiger Paare statt der rohen
    # Tages-POSITION indiziert, zeigt sich NICHT zwangslaeufig in max() --
    # ein reiner Off-by-eins-Shift laesst den Sentinel-Wert oft einfach an
    # einem anderen (weiterhin vorhandenen) Tag landen, das Maximum aendert
    # sich dann nicht. Deshalb sitzt der Sentinel hier auf der LETZTEN
    # rohen Position (Index 10) -- ein sequenzieller Index kaeme dort nie an
    # (nur 10 gueltige Paare -> sequenzielle Indizes 0..9), der Sentinel
    # wuerde bei diesem Bug also komplett VERFEHLT, nicht nur verschoben.
    rec = _new()
    # 11 rohe Folgetage, davon 1 nicht-finit (Index 2) -> 10 gueltige Bars,
    # identische GUELTIGE Schlusskursreihe wie test_mfe_mae_basic_hand_computed
    # (nur mit einem zusaetzlichen kaputten Bar dazwischengeschoben).
    dates, closes = _series(
        "s", [102, 105, math.nan, 108, 112, 116, 121, 123, 124, 125, 125])
    # highs BAR-GENAU zur rohen (ungefilterten) closes-Reihe ausgerichtet --
    # genau wie _extract_bars() sie liefert. Der Sentinel 999.0 sitzt auf der
    # LETZTEN rohen Position (Index 10, letzter gueltiger Close=125). Die
    # eigene High des kaputten Bars (50.0, Index 2) darf NIE einfliessen.
    highs = [100.0, 104, 108, 50.0, 112, 118, 121, 124, 126, 127, 128, 999.0]
    fc.mature_record(rec, dates, closes, NOW, highs=highs, lows=None)
    assert rec["bars_elapsed"] == 10
    assert rec["skipped_bars"] == 1
    assert rec["matured"] is True
    assert rec["mfe_high_10d"] == 899.0  # (999.0-100)/100*100 -- Sentinel gefunden
