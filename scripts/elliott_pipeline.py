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
from numeric import finite  # noqa: E402 — EIN Finit-Prädikat für alle Guards
from rules import validate_impulse, validate_partial_to_w4  # noqa: E402
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
# Produktentscheidung (23.07., PRU-Diagnose): ein Setup, dessen Lauf-Schlusskurs
# die Zielzone bereits erreicht hat (close >= target_zone.low), ist nicht mehr
# handelbar — es fliegt VOR dem Ranking aus den Markt-Top-5 (Rang 6+ rückt nach).
# NUR Markt-Pipeline; die Watchlist zeigt weiter alles (Badge markiert dort den
# Zustand). Zusammenspiel mit dem #28-Guard = Verteidigung in der Tiefe: der Filter
# verhindert die Neuanlage über Zone, der Guard schützt die Messung, falls doch je
# einer durchkommt.
TARGET_EXCEEDED = "target_exceeded"
SKIP_REASONS = (
    FETCH_ERROR, EMPTY_DATA, TOO_FEW_PIVOTS, NO_VALID_COUNT, SHORT_SETUP_EXCLUDED,
    TARGET_EXCEEDED,
)


# Verworfene-Bar-Daten je Ticker im Report: gekappt, damit ein systemischer
# Ausfall den Report nicht aufblaeht. Die ANZAHL bleibt vollstaendig.
MAX_DROPPED_DATES = 5


@dataclass
class FetchOutcome:
    """Ergebnis eines Abrufs. Trägt bei Misserfolg den Grund + ein Detail.

    Das Detail dient NUR dem Log (Traceback bzw. Datenform). Es beeinflusst
    weder Report noch die Skip-Entscheidung.
    """

    data: Optional[Tuple[List[str], List[float]]] = None
    reason: Optional[str] = None
    detail: str = ""
    # Additiv (Messfelder v1): Tagesvolumen, gleich ausgerichtet/gekürzt wie
    # data[1] (closes). Steckt im SELBEN yfinance-Download — KEIN Extra-Call.
    # Fail-soft None, wenn keine Volume-Spalte vorliegt. Berührt data NICHT
    # (bestehende `dates, closes = outcome.data`-Unpacks bleiben byte-identisch).
    volumes: Optional[List[Optional[float]]] = None
    # Nicht-finit-Härtung (27.07.2026): wie viele Bars beim Parsen VERWORFEN
    # wurden, weil ihr Close nicht endlich war (NaN/±Inf), und wie viele Bars
    # ein unbrauchbares Volumen hatten (Bar bleibt, Volumen wird None).
    # Rein diagnostisch — Skip-Entscheidung und `data` bleiben unberührt.
    dropped_bars: int = 0
    invalid_volume_bars: int = 0
    # Nur Diagnose (30.07.2026): WELCHE Zeilen verworfen wurden. Ein Muster
    # „immer der letzte Bar" ist eine unfertige Tages-Zeile; ein Datum mitten in
    # der Reihe ist eine echte Lücke in der Quelle. Ohne diese Angabe war beides
    # nicht unterscheidbar (DE-Lauf 29.07.: 116 verworfene Bars, Ursache offen).
    dropped_dates: Tuple[str, ...] = ()
    dropped_last_row: int = 0
    dropped_mid_row: int = 0


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

    (dates, closes, volumes, dropped, bad_vol,
     dropped_dates, dropped_last, dropped_mid) = _extract_bars(df)
    if len(closes) < mb:
        return FetchOutcome(
            reason=EMPTY_DATA,
            detail=(
                f"zu wenige Kerzen: {len(closes)} < min_bars={mb}; "
                f"shape={df.shape}, columns={list(df.columns)}, "
                f"verworfene Bars={dropped}"
            ),
            dropped_bars=dropped,
            invalid_volume_bars=bad_vol,
            dropped_dates=tuple(dropped_dates),
            dropped_last_row=dropped_last, dropped_mid_row=dropped_mid,
        )
    return FetchOutcome(data=(dates, closes), volumes=volumes,
                        dropped_bars=dropped, invalid_volume_bars=bad_vol,
                        dropped_dates=tuple(dropped_dates),
                        dropped_last_row=dropped_last,
                        dropped_mid_row=dropped_mid)


def _extract_bars(df):
    """Datum/Close/Volumen in EINEM ausgerichteten Durchgang — die Quelle.

    NICHT-FINIT-HÄRTUNG (27.07.2026, Ursachen-Fix zu #51). Vorher lief das so:

        closes = [float(x) for x in df["Close"].dropna().tolist()]
        dates  = [...alle Datumswerte...][: len(closes)]
        volumes = _extract_volumes(df, len(closes))   # aus dem UNGEFILTERTEN df

    Daran waren **drei** Dinge kaputt, und zwar still:

    1. **Datums-Versatz.** ``dropna`` entfernt die Zeile, das Datum wird aber
       nur vorne abgeschnitten. Sitzt das Loch in der MITTE, bekommt jeder
       Close danach das Datum seines Vorgängers. Belegt: Close-Reihe
       ``[10, NaN, 30, 40]`` liefert ``30.0`` mit dem Datum des 02.01. statt
       des 03.01. Das verschiebt Pivot-Daten, ``chart_points``, die
       Sparkline-Achsen (#47) und die point-in-time eingefrorenen Pivots in
       der Sammlung — also genau die Belege, die später ausgewertet werden.
    2. **±Inf blieb drin.** ``dropna`` entfernt NUR NaN. Ein unendlicher Close
       lief unverändert in Zählung, Zielzone und Score.
    3. **Volumen-Versatz.** Die Volumen kamen aus dem ungefilterten Frame und
       passten nach jedem entfernten Close nicht mehr zu den Pivot-Indizes.

    Jetzt: EIN Durchgang über die Zeilen, gemeinsam gefiltert. Ein Bar ohne
    endlichen Close ist **kein Bar** und wird verworfen (gezählt). Ein Bar mit
    unbrauchbarem Volumen bleibt (der Preis ist gültig!), sein Volumen wird
    ``None`` — Messfeld-Semantik, siehe ``numeric``. Bewusst NICHT der ganze
    Bar: das Volumen ist ein rein additives Messfeld ohne Score-Wirkung, ein
    Verwerfen würde die Zählung von der Volumen-Verfügbarkeit abhängig machen.

    Returnt ``(dates, closes, volumes|None, dropped_bars, invalid_volume_bars)``.
    """
    has_vol = "Volume" in getattr(df, "columns", [])
    close_col = df["Close"].tolist()
    vol_col = df["Volume"].tolist() if has_vol else None
    idx = list(df.index)

    dates: List[str] = []
    closes: List[float] = []
    volumes: List[Optional[float]] = []
    dropped = bad_vol = 0
    # Diagnose (30.07.2026): Datum und Position der verworfenen Zeilen. Ändert
    # NICHTS am Verwerfen selbst — nur die Auskunft darüber.
    dropped_dates: List[str] = []
    dropped_last = dropped_mid = 0
    letzte = len(close_col) - 1

    def _merke_verworfen(i: int) -> None:
        nonlocal dropped_last, dropped_mid
        try:
            dropped_dates.append(idx[i].strftime("%Y-%m-%d"))
        except Exception:  # noqa: BLE001 — Index ohne Datum: ehrlich als „?"
            dropped_dates.append("?")
        if i == letzte:
            dropped_last += 1
        else:
            dropped_mid += 1

    for i, raw_close in enumerate(close_col):
        try:
            c = float(raw_close)
        except (TypeError, ValueError):
            c = float("nan")
        if not finite(c):
            dropped += 1
            _merke_verworfen(i)
            continue                      # kein gültiger Preis = kein Bar
        try:
            dates.append(idx[i].strftime("%Y-%m-%d"))
        except Exception:  # noqa: BLE001 — Index ohne strftime: Bar unbrauchbar
            dropped += 1
            _merke_verworfen(i)
            continue
        closes.append(c)
        if vol_col is None:
            continue
        try:
            v = float(vol_col[i])
        except (TypeError, ValueError, IndexError):
            v = float("nan")
        if finite(v):
            volumes.append(v)
        else:
            volumes.append(None)          # Messfeld fehlt ehrlich, statt 0.0
            bad_vol += 1

    return (dates, closes, (volumes if has_vol else None), dropped, bad_vol,
            dropped_dates, dropped_last, dropped_mid)


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

    # Deterministisches Volumen je Segment (Guideline-Form: W1 trägt mehr als W2)
    # — rein additiv für den Offline-/Dev-Pfad, gleiche Segment-/Schritt-Logik wie
    # `closes`, damit beide exakt gleich lang und ausgerichtet sind.
    vol_base = 1_000_000.0 + (seed % 50) * 10_000.0
    seg_vol_mult = [0.7, 1.6, 0.9, 1.1]  # Abstieg P0 · W1 (hoch) · W2 (niedriger) · Beginn W3

    closes: List[float] = []
    volumes: List[float] = []
    for (start, end, n), vmult in zip(seg, seg_vol_mult):
        # n Schritte, exklusive Startpunkt (außer beim allerersten Segment).
        rng = range(n + 1) if not closes else range(1, n + 1)
        for k in rng:
            closes.append(start + (end - start) * (k / n))
            volumes.append(round(vol_base * vmult * (1.0 + 0.01 * (k % 5)), 1))

    dates = _synthetic_dates(len(closes))
    return FetchOutcome(data=(dates, closes), volumes=volumes)


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
    """Weicher Bonus je näher `retrace` an einem Schlüssel-Fib liegt.

    Nicht-finit-Härtung: ein nicht endliches ``retrace`` ergäbe über
    ``max(best, nan)`` einen NaN-Bonus und damit einen NaN-Score. Kein Bonus
    ist die ehrliche Antwort — die Nähe ist schlicht nicht bestimmbar.
    """
    if not finite(retrace):
        return 0.0
    tol = config.FIB_PROXIMITY_TOLERANCE
    best = 0.0
    for t in targets:
        closeness = 1.0 - abs(retrace - t) / tol
        best = max(best, closeness)
    best = max(0.0, min(1.0, best))
    return best * config.FIB_PROXIMITY_MAX_BONUS


