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

import config
from numeric import all_finite, finite  # EIN Finit-Prädikat (siehe numeric.py)
from zigzag import zigzag

REPO_ROOT = Path(__file__).resolve().parent.parent

FORWARD_PATH = "data/forward_collection.json"
FORWARD_PATH_PUBLISHED = "docs/data/forward_collection.json"

HORIZON_DAYS = 10          # Reifungs-Horizont in Handelstagen
EVAL_MIN_N = 100           # Auswertung erst ab so vielen gereiften Setups
SCHEMA_VERSION = 1

# W5->A-Nachprüfung (Lit-Check-Punkt b, ElliottAgents): eine Zählung ist erst
# gestützt, wenn auch das NACHSPIEL stimmt — auf W5 folgt Korrektur A. REINES
# Mess-Feld (kein Score/Ranking/Filter). NUR für gereifte end_of_w4-Episoden mit
# target_hit; angehängtes Beobachtungsfenster, das die bestehende Reifung NICHT
# verlängert oder verändert.
A_OBSERVE_DAYS = 10        # Handelstage NACH dem Episoden-Hoch beobachten
A_RETRACE_MIN = 0.382      # Fib-Minimum: Korrektur gilt ab 38,2 % Rücklauf der
                           # W5-Strecke (P4 -> Episoden-Hoch)

# ---------------------------------------------------------------------------
# Messfelder v1 (Lit-Check P2, ab 2026-07-25) — REINE MESSUNG, kein Score/Ranking/
# Filter/Population-Einfluss. Point-in-time eingefroren. STEHENDE REGEL: Definitionen
# werden NIE umdefiniert; eine Änderung erzeugt NEUE, datierte Felder (v2, …).
# Siehe docs/validation_registry.md „Messfelder v1".
# (A) Volumen-Profil: bei Anlage in der Pipeline (build_candidate) berechnet, hier
#     nur aus dem Kandidaten eingefroren — Guideline: Volumen trägt in W1/3/5,
#     W3 am höchsten (W3 < W1 = Zählfehler-Verdacht).
# (B) Alternation (NUR end_of_w4; end_of_w2 hat noch kein W4 -> null): W2/W4
#     alternieren im Charakter (scharf<->flach). Rohwerte eingefroren; das Flag ist
#     definierbar, die Rohwerte machen die Auswertung definitions-unabhängig.
ALTERNATION_MIN_DIFF_PP = 20.0    # |w2_retrace − w4_retrace| ≥ 20 Prozentpunkte ODER
ALTERNATION_DURATION_RATIO = 2.0  # Dauer-Verhältnis (länger/kürzer) ≥ 2× -> alterniert
# (C) W5-Momentum-Divergenz (bei REIFUNG, NUR end_of_w4 + target_hit): einfacher
#     deterministischer Momentum-Proxy = n-Tage-Rate-of-Change der Schlusskurse
#     (reines Python, keine Dependency). Divergenz = Episoden-Hoch > W3-Hoch, aber
#     Momentum am Episoden-Hoch < Momentum am W3-Hoch. Roh-Momentum mit eingefroren.
MOMENTUM_ROC_BARS = 14

# Regime-Index je Markt (200-Tage-Linie).
REGIME_INDEX = {"US": "SPY", "DE": "^GDAXI"}


