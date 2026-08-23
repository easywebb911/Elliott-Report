"""Extension-Zone visuell abgeschwächt gegenüber der Retracement-Zone (23.08.2026).

WISSENSCHAFTLICHER ANLASS (bereits recherchiert, s. PR-Text, nicht hier neu
geprüft): Extension-Level (161,8 %/261,8 %) sind die am schwächsten belegte
Teilkomponente der Methode — Batchelor & Ramyar (2006) testeten Extensions/
Projektionen EXPLIZIT und fanden auch dort keinen Unterschied zu zufälligen
Niveaus. Retracement-Level (bereits als „Beobachtungszone" in PR #96
umbenannt) haben dieselbe Kernkritik, aber mehrere unabhängige Studien, die
sie direkt untersucht haben — eine Asymmetrie in der Beleglage, die sich jetzt
auch visuell widerspiegeln soll.

AUFTRAG: NUR visuelle Differenzierung (neue CSS-Klasse `evidence-weak` +
Badge „spekulativ" auf der Hauptkarte + eigener, spezifischerer Beleg-Hinweis
FIB_EVIDENZ_EXT) — keine neue Berechnung, keine neue Zahl, keine
Retracement-Änderung (die bleibt aus PR #96 unverändert, s. Regressionstest
unten).

ZWEI NETZE (Muster aus test_beobachtungszone_umbenennung.py):
  (a) Positiv-Anker — JEDE der vier gefundenen Extension-Anzeigestellen
      (Haupt-Karte, Großer Grad, Zeitebenen-Panel, Episode-Detail) trägt die
      neue Klasse/den neuen Beleg-Hinweis, mit einem expliziten Soll-Wert
      (nicht nur "sieht anders aus").
  (b) Negativ-/Regressions-Anker — die Retracement-Zone („Beobachtungszone")
      trägt an KEINER dieser vier Stellen die neue Klasse, und die aus PR #96
      bestehenden Beobachtungszone-Anker bleiben unverändert grün.

NACHTRAG (23.08.2026, ATR-Band-Auftrag): die `zoneStr(c.target_zone)`/
`zoneStr(c.target_zone_extended)`/`fmtZone(ez, market)`-Aufrufe unten sind auf
`zoneStr(fibBand(c.target_zone, atr))` usw. aktualisiert — das ist die
GEPLANTE Line-zu-Band-Umstellung dieses neuen Auftrags (s. dortiger PR-Text),
keine unbeabsichtigte Änderung. Alles andere in dieser Datei (Klassen-Namen,
Beleg-Hinweise, die Retracement-/Extension-Asymmetrie selbst) bleibt exakt
wie in PR #100.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "docs/index.html").read_text(encoding="utf-8")


def _fn(name: str, tiefe: str = "    ") -> str:
    """Extrahiert EINE Funktion aus der Karten-Quelle (Muster aus
    test_waehrungssymbole.py) — Funktionsvergleich statt globalem
    String-Count, damit ein Treffer in einer ANDEREN Funktion nicht
    fälschlich als "gefunden" durchgeht."""
    marke = f"{tiefe}function {name}("
    start = HTML.index(marke)
    return HTML[start:HTML.index(f"\n{tiefe}}}", start) + len(f"\n{tiefe}}}")]


# ---------------------------------------------------------------------------
# (a) CSS-Grundlage: die neue Klasse existiert mit einem expliziten Soll-Wert
# ---------------------------------------------------------------------------
def test_evidence_weak_klasse_existiert_mit_reduzierter_deckkraft():
    assert ".evidence-weak { opacity:.68; }" in HTML


def test_evidence_badge_klasse_existiert():
    assert ".evidence-badge {" in HTML
    # Gestrichelter Rahmen ("gestrichelt statt durchgezogen" aus dem Auftrag).
    assert "border:1px dashed var(--brd);" in HTML


def test_fib_evidenz_ext_erweitert_die_bestehende_konstante():
    assert "const FIB_EVIDENZ_EXT = FIB_EVIDENZ +" in HTML
    assert "Batchelor & Ramyar (2006) testeten explizit auch " in HTML
    assert "Extensions und fanden auch dort keinen Unterschied zum Zufall." in HTML


# ---------------------------------------------------------------------------
# (a) Positiv-Anker — alle vier gefundenen Extension-Anzeigestellen
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("anker", [
    # 1. Haupt-Karte (card()): Zeile + Badge, neuer Beleg-Hinweis.
    '<div class="ext-zone evidence-weak"><span class="ext-lbl" title="${FIB_EVIDENZ_EXT}">Extension</span>${fmtZone(fibBand(ez, c.atr_14), market)}',
    '<span class="evidence-badge" title="${FIB_EVIDENZ_EXT}">spekulativ</span></div>',
    # 2. Großer Grad (higher_degree-Block): Zeile abgeschwächt.
    '<div class="evidence-weak"><span class="hd-k" title="${FIB_EVIDENZ_EXT}">Extension</span>',
    # 3. Zeitebenen-Panel (tfPanel): der 'Ext'-Pair bekommt die Klasse über
    #    den neuen optionalen `cls`-Parameter von `pair()`.
    "'evidence-weak')",
    # 4. Episode-Detail (showEpisodeDetail): Schlüssel UND Wert abgeschwächt.
    '<span class="k evidence-weak" title="${FIB_EVIDENZ_EXT}">Extension</span><span class="v evidence-weak">${fmt(ez.low)}–${fmt(ez.high)}</span>',
    # Methodik-Legende: der spezifischere Beleg-Hinweis für Extensions.
    'Batchelor &amp; Ramyar (2006) testeten Extensions/Projektionen EXPLIZIT',
])
def test_neue_beleglage_beschriftung_an_allen_fundstellen(anker):
    assert anker in HTML, anker


def test_pair_helper_hat_optionalen_klassen_parameter():
    """`pair()` in tfPanel wird von drei Aufrufern geteilt (Inval/Zone/Ext) —
    der neue 4. Parameter darf die beiden ANDEREN Aufrufer nicht anfassen."""
    koerper = _fn("tfPanel")
    assert "const pair = (kk, vv, dist, cls) =>" in koerper
    assert "pair('Inval', fmtP(c.invalidation_price, market))" in koerper
    assert "pair('Zone', zoneStr(fibBand(c.target_zone, atr))," in koerper
    assert "pair('Ext', zoneStr(fibBand(c.target_zone_extended, atr))," in koerper
    assert "'evidence-weak')" in koerper


# ---------------------------------------------------------------------------
# (b) Negativ-/Regressions-Anker — Retracement bleibt unangetastet
# ---------------------------------------------------------------------------
def test_retracement_beobachtungszone_traegt_nirgends_evidence_weak():
    """GRENZEN: 'Keine erneute Umbenennung der bereits mit #96 fertigen
    Retracement-Bezeichnung' UND keine visuelle Änderung an ihr. Prüft in
    allen vier betroffenen Funktionen einzeln, dass NUR die
    Extension-Stelle die neue Klasse trägt, nicht die Beobachtungszone."""
    card_body = _fn("card")
    assert '<span class="m-lbl" title="${FIB_EVIDENZ}">Beobachtungszone</span>' in card_body
    assert 'evidence-weak">Beobachtungszone' not in card_body
    # Die m-lbl-Zeile selbst (Retracement) bekommt keine evidence-weak-Klasse.
    assert '<div class="metric-box zone">' in card_body, \
        "die Retracement-Metrik-Box bleibt ohne evidence-weak"

    tf_body = _fn("tfPanel")
    assert ("pair('Zone', zoneStr(fibBand(c.target_zone, atr)),\n"
            "                   c.target_zone ? zoneDistSpan(c.target_zone.low, cardClose) : '')"
            ) in tf_body, "der 'Zone'-Aufruf (Retracement) bekommt KEINEN cls-Parameter"

    ep_body = _fn("showEpisodeDetail")
    assert '<span class="k">Beobachtungszone</span>' in ep_body
    assert 'evidence-weak" title="${FIB_EVIDENZ}">Beobachtungszone' not in ep_body


def test_hd_block_beobachtungszone_zeile_ohne_evidence_weak():
    """Im higher_degree-Block trägt NUR die Extension-Zeile die neue Klasse,
    die Beobachtungszone-Zeile direkt darüber bleibt unverändert (kein
    umschließendes `evidence-weak` auf ihrem `<div>`)."""
    start = HTML.index('<div class="hd-rows">')
    ende = HTML.index("</div>\n          ${degreeSpark", start)
    hd_rows = HTML[start:ende]
    assert '<div><span class="hd-k" title="${FIB_EVIDENZ}">Beobachtungszone</span>' in hd_rows
    assert '<div class="evidence-weak"><span class="hd-k" title="${FIB_EVIDENZ_EXT}">Extension</span>' in hd_rows


def test_alte_beobachtungszone_anker_aus_pr96_bleiben_unveraendert():
    """Regressionstest: die #96-Anker für die RETRACEMENT-Zone (Wortlaut
    „Beobachtungszone", Beleg-Hinweis FIB_EVIDENZ ohne _EXT) bleiben grün —
    nur ihr jeweiliges `title`-Attribut auf der Extension-Zeile daneben hat
    sich geändert, nicht ihr eigenes."""
    for anker in (
        '<span class="m-lbl" title="${FIB_EVIDENZ}">Beobachtungszone</span>',
        "'Beobachtungszone überschritten'",
        "'Beobachtungszone erreicht'",
        "pair('Zone', zoneStr(fibBand(c.target_zone, atr)),",
        '<span class="hd-k" title="${FIB_EVIDENZ}">Beobachtungszone</span>',
        '<span class="k">Beobachtungszone</span>',
    ):
        assert anker in HTML, anker


def test_episode_status_extension_treffer_badge_bewusst_unangetastet():
    """`episodeStatus()`s 'Extension ✓✓'-Badge ist ein historischer
    Trefferstatus (ext_hit, Backtesting), keine Anzeige der Zonen-WERTE
    selbst — bewusst außerhalb dieses Auftrags, keine evidence-weak-Klasse
    nötig oder vorhanden."""
    assert "{ label: 'Extension ✓✓', cls: 'st-ext' }" in HTML
    assert "evidence-weak', cls: 'st-ext'" not in HTML


def test_ep_chart_baender_bewusst_unangetastet():
    """Die SVG-Bänder im Episode-Detail-Chart hatten SCHON VOR diesem Auftrag
    eine asymmetrische Deckkraft (Extension 0.07 vs. Retracement 0.15) — das
    ist eine bestehende, unabhängig entstandene Darstellung (Layering, kein
    Beleg-Statement) und bewusst nicht Teil dieses Auftrags (GRENZEN: kein
    Band-statt-Linie-Umbau). Gegenprobe, dass sie unverändert blieb."""
    assert "band(ez.low, ez.high, 'rgba(34,197,94,0.07)')" in HTML
    assert "band(tz.low, tz.high, 'rgba(34,197,94,0.15)')" in HTML