def _invalidation_bonus(close: float, invalidation: float) -> float:
    """Bonus nach prozentualem Abstand des Kurses zum K.o.-Level.

    Nicht-finit-Härtung: ``close <= 0`` ist die negierte Form — NaN rutschte
    durch, ``dist_pct`` wurde NaN und der Score damit auch.
    """
    if not finite(close) or not finite(invalidation) or close <= 0:
        return 0.0
    dist_pct = abs(close - invalidation) / close * 100.0
    frac = min(dist_pct / config.INVALIDATION_DISTANCE_CAP, 1.0)
    return frac * config.INVALIDATION_DISTANCE_MAX_BONUS


def _target_zone(base: float, direction: int, w1_len: float, ext: Sequence[float]) -> Dict[str, float]:
    a = base + direction * ext[0] * w1_len
    b = base + direction * ext[1] * w1_len
    return {"low": round(min(a, b), 4), "high": round(max(a, b), 4)}


def _eval_end_of_w4(prices: Sequence[float], close: float) -> Optional[Dict]:
    """Bewertet die letzten 5 Pivots als Teil-Impuls P0..P4 (end_of_w4). Setup-Dict
    oder None. Extrahiert aus classify_setup — Logik/Rückgabe UNVERÄNDERT."""
    if len(prices) < 5:
        return None
    pts = prices[-5:]
    res = validate_partial_to_w4(pts)
    if not res.is_valid:
        return None
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
    # Extension-Zielzone (additiv): W5 gemessen an der Netto-Strecke P0->P3
    # (nicht an W1), ab P4. _target_zone sichert die min/max-Ordnung.
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


def _eval_end_of_w2(prices: Sequence[float], close: float) -> Optional[Dict]:
    """Bewertet die letzten 3 Pivots P0..P2 (end_of_w2). Setup-Dict oder None.
    Extrahiert aus classify_setup — Logik/Rückgabe UNVERÄNDERT."""
    if len(prices) < 3:
        return None
    p0, p1, p2 = prices[-3:]
    direction = 1 if p1 >= p0 else -1
    # Regel 1 (W2 <= 100 %): normalisiert P2 nicht jenseits von P0.
    norm_p0, norm_p2 = direction * p0, direction * p2
    if norm_p2 < norm_p0:
        return None
    w1_len = abs(p1 - p0)
    retrace_w2 = abs(p2 - p1) / w1_len if w1_len else 0.0
    # Nur plausible Retracements (0 < r <= 1) als Setup werten.
    if not (0.0 < retrace_w2 <= 1.0):
        return None
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


def classify_setup(pivots: List[Pivot], close: float) -> Optional[Dict]:
    """Ermittelt das aktuelle Setup aus den jüngsten Pivots.

    Priorität: end_of_w4 (mehr bestätigte Struktur) vor end_of_w2 — **first-fit**
    über genau diese zwei festen End-Fenster (letzte 5 / letzte 3 Pivots). Gibt
    None zurück, wenn kein sauberes, regelkonformes Setup vorliegt. Verhalten
    byte-identisch zu vorher (nur in zwei Helfer ausgelagert; die Ambiguitäts-
    Enumeration zählt dieselben zwei Fenster, ändert die PRIMÄR-Wahl NICHT)."""
    prices = [p.price for p in pivots]
    return _eval_end_of_w4(prices, close) or _eval_end_of_w2(prices, close)


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
# AMBIGUITÄT v1 (additiv, REINE ANZEIGE/MESSUNG — kein Score/Ranking/Filter)
# ---------------------------------------------------------------------------
# Fach-Konsens ist Multi-Count: fast immer > eine valide Zählung. classify_setup
# ist first-fit über ZWEI feste End-Fenster (Ende-W4 auf den letzten 5, Ende-W2 auf
# den letzten 3 Pivots). Der Ausweis ZÄHLT beide Fenster (statt nur first-fit) und
# weist die beste Alternative aus — die PRIMÄR-Wahl (classify_setup) bleibt
# byte-identisch. Bewusst begrenzt auf das heutige Zähl-Vokabular (2 Fenster),
# NICHT der volle Elliott-Interpretationsraum → Maximum ist „1 von 2". Erweitert
# sich das Vokabular (z. B. ABC ab P4), entsteht ein NEUES datiertes Feld
# (ambiguity v2); v1 wird nie umdefiniert. Long-only (konsistent zum Board).
def enumerate_long_counts(pivots: List[Pivot], close: float) -> List[Dict]:
    """Alle validen LONG-Counts im definierten Suchraum (die zwei End-Fenster von
    classify_setup), in Prioritätsreihenfolge [Ende-W4, Ende-W2]. Short-Counts
    zählen NICHT mit (Long-only). Deterministisch (gleiche Pivots → gleiche Liste)."""
    prices = [p.price for p in pivots]
    out: List[Dict] = []
    for setup in (_eval_end_of_w4(prices, close), _eval_end_of_w2(prices, close)):
        if setup is not None and setup["direction"] > 0:
            out.append(setup)
    return out


def ambiguity_fields(pivots: List[Pivot], close: float) -> Tuple[int, Optional[Dict]]:
    """(valid_count_total, alt_count). total = Anzahl valider Long-Counts (0..2).
    alt_count (nur bei total ≥ 2) = kompakte **zweitbeste** nach **exakt derselben**
    Score-Formel (`score_setup`) — kein neues Ranking-Kriterium. Die Primär-Zählung
    (counts[0]) ist byte-identisch zu classify_setup; alt = beste der übrigen."""
    counts = enumerate_long_counts(pivots, close)
    total = len(counts)
    alt = None
    if total >= 2:
        best_alt = max(counts[1:], key=score_setup)  # zweitbeste (bei 2: counts[1])
        alt = {
            "count_label": best_alt["count_label"],
            "invalidation_price": best_alt["invalidation_price"],
            "target_zone": best_alt["target_zone"],
            "score_heuristic": score_setup(best_alt),
        }
    return total, alt


