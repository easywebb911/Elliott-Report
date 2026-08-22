"""Umbenennung „Zielzone"/„Kursziel" -> „Beobachtungszone" (22.08.2026).

AUFTRAG (reine Anzeige-Änderung, siehe docs/validation_registry.md,
Eintrag 22.08.2026): Fibonacci-Retracement-/Extension-Level zeigen in rigoros
getesteten Studien (Batchelor & Ramyar 2006; Tsinaslanidis, Guijarro &
Voukelatos 2022) keine über den Zufall hinausgehende Trefferquote. Die alte
Bezeichnung „Zielzone"/„Kursziel" suggerierte mehr Vorhersagekraft, als die
Evidenzlage hergibt. Score, Ranking, die Fibonacci-Berechnung selbst
(`target_zone`-Werte/-Ratios) und der `target_exceeded`-Filter sind davon
NICHT betroffen — nur die Beschriftung.

ZWEI NETZE (Muster aus test_waehrungssymbole.py):
  (a) Negativ-Test — „Zielzone"/„Kursziel"/„Zielniveau" kommt an KEINER Stelle
      des gerenderten Frontends mehr vor. `docs/index.html` hat keinen
      separaten Build-Schritt — die Datei IST der Auslieferungsstand, ein
      Grep über die volle Datei entspricht daher dem „gebauten Frontend-
      Output".
  (b) Positiv-Anker — die neue Beschriftung UND der Beleg-Hinweis
      (`FIB_EVIDENZ`) stehen an den dokumentierten Stellen, und der
      Live-Update-Pfad (quotePatch -> _setZoneBadge/_setTfHint) zeigt exakt
      denselben Text wie der initiale Render-Pfad (card()/tfPanel()) — sonst
      würde der erste Live-Tick nach dem Laden einen ANDEREN Text zeigen als
      der Report-Stand.

Bewusst NICHT geprüft (kein Fibonacci-Bezug, s. Registry-Eintrag 22.08.2026):
„A-Ziel-Region" (rohes W4-Extrem, keine Fibonacci-Ratio), „Tap-Ziel"/
„Poller-Ziele" (UI-/Tech-Jargon).
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "docs/index.html").read_text(encoding="utf-8")
REGISTRY = (ROOT / "docs/validation_registry.md").read_text(encoding="utf-8")


def _fn(name: str, tiefe: str = "    ") -> str:
    """Extrahiert EINE Funktion aus der Karten-Quelle (Muster aus
    test_waehrungssymbole.py). Direkter Funktionsvergleich statt globalem
    String-Count — ein globaler Count kann durch einen zufällig gleichen
    String an unabhängiger Stelle (z. B. das RLABEL-Skip-Grund-Label) einen
    tatsächlichen Textbruch zwischen zwei Code-Pfaden verdecken."""
    marke = f"{tiefe}function {name}("
    start = HTML.index(marke)
    return HTML[start:HTML.index(f"\n{tiefe}}}", start) + len(f"\n{tiefe}}}")]


# ---------------------------------------------------------------------------
# (a) Negativ-Test — die alte Bezeichnung ist vollständig verschwunden
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("verboten", ["Zielzone", "Kursziel", "Zielniveau"])
def test_alte_bezeichnung_kommt_im_frontend_nicht_mehr_vor(verboten):
    meldung = (
        verboten + " steht noch in docs/index.html — Fibonacci-Zonen heissen "
        "seit dem 22.08.2026 durchgaengig Beobachtungszone."
    )
    assert verboten not in HTML, meldung


@pytest.mark.parametrize("verboten", [
    "'Ziel ✓'",             # episodeStatus() — alter Erfolgs-Status
    "'Ziel erreicht'",       # alter Zeitebenen-Hinweis (Karte + Live-Update)
    "'Ziel überschritten'",  # dito
    "amb-k\">Ziel<",         # Ambiguitäts-Block, Alternativ-Zone
    "wl-hist-k\">Ziel<",     # Watchlist-Top-5-Historie
    "pair('Ziel',",          # Zeitebenen-Panel (tfPanel)
])
def test_alte_kompakt_beschriftung_ziel_kommt_nicht_mehr_vor(verboten):
    assert verboten not in HTML, verboten


def test_registry_aktuelle_abschnitte_frei_von_zielzone():
    """Nur die AKTUELL gültigen Definitionsabschnitte sind Teil des Auftrags —
    die datierten Einträge im „Änderungs-Log der Population" (23.07.-
    08.08.2026) behalten bewusst ihren damaligen Wortlaut (Verlaufsprotokoll,
    kein lebendes Glossar; siehe Registry-Eintrag 22.08.2026 für die
    Begründung dieser Grenze)."""
    aktueller_teil = REGISTRY.split("## Änderungs-Log der Population")[0]
    assert "Zielzone" not in aktueller_teil
    assert "Kursziel" not in aktueller_teil


def test_registry_historie_bewusst_unangetastet():
    """Gegenprobe zum Test oben: die Historie VOR diesem Auftrag enthielt
    „Zielzone" — bleibt sie das nicht mehr, wurde versehentlich doch die
    Vergangenheit umgeschrieben statt nur die aktuellen Abschnitte."""
    historie = REGISTRY.split("## Änderungs-Log der Population")[1]
    assert "Zielzone" in historie


# ---------------------------------------------------------------------------
# (b) Positiv-Anker — neue Beschriftung + Beleg-Hinweis an den Kernstellen
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("anker", [
    # Haupt-Karte: Metrik-Box-Label + Zonen-Badge (Anfangs-Render).
    '<span class="m-lbl" title="${FIB_EVIDENZ}">Beobachtungszone</span>',
    "'Beobachtungszone überschritten'",
    "'Beobachtungszone erreicht'",
    # Zeitebenen-Panel (tfPanel): kompaktes Label + Hinweis.
    "pair('Zone', zoneStr(c.target_zone),",
    "'Zone überschritten'",
    "'Zone erreicht'",
    # Großer Grad (higher_degree) — Zielzone UND Extension mit Beleg-Hinweis.
    '<span class="hd-k" title="${FIB_EVIDENZ}">Beobachtungszone</span>',
    # Extension: seit 23.08.2026 (Beleglage-Auftrag) EIGENER Beleg-Hinweis
    # (FIB_EVIDENZ_EXT) + `evidence-weak`-Klasse — die im PR #96 dieses
    # Kommentars noch angekündigte "keine visuelle Sonderbehandlung" war
    # ausdrücklich als späterer, separater Auftrag vorgesehen; das ist er.
    '<span class="hd-k" title="${FIB_EVIDENZ_EXT}">Extension</span>',
    '<span class="ext-lbl" title="${FIB_EVIDENZ_EXT}">Extension</span>',
    # Konfluenz-Chip, Episode-Detail, Chart-Legende, Trade-Journal.
    "row(conf.target, 'Beobachtungszone')",
    '<span class="k">Beobachtungszone</span>',
    "Beobachtungszone</span>",
    "· Beobachtungszone ${zone}",
    # Lauf-Status (Skip-Grund-Label).
    "target_exceeded: 'Beobachtungszone erreicht',",
    # episodeStatus(): neuer Erfolgs-Status.
    "label: 'Zone ✓', cls: 'st-target'",
])
def test_neue_beschriftung_an_kernstellen_vorhanden(anker):
    assert anker in HTML, anker


def test_fib_evidenz_konstante_existiert_und_zitiert_beide_quellen():
    assert "const FIB_EVIDENZ =" in HTML
    assert "Batchelor" in HTML and "Ramyar" in HTML and "2006" in HTML
    assert "Tsinaslanidis" in HTML and "2022" in HTML


def test_methodik_legende_erklaert_beobachtungszone_mit_beleg():
    assert "['Beobachtungszone', 'Fibonacci-basierte Beobachtungsmarke" in HTML
    assert "Beleg-Hinweis" in HTML


def test_live_update_pfad_zeigt_denselben_text_wie_initial_render():
    """quotePatch() -> _setZoneBadge/_setTfHint MUSS exakt dieselben Strings
    wie card()/tfPanel() verwenden — sonst zeigt der erste Live-Tick nach dem
    Laden einen anderen Text als der Report-Stand (stiller Beschriftungs-
    Bruch, schwer zu bemerken, weil er nur bei Kursbewegung sichtbar wird).
    Direkter Funktionsvergleich (nicht nur ein globaler String-Count, der
    durch das gleichlautende RLABEL-Skip-Grund-Label falsch grün werden
    könnte)."""
    card_body = _fn("card")
    badge_body = _fn("_setZoneBadge")
    for text in ("Beobachtungszone überschritten", "Beobachtungszone erreicht"):
        assert f"'{text}'" in card_body, f"fehlt im initialen Render (card()): {text}"
        assert f"'{text}'" in badge_body, f"fehlt im Live-Update (_setZoneBadge): {text}"

    tf_body = _fn("tfPanel")
    hint_body = _fn("_setTfHint")
    for text in ("Zone überschritten", "Zone erreicht"):
        assert f"'{text}'" in tf_body, f"fehlt im initialen Render (tfPanel()): {text}"
        assert f"'{text}'" in hint_body, f"fehlt im Live-Update (_setTfHint): {text}"


# ---------------------------------------------------------------------------
# GRENZEN: interne Feldnamen/Skip-Codes bleiben unangetastet — nur die
# Beschriftung des ERGEBNISSES ändert sich, nicht der Wert oder die
# Berechnung dahinter.
# ---------------------------------------------------------------------------
def test_interne_feldnamen_und_skip_code_unveraendert():
    assert "c.target_zone" in HTML
    assert "target_exceeded" in HTML
    assert "class=\"zone-badge" in HTML   # CSS-Klassenname bleibt intern
    assert "class=\"tf-hint" in HTML      # dito


@pytest.mark.parametrize("nicht_fib_bezogen", [
    "A-Ziel-Region",   # rohes W4-Extrem, keine Fibonacci-Ratio (tfPanel)
    "Tap-Ziel",        # UI-Tap-Target, kein Kurswert
    "Poller-Ziele",    # JS-Intervall-Handles, kein Kurswert
])
def test_nicht_fibonacci_bezogene_stellen_bewusst_unangetastet(nicht_fib_bezogen):
    """Gegenprobe: diese drei Stellen enthalten das Wort „Ziel", sind aber
    NICHT Fibonacci-bezogen (Registry-Eintrag 22.08.2026 begründet das im
    Detail) — verschwänden sie, wäre das ein stiller, unbeauftragter Umbau."""
    assert nicht_fib_bezogen in HTML
