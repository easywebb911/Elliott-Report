"""Live-Überholt-Kennzeichnung (05.09.2026, ADBE-Diagnose vom 04.09.2026).

ANLASS: Score, Ranking und der PRU-Guard-Filter (#112) werden EINMAL täglich
beim Batch-Lauf berechnet und bleiben bis zum nächsten Lauf fest — nur der
Live-Kurs (`quotePatch`) aktualisiert sich zwischendurch. Belegter Fall:
ADBE stand am 04.09.2026 (Report-Commit d4c20c3) auf Platz 1 (Score 81), der
Live-Kurs (285,75 $) hatte die eigene Beobachtungszone (target_zone.low
281,1331 $) bereits überschritten — nach der Systemlogik (#112) hätte der
Kandidat bei diesem Kurs gar nicht mehr in den Top-5 auftauchen dürfen. Das
bestehende `.zone-badge` (seit #28) existiert zwar, ist aber zu unauffällig
für genau diesen Fall: klein (0.62rem), weit unten auf der Karte (nach
Metriken/Extension), und der "reached"-Zustand — genau ADBEs Fall — trägt
GAR KEINE Signalfarbe (Grundstil ist neutral/grau, Orange nur bei "over").

Score/Ranking/der #112-Filter selbst werden NICHT angefasst — dieser Auftrag
betrifft ausschließlich die Anzeige eines bereits vom Batch-Lauf berechneten
Zustands (target_zone/invalidation_price) gegen den Live-Kurs.

ZWEI NETZE:
  (a) Die reine Entscheidungsfunktion `_liveOutdatedStatus` — direkt mit
      echten Zahlen (ADBE@04.09.2026) und synthetischen Grenzfällen belegt.
  (b) Quellcode-Abgleich (Muster aus test_beobachtungszone_umbenennung.py):
      card() (Erstrender) und _setLiveOutdated() (Live-Update via
      quotePatch) MÜSSEN dieselbe Entscheidungsfunktion + denselben
      Text-Generator verwenden — sonst zeigt der erste Live-Tick nach dem
      Laden einen anderen Zustand/Text als der initiale Render.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "docs/index.html").read_text(encoding="utf-8")

_NODE = shutil.which("node") or shutil.which("nodejs")


def _fn(name: str, tiefe: str = "    ") -> str:
    """Extrahiert EINE Funktion aus der Karten-Quelle (Muster aus
    test_beobachtungszone_umbenennung.py/test_reihen_diagnose.py)."""
    marke = f"{tiefe}function {name}("
    start = HTML.index(marke)
    return HTML[start:HTML.index(f"\n{tiefe}}}", start) + len(f"\n{tiefe}}}")]


def _js(script: str):
    if not _NODE:
        pytest.skip("kein node vorhanden — die Quellcode-Abgleich-Tests decken "
                    "dieselben Fälle statisch ab")
    quelle = "\n".join([_fn("esc"), _fn("_wlZeitKurz"),
                        _fn("_liveOutdatedStatus"), _fn("_liveOutdatedText")])
    r = subprocess.run([_NODE, "-e", quelle + "\n" + script],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# ---------------------------------------------------------------------------
# (a) Reine Entscheidungsfunktion — Wert-Test (echter ADBE-Fall) + Grenzfälle
# ---------------------------------------------------------------------------
def test_adbe_04_09_fall_ergibt_reached():
    """Wert-Test: echte Zahlen aus data/report.json@d4c20c3 (Diagnose
    04.09.2026) — Live-Kurs 285,75 $, target_zone.low 281,1331 $,
    target_zone.high 297,88 $, invalidation_price 237,25 $."""
    status = _js("console.log(JSON.stringify("
                 "_liveOutdatedStatus(285.75, 281.1331, 297.88, 237.25)))")
    assert status == "reached"


def test_adbe_fall_erzeugt_den_erwarteten_hinweistext():
    ergebnis = _js("""
      const s = _liveOutdatedStatus(285.75, 281.1331, 297.88, 237.25);
      console.log(JSON.stringify(_liveOutdatedText(s, _wlZeitKurz('2026-09-04T00:24:13Z'))));
    """)
    assert "Beobachtungszone laut Live-Kurs bereits erreicht" in ergebnis
    assert "Einstufung basiert auf dem letzten Lauf" in ergebnis
    assert "04.09., 00:24" in ergebnis


def test_kurs_unter_der_zone_bleibt_ohne_status():
    """Regressionstest: ein Kandidat, dessen Live-Kurs die Zone NICHT
    erreicht hat, bekommt KEINE Kennzeichnung."""
    status = _js("console.log(JSON.stringify("
                 "_liveOutdatedStatus(250, 281.1331, 297.88, 237.25)))")
    assert status is None


def test_kurs_ueber_der_zone_ergibt_over():
    status = _js("console.log(JSON.stringify("
                 "_liveOutdatedStatus(300, 281.1331, 297.88, 237.25)))")
    assert status == "over"


@pytest.mark.parametrize("price", [237.25, 200])
def test_kurs_auf_oder_unter_invalidierung_ergibt_inval(price):
    """Auftrag Punkt 4: der noch gravierendere Fall — die ganze
    Wellen-Zählung wäre nach aktuellem Kurs bereits ungültig."""
    status = _js(f"console.log(JSON.stringify("
                 f"_liveOutdatedStatus({price}, 281.1331, 297.88, 237.25)))")
    assert status == "inval"


def test_invalidierung_hat_vorrang_vor_zone():
    """Rangfolge-Test: selbst wenn ein (konstruierter) Fall sowohl die
    Zonen- als auch die Invalidierungs-Schwelle erfüllen würde, gewinnt
    IMMER 'inval' — die ungültige Zählung wiegt schwerer als eine
    erreichte/überschrittene Zone."""
    status = _js("console.log(JSON.stringify("
                 "_liveOutdatedStatus(150, 100, 110, 200)))")
    assert status == "inval"


@pytest.mark.parametrize("zl, zh, inv", [
    (None, None, None), ("", "", ""), (float("nan"), float("nan"), float("nan")),
])
def test_fehlende_werte_ergeben_keinen_status_kein_absturz(zl, zh, inv):
    """Fail-soft: Number(null) ist 0 (endlich!) — ohne expliziten Guard
    würde eine FEHLENDE Zone/Invalidierung fälschlich als 'Kurs >= 0'
    durchgehen. Direkter Regressionstest für genau diesen Fallstrick
    (Muster aus zoneDistPct, s. Kommentar in _liveOutdatedStatus)."""
    def j(v):
        return "NaN" if isinstance(v, float) else json.dumps(v)
    status = _js(f"console.log(JSON.stringify("
                 f"_liveOutdatedStatus(500, {j(zl)}, {j(zh)}, {j(inv)})))")
    assert status is None


def test_kaputter_preis_ergibt_keinen_status():
    status = _js("console.log(JSON.stringify("
                 "_liveOutdatedStatus(NaN, 281.1331, 297.88, 237.25)))")
    assert status is None


def test_dataset_strings_funktionieren_wie_zahlen():
    """_setLiveOutdated liest die Werte aus el.dataset.* — das sind IMMER
    Strings, nie Zahlen. Number('281.1331') muss also identisch zum
    reinen Zahlenwert funktionieren."""
    status = _js("console.log(JSON.stringify("
                 "_liveOutdatedStatus('285.75', '281.1331', '297.88', '237.25')))")
    assert status == "reached"


def test_ohne_stand_zeitstempel_bleibt_der_satz_vollstaendig_aber_ohne_stand():
    """Fail-soft: ein kaputter/fehlender _lastReportTs darf den Hinweistext
    nicht mit 'undefined'/'null' verunstalten — der Satz bleibt ohne den
    Stand-Halbsatz vollständig."""
    ergebnis = _js("""
      console.log(JSON.stringify([
        _liveOutdatedText('reached', _wlZeitKurz(null)),
        _liveOutdatedText('over', _wlZeitKurz('kaputt')),
      ]));
    """)
    for text in ergebnis:
        assert "undefined" not in text and "null" not in text and "NaN" not in text
        assert "Beobachtungszone laut Live-Kurs bereits" in text
        assert "Stand" not in text   # kein Halbsatz ohne echten Zeitstempel


def test_inval_text_benennt_die_zaehlung_als_ungueltig():
    ergebnis = _js("""
      console.log(JSON.stringify(_liveOutdatedText('inval', null)));
    """)
    assert "Invalidierung" in ergebnis
    assert "nicht mehr gültig" in ergebnis


# ---------------------------------------------------------------------------
# (b) Quellcode-Abgleich — Erstrender und Live-Update dürfen nicht
# auseinanderlaufen (Muster aus test_beobachtungszone_umbenennung.py)
# ---------------------------------------------------------------------------
def test_card_und_live_update_nutzen_dieselbe_entscheidungsfunktion():
    card_body = _fn("card")
    setter_body = _fn("_setLiveOutdated")
    assert "_liveOutdatedStatus(" in card_body, \
        "card() berechnet den Anfangszustand nicht über _liveOutdatedStatus"
    assert "_liveOutdatedStatus(" in setter_body, \
        "_setLiveOutdated() berechnet den Live-Zustand nicht über dieselbe Funktion"


def test_card_und_live_update_nutzen_denselben_text_generator():
    card_body = _fn("card")
    setter_body = _fn("_setLiveOutdated")
    assert "_liveOutdatedText(" in card_body
    assert "_liveOutdatedText(" in setter_body


def test_quotepatch_ruft_setliveoutdated_zusaetzlich_zu_den_bestehenden_updates():
    """GRENZEN: quotePatch()s bestehende Update-Logik (welche Felder live
    aktualisiert werden) bleibt unveraendert — _setLiveOutdated kommt NUR
    additiv dazu, keiner der bisherigen Aufrufe wird ersetzt."""
    qp_body = _fn("quotePatch")
    for bestehend in ("_setZoneBadge(", "_setTfHint(", "_setZoneDist("):
        assert bestehend in qp_body, f"bestehender quotePatch-Aufruf fehlt: {bestehend}"
    assert "_setLiveOutdated(card, q.price)" in qp_body


def test_setliveoutdated_liest_dieselben_daten_attribute_wie_card():
    """Anker-Konsistenz: card() schreibt data-zl/data-zh/data-inv auf
    [data-live-outdated] — _setLiveOutdated liest exakt diese drei."""
    card_body = _fn("card")
    setter_body = _fn("_setLiveOutdated")
    assert "data-live-outdated" in card_body
    assert "data-zl=" in card_body and "data-zh=" in card_body and "data-inv=" in card_body
    for attr in ("dataset.zl", "dataset.zh", "dataset.inv"):
        assert attr in setter_body, f"{attr} fehlt in _setLiveOutdated"


# ---------------------------------------------------------------------------
# CSS: die verstärkte Kennzeichnung existiert wirklich (Kartenrahmen + Text)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("klasse", [
    ".card-outdated-zone", ".card-outdated-inval",
    ".live-outdated", ".live-outdated-zone", ".live-outdated-inval",
])
def test_css_klassen_fuer_die_verstaerkte_kennzeichnung_existieren(klasse):
    assert klasse in HTML, f"CSS-Klasse {klasse} fehlt"


def test_bestehendes_zone_badge_bleibt_unveraendert():
    """Das bestehende, bewusst dezente .zone-badge (#28) wird NICHT entfernt
    oder umgeschrieben — die neue Kennzeichnung ist rein additiv daneben."""
    badge_body = _fn("_setZoneBadge")
    assert "'Beobachtungszone überschritten'" in badge_body
    assert "'Beobachtungszone erreicht'" in badge_body
    assert "zone-badge-over" in badge_body and "zone-badge-reached" in badge_body


# ---------------------------------------------------------------------------
# GRENZEN: keine Berührung von Score/Ranking/Filter-Konsumenten
# ---------------------------------------------------------------------------
def test_neue_funktionen_lesen_keine_score_ranking_felder():
    for name in ("_liveOutdatedStatus", "_liveOutdatedText", "_setLiveOutdated"):
        body = _fn(name)
        for verboten in ("score_heuristic", "target_exceeded", "candidates.sort",
                          "rank"):
            assert verboten not in body, f"{name} berührt {verboten}"