def ambiguity_v2_fields(pivots: List[Pivot], close: float) -> Tuple[int, Optional[Dict]]:
    """Ambiguität v2 (Struktur-Vokabular v2, ab 2026-07-25): zählt Lesarten im
    ERWEITERTEN Vokabular = die validen Impuls-Fenster (wie v1) PLUS eine bestätigte
    A-B-C-Korrektur-Lesart (falls vorhanden). `valid_count_total_v2` ≥ v1. Die
    Primär-Lesart bleibt die Impuls-Zählung (counts[0]); die Korrektur ist immer
    ALTERNATIVE. alt bevorzugt die zweitbeste Impuls-Lesart (nach `score_setup`),
    sonst die Korrektur-Lesart (ohne Zielzone/Score — `kind`='correction'). v1 läuft
    UNVERÄNDERT weiter (Vergleichbarkeit der Alt-Daten)."""
    impulse = enumerate_long_counts(pivots, close)
    corr = _detect_correction([p.price for p in pivots])
    total = len(impulse) + (1 if corr is not None else 0)
    alt = None
    if len(impulse) >= 2:
        best = max(impulse[1:], key=score_setup)
        alt = {
            "count_label": best["count_label"],
            "invalidation_price": best["invalidation_price"],
            "target_zone": best["target_zone"],
            "score_heuristic": score_setup(best),
            "kind": "impulse",
        }
    elif corr is not None and impulse:
        alt = {
            "count_label": corr["label"],
            "invalidation_price": corr["invalidation_price"],
            "target_zone": None,
            "score_heuristic": None,
            "kind": "correction",
        }
    return total, alt


# ---------------------------------------------------------------------------
# KONFLUENZ-MARKEN (additiv, REINE ANZEIGE/MESSUNG — kein Score/Ranking)
# ---------------------------------------------------------------------------
def _round_step(price: float) -> float:
    """Runde-Zahl-Schrittweite je Preisklasse (config.CONFLUENCE_ROUND_STEPS)."""
    for upper, step in config.CONFLUENCE_ROUND_STEPS:
        if price < upper:
            return step
    return config.CONFLUENCE_ROUND_STEP_LARGE


def _nearest_round(price: float) -> float:
    step = _round_step(price)
    return round(price / step) * step


def compute_confluence(closes: Sequence[float], target_zone: Dict[str, float],
                       invalidation: float) -> Dict[str, List[str]]:
    """Crowd-Marken vs. Zielzone/Invalidierung — REINE ANZEIGE/MESSUNG, KEINE
    Score-/Ranking-Wirkung. Aus den BEREITS geladenen Tagesschlusskursen (keine
    neuen Fetches). Drei Marken: 52-Wochen-Hoch, 200-Tage-Linie, nächste runde
    Zahl.

    Rückgabe {"target": [...], "invalidation": [...]} mit Marken-Keys
    (``"52w_high"``, ``"200d"``, ``"round"``) in fester Reihenfolge (deterministisch).

    - 52w-Hoch / 200d sind EINZELwerte -> „konfluent mit der Zielzone", wenn der
      Wert im Band [low, high] (± Toleranz) liegt; „mit Invalidierung", wenn er
      innerhalb ±Toleranz der Invalidierung liegt.
    - Runde Zahlen sind DICHT -> hier nur an den KANTEN geprüft (Zonen-Low/-High
      bzw. Invalidierung): sitzt die aktionable Marke direkt auf einer runden Zahl?
      (Band-Mitgliedschaft wäre bei dichten Rundzahlen nichtssagend.)
    """
    out: Dict[str, List[str]] = {"target": [], "invalidation": []}
    if not closes or not target_zone:
        return out
    tol = config.CONFLUENCE_TOLERANCE_PCT / 100.0
    low = target_zone.get("low")
    high = target_zone.get("high")
    if low is None or high is None:
        return out

    def _near(value: float, ref: float) -> bool:
        return ref not in (None, 0) and abs(value - ref) <= tol * abs(ref)

    def _in_band(value: float) -> bool:
        return low * (1 - tol) <= value <= high * (1 + tol)

    # 1) Einzelwert-Marken in fester Reihenfolge.
    single: List[Tuple[str, float]] = []
    lookback = list(closes)[-config.CONFLUENCE_52W_LOOKBACK:]
    if lookback:
        single.append(("52w_high", max(lookback)))
    if len(closes) >= config.CONFLUENCE_SMA_WINDOW:
        window = list(closes)[-config.CONFLUENCE_SMA_WINDOW:]
        single.append(("200d", sum(window) / config.CONFLUENCE_SMA_WINDOW))
    for name, value in single:
        if _in_band(value):
            out["target"].append(name)
        if _near(value, invalidation):
            out["invalidation"].append(name)

    # 2) Runde Zahl NUR an den Kanten (dicht -> Band nichtssagend).
    if _near(_nearest_round(low), low) or _near(_nearest_round(high), high):
        out["target"].append("round")
    if invalidation and _near(_nearest_round(invalidation), invalidation):
        out["invalidation"].append("round")
    return out


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


