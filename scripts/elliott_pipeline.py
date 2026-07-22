"""Elliott-Report Pipeline (Skelett, lauffähig, deterministisch, fail-soft).

Ablauf je Markt (US / DE):
  1. Universum aus config.py laden (statische Startlisten).
  2. Kursdaten holen (yfinance, 2 J. Tageskerzen) — fail-soft je Ticker.
  3. ZigZag: bestätigte, alternierende Pivots.
  4. Setup + Regel-Validierung (3 harte Elliott-Regeln als K.o.).
  5. Score (HEURISTISCH, keine Wahrscheinlichkeit) -> Top-N je Markt.
  6. data/report.json schreiben (+ Spiegel nach docs/data/ für GitHub Pages).

Determinismus: gleicher Input -> gleiches JSON (einzige Ausnahme:
run_timestamp_utc). Kein random, keine impliziten Zeit-/Zufallsquellen im
Kern; der Zeitstempel wird von außen hereingereicht.

Offline-/Dev-Modus: Mit Umgebungsvariable ELLIOTT_OFFLINE=1 nutzt die Pipeline
einen deterministischen synthetischen Kurs-Generator statt yfinance. Das dient
NUR der Entwicklung/Demonstration und ist klar als solches markiert.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

# Robuste Imports unabhängig vom Arbeitsverzeichnis:
# config.py liegt im Repo-Root, rules.py/zigzag.py in scripts/.
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
for _p in (str(_ROOT), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import config  # noqa: E402
from rules import validate_partial_to_w4  # noqa: E402
from zigzag import Pivot, zigzag  # noqa: E402

# Ein Fetcher liefert (dates, closes) oder None (fail-soft).
Fetcher = Callable[[str], Optional[Tuple[List[str], List[float]]]]

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# 2) KURSDATEN
# ---------------------------------------------------------------------------
def fetch_yfinance(ticker: str) -> Optional[Tuple[List[str], List[float]]]:
    """Holt Tageskerzen via yfinance. Fail-soft: None bei jedem Problem.

    yfinance wird bewusst LAZY importiert, damit Tests und Offline-Läufe die
    Bibliothek (und das Netz) nicht benötigen.
    """
    try:
        import yfinance as yf  # noqa: WPS433 (lazy import gewollt)

        df = yf.download(
            ticker,
            period=config.DATA_PERIOD,
            interval=config.DATA_INTERVAL,
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        if df is None or df.empty or "Close" not in df:
            return None
        closes = [float(x) for x in df["Close"].dropna().tolist()]
        dates = [d.strftime("%Y-%m-%d") for d in df.index.to_pydatetime()]
        dates = dates[: len(closes)]
        if len(closes) < config.MIN_BARS:
            return None
        return dates, closes
    except Exception:  # noqa: BLE001 — fail-soft ist hier Absicht
        return None


def fetch_synthetic(ticker: str) -> Optional[Tuple[List[str], List[float]]]:
    """Deterministischer Ersatz-Fetcher (NUR Dev/Demo, kein Netz).

    Erzeugt eine saubere W1-W2-Struktur (Long-Setup am Ende W2), damit die
    Pipeline end-to-end nachweisbar Kandidaten produziert. Variation je Ticker
    über einen stabilen Seed -> reproduzierbar, aber unterschiedliche Scores.
    """
    seed = sum(ord(c) for c in ticker)
    base = 90.0 + (seed % 20)
    w1 = 18.0 + (seed % 7) * 2.0
    # Deterministische Auswahl des W2-Retracements (spreizt die Fib-Nähe/Scores).
    retrace_options = [0.5, 0.618, 0.382, 0.66, 0.45, 0.55, 0.618]
    retrace = retrace_options[seed % len(retrace_options)]

    a_start = base + w1 * 0.6  # Ausgangspunkt oberhalb von A0 (P0 wird Tief)
    a0 = base                  # P0 (Tief)
    a1 = base + w1             # P1 (Hoch)
    a2 = a1 - retrace * w1     # P2 (Tief, W2-Retracement)
    a3_partial = a2 + 0.35 * w1  # Beginn W3, bleibt unter A1 (kein neuer Pivot)

    w = config.ZIGZAG_WINDOW
    # Segmentlängen so wählen, dass jeder Anker sein Fenster dominiert.
    seg = [
        (a_start, a0, w + 2),   # Abstieg in P0
        (a0, a1, w + 4),        # W1 hoch
        (a1, a2, w + 3),        # W2 runter
        (a2, a3_partial, w + 2),  # Beginn W3 (bestätigt P2)
    ]

    closes: List[float] = []
    for start, end, n in seg:
        # n Schritte, exklusive Startpunkt (außer beim allerersten Segment).
        rng = range(n + 1) if not closes else range(1, n + 1)
        for k in rng:
            closes.append(start + (end - start) * (k / n))

    dates = _synthetic_dates(len(closes))
    return dates, closes


def _synthetic_dates(n: int) -> List[str]:
    """Deterministische, aufsteigende Pseudo-Datumsstrings (kein 'today')."""
    # Fester Anker, damit Läufe reproduzierbar sind (kein Date.now()).
    from datetime import date, timedelta

    anchor = date(2024, 1, 1)
    return [(anchor + timedelta(days=i)).isoformat() for i in range(n)]


def get_fetcher() -> Fetcher:
    """Wählt Fetcher nach Umgebungsvariable (Default: yfinance)."""
    if os.environ.get("ELLIOTT_OFFLINE") == "1":
        return fetch_synthetic
    return fetch_yfinance


# ---------------------------------------------------------------------------
# 4) SETUP-ERKENNUNG + REGEL-VALIDIERUNG
# ---------------------------------------------------------------------------
def _fib_proximity_bonus(retrace: float, targets: Sequence[float]) -> float:
    """Weicher Bonus je näher `retrace` an einem Schlüssel-Fib liegt."""
    tol = config.FIB_PROXIMITY_TOLERANCE
    best = 0.0
    for t in targets:
        closeness = 1.0 - abs(retrace - t) / tol
        best = max(best, closeness)
    best = max(0.0, min(1.0, best))
    return best * config.FIB_PROXIMITY_MAX_BONUS


def _invalidation_bonus(close: float, invalidation: float) -> float:
    """Bonus nach prozentualem Abstand des Kurses zum K.o.-Level."""
    if close <= 0:
        return 0.0
    dist_pct = abs(close - invalidation) / close * 100.0
    frac = min(dist_pct / config.INVALIDATION_DISTANCE_CAP, 1.0)
    return frac * config.INVALIDATION_DISTANCE_MAX_BONUS


def _target_zone(base: float, direction: int, w1_len: float, ext: Sequence[float]) -> Dict[str, float]:
    a = base + direction * ext[0] * w1_len
    b = base + direction * ext[1] * w1_len
    return {"low": round(min(a, b), 4), "high": round(max(a, b), 4)}


def classify_setup(pivots: List[Pivot], close: float) -> Optional[Dict]:
    """Ermittelt das aktuelle Setup aus den jüngsten Pivots.

    Priorität: end_of_w4 (mehr bestätigte Struktur) vor end_of_w2.
    Gibt None zurück, wenn kein sauberes, regelkonformes Setup vorliegt.
    """
    prices = [p.price for p in pivots]

    # --- end_of_w4: die letzten 5 Pivots als Teil-Impuls P0..P4 ---
    if len(prices) >= 5:
        pts = prices[-5:]
        res = validate_partial_to_w4(pts)
        if res.is_valid:
            p0, p1, p2, p3, p4 = pts
            direction = res.direction
            w1_len = abs(p1 - p0)
            w3_len = abs(p3 - p2)
            retrace_w4 = abs(p4 - p3) / w3_len if w3_len else 0.0
            fib = _fib_proximity_bonus(retrace_w4, config.FIB_TARGETS["w4_retrace"])
            invalid = p1  # W4 darf W1 nicht überlappen
            inval_bonus = _invalidation_bonus(close, invalid)
            base_pts = config.SETUP_BASE_POINTS["end_of_w4"]
            side = "Long" if direction > 0 else "Short"
            return {
                "setup": "end_of_w4",
                "direction": direction,
                "count_label": f"Impuls 1–5 · {side}-Setup am Ende W4 (W5 erwartet)",
                "invalidation_price": round(invalid, 4),
                "target_zone": _target_zone(p4, direction, w1_len, config.TARGET_EXTENSIONS["w5"]),
                "base_points": base_pts,
                "fib_bonus": fib,
                "inval_bonus": inval_bonus,
            }

    # --- end_of_w2: die letzten 3 Pivots P0..P2 ---
    if len(prices) >= 3:
        p0, p1, p2 = prices[-3:]
        direction = 1 if p1 >= p0 else -1
        # Regel 1 (W2 <= 100 %): normalisiert P2 nicht jenseits von P0.
        norm_p0, norm_p2 = direction * p0, direction * p2
        if norm_p2 >= norm_p0:
            w1_len = abs(p1 - p0)
            retrace_w2 = abs(p2 - p1) / w1_len if w1_len else 0.0
            # Nur plausible Retracements (0 < r <= 1) als Setup werten.
            if 0.0 < retrace_w2 <= 1.0:
                fib = _fib_proximity_bonus(retrace_w2, config.FIB_TARGETS["w2_retrace"])
                invalid = p0  # W2 darf W1 nicht > 100 % retracen
                inval_bonus = _invalidation_bonus(close, invalid)
                base_pts = config.SETUP_BASE_POINTS["end_of_w2"]
                side = "Long" if direction > 0 else "Short"
                return {
                    "setup": "end_of_w2",
                    "direction": direction,
                    "count_label": f"Impuls 1–5 · {side}-Setup am Ende W2 (W3 erwartet)",
                    "invalidation_price": round(invalid, 4),
                    "target_zone": _target_zone(p2, direction, w1_len, config.TARGET_EXTENSIONS["w3"]),
                    "base_points": base_pts,
                    "fib_bonus": fib,
                    "inval_bonus": inval_bonus,
                }

    return None


def score_setup(setup: Dict) -> float:
    """Setzt den heuristischen Score aus den drei Komponenten zusammen."""
    w = config.SCORE_WEIGHTS
    score = (
        setup["base_points"] * w["setup_base"]
        + setup["fib_bonus"] * w["fib_proximity"]
        + setup["inval_bonus"] * w["invalidation_distance"]
    )
    return round(score, 2)


# ---------------------------------------------------------------------------
# 5/6) REPORT-AUFBAU
# ---------------------------------------------------------------------------
def _company_name(ticker: str) -> str:
    # Skelett: Klartext-Name folgt später (z. B. yfinance longName).
    # Bis dahin bewusst = Ticker, damit das Schema stabil bleibt.
    return ticker


def build_candidate(ticker: str, dates: List[str], closes: List[float]) -> Optional[Dict]:
    """Baut einen Kandidaten-Eintrag oder None (kein valides Setup)."""
    pivots = zigzag(closes, config.ZIGZAG_WINDOW, dates)
    if len(pivots) < 3:
        return None
    close = closes[-1]
    setup = classify_setup(pivots, close)
    if setup is None:
        return None

    chart_points = [p.as_dict() for p in pivots[-12:]]
    return {
        "ticker": ticker,
        "name": _company_name(ticker),
        "close": round(close, 4),
        "count_label": setup["count_label"],
        "invalidation_price": setup["invalidation_price"],
        "target_zone": setup["target_zone"],
        "score_heuristic": score_setup(setup),
        "chart_points": chart_points,
        "status": config.CARD_STATUS,
    }


def build_market(market_key: str, fetcher: Fetcher) -> Dict:
    """Verarbeitet ein Marktuniversum (fail-soft je Ticker)."""
    cfg = config.MARKETS[market_key]
    universe = cfg["universe"]
    candidates: List[Dict] = []
    skipped = 0

    for ticker in universe:
        try:
            data = fetcher(ticker)
        except Exception:  # noqa: BLE001 — fail-soft
            data = None
        if data is None:
            skipped += 1
            continue
        dates, closes = data
        entry = build_candidate(ticker, dates, closes)
        if entry is None:
            skipped += 1
            continue
        candidates.append(entry)

    # Deterministische Sortierung: Score desc, dann Ticker asc.
    candidates.sort(key=lambda e: (-e["score_heuristic"], e["ticker"]))
    top = candidates[: config.TOP_N]

    return {
        "label": cfg["label"],
        "universe_size": len(universe),
        "evaluated": len(universe),
        "skipped": skipped,
        "candidates_found": len(candidates),
        "candidates": top,
    }


def build_report(fetcher: Fetcher, run_timestamp_utc: str) -> Dict:
    """Baut das komplette Report-Objekt (deterministisch bei festem Input)."""
    markets: Dict[str, Dict] = {}
    for key in config.MARKETS:
        markets[key] = build_market(key, fetcher)
    return {
        "schema_version": config.SCHEMA_VERSION,
        "run_timestamp_utc": run_timestamp_utc,
        "generator": "elliott_pipeline",
        "disclaimer": "Heuristische Elliott-Wellen-Auszählung, unvalidiert. Keine Anlageberatung.",
        "markets": markets,
    }


def write_report(report: Dict) -> List[Path]:
    """Schreibt den Report kanonisch + gespiegelt (Pages /docs)."""
    written: List[Path] = []
    for rel in (config.REPORT_PATH, config.REPORT_PATH_PUBLISHED):
        path = REPO_ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        written.append(path)
    return written


def main() -> int:
    fetcher = get_fetcher()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = build_report(fetcher, ts)
    written = write_report(report)

    us = report["markets"]["US"]
    de = report["markets"]["DE"]
    mode = "OFFLINE/synthetisch" if fetcher is fetch_synthetic else "yfinance"
    print(f"[elliott] Modus: {mode}")
    print(
        f"[elliott] US: {us['candidates_found']} Kandidaten "
        f"({us['skipped']} übersprungen von {us['universe_size']})"
    )
    print(
        f"[elliott] DE: {de['candidates_found']} Kandidaten "
        f"({de['skipped']} übersprungen von {de['universe_size']})"
    )
    for p in written:
        print(f"[elliott] geschrieben: {p.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
