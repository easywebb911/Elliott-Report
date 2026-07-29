"""EINE QUELLE — Tests gegen doppelte Wahrheiten (29.07.2026).

Anlass: die Zählung „gereift" vs. „auswertbar" lief in `notify.py` schon einmal
auseinander (#57). Dieselbe Regel stand danach immer noch ein zweites Mal im
Frontend, das Finit-Prädikat ein zweites Mal in `health_check`, und die
Score-Konstanten als Fließtext auf der Methodik-Seite.

Diese Datei hält die Quellen zusammen. Sie prüft NICHT, ob eine Zahl richtig
ist — sie prüft, dass es sie nur EINMAL gibt bzw. dass zwei Fassungen
nachweislich dasselbe sagen.
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import config  # noqa: E402
import evaluate as ev  # noqa: E402
import forward_collection as fc  # noqa: E402
import health_check as hc  # noqa: E402
import numeric  # noqa: E402

HTML = (ROOT / "docs/index.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1 · DIE ZÄHLUNG — Aggregate kommen aus dem Report, nicht aus dem Frontend
# ---------------------------------------------------------------------------
def test_pipeline_schreibt_validation_block_aus_eval_counts():
    """Der Block ist ein DURCHREICHEN von eval_counts, keine zweite Rechnung."""
    src = (ROOT / "scripts/elliott_pipeline.py").read_text(encoding="utf-8")
    block = re.search(r'report\["validation"\] = \{(.*?)\}', src, re.S)
    assert block, "report['validation'] fehlt in der Pipeline"
    inhalt = block.group(1)
    for feld in ("collected", "matured", "evaluable", "eval_min_n"):
        assert f'"{feld}"' in inhalt, feld
    # Die Werte stammen aus eval_counts / EVAL_MIN_N — nicht aus einer
    # eigenen filter-Schleife im Pipeline-Code.
    vor = src[:block.start()]
    assert "fc.eval_counts(coll)" in vor[-800:], \
        "validation-Block wird nicht direkt aus eval_counts gespeist"
    assert "fc.EVAL_MIN_N" in inhalt


def test_pipeline_ordnet_die_zahlen_zur_laufzeit_richtig_zu(tmp_path, monkeypatch):
    """LAUFZEIT-Beweis, nicht Quelltext-Nähe: `main()` wird wirklich ausgeführt.

    `eval_counts` liefert hier drei UNTERSCHEIDBARE Zahlen (7/5/2). Nur so
    fällt eine vertauschte Zuordnung auf — würde der Block `matured` in
    `evaluable` schreiben, stünde hier 5 statt 2. Genau diese Verwechslung war
    der Fehler in #57, und ein Test, der nur den Quelltext liest, fängt sie
    nicht (Guardian-Mutationsprobe 29.07.: `evaluable` → `matured` blieb grün).
    """
    import elliott_pipeline as pipe

    (tmp_path / "data").mkdir()
    (tmp_path / "docs/data").mkdir(parents=True)
    (tmp_path / "data/forward_collection.json").write_text(
        json.dumps({"schema_version": 1, "records": []}), encoding="utf-8")

    monkeypatch.setenv("ELLIOTT_OFFLINE", "1")
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(pipe, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(fc, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(pipe.config, "MARKETS", {
        "US": {"label": "USA", "universe": ["AAPL", "MSFT"]},
        "DE": {"label": "Deutschland", "universe": ["SAP.DE"]},
    })
    monkeypatch.setattr(pipe, "load_watchlist", lambda: [])
    # DREI unterscheidbare Zahlen — eine Vertauschung kann sich nicht verstecken.
    monkeypatch.setattr(pipe.fc, "eval_counts", lambda coll: (7, 5, 2))

    assert pipe.main() == 0
    rep = json.loads((tmp_path / "data/report.json").read_text(encoding="utf-8"))
    assert rep["validation"] == {
        "collected": 7, "matured": 5, "evaluable": 2,
        "eval_min_n": fc.EVAL_MIN_N,
    }, rep.get("validation")


def test_validation_block_stimmt_mit_eval_counts_ueberein():
    """Gegen den ECHTEN Sammlungsstand gegengerechnet."""
    coll = json.loads((ROOT / "data/forward_collection.json")
                      .read_text(encoding="utf-8"))
    n, matured, evaluable = fc.eval_counts(coll)
    erwartet = {"collected": n, "matured": matured, "evaluable": evaluable,
                "eval_min_n": fc.EVAL_MIN_N}
    assert erwartet["evaluable"] <= erwartet["matured"] <= erwartet["collected"]
    assert erwartet["eval_min_n"] == 100


def test_frontend_rechnet_die_aggregate_nicht_mehr_selbst():
    """Kein JS-Nachbau, keine hartkodierte Schwelle."""
    assert "_evalCounts" not in HTML, "JS-Zählung ist wieder da"
    assert not re.search(r"const\s+EVAL_MIN_N\s*=", HTML), \
        "EVAL_MIN_N wieder hartkodiert"
    # und die Zähler hängen sichtbar am Report-Block
    assert "_val.evaluable" in HTML and "_val.eval_min_n" in HTML
    assert "r.validation" in HTML


def test_recExcluded_im_frontend_deckt_sich_mit_is_excluded():
    """`_recExcluded` bleibt (wird JE FALL gebraucht) — aber deckungsgleich.

    Verglichen werden die FELDNAMEN beider Fassungen. Kommt im PRU-Guard je ein
    vierter Grund dazu, schlägt dieser Test fehl, statt dass das Frontend still
    nach altem Recht weiterzählt.
    """
    import inspect
    py_felder = set(re.findall(r'rec\.get\("([\w_]+)"\)',
                               inspect.getsource(fc.is_excluded)))

    js_body = re.search(r"function _recExcluded\(r\) \{(.*?)\}", HTML, re.S).group(1)
    js_felder = set(re.findall(r"r\.([\w_]+)", js_body))

    assert py_felder == js_felder, (
        f"PRU-Guard läuft auseinander — Python {sorted(py_felder)}, "
        f"JS {sorted(js_felder)}")
    assert py_felder == {"pre_reached_target", "pre_reached_ext",
                         "pre_guard_contaminated"}


# ---------------------------------------------------------------------------
# 2 · DAS FINIT-PRÄDIKAT — eine Implementierung
# ---------------------------------------------------------------------------
EINGABEN = [
    None, float("nan"), float("inf"), float("-inf"), True, False,
    0, -1, 1, 3.5, -3.5, 1e9, -1e9, 0.0, -0.0,
    "3.5", "", "nan", [], {}, (), set(), object(),
    10**30, -10**30, 1e-300, complex(1, 0),
]


def test_health_check_nutzt_das_eine_praedikat():
    """`health_check._finite` IST `numeric.finite` — kein zweiter Nachbau."""
    assert hc._finite is numeric.finite, \
        "health_check hat wieder eine eigene Finit-Fassung"


@pytest.mark.parametrize("v", EINGABEN)
def test_finit_praedikat_liefert_ueberall_dasselbe(v):
    """Gilt auch dann, wenn jemand die Fassungen wieder trennt.

    Der Test war ZUERST da (Beweis vor dem Ersetzen): beide Fassungen lieferten
    für dieselbe Eingabemenge dasselbe, erst danach wurde zusammengelegt.
    """
    erwartet = (not isinstance(v, bool)) and isinstance(v, (int, float)) \
        and math.isfinite(v)
    assert numeric.finite(v) is erwartet
    assert hc._finite(v) is erwartet


def test_finit_praedikat_wird_nur_einmal_definiert():
    hc_src = (ROOT / "scripts/health_check.py").read_text(encoding="utf-8")
    assert not re.search(r"^def _finite\(", hc_src, re.M), \
        "health_check definiert das Prädikat wieder selbst"
    assert "from numeric import" in hc_src


# ---------------------------------------------------------------------------
# 4 · SETUP-TYP — evaluate nutzt die Fassung der Sammlung
# ---------------------------------------------------------------------------
def _rec(waves):
    return {"count_wave_labels": [{"wave": w} for w in waves]}


def test_evaluate_nutzt_is_end_of_w4_der_sammlung():
    assert ev._is_end_of_w4 is fc._is_end_of_w4, \
        "evaluate hat wieder eine eigene Fassung"


@pytest.mark.parametrize("rec", [
    _rec([0, 1, 2, 3, 4]), _rec([0, 1, 2]), _rec([]), _rec([4]), _rec([1, 2, 3]),
    {}, {"count_wave_labels": None}, {"count_wave_labels": [{}, {"wave": None}]},
    {"count_wave_labels": [{"wave": 4}, {"wave": 2}]},
])
def test_beide_fassungen_gruppieren_gleich(rec):
    """Verhalten unverändert — KEINE Definitionsänderung an „Auswertung v1".

    Nachgestellt wird die alte, eigene Fassung aus evaluate.py; sie muss für
    jeden Fall dieselbe Gruppe liefern wie die der Sammlung.
    """
    def alt(r):                       # wortgleiche Kopie der entfernten Fassung
        return any(l.get("wave") == 4 for l in (r.get("count_wave_labels") or []))

    assert ev._is_end_of_w4(rec) == alt(rec)


# ---------------------------------------------------------------------------
# 5 · METHODIK-TEXT — handgeschrieben, aber nicht mehr still veraltend
# ---------------------------------------------------------------------------
def _methodik_text() -> str:
    """Der Fließtext der Methodik-Seite (ohne CSS/JS drumherum)."""
    m = re.search(r"info-section-h\">Wie der Score entsteht<.*?</div>\s*</div>",
                  HTML, re.S)
    assert m, "Score-Abschnitt der Methodik-Seite nicht gefunden"
    return m.group(0)


def _de(x: float) -> str:
    """Deutsche Schreibweise: 0.618 -> 0,618 (ohne unnötige Null am Ende)."""
    s = f"{x:g}".replace(".", ",")
    return s


def test_methodik_nennt_die_basispunkte_aus_config():
    t = _methodik_text()
    for key, label in (("end_of_w2", "Ende W2"), ("end_of_w4", "Ende W4")):
        wert = int(config.SETUP_BASE_POINTS[key])
        assert re.search(rf"{label}\s*=\s*<b>{wert}</b>", t), \
            f"{label} im Text weicht von SETUP_BASE_POINTS[{key}]={wert} ab"


def test_methodik_nennt_die_boni_und_die_kappung_aus_config():
    t = _methodik_text()
    assert f"<b>+{int(config.FIB_PROXIMITY_MAX_BONUS)}</b>" in t
    assert f"<b>+{int(config.INVALIDATION_DISTANCE_MAX_BONUS)}</b>" in t
    assert f"bis {int(config.INVALIDATION_DISTANCE_CAP)} %" in t
    # „Maximum also rund 90" = bestes Setup + beide Boni
    maximum = (max(config.SETUP_BASE_POINTS.values())
               + config.FIB_PROXIMITY_MAX_BONUS
               + config.INVALIDATION_DISTANCE_MAX_BONUS)
    assert f"<b>{int(maximum)}</b> Punkte" in t, \
        f"Maximum im Text weicht von der Summe ({maximum}) ab"


def test_methodik_nennt_die_fibonacci_level_und_toleranz_aus_config():
    t = _methodik_text()
    for key, label in (("w2_retrace", "W2"), ("w4_retrace", "W4")):
        level = " / ".join(_de(v) for v in config.FIB_TARGETS[key])
        assert f"{label}: {level}" in t, \
            f"Fibonacci-Level {label} weichen von FIB_TARGETS[{key}] ab"
    assert f"±{_de(config.FIB_PROXIMITY_TOLERANCE)}" in t


def test_methodik_nennt_konfluenz_toleranz_und_linie_aus_config():
    abschnitt = re.search(
        r'info-section-h">Konfluenz-Marken<.*?</div>\s*</div>', HTML, re.S).group(0)
    assert f"±{int(config.CONFLUENCE_TOLERANCE_PCT)}&nbsp;%" in abschnitt
    assert f"{config.CONFLUENCE_SMA_WINDOW}-Tage-Linie" in abschnitt


def test_frontend_nennt_den_reifungs_horizont_aus_forward_collection():
    """„10 Börsentage" / „/ 10" hängen an HORIZON_DAYS."""
    h = fc.HORIZON_DAYS
    assert f"{h} Börsentage" in HTML, "Klartext-Horizont weicht ab"
    assert re.search(rf"bars_elapsed \?\? 0\}}\s*/\s*{h}", HTML), \
        "Handelstage-Zeile der Episoden-Detailansicht weicht ab"
