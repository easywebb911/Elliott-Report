"""Forward-Sammlung für die Score-Validierung (siehe docs/validation_registry.md).

Separat von report.json. Sammelt je Ticker-EPISODE forward-only Kennzahlen über
10 Handelstage; reift offene Records gegen die (ohnehin geladenen) Kursdaten der
Folgetage. Reine Zähler nach außen — KEINE Zwischenergebnisse/Trefferquoten vor
n >= EVAL_MIN_N.

Design-Prinzipien:
- Fail-soft: ein Sammel-Fehler darf den Report NIE brechen (der Aufrufer schreibt
  report.json zuerst und kapselt die Sammlung in try/except).
- Deterministisch/idempotent: mature_record rechnet je Lauf aus der vollen
  Historie neu — gleiche Kursdaten -> gleiche Kennzahlen.
- Kein Survivorship-Bias: offene Records reifen aus, auch wenn der Ticker aus den
  Top-5 gefallen ist.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

FORWARD_PATH = "data/forward_collection.json"
FORWARD_PATH_PUBLISHED = "docs/data/forward_collection.json"

HORIZON_DAYS = 10          # Reifungs-Horizont in Handelstagen
EVAL_MIN_N = 100           # Auswertung erst ab so vielen gereiften Setups
SCHEMA_VERSION = 1

# Regime-Index je Markt (200-Tage-Linie).
REGIME_INDEX = {"US": "SPY", "DE": "^GDAXI"}


# ---------------------------------------------------------------------------
# I/O (fail-soft)
# ---------------------------------------------------------------------------
def load_collection() -> Dict:
    """Lädt die Sammlung (fail-soft: leere Struktur bei fehlender/kaputter Datei)."""
    empty = {"schema_version": SCHEMA_VERSION, "last_run_date": None,
             "updated_utc": None, "records": []}
    try:
        path = REPO_ROOT / FORWARD_PATH
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict) or "records" not in data:
            return empty
        return data
    except Exception:  # noqa: BLE001 — fail-soft
        return empty


def write_collection(coll: Dict) -> List[Path]:
    """Schreibt die Sammlung kanonisch + gespiegelt (wie report.json)."""
    written: List[Path] = []
    for rel in (FORWARD_PATH, FORWARD_PATH_PUBLISHED):
        path = REPO_ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(coll, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        written.append(path)
    return written


# ---------------------------------------------------------------------------
# Regime (200-Tage-Linie)
# ---------------------------------------------------------------------------
def compute_regime(index_closes: Sequence[float]) -> str:
    """risk_on/risk_off aus Schlusskurs vs. 200-Tage-SMA. Sonst 'unknown'."""
    if not index_closes or len(index_closes) < 200:
        return "unknown"
    sma200 = sum(index_closes[-200:]) / 200.0
    return "risk_on" if index_closes[-1] > sma200 else "risk_off"


def market_regimes(offline: bool) -> Dict[str, str]:
    """Regime je Markt. Fail-soft -> 'unknown'. Offline -> deterministisch."""
    out: Dict[str, str] = {}
    for mk, sym in REGIME_INDEX.items():
        if offline:
            out[mk] = "risk_on"  # deterministisch für Offline/Dev/Tests
            continue
        out[mk] = "unknown"
        try:
            import yfinance as yf  # noqa: WPS433

            df = yf.download(sym, period="2y", interval="1d",
                             auto_adjust=True, progress=False, threads=False)
            if df is None or getattr(df, "empty", True):
                continue
            if getattr(df.columns, "nlevels", 1) > 1:  # MultiIndex-Lesson
                df = df.copy()
                df.columns = df.columns.get_level_values(0)
            if "Close" not in df.columns:
                continue
            closes = [float(x) for x in df["Close"].dropna().tolist()]
            out[mk] = compute_regime(closes)
        except Exception:  # noqa: BLE001 — fail-soft
            out[mk] = "unknown"
    return out


# ---------------------------------------------------------------------------
# Reifung (pure) — je Lauf aus der vollen Historie neu berechnet
# ---------------------------------------------------------------------------
def mature_record(rec: Dict, dates: Sequence[str], closes: Sequence[float],
                  now_iso: str) -> None:
    """Füllt die forward-Kennzahlen aus den Kursen NACH first_seen_date.

    Binär (long): target_hit = Basiszone (low) erreicht VOR Invalidierung;
    invalidated = Invalidierung zuerst gerissen; ext_hit = Extension-Zone (low)
    vor Invalidierung. Nach HORIZON_DAYS Handelstagen -> matured.
    """
    try:
        idx = list(dates).index(rec["first_seen_date"])
    except ValueError:
        return  # Einstiegstag (noch) nicht in den Daten -> diesen Lauf überspringen
    fwd = list(closes)[idx + 1: idx + 1 + HORIZON_DAYS]
    fwd_dates = list(dates)[idx + 1: idx + 1 + HORIZON_DAYS]
    rec["last_update_utc"] = now_iso
    rec["bars_elapsed"] = len(fwd)
    # Kursverlauf NACH dem Einstieg (max HORIZON_DAYS Werte). Wird je Lauf aus
    # der vollen Historie neu aufgebaut -> deterministisch/idempotent.
    rec["price_path"] = [{"date": d, "close": round(float(c), 4)}
                         for d, c in zip(fwd_dates, fwd)]
    if not fwd:
        rec["matured"] = False
        return

    entry = rec["entry_close"]
    inval = rec["invalidation_price"]
    tlow = rec["target_zone"]["low"]
    elow = rec["target_zone_extended"]["low"]

    maxc = minc = entry
    inval_day = target_day = ext_day = None
    for i, c in enumerate(fwd):
        if c > maxc:
            maxc = c
        if c < minc:
            minc = c
        if inval_day is None and c <= inval:
            inval_day = i
        if target_day is None and c >= tlow:
            target_day = i
        if ext_day is None and c >= elow:
            ext_day = i

    matured = len(fwd) >= HORIZON_DAYS
    resolved = matured or target_day is not None or inval_day is not None
    if resolved:
        # Gleichstand am selben Tag (target_day == inval_day): Close-only-Daten
        # verraten die Intraday-Reihenfolge nicht. Konservativ (worst-case) zählt
        # der Tag dann als Invalidierung, NICHT als Treffer — ein "hit" wird nie
        # aufgebläht. Deshalb: invalidated mit <= (schlägt bei Gleichstand),
        # target_hit/ext_hit mit striktem < (verlieren bei Gleichstand).
        rec["target_hit"] = 1 if (target_day is not None and (inval_day is None or target_day < inval_day)) else 0
        rec["invalidated"] = 1 if (inval_day is not None and (target_day is None or inval_day <= target_day)) else 0
        rec["ext_hit"] = 1 if (ext_day is not None and (inval_day is None or ext_day < inval_day)) else 0

    rec["max_gain_10d"] = round((maxc - entry) / entry * 100.0, 4) if entry else None
    rec["max_drawdown_10d"] = round((minc - entry) / entry * 100.0, 4) if entry else None
    risk = entry - inval
    rec["r_multiple"] = round((maxc - entry) / risk, 4) if risk > 0 else None
    rec["matured"] = matured


# ---------------------------------------------------------------------------
# Episoden-Anlage + Reifung (pure)
# ---------------------------------------------------------------------------
def _new_record(entry: Dict, market: str, first_seen: str, regime: str,
                run_date: str, now_iso: str) -> Dict:
    return {
        "episode_id": f"{entry['ticker']}@{first_seen}",
        "ticker": entry["ticker"],
        "market": market,
        "first_seen_date": first_seen,
        "entry_close": entry["close"],
        "score_heuristic": entry["score_heuristic"],
        "count_label": entry.get("count_label", ""),
        "target_zone": entry["target_zone"],
        "target_zone_extended": entry["target_zone_extended"],
        "invalidation_price": entry["invalidation_price"],
        "direction": entry.get("direction", "long"),
        "regime": regime,
        # Point-in-time eingefrorene Zählung: die Pivots (Datum/Kurs/Art) und die
        # Wellen-Ziffern-Zuordnung des Setups zum Anlage-Zeitpunkt. Werden bei
        # späteren (Reifungs-)Läufen NIE geändert -> die damalige Auszählung
        # bleibt exakt verortbar. Fail-soft: fehlen sie im Kandidaten, leere Liste.
        "chart_points": entry.get("chart_points", []),
        "count_wave_labels": entry.get("count_wave_labels", []),
        # Wird bei der Reifung mit den Folgetags-Schlusskursen gefüllt (max 10).
        "price_path": [],
        "last_seen_top5_date": run_date,
        "created_utc": now_iso,
        "bars_elapsed": 0,
        "matured": False,
        "target_hit": None,
        "ext_hit": None,
        "invalidated": None,
        "max_gain_10d": None,
        "max_drawdown_10d": None,
        "r_multiple": None,
        "last_update_utc": now_iso,
    }


def update_forward_collection(
    coll: Dict,
    report: Dict,
    price_data: Dict[str, Tuple[Sequence[str], Sequence[float]]],
    regimes: Dict[str, str],
    run_date: str,
    now_iso: str,
) -> Dict:
    """Legt neue Episoden an, reift offene Records, aktualisiert Metadaten.

    Episoden-Regel: ein Record je Ticker-Episode. Konsekutive Top-5-Tage
    verlängern dieselbe Episode (kein Doppel-Record). Wiederauftauchen nach
    Verschwinden (last_seen != vorheriges Lauf-Datum) = neue Episode. Offene
    Records reifen unabhängig von der Top-5-Zugehörigkeit aus.
    """
    records: List[Dict] = coll.setdefault("records", [])
    prev_run_date = coll.get("last_run_date")

    # 1) Anlegen / Verlängern für die heutigen Top-5.
    for mk, market in report.get("markets", {}).items():
        for entry in market.get("candidates", []):
            ticker = entry["ticker"]
            active = next(
                (r for r in records
                 if r["ticker"] == ticker and not r["matured"]
                 and r.get("last_seen_top5_date") == prev_run_date),
                None,
            )
            if active is not None:
                active["last_seen_top5_date"] = run_date  # gleiche Episode
                continue
            pdata = price_data.get(ticker)
            first_seen = pdata[0][-1] if (pdata and len(pdata[0])) else run_date
            records.append(
                _new_record(entry, mk, first_seen, regimes.get(mk, "unknown"),
                            run_date, now_iso)
            )

    # 2) ALLE offenen Records reifen (auch aus Top-5 gefallene).
    for r in records:
        if r["matured"]:
            continue
        pdata = price_data.get(r["ticker"])
        if pdata:
            mature_record(r, pdata[0], pdata[1], now_iso)

    coll["schema_version"] = SCHEMA_VERSION
    coll["last_run_date"] = run_date
    coll["updated_utc"] = now_iso
    return coll


def counts(coll: Dict) -> Tuple[int, int]:
    """(gesammelt, gereift)."""
    records = coll.get("records", [])
    return len(records), sum(1 for r in records if r.get("matured"))


def appearance_count(coll: Dict, ticker: str) -> int:
    """Wie oft ``ticker`` als Top-5-Kandidat erschienen ist — **Episoden**, nicht
    Tage — inkl. der AKTUELLEN Erscheinung.

    Ein Record = eine Episode. Zum Report-Bauzeitpunkt ist die aktuelle
    Erscheinung noch NICHT in der Sammlung (die wird erst nach write_report
    aktualisiert). Deshalb: Zahl der vorhandenen Episoden + 1, ES SEI DENN die
    aktuelle Erscheinung verlängert eine bereits offene Episode (Ticker war schon
    im vorherigen Lauf Top-5) — dann ist sie bereits gezählt. Die
    Fortsetzungs-Prüfung spiegelt exakt die ``active``-Erkennung in
    ``update_forward_collection`` (kein Doppelzählen)."""
    records = coll.get("records", [])
    episodes = sum(1 for r in records if r.get("ticker") == ticker)
    prev_run_date = coll.get("last_run_date")
    continues = any(
        r.get("ticker") == ticker and not r.get("matured")
        and r.get("last_seen_top5_date") == prev_run_date
        for r in records
    )
    return episodes if continues else episodes + 1


def annotate_appearance_counts(coll: Dict, report: Dict) -> None:
    """Setzt je Markt-Top-5-Kandidat additiv ``appearance_count``. In-place.

    NUR für markets[].candidates — Watchlist-Karten bekommen KEINEN Zähler
    (nicht Teil der Population). Reine Anzeige: berührt Score/Ranking/Sammlung
    nicht."""
    for market in report.get("markets", {}).values():
        for entry in market.get("candidates", []):
            entry["appearance_count"] = appearance_count(coll, entry["ticker"])
