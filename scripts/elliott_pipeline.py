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
import time
import traceback
from dataclasses import dataclass
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
import forward_collection as fc  # noqa: E402
import notify  # noqa: E402 — Score-Alert-Push (fail-soft, no-op ohne NTFY_TOPIC)
from rules import validate_partial_to_w4  # noqa: E402
from zigzag import Pivot, zigzag  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# DIAGNOSE-INSTRUMENTIERUNG (reines Logging — KEINE Logik-/Schema-Änderung)
# ---------------------------------------------------------------------------
# Die möglichen Skip-Gründe. Sie klassifizieren nur, warum ein Ticker ohnehin
# übersprungen wird; die Skip-ENTSCHEIDUNG selbst ist ansonsten unverändert.
FETCH_ERROR = "fetch_error"        # Exception beim Abruf (yfinance/Netz/Import)
EMPTY_DATA = "empty_data"          # Abruf ok, aber keine/zu wenige Kursdaten
TOO_FEW_PIVOTS = "too_few_pivots"  # ZigZag liefert < 3 Pivots
NO_VALID_COUNT = "no_valid_count"  # kein regelkonformes Setup gefunden
# Long-only-Report: Short-Setups (Abwärts-Erwartung) werden vor dem Ranking
# verworfen. Eigener Grund, damit im Diag-Log sichtbar bleibt, wie viele
# Shorts aussortiert wurden. Die Richtungs-ERKENNUNG ist unverändert.
SHORT_SETUP_EXCLUDED = "short_setup_excluded"
SKIP_REASONS = (
    FETCH_ERROR, EMPTY_DATA, TOO_FEW_PIVOTS, NO_VALID_COUNT, SHORT_SETUP_EXCLUDED,
)


@dataclass
class FetchOutcome:
    """Ergebnis eines Abrufs. Trägt bei Misserfolg den Grund + ein Detail.

    Das Detail dient NUR dem Log (Traceback bzw. Datenform). Es beeinflusst
    weder Report noch die Skip-Entscheidung.
    """

    data: Optional[Tuple[List[str], List[float]]] = None
    reason: Optional[str] = None
    detail: str = ""


# Ein Fetcher liefert ein FetchOutcome (Daten ODER Skip-Grund + Detail).
Fetcher = Callable[[str], FetchOutcome]


