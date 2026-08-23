"""Frontend: Beobachtungszone/Extension als ATR(14)-Band statt scharfer Linie
(23.08.2026, Bau-Auftrag "Band statt Linie").

WAS SICH ÄNDERT: an den VIER im Auftrag benannten Anzeigestellen (Haupt-Karte
Metrik-Box, Großer-Grad-Block, Zeitebenen-Panel, Episode-Detail-kv-Grid) wird
die angezeigte Zonen-Spanne über `fibBand(zone, atr)` symmetrisch um ±ATR/2
gepolstert (Faktor 1,0×ATR als Gesamt-Bandbreite). Die Fibonacci-Werte selbst
(`zone.low`/`.high`), Score, `target_exceeded` und die Zonen-Abstands-Kante
(`zoneDistSpan`) bleiben UNVERÄNDERT — das ist eine reine Anzeige-Verbreiterung.

BEWUSST UNANGETASTET (Widerspruch gemeldet, nicht umgangen — s. PR-Text):
  - Die SVG-Zonen-Bänder in `drawEpisodeChart` (`tgtBand`/`extBand`) waren
    laut PR #100 schon VORHER Flächen (kein Linie-Problem) und wurden dort
    ausdrücklich als außerhalb des Auftrags markiert
    (`test_ep_chart_baender_bewusst_unangetastet`). Diese Grenze bleibt.
  - `watchlistCard()`s eigener `tfPanel(...)`-Aufruf (kompakte Watchlist-Karte
    OHNE Top-5-Setup) bekommt aus Auftrags-Minimalismus keinen ATR-Parameter —
    diese Fälle carrien in `_wl_no_setup_entry` ohnehin kein `atr_14`-Feld.
  - Der Großer-Grad-Block (Wochen-Grad) nutzt den TÄGLICHEN `c.atr_14` (keine
    eigene Wochen-ATR-Berechnung) — eine bekannte, im PR-Text benannte
    Vereinfachung, kein neuer Netz-/Rechen-Aufwand für dieses Feld.

ZWEI NETZE (Muster aus test_extension_beleglage.py):
  (a) Positiv-Anker — `fibBand` existiert mit der erwarteten Formel, und alle
      vier Aufrufer nutzen es.
  (b) Negativ-/Regressions-Anker — die Zonen-Abstands-Kante (`zoneDistSpan`)
      bleibt an jeder der vier Stellen auf der EXAKTEN (ungepolsterten) Zone,
      und der Chart bleibt unverändert.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "docs/index.html").read_text(encoding="utf-8")


def _fn(name: str, tiefe: str = "    ") -> str:
    marke = f"{tiefe}function {name}("
    start = HTML.index(marke)
    return HTML[start:HTML.index(f"\n{tiefe}}}", start) + len(f"\n{tiefe}}}")]


# ---------------------------------------------------------------------------
# (a) Die Formel selbst
# ---------------------------------------------------------------------------
def test_fibband_existiert_mit_der_erwarteten_formel():
    koerper = _fn("fibBand")
    assert "function fibBand(zone, atr) {" in koerper
    # Fail-soft: ohne Zone ODER ohne endliches ATR unverändert die Original-Zone.
    assert "if (!zone || !Number.isFinite(atr)) return zone;" in koerper
    # Faktor 1,0×ATR als GESAMT-Bandbreite -> ±ATR/2 je Seite.
    assert "const pad = atr / 2;" in koerper
    assert "low: zone.low - pad" in koerper and "high: zone.high + pad" in koerper


# ---------------------------------------------------------------------------
# (a) Positiv-Anker — alle vier Anzeigestellen nutzen fibBand()
# ---------------------------------------------------------------------------
def test_haupt_karte_metrik_box_nutzt_fibband():
    koerper = _fn("card")
    assert "const zone = fmtZone(fibBand(c.target_zone, c.atr_14), market);" in koerper
    assert "${fmtZone(fibBand(ez, c.atr_14), market)}" in koerper


def test_hd_block_nutzt_fibband_mit_dem_taeglichen_atr():
    koerper = _fn("card")
    assert "${zoneStr(fibBand(hd.target_zone, c.atr_14))}" in koerper
    assert "${zoneStr(fibBand(hd.target_zone_extended, c.atr_14))}" in koerper


def test_tfpanel_nutzt_fibband_fuer_zone_und_ext():
    koerper = _fn("tfPanel")
    assert "function tfPanel(tf, structure, cardClose, market, atr) {" in HTML
    assert "pair('Zone', zoneStr(fibBand(c.target_zone, atr))," in koerper
    assert "pair('Ext', zoneStr(fibBand(c.target_zone_extended, atr))," in koerper
    # Aufrufer in card() reicht c.atr_14 als 5. Parameter durch.
    assert "tfPanel(c.timeframes, c.structure, c.close, market, c.atr_14)" in HTML


def test_episode_detail_kv_grid_nutzt_fibband_mit_dem_eingefrorenen_atr():
    koerper = _fn("showEpisodeDetail")
    assert "const tz = fibBand(r.target_zone, r.atr_14) || {};" in koerper
    assert "const ez = fibBand(r.target_zone_extended, r.atr_14) || {};" in koerper


def test_methodik_legende_erklaert_die_band_breite():
    assert "['Band-Breite (ATR)'," in HTML
    assert "±ATR(14)/2" in HTML


# ---------------------------------------------------------------------------
# (b) Negativ-/Regressions-Anker
# ---------------------------------------------------------------------------
def test_zonen_abstand_bleibt_an_allen_vier_stellen_auf_der_exakten_kante():
    """GRENZEN: 'keine Änderung an Invalidierungs-/Zonen-Abstands-Berechnung
    oder -Anzeige'. `zoneDistSpan` darf NIRGENDS ein `fibBand(...)`-Ergebnis
    bekommen — sonst würde sich lautlos verschieben, ab welchem Kurs eine Zone
    als 'erreicht' gilt (dieselbe Kante wie `target_exceeded`, s. Kommentar im
    Quelltext bei `ZONE_DIST_TITLE`)."""
    card_body = _fn("card")
    assert "zoneDistSpan(c.target_zone.low, c.close)" in card_body
    assert "zoneDistSpan(ez.low, c.close)" in card_body
    assert "zoneDistSpan(fibBand" not in card_body

    tf_body = _fn("tfPanel")
    assert "zoneDistSpan(c.target_zone.low, cardClose)" in tf_body
    assert "zoneDistSpan(c.target_zone_extended.low, cardClose)" in tf_body
    assert "zoneDistSpan(fibBand" not in tf_body


def test_hd_block_zonen_abstand_bleibt_exakt():
    koerper = _fn("card")
    assert "zoneDistSpan(hd.target_zone.low, c.close)" in koerper
    assert "zoneDistSpan(hd.target_zone_extended.low, c.close)" in koerper


def test_drawepisodechart_baender_bewusst_unangetastet():
    """Gegenprobe zur PR-#100-Regression (`test_ep_chart_baender_bewusst_
    unangetastet`): die SVG-Bänder bleiben AUCH nach diesem Auftrag exakt
    unverändert — kein `fibBand(...)` im Chart-Code."""
    koerper = _fn("drawEpisodeChart")
    assert "band(ez.low, ez.high, 'rgba(34,197,94,0.07)')" in koerper
    assert "band(tz.low, tz.high, 'rgba(34,197,94,0.15)')" in koerper
    assert "fibBand" not in koerper


def test_watchlistcard_tfpanel_aufruf_bewusst_ohne_atr_parameter():
    """Auftrags-Minimalismus: die kompakte Watchlist-Karte (kein Top-5-Setup)
    bekommt keinen ATR-Parameter — `_wl_no_setup_entry` trägt ohnehin kein
    `atr_14`-Feld (s. Backend-Tests)."""
    koerper = _fn("watchlistCard")
    assert "tfPanel(c.timeframes, c.structure, c.close, c.market_key)" in koerper
    assert "c.atr_14" not in koerper


def test_fibband_wird_nicht_faelschlich_auf_score_oder_invalidierung_angewendet():
    """Gegenprobe über die GANZE Datei: `fibBand(` taucht NUR an den vier
    Zonen-Stellen auf, nirgends bei Invalidierung/Score."""
    treffer = HTML.count("fibBand(")
    # Definition (1) + 4 Card-/HD-Aufrufe (zone, ez, hd.target_zone,
    # hd.target_zone_extended) + 2 tfPanel-Aufrufe + 2 Episode-Detail-Aufrufe.
    assert treffer == 9, f"unerwartete Anzahl fibBand(...)-Fundstellen: {treffer}"
    assert "fibBand(c.invalidation_price" not in HTML
    assert "fibBand(c.score_heuristic" not in HTML