# ---------------------------------------------------------------------------
# I/O (fail-soft)
# ---------------------------------------------------------------------------
def load_collection() -> Dict:
    """Lädt die Sammlung (fail-soft: leere Struktur bei fehlender/kaputter Datei)."""
    empty = {"schema_version": SCHEMA_VERSION, "last_run_date": None,
             "prev_distinct_run_date": None, "updated_utc": None, "records": []}
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
            closes = [float(x) for x in df["Close"].tolist() if finite(x)]
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

    NICHT-FINIT-HÄRTUNG (27.07.2026, Ursachen-Fix zu #51): Ein nicht endlicher
    Close ist ein **fehlender Bar**, kein „kein Treffer". Vorher verlor er
    jeden Vergleich (``nan <= inval`` ist False, ``nan >= tlow`` ist False) und
    zählte trotzdem als abgelaufener Handelstag — er konnte also eine
    Invalidierung oder einen Treffer **verschlucken** und die Reifung
    gleichzeitig vorantreiben. Das verzerrt die Validierungs-Population
    lautlos. Jetzt: solche Bars werden aussortiert und in ``skipped_bars``
    gezählt; die Reifung läuft mit den GÜLTIGEN Bars weiter (``bars_elapsed``
    zählt gültige Bars) — ein Record bleibt also nie still ewig offen, sobald
    genügend gültige Kurse nachkommen.
    """
    try:
        idx = list(dates).index(rec["first_seen_date"])
    except ValueError:
        return  # Einstiegstag (noch) nicht in den Daten -> diesen Lauf überspringen
    # HORIZON_DAYS **gültige** Bars einsammeln, nicht die ersten HORIZON_DAYS
    # Zeilen. Ein fester Fenster-Schnitt würde einen Record mit einem kaputten
    # Bar im Fenster NIE auf 10 gültige Bars bringen — er bliebe still ewig
    # offen (genau das soll nicht passieren). Der Fehlbar VERZÖGERT die Reifung
    # also um einen Handelstag, er blockiert sie nicht.
    # Für gesunde Daten identisch: dort stoppt der Scan exakt bei idx+1+HORIZON.
    pairs: List[Tuple[str, float]] = []
    skipped = 0
    for d, c in zip(list(dates)[idx + 1:], list(closes)[idx + 1:]):
        if len(pairs) >= HORIZON_DAYS:
            break
        if finite(c):
            pairs.append((d, float(c)))
        else:
            skipped += 1
    fwd_dates = [d for d, _ in pairs]
    fwd = [c for _, c in pairs]
    rec["last_update_utc"] = now_iso
    rec["bars_elapsed"] = len(fwd)
    # additiv, nur wenn es etwas zu melden gibt — und WIEDER WEG, sobald die
    # Quelle den Bar nachgeliefert hat (05.08.2026). Vorher wurde das Feld nur
    # gesetzt, nie gelöscht: ein Record behauptete dann dauerhaft einen
    # übersprungenen Bar, den es nicht mehr gab. Bewusst nicht „immer setzen":
    # das hätte allen Records ein `skipped_bars: 0` angehängt, obwohl heute
    # keiner das Feld trägt. Reine Diagnose — nicht in evaluate.FROZEN_FIELDS,
    # vom Frontend nirgends gelesen.
    if skipped:
        rec["skipped_bars"] = skipped
    else:
        rec.pop("skipped_bars", None)
    # Kursverlauf NACH dem Einstieg (max HORIZON_DAYS Werte). Wird je Lauf aus
    # der vollen Historie neu aufgebaut -> deterministisch/idempotent.
    rec["price_path"] = [{"date": d, "close": round(c, 4)}
                         for d, c in pairs]
    if not fwd:
        rec["matured"] = False
        return

    entry = rec["entry_close"]
    inval = rec["invalidation_price"]
    tlow = rec["target_zone"]["low"]
    elow = rec["target_zone_extended"]["low"]
    # Die Anlage-Werte stammen aus einem früheren Lauf. Ist einer davon nicht
    # endlich (Alt-Record aus der Zeit vor dieser Härtung), ist der Record nicht
    # bewertbar: markieren und NICHT weiterrechnen — ein NaN-Vergleich würde
    # sonst jede Bedingung still auf False setzen.
    if not all(finite(v) for v in (entry, inval, tlow, elow)):
        rec["unmeasurable"] = True
        rec["matured"] = False
        return
    rec.pop("unmeasurable", None)

    # PRU-Guard (2026-07-23, siehe docs/validation_registry.md): War der Kurs schon
    # BEI ANLAGE (entry_close) ≥ Zonen-Unterkante, ist ein späterer „Treffer" ein
    # Look-ahead-Artefakt — das Ziel war zum Anlage-Zeitpunkt bereits erreicht,
    # keine Vorhersage. Solche Records reifen NORMAL aus (Invalidierung,
    # max_gain/drawdown/r_multiple bleiben voll gültig), aber die HIT-Zählung ist
    # gesperrt (auf 0 gedeckelt, nie 1) und pre_reached_* markiert sie für den
    # Auswertungs-Ausschluss. Getrennt für Basis- (tlow) und Extension-Zone (elow).
    pre_reached_target = entry >= tlow
    pre_reached_ext = entry >= elow
    rec["pre_reached_target"] = bool(pre_reached_target)
    rec["pre_reached_ext"] = bool(pre_reached_ext)

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
        target_hit = 1 if (target_day is not None and (inval_day is None or target_day < inval_day)) else 0
        ext_hit = 1 if (ext_day is not None and (inval_day is None or ext_day < inval_day)) else 0
        # PRU-Guard: Hit auf 0 sperren, wenn schon bei Anlage über der Zone
        # (Invalidierung bleibt UNBERÜHRT — sie ist keine Look-ahead-Größe).
        rec["target_hit"] = 0 if pre_reached_target else target_hit
        rec["invalidated"] = 1 if (inval_day is not None and (target_day is None or inval_day <= target_day)) else 0
        rec["ext_hit"] = 0 if pre_reached_ext else ext_hit

    # `if entry` war truthy-Form: ein nicht endlicher entry ist truthy und hätte
    # NaN-Kennzahlen erzeugt. Oben schon abgefangen — hier explizit, damit die
    # Absicht an der Rechenstelle steht (0.0 bleibt wie bisher ausgeschlossen).
    rec["max_gain_10d"] = (round((maxc - entry) / entry * 100.0, 4)
                           if entry else None)
    rec["max_drawdown_10d"] = (round((minc - entry) / entry * 100.0, 4)
                               if entry else None)
    risk = entry - inval
    rec["r_multiple"] = (round((maxc - entry) / risk, 4)
                         if finite(risk) and risk > 0 else None)
    rec["matured"] = matured


# ---------------------------------------------------------------------------
# W5->A-Nachprüfung (Lit-Check b) — ANGEHÄNGTES Beobachtungsfenster, ändert die
# bestehende Reifung NICHT. Reines Mess-Feld.
# ---------------------------------------------------------------------------
def _is_end_of_w4(rec: Dict) -> bool:
    """end_of_w4 hat Wellen-Ziffern 0..4 (Welle 4 vorhanden); end_of_w2 nur 0..2."""
    return any(l.get("wave") == 4 for l in (rec.get("count_wave_labels") or []))


def _p4_price(rec: Dict) -> Optional[float]:
    """P4-Kurs (Start der W5) aus den eingefrorenen Pivots: der chart_point, dessen
    Wellen-Ziffer 4 ist. None, wenn nicht ableitbar (fail-soft)."""
    cps = rec.get("chart_points") or []
    for lab in (rec.get("count_wave_labels") or []):
        if lab.get("wave") == 4:
            i = lab.get("index")
            if isinstance(i, int) and 0 <= i < len(cps):
                return cps[i].get("price")
    return None


def observe_a_correction(rec: Dict, dates: Sequence[str], closes: Sequence[float],
                         now_iso: str) -> None:
    """W5->A: setzt bei gereiften end_of_w4-Treffern, ob nach dem Episoden-Hoch die
    theorie-gemäße Korrektur (>= A_RETRACE_MIN der W5-Strecke P4->Hoch) innerhalb
    A_OBSERVE_DAYS einsetzt. Deterministisch/idempotent (je Lauf aus voller
    Historie neu). Berührt WEDER target_hit/matured NOCH andere Reifungs-Zahlen —
    schreibt ausschließlich a_correction_observed / a_retrace_pct / a_observe_until.

    Guard-Konsistenz: pre_reached/pre_guard-Records (is_excluded) bekommen KEINE
    Messung — ihr „Hoch" ist nicht interpretierbar (Feld bleibt None).
    """
    # NUR gereifte end_of_w4-Treffer, nicht ausgeschlossen.
    if not rec.get("matured") or rec.get("target_hit") != 1:
        return
    if not _is_end_of_w4(rec) or is_excluded(rec):
        return
    p4 = _p4_price(rec)
    if p4 is None:
        return
    try:
        idx = list(dates).index(rec["first_seen_date"])
    except ValueError:
        return
    fwd = list(closes)[idx + 1: idx + 1 + HORIZON_DAYS]
    if len(fwd) < HORIZON_DAYS:
        return  # sollte durch matured impliziert sein; defensiv
    # Nicht-finit-Härtung: ein NaN im Fenster macht `max()` reihenfolge-abhaengig
    # und jeden Folgevergleich still False -> lieber gar nicht messen.
    if not all_finite(fwd) or not finite(p4):
        return
    high = max(fwd)
    high_pos = fwd.index(high)                 # erstes Auftreten des Hochs
    w5_len = high - p4
    if not finite(w5_len) or w5_len <= 0:
        return  # W5-Strecke nicht interpretierbar (degeneriert) -> keine Messung
    trigger = high - A_RETRACE_MIN * w5_len    # 38,2 %-Rücklauf-Schwelle
    # A-Fenster: die Schlusskurse NACH dem Episoden-Hoch (bis A_OBSERVE_DAYS).
    a_start = idx + 1 + high_pos + 1
    a_win = list(closes)[a_start: a_start + A_OBSERVE_DAYS]
    end_idx = a_start + A_OBSERVE_DAYS - 1
    rec["a_observe_until"] = dates[end_idx] if end_idx < len(dates) else None
    if a_win:
        minc = min(a_win)
        rec["a_retrace_pct"] = round((high - minc) / w5_len * 100.0, 4)
        if minc <= trigger:
            rec["a_correction_observed"] = True
            return
    else:
        rec["a_retrace_pct"] = 0.0
    # Kein Trigger: False wenn das Fenster voll beobachtet ist, sonst offen (None).
    rec["a_correction_observed"] = False if len(a_win) >= A_OBSERVE_DAYS else None


# ---------------------------------------------------------------------------
# Messfelder v1 (Lit-Check P2) — (B) Alternation + (C) W5-Momentum-Divergenz.
# REINE MESSUNG, point-in-time. Definitionen s. Konstanten + validation_registry.
# ---------------------------------------------------------------------------
def _pivot_by_wave(chart_points: Sequence[Dict], labels: Sequence[Dict],
                   wave: int) -> Optional[Dict]:
    """Der eingefrorene chart_point zur Wellen-Ziffer `wave` (0..4). None, wenn
    nicht ableitbar. `labels`-index zeigt auf die Position in `chart_points`."""
    for lab in (labels or []):
        if lab.get("wave") == wave:
            i = lab.get("index")
            if isinstance(i, int) and 0 <= i < len(chart_points or []):
                return chart_points[i]
    return None


def _alternation_fields(chart_points: Optional[Sequence[Dict]],
                        labels: Optional[Sequence[Dict]]) -> Dict:
    """(B) Alternation W2<->W4 — NUR end_of_w4 (Wellen-Ziffer 4 vorhanden); sonst
    alle Felder null. Rohwerte (retrace % + Dauer in Bars) aus den EINGEFRORENEN
    Pivots; `alternation_observed` = |ΔRetrace| ≥ ALTERNATION_MIN_DIFF_PP ODER
    Dauer-Verhältnis ≥ ALTERNATION_DURATION_RATIO. Fail-soft: fehlende Pivots/
    0-Nenner -> betroffenes Feld null. Die ROHWERTE machen die spätere Auswertung
    definitions-unabhängig (das Flag ist nur eine mögliche Operationalisierung)."""
    out = {"w2_retrace_pct": None, "w4_retrace_pct": None,
           "w2_bars": None, "w4_bars": None, "alternation_observed": None}
    cps = chart_points or []
    labs = labels or []
    if not any(l.get("wave") == 4 for l in labs):
        return out  # end_of_w2 -> es gibt noch kein W4
    p = {w: _pivot_by_wave(cps, labs, w) for w in range(5)}
    if any(p[w] is None for w in range(5)):
        return out

    def retr(a: Dict, b: Dict, c: Dict) -> Optional[float]:
        # Nicht-finit-Härtung: `den > 0` ist die negierte Form — mit einem
        # nicht endlichen Pivot-Preis wäre `den` NaN, der Vergleich False, und
        # das Feld hätte still `null` gemeldet statt „nicht messbar". Explizit.
        if not all(finite(x.get("price")) for x in (a, b, c)):
            return None
        den = abs(b["price"] - a["price"])
        return round(abs(c["price"] - b["price"]) / den * 100.0, 4) if den > 0 else None

    def bars(a: Dict, b: Dict) -> Optional[int]:
        ia, ib = a.get("index"), b.get("index")
        return abs(ib - ia) if isinstance(ia, int) and isinstance(ib, int) else None

    w2r = retr(p[0], p[1], p[2])   # W2 = |P2-P1| / |P1-P0|
    w4r = retr(p[2], p[3], p[4])   # W4 = |P4-P3| / |P3-P2|
    w2b = bars(p[1], p[2])
    w4b = bars(p[3], p[4])
    out.update(w2_retrace_pct=w2r, w4_retrace_pct=w4r, w2_bars=w2b, w4_bars=w4b)

    diff = abs(w2r - w4r) if (finite(w2r) and finite(w4r)) else None
    dur = None
    if w2b and w4b and min(w2b, w4b) > 0:
        dur = max(w2b, w4b) / min(w2b, w4b)
    if diff is None and dur is None:
        out["alternation_observed"] = None
    else:
        out["alternation_observed"] = bool(
            (diff is not None and diff >= ALTERNATION_MIN_DIFF_PP)
            or (dur is not None and dur >= ALTERNATION_DURATION_RATIO))
    return out


def _roc(closes: Sequence[float], pos: int, n: int) -> Optional[float]:
    """n-Tage-Rate-of-Change als Momentum-Proxy (reines Python). None, wenn zu
    wenig Vorlauf (pos < n) oder Nenner 0."""
    if pos < n or pos >= len(closes):
        return None
    prev = closes[pos - n]
    # Nicht-finit-Härtung: `prev == 0` ist gegen NaN wirkungslos (jeder
    # Vergleich mit NaN ist False) -> das Momentum waere still NaN geworden.
    if not finite(prev) or not finite(closes[pos]) or prev == 0:
        return None
    return round(closes[pos] / prev - 1.0, 6)


def _w3_date_price(rec: Dict) -> Tuple[Optional[str], Optional[float]]:
    """(Datum, Kurs) des W3-Hochs (P3) aus den eingefrorenen Pivots — per DATUM
    (nicht Index), da das 2-Jahres-Fenster bei der Reifung vorne wandert."""
    cp = _pivot_by_wave(rec.get("chart_points") or [],
                        rec.get("count_wave_labels") or [], 3)
    if cp is None:
        return None, None
    return cp.get("date"), cp.get("price")


def observe_w5_divergence(rec: Dict, dates: Sequence[str], closes: Sequence[float],
                          now_iso: str) -> None:
    """(C) W5-Momentum-Divergenz — NUR gereifte end_of_w4-Treffer, nicht
    ausgeschlossen. Divergenz = Episoden-Hoch > W3-Hoch, aber ROC am Episoden-Hoch
    < ROC am W3-Hoch. Nicht bestimmbar (zu wenig Bars/pre_reached/kein P3) -> null.
    Deterministisch/idempotent; schreibt NUR w5_momentum_divergence + Roh-Momentum,
    berührt die Reifung (Schritt 2) NICHT — angehängter Schritt wie W5->A."""
    if not rec.get("matured") or rec.get("target_hit") != 1:
        return
    if not _is_end_of_w4(rec) or is_excluded(rec):
        return
    w3_date, w3_price = _w3_date_price(rec)
    if w3_date is None or w3_price is None:
        return
    dl, cl = list(dates), list(closes)
    try:
        w3_pos = dl.index(w3_date)
        idx = dl.index(rec["first_seen_date"])
    except ValueError:
        return
    # „Episoden-Hoch" = Hoch im SELBEN HORIZON_DAYS-Fenster nach dem Einstieg wie in
    # mature_record/observe_a_correction (ein Fenster, eine Wahrheit — kein neues).
    fwd = cl[idx + 1: idx + 1 + HORIZON_DAYS]
    if len(fwd) < HORIZON_DAYS:
        return  # defensiv (durch matured impliziert)
    if not all_finite(fwd):
        return  # Nicht-finit-Haertung (siehe observe_a_correction)
    high = max(fwd)
    high_pos = idx + 1 + fwd.index(high)
    mom_w3 = _roc(cl, w3_pos, MOMENTUM_ROC_BARS)
    mom_high = _roc(cl, high_pos, MOMENTUM_ROC_BARS)
    rec["w5_mom_w3"] = mom_w3
    rec["w5_mom_high"] = mom_high
    if mom_w3 is None or mom_high is None:
        rec["w5_momentum_divergence"] = None
        return
    rec["w5_momentum_divergence"] = bool(high > w3_price and mom_high < mom_w3)


def _p4_date_price(rec: Dict) -> Tuple[Optional[str], Optional[float]]:
    """(Datum, Kurs) des W5-Start-Pivots P4 aus den eingefrorenen Pivots — Basis der
    W5-Strecke P4→Episoden-Hoch. None, wenn nicht ableitbar."""
    cps = rec.get("chart_points") or []
    for lab in (rec.get("count_wave_labels") or []):
        if lab.get("wave") == 4:
            i = lab.get("index")
            if isinstance(i, int) and 0 <= i < len(cps):
                return cps[i].get("date"), cps[i].get("price")
    return None, None


def observe_w5_structure(rec: Dict, dates: Sequence[str], closes: Sequence[float],
                         now_iso: str) -> None:
    """(Struktur-Vokabular v2) W5→A STRUKTURELL — NUR gereifte end_of_w4-Treffer,
    nicht ausgeschlossen. Ist die Gegenbewegung nach dem Episoden-Hoch als
    regelkonforme A-/ABC-Struktur BESTÄTIGT (mind. ein bestätigter ZigZag-Pivot nach
    dem Hoch)? a_structure_observed True/False/null; c_target_pct = Tiefe des
    tiefsten bestätigten Korrektur-Pivots in % der W5-Strecke (P4→Hoch), sonst null.
    Deterministisch/idempotent; schreibt NUR a_structure_observed/c_target_pct,
    berührt Reifung + bestehende W5→A-Felder NICHT — angehängter Schritt."""
    if not rec.get("matured") or rec.get("target_hit") != 1:
        return
    if not _is_end_of_w4(rec) or is_excluded(rec):
        return
    p4_date, p4 = _p4_date_price(rec)
    if p4 is None:
        return
    dl, cl = list(dates), list(closes)
    try:
        idx = dl.index(rec["first_seen_date"])
    except ValueError:
        return
    fwd = cl[idx + 1: idx + 1 + HORIZON_DAYS]
    if len(fwd) < HORIZON_DAYS:
        return
    # Nicht-finit-Härtung (Guardian-Nit 27.07.): dasselbe Fenster-Pendant wie
    # in observe_a_correction und observe_w5_divergence. `max()` ist mit einem
    # NaN im Fenster reihenfolge-abhängig; der `finite(w5_len)`-Guard unten
    # fängt zwar den erreichbaren Schadensfall ab, aber die drei Funktionen
    # sollen dieselbe Fenster-Regel tragen — sonst driftet die nächste
    # Änderung an einer davon vorbei.
    if not all_finite(fwd) or not finite(p4):
        return
    high = max(fwd)
    high_pos = idx + 1 + fwd.index(high)
    w5_len = high - p4
    if not finite(w5_len) or w5_len <= 0:
        return  # W5-Strecke nicht interpretierbar
    # Bestätigte ZigZag-Pivots NACH dem Episoden-Hoch, STRIKT im selben
    # A_OBSERVE_DAYS-Fenster wie die v1-Pendants (a_retrace_pct etc.) — True und
    # False sind damit symmetrisch fenstergebunden und über Läufe STABIL (ein
    # späterer Pivot außerhalb des Fensters kann das Ergebnis nie mehr kippen).
    window_end = high_pos + A_OBSERVE_DAYS
    pivots = zigzag(cl, config.ZIGZAG_WINDOW, dl)
    post = [p for p in pivots
            if isinstance(p.index, int) and high_pos < p.index <= window_end]
    if post:
        rec["a_structure_observed"] = True
        low = min(p.price for p in post)              # tiefster bestätigter Korrektur-Pivot
        rec["c_target_pct"] = round((high - low) / w5_len * 100.0, 4)
    elif window_end + config.ZIGZAG_WINDOW < len(cl):
        # False erst, wenn JEDER Bar im Fenster seine Bestätigungs-Chance hatte
        # (ZigZag braucht rechts ZIGZAG_WINDOW Bars) -> False ist final/stabil.
        rec["a_structure_observed"] = False
    # sonst: Fenster noch offen -> None (unverändert)


# ---------------------------------------------------------------------------
# Episoden-Anschluss: welche `last_seen_top5_date` setzen eine Episode fort?
# ---------------------------------------------------------------------------
def episode_anchor_dates(coll: Dict, run_date: str,
                         market: Optional[str] = None) -> set:
    """Die Lauf-Daten, deren Records der heutige Lauf VERLÄNGERT (statt neu
    anzulegen). Genau zwei Anker, beide Kalendertage:

      1. ``run_date`` selbst — ein FRÜHERER Lauf DESSELBEN Kalendertags hat
         den Record bereits verlängert.
      2. das jüngste davorliegende Lauf-Datum mit ANDEREM Kalendertag.

    Warum (Präzisierung vom 01.08.2026, keine Umdefinition): die Regel lautet
    „konsekutive Top-5-**Tage** verlängern dieselbe Episode". Bis hierher stand
    dafür ``coll["last_run_date"]`` — das Datum des letzten LAUFS. Bei einem
    einzigen Lauf pro Tag ist das dasselbe. Bei MEHREREN Läufen am selben Tag
    nicht: der erste Lauf setzt ``last_run_date`` bereits auf heute, und ein
    Record von gestern findet im zweiten Lauf keinen Anschluss mehr — er wird
    zu einer zweiten Episode zerschnitten, obwohl er an zwei konsekutiven
    Tagen in den Top 5 stand (beobachtet 31.07.2026: MTX.DE, G1A.DE, KKR nach
    drei Hand-Dispatches am Vormittag; ebenso 30.07. und 25.07.).

    'Tag' heißt ab hier KALENDERTAG, unabhängig von der Zahl der Läufe an ihm.
    Eine UNTERBRECHUNG bleibt eine Unterbrechung: wer am letzten Lauf-Kalender-
    tag nicht in den Top 5 war, bekommt weiterhin eine neue Episode. Über
    Wochenenden und Feiertage trägt der Anker unverändert (das vorige distinct
    Lauf-Datum ist dann der Freitag bzw. der letzte Handelstag).

    Migration: fehlt ``prev_distinct_run_date`` (Sammlungs-Stand von vor dem
    01.08.2026) und ist heute bereits ein Lauf gelaufen, ist das vorige distinct
    Datum unbekannt — dann bleibt nur ``run_date`` als Anker. Das ist exakt das
    ALTE Verhalten, also keine Verschlechterung; ab dem ersten Lauf an einem
    neuen Kalendertag ist das Feld gesetzt und der Fall erledigt sich.

    MARKT-BEWUSST seit 05.08.2026: wird ein Markt an einem Lauf wegen
    veralteten Kurs-Stands übersprungen (siehe ``stale_markets``), darf dieser
    Tag für ihn NICHT als „gesehen" gelten. Sonst zerschneidet der Schutz genau
    die Episoden, die er schützen soll: der übersprungene Lauf schreibt
    ``last_run_date`` fort, und der nächste saubere Lauf findet die Records von
    vorgestern nicht mehr unter seinen Ankern (nachgestellt und reproduziert —
    sauber → stale → sauber ergab ZWEI Records statt einem). Deshalb ankert ein
    Markt auf seinen letzten **frischen** Lauf (``last_fresh_run_date[markt]``).
    Ohne Markt-Angabe oder ohne das Feld gilt exakt das Verhalten von #68.
    """
    prev_run = _letzter_anschluss_lauf(coll, market)
    if not prev_run:
        return {run_date}
    if prev_run != run_date:
        # Erster Lauf an diesem Kalendertag: der bisherige Anschluss-Lauf IST
        # das vorige distinct Datum — unabhängig davon, ob das Feld schon
        # existiert (deshalb hier kein Rückgriff darauf).
        return {run_date, prev_run}
    prev_distinct = coll.get("prev_distinct_run_date")
    return {run_date, prev_distinct} if prev_distinct else {run_date}


def _letzter_anschluss_lauf(coll: Dict, market: Optional[str]) -> Optional[str]:
    """Das Lauf-Datum, an das dieser Markt anschließt.

    Ohne Markt (oder ohne den markt-eigenen Eintrag): ``last_run_date`` — das
    Verhalten von #68, unverändert. Mit Markt und Eintrag: der letzte Lauf, an
    dem DIESER Markt einen frischen Kurs-Stand hatte. An frischen Tagen sind
    beide identisch; sie laufen erst auseinander, wenn ein Lauf den Markt wegen
    Rückstands übersprungen hat.
    """
    if market:
        frisch = coll.get("last_fresh_run_date")
        if isinstance(frisch, dict) and frisch.get(market):
            return frisch[market]
    return coll.get("last_run_date")


def _open_episode(records: List[Dict], ticker: str, anchors: set) -> Optional[Dict]:
    """Die fortzusetzende offene Episode von ``ticker`` — oder None.

    Deterministisch: unter den passenden Records gewinnt das JÜNGSTE
    ``last_seen_top5_date``; bei Gleichstand der zuerst angelegte (Listen-
    Reihenfolge). An Ein-Lauf-Tagen kann höchstens ein Anker-Datum vorkommen,
    dort ist das Ergebnis identisch mit dem früheren ``next(...)``-Griff.
    Wichtig wird die Ordnung erst bei bereits zerschnittenen Alt-Episoden:
    dort ist der jüngere Record der richtige Anschluss.
    """
    best: Optional[Dict] = None
    for r in records:
        if r.get("ticker") != ticker or r.get("matured"):
            continue
        seen = r.get("last_seen_top5_date")
        if seen not in anchors:
            continue
        if best is None or str(seen) > str(best.get("last_seen_top5_date")):
            best = r
    return best


# ---------------------------------------------------------------------------
# Episoden-Anlage + Reifung (pure)
# ---------------------------------------------------------------------------
def _unique_episode_id(records: Sequence[Dict], ticker: str, first_seen: str) -> str:
    """``ticker@first_seen`` — mit einem ``#N``-Suffix NUR dann, wenn diese ID
    unter den BESTEHENDEN Records schon vergeben ist.

    GRUND (Backlog-Punkt, #68-Archiv): ``episode_id`` hat nur zwei Achsen —
    Ticker-String und Kalendertag von ``first_seen`` — und keinerlei Schutz
    gegen eine zweite Anlage auf denselben Wert. Das ist kein theoretisches
    Risiko: der #68-Anschluss-Fehler hat real bereits ZEHN Kollisionen erzeugt
    (u. a. zweimal ``ADS.DE@2026-07-24``, SESSION_ARCHIVE.md #68), erkennbar
    nur über die Ersatz-Identität ``(ticker, created_utc)`` — nachgezogen in
    ``mark_stale_market_records.record_key`` und ``mark_episode_splits``, mit
    demselben Kommentar: „NICHT episode_id … das kollidiert real". #68 hat die
    DAMALIGE Ursache (Anschluss-Logik) repariert, aber nicht die ID-Vergabe
    selbst geändert — jede KÜNFTIGE Anlage zweier Episoden auf denselben
    (ticker, first_seen) würde weiterhin kollidieren, unabhängig davon, wie sie
    zustande kommt. Diese Funktion macht Eindeutigkeit zur GARANTIE statt zur
    Wahrscheinlichkeit: sie prüft gegen den tatsächlichen Bestand, nicht gegen
    eine vermutete Ursache. Der Normalfall (keine Kollision) bleibt exakt das
    alte, lesbare Format — nur der Kollisionsfall bekommt einen Suffix.
    """
    vergeben = {r.get("episode_id") for r in records if isinstance(r, dict)}
    basis = f"{ticker}@{first_seen}"
    if basis not in vergeben:
        return basis
    n = 2
    while f"{basis}#{n}" in vergeben:
        n += 1
    return f"{basis}#{n}"


def _new_record(entry: Dict, market: str, first_seen: str, regime: str,
                run_date: str, now_iso: str,
                episode_id: Optional[str] = None) -> Dict:
    """``episode_id`` optional, damit bestehende Aufrufer (Tests, die eine
    einzelne Episode ohne Kollisions-Kontext bauen) unverändert bleiben — ohne
    Angabe gilt exakt das alte, einfache ``ticker@first_seen``-Format. Der
    Produktionscode in ``update_forward_collection`` reicht die per
    ``_unique_episode_id`` gegen den echten Bestand geprüfte ID explizit
    durch."""
    if episode_id is None:
        episode_id = f"{entry['ticker']}@{first_seen}"
    return {
        "episode_id": episode_id,
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
        # Konfluenz-Marken zum ANLAGE-Zeitpunkt point-in-time eingefroren (wie die
        # Pivots) — damit die spätere n>=EVAL_MIN_N-Auswertung testen kann, ob
        # Konfluenz-Zonen öfter treffen. Werden bei Reifungs-Läufen NIE geändert.
        # Reines Mess-Feld, additiv, kein Score/Ranking. Siehe validation_registry.
        "confluence": entry.get("confluence", {"target": [], "invalidation": []}),
        # Wird bei der Reifung mit den Folgetags-Schlusskursen gefüllt (max 10).
        "price_path": [],
        "last_seen_top5_date": run_date,
        # Score-Alert-Flanke: das Lauf-Datum, an dem diese Episode ZUERST über
        # die Alert-Schwelle stieg (None = noch nie). Rein additiv, einmalig je
        # Episode gesetzt; berührt Score/Ranking/Reifung nicht. Siehe
        # score_alert_edges + config.score_alert_threshold(typ).
        "score_alert_fired": None,
        "created_utc": now_iso,
        "bars_elapsed": 0,
        "matured": False,
        "target_hit": None,
        "ext_hit": None,
        "invalidated": None,
        # PRU-Guard (2026-07-23): bei der Reifung gesetzt (Kurs schon bei Anlage
        # ≥ Zonen-Unterkante → Hit gesperrt + aus der Auswertung ausgeschlossen).
        "pre_reached_target": False,
        "pre_reached_ext": False,
        "max_gain_10d": None,
        "max_drawdown_10d": None,
        "r_multiple": None,
        # W5->A-Nachprüfung (nur end_of_w4 + target_hit, s. observe_a_correction).
        # None = keine Messung / Fenster offen; True/False = Korrektur (nicht)
        # beobachtet. Rein additiv, kein Score/Ranking/Reifung.
        "a_correction_observed": None,
        "a_retrace_pct": None,
        "a_observe_until": None,
        # Messfelder v1 (Lit-Check P2, ab 2026-07-25) — REINE MESSUNG, additiv,
        # point-in-time. (A) Volumen-Profil bei Anlage in der Pipeline berechnet ->
        # hier nur aus dem Kandidaten EINGEFROREN (wie confluence/chart_points).
        "vol_profile": entry.get("vol_profile", {}),
        "vol_ratio_w3_w1": entry.get("vol_ratio_w3_w1"),
        "vol_ratio_w4_w3": entry.get("vol_ratio_w4_w3"),
        "vol_ratio_w2_w1": entry.get("vol_ratio_w2_w1"),
        # ATR(14) (Messfeld v2, ab 23.08.2026) — bei Anlage in der Pipeline
        # berechnet, hier NUR aus dem Kandidaten eingefroren (wie das
        # Volumen-Profil). Reine Anzeige-Band-Breite im Episode-Detail; kein
        # Score-/Ranking-/Reifungs-Einfluss. Alt-Episoden (vor diesem Datum)
        # haben das Feld nicht -> None, Anzeige bleibt fail-soft die
        # ungepolsterte Zone.
        "atr_14": entry.get("atr_14"),
        # (B) Alternation W2<->W4 (NUR end_of_w4) aus den eingefrorenen Pivots —
        # Rohwerte + Flag; end_of_w2 -> alle null.
        **_alternation_fields(entry.get("chart_points"), entry.get("count_wave_labels")),
        # (C) W5-Momentum-Divergenz — bei der Reifung gesetzt (nur end_of_w4 +
        # target_hit). None = keine Messung / nicht bestimmbar.
        "w5_momentum_divergence": None,
        "w5_mom_w3": None,
        "w5_mom_high": None,
        # Ambiguität v1 (Lit-Check P3, ab 2026-07-25) — Mehrdeutigkeit INNERHALB des
        # heutigen Zähl-Vokabulars (2 Fenster Ende-W4/Ende-W2), point-in-time bei
        # Anlage eingefroren. Auswertungs-Dimension: treffen eindeutige Zählungen
        # (N=1) öfter als mehrdeutige (N=2)? Reine Messung, kein Score/Ranking.
        "ambiguity_n": entry.get("valid_count_total"),
        # Ambiguität v2 (Struktur-Vokabular v2, ab 2026-07-25) — ZUSÄTZLICH zu v1
        # (v1 läuft unverändert weiter, Vergleichbarkeit der Alt-Daten). Erweitertes
        # Vokabular inkl. A-B-C-Korrektur-Lesart.
        "ambiguity_n_v2": entry.get("valid_count_total_v2"),
        # Agent-Kommentar v1 (ab 26.07.2026) — das LLM-Urteil zum ANLAGE-Zeitpunkt
        # point-in-time eingefroren (LLM-Output ist nicht deterministisch;
        # temperature 0 mildert das, garantiert es nicht → der damalige Wert muss
        # verortbar bleiben). Auswertungs-Frage: trifft concern_level="high"
        # schlechter? Reine Mess-Dimension, kein Score/Ranking. Alt-Records null.
        "agent_concern_level": ((entry.get("agent_comment") or {}).get("concern_level")
                                if isinstance(entry.get("agent_comment"), dict) else None),
        "agent_model": ((entry.get("agent_comment") or {}).get("model")
                        if isinstance(entry.get("agent_comment"), dict) else None),
        # W5→A strukturell (additiv, bei Reifung): ist die Gegenbewegung nach dem
        # Episoden-Hoch als regelkonforme A-/ABC-Struktur (bestätigter Pivot)
        # bestätigt? + Korrektur-Tiefe (C) in % der W5-Strecke. None = keine Messung.
        "a_structure_observed": None,
        "c_target_pct": None,
        "last_update_utc": now_iso,
    }


def stale_markets(report: Dict) -> Dict[str, int]:
    """``{markt: rueckstand}`` für Märkte mit veraltetem Kurs-Stand.

    Quelle ist ``diag.bar_lag_trading_days`` — dieselbe Zahl, die der
    Kurs-Stand-Wächter meldet und die ``build_report`` aus
    ``market_calendar.handelstage_rueckstand`` schreibt. **Keine zweite
    Definition von „letzter Handelstag"**; wandert die Kalender-Regel, wandert
    dieses Gate mit.

    Schwelle ist **≥ 1 Handelstag** — so steht es in der Registry-Notiz vom
    05.08.2026 („hinter dem letzten erwarteten Handelstag zurück"). Über die
    committete Historie (Stand 04.08.2026 22:42: 53 Sammlungs-Stände,
    106 Markt-Läufe) hätte das Gate **8×** gegriffen (7,5 %), bei Schwelle
    ≥ 2 nur 3× (2,8 %) — der bekannte Ein-Tag-Versatz hungert die Sammlung
    also nicht aus, und gerade aus ihm stammen drei der vier markierten
    Alt-Records. Die Zahlen wandern mit jedem Lauf; die Tests pinnen
    deshalb die ZUGEHÖRIGKEIT der bekannten Fälle, keinen Zählerstand.

    Fail-soft: fehlt das Feld (Report-Stände von vor dem 04.08.2026) oder ist
    es unbrauchbar, gilt der Markt als **frisch**. Ein Gate, das aus Unwissen
    sperrt, würde die Sammlung stillschweigend anhalten — das wäre schlimmer
    als der Schaden, den es verhindern soll.
    """
    out: Dict[str, int] = {}
    for key, market in (report.get("markets") or {}).items():
        if not isinstance(market, dict):
            continue
        lag = (market.get("diag") or {}).get("bar_lag_trading_days")
        if isinstance(lag, int) and not isinstance(lag, bool) and lag >= 1:
            out[key] = lag
    return out


def update_forward_collection(
    coll: Dict,
    report: Dict,
    price_data: Dict[str, Tuple[Sequence[str], Sequence[float]]],
    regimes: Dict[str, str],
    run_date: str,
    now_iso: str,
) -> Dict:
    """Legt neue Episoden an, reift offene Records, aktualisiert Metadaten.

    Episoden-Regel: ein Record je Ticker-Episode. Konsekutive Top-5-KALENDER-
    TAGE verlängern dieselbe Episode (kein Doppel-Record), unabhängig davon,
    wie viele Läufe an einem Tag stattfinden — siehe ``episode_anchor_dates``
    (Präzisierung 01.08.2026). Wiederauftauchen nach Verschwinden (nicht am
    letzten Lauf-Kalendertag in den Top 5) = neue Episode. Offene Records
    reifen unabhängig von der Top-5-Zugehörigkeit aus.

    EINFRIER-INVARIANTE: eine Verlängerung schreibt AUSSCHLIESSLICH
    ``last_seen_top5_date``. Die Anlage-Felder (entry_close, score_heuristic,
    Zonen, Pivots, Konfluenz, …) friert der ERSTE Lauf eines Tages ein; jeder
    weitere Lauf desselben Tages lässt sie unberührt.

    SAMMLUNGS-SCHUTZ (05.08.2026): ein Markt mit veraltetem Kurs-Stand wird in
    Schritt 1 **komplett übersprungen** — keine neue Episode UND keine
    Verlängerung. Beides gehört zusammen: würde nur die Anlage unterbleiben,
    die Verlängerung aber laufen, wanderte ``last_seen_top5_date`` auf einen
    Tag, den der markt-eigene Anker gar nicht kennt — der nächste saubere Lauf
    fände den Record nicht mehr und zerschnitte die Episode. Der Tag ist für
    diesen Markt unsichtbar; ``last_fresh_run_date[markt]`` bleibt stehen und
    überbrückt ihn. Die REIFUNG (Schritt 2 ff.) läuft bewusst weiter: sie
    rechnet idempotent aus der Kursreihe neu und korrigiert sich am Folgetag
    selbst — ein Gate dort würde genau diese Eigenschaft zerstören.
    """
    records: List[Dict] = coll.setdefault("records", [])
    stale = stale_markets(report)

    # 1) Anlegen / Verlängern für die heutigen Top-5 — je Markt, mit
    #    markt-eigenen Ankern.
    for mk, market in report.get("markets", {}).items():
        if mk in stale:
            continue                       # Markt unsichtbar (Sammlungs-Schutz)
        anchors = episode_anchor_dates(coll, run_date, mk)
        for entry in market.get("candidates", []):
            ticker = entry["ticker"]
            active = _open_episode(records, ticker, anchors)
            if active is not None:
                active["last_seen_top5_date"] = run_date  # gleiche Episode
                continue
            pdata = price_data.get(ticker)
            first_seen = pdata[0][-1] if (pdata and len(pdata[0])) else run_date
            eid = _unique_episode_id(records, ticker, first_seen)
            records.append(
                _new_record(entry, mk, first_seen, regimes.get(mk, "unknown"),
                            run_date, now_iso, eid)
            )

    # 2) ALLE offenen Records reifen (auch aus Top-5 gefallene).
    for r in records:
        if r["matured"]:
            continue
        pdata = price_data.get(r["ticker"])
        if pdata:
            mature_record(r, pdata[0], pdata[1], now_iso)

    # 3) W5->A-Nachprüfung (Lit-Check b) — SEPARATER Durchgang, damit die Reifung
    #    (Schritt 2) byte-identisch bleibt. Angehängtes Beobachtungsfenster für
    #    gereifte end_of_w4-Treffer; braucht Kurse ÜBER den Reifungs-Horizont
    #    hinaus, die über die Läufe akkumulieren (offen -> True/False).
    for r in records:
        if not r.get("matured"):
            continue
        pdata = price_data.get(r["ticker"])
        if pdata:
            observe_a_correction(r, pdata[0], pdata[1], now_iso)

    # 4) W5-Momentum-Divergenz (Messfeld v1 C) — SEPARATER Durchgang, damit die
    #    Reifung (Schritt 2) byte-identisch bleibt. Angehängter Schritt wie W5->A.
    for r in records:
        if not r.get("matured"):
            continue
        pdata = price_data.get(r["ticker"])
        if pdata:
            observe_w5_divergence(r, pdata[0], pdata[1], now_iso)

    # 5) W5→A STRUKTURELL (Struktur-Vokabular v2) — SEPARATER Durchgang; schreibt nur
    #    a_structure_observed/c_target_pct, Reifung + W5→A-Felder byte-identisch.
    for r in records:
        if not r.get("matured"):
            continue
        pdata = price_data.get(r["ticker"])
        if pdata:
            observe_w5_structure(r, pdata[0], pdata[1], now_iso)

    coll["schema_version"] = SCHEMA_VERSION
    # Vor dem Überschreiben: das vorige DISTINCT Lauf-Datum festhalten — nur
    # beim Wechsel des Kalendertags. Ein zweiter Lauf desselben Tages lässt es
    # stehen, sonst ginge genau der Anker verloren, den er braucht.
    if coll.get("last_run_date") != run_date:
        coll["prev_distinct_run_date"] = coll.get("last_run_date")
    coll["last_run_date"] = run_date
    # Markt-eigener Anschluss (05.08.2026): NUR frische Märkte schreiben ihren
    # letzten frischen Lauf fort. Ein gegateter Markt behält seinen alten Wert
    # — genau das überbrückt den stale Tag, ohne die Episode zu zerschneiden.
    # Ist das Feld unbrauchbar (fremd beschrieben, von Hand kaputtgemacht), wird
    # es hier NEU aufgebaut statt still liegengelassen: sonst fiele der Anker
    # dauerhaft auf #68 zurück und der Schutz wäre lautlos aus.
    frisch = coll.get("last_fresh_run_date")
    if not isinstance(frisch, dict):
        frisch = {}
        coll["last_fresh_run_date"] = frisch
    for mk in (report.get("markets") or {}):
        if mk not in stale:
            frisch[mk] = run_date
    coll["updated_utc"] = now_iso
    return coll


def is_excluded(rec: Dict) -> bool:
    """Aus der Auswertungs-POPULATION ausgeschlossen (PRU-Guard, 2026-07-23).

    Grund: Kurs war schon bei Anlage über der Zone (`pre_reached_*`) → ein
    „Treffer" wäre ein Look-ahead-Artefakt; ODER historisch vor dem Guard als
    Treffer gezählt (`pre_guard_contaminated`, forward-only ausgewiesen, nie
    gelöscht). Diese Records reifen weiter (Invalidierung/Kennzahlen gültig),
    zählen aber NICHT in Trefferquote/AUC. Siehe docs/validation_registry.md."""
    return bool(rec.get("pre_reached_target") or rec.get("pre_reached_ext")
                or rec.get("pre_guard_contaminated"))


def eval_counts(coll: Dict) -> Tuple[int, int, int]:
    """(gesammelt, gereift, auswertbar). auswertbar = gereift UND nicht
    ausgeschlossen (PRU-Guard). Der n≥EVAL_MIN_N-Schwellwert bezieht sich auf
    ``auswertbar`` — nicht auf ``gereift``."""
    records = coll.get("records", [])
    collected = len(records)
    matured = sum(1 for r in records if r.get("matured"))
    evaluable = sum(1 for r in records if r.get("matured") and not is_excluded(r))
    return collected, matured, evaluable


def appearance_count(coll: Dict, ticker: str, run_date: Optional[str] = None,
                     market: Optional[str] = None) -> int:
    """Wie oft ``ticker`` als Top-5-Kandidat erschienen ist — **Episoden**, nicht
    Tage — inkl. der AKTUELLEN Erscheinung.

    Ein Record = eine Episode. Zum Report-Bauzeitpunkt ist die aktuelle
    Erscheinung noch NICHT in der Sammlung (die wird erst nach write_report
    aktualisiert). Deshalb: Zahl der vorhandenen Episoden + 1, ES SEI DENN die
    aktuelle Erscheinung verlängert eine bereits offene Episode (Ticker war schon
    am letzten Lauf-Kalendertag Top-5) — dann ist sie bereits gezählt. Die
    Fortsetzungs-Prüfung spiegelt exakt die ``active``-Erkennung in
    ``update_forward_collection`` (kein Doppelzählen) und benutzt seit dem
    01.08.2026 dieselben ``episode_anchor_dates`` — sonst zählte ein zweiter
    Lauf desselben Tages eine Erscheinung doppelt. Wirkt nur vorwärts: der
    Zähler wird bei jedem Lauf neu in den Report geschrieben, nie gespeichert."""
    records = coll.get("records", [])
    episodes = sum(1 for r in records if r.get("ticker") == ticker)
    anchors = episode_anchor_dates(coll, run_date, market) if run_date else None
    if anchors is None:
        # Ohne Lauf-Datum bleibt nur der alte Anker (Rückwärtskompatibilität
        # für Aufrufer, die das Datum nicht durchreichen).
        anchors = {coll.get("last_run_date")}
    continues = _open_episode(records, ticker, anchors) is not None
    return episodes if continues else episodes + 1


def annotate_appearance_counts(coll: Dict, report: Dict,
                               run_date: Optional[str] = None) -> None:
    """Setzt je Markt-Top-5-Kandidat additiv ``appearance_count``. In-place.

    NUR für markets[].candidates — Watchlist-Karten bekommen KEINEN Zähler
    (nicht Teil der Population). Reine Anzeige: berührt Score/Ranking/Sammlung
    nicht. ``run_date`` optional: ohne Angabe zählt der alte Anker (identisch
    an Ein-Lauf-Tagen), mit Angabe auch der Mehrfach-Lauf-Fall korrekt."""
    for mk, market in (report.get("markets") or {}).items():
        for entry in market.get("candidates", []):
            entry["appearance_count"] = appearance_count(
                coll, entry["ticker"], run_date, mk)


# ---------------------------------------------------------------------------
# Score-Alert-Flanke (EINMALIG je Episode) — an die vorhandene Episoden-Logik
# gekoppelt, KEIN zweites Episoden-System.
# ---------------------------------------------------------------------------
def setup_typ_aus_label(label) -> Optional[str]:
    """Setup-Typ eines Report-Kandidaten aus seinem ``count_label``.

    Der Report führt den Typ nicht als eigenes Feld, und er soll auch keins
    bekommen — eine Alarm-Justierung darf den Report nicht verändern. Die
    Marker stehen in ``config.SETUP_LABEL_MARKER``; ein Laufzeit-Test schickt
    echte ``classify_setup``-Ausgaben hier durch, damit Beschriftung und
    Marker nicht auseinanderlaufen können.

    None = nicht bestimmbar. Der Aufrufer faellt dann auf die STRENGSTE
    Schwelle zurueck, nicht auf „kein Alarm" (siehe score_alert_edges).
    """
    if not isinstance(label, str):
        return None
    for typ, marker in config.SETUP_LABEL_MARKER.items():
        if marker in label:
            return typ
    return None


def score_alert_edges(coll: Dict, report: Dict, run_date: str) -> List[Dict]:
    """Kandidaten, die in IHRER Episode NEU die Schwelle ihres Setup-TYPS
    erreichen (Flanke, nicht Zustand). Setzt je Episode einmalig
    ``score_alert_fired`` und gibt sie für EINEN gebündelten Push zurück.

    Die Schwelle kommt aus ``config.score_alert_threshold(typ)`` und wird zur
    LAUFZEIT aus den Score-Deckeln berechnet (31.07.2026). Vorher stand hier
    eine feste 90 — bei einem erreichbaren Maximum von exakt 90.00 und einem
    Vergleich `> 90` war der Alarm damit unerreichbar. Ein Typ-Maximum von 80
    (``end_of_w2``) haette den Alarm ohnehin nie ausloesen koennen.

    MUSS NACH ``update_forward_collection`` laufen: danach trägt der Record der
    heutigen Erscheinung ``last_seen_top5_date == run_date`` — das ist eindeutig
    die AKTUELLE Episode (die active-Erkennung von update_forward_collection
    verlängert genau diesen einen Record bzw. legt einen neuen an). Damit greift
    die Flanke auf DASSELBE Episoden-System wie der N×-Zähler; kein Parallel-State.

    Verhalten (Flanke, nicht Zustand):
      - Neu an der Schwelle in einer Episode -> Flag None -> feuert, Flag = run_date.
      - Bleibt über Schwelle (Folgetage, gleiche Episode) -> Flag gesetzt -> stumm.
      - Fällt unter, steigt in DERSELBEN Episode wieder über -> Flag bleibt -> stumm.
      - Neue Episode (Ticker war weg, kommt >Schwelle zurück) -> neuer Record,
        Flag None -> feuert erneut.

    Bewertet wird der AKTUELLE Report-Score (``score_heuristic``), nicht der im
    Record eingefrorene Anlage-Score — eine Episode kann erst an einem späteren
    Tag über die Schwelle steigen. Watchlist ist ausgenommen (nicht Teil von
    ``markets[].candidates``). Rein additiv: Score/Ranking/Reifung unberührt.
    """
    records = coll.get("records", [])
    fired: List[Dict] = []
    for mk, market in report.get("markets", {}).items():
        for entry in market.get("candidates", []):
            score = entry.get("score_heuristic")
            if not isinstance(score, (int, float)):
                continue
            typ = setup_typ_aus_label(entry.get("count_label"))
            schwelle = (config.score_alert_threshold(typ) if typ
                        else config.score_alert_threshold_max())
            if score < schwelle:
                continue
            # Record der HEUTIGEN Episode: eindeutig der mit last_seen == run_date
            # (update_forward_collection setzt genau diesen für jeden Top-5-Ticker).
            rec = next(
                (r for r in records
                 if r.get("ticker") == entry["ticker"]
                 and r.get("last_seen_top5_date") == run_date),
                None,
            )
            if rec is None:
                continue  # defensiv: kein Episoden-Record -> nichts feuern
            if rec.get("score_alert_fired"):
                continue  # in dieser Episode bereits gemeldet -> stumm (Flanke)
            rec["score_alert_fired"] = run_date
            fired.append({"ticker": entry["ticker"], "market": mk,
                          "score": float(score), "setup": typ,
                          "threshold": round(schwelle, 2)})
    return fired
