"""Chart-Vorschau (23.08.2026, Bau-Auftrag "Kursverlauf + Zonen auf der Karte").

EIN wiederverwendbares Chart-Element (historischer Kursverlauf + Zonen-Bänder
+ 10-Handelstage-Vorschau mit fortgeführten Zonen, KEINE Kursprognose) an
zwei Stellen: Haupt-Card (Tagesgrad, `chart_points`) und "Großer Grad ·
Wochen"-Block (`higher_degree.chart_points`). Standardmäßig eingeklappt,
DASSELBE Auf-/Zuklapp-Muster wie das KI-Kommentar-Feld (`agentBlock`), lazy
gerendert (Performance-Vorgabe: kein SVG vor dem tatsächlichen Aufklappen).

GRENZEN: keine neue Berechnung — die Zonen-Grenzen kommen unverändert über
`fibBand(zone, atr)` (#101), derselbe Aufruf wie an den vier bestehenden
Zahlen-Anzeigestellen. `drawEpisodeChart` selbst bleibt unangetastet (eigene,
neue Funktion `drawZonePreviewChart` statt Extraktion — kein Regressions-
risiko für die bestehende Episode-Detail-Ansicht, s. `test_atr_band_
frontend.py::test_drawepisodechart_baender_bewusst_unangetastet`, das nach
diesem Auftrag weiterhin grün bleibt).

Zwei Netze (Muster aus test_zonen_abstand.py):
  (a) Literale/String-Anker — laufen überall, ohne Zusatz-Abhängigkeit.
  (b) node: die Rechenkerne WIRKLICH ausgeführt, inkl. eines echten
      Beispiel-Tickers (MA, aus `data/report.json`, Lauf 23.08.2026) — die im
      Chart gerenderte Pixel-Geometrie wird auf die Zonen-Zahl zurückgerechnet
      und gegen `fibBand(...)` verglichen (kein Rundungs-/Umrechnungsfehler
      zwischen Zahl und Chart). Fehlt node, greift (a) allein (skip).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "docs/index.html").read_text(encoding="utf-8")


def _fn(name: str, tiefe: str = "    ") -> str:
    marke = f"{tiefe}function {name}("
    start = HTML.index(marke)
    return HTML[start:HTML.index(f"\n{tiefe}}}", start) + len(f"\n{tiefe}}}")]


def _konst(name: str) -> str:
    start = HTML.index(f"    const {name} =")
    return HTML[start:HTML.index(";\n", start) + 1]


# ---------------------------------------------------------------------------
# (a) Literale/String-Anker
# ---------------------------------------------------------------------------
def test_chartpreviewblock_existiert_und_ist_fail_soft():
    koerper = _fn("chartPreviewBlock")
    assert "if (!Array.isArray(pts) || pts.length < 2) return '';" in koerper


def test_chartpreviewblock_nutzt_dasselbe_klapp_muster_wie_ki_kommentar():
    """DASSELBE Muster wie `agentBlock` (KI-Kommentar): <details>/<summary>,
    KEIN `open`-Attribut (Standard eingeklappt)."""
    koerper = _fn("chartPreviewBlock")
    assert '<details class="cp-block">' in koerper
    assert '<summary class="cp-summary">' in koerper
    assert "open" not in koerper.split('<details class="cp-block">')[1].split(">")[0]


def test_beide_einsatzstellen_sind_verdrahtet():
    """Item 1a (Haupt-Card, `c.chart_points`) und 1b (Großer-Grad-Block,
    `hd.chart_points`) — je EIN Aufruf, je mit dem passenden Degree-Label."""
    card_body = _fn("card")
    assert "chartPreviewBlock({ points: c.chart_points, inval: c.invalidation_price,\n" \
           "                               zone: c.target_zone, zoneExt: c.target_zone_extended,\n" \
           "                               atr: c.atr_14 }, 'Tagesgrad')" in card_body
    assert "chartPreviewBlock({ points: hd.chart_points, inval: hd.invalidation_price,\n" \
           "                                 zone: hd.target_zone, zoneExt: hd.target_zone_extended,\n" \
           "                                 atr: c.atr_14 }, 'Wochen')" in card_body


def test_hd_chart_nutzt_denselben_taeglichen_atr_wie_die_hd_zahlen():
    """Konsistenz mit der bestehenden hd-Anzeige (#101): `c.atr_14`, keine
    eigene Wochen-ATR — sonst würden Zahl und Chart im selben Block
    unterschiedliche Bänder zeigen."""
    koerper = _fn("card")
    assert "atr: c.atr_14 }, 'Wochen')" in koerper


def test_drawzonepreviewchart_nutzt_fibband_fuer_beide_zonen():
    koerper = _fn("drawZonePreviewChart")
    assert "const tz = fibBand(o.zone, o.atr) || {};" in koerper
    assert "const ez = fibBand(o.zoneExt, o.atr) || {};" in koerper


def test_drawepisodechart_bleibt_unangetastet():
    """Gegenprobe: `drawEpisodeChart` (bestehende Episode-Detail-Chart-Logik)
    wurde NICHT verändert — keine neue Funktion extrahiert/eingebaut,
    weiterhin exakt die PR-#100-Bänder."""
    koerper = _fn("drawEpisodeChart")
    assert "fibBand" not in koerper
    assert "drawZonePreviewChart" not in koerper
    assert "band(ez.low, ez.high, 'rgba(34,197,94,0.07)')" in koerper
    assert "band(tz.low, tz.high, 'rgba(34,197,94,0.15)')" in koerper


def test_vorschau_horizont_ist_der_bestehende_forward_testing_horizont():
    """Keine neue, willkürliche Zeitspanne — derselbe Wert wie
    `HORIZON_DAYS` in scripts/forward_collection.py."""
    assert "const PREVIEW_HORIZON_DAYS = 10;" in HTML
    py = (ROOT / "scripts/forward_collection.py").read_text(encoding="utf-8")
    assert "HORIZON_DAYS = 10" in py


def test_lazy_rendering_ueber_toggle_event_verdrahtet():
    """Performance-Vorgabe: KEIN Rendern bei jedem Karten-Laden — erst beim
    tatsächlichen Aufklappen, per `toggle`-Event (Capture-Phase, s. Kommentar
    im Quelltext) und mit einem Rendered-Guard (kein Doppel-Rendern)."""
    assert "document.addEventListener('toggle', (ev) => {" in HTML
    stelle = HTML.index("document.addEventListener('toggle', (ev) => {")
    block = HTML[stelle:stelle + 900]
    assert "classList.contains('cp-block')" in block
    assert "!det.open) return;" in block
    assert "el.dataset.rendered" in block
    assert "drawZonePreviewChart(el, payload);" in block
    assert ", true);" in block  # Capture-Phase — `toggle` bubbelt nicht


def test_extension_band_bekommt_gestrichelten_rand_im_chart():
    """#100-Optik ('spekulativ') jetzt auch im Chart, nicht nur beim
    Zahlen-Label: gestrichelter Rand NUR auf dem Extension-Band."""
    koerper = _fn("drawZonePreviewChart")
    assert 'stroke-dasharray="4 3"' in koerper
    assert "extBand = band(ez.low, ez.high, 'rgba(34,197,94,0.07)'," in koerper
    assert "tgtBand = band(tz.low, tz.high, 'rgba(34,197,94,0.15)');" in koerper
    assert "tgtBand = band(tz.low, tz.high, 'rgba(34,197,94,0.15)', " not in koerper  # kein Rand hier


def test_caption_nennt_klar_keine_prognose():
    koerper = _fn("drawZonePreviewChart")
    assert "keine Kursprognose" in koerper


# ---------------------------------------------------------------------------
# (b) node: die Rechenkerne WIRKLICH ausgeführt
# ---------------------------------------------------------------------------
_NODE = shutil.which("node") or shutil.which("nodejs")

# Echter Beispiel-Ticker, Quelle: data/report.json, Lauf 23.08.2026, US-Markt,
# Kandidat "MA" (Mastercard) — alle vier Zonen-/ATR-Felder vorhanden.
_MA = json.loads((ROOT / "data/report.json").read_text(encoding="utf-8"))
_MA_REC = next(
    c for c in _MA["markets"]["US"]["candidates"] if c["ticker"] == "MA"
)


def _js(script: str):
    if not _NODE:
        pytest.skip("kein node vorhanden — die Literal-Tests decken dieselben Fälle")
    quelle = "\n".join([
        _konst("CP_PREVIEW_FRAC"),
        _konst("PREVIEW_HORIZON_DAYS"),
        # CP_CHART_* sind EIN Mehrfach-const (nicht `_konst()`-kompatibel) —
        # eigens extrahiert, damit der Test dieselben Zahlen mitliest statt
        # sie ein zweites Mal zu behaupten.
        HTML[HTML.index("    const CP_CHART_W_MIN ="):
             HTML.index(";\n", HTML.index("    const CP_CHART_W_MIN =")) + 1],
        _fn("fibBand"),
        _fn("drawZonePreviewChart"),
    ])
    r = subprocess.run([_NODE, "-e", quelle + "\n" + script],
                        capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_chart_zonen_grenzen_entsprechen_exakt_fibband_MA_tagesgrad():
    """Der Wert-Test aus dem Auftrag: die im Chart gerenderte Pixel-Geometrie
    der Beobachtungszone/Extension wird auf den Preis zurückgerechnet und
    gegen `fibBand(target_zone, atr_14)` verglichen — derselbe Aufruf, der
    auch die Zahl auf der Karte erzeugt (`m-val`/`zoneStr`)."""
    rec = _MA_REC
    opts = {
        "points": [{"price": p} for p in
                   [pt["price"] for pt in rec["chart_points"]]],
        "inval": rec["invalidation_price"],
        "zone": rec["target_zone"],
        "zoneExt": rec["target_zone_extended"],
        "atr": rec["atr_14"],
    }
    ergebnis = _js(f"""
      const opts = {json.dumps(opts)};
      const el = {{ clientWidth: 340, innerHTML: '' }};
      drawZonePreviewChart(el, opts);
      const svg = el.innerHTML;

      // Dieselbe fibBand-Rechnung wie die Karten-Zahl.
      const tz = fibBand(opts.zone, opts.atr);
      const ez = fibBand(opts.zoneExt, opts.atr);

      // Domäne/yOf UNABHÄNGIG nachgebaut (dieselben Konstanten, dieselbe
      // Logik wie in drawZonePreviewChart) -- damit die Pixel-Rückrechnung
      // eine ECHTE Gegenprobe ist, keine Tautologie.
      const ys = opts.points.map(p => p.price);
      const domain = ys.slice();
      [tz.low, tz.high, ez.low, ez.high, opts.inval].forEach(v => domain.push(v));
      const min = Math.min(...domain), max = Math.max(...domain), span = (max - min) || 1;
      const W = 340, H = CP_CHART_H, PYt = CP_CHART_PYT, PYb = CP_CHART_PYB;
      const yOf = v => H - PYb - ((v - min) / span) * (H - PYt - PYb);
      const priceOfY = y => min + (H - PYb - y) / (H - PYt - PYb) * span;

      // tgtBand-Rect aus dem SVG-String ziehen (erstes rect nach dem
      // extBand-Rect, s. Reihenfolge in drawZonePreviewChart).
      const rectRe = /<rect x="0" y="([\\d.]+)" width="[\\d.]+" height="([\\d.]+)" fill="(rgba\\(34,197,94,0\\.\\d+\\))"/g;
      const rects = [...svg.matchAll(rectRe)];
      const ext = rects.find(m => m[3] === 'rgba(34,197,94,0.07)');
      const tgt = rects.find(m => m[3] === 'rgba(34,197,94,0.15)');

      const tgtHighAusChart = priceOfY(parseFloat(tgt[1]));
      const tgtLowAusChart = priceOfY(parseFloat(tgt[1]) + parseFloat(tgt[2]));
      const extHighAusChart = priceOfY(parseFloat(ext[1]));
      const extLowAusChart = priceOfY(parseFloat(ext[1]) + parseFloat(ext[2]));

      console.log(JSON.stringify({{
        tz, ez,
        tgtHighAusChart, tgtLowAusChart, extHighAusChart, extLowAusChart,
      }}));
    """)
    tol = 0.5  # ein SVG-Pixel (.toFixed(1)) zurückgerechnet auf den Kurs
    assert abs(ergebnis["tgtHighAusChart"] - ergebnis["tz"]["high"]) < tol
    assert abs(ergebnis["tgtLowAusChart"] - ergebnis["tz"]["low"]) < tol
    assert abs(ergebnis["extHighAusChart"] - ergebnis["ez"]["high"]) < tol
    assert abs(ergebnis["extLowAusChart"] - ergebnis["ez"]["low"]) < tol
    # Und: fibBand liefert wirklich die ATR-gepolsterte Zone (±ATR/2), nicht
    # zufällig die rohe Zone — echte Gegenprobe der Zahlen selbst.
    pad = rec["atr_14"] / 2
    assert abs(ergebnis["tz"]["low"] - (rec["target_zone"]["low"] - pad)) < 1e-9
    assert abs(ergebnis["tz"]["high"] - (rec["target_zone"]["high"] + pad)) < 1e-9


def test_chart_zonen_grenzen_entsprechen_exakt_fibband_MA_woche():
    """Dasselbe für den zweiten Einsatzort (Item 1b): `higher_degree`-Zonen
    mit dem TÄGLICHEN `atr_14` (bestehende Konvention aus #101)."""
    rec = _MA_REC
    hd = rec["higher_degree"]
    opts = {
        "points": [{"price": p} for p in [pt["price"] for pt in hd["chart_points"]]],
        "inval": hd["invalidation_price"],
        "zone": hd["target_zone"],
        "zoneExt": hd["target_zone_extended"],
        "atr": rec["atr_14"],
    }
    ergebnis = _js(f"""
      const opts = {json.dumps(opts)};
      const el = {{ clientWidth: 340, innerHTML: '' }};
      drawZonePreviewChart(el, opts);
      const tz = fibBand(opts.zone, opts.atr);
      console.log(JSON.stringify({{ tzLow: tz.low, tzHigh: tz.high, svgLaenge: el.innerHTML.length }}));
    """)
    pad = rec["atr_14"] / 2
    assert abs(ergebnis["tzLow"] - (hd["target_zone"]["low"] - pad)) < 1e-9
    assert abs(ergebnis["tzHigh"] - (hd["target_zone"]["high"] + pad)) < 1e-9
    assert ergebnis["svgLaenge"] > 0


def test_strukturell_keine_kurslinie_im_vorschau_bereich():
    """Struktureller Test aus dem Auftrag: der Vorschau-Bereich (rechts von
    "heute") enthält NACHWEISLICH keine Kurslinie — nur EIN `<path>` (die
    historische Linie), und dessen letzter Punkt liegt GENAU auf der
    "heute"-Trennlinie, nie dahinter."""
    rec = _MA_REC
    opts = {
        "points": [{"price": p} for p in [pt["price"] for pt in rec["chart_points"]]],
        "inval": rec["invalidation_price"],
        "zone": rec["target_zone"],
        "zoneExt": rec["target_zone_extended"],
        "atr": rec["atr_14"],
    }
    ergebnis = _js(f"""
      const opts = {json.dumps(opts)};
      const el = {{ clientWidth: 340, innerHTML: '' }};
      drawZonePreviewChart(el, opts);
      const svg = el.innerHTML;
      const pfade = [...svg.matchAll(/<path d="([^"]+)"/g)];
      const todayLine = svg.match(/<line x1="([\\d.]+)" y1="{{CP_CHART_PYT}}"/);
      // letzte Koordinate im Pfad (letztes "L<x>,<y>" oder das "M<x>,<y>" bei nur einem Punkt).
      const letzterPfad = pfade[pfade.length - 1][1];
      const teile = letzterPfad.split(/[ML]/).filter(Boolean);
      const [lastX] = teile[teile.length - 1].split(',').map(Number);
      console.log(JSON.stringify({{ anzahlPfade: pfade.length, lastX }}));
    """.replace("{CP_CHART_PYT}", "20"))
    assert ergebnis["anzahlPfade"] == 1, "es darf nur EINEN Pfad geben — die historische Linie"
    # todayX bei W=340: PX=8, plotW=324, histW=324*0.76=246.24, todayX=254.24
    assert abs(ergebnis["lastX"] - 254.24) < 0.2


def test_ohne_ausreichend_pivots_entsteht_kein_kaputtes_chart():
    ergebnis = _js("""
      const el = { clientWidth: 340, innerHTML: '' };
      drawZonePreviewChart(el, { points: [{price: 100}], zone: null, zoneExt: null, atr: null, inval: null });
      console.log(JSON.stringify({ hatLeerHinweis: el.innerHTML.includes('Kein Kursverlauf') }));
    """)
    assert ergebnis["hatLeerHinweis"] is True