# Grad-Sparklines (P4b): wie viele Pivots die Wochen-/Monats-Zählung als
# Mini-Chart mitgibt — die gezählte Struktur (max 5 Pivots bei Ende-W4) plus
# wenige Vorlauf-Pivots für Kontext. Bewusst KLEIN (Payload): 8 Pivots ≈ ~0,5 KB
# je Zählung; die Tages-Sparkline der Karten bleibt bei ihren 12 (unberührt).
DEGREE_CHART_PIVOTS = 8


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
    # Ambiguität v1 (additiv, kein Score/Ranking): wie viele valide Long-Counts
    # lässt die Struktur zu (max 2), plus die beste Alternative. v2 zusätzlich (ABC).
    total, alt = ambiguity_fields(pivots, closes[-1])
    total_v2, alt_v2 = ambiguity_v2_fields(pivots, closes[-1])
    # Grad-Sparkline (P4b, additiv): Pivot-Punkte der gezählten Struktur + wenige
    # Vorlauf-Pivots (DEGREE_CHART_PIVOTS), Wellen-Ziffern wie beim Tagesgrad
    # (index relativ zu chart_points; wave 0 = P0-Start). Reine Anzeige.
    chart_points = [p.as_dict() for p in pivots[-DEGREE_CHART_PIVOTS:]]
    k = 5 if setup["setup"] == "end_of_w4" else 3
    ncp = len(chart_points)
    count_wave_labels = [{"index": ncp - k + j, "wave": j} for j in range(k)]
    return {
        "count_label": setup["count_label"],
        "invalidation_price": setup["invalidation_price"],
        "target_zone": setup["target_zone"],
        "target_zone_extended": setup["target_zone_extended"],
        "valid_count_total": total,
        "alt_count": alt,
        "valid_count_total_v2": total_v2,
        "alt_count_v2": alt_v2,
        "chart_points": chart_points,
        "count_wave_labels": count_wave_labels,
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


# ── Struktur-Befund (NUR Watchlist-Diagnostik) ─────────────────────────────
# Ehrliche Einordnung JE ZEITEBENE — auch wenn KEIN Long-Setup vorliegt: wo steht
# der Titel in der Elliott-Struktur (statt nur „kein Count")? Fünf Kategorien,
# KEINE Wahrscheinlichkeit, kein Score. Dieselben Pivots/Regeln wie der Count.
# Reine Anzeige: Markt-Pipeline, Score, Ranking, Filter und die
# forward_collection-Population bleiben unberührt (nur im Watchlist-Zweig gesetzt).
STRUCTURE_NO = "no_structure"
_STRUCTURE_DEFAULT = {"state": STRUCTURE_NO, "label": "keine regelkonforme Zählung",
                      "invalidation_price": None, "mark_label": None,
                      "orientation_price": None, "direction": None}


# ── ABC-Korrektur (Struktur-Vokabular v2, ab 2026-07-25) ───────────────────
# Eine einfache Zigzag-Korrektur (A-B-C) NACH einem validen 5-Wellen-Impuls,
# erkannt AUSSCHLIESSLICH auf den BESTÄTIGTEN ZigZag-Pivots. Bewusst OHNE
# Magnituden-Schwelle: die ZigZag-Bestätigung (Fenster) IST der Signifikanzfilter,
# der Rest sind strikte Preis-Ungleichungen → sauber abgrenzbar & deterministisch.
# NUR für den Watchlist-Struktur-Befund + ambiguity v2 + W5→A-Strukturmessung —
# KEIN neuer Markt-Setup-Typ (Board/Score/Ranking/Filter unberührt).
_ABC_IMPULSE_PIVOTS = 6   # P0..P5 (validate_impulse)
_ABC_MAX_CORR_PIVOTS = 3  # A, B, C (longest-first: complete vor running)


def _corr_reading(state: str, label: str, invalid: Optional[float], d: int,
                  mark: Optional[str], orient: Optional[float]) -> Dict:
    """Korrektur-Reading im gleichen Schema wie _classify_structure.mk()."""
    return {"state": state, "label": label,
            "invalidation_price": round(invalid, 4) if finite(invalid) else None,
            "mark_label": mark,
            "orientation_price": round(orient, 4) if finite(orient) else None,
            "direction": "long" if d > 0 else "short"}


def _corr_from(imp: Sequence[float], corr: Sequence[float], d: int) -> Optional[Dict]:
    """Prüft die Korrektur-Pivots gegen den Impuls (Richtung d). d normalisiert die
    Ungleichungen (long: Korrektur nach UNTEN; short: symmetrisch nach OBEN).
    A gegen Impulsrichtung · B retraced A in (0,1) (überschreitet A-Start=P5 nicht)
    · C jenseits des A-Endes. Invalidierung der Korrektur-Lesart: running(A) über
    dem Impuls-Extrem, running(A-B) über B, complete(A-B-C) jenseits C."""
    p5 = imp[-1]                      # Impuls-Ende (W5-Extrem)
    a = corr[0]
    if not (d * a < d * p5):          # A muss GEGEN die Impulsrichtung laufen
        return None
    long_ctx = d > 0
    if len(corr) == 1:
        return _corr_reading("correction_running", "Korrektur läuft · A (ABC im Aufbau)",
                             p5, d, mark="W5-Extrem", orient=a)
    b = corr[1]
    if not (d * a < d * b < d * p5):  # B retraced A, bleibt unter dem Impuls-Extrem
        return None
    if len(corr) == 2:
        return _corr_reading("correction_running", "Korrektur läuft · A-B (C erwartet)",
                             b, d, mark=("B-Hoch" if long_ctx else "B-Tief"), orient=a)
    c = corr[2]
    if not (d * c < d * a):           # C jenseits des A-Endes (neuer Extrempunkt)
        return None
    return _corr_reading("correction_complete", "Korrektur A-B-C komplett · neuer Impuls möglich",
                         c, d, mark=("C-Tief" if long_ctx else "C-Hoch"), orient=None)


def _detect_correction(prices: Sequence[float]) -> Optional[Dict]:
    """A-B-C-Korrektur nach validem 5er-Impuls auf den bestätigten Pivots. None,
    wenn keine sauber abgrenzbare Korrektur vorliegt. Longest-first (A-B-C vor A-B
    vor A) → correction_complete gewinnt gegen correction_running. Deterministisch."""
    n = len(prices)
    for k in range(_ABC_MAX_CORR_PIVOTS, 0, -1):   # 3 -> 2 -> 1
        need = _ABC_IMPULSE_PIVOTS + k
        if n < need:
            continue
        imp = prices[-need:-k]                      # 6 Impuls-Pivots P0..P5
        corr = prices[-k:]                          # k Korrektur-Pivots
        r = validate_impulse(list(imp))
        if not r.is_valid:
            continue
        reading = _corr_from(imp, corr, r.direction)
        if reading is not None:
            return reading
    return None


def _classify_structure(prices: Sequence[float], close: float) -> Dict:
    """Reine Klassifikation aus den Pivot-Preisen + aktuellem Schlusskurs (ohne
    Netz/ZigZag — direkt testbar). Priorität: kompletter 5-Wellen-Impuls (letzte
    6 Pivots) -> Teil-Impuls bis W4 (5) -> Ende W2 (3). Long/Short aus P0->P1.
    „läuft" vs. „Setup" über die Lage des Schlusskurses zur zuletzt bestätigten
    Impulsspitze (W1- bzw. W3-Hoch): ist sie gebrochen, läuft die Folge-Welle
    (W3/W5); sonst ist es ein offenes Ende-W2/W4-Setup."""
    n = len(prices)
    if n < 3:
        return dict(_STRUCTURE_DEFAULT)

    # PRÄZEDENZ (Struktur-Vokabular v2): Eine bestätigte A-B-C-Korrektur NACH einem
    # validen Impuls beschreibt die aktuelle Lage vollständiger als ein erneutes
    # Lesen der letzten 6/5/3 Pivots → sie gewinnt gegen die Impuls-Kategorien.
    # Greift nur bei ≥7 Pivots mit validem Impuls + Korrektur-Ungleichungen; sonst
    # None → unveränderte Weiterverarbeitung der bestehenden 5 Kategorien.
    corr = _detect_correction(prices)
    if corr is not None:
        return corr

    # `invalid` = struktureller Ungültigkeitspunkt der Zählung; `mark_label` sagt,
    # WELCHER Pivot das ist (sonst wirkt die nackte Zahl wie eine nahe Orientierung).
    # `orient` = NAHE, handlungsnähere Orientierung (nur bei komplettem Impuls: das
    # W4-Extrem als typische erste Ziel-Region der erwarteten Korrektur A).
    def mk(state: str, label: str, invalid: Optional[float], direction: int,
           mark_label: Optional[str] = None, orient: Optional[float] = None) -> Dict:
        return {"state": state, "label": label,
                "invalidation_price": round(invalid, 4) if finite(invalid) else None,
                "mark_label": mark_label,
                "orientation_price": round(orient, 4) if finite(orient) else None,
                "direction": "long" if direction > 0 else "short"}

    # 1) Kompletter 5-Wellen-Impuls (letzte 6 Pivots) -> Korrektur erwartet.
    #    Marke = Impuls-Start (P0, Zählung ungültig darunter); Orientierung = W4-
    #    Extrem (P4), das typische erste Ziel einer Korrektur A.
    if n >= 6:
        r = validate_impulse(prices[-6:])
        if r.is_valid:
            p0, _p1, _p2, _p3, p4, _p5 = prices[-6:]
            if r.direction > 0:
                return mk("impulse_complete",
                          "5 Wellen komplett · Korrektur (A) erwartet", p0, 1,
                          mark_label="Impuls-Start", orient=p4)
            return mk("short_structure",
                      "Abwärts-Impuls · 5 Wellen komplett", p0, -1,
                      mark_label="Impuls-Start", orient=p4)

    # 2) Teil-Impuls bis W4 (letzte 5 Pivots). Marke = W1-Hoch (P1; W4 darf W1 nicht
    #    überlappen -> darunter Zählung hin) — zugleich der Count-Invalidierungspunkt.
    if n >= 5:
        r = validate_partial_to_w4(prices[-5:])
        if r.is_valid:
            _p0, p1, _p2, p3, _p4 = prices[-5:]
            if r.direction > 0:
                if close > p3:            # W3-Hoch gebrochen -> W5 läuft
                    return mk("impulse_running", "Impuls läuft · vermutlich W5", p1, 1,
                              mark_label="W1-Hoch")
                return mk("long_setup", "Long-Setup · Ende W4 (W5 erwartet)", p1, 1,
                          mark_label="W1-Hoch")
            return mk("short_structure", "Abwärts-Impuls · Ende W4", p1, -1,
                      mark_label="W1-Hoch")

    # 3) Ende W2 (letzte 3 Pivots). Fallback, wenn weder ein kompletter Impuls
    #    (6) noch ein Teil-Impuls bis W4 (5) regelkonform war — hier zählen die
    #    letzten drei bestätigten Pivots als P0/P1/P2 (Regel 1 + plausibler Retrace).
    #    Marke = W1-Start (P0; W2 darf W1 nicht > 100 % zurücklaufen).
    p0, p1, p2 = prices[-3:]
    direction = 1 if p1 >= p0 else -1
    if direction * p2 >= direction * p0:              # Regel 1: W2 <= 100 %
        w1 = abs(p1 - p0)
        retr = abs(p2 - p1) / w1 if w1 else 0.0
        if 0.0 < retr <= 1.0:
            if direction > 0:
                if close > p1:            # W1-Hoch gebrochen -> W3 läuft
                    return mk("impulse_running", "Impuls läuft · vermutlich W3", p0, 1,
                              mark_label="W1-Start")
                return mk("long_setup", "Long-Setup · Ende W2 (W3 erwartet)", p0, 1,
                          mark_label="W1-Start")
            return mk("short_structure", "Abwärts-Impuls · Ende W2", p0, -1,
                      mark_label="W1-Start")
    return dict(_STRUCTURE_DEFAULT)


def _structure_from_series(dates: Sequence[str], closes: Sequence[float]) -> Dict:
    """Struktur-Befund aus EINER Kursreihe: dieselben Pivots/Regeln wie der Count
    (ZigZag), dann `_classify_structure`. Fail-soft -> no_structure-Default."""
    if not closes or len(closes) < 2:
        return dict(_STRUCTURE_DEFAULT)
    pivots = zigzag(list(closes), config.ZIGZAG_WINDOW, list(dates))
    prices = [p.price for p in pivots]
    if len(prices) < 3:
        return dict(_STRUCTURE_DEFAULT)
    return _classify_structure(prices, closes[-1])


def _analyze_from_fetch(ticker: str, fetcher: Optional[Fetcher]) -> Tuple[Optional[Dict], Dict]:
    """Holt EINE Reihe und liefert (Long-Count|None, Struktur-Befund) aus EINEM
    Fetch (kein Doppelabruf). Fail-soft -> (None, no_structure-Default)."""
    if fetcher is None:
        return None, dict(_STRUCTURE_DEFAULT)
    try:
        outcome = fetcher(ticker)
    except Exception:  # noqa: BLE001 — fail-soft
        return None, dict(_STRUCTURE_DEFAULT)
    if outcome is None or outcome.data is None:
        return None, dict(_STRUCTURE_DEFAULT)
    dates, closes = outcome.data
    return _count_from_series(dates, closes), _structure_from_series(dates, closes)


def higher_degree_for(ticker: str, weekly_fetcher: Optional[Fetcher]) -> Optional[Dict]:
    """Zweite Zählung auf WOCHEN-Basis (großer Grad) für EINEN Ticker.

    Unverändertes Verhalten (Delegation an die geteilten Helfer). Wird für die
    finalen Top-5 je Markt UND für Watchlist-Titel (dort als timeframes.week)
    genutzt. Fail-soft -> None.
    """
    return _count_from_fetch(ticker, weekly_fetcher)


def _volume_profile(wave_pivots, setup_name: str,
                    volumes: Optional[Sequence[float]]) -> Dict:
    """Ø-Tagesvolumen je Welle (Pivot-Index bis Pivot-Index, inklusive) + die in der
    Literatur beachteten Verhältnisse. Messfeld v1, bei Anlage eingefroren — REINE
    Messung, kein Score/Ranking. `wave_pivots` = die GEZÄHLTEN Pivots (end_of_w4:
    P0..P4; end_of_w2: P0..P2); `.index` zeigt auf `volumes` (== `closes`-Index).
    Fail-soft: kein/0-Volumen im Segment -> betroffenes Feld null (Division-Guards).

    NICHT-FINIT-HÄRTUNG (27.07.2026): ``s <= 0`` und ``vb <= 0`` waren negierte
    Guards — ``nan <= 0`` ist False, ein NaN rutschte durch und ``vol_ratio_*``
    wurde NaN (in #51 am echten Pfad nachgewiesen). Ein Segment mit auch nur
    EINEM unbrauchbaren Volumen liefert jetzt ``None``: das Messfeld fehlt
    ehrlich, statt einen aus Lücken gemittelten Wert zu behaupten. Für gesunde
    Daten identisch (dort ist jedes Volumen endlich)."""
    out = {"vol_mean": {}, "vol_ratio_w3_w1": None, "vol_ratio_w4_w3": None,
           "vol_ratio_w2_w1": None}
    if not volumes:
        return out
    n = len(volumes)

    def seg_mean(pa, pb) -> Optional[float]:
        i0, i1 = getattr(pa, "index", None), getattr(pb, "index", None)
        if not (isinstance(i0, int) and isinstance(i1, int)):
            return None
        lo, hi = min(i0, i1), max(i0, i1)
        if lo < 0 or hi >= n:
            return None
        seg = volumes[lo:hi + 1]
        if not seg or not all(finite(v) for v in seg):
            return None            # Lücke im Segment -> kein gemittelter Wert
        s = sum(seg)
        if s <= 0:
            return None
        return round(s / len(seg), 2)

    # Wellen W1=P0->P1, W2=P1->P2, (W3=P2->P3, W4=P3->P4). Max 4 Wellen (end_of_w4).
    waves = min(len(wave_pivots) - 1, 4)
    vm = {f"w{m}": seg_mean(wave_pivots[m - 1], wave_pivots[m])
          for m in range(1, waves + 1)}
    out["vol_mean"] = vm

    def ratio(a: str, b: str) -> Optional[float]:
        va, vb = vm.get(a), vm.get(b)
        if not finite(va) or not finite(vb) or vb <= 0:
            return None
        return round(va / vb, 4)

    if setup_name == "end_of_w4":
        out["vol_ratio_w3_w1"] = ratio("w3", "w1")
        out["vol_ratio_w4_w3"] = ratio("w4", "w3")
    else:  # end_of_w2
        out["vol_ratio_w2_w1"] = ratio("w2", "w1")
    return out


def build_candidate(
    ticker: str, dates: List[str], closes: List[float],
    exclude_target_reached: bool = True,
    volumes: Optional[Sequence[float]] = None,
) -> Tuple[Optional[Dict], Optional[str], str]:
    """Baut einen Kandidaten-Eintrag.

    Returns (entry, reason, detail):
      - Erfolg -> (entry, None, "")
      - Skip   -> (None, reason, detail-fürs-Log)
    Die Entscheidungslogik ist unverändert; es wird nur der Grund + ein
    Detail fürs Log ergänzt.

    exclude_target_reached: Markt-Pipeline (Default True) verwirft Setups, deren
    Kurs die Zielzone bereits erreicht hat (close >= target_zone.low) VOR dem
    Ranking (Skip target_exceeded). Die Watchlist ruft mit False auf — dort bleibt
    das Setup sichtbar (Badge aus #28 markiert den Zustand).
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

    # Zielzone erreicht = nicht mehr handelbar -> VOR dem Ranking verwerfen
    # (Rang 6+ rückt nach). NUR Markt-Pipeline (exclude_target_reached=True); die
    # Watchlist ruft mit False auf und zeigt das Setup weiter (Badge markiert es).
    # Schwelle = target_zone.low (identisch zur #28-Guard-/Entry-Regel-Schwelle).
    tlow = setup["target_zone"]["low"]
    if exclude_target_reached and close >= tlow:
        return (
            None,
            TARGET_EXCEEDED,
            f"{setup['setup']} close={round(close, 4)} >= target_zone.low={tlow} "
            f"(Zielzone erreicht, nicht mehr handelbar)",
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
        # Konfluenz-Marken (additiv, REINE Anzeige/Messung — NACH dem Score, kein
        # Einfluss auf score_heuristic/Ranking). Aus denselben `closes` (keine
        # neuen Fetches). Gilt für Markt-Top-5 UND Watchlist.
        "confluence": compute_confluence(closes, setup["target_zone"],
                                         setup["invalidation_price"]),
        "status": config.CARD_STATUS,
    }
    # Volumen-Profil (Messfeld v1, additiv, NACH dem Score — kein Einfluss auf
    # score_heuristic/Ranking). Aus DEMSELBEN Download (volumes), kein Extra-Call.
    # Die gezählten Pivots sind die letzten k (== chart_points-Zählstruktur).
    _vp = _volume_profile(pivots[-k:], setup["setup"], volumes)
    entry["vol_profile"] = _vp["vol_mean"]
    entry["vol_ratio_w3_w1"] = _vp["vol_ratio_w3_w1"]
    entry["vol_ratio_w4_w3"] = _vp["vol_ratio_w4_w3"]
    entry["vol_ratio_w2_w1"] = _vp["vol_ratio_w2_w1"]
    # Ambiguitäts-Ausweis v1 (additiv, NACH dem Score — kein Score/Ranking-Einfluss):
    # Anzahl valider Long-Counts (max 2) + beste Alternative. Primär byte-identisch.
    total, alt = ambiguity_fields(pivots, close)
    entry["valid_count_total"] = total
    entry["alt_count"] = alt
    # Ambiguität v2 (additiv, ZUSÄTZLICH zu v1): erweitertes Vokabular inkl. ABC.
    total_v2, alt_v2 = ambiguity_v2_fields(pivots, close)
    entry["valid_count_total_v2"] = total_v2
    entry["alt_count_v2"] = alt_v2
    return entry, None, ""


def _scan_market(
    universe: Sequence[str], fetcher: Fetcher,
    price_sink: Optional[Dict[str, Tuple[List[str], List[float]]]] = None,
    volume_sink: Optional[Dict[str, List[float]]] = None,
) -> Tuple[List[Dict], Dict[str, int], List[Tuple[str, str, str]], List[Tuple[str, str]]]:
    """Verarbeitet ein Universum (fail-soft je Ticker) — ohne I/O/Logging.

    Ausgelagert aus build_market, damit die Skip-Zähler (inkl.
    short_setup_excluded) direkt unit-testbar sind. Verhalten identisch.

    Returns:
        (candidates, reason_counts, first_samples, dead_tickers, bad_bars)
        candidates: unsortierte Long-Kandidaten
        reason_counts: Zähler je Skip-Grund (SKIP_REASONS)
        first_samples: erste 3 Skips (ticker, reason, detail) fürs Log
        dead_tickers: (ticker, reason) für JEDEN empty_data/fetch_error —
            Listen-Hygiene: benennt tote/fehlerhafte Symbole namentlich.
        letztes_bar: jüngster gültiger Handelstag im Markt (informativ)
        bad_bars: (ticker, dropped, bad_vol, dropped_dates, last, mid) je Ticker mit
            nicht-finiten Rohdaten (Nicht-finit-Härtung, 27.07.2026).
    """
    candidates: List[Dict] = []
    reason_counts: Dict[str, int] = {r: 0 for r in SKIP_REASONS}
    first_samples: List[Tuple[str, str, str]] = []  # (ticker, reason, detail)
    dead_tickers: List[Tuple[str, str]] = []         # (ticker, reason) hygiene
    # Nicht-finit-Härtung (27.07.2026): je Ticker die beim Parsen verworfenen
    # Bars. Soll im Normalbetrieb LEER sein — jeder Eintrag ist ein Hinweis auf
    # eine löchrige Kursquelle und landet im Lauf-Status.
    # (ticker, dropped, bad_vol, dropped_dates, dropped_last_row, dropped_mid_row)
    bad_bars: List[Tuple[str, int, int, Tuple[str, ...], int, int]] = []
    # Jüngster Handelstag, der in diesem Markt ÜBERHAUPT als gültiger Bar
    # angekommen ist (30.07.2026, rein informativ). Er kann zwischen den
    # Märkten abweichen — abhängig davon, was die Quelle zum Abrufzeitpunkt
    # liefert. Ohne diese Angabe war nur aus `price_path` rekonstruierbar, von
    # welchem Tag die Preise stammen. Ändert NICHTS an der Zählung.
    letztes_bar: Optional[str] = None
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

        # Verworfene Bars IMMER erfassen — auch wenn der Ticker danach ohnehin
        # übersprungen wird (gerade dann ist die Zahl interessant).
        if outcome.dropped_bars or outcome.invalid_volume_bars:
            bad_bars.append((ticker, outcome.dropped_bars,
                             outcome.invalid_volume_bars,
                             outcome.dropped_dates,
                             outcome.dropped_last_row,
                             outcome.dropped_mid_row))

        if outcome.data is None:
            _record_skip(ticker, outcome.reason or FETCH_ERROR, outcome.detail)
            continue

        dates, closes = outcome.data
        if dates and (letztes_bar is None or dates[-1] > letztes_bar):
            letztes_bar = dates[-1]
        # Kursdaten für die Forward-Sammlung mitnehmen (kein Re-Fetch): ALLE
        # erfolgreich geladenen Ticker, damit auch aus Top-5 gefallene Records
        # ausreifen können.
        if price_sink is not None:
            price_sink[ticker] = (dates, closes)
        # Volumen (Messfeld v1) parallel mitnehmen — additiv, kein Re-Fetch.
        if volume_sink is not None and outcome.volumes is not None:
            volume_sink[ticker] = outcome.volumes
        entry, reason, detail = build_candidate(ticker, dates, closes,
                                                volumes=outcome.volumes)
        if entry is None:
            _record_skip(ticker, reason or NO_VALID_COUNT, detail)
            continue
        candidates.append(entry)

    return (candidates, reason_counts, first_samples, dead_tickers, bad_bars,
            letztes_bar)


def build_market(
    market_key: str, fetcher: Fetcher, weekly_fetcher: Optional[Fetcher] = None,
    price_sink: Optional[Dict[str, Tuple[List[str], List[float]]]] = None,
    volume_sink: Optional[Dict[str, List[float]]] = None,
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

    (candidates, reason_counts, first_samples, dead_tickers, bad_bars,
     _letztes_bar) = _scan_market(
        universe, fetcher, price_sink, volume_sink)

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
        f"short_setup_excluded={reason_counts[SHORT_SETUP_EXCLUDED]}, "
        f"target_exceeded={reason_counts[TARGET_EXCEEDED]}"
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
    # Nicht-finit-Härtung: verworfene Bars namentlich. Soll 0 sein.
    _dropped_total = sum(b[1] for b in bad_bars)
    _badvol_total = sum(b[2] for b in bad_bars)
    # Wo lagen die verworfenen Zeilen? Das Datums-Histogramm ist die Antwort auf
    # „aktueller Tag oder echte Lücke": steht dort EIN Datum mit der Anzahl der
    # betroffenen Ticker, ist es eine unfertige Tages-Zeile.
    _dropped_dates: Dict[str, int] = {}
    for b in bad_bars:
        for d in b[3]:
            _dropped_dates[d] = _dropped_dates.get(d, 0) + 1
    _dropped_last = sum(b[4] for b in bad_bars)
    _dropped_mid = sum(b[5] for b in bad_bars)
    if bad_bars:
        _log(f"[elliott][diag] {market_key} nicht-finite Rohdaten: "
             f"{_dropped_total} Bars verworfen, {_badvol_total} ohne Volumen "
             f"-> " + ", ".join(f"{b[0]}(-{b[1]}/{b[2]})" for b in bad_bars))
        _log(f"[elliott][diag] {market_key} verworfene Bars nach Datum: "
             f"{dict(sorted(_dropped_dates.items()))} "
             f"(letzte Zeile {_dropped_last}, mitten in der Reihe {_dropped_mid})")

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
            # Nicht-finit-Härtung (27.07.2026): beim Parsen verworfene Bars.
            # Soll im Normalbetrieb 0/leer sein — sichtbar im Lauf-Status.
            "dropped_bars": _dropped_total,
            "invalid_volume_bars": _badvol_total,
            "bad_bar_tickers": [
                {"ticker": b[0], "dropped": b[1], "invalid_volume": b[2],
                 # Nur Diagnose (30.07.2026), gekappt: die ersten Daten reichen,
                 # um „aktueller Tag" von „Lücke in der Mitte" zu unterscheiden.
                 "dropped_dates": list(b[3][:MAX_DROPPED_DATES]),
                 "dropped_last_row": b[4], "dropped_mid_row": b[5]}
                for b in bad_bars
            ],
            # Markt-Ebene: EIN Blick genügt. Ein einziges Datum mit der Anzahl
            # betroffener Ticker = unfertige Tages-Zeile; verstreute Daten oder
            # `dropped_mid_row > 0` = echte Lücken in der Quelle.
            # Von WELCHEM Handelstag stammen die Preise dieses Marktes?
            # Rein informativ und additiv (30.07.2026). Die Märkte können hier
            # auseinanderliegen — siehe Registry-Notiz vom 30.07.
            "last_bar_date": _letztes_bar,
            "dropped_bar_dates": dict(sorted(_dropped_dates.items())),
            "dropped_last_row": _dropped_last,
            "dropped_mid_row": _dropped_mid,
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
        # Struktur-Befund je Zeitebene (NUR Watchlist-Diagnostik, additiv). Sagt
        # ehrlich, WO der Titel in der Elliott-Struktur steht, auch ohne Long-
        # Setup (statt bloßem „kein Count"). Default null -> Fehler-Karte fail-soft.
        "structure": {"day": None, "week": None, "month": None},
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
    volume_sink: Optional[Dict[str, List[float]]] = None,
) -> Dict:
    """Volle Analyse EINES Watchlist-Tickers. Wiederverwendet bereits geladene
    Kurse aus price_sink; sonst frischer Fetch. Immer eine Karte (fail-soft).

    Watchlist-Titel bekommen zusätzlich die Multi-Timeframe-Analyse
    (timeframes = Tag/Woche/Monat). Tag reift aus der bereits geladenen Tagesreihe
    (kein Extra-Fetch); Woche + Monat kosten je einen Fetch (bis zu +2 pro Titel,
    NUR im Watchlist-Zweig). Der Wochen-Count wird EINMAL geholt und dient sowohl
    higher_degree (unverändert) als auch timeframes.week (kein Doppel-Fetch)."""
    data = price_sink.get(ticker) if price_sink else None
    # Volumen (Messfeld v1) aus dem Sink wiederverwenden (kein Re-Fetch); bei
    # frischem Abruf unten aus dem Outcome. Fehlt es -> None (Profil wird null).
    volumes = volume_sink.get(ticker) if volume_sink else None
    if data is None:
        outcome = fetcher(ticker)
        if outcome.reason is not None or outcome.data is None:
            # Kein Daten -> Fehler-Karte; timeframes bleiben alle null (aus Base):
            # Woche/Monat werden NICHT extra probiert (der Tagesabruf scheiterte
            # bereits — kein Grund, zwei weitere Fehl-Fetches zu erzwingen).
            return _wl_error_entry(ticker, outcome.reason, outcome.detail)
        dates, closes = outcome.data
        volumes = outcome.volumes
        if price_sink is not None:
            price_sink[ticker] = (dates, closes)
        if volume_sink is not None and outcome.volumes is not None:
            volume_sink[ticker] = outcome.volumes
    else:
        dates, closes = data

    # Je Zeitebene EIN Fetch -> Long-Count UND Struktur-Befund (kein Doppelabruf).
    # Tag reust die bereits geladene Tagesreihe.
    week_count, week_struct = _analyze_from_fetch(ticker, weekly_fetcher)
    month_count, month_struct = _analyze_from_fetch(ticker, monthly_fetcher)
    timeframes = {
        "day": _count_from_series(dates, closes),
        "week": week_count,
        "month": month_count,
    }
    structure = {
        "day": _structure_from_series(dates, closes),
        "week": week_struct,
        "month": month_struct,
    }

    # Watchlist zeigt ALLES — auch Setups mit erreichter Zielzone (Badge markiert
    # sie); daher target_exceeded-Filter hier AUS (nur die Markt-Top-5 filtern).
    entry, reason, detail = build_candidate(ticker, dates, closes,
                                            exclude_target_reached=False,
                                            volumes=volumes)
    if entry is not None:
        # Long-Setup vorhanden -> volle Karte inkl. großem Grad (Wochen).
        entry["higher_degree"] = week_count          # == vorher (higher_degree_for)
        entry["timeframes"] = timeframes
        entry["structure"] = structure
        entry["watchlist"] = True
        entry["wl_status"] = "setup"
        entry["note"] = ""
        entry["reason"] = ""
        return entry
    e = _wl_no_setup_entry(ticker, dates, closes, reason, detail)
    e["timeframes"] = timeframes
    e["structure"] = structure
    return e


def build_watchlist(
    fetcher: Fetcher, weekly_fetcher: Optional[Fetcher] = None,
    monthly_fetcher: Optional[Fetcher] = None,
    price_sink: Optional[Dict[str, Tuple[List[str], List[float]]]] = None,
    tickers: Optional[Sequence[str]] = None,
    volume_sink: Optional[Dict[str, List[float]]] = None,
) -> Dict:
    """Baut die Watchlist-Sektion (separat von den Märkten, ranking-neutral)."""
    tks = list(tickers) if tickers is not None else load_watchlist()
    entries: List[Dict] = []
    counts = {"setup": 0, "no_setup": 0, "error": 0}
    for tk in tks:
        e = build_watchlist_entry(tk, fetcher, weekly_fetcher, monthly_fetcher,
                                  price_sink, volume_sink)
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
    volume_sink: Optional[Dict[str, List[float]]] = None,
) -> Dict:
    """Baut das komplette Report-Objekt (deterministisch bei festem Input).

    price_sink (optional): wird mit {ticker: (dates, closes)} aller erfolgreich
    geladenen Ticker gefüllt — für die Forward-Sammlung, ohne Re-Fetch.
    volume_sink (optional): analog {ticker: volumes} (Messfeld v1), ebenfalls
    ohne Re-Fetch — nur für die Anzeige/Messung, NICHT für die Sammlung nötig.

    monthly_fetcher (optional): NUR für die Watchlist (Monatsgrad). Die
    Markt-Pipeline (Top-5) bekommt ihn NICHT — sie bleibt Tag+Woche.
    """
    markets: Dict[str, Dict] = {}
    for key in config.MARKETS:
        markets[key] = build_market(key, fetcher, weekly_fetcher, price_sink,
                                    volume_sink)
    # Watchlist NACH den Märkten und in EIGENEM Feld -> Ranking unberührt, und
    # die Forward-Sammlung (liest nur markets[].candidates) sieht sie nie.
    watchlist = build_watchlist(fetcher, weekly_fetcher, monthly_fetcher,
                                price_sink, volume_sink=volume_sink)
    return {
        "schema_version": config.SCHEMA_VERSION,
        "run_timestamp_utc": run_timestamp_utc,
        "generator": "elliott_pipeline",
        "disclaimer": "Heuristische Elliott-Wellen-Auszählung, unvalidiert. Keine Anlageberatung.",
        "markets": markets,
        "watchlist": watchlist,
    }


def write_report(report: Dict) -> List[Path]:
    """Schreibt den Report kanonisch + gespiegelt (Pages /docs).

    ATOMAR (Guardian-Nit 27.07.): erst in eine Temp-Datei im SELBEN Verzeichnis
    schreiben, dann ``os.replace`` — ein Abbruch mitten im Schreiben (Timeout,
    OOM) kann so keine halbfertige `report.json` hinterlassen; entweder steht
    der alte oder der neue Stand da. Vorher truncierte ``open(..., "w")``
    die gültige Datei sofort. Der Health-Check schreibt den Report ein ZWEITES
    Mal (additiver `health`-Block) — er verdoppelt das Zeitfenster, also wird
    es hier geschlossen statt bloß dokumentiert. Ergebnis-Bytes unverändert.
    """
    written: List[Path] = []
    for rel in (config.REPORT_PATH, config.REPORT_PATH_PUBLISHED):
        path = REPO_ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)   # atomar auf demselben Dateisystem
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
    volume_sink: Dict[str, List[float]] = {}  # Messfeld v1 (Volumen), kein Re-Fetch
    _t0 = time.monotonic()
    report = build_report(fetcher, ts, get_weekly_fetcher(),
                          get_monthly_fetcher(), price_sink, volume_sink)
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
    # Agent-Kommentar v1 (additiv, REINE Kommentar-Ebene): läuft NACH build_report
    # — also nach Sortierung, Top-N-Schnitt und allen Filtern — und schreibt nur
    # `agent_comment` auf die finalen Markt-Top-5 (Watchlist ausgenommen). Ohne
    # ANTHROPIC_API_KEY ein no-op; jeder Fehler ist gekapselt (Report geht raus).
    try:
        import agent_comment as ac  # noqa: WPS433 — lazy, hält Tests/Offline leicht

        ac.annotate_agent_comments(report, os.environ.get("ANTHROPIC_API_KEY", ""), ts)
    except Exception as exc:  # noqa: BLE001
        _log(f"[elliott] Agent-Kommentar übersprungen (fail-soft): "
             f"{type(exc).__name__}: {exc}")

    # Health-Check Stufe 2, Teil 1 von 3 — NICHT-FINIT-PRÜFUNG des Reports.
    # MUSS hier stehen: nach dem Report-Bau, aber VOR der Serialisierung. Sonst
    # steht im File bereits literales `NaN` (kein gültiges JSON, der Browser
    # wirft beim Parsen) und der Befund käme im selben Lauf zu spät. Der
    # Vorlauf-Report wird ebenfalls JETZT gelesen — gleich überschreibt ihn
    # write_report, und die Delta-Regel (tote Ticker) braucht ihn.
    _hc_prev_report = None
    _hc_finite: list = []
    try:
        import health_check as hc  # noqa: WPS433 — lazy wie agent_comment

        _hc_prev_report = hc.load_previous_report()
        _hc_finite = hc.check_finite(report, "report")
    except Exception as exc:  # noqa: BLE001 — Prüfung darf den Lauf nie brechen
        _log(f"[elliott] Health-Check (Report-Finit) übersprungen (fail-soft): "
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
    run_date = report["run_timestamp_utc"][:10]
    # Health-Check-Signaturen: bleiben None, wenn der Sammel-Schritt scheitert
    # — dann meldet Regel 4 bewusst NICHTS (der Fehler steht schon im Log,
    # ein Phantom-Alarm wäre Rauschen).
    _hc_sig_before = _hc_sig_after = None
    # Zweiter Lauf am SELBEN Kalendertag (Retry-Dispatch)? Dann ist ein
    # Sammlungs-„Stillstand" das korrekte Verhalten — Regel 4 schweigt.
    # VOR dem Update lesen: update_forward_collection setzt last_run_date neu.
    _hc_same_day = False
    # Sammlungs-Zaehler fuer den Herzschlag (None = Sammel-Schritt gescheitert;
    # dann nennt der OK-Push die Sammlung schlicht nicht, statt zu raten).
    _hc_counts = None
    try:
        regimes = fc.market_regimes(fetcher is fetch_synthetic)
        coll = fc.load_collection()
        _hc_same_day = coll.get("last_run_date") == run_date
        try:
            import health_check as hc  # noqa: WPS433

            _hc_sig_before = hc.collection_signature(coll)
        except Exception:  # noqa: BLE001
            _hc_sig_before = None
        fc.update_forward_collection(coll, report, price_sink, regimes, run_date, ts)
        # Health-Check Stufe 2, Teil 2 von 3 — NICHT-FINIT-PRÜFUNG der Sammlung,
        # ebenfalls VOR write_collection (gleiche Begründung wie beim Report).
        try:
            import health_check as hc  # noqa: WPS433

            _hc_finite += hc.check_finite(coll, "collection")
            _hc_sig_after = hc.collection_signature(coll)
        except Exception as exc:  # noqa: BLE001
            _log(f"[elliott] Health-Check (Sammlung-Finit) übersprungen "
                 f"(fail-soft): {type(exc).__name__}: {exc}")
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
        _hc_counts = {"collected": n, "matured": matured, "evaluable": evaluable}
        # EINE ZÄHL-QUELLE (29.07.2026). Die Aggregate stehen ab jetzt IM Report.
        # Vorher rechnete das Frontend sie in JavaScript nach (`_evalCounts`) —
        # dieselbe Registry-Regel ein zweites Mal, in einer zweiten Sprache.
        # Genau daran ist `notify.py` schon einmal auseinandergelaufen (#57:
        # zählte `gereift` statt `auswertbar`). Hier wird `eval_counts` nur
        # DURCHGEREICHT, nicht kopiert — additiv, ohne Score-/Ranking-Wirkung.
        report["validation"] = {
            "collected": n,
            "matured": matured,
            "evaluable": evaluable,
            "eval_min_n": fc.EVAL_MIN_N,
        }
        _log(f"[elliott] Forward-Sammlung: {n} gesammelt · {matured} gereift · "
             f"{evaluable} auswertbar (Auswertung ab n>={fc.EVAL_MIN_N}, PRU-Guard) "
             f"· Regime {regimes}")
    except Exception as exc:  # noqa: BLE001 — Sammlung darf Report nie brechen
        _log(f"[elliott] Forward-Sammlung übersprungen (fail-soft): "
             f"{type(exc).__name__}: {exc}")

    # Health-Check Stufe 2, Teil 3 von 3 — restliche Regeln, Push, Transparenz.
    # GANZ am Ende, weil Regel 4 den Sammlungs-Stand NACH dem Update braucht.
    # Der Report wurde oben BEREITS geschrieben (unverändert wie bisher); hier
    # kommt ein ZWEITER Schreibvorgang, der nur den additiven `health`-Block
    # ergänzt. Bewusst so herum: scheitert irgendetwas hier, liegt der
    # vollständige Report längst auf Platte — der Lauf bricht nie ab und
    # veröffentlicht nie weniger als vorher.
    try:
        import health_check as hc  # noqa: WPS433

        health = hc.run(
            report, _hc_prev_report, _hc_finite, _hc_sig_before, _hc_sig_after,
            has_agent_key=bool(os.environ.get("ANTHROPIC_API_KEY", "")),
            topic=os.environ.get("NTFY_TOPIC", ""),
            run_date=run_date, now_iso=ts, now=datetime.now(timezone.utc),
            same_day_rerun=_hc_same_day, counts=_hc_counts,
        )
        _log(f"[elliott] Health-Check: Status {health['status']} "
             f"({len(health['findings'])} Befund(e))")
    except Exception as exc:  # noqa: BLE001 — Selbstüberwachung nie den Lauf
        _log(f"[elliott] Health-Check übersprungen (fail-soft): "
             f"{type(exc).__name__}: {exc}")

    # ABSCHLUSS-SCHREIBVORGANG für die beiden additiven Blöcke `validation`
    # (Sammlung) und `health` (Selbstüberwachung). Bewusst AUSSERHALB beider
    # try-Blöcke: vorher hing das Schreiben am Health-Check — scheiterte der,
    # fehlte auch alles andere Additive im File. Der vollständige Report liegt
    # seit `written` ohnehin auf Platte; dieser Vorgang ERGÄNZT nur und kann
    # nie weniger schreiben als vorher.
    try:
        write_report(report)
    except Exception as exc:  # noqa: BLE001 — der Report von oben steht bereits
        _log(f"[elliott] Nachtrag (validation/health) übersprungen (fail-soft): "
             f"{type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
