"""Recalculate-Button: Sitzungs-Vorab-Prüfung im Frontend (Bau-Auftrag nach
Diagnose 14./15.09.2026).

ANLASS: Der Recalculate-Button löste einen `workflow_dispatch` von
daily.yml aus, OHNE zu wissen, dass das Backend-Gate (#125) diesen Dispatch
während einer laufenden US/DE-Börsensitzung ohnehin ablehnt — der Nutzer
sah erst nachträglich eine "Elliott-Lauf fehlgeschlagen"-Push-Meldung
(real erlebt am 14.09.2026, Runs 34875514566/34879024450).

GEBAUT: `imSitzungsfenster()`/`_sitzungBlockierteMaerkte()` in
docs/index.html — ein 1:1-Spiegel von
`scripts/in_session.py::im_sitzungsfenster()` (Öffnungszeiten/Zeitzonen
identisch, exklusive Grenzen, KEIN Handelstag-Check — genau wie das
Backend-Gate selbst, s. Kommentar dort). `triggerRecalc()` prüft das VOR
`_ensureToken(dispatchRecalc)` — bei Blockade wird `dispatchRecalc()`
(und damit der eigentliche `fetch(...)`-Aufruf gegen die GitHub-API) gar
nicht erst aufgerufen.

ZWEI NETZE:
  (a) Wert-Test der echten, extrahierten `imSitzungsfenster()`/
      `_sitzungBlockierteMaerkte()`-Funktionen gegen die ECHTEN Diagnose-
      Zeitpunkte (per Node.js ausgeführt, kein Nachbau) — UND ein direkter
      Abgleich gegen `scripts/in_session.py::im_sitzungsfenster()` (echte
      Python-Ausführung) für dieselben Zeitpunkte, um Frontend/Backend-
      Übereinstimmung nicht nur zu behaupten.
  (b) Struktureller Test: `triggerRecalc()` ruft bei Blockade nachweislich
      `_ensureToken`/`dispatchRecalc` NICHT auf (Aufruf-Zähler in der
      Simulation, nicht nur Text-Präsenz).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
HTML = (ROOT / "docs/index.html").read_text(encoding="utf-8")

import in_session as ins  # noqa: E402 — echtes Backend, für den Abgleich

NODE = shutil.which("node") or shutil.which("nodejs")
pytestmark = pytest.mark.skipif(NODE is None, reason="node nicht verfügbar")


def _fn(name: str, tiefe: str = "    ") -> str:
    """Extrahiert EINE Funktion (Muster aus test_live_ueberholt.py)."""
    marke = f"{tiefe}function {name}("
    start = HTML.index(marke)
    return HTML[start:HTML.index(f"\n{tiefe}}}", start) + len(f"\n{tiefe}}}")]


def _sitzungsfenster_block() -> str:
    """Konstanten + alle drei Funktionen als EIN zusammenhängender Block —
    dieselbe Reihenfolge/derselbe Text wie in docs/index.html, keine Kopie."""
    start = HTML.index("const SITZUNG_OEFFNUNG_LOKAL")
    ende = HTML.index("\n    }\n", HTML.index("function _sitzungBlockierteMaerkte(")) + len("\n    }\n")
    block = HTML[start:ende]
    for marke in ("const SITZUNG_SCHLUSS_LOKAL", "const SITZUNG_TZ",
                 "function _lokaleSekundenSeitMitternacht(",
                 "function imSitzungsfenster(", "function _sitzungBlockierteMaerkte("):
        assert marke in block, f"Block unvollständig — '{marke}' fehlt"
    return block


BLOCK = _sitzungsfenster_block()


def _js(script: str):
    r = subprocess.run([NODE, "-e", BLOCK + "\n" + script],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# ---------------------------------------------------------------------------
# (a) Wert-Test — echte Diagnose-Zeitpunkte, gegen das echte Backend geprüft
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("iso_utc,erwartet_blockiert,quelle", [
    ("2026-09-14T17:34:06Z", ["US"],
     "echter Backend-Block, Run 34875514566 (Original-Dispatch)"),
    ("2026-09-14T17:34:44Z", ["US"],
     "echter Backend-Block, Run 34875586167 (Auto-Retry Nr. 1)"),
    ("2026-09-14T18:09:04Z", ["US"],
     "echter Backend-Block, Run 34879024450 (zweiter Hand-Dispatch)"),
    ("2026-09-15T00:53:57Z", [],
     "echter erfolgreicher Lauf, Run 34915062450 (Abend-Cron)"),
])
def test_frontend_erkennt_dieselben_faelle_wie_das_echte_backend(
        iso_utc, erwartet_blockiert, quelle):
    """Wert-Test UND Frontend/Backend-Abgleich in einem: für jeden echten
    Diagnose-Zeitpunkt muss die neue JS-Funktion GENAU dasselbe Ergebnis
    liefern wie scripts/in_session.py::im_sitzungsfenster() selbst."""
    js_ergebnis = _js(
        f"console.log(JSON.stringify(_sitzungBlockierteMaerkte(new Date('{iso_utc}'))));"
    )
    assert sorted(js_ergebnis) == sorted(erwartet_blockiert), (
        f"{iso_utc} ({quelle}): JS meldet {js_ergebnis}, erwartet {erwartet_blockiert}")

    # Direkter Abgleich gegen die ECHTE Backend-Funktion — kein Vertrauen
    # auf einen von Hand gepflegten Sollwert allein.
    for markt in ("US", "DE"):
        backend = ins.im_sitzungsfenster(markt, iso_utc)
        js_markt_blockiert = markt in js_ergebnis
        assert bool(backend) == js_markt_blockiert, (
            f"{iso_utc} {markt}: Backend liefert {backend}, "
            f"Frontend-Block-Status ist {js_markt_blockiert} — Inkonsistenz!")


def test_de_sitzung_wird_ebenfalls_erkannt():
    """Eigener Wert-Test für DE (die Diagnose-Zeitpunkte waren alle
    US-lastig) — Xetra-Sitzung 09:00–17:30 Europe/Berlin, hier 12:00 CEST
    an einem beliebigen Werktag im Sommer (10:00 UTC)."""
    js_ergebnis = _js(
        "console.log(JSON.stringify(_sitzungBlockierteMaerkte(new Date('2026-07-15T10:00:00Z'))));"
    )
    assert "DE" in js_ergebnis
    assert ins.im_sitzungsfenster("DE", "2026-07-15T10:00:00Z") is True


# ---------------------------------------------------------------------------
# Exakte Grenze — exklusiv, wie im_sitzungsfenster() selbst (Guardian-Fund,
# 15.09.2026: eine Mutationsprobe `<`/`<=` überlebte alle bisherigen Tests
# unbemerkt, weil keiner exakt auf der Sekundengrenze prüfte)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("iso_utc,markt,bezeichnung", [
    ("2026-07-15T13:30:00Z", "US", "US Eröffnung 09:30:00.000 EDT, exakt"),
    ("2026-07-15T20:00:00Z", "US", "US Schluss 16:00:00.000 EDT, exakt"),
    ("2026-07-15T07:00:00Z", "DE", "DE Eröffnung 09:00:00.000 CEST, exakt"),
    ("2026-07-15T15:30:00Z", "DE", "DE Schluss 17:30:00.000 CEST, exakt"),
])
def test_exakte_grenze_ist_exklusiv_nicht_blockiert(iso_utc, markt, bezeichnung):
    """Genau AUF der Öffnungs-/Schlussgrenze gilt die Sitzung als NICHT
    laufend (exklusive Grenzen, s. Docstring in_session.py:
    „GRENZEN laut Auftrag: exklusiv Eröffnung, exklusiv Schluss"). Gegen
    das echte Backend abgeglichen, nicht nur behauptet."""
    backend = ins.im_sitzungsfenster(markt, iso_utc)
    assert backend is False, f"{bezeichnung}: Backend selbst liefert {backend}, erwartet False"
    js_ergebnis = _js(
        f"console.log(JSON.stringify(_sitzungBlockierteMaerkte(new Date('{iso_utc}'))));"
    )
    assert markt not in js_ergebnis, f"{bezeichnung}: Frontend blockiert {markt}, Backend nicht — Inkonsistenz!"


@pytest.mark.parametrize("iso_utc,markt,bezeichnung", [
    ("2026-07-15T13:30:01Z", "US", "US eine Sekunde nach Eröffnung"),
    ("2026-07-15T19:59:59Z", "US", "US eine Sekunde vor Schluss"),
    ("2026-07-15T07:00:01Z", "DE", "DE eine Sekunde nach Eröffnung"),
    ("2026-07-15T15:29:59Z", "DE", "DE eine Sekunde vor Schluss"),
])
def test_eine_sekunde_innerhalb_der_grenze_ist_blockiert(iso_utc, markt, bezeichnung):
    """Gegenprobe zur exakten Grenze: eine Sekunde INNERHALB des Fensters
    muss blockieren — bestätigt, dass die Grenzen wirklich eng (exklusiv,
    nicht zufällig viel großzügiger) gezogen sind."""
    backend = ins.im_sitzungsfenster(markt, iso_utc)
    assert backend is True, f"{bezeichnung}: Backend selbst liefert {backend}, erwartet True"
    js_ergebnis = _js(
        f"console.log(JSON.stringify(_sitzungBlockierteMaerkte(new Date('{iso_utc}'))));"
    )
    assert markt in js_ergebnis, f"{bezeichnung}: Frontend blockiert NICHT, Backend schon — Inkonsistenz!"


# ---------------------------------------------------------------------------
# Regression: außerhalb jeder Sitzung bleibt das Verhalten unverändert
# ---------------------------------------------------------------------------
def test_ausserhalb_der_sitzung_keine_blockade():
    js_ergebnis = _js(
        "console.log(JSON.stringify(_sitzungBlockierteMaerkte(new Date('2026-09-15T00:53:57Z'))));"
    )
    assert js_ergebnis == []


# ---------------------------------------------------------------------------
# Kein Handelstag-Check — bewusst dieselbe (überkonservative) Eigenschaft
# wie das Backend-Gate, keine mildere Variante
# ---------------------------------------------------------------------------
def test_wochenende_im_uhrzeitfenster_wird_ebenfalls_blockiert():
    """2026-07-25 war ein Samstag (belegt in scripts/in_session.py:
    ADS.DE @ 2026-07-25T13:35:26Z, 15:35 CEST) — Uhrzeit liegt im
    Xetra-Fenster, obwohl kein Handelstag. Das Backend-Gate prüft laut
    eigenem Docstring NUR die Uhrzeit — die Frontend-Prüfung muss densel-
    ben (überkonservativen) Fall zeigen, keine 'schlauere', abweichende
    Milderung (GRENZEN dieses Auftrags)."""
    iso = "2026-07-25T13:35:26Z"
    js_ergebnis = _js(f"console.log(JSON.stringify(_sitzungBlockierteMaerkte(new Date('{iso}'))));")
    assert "DE" in js_ergebnis
    assert ins.im_sitzungsfenster("DE", iso) is True


# ---------------------------------------------------------------------------
# (b) Struktureller Test: bei Blockade wird NACHWEISLICH kein Dispatch
# ausgelöst — Simulation von triggerRecalc() mit Aufruf-Zählern
# ---------------------------------------------------------------------------
def _trigger_recalc_quelle() -> str:
    marke = "    function triggerRecalc() {"
    start = HTML.index(marke)
    return HTML[start:HTML.index("\n    }\n", start) + len("\n    }\n")]


def _simuliere_trigger(iso_utc: str) -> dict:
    script = f"""
    let _ensureTokenAufrufe = 0;
    let _bannerAufrufe = [];
    function _ensureToken(fn) {{ _ensureTokenAufrufe++; }}
    function dispatchRecalc(token) {{ throw new Error('darf hier nie aufgerufen werden'); }}
    function closeMenu() {{}}
    function _rcBanner(state, html) {{ _bannerAufrufe.push({{state, html}}); }}
    const __ECHTE_ZEIT_MS = globalThis.Date.parse('{iso_utc}');
    class Date extends globalThis.Date {{
      constructor(...args) {{
        if (args.length === 0) {{ super(__ECHTE_ZEIT_MS); }}
        else {{ super(...args); }}
      }}
    }}
    {_trigger_recalc_quelle()}
    triggerRecalc();
    console.log(JSON.stringify({{ensureTokenAufrufe: _ensureTokenAufrufe, banner: _bannerAufrufe}}));
    """
    r = subprocess.run([NODE, "-e", BLOCK + "\n" + script],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_blockierter_zeitpunkt_ruft_ensuretoken_nicht_auf():
    """Struktureller Beweis: bei einer laufenden Sitzung wird NICHT nur die
    Anzeige geändert, sondern der Dispatch-Pfad selbst (_ensureToken ->
    dispatchRecalc -> fetch) nie erreicht."""
    r = _simuliere_trigger("2026-09-14T17:34:06Z")
    assert r["ensureTokenAufrufe"] == 0, "Dispatch-Pfad wurde trotz Sitzung angestoßen!"
    assert len(r["banner"]) == 1
    assert r["banner"][0]["state"] == "rc-timeout"
    text = r["banner"][0]["html"]
    assert "Handelssitzung" in text
    assert "Mittagslauf" in text and "12:00 UTC" in text
    assert "Abendlauf" in text and "22:45 UTC" in text
    # GRENZEN: kein Fehler-Framing, kein Warnsymbol.
    assert "⚠" not in text
    assert "fehlgeschlagen" not in text.lower()
    assert "Fehler" not in text


def test_freier_zeitpunkt_ruft_ensuretoken_normal_auf():
    """Regression: außerhalb der Sitzung bleibt der bisherige Ablauf exakt
    erhalten — _ensureToken wird wie vor diesem Auftrag aufgerufen."""
    r = _simuliere_trigger("2026-09-15T00:53:57Z")
    assert r["ensureTokenAufrufe"] == 1
    assert r["banner"] == []


# ---------------------------------------------------------------------------
# Determinismus / Isolierbarkeit
# ---------------------------------------------------------------------------
def test_keine_netzwerkabhaengigkeit_in_der_sitzungsfenster_berechnung():
    for verboten in ("fetch(", "XMLHttpRequest", "await "):
        assert verboten not in BLOCK, (
            f"'{verboten}' in der Sitzungsfenster-Berechnung — "
            "sie darf nur von der aktuellen Uhrzeit abhängen, kein Netz")


def test_kein_handelstag_import_in_den_neuen_funktionen():
    """Explizite Gegenprobe zur GRENZEN-Vorgabe: kein `_isTradingDay`/
    `MARKET_FULL_CLOSURE`-Bezug in den neuen Funktionen — reine Uhrzeit,
    wie das Backend-Gate selbst."""
    assert "_isTradingDay" not in BLOCK
    assert "MARKET_FULL_CLOSURE" not in BLOCK
