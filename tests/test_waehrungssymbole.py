"""Preisfeld-Währungssymbole auf der Karte (10.08.2026).

AUFTRAG: alle vier Preisfelder der Karte (Live-Kurs, Invalidierung, Zielzone,
Extension) bekommen ihr Markt-Symbol ('€' für DE, '$' für US) — bei den beiden
Bereichen EINMAL am Ende, nicht an jeder Zahl einzeln. Markt-Erkennung nutzt
die bestehende Quelle (Sektions-Id bzw. `market_key`), kein zweiter Test.

ZWEI NETZE, wie bei der Reihen-Diagnose (`test_reihen_diagnose.py`):
  (a) Quelltext-Anker — welche Stelle nutzt welches Feld, mit welcher
      Markt-Quelle (keine Ausführung, reine Übereinstimmungsprüfung);
  (b) node-Läufe mit von Hand nachgerechnetem Soll für die reinen
      Formatierungsfunktionen (`fmt`/`priceSym`/`fmtP`/`fmtZone`).

DER ENTSCHEIDENDE PUNKT (Live-Kurs, zwei Renderpfade — Kartenaufbau UND
Live-Poller alle 15s): das Symbol steht als eigener, vom Poller NIE berührter
DOM-Knoten NEBEN `[data-quote="price"]`, nicht darin. `quotePatch()` ersetzt
nur `el.textContent` des Preis-Spans — der Symbol-Text liegt strukturell
außerhalb davon und kann dadurch gar nicht verschwinden, ganz ohne eine
zweite, im Poller-Pfad dupliziert gepflegte Symbol-Logik. Das wird hier
STRUKTURELL geprüft (Anker-Reihenfolge im Quelltext) UND dadurch belegt, dass
`quotePatch` selbst KEINE neue Markt-/Symbol-Logik enthält.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

HTML = (ROOT / "docs/index.html").read_text(encoding="utf-8")

_NODE = shutil.which("node") or shutil.which("nodejs")


def _fn(name: str, tiefe: str = "    ") -> str:
    marke = f"{tiefe}function {name}("
    start = HTML.index(marke)
    return HTML[start:HTML.index(f"\n{tiefe}}}", start) + len(f"\n{tiefe}}}")]


def _const(name: str) -> str:
    marke = f"const {name} ="
    start = HTML.index(marke)
    return HTML[start:HTML.index(";", start) + 1]


def _js(script: str):
    if not _NODE:
        pytest.skip("kein node vorhanden — die Anker-Tests decken dieselben Fälle")
    quelle = "\n".join([_fn("fmt"), _const("CUR"), _fn("priceSym"), _fn("fmtP"),
                        _fn("fmtZone")])
    r = subprocess.run([_NODE, "-e", quelle + "\n" + script],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# ---------------------------------------------------------------------------
# (a) Quelltext-Anker — Fundstellen und ihre Markt-Quelle
# ---------------------------------------------------------------------------
def test_cur_kennt_beide_maerkte_richtig_herum():
    assert "const CUR = { US: '$', DE: '€' };" in HTML


def test_markt_erkennung_ist_die_bestehende_quelle_kein_zweiter_test():
    """Kein `.endsWith('.DE')` o.ä. in den neuen Preis-Helfern — die Karte
    bekommt ihren Markt aus derselben Quelle wie die Flaggen-Anzeige (Sektions-
    Id `id` bzw. `market_key`), nicht aus einem eigens erfundenen Ticker-Test."""
    for name in ("priceSym", "fmtP", "fmtZone"):
        koerper = _fn(name)
        assert ".endsWith" not in koerper and "market_key ===" not in koerper


@pytest.mark.parametrize("anker", [
    # Live-Kurs — Haupt-Karte: Symbol als eigener Knoten NEBEN dem Preis-Span,
    # nicht darin — das ist die ganze Poller-Persistenz-Garantie.
    '<div class="cockpit-price"><span data-quote="price">${fmt(c.close)}</span>${priceSym(market) ? ` ${priceSym(market)}` : \'\'}</div>',
    # Invalidierung — Metrik-Box.
    '<span class="m-val inval">${fmtP(c.invalidation_price, market)}</span>',
    # Zielzone — Metrik-Box (über die `zone`-Variable, s. u.).
    'const zone = fmtZone(c.target_zone, market);',
    # Extension.
    '<div class="ext-zone"><span class="ext-lbl">Extension</span>${fmtZone(ez, market)}`',
    # Großer-Grad-Block (Fallback ohne `timeframes`) — dieselben drei Felder
    # nochmal, damit ein älterer Report-Stand nicht unsymbolisiert aussieht.
    '<span class="hd-k">Invalidierung</span><span class="hd-v">${fmtP(hd.invalidation_price, market)}</span>',
    "const zoneStr = z => fmtZone(z, market);",
    # `card()` reicht `market` in jede Sub-Funktion durch, die Preisfelder
    # zeigt — Alternativ-Zählung und Zeitebenen-Panel.
    "${ambiguityBlock(c, market)}",
    "${c.timeframes ? tfPanel(c.timeframes, c.structure, c.close, market) : hdBlock}",
])
def test_fundstelle_vorhanden(anker):
    assert anker in HTML, anker


def test_card_bekommt_den_markt_von_beiden_aufrufern():
    # Markt-Karten: `id` ist buchstäblich 'US'/'DE' (derselbe Wert, der die
    # Flagge speist) — siehe `renderMarket('US', r.markets.US)` weiter unten.
    assert "card(c, i + 1, stand, id)" in HTML
    assert "renderMarket('US', r.markets.US);" in HTML
    assert "renderMarket('DE', r.markets.DE);" in HTML
    # Watchlist-Karte im 'setup'-Zustand geht durch dieselbe `card()` —
    # ihr Markt ist `market_key`, von der Pipeline gesetzt (nicht geraten).
    assert "return card(c, '☆', stand, c.market_key);" in HTML


def test_ambiguityblock_und_tfpanel_haben_den_markt_parameter():
    assert "function ambiguityBlock(c, market) {" in HTML
    assert "function tfPanel(tf, structure, cardClose, market) {" in HTML


def test_watchlist_kompaktkarte_traegt_ihr_symbol_und_reicht_market_key_weiter():
    """Die kompakte Watchlist-Karte (kein Top-5-Setup) zeigt Live-Kurs UND das
    Zeitebenen-Panel (`tfPanel`) — beide müssen den Markt aus `market_key`
    bekommen, derselben Quelle wie die Karten-Historie."""
    koerper = _fn("watchlistCard")
    assert "priceSym(c.market_key)" in koerper
    assert "tfPanel(c.timeframes, c.structure, c.close, c.market_key)" in koerper


def test_quote_patch_kennt_keine_waehrung_das_ist_der_punkt():
    """Der Live-Poller (alle 15s) braucht KEINE Symbol-Logik — genau deshalb
    kann das Symbol nach einem Tick nicht verschwinden: der berührte Knoten
    (`[data-quote=\"price\"]`) enthält nie das Symbol, nur die Zahl."""
    koerper = _fn("quotePatch")
    assert "textContent = fmt(q.price)" in koerper
    # NICHT auf blosses "$" geprueft — das steckt in jeder Template-Literal-
    # Interpolation (`${...}`) und waere ein Fehlalarm. "€" dagegen kommt in
    # normalem JS-Quelltext nirgends sonst vor.
    for verboten in ("CUR", "priceSym", "fmtP(", "fmtZone(", "market", "€"):
        assert verboten not in koerper, (
            f"quotePatch enthaelt `{verboten}` — die Poller-Persistenz sollte "
            f"strukturell gelten, nicht durch eine zweite Symbol-Logik")


def test_wl_instant_card_bleibt_unveraendert_kein_markt_bekannt():
    """Widerspruch, gemeldet statt umgangen: die Watchlist-Sofortkarte zeigt
    den Live-Kurs, bevor der nächste Lauf Markt/Analyse geliefert hat — hier
    gibt es keine bestehende Markt-Quelle (kein `market_key`, keine Flagge).
    Ein Symbol anzubringen bräuchte einen NEUEN, verbotenen Test (Ticker-
    Endung). Bleibt deshalb bewusst ohne Symbol."""
    koerper = _fn("_wlInstantCard")
    assert '<div class="cockpit-price" data-quote="price">…</div>' in koerper
    assert "priceSym" not in koerper and "CUR" not in koerper


@pytest.mark.parametrize("stelle, funktion", [
    ("episode-detail-panel (Backtesting)", "showEpisodeDetail"),
    ("Watchlist-Top-5-Historie", "_wlHistRow"),
])
def test_ausserhalb_der_haupt_karte_bewusst_unangetastet(stelle, funktion):
    """GRENZEN: nur die vier Preisfelder auf der Haupt-Karte. Diese beiden
    Stellen zeigen dieselben Feldnamen (Zielzone/Extension/Invalidierung),
    liegen aber außerhalb der Karte — bewusst nicht geändert, damit ein
    stiller Rückbau hier auffiele statt unbemerkt zu bleiben."""
    koerper = _fn(funktion)
    assert "fmtZone" not in koerper and "fmtP" not in koerper, (
        f"{stelle} wurde doch angefasst — das war nicht beauftragt")


def test_trade_journal_bewusst_unangetastet():
    """Dieselbe Grenze wie oben, für die zwei Preisfeld-Stellen im
    Trade-Journal (`_tjFrozenZeile`, `_tjEntwurfBlock`)."""
    for name in ("_tjFrozenZeile", "_tjEntwurfBlock"):
        koerper = _fn(name)
        assert "fmtZone" not in koerper and "fmtP" not in koerper, name


# ---------------------------------------------------------------------------
# (b) Ausgeführte Werte — Soll von Hand nachgerechnet
# ---------------------------------------------------------------------------
def test_priceSym_kennt_nur_die_beiden_bekannten_maerkte():
    assert _js("console.log(JSON.stringify(priceSym('DE')))") == "€"
    assert _js("console.log(JSON.stringify(priceSym('US')))") == "$"
    for unbekannt in ("XX", "", None, "us", "de"):  # Groß/Kleinschreibung zaehlt
        assert _js(f"console.log(JSON.stringify(priceSym({json.dumps(unbekannt)})))") == ""


@pytest.mark.parametrize("n, market, soll", [
    (20.8, "DE", "20,8 €"),
    (20.8, "US", "20,8 $"),
    (155.2, "US", "155,2 $"),
    (0, "DE", "0 €"),                 # 0 ist ein gültiger Kurs, kein „fehlt"
    (None, "DE", "–"),                # fehlender Wert -> '–' OHNE Symbol
    (20.8, None, "20,8"),             # unbekannter Markt -> kein Symbol
    (20.8, "XX", "20,8"),
])
def test_fmtP_einzelwert_von_hand_nachgerechnet(n, market, soll):
    m = "null" if market is None else json.dumps(market)
    v = "null" if n is None else json.dumps(n)
    erg = _js(f"console.log(JSON.stringify(fmtP({v}, {m})))")
    assert erg == soll


@pytest.mark.parametrize("z, market, soll", [
    ({"low": 21.93, "high": 22.5}, "DE", "21,93–22,5 €"),
    ({"low": 22.01, "high": 22.64}, "DE", "22,01–22,64 €"),
    ({"low": 160.1, "high": 165.4}, "US", "160,1–165,4 $"),
    (None, "DE", "–"),
    ({"low": 21.93, "high": 22.5}, None, "21,93–22,5"),
])
def test_fmtZone_bereich_symbol_nur_einmal_am_ende(z, market, soll):
    zz = "null" if z is None else json.dumps(z)
    m = "null" if market is None else json.dumps(market)
    erg = _js(f"console.log(JSON.stringify(fmtZone({zz}, {m})))")
    assert erg == soll
    # Die eigentliche Zusage aus dem Auftrag: EIN Symbol, nicht zwei.
    if market and z:
        assert erg.count("€") + erg.count("$") == 1, erg
