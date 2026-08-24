"""Chart-Vorschau (23.08.2026, Bau-Auftrag "Kursverlauf + Zonen auf der Karte").

EIN wiederverwendbares Chart-Element (historischer Kursverlauf + Zonen-Bänder
+ 10-Handelstage-Vorschau mit fortgeführten Zonen, KEINE Kursprognose) an
zwei Stellen: Haupt-Card (Tagesgrad, `chart_points`) und "Großer Grad ·
Wochen"-Block (`higher_degree.chart_points`). Standardmäßig eingeklappt,
DASSELBE Auf-/Zuklapp-Muster wie das KI-Kommentar-Feld (`agentBlock`), lazy
gerendert (Performance-Vorgabe: kein SVG vor dem tatsächlichen Aufklappen).

GRENZEN: keine neue Berechnung — die Zonen-Grenzen kommen unverändert über
`fibBand(zone, atr)` (#101), derselbe Aufruf wie an den vier bestehenden
Zahlen-Anzeigestellen. `drawEpisodeChart`s ZEICHEN-Logik (Bänder/Linien
selbst) bleibt unangetastet (eigene, neue Funktion `drawZonePreviewChart`
statt Extraktion — kein Regressionsrisiko für die bestehende Episode-Detail-
Ansicht, s. `test_atr_band_frontend.py::test_drawepisodechart_
baender_bewusst_unangetastet`, das weiterhin grün bleibt).

NACHTRAG (Folge-Auftrag nach #105): `drawEpisodeChart`s eigene Legende hatte
DIESELBE Diskrepanz wie #104s neuer Chart (Beobachtungszone-Symbol zeigte
eine helle Linie statt der tatsächlichen Flächen-Füllung) — #105 hatte das
bewusst NICHT mitgefixt (außerhalb der damaligen Grenzen) und einen
Gegenprobe-Test hinterlassen. Dieser Auftrag überträgt exakt dieselbe
#105-Korrektur (identischer Füllfarbe-Literal, keine neue Farbe) auf
`drawEpisodeChart`s Legende — NUR die Legende, nicht die Bänder/Linien
selbst. Der alte Gegenprobe-Test (`test_drawepisodechart_legende_bleibt_
bewusst_unangetastet`) ist jetzt `test_drawepisodechart_legende_ist_jetzt_
ebenfalls_korrigiert` mit geändertem Soll-Wert.

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


def test_beobachtungszone_legende_zeigt_die_flaeche_nicht_die_linie():
    """Bugfix (Folge-Auftrag nach #104, Easy-Meldung): das Legenden-Symbol vor
    "Beobachtungszone" zeigte bisher dieselbe helle Linien-Optik wie
    "Kursverlauf" (`border-color:var(--grn)`, geerbt von `.ep-legend i`s
    Linien-CSS) — im Chart ist die Beobachtungszone aber eine gefüllte
    FLÄCHE (`tgtBand`), keine Linie. Soll-Wert: dieselbe Füllfarbe wie
    `tgtBand` (`rgba(34,197,94,0.15)`), kein Rand (echte Fläche, kein
    Linien-Rest aus der geerbten CSS)."""
    koerper = _fn("drawZonePreviewChart")
    assert '<span><i style="background:rgba(34,197,94,0.15);border:none;height:9px"></i>Beobachtungszone</span>' in koerper
    # Gegenprobe: die alte, falsche Linien-Optik ist weg.
    assert '<span><i style="border-color:var(--grn)"></i>Beobachtungszone</span>' not in koerper


def test_extension_legende_zeigt_ebenfalls_die_flaeche_mit_gestricheltem_rand():
    """Zusätzlich gefundene, gleichartige Diskrepanz (AUFTRAG Punkt 3): das
    Extension-Symbol zeigte bisher NUR den gestrichelten Rand als Linie,
    ohne die (blasse) Füllfarbe der tatsächlichen `extBand`-Fläche. Jetzt:
    dieselbe Füllfarbe (`rgba(34,197,94,0.07)`) UND derselbe gestrichelte
    Rand (`var(--txt-dim)`) wie im Chart — keine neue, eigene Farbe."""
    koerper = _fn("drawZonePreviewChart")
    assert ('<span><i style="background:rgba(34,197,94,0.07);border:1px dashed var(--txt-dim);height:9px">'
            '</i>Extension (spekulativ)</span>') in koerper


def test_kursverlauf_und_invalidierung_legende_bleiben_unveraendert_korrekt():
    """Gegenprobe (AUFTRAG Punkt 3): diese zwei Einträge sind TATSÄCHLICH
    Linien im Chart (`histLine` solide, `invLine` gestrichelt) — ihre
    Linien-Symbole waren schon vorher korrekt und bleiben unangetastet."""
    koerper = _fn("drawZonePreviewChart")
    assert '<span><i style="border-color:var(--spark-end)"></i>Kursverlauf</span>' in koerper
    assert '<span><i style="border-color:var(--red);border-top-style:dashed"></i>Invalidierung</span>' in koerper


def test_drawepisodechart_legende_ist_jetzt_ebenfalls_korrigiert():
    """SOLL-WERT GEÄNDERT (Folge-Auftrag nach #105): #105 hatte diese
    Diskrepanz in `drawEpisodeChart`s eigener Legende bewusst NICHT
    angefasst (außerhalb der damaligen Auftragsgrenzen) und stattdessen
    diesen Test als Gegenprobe hinterlassen, dass sie unangetastet bleibt.
    Dieser Auftrag überträgt exakt dieselbe #105-Korrektur (identischer
    Füllfarbe-Literal `rgba(34,197,94,0.15)`, keine neue Farbe) auf
    `drawEpisodeChart` — der alte Soll-Wert (reine Linien-Optik) ist damit
    absichtlich überholt, nicht mehr die Erwartung."""
    koerper = _fn("drawEpisodeChart")
    assert '<span><i style="background:rgba(34,197,94,0.15);border:none;height:9px"></i>Beobachtungszone</span>' in koerper
    # Gegenprobe: die alte, falsche Linien-Optik ist weg.
    assert '<span><i style="border-color:var(--grn)"></i>Beobachtungszone</span>' not in koerper
    # Die drei echten Linien-Einträge (Zählung, Verlauf nach Einstieg,
    # Invalidierung) bleiben unverändert — GRENZEN: nur Beobachtungszone.
    assert '<span><i style="border-color:var(--spark-end)"></i>Zählung (0–${Math.max(0, waves.length - 1)})</span>' in koerper
    assert '<span><i style="border-color:var(--ora)"></i>Verlauf nach Einstieg</span>' in koerper
    assert '<span><i style="border-color:var(--red);border-top-style:dashed"></i>Invalidierung</span>' in koerper


def test_drawepisodechart_hat_jetzt_einen_extension_legenden_eintrag():
    """Folge-Auftrag nach #106: `drawEpisodeChart` zeichnet die Extension-
    Zone durchaus (`extBand = band(ez.low, ez.high, 'rgba(34,197,94,0.07)')`,
    Zeile direkt über dem SVG-Body), hatte dafür aber KEINEN Legenden-
    Eintrag — anders als der #104/#105-Chart, der "Extension (spekulativ)"
    bereits mit Füllung+gestricheltem Rand zeigt. Exakt derselbe Wortlaut/
    dieselben Farb-Literale werden hier übernommen, direkt nach
    "Beobachtungszone" eingefügt (dieselbe Reihenfolge wie #104/#105)."""
    koerper = _fn("drawEpisodeChart")
    assert "extBand = band(ez.low, ez.high, 'rgba(34,197,94,0.07)');" in koerper
    assert ('<span><i style="background:rgba(34,197,94,0.07);border:1px dashed var(--txt-dim);height:9px">'
            '</i>Extension (spekulativ)</span>') in koerper
    # Reihenfolge: Beobachtungszone direkt gefolgt von Extension, dann Invalidierung.
    beob = koerper.index("Beobachtungszone</span>")
    ext = koerper.index("Extension (spekulativ)</span>")
    inval = koerper.index("Invalidierung</span>")
    assert beob < ext < inval
    # Die vier bestehenden Einträge bleiben in Wortlaut/Position unverändert.
    assert '<span><i style="border-color:var(--spark-end)"></i>Zählung (0–${Math.max(0, waves.length - 1)})</span>' in koerper
    assert '<span><i style="border-color:var(--ora)"></i>Verlauf nach Einstieg</span>' in koerper
    assert '<span><i style="background:rgba(34,197,94,0.15);border:none;height:9px"></i>Beobachtungszone</span>' in koerper
    assert '<span><i style="border-color:var(--red);border-top-style:dashed"></i>Invalidierung</span>' in koerper


def test_ext104105_chart_und_legenden_struktur_unangetastet():
    """GRENZEN: keine Änderung an #104/#105/#106s bereits korrekten
    Legenden/Zeichenlogik — nur `drawEpisodeChart` betroffen."""
    koerper = _fn("drawZonePreviewChart")
    assert ('<span><i style="background:rgba(34,197,94,0.07);border:1px dashed var(--txt-dim);height:9px">'
            '</i>Extension (spekulativ)</span>') in koerper
    assert "extBand = band(ez.low, ez.high, 'rgba(34,197,94,0.07)'," in koerper  # unverändert (mit Rand-Param)


# Echter Beispiel-Record, Quelle: data/forward_collection.json, episode_id
# "PANW@2026-07-22" — hat chart_points, target_zone, target_zone_extended,
# invalidation_price.
_PANW = next(
    r for r in json.loads((ROOT / "data/forward_collection.json").read_text(encoding="utf-8"))["records"]
    if r.get("episode_id") == "PANW@2026-07-22"
)


def test_drawepisodechart_legenden_swatch_stimmt_ECHT_mit_der_gerenderten_flaeche_ueberein():
    """Der Wert-Test aus dem Auftrag, für `drawEpisodeChart`: kein
    String-Vergleich zweier Literale, sondern ein echter Lauf der Funktion —
    die tatsächlich gerenderte `fill`-Farbe von `tgtBand` im SVG wird gegen
    die tatsächlich gerenderte `background`-Farbe des Beobachtungszone-
    Legenden-Swatches verglichen. Soll-Wert explizit benannt: beide MÜSSEN
    identisch sein, nämlich `rgba(34,197,94,0.15)`."""
    if not _NODE:
        pytest.skip("kein node vorhanden — die Literal-Tests decken denselben Fall")
    quelle = _fn("drawEpisodeChart")
    r = _PANW
    script = f"""
      const el = {{ clientWidth: 340, innerHTML: '' }};
      drawEpisodeChart(el, {json.dumps(r)});
      const svg = el.innerHTML;
      const tgtFill = svg.match(/<rect[^>]*fill="(rgba\\(34,197,94,0\\.15\\))"/)[1];
      const swatch = svg.match(/<i style="background:(rgba\\(34,197,94,0\\.15\\));border:none[^"]*"><\\/i>Beobachtungszone/)[1];
      console.log(JSON.stringify({{ tgtFill, swatch }}));
    """
    proc = subprocess.run([_NODE, "-e", quelle + "\n" + script],
                           capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    ergebnis = json.loads(proc.stdout)
    assert ergebnis["swatch"] == ergebnis["tgtFill"] == "rgba(34,197,94,0.15)"


def test_drawepisodechart_extension_legenden_swatch_stimmt_ECHT_mit_der_gerenderten_flaeche_ueberein():
    """Derselbe Wert-Test wie oben, jetzt für den neuen Extension-Eintrag:
    ein echter Lauf von `drawEpisodeChart`, die tatsächlich gerenderte
    `fill`-Farbe von `extBand` gegen die tatsächlich gerenderte `background`-
    Farbe des Extension-Swatches verglichen. Soll-Wert: beide identisch
    `rgba(34,197,94,0.07)`.

    TRANSPARENT DOKUMENTIERT (Exzellenz-Selbstprüfung Punkt 2): `extBand` in
    `drawEpisodeChart` selbst hat KEINEN `stroke` (nur `fill` — der `band()`-
    Helfer dieser Funktion nimmt gar keinen Rand-Parameter, anders als
    `drawZonePreviewChart`s `band()`). Der gestrichelte Rand im Legenden-
    Swatch ist also eine bewusste, vom Auftrag ausdrücklich verlangte
    Konsistenz-Entscheidung mit dem #104/#105-Chart (gleiches Symbol für
    "Extension (spekulativ)" app-weit) — KEIN 1:1-Abbild von `extBand`s
    eigenem SVG-Attribut. Dieser Test prüft deshalb die FÜLLFARBE exakt
    (echte Übereinstimmung) und bestätigt zusätzlich explizit, dass
    `extBand` selbst keinen `stroke` trägt — damit dieser Unterschied
    sichtbar bleibt, nicht stillschweigend verschwindet."""
    if not _NODE:
        pytest.skip("kein node vorhanden — die Literal-Tests decken denselben Fall")
    quelle = _fn("drawEpisodeChart")
    r = _PANW
    script = f"""
      const el = {{ clientWidth: 340, innerHTML: '' }};
      drawEpisodeChart(el, {json.dumps(r)});
      const svg = el.innerHTML;
      const extRectMatch = svg.match(/<rect[^>]*fill="(rgba\\(34,197,94,0\\.07\\))"[^>]*\\/>/);
      const extFill = extRectMatch[1];
      const extRectHatStroke = /stroke=/.test(extRectMatch[0]);
      const swatch = svg.match(/<i style="background:(rgba\\(34,197,94,0\\.07\\));border:1px dashed var\\(--txt-dim\\);height:9px"><\\/i>Extension \\(spekulativ\\)/)[1];
      console.log(JSON.stringify({{ extFill, extRectHatStroke, swatch }}));
    """
    proc = subprocess.run([_NODE, "-e", quelle + "\n" + script],
                           capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    ergebnis = json.loads(proc.stdout)
    assert ergebnis["swatch"] == ergebnis["extFill"] == "rgba(34,197,94,0.07)"
    assert ergebnis["extRectHatStroke"] is False, \
        "extBand hat jetzt einen Rand — das wäre eine Änderung der Chart-Zeichenlogik (GRENZEN)"


def test_legenden_swatches_stimmen_ECHT_mit_der_gerenderten_flaeche_ueberein():
    """Der Wert-Test aus dem Auftrag: kein String-Vergleich zweier Literale,
    sondern ein echter Lauf von `drawZonePreviewChart` — die tatsächlich
    gerenderte `fill`-Farbe von `tgtBand`/`extBand` im SVG wird gegen die
    tatsächlich gerenderte `background`-Farbe der Legenden-Swatches
    verglichen. Soll-Wert explizit benannt: beide MÜSSEN identisch sein."""
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
      const tgtFill = svg.match(/<rect[^>]*fill="(rgba\\(34,197,94,0\\.15\\))"/)[1];
      const extFill = svg.match(/<rect[^>]*fill="(rgba\\(34,197,94,0\\.07\\))"[^>]*stroke=/)[1];
      const tgtSwatch = svg.match(/<i style="background:(rgba\\(34,197,94,0\\.15\\));border:none[^"]*"><\\/i>Beobachtungszone/)[1];
      const extSwatch = svg.match(/<i style="background:(rgba\\(34,197,94,0\\.07\\));border:1px dashed[^"]*"><\\/i>Extension/)[1];
      console.log(JSON.stringify({{ tgtFill, extFill, tgtSwatch, extSwatch }}));
    """)
    assert ergebnis["tgtSwatch"] == ergebnis["tgtFill"] == "rgba(34,197,94,0.15)"
    assert ergebnis["extSwatch"] == ergebnis["extFill"] == "rgba(34,197,94,0.07)"


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
