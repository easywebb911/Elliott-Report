"""Ersatzbank/Nachrücker-Funktion (Auftrag 23.09.2026, #118-Folge).

KONTEXT: Easy-Entscheidung nach Rückfrage (23.09.2026) — die ECHTE Episode
für einen Nachrücker entsteht NICHT live/sofort, sondern erst beim nächsten
regulären elliott_pipeline.py-Lauf (dort landet er dann ganz normal in den
sichtbaren Top-N, s. tests/test_forward_collection.py::
test_nachruecker_wird_episode_faehig_sobald_er_selbst_top5_ist und
tests/test_in_session_creation.py::
test_nachruecker_episode_wird_in_session_markiert_ohne_neuen_code). Das
Frontend zeigt bis dahin nur eine reine LIVE-VORSCHAU: market.candidates
trägt seit dem Backend-Auftrag bis zu TOP_N_STORED (8) Kandidaten (sichtbare
Top-5 + Ersatzbank Platz 6-8, dieselben bereits berechneten Kandidaten, kein
neuer Datenabruf). _effectiveVisible() entscheidet rein aus dem AKTUELLEN
Live-Status (via dieselbe _liveOutdatedStatus()-Funktion wie die bestehende
#118-Anzeige), welche 5 davon gerade als Karte erscheinen — GENAU der reale
ADBE-Fall vom 04.09.2026 (Report-Commit d4c20c3, s. test_live_ueberholt.py)
dient hier als Wert-Test für die Nachrücker-Situation: ADBE (Platz 1) hätte
laut Live-Kurs bereits die Zone erreicht und würde durch den nächsten
gespeicherten Kandidaten ersetzt.

ZWEI NETZE:
  (a) Reine Entscheidungsfunktion _effectiveVisible() — direkt mit
      Kandidatenlisten und manuell gesetztem Live-Status getestet (kein DOM).
  (b) Quellcode-Abgleich: dieselbe _liveOutdatedStatus()-Funktion wie #118,
      keine Berührung von Score/Ranking/Filter-Feldern.
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
    marke = f"{tiefe}function {name}("
    start = HTML.index(marke)
    return HTML[start:HTML.index(f"\n{tiefe}}}", start) + len(f"\n{tiefe}}}")]


def _ersatzbank_block() -> str:
    """VISIBLE_TOP_N + _liveOutdatedByTicker + _effectiveVisible als EIN
    zusammenhängender Block — dieselbe Reihenfolge/derselbe Text wie in
    docs/index.html, keine Kopie (Muster aus test_recalc_sitzungs_check.py
    ::_sitzungsfenster_block())."""
    start = HTML.index("const VISIBLE_TOP_N = 5;")
    ende = HTML.index("\n    }\n", HTML.index("function _effectiveVisible(")) + len("\n    }\n")
    block = HTML[start:ende]
    for marke in ("const VISIBLE_TOP_N", "const _liveOutdatedByTicker",
                 "function _effectiveVisible("):
        assert marke in block, f"Block unvollständig — '{marke}' fehlt"
    return block


BLOCK = _ersatzbank_block()


def _js(script: str):
    if not _NODE:
        pytest.skip("kein node vorhanden")
    quelle = "\n".join([_fn("esc"), _fn("_liveOutdatedStatus"), BLOCK])
    r = subprocess.run([_NODE, "-e", quelle + "\n" + script],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _kandidat(ticker, zl=281.1331, zh=297.88, inv=237.25):
    return {"ticker": ticker, "target_zone": {"low": zl, "high": zh},
            "invalidation_price": inv}


# ---------------------------------------------------------------------------
# (a) _effectiveVisible() — Wert-Test mit dem echten ADBE-Fall
# ---------------------------------------------------------------------------
def test_adbe_faellt_ohne_live_status_normal_unter_die_sichtbaren_top5():
    """Regressionstest: ohne jeden Live-Status (frisch geladener Report, vor
    dem ersten Live-Tick) bleiben die sichtbaren Top-5 exakt die ersten 5
    nach Score-Reihenfolge — unverändert zum Verhalten vor diesem Auftrag."""
    acht = [_kandidat(f"T{i}") for i in range(8)]
    ergebnis = _js(f"""
      const market = {{candidates: {json.dumps(acht)}}};
      console.log(JSON.stringify(_effectiveVisible(market).map(c => c.ticker)));
    """)
    assert ergebnis == ["T0", "T1", "T2", "T3", "T4"]


def test_adbe_04_09_fall_wird_durch_den_naechsten_kandidaten_ersetzt():
    """Wert-Test: ADBE (Platz 1) hat laut echtem Live-Kurs (285,75 $, ADBE@
    04.09.2026) die Zone bereits erreicht ('reached', s. test_live_ueberholt.
    py::test_adbe_04_09_fall_ergibt_reached) — er verschwindet aus der
    sichtbaren Liste, der nächste gespeicherte Kandidat (Platz 6, hier T5)
    rückt nach, MIT korrekter Neu-Nummerierung (Listenposition, nicht Feld —
    die Nummerierung selbst macht card(), s. renderMarket)."""
    acht = [_kandidat("ADBE", zl=281.1331, zh=297.88, inv=237.25)] + \
        [_kandidat(f"T{i}") for i in range(1, 8)]
    ergebnis = _js(f"""
      const market = {{candidates: {json.dumps(acht)}}};
      _liveOutdatedByTicker.set('ADBE', _liveOutdatedStatus(285.75, 281.1331, 297.88, 237.25));
      console.log(JSON.stringify(_effectiveVisible(market).map(c => c.ticker)));
    """)
    assert ergebnis == ["T1", "T2", "T3", "T4", "T5"]
    assert "ADBE" not in ergebnis


def test_reversibilitaet_kurs_erholt_sich_vor_dem_naechsten_lauf():
    """Auftrag Punkt 3: fällt der Live-Kurs des ursprünglichen Kandidaten
    wieder unter die Schwelle, kehrt er automatisch zurück — OHNE eigenen
    Rückweg-Code, einfach weil _effectiveVisible() bei jedem Aufruf neu aus
    market.candidates (unverändert) filtert."""
    acht = [_kandidat("ADBE")] + [_kandidat(f"T{i}") for i in range(1, 8)]
    market_json = json.dumps(acht)
    ergebnis = _js(f"""
      const market = {{candidates: {market_json}}};
      _liveOutdatedByTicker.set('ADBE', _liveOutdatedStatus(285.75, 281.1331, 297.88, 237.25));
      const ausgeschieden = _effectiveVisible(market).map(c => c.ticker);
      _liveOutdatedByTicker.set('ADBE', _liveOutdatedStatus(275, 281.1331, 297.88, 237.25));
      const erholt = _effectiveVisible(market).map(c => c.ticker);
      console.log(JSON.stringify({{ausgeschieden, erholt}}));
    """)
    assert "ADBE" not in ergebnis["ausgeschieden"]
    assert ergebnis["erholt"] == ["ADBE", "T1", "T2", "T3", "T4"]  # wieder Platz 1


def test_mehrfaches_ausscheiden_am_selben_tag_deckt_die_ganze_ersatzbank():
    """Grund für Top-8 statt Top-6 (Backend-Auftrag): auch wenn GLEICHZEITIG
    drei sichtbare Kandidaten ausscheiden, bleibt die sichtbare Liste voll
    besetzt — die Ersatzbank hat genug Tiefe (Platz 6-8)."""
    acht = [_kandidat(f"T{i}") for i in range(8)]
    ergebnis = _js(f"""
      const market = {{candidates: {json.dumps(acht)}}};
      for (const t of ['T0', 'T1', 'T2']) {{
        _liveOutdatedByTicker.set(t, _liveOutdatedStatus(300, 281.1331, 297.88, 237.25));
      }}
      console.log(JSON.stringify(_effectiveVisible(market).map(c => c.ticker)));
    """)
    assert ergebnis == ["T3", "T4", "T5", "T6", "T7"]


def test_invalidierung_scheidet_genauso_aus_wie_zone():
    """#118-Kriterium unverändert übernommen: 'inval' ist der schwerste Fall,
    scheidet also ebenso aus der sichtbaren Liste aus wie 'reached'/'over'."""
    acht = [_kandidat("T0")] + [_kandidat(f"T{i}") for i in range(1, 8)]
    ergebnis = _js(f"""
      const market = {{candidates: {json.dumps(acht)}}};
      _liveOutdatedByTicker.set('T0', _liveOutdatedStatus(200, 281.1331, 297.88, 237.25));
      console.log(JSON.stringify(_effectiveVisible(market).map(c => c.ticker)));
    """)
    assert ergebnis[0] != "T0"
    assert "T0" not in ergebnis


def test_ohne_ersatzbank_bleibt_die_liste_einfach_kuerzer():
    """Regression: kommen (Ausnahmefall, wenig Universum) nur 3 Kandidaten
    insgesamt, scheidet einer aus und es bleiben nur 2 sichtbar — KEIN
    Absturz, keine Erfindung eines Kandidaten aus dem Nichts."""
    drei = [_kandidat(f"T{i}") for i in range(3)]
    ergebnis = _js(f"""
      const market = {{candidates: {json.dumps(drei)}}};
      _liveOutdatedByTicker.set('T0', _liveOutdatedStatus(300, 281.1331, 297.88, 237.25));
      console.log(JSON.stringify(_effectiveVisible(market).map(c => c.ticker)));
    """)
    assert ergebnis == ["T1", "T2"]


# ---------------------------------------------------------------------------
# Mutationsprobe: das Kriterium muss WIRKLICH "Status != null" sein, nicht
# nur "Status == 'reached'"
# ---------------------------------------------------------------------------
def test_mutationsprobe_over_und_inval_scheiden_ebenfalls_aus():
    """Eine Fassung, die nur auf 'reached' statt auf jeden Nicht-null-Status
    prüft, würde 'over'/'inval' fälschlich sichtbar lassen — hier direkt mit
    beiden Zuständen belegt (ergänzt test_invalidierung_scheidet_genauso_aus_
    wie_zone für 'over')."""
    acht = [_kandidat("T0")] + [_kandidat(f"T{i}") for i in range(1, 8)]
    ergebnis = _js(f"""
      const market = {{candidates: {json.dumps(acht)}}};
      _liveOutdatedByTicker.set('T0', _liveOutdatedStatus(300, 281.1331, 297.88, 237.25));
      console.log(JSON.stringify(_effectiveVisible(market).map(c => c.ticker)));
    """)
    assert "T0" not in ergebnis


# ---------------------------------------------------------------------------
# (b) Quellcode-Abgleich — GRENZEN: keine Berührung von Score/Ranking/Filter
# ---------------------------------------------------------------------------
def test_effectivevisible_nutzt_dieselbe_entscheidungsfunktion_wie_118():
    body = _fn("_effectiveVisible")
    assert "_liveOutdatedStatus(" not in body  # liest nur die MAP, rechnet nicht neu
    assert "_liveOutdatedByTicker.get(" in body


def test_neue_funktionen_lesen_keine_score_ranking_felder():
    for name in ("_effectiveVisible", "_maybeReflow", "_benchRow", "_benchHtml"):
        body = _fn(name)
        for verboten in ("score_heuristic", "target_exceeded", "candidates.sort"):
            assert verboten not in body, f"{name} berührt {verboten}"


def test_visible_top_n_stimmt_mit_backend_top_n_ueberein():
    """Struktureller Anker: VISIBLE_TOP_N (Frontend) und config.TOP_N
    (Backend, unverändert 5) müssen dieselbe Zahl sein — sonst zeigt das
    Frontend eine andere Menge als das Backend episode-fähig macht."""
    import sys
    sys.path.insert(0, str(ROOT))
    import config
    assert "const VISIBLE_TOP_N = 5;" in HTML
    assert config.TOP_N == 5


def test_data_live_poll_auf_karte_und_ersatzbank_zeile_vorhanden():
    """Reversibilität braucht Live-Polling auch für ausgeschiedene/nicht
    sichtbare Kandidaten — sonst könnte eine Erholung nie erkannt werden."""
    card_body = _fn("card")
    bench_body = _fn("_benchRow")
    assert "data-live-poll" in card_body
    assert "data-live-poll" in bench_body
    for attr in ("data-zl=", "data-zh=", "data-inv=", "data-market="):
        assert attr in card_body, f"{attr} fehlt in card()"
        assert attr in bench_body, f"{attr} fehlt in _benchRow()"