def _log(msg: str) -> None:
    """Einheitliche, sofort sichtbare Log-Ausgabe (stdout, für Actions-Log)."""
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# 2) KURSDATEN
# ---------------------------------------------------------------------------
def fetch_yfinance(ticker: str) -> FetchOutcome:
    """Holt Tageskerzen via yfinance. Fail-soft: Skip-Grund statt Absturz.

    yfinance wird bewusst LAZY importiert, damit Tests und Offline-Läufe die
    Bibliothek (und das Netz) nicht benötigen. Die Skip-ENTSCHEIDUNGEN sind
    identisch zu vorher; nur der GRUND (+ Detail fürs Log) wird jetzt
    mitgeliefert.
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
        # Verarbeitung (inkl. Spalten-Normalisierung) zentral + testbar.
        return parse_download_df(df)
    except Exception as exc:  # noqa: BLE001 — fail-soft ist hier Absicht
        return FetchOutcome(
            reason=FETCH_ERROR,
            detail=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
        )


def fetch_yfinance_weekly(ticker: str) -> FetchOutcome:
    """Wie fetch_yfinance, aber Wochenkerzen über lange Historie (großer Grad).

    Nutzt DIESELBE parse_download_df — die yfinance-Wochenform ist spaltengleich
    zur Tagesform (MultiIndex je Ticker), daher ist die MultiIndex-Lesson
    bereits abgedeckt. Fail-soft wie gehabt.
    """
    try:
        import yfinance as yf  # noqa: WPS433

        df = yf.download(
            ticker,
            period=config.DATA_PERIOD_WEEKLY,
            interval=config.DATA_INTERVAL_WEEKLY,
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        return parse_download_df(df)
    except Exception as exc:  # noqa: BLE001 — fail-soft
        return FetchOutcome(
            reason=FETCH_ERROR,
            detail=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
        )


def fetch_yfinance_monthly(ticker: str) -> FetchOutcome:
    """Wie fetch_yfinance, aber MONATSKERZEN über die volle Historie (Monatsgrad).

    NUR für Watchlist-Titel. Nutzt DIESELBE parse_download_df (MultiIndex-Lesson
    geerbt), mit der HÖHEREN Monats-Schwelle config.MIN_BARS_MONTHLY: junge Titel
    mit < 5 Jahren Historie liefern keinen Monats-Count (fail-soft -> null).
    """
    try:
        import yfinance as yf  # noqa: WPS433

        df = yf.download(
            ticker,
            period=config.DATA_PERIOD_MONTHLY,
            interval=config.DATA_INTERVAL_MONTHLY,
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        return parse_download_df(df, config.MIN_BARS_MONTHLY)
    except Exception as exc:  # noqa: BLE001 — fail-soft
        return FetchOutcome(
            reason=FETCH_ERROR,
            detail=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
        )


def _normalize_columns(df):
    """Reduziert MultiIndex-Spalten robust auf Ebene 0.

    yfinance liefert je nach Version FLACHE oder MULTIINDEX-Spalten — z. B.
    ``[('Close','AAPL'), ('High','AAPL'), ...]`` AUCH bei Einzel-Tickern
    (so ab 0.2.5x). Ohne Reduktion trifft ``df["Close"]`` dann ein
    Sub-DataFrame statt einer Series -> ``.tolist()`` wirft AttributeError.

    Diese EINE zentrale Normalisierung fängt BEIDE Formen ab (per
    ``get_level_values(0)``, mehrstufen-robust) und macht alle späteren
    Spalten-Zugriffe (Close/High/Low/Open/Volume) versionsunabhängig.
    """
    if getattr(df.columns, "nlevels", 1) > 1:
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    return df


def parse_download_df(df, min_bars: Optional[int] = None) -> FetchOutcome:
    """Wandelt einen yfinance-Download in ein FetchOutcome um.

    Netz-/versionsunabhängig und damit unit-testbar (synthetischer DataFrame).
    Einzige Stelle für Spalten-Normalisierung + Skip-Grund-Klassifizierung.
    Die Skip-ENTSCHEIDUNGEN sind identisch zu vorher.

    min_bars: Mindest-Kerzenzahl; None -> config.MIN_BARS (Tag/Woche, unverändert).
    Der Monats-Fetcher reicht die höhere Monats-Schwelle herein.
    """
    mb = config.MIN_BARS if min_bars is None else min_bars
    if df is None or getattr(df, "empty", True):
        shape = getattr(df, "shape", None)
        cols = list(getattr(df, "columns", []))
        return FetchOutcome(
            reason=EMPTY_DATA,
            detail=f"df leer/None; shape={shape}, columns={cols}",
        )

    df = _normalize_columns(df)
    if "Close" not in df.columns:
        return FetchOutcome(
            reason=EMPTY_DATA,
            detail=f"keine 'Close'-Spalte; columns={list(df.columns)}",
        )

    closes = [float(x) for x in df["Close"].dropna().tolist()]
    dates = [d.strftime("%Y-%m-%d") for d in df.index.to_pydatetime()]
    dates = dates[: len(closes)]
    if len(closes) < mb:
        return FetchOutcome(
            reason=EMPTY_DATA,
            detail=(
                f"zu wenige Kerzen: {len(closes)} < min_bars={mb}; "
                f"shape={df.shape}, columns={list(df.columns)}"
            ),
        )
    return FetchOutcome(data=(dates, closes))


def fetch_synthetic(ticker: str) -> FetchOutcome:
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
    return FetchOutcome(data=(dates, closes))


def _synthetic_dates(n: int) -> List[str]:
    """Deterministische, aufsteigende Pseudo-Datumsstrings (kein 'today')."""
    # Fester Anker, damit Läufe reproduzierbar sind (kein Date.now()).
    from datetime import date, timedelta

    anchor = date(2024, 1, 1)
    return [(anchor + timedelta(days=i)).isoformat() for i in range(n)]


def _synthetic_weekly_dates(n: int) -> List[str]:
    """Wöchentlich gespaced (kein 'today'), damit die Wochen-Ebene realistisch
    aussieht (Wellen-Beine über Monate)."""
    from datetime import date, timedelta

    anchor = date(2016, 1, 4)  # Montag
    return [(anchor + timedelta(weeks=i)).isoformat() for i in range(n)]


def fetch_synthetic_weekly(ticker: str) -> FetchOutcome:
    """Deterministischer Wochen-Ersatz (NUR Dev/Demo). Erzeugt einen sauberen
    W1–W4-Impuls (end_of_w4) über die Wochen-Ebene, damit die zweite Zählung
    (großer Grad) nachweisbar erscheint. Variation je Ticker über Seed.
    """
    seed = sum(ord(c) for c in ticker)
    base = 80.0 + (seed % 25)
    w1 = 22.0 + (seed % 6) * 3.0
    retr2 = [0.5, 0.618, 0.382][seed % 3]
    w3 = w1 * (1.6 + (seed % 4) * 0.1)         # W3 > W1 (nicht kürzeste)
    retr4 = [0.382, 0.5][seed % 2]

    a_start = base + w1 * 0.6
    a0 = base
    a1 = base + w1
    a2 = a1 - retr2 * w1                        # P2 (W2-Tief, > P0)
    a3 = a2 + w3                                # P3 (W3-Hoch, > P1)
    a4 = a3 - retr4 * w3                        # P4 (W4-Tief, > P1)
    a5_partial = a4 + 0.30 * w3                 # Beginn W5, bestätigt P4

    w = config.ZIGZAG_WINDOW
    seg = [
        (a_start, a0, w + 2),
        (a0, a1, w + 4),
        (a1, a2, w + 3),
        (a2, a3, w + 4),
        (a3, a4, w + 3),
        (a4, a5_partial, w + 2),
    ]
    closes: List[float] = []
    for start, end, n in seg:
        rng = range(n + 1) if not closes else range(1, n + 1)
        for k in rng:
            closes.append(start + (end - start) * (k / n))

    return FetchOutcome(data=(_synthetic_weekly_dates(len(closes)), closes))


def _synthetic_monthly_dates(n: int) -> List[str]:
    """Monatlich gespaced (kein 'today'), Anker 2010-01 -> die Pivots liegen
    Jahre auseinander (die großen, mehrjährigen Züge)."""
    from datetime import date

    out: List[str] = []
    y, m = 2010, 1
    for _ in range(n):
        out.append(date(y, m, 1).isoformat())
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def fetch_synthetic_monthly(ticker: str) -> FetchOutcome:
    """Deterministischer Monats-Ersatz (NUR Dev/Demo). Sauberer W1–W4-Impuls
    (end_of_w4) über die Monats-Ebene, damit der Monatsgrad offline nachweisbar
    erscheint. Variation je Ticker über Seed. Umgeht die MIN_BARS_MONTHLY-Schwelle
    bewusst (die gilt nur dem echten Netz-Abruf via parse_download_df)."""
    seed = sum(ord(c) for c in ticker)
    base = 60.0 + (seed % 30)
    w1 = 25.0 + (seed % 6) * 4.0
    retr2 = [0.5, 0.618, 0.382][seed % 3]
    w3 = w1 * (1.6 + (seed % 4) * 0.15)        # W3 > W1 (nicht kürzeste)
    retr4 = [0.382, 0.5][seed % 2]

    a_start = base + w1 * 0.6
    a0 = base
    a1 = base + w1
    a2 = a1 - retr2 * w1
    a3 = a2 + w3
    a4 = a3 - retr4 * w3
    a5_partial = a4 + 0.30 * w3

    w = config.ZIGZAG_WINDOW
    seg = [
        (a_start, a0, w + 2),
        (a0, a1, w + 4),
        (a1, a2, w + 3),
        (a2, a3, w + 4),
        (a3, a4, w + 3),
        (a4, a5_partial, w + 2),
    ]
    closes: List[float] = []
    for start, end, n in seg:
        rng = range(n + 1) if not closes else range(1, n + 1)
        for k in rng:
            closes.append(start + (end - start) * (k / n))

    return FetchOutcome(data=(_synthetic_monthly_dates(len(closes)), closes))


def get_fetcher() -> Fetcher:
    """Wählt Fetcher nach Umgebungsvariable (Default: yfinance)."""
    if os.environ.get("ELLIOTT_OFFLINE") == "1":
        return fetch_synthetic
    return fetch_yfinance


def get_weekly_fetcher() -> Fetcher:
    """Wochen-Fetcher für den großen Grad (passend zum Modus)."""
    if os.environ.get("ELLIOTT_OFFLINE") == "1":
        return fetch_synthetic_weekly
    return fetch_yfinance_weekly


def get_monthly_fetcher() -> Fetcher:
    """Monats-Fetcher für den Monatsgrad (NUR Watchlist; passend zum Modus)."""
    if os.environ.get("ELLIOTT_OFFLINE") == "1":
        return fetch_synthetic_monthly
    return fetch_yfinance_monthly


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
            # Extension-Zielzone (additiv): W5 gemessen an der Netto-Strecke
            # P0->P3 (nicht an W1), ab P4. _target_zone sichert die min/max-
            # Ordnung auch bei degenerierten Fällen (winzige Strecke etc.).
            net_len = abs(p3 - p0)
            return {
                "setup": "end_of_w4",
                "direction": direction,
                "count_label": f"Impuls 1–5 · {side}-Setup am Ende W4 (W5 erwartet)",
                "invalidation_price": round(invalid, 4),
                "target_zone": _target_zone(p4, direction, w1_len, config.TARGET_EXTENSIONS["w5"]),
                "target_zone_extended": _target_zone(p4, direction, net_len, config.TARGET_EXTENSIONS["w5_ext"]),
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
                    "target_zone_extended": _target_zone(p2, direction, w1_len, config.TARGET_EXTENSIONS["w3_ext"]),
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
    # Bestehendes Feld "name" bleibt unverändert = Ticker (Schema-Stabilität).
    # Der Klartext-Name kommt additiv über "company_name" (s. _meta_name).
    return ticker


_TICKER_META_CACHE: Optional[Dict[str, Dict]] = None


def _load_ticker_meta() -> Dict[str, Dict]:
    """Lädt die kuratierte Ticker-Metadaten-Map einmalig. Fail-soft: {}."""
    global _TICKER_META_CACHE
    if _TICKER_META_CACHE is None:
        try:
            path = REPO_ROOT / config.TICKER_META_PATH
            with path.open(encoding="utf-8") as fh:
                _TICKER_META_CACHE = json.load(fh)
        except Exception:  # noqa: BLE001 — fail-soft (Datei fehlt/kaputt)
            _TICKER_META_CACHE = {}
    return _TICKER_META_CACHE


def _meta_name(ticker: str) -> str:
    """Klartext-Firmenname aus der Mapping-Datei; fail-soft -> Ticker."""
    entry = _load_ticker_meta().get(ticker) or {}
    return entry.get("name") or ticker


def _meta_sector(ticker: str) -> str:
    """Sektor aus der Mapping-Datei; fail-soft -> leer."""
    entry = _load_ticker_meta().get(ticker) or {}
    return entry.get("sector") or ""


def _count_from_series(dates: Sequence[str], closes: Sequence[float]) -> Optional[Dict]:
    """Long-Count (4 Anzeige-Felder) aus EINER fertigen Kursreihe — reine Logik,
    kein Netz. Reuse der bestehenden ZigZag-/Regel-/Zielzonen-Mechanik inkl.
    target_zone_extended. Long-only: Short-Counts -> None. Zu wenig Daten/keine
    saubere Struktur -> None (fail-soft). Basis für Tag/Woche/Monat."""
    if not closes or len(closes) < 2:
        return None
    pivots = zigzag(list(closes), config.ZIGZAG_WINDOW, list(dates))
    if len(pivots) < 3:
        return None
    setup = classify_setup(pivots, closes[-1])
    if setup is None or setup["direction"] < 0:
        return None
    return {
        "count_label": setup["count_label"],
        "invalidation_price": setup["invalidation_price"],
        "target_zone": setup["target_zone"],
        "target_zone_extended": setup["target_zone_extended"],
    }


def _count_from_fetch(ticker: str, fetcher: Optional[Fetcher]) -> Optional[Dict]:
    """Holt EINE Kursreihe über ``fetcher`` und zählt sie aus (fail-soft: kein
    Fetcher / kein Netz / Fehler / keine Daten -> None). Fetcher-agnostisch —
    dieselbe Funktion trägt Wochen- (großer Grad) UND Monatsgrad."""
    if fetcher is None:
        return None
    try:
        outcome = fetcher(ticker)
    except Exception:  # noqa: BLE001 — fail-soft
        return None
    if outcome is None or outcome.data is None:
        return None
    dates, closes = outcome.data
    return _count_from_series(dates, closes)


def higher_degree_for(ticker: str, weekly_fetcher: Optional[Fetcher]) -> Optional[Dict]:
    """Zweite Zählung auf WOCHEN-Basis (großer Grad) für EINEN Ticker.

    Unverändertes Verhalten (Delegation an die geteilten Helfer). Wird für die
    finalen Top-5 je Markt UND für Watchlist-Titel (dort als timeframes.week)
    genutzt. Fail-soft -> None.
    """
    return _count_from_fetch(ticker, weekly_fetcher)


def build_candidate(
    ticker: str, dates: List[str], closes: List[float]
) -> Tuple[Optional[Dict], Optional[str], str]:
    """Baut einen Kandidaten-Eintrag.

    Returns (entry, reason, detail):
      - Erfolg -> (entry, None, "")
      - Skip   -> (None, reason, detail-fürs-Log)
    Die Entscheidungslogik ist unverändert; es wird nur der Grund + ein
    Detail fürs Log ergänzt.
    """
    pivots = zigzag(closes, config.ZIGZAG_WINDOW, dates)
    if len(pivots) < 3:
        return None, TOO_FEW_PIVOTS, f"pivots={len(pivots)} (< 3), bars={len(closes)}"
    close = closes[-1]
    setup = classify_setup(pivots, close)
    if setup is None:
        return (
            None,
            NO_VALID_COUNT,
            f"pivots={len(pivots)}, kein regelkonformes Setup (W2/W4)",
        )

    # Long-only: Short-Setups (Abwärts-Erwartung, direction < 0) VOR dem
    # Ranking verwerfen, damit sie keine Longs aus den Top 5 verdrängen.
    # Die Richtungs-Erkennung in classify_setup bleibt unangetastet — hier
    # wird nur gefiltert.
    if setup["direction"] < 0:
        return (
            None,
            SHORT_SETUP_EXCLUDED,
            f"{setup['setup']} short (direction={setup['direction']}): "
            f"{setup['count_label']}",
        )

    chart_points = [p.as_dict() for p in pivots[-12:]]
    # Wellen-Ziffern für die Sparkline (additiv): die GEZÄHLTE Struktur sind
    # die letzten k Pivots (end_of_w4 -> 5 Pivots P0..P4, sonst 3 Pivots
    # P0..P2). index bezieht sich auf chart_points; wave 0 = P0-Start.
    k = 5 if setup["setup"] == "end_of_w4" else 3
    ncp = len(chart_points)
    count_wave_labels = [{"index": ncp - k + j, "wave": j} for j in range(k)]
    # Tagesveränderung aus den letzten ZWEI bereits geladenen Schlusskursen —
    # KEIN zusätzlicher API-Call, kein Live-Polling.
    prev_close = closes[-2] if len(closes) >= 2 else close
    change_abs = round(close - prev_close, 4)
    change_pct = round((close / prev_close - 1.0) * 100.0, 4) if prev_close else 0.0
    entry = {
        "ticker": ticker,
        "name": _company_name(ticker),
        # Additive Header-Felder (kuratierte Meta + Tagesveränderung).
        "company_name": _meta_name(ticker),
        "sector": _meta_sector(ticker),
        "change_abs": change_abs,
        "change_pct": change_pct,
        "close": round(close, 4),
        # Additiv: immer "long" (Short-Setups sind bereits ausgefiltert). Eine
        # spätere Wiedereinführung von Shorts wäre so kein Schema-Bruch.
        "direction": "long",
        "count_label": setup["count_label"],
        "invalidation_price": setup["invalidation_price"],
        "target_zone": setup["target_zone"],
        "target_zone_extended": setup["target_zone_extended"],
        "score_heuristic": score_setup(setup),
        "chart_points": chart_points,
        "count_wave_labels": count_wave_labels,
        "status": config.CARD_STATUS,
    }
    return entry, None, ""


def _scan_market(
    universe: Sequence[str], fetcher: Fetcher,
    price_sink: Optional[Dict[str, Tuple[List[str], List[float]]]] = None,
) -> Tuple[List[Dict], Dict[str, int], List[Tuple[str, str, str]], List[Tuple[str, str]]]:
    """Verarbeitet ein Universum (fail-soft je Ticker) — ohne I/O/Logging.

    Ausgelagert aus build_market, damit die Skip-Zähler (inkl.
    short_setup_excluded) direkt unit-testbar sind. Verhalten identisch.

    Returns:
        (candidates, reason_counts, first_samples, dead_tickers)
        candidates: unsortierte Long-Kandidaten
        reason_counts: Zähler je Skip-Grund (SKIP_REASONS)
        first_samples: erste 3 Skips (ticker, reason, detail) fürs Log
        dead_tickers: (ticker, reason) für JEDEN empty_data/fetch_error —
            Listen-Hygiene: benennt tote/fehlerhafte Symbole namentlich.
    """
    candidates: List[Dict] = []
    reason_counts: Dict[str, int] = {r: 0 for r in SKIP_REASONS}
    first_samples: List[Tuple[str, str, str]] = []  # (ticker, reason, detail)
    dead_tickers: List[Tuple[str, str]] = []         # (ticker, reason) hygiene
    MAX_SAMPLES = 3

    def _record_skip(tk: str, reason: str, detail: str) -> None:
        reason_counts[reason] += 1
        if len(first_samples) < MAX_SAMPLES:
            first_samples.append((tk, reason, detail))
        if reason in (EMPTY_DATA, FETCH_ERROR):
            dead_tickers.append((tk, reason))

    for ticker in universe:
        # Sicherheitsnetz: ein Fetcher soll ein FetchOutcome liefern, aber
        # falls er doch wirft, als fetch_error klassifizieren (kein Absturz).
        try:
            outcome = fetcher(ticker)
        except Exception as exc:  # noqa: BLE001 — fail-soft
            _record_skip(
                ticker, FETCH_ERROR,
                f"Fetcher warf: {type(exc).__name__}: {exc}\n{traceback.format_exc()}",
            )
            continue

        if outcome.data is None:
            _record_skip(ticker, outcome.reason or FETCH_ERROR, outcome.detail)
            continue

        dates, closes = outcome.data
        # Kursdaten für die Forward-Sammlung mitnehmen (kein Re-Fetch): ALLE
        # erfolgreich geladenen Ticker, damit auch aus Top-5 gefallene Records
        # ausreifen können.
        if price_sink is not None:
            price_sink[ticker] = (dates, closes)
        entry, reason, detail = build_candidate(ticker, dates, closes)
        if entry is None:
            _record_skip(ticker, reason or NO_VALID_COUNT, detail)
            continue
        candidates.append(entry)

    return candidates, reason_counts, first_samples, dead_tickers


def build_market(
    market_key: str, fetcher: Fetcher, weekly_fetcher: Optional[Fetcher] = None,
    price_sink: Optional[Dict[str, Tuple[List[str], List[float]]]] = None,
) -> Dict:
    """Verarbeitet ein Marktuniversum (fail-soft je Ticker).

    Instrumentiert: zählt Skips nach Grund (inkl. short_setup_excluded) und
    loggt für die ersten 3 Skips je Markt das volle Detail (Traceback bzw.
    Datenform). Report/Schema bleiben unverändert.

    Großer Grad: NUR für die finalen Top-5 (nach Ranking) wird der
    Wochen-Count geholt und additiv als higher_degree angehängt — hält die
    Extra-Fetches bei ~TOP_N Tickern. higher_degree berührt Score/Ranking NICHT
    (wird erst NACH der Sortierung gesetzt).
    """
    cfg = config.MARKETS[market_key]
    universe = cfg["universe"]

    candidates, reason_counts, first_samples, dead_tickers = _scan_market(
        universe, fetcher, price_sink)

    # Deterministische Sortierung: Score desc, dann Ticker asc.
    candidates.sort(key=lambda e: (-e["score_heuristic"], e["ticker"]))
    top = candidates[: config.TOP_N]

    # Großer Grad NUR für die Top-N (additiv, ranking-neutral).
    higher_count = 0
    for entry in top:
        hd = higher_degree_for(entry["ticker"], weekly_fetcher)
        entry["higher_degree"] = hd
        if hd is not None:
            higher_count += 1

    skipped = sum(reason_counts.values())

    # --- Diagnose-Log (verändert Report/Schema NICHT) ---
    _log(
        f"[elliott][diag] {market_key}: {len(candidates)} Kandidaten, "
        f"{skipped} übersprungen von {len(universe)} — Gründe: "
        f"fetch_error={reason_counts[FETCH_ERROR]}, "
        f"empty_data={reason_counts[EMPTY_DATA]}, "
        f"too_few_pivots={reason_counts[TOO_FEW_PIVOTS]}, "
        f"no_valid_count={reason_counts[NO_VALID_COUNT]}, "
        f"short_setup_excluded={reason_counts[SHORT_SETUP_EXCLUDED]}"
    )
    _log(f"[elliott][diag] {market_key} großer Grad: "
         f"{higher_count}/{len(top)} Top-Kandidaten mit Wochen-Count")
    for i, (tk, reason, detail) in enumerate(first_samples, start=1):
        _log(f"[elliott][diag] {market_key} Skip-Probe {i}/{len(first_samples)}: "
             f"{tk} -> {reason}")
        _log(f"[elliott][diag]   Detail: {detail}")
    # Listen-Hygiene: tote/fehlerhafte Symbole namentlich (empty_data/fetch_error)
    # — so lassen sich nach einem echten Lauf gezielt Ticker aus config.py räumen.
    if dead_tickers:
        names = ", ".join(f"{tk}({rs})" for tk, rs in dead_tickers)
        _log(f"[elliott][diag] {market_key} Listen-Hygiene: "
             f"{len(dead_tickers)} tote/fehlerhafte Ticker -> {names}")

    return {
        "label": cfg["label"],
        "universe_size": len(universe),
        "evaluated": len(universe),
        "skipped": skipped,
        "candidates_found": len(candidates),
        "candidates": top,
        # Additive Diagnose-Zusammenfassung (die Zahlen stehen bereits im Log).
        # Rein für die „Lauf-Status"-Ansicht; Score/Ranking/Schema unberührt.
        "diag": {
            "reason_counts": dict(reason_counts),
            "higher_degree_count": higher_count,
            "top_count": len(top),
            # Listen-Hygiene: tote/fehlerhafte Symbole namentlich (Anzeige/Log).
            "dead_tickers": [{"ticker": tk, "reason": rs} for tk, rs in dead_tickers],
        },
    }


# ---------------------------------------------------------------------------
# 5b) PERSÖNLICHE WATCHLIST (Squeeze-Muster)
# ---------------------------------------------------------------------------
# Eigene Ticker laufen durch die VOLLE Analyse, unabhängig vom Top-5-Ranking.
# Sie erscheinen in einem SEPARATEN Report-Feld ``watchlist`` — nie in
# markets[].candidates. Damit können sie das Ranking nicht beeinflussen UND
# fließen NIE in die Forward-Sammlung (die liest ausschließlich die Top-5).
def load_watchlist() -> List[str]:
    """Lädt die persönliche Watchlist (fail-soft). Akzeptiert ein bloßes Array
    oder ``{"tickers": [...]}`` / ``{"watchlist": [...]}``. Dedup, Upper, Cap."""
    try:
        path = REPO_ROOT / config.WATCHLIST_PATH
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:  # noqa: BLE001 — fehlt/kaputt -> leere Watchlist
        return []
    if isinstance(data, dict):
        data = data.get("tickers") or data.get("watchlist") or []
    if not isinstance(data, list):
        return []
    out: List[str] = []
    seen = set()
    for t in data:
        if not isinstance(t, str):
            continue
        tk = t.strip().upper()
        if tk and tk not in seen:
            seen.add(tk)
            out.append(tk)
        if len(out) >= config.WATCHLIST_MAX:
            break
    return out


def _wl_base_entry(ticker: str) -> Dict:
    """Gemeinsames Karten-Gerüst (alle Felder vorhanden -> Frontend fail-soft)."""
    return {
        "ticker": ticker,
        "name": _company_name(ticker),
        "company_name": _meta_name(ticker),
        "sector": _meta_sector(ticker),
        "close": None,
        "change_abs": 0.0,
        "change_pct": 0.0,
        "direction": "long",
        "watchlist": True,
        "wl_status": "error",
        "note": "",
        "reason": "",
        "score_heuristic": None,
        "count_label": None,
        "invalidation_price": None,
        "target_zone": None,
        "target_zone_extended": None,
        "chart_points": [],
        "count_wave_labels": [],
        "higher_degree": None,
        # Multi-Timeframe-Analyse (NUR Watchlist, additiv): drei Zählungen je
        # Titel. Default alle null -> Fehler-/Kein-Daten-Karten zeigen ehrliche
        # „kein Count"-Zeilen statt zu verschweigen. Jede Ebene ist entweder null
        # oder {count_label, invalidation_price, target_zone, target_zone_extended}.
        "timeframes": {"day": None, "week": None, "month": None},
        "status": config.CARD_STATUS,
    }


def _wl_no_setup_entry(ticker: str, dates: List[str], closes: List[float],
                       reason: Optional[str], detail: str) -> Dict:
    """Watchlist-Karte OHNE regelkonformes Long-Setup — Kurs + Hinweis statt
    Verschweigen (bei eigener Watchlist will man den Stand sehen)."""
    e = _wl_base_entry(ticker)
    close = closes[-1] if closes else None
    prev = closes[-2] if len(closes) >= 2 else close
    if close is not None:
        e["close"] = round(close, 4)
        if prev:
            e["change_abs"] = round(close - prev, 4)
            e["change_pct"] = round((close / prev - 1.0) * 100.0, 4)
    # Pivots für eine kleine Sparkline mitgeben, falls vorhanden.
    if closes:
        pivots = zigzag(closes, config.ZIGZAG_WINDOW, dates)
        e["chart_points"] = [p.as_dict() for p in pivots[-12:]]
    e["wl_status"] = "no_setup"
    e["note"] = "kein regelkonformes Long-Setup"
    e["reason"] = reason or NO_VALID_COUNT
    return e


def _wl_error_entry(ticker: str, reason: Optional[str], detail: str) -> Dict:
    """Watchlist-Karte bei Fetch-/Datenfehler — Fehlhinweis statt Crash."""
    e = _wl_base_entry(ticker)
    e["wl_status"] = "error"
    e["note"] = "Daten nicht abrufbar"
    e["reason"] = reason or FETCH_ERROR
    return e


def build_watchlist_entry(
    ticker: str, fetcher: Fetcher, weekly_fetcher: Optional[Fetcher] = None,
    monthly_fetcher: Optional[Fetcher] = None,
    price_sink: Optional[Dict[str, Tuple[List[str], List[float]]]] = None,
) -> Dict:
    """Volle Analyse EINES Watchlist-Tickers. Wiederverwendet bereits geladene
    Kurse aus price_sink; sonst frischer Fetch. Immer eine Karte (fail-soft).

    Watchlist-Titel bekommen zusätzlich die Multi-Timeframe-Analyse
    (timeframes = Tag/Woche/Monat). Tag reift aus der bereits geladenen Tagesreihe
    (kein Extra-Fetch); Woche + Monat kosten je einen Fetch (bis zu +2 pro Titel,
    NUR im Watchlist-Zweig). Der Wochen-Count wird EINMAL geholt und dient sowohl
    higher_degree (unverändert) als auch timeframes.week (kein Doppel-Fetch)."""
    data = price_sink.get(ticker) if price_sink else None
    if data is None:
        outcome = fetcher(ticker)
        if outcome.reason is not None or outcome.data is None:
            # Kein Daten -> Fehler-Karte; timeframes bleiben alle null (aus Base):
            # Woche/Monat werden NICHT extra probiert (der Tagesabruf scheiterte
            # bereits — kein Grund, zwei weitere Fehl-Fetches zu erzwingen).
            return _wl_error_entry(ticker, outcome.reason, outcome.detail)
        dates, closes = outcome.data
        if price_sink is not None:
            price_sink[ticker] = (dates, closes)
    else:
        dates, closes = data

    # Drei Zählungen: Tag (reuse geladene Tagesreihe), Woche + Monat (je 1 Fetch).
    week_count = _count_from_fetch(ticker, weekly_fetcher)
    timeframes = {
        "day": _count_from_series(dates, closes),
        "week": week_count,
        "month": _count_from_fetch(ticker, monthly_fetcher),
    }

    entry, reason, detail = build_candidate(ticker, dates, closes)
    if entry is not None:
        # Long-Setup vorhanden -> volle Karte inkl. großem Grad (Wochen).
        entry["higher_degree"] = week_count          # == vorher (higher_degree_for)
        entry["timeframes"] = timeframes
        entry["watchlist"] = True
        entry["wl_status"] = "setup"
        entry["note"] = ""
        entry["reason"] = ""
        return entry
    e = _wl_no_setup_entry(ticker, dates, closes, reason, detail)
    e["timeframes"] = timeframes
    return e


def build_watchlist(
    fetcher: Fetcher, weekly_fetcher: Optional[Fetcher] = None,
    monthly_fetcher: Optional[Fetcher] = None,
    price_sink: Optional[Dict[str, Tuple[List[str], List[float]]]] = None,
    tickers: Optional[Sequence[str]] = None,
) -> Dict:
    """Baut die Watchlist-Sektion (separat von den Märkten, ranking-neutral)."""
    tks = list(tickers) if tickers is not None else load_watchlist()
    entries: List[Dict] = []
    counts = {"setup": 0, "no_setup": 0, "error": 0}
    for tk in tks:
        e = build_watchlist_entry(tk, fetcher, weekly_fetcher, monthly_fetcher,
                                  price_sink)
        counts[e["wl_status"]] = counts.get(e["wl_status"], 0) + 1
        entries.append(e)
    _log(f"[elliott][diag] Watchlist: {len(entries)} Ticker "
         f"(setup={counts['setup']}, no_setup={counts['no_setup']}, "
         f"error={counts['error']})")
    return {"entries": entries, "diag": counts}


def build_report(
    fetcher: Fetcher, run_timestamp_utc: str, weekly_fetcher: Optional[Fetcher] = None,
    monthly_fetcher: Optional[Fetcher] = None,
    price_sink: Optional[Dict[str, Tuple[List[str], List[float]]]] = None,
) -> Dict:
    """Baut das komplette Report-Objekt (deterministisch bei festem Input).

    price_sink (optional): wird mit {ticker: (dates, closes)} aller erfolgreich
    geladenen Ticker gefüllt — für die Forward-Sammlung, ohne Re-Fetch.

    monthly_fetcher (optional): NUR für die Watchlist (Monatsgrad). Die
    Markt-Pipeline (Top-5) bekommt ihn NICHT — sie bleibt Tag+Woche.
    """
    markets: Dict[str, Dict] = {}
    for key in config.MARKETS:
        markets[key] = build_market(key, fetcher, weekly_fetcher, price_sink)
    # Watchlist NACH den Märkten und in EIGENEM Feld -> Ranking unberührt, und
    # die Forward-Sammlung (liest nur markets[].candidates) sieht sie nie.
    watchlist = build_watchlist(fetcher, weekly_fetcher, monthly_fetcher, price_sink)
    return {
        "schema_version": config.SCHEMA_VERSION,
        "run_timestamp_utc": run_timestamp_utc,
        "generator": "elliott_pipeline",
        "disclaimer": "Heuristische Elliott-Wellen-Auszählung, unvalidiert. Keine Anlageberatung.",
        "markets": markets,
        "watchlist": watchlist,
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


def probe_ticker(ticker: str = "AAPL") -> None:
    """Expliziter Roh-Abruf eines Probe-Tickers rein fürs Log.

    Loggt yfinance-Version, Zeilen-/Spaltenform und die Datums-Range (KEINE
    Preisflut). Fängt alles ab — die Probe darf den Lauf nie beeinflussen.
    """
    _log(f"[elliott][diag] Probe-Abruf '{ticker}' (Roh-yfinance):")
    try:
        import yfinance as yf  # noqa: WPS433

        _log(f"[elliott][diag]   yfinance-Version: {getattr(yf, '__version__', '?')}")
        df = yf.download(
            ticker,
            period=config.DATA_PERIOD,
            interval=config.DATA_INTERVAL,
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        if df is None or getattr(df, "empty", True):
            _log(f"[elliott][diag]   Ergebnis: LEER (df={df!r})")
            return
        idx = df.index
        first = idx[0].strftime("%Y-%m-%d") if len(idx) else "?"
        last = idx[-1].strftime("%Y-%m-%d") if len(idx) else "?"
        _log(f"[elliott][diag]   Zeilen: {len(df)}, Spalten: {list(df.columns)}")
        _log(f"[elliott][diag]   Datums-Range: {first} .. {last}")
    except Exception as exc:  # noqa: BLE001 — Probe fail-soft
        _log(f"[elliott][diag]   Probe-Fehler: {type(exc).__name__}: {exc}")
        _log(f"[elliott][diag]   {traceback.format_exc().rstrip()}")


def main() -> int:
    fetcher = get_fetcher()
    mode = "OFFLINE/synthetisch" if fetcher is fetch_synthetic else "yfinance"
    _log(f"[elliott] Modus: {mode}")

    # NUR im echten Modus (offline/Dev läuft immer): Feiertags-Gate + Probe.
    if fetcher is not fetch_synthetic:
        # Feiertags-Gate: an gemeinsamen Voll-Schließtagen (NYSE ∩ Xetra) NICHT
        # rechnen — keine neuen Tageskerzen. Wochenenden deckt bereits der
        # daily.yml-Cron (Mo–Fr) ab. Der Staleness-Wächter kennt denselben
        # Kalender → kein Fehlalarm. Gate VOR der Probe (an Feiertagen kein Netz).
        import market_calendar as cal  # noqa: WPS433
        today = datetime.now(timezone.utc).date()
        if cal.holiday_list_expiring(today):
            _log("[elliott] WARNUNG: Feiertagsliste läuft aus — erneuern "
                 "(scripts/market_calendar.py, FULL_CLOSURE).")
        holiday = cal.is_full_closure(today)
        if holiday:
            _log(f"[elliott] Feiertag {holiday} — übersprungen "
                 f"(kein Lauf, nichts geschrieben).")
            return 0
        # Probe (Diagnose) nur im echten Modus und nur an Handelstagen.
        probe_ticker("AAPL")

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    price_sink: Dict[str, Tuple[List[str], List[float]]] = {}
    _t0 = time.monotonic()
    report = build_report(fetcher, ts, get_weekly_fetcher(),
                          get_monthly_fetcher(), price_sink)
    # Lauf-Dauer additiv (nur in main gesetzt -> build_report bleibt
    # deterministisch/testbar). Rein informativ für die „Lauf-Status"-Ansicht.
    report["generated_in_seconds"] = round(time.monotonic() - _t0, 1)
    # N×-Zähler additiv annotieren — mit dem Sammlungs-Stand VOR dem Update
    # (die aktuelle Erscheinung wird erst danach eingetragen). Fail-soft: fehlt/
    # kaputt -> kein Zähler, Report bleibt heil. Rein Anzeige, kein Ranking.
    try:
        fc.annotate_appearance_counts(fc.load_collection(), report)
    except Exception as exc:  # noqa: BLE001
        _log(f"[elliott] N×-Zähler übersprungen (fail-soft): "
             f"{type(exc).__name__}: {exc}")
    written = write_report(report)

    us = report["markets"]["US"]
    de = report["markets"]["DE"]
    _log(
        f"[elliott] US: {us['candidates_found']} Kandidaten "
        f"({us['skipped']} übersprungen von {us['universe_size']})"
    )
    _log(
        f"[elliott] DE: {de['candidates_found']} Kandidaten "
        f"({de['skipped']} übersprungen von {de['universe_size']})"
    )
    for p in written:
        _log(f"[elliott] geschrieben: {p.relative_to(REPO_ROOT)}")

    # Forward-Sammlung — NACH write_report (report.json ist schon geschrieben)
    # und komplett gekapselt: ein Sammel-Fehler darf den Report NIE brechen.
    try:
        run_date = report["run_timestamp_utc"][:10]
        regimes = fc.market_regimes(fetcher is fetch_synthetic)
        coll = fc.load_collection()
        fc.update_forward_collection(coll, report, price_sink, regimes, run_date, ts)
        # Score-Alert-Flanke: an DIESELBE Episoden-Logik gekoppelt. NACH dem
        # Update (Episoden-Records tragen jetzt last_seen == run_date), Flags
        # werden in coll gesetzt -> VOR write_collection persistiert. Der Push
        # kommt erst NACH dem Schreiben: die Einmaligkeit (Flag) ist dann schon
        # gesichert und ein Push-Fehler kann sie nicht rückgängig machen
        # (Einmaligkeit vor Zustellgarantie — wie beim Meilenstein-Marker).
        edges = fc.score_alert_edges(coll, report, config.SCORE_ALERT_THRESHOLD,
                                     run_date)
        fc.write_collection(coll)
        if edges:
            notify.send_score_alert(os.environ.get("NTFY_TOPIC", ""), edges,
                                    config.SCORE_ALERT_THRESHOLD)
            _log(f"[elliott] Score-Alert (>{config.SCORE_ALERT_THRESHOLD}): "
                 f"{len(edges)} neu — {', '.join(e['ticker'] for e in edges)}")
        n, matured, evaluable = fc.eval_counts(coll)
        _log(f"[elliott] Forward-Sammlung: {n} gesammelt · {matured} gereift · "
             f"{evaluable} auswertbar (Auswertung ab n>={fc.EVAL_MIN_N}, PRU-Guard) "
             f"· Regime {regimes}")
    except Exception as exc:  # noqa: BLE001 — Sammlung darf Report nie brechen
        _log(f"[elliott] Forward-Sammlung übersprungen (fail-soft): "
             f"{type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
