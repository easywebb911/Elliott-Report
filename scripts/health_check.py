"""Health-Check Stufe 2 — Plausibilitäts-Regeln am Ende des Laufs.

Stufe 1 (`notify.py`) meldet, wenn ein Lauf **abstürzt** oder **ausfällt**.
Diese Stufe schließt die andere Lücke: ein Lauf kann technisch ERFOLGREICH
sein und trotzdem Unsinn liefern.

ANLASS (27.07.2026) — Lehre aus dem Schwester-Repo (easywebb911/Aktien-Update,
PR #485): dort erzeugte ein Fetch-Pfad **NaN statt None**. NaN passierte ALLE
None-Guards (``x is not None`` ist wahr) und JEDEN Vergleich (``nan <= 0`` ist
False), der Provider-Check verbuchte „Erfolg", der Fehler lief **zwei Tage
still** weiter und ließ am Ende einen Trigger falsch feuern. Elliott rechnet
ebenfalls Ratios aus Kursreihen (``vol_ratio_*``, Retrace-Prozente, Zonen,
Score) — dieselbe Klasse ist strukturell möglich.

**Elliotts Schadensbild ist ANDERS und schlimmer** (empirisch geprüft, nicht
angenommen): ``json.dump`` schreibt ``float('nan')`` als literales ``NaN`` —
das ist **kein gültiges JSON**. Python liest es klaglos zurück (deshalb merkt
es die Workflow-Validierung nicht), aber ``JSON.parse`` im Browser **wirft** →
die PWA lädt gar nicht mehr. Ein NaN wird hier also nicht still zu ``null``
(Squeeze-Fall), sondern legt das Frontend lahm. Genau deshalb prüft Regel 1
**VOR der Serialisierung** und mit ``math.isfinite`` statt ``is not None``.

GRENZEN (hart, siehe PR):
  • ändert NIE Daten — nur lesen und melden;
  • bricht den Lauf NIE ab — der Report wird geschrieben, der Befund gemeldet;
  • berührt Score/Ranking/Filter/Reifung nicht (der Health-Block ist additiv
    unter ``report["health"]``, wie ``diag``).

PUSH-DISZIPLIN: alle Befunde eines Laufs gebündelt in **EINEN** ntfy-Push, und
nur auf der **FLANKE** (Befund neu oder verschlechtert). Unveränderter Zustand
→ kein erneuter Push; ``warn`` wiederholt sich frühestens nach
``HEALTH_WARN_REPEAT_RUNS`` Läufen. Marker in ``data/health_state.json``
(committet wie die Sammlung). Wochenend-/Feiertags-Gate wie überall.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

try:
    import config  # noqa: E402
except Exception:  # pragma: no cover — config immer vorhanden, defensiv
    config = None

import market_calendar as cal  # noqa: E402
import notify  # noqa: E402  — geteilte ntfy-Schicht (fail-soft, ASCII-Title)

# ── Schwellen (Betriebs-Parameter, KEINE Auswertungs-Definitionen) ──────────
# Sie steuern, wann sich die Selbstüberwachung MELDET — sie definieren nichts,
# was ausgewertet wird (kein Score, kein Erfolgsmaß). Änderbar ohne Registry-
# Versionierung; die Registry-Notiz führt sie nur der Nachvollziehbarkeit
# halber auf.
MIN_CANDIDATES = getattr(config, "HEALTH_MIN_CANDIDATES", 3)
MAX_FETCH_ERROR_PCT = getattr(config, "HEALTH_MAX_FETCH_ERROR_PCT", 10.0)
MAX_DEAD_DELTA = getattr(config, "HEALTH_MAX_DEAD_DELTA", 3)
AGENT_MIN_OK = getattr(config, "HEALTH_AGENT_MIN_OK", 5)
WARN_REPEAT_RUNS = getattr(config, "HEALTH_WARN_REPEAT_RUNS", 3)
STATE_PATH = getattr(config, "HEALTH_STATE_PATH", "data/health_state.json")
REPORT_PATH = getattr(config, "REPORT_PATH", "data/report.json")

CRIT = "crit"
WARN = "warn"
_SEV_RANK = {WARN: 1, CRIT: 2}

# Wie viele Fundstellen je Regel maximal in den Report/Push wandern. Ein
# systemischer NaN-Ausfall würde sonst tausende Pfade erzeugen — die Zahl
# ``count`` bleibt vollständig, nur die Beispiel-Pfade sind gekappt.
MAX_PATHS_REPORTED = 8


def _log(msg: str) -> None:
    print(f"[health] {msg}", flush=True)


# ---------------------------------------------------------------------------
# 0) Das Prädikat — der Kern der Lehre
# ---------------------------------------------------------------------------
def _finite(v) -> bool:
    """Ist ``v`` eine echte, ENDLICHE Zahl?

    Bewusst NICHT ``x is not None``: genau daran ist das Schwester-Repo
    gescheitert. ``bool`` fällt raus (True/False sind keine Messwerte),
    ``None``/``NaN``/``±Inf``/Strings ebenfalls.
    """
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    return math.isfinite(v)


def non_finite_paths(obj, path: str = "") -> List[str]:
    """Rekursiv ALLE Pfade zu nicht-endlichen Zahlen (NaN/±Inf).

    Bewusst ohne Feld-Allowlist: eine Liste erlaubter Schlüssel altert und
    würde ein neues Feld stillschweigend durchlassen. Geprüft wird jeder
    ``float`` im Baum — Strings/Bools/None sind keine Zahlen und daher kein
    Befund (ein fehlender Wert ist ``null``, das ist gültig und gewollt).
    """
    out: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.extend(non_finite_paths(v, f"{path}.{k}" if path else str(k)))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            out.extend(non_finite_paths(v, f"{path}[{i}]"))
    elif isinstance(obj, float) and not math.isfinite(obj):
        out.append(path or "<root>")
    return out


def _finding(rule: str, severity: str, message: str,
             market: Optional[str] = None, detail: Optional[Dict] = None) -> Dict:
    return {"rule": rule, "severity": severity, "market": market,
            "message": message, "detail": detail or {}}


# ---------------------------------------------------------------------------
# 1) NICHT-FINIT-PRÜFUNG (der wichtigste Punkt — eigener Prüfschritt)
# ---------------------------------------------------------------------------
def check_finite(obj, scope: str) -> List[Dict]:
    """NaN/±Inf irgendwo im Baum → **crit**.

    ``scope`` ist ``"report"`` oder ``"collection"``. MUSS vor der
    JSON-Serialisierung laufen: danach steht im File literales ``NaN`` (kein
    gültiges JSON) und die Prüfung käme zu spät für den Befund im selben Lauf.
    """
    paths = non_finite_paths(obj)
    if not paths:
        return []
    shown = paths[:MAX_PATHS_REPORTED]
    more = len(paths) - len(shown)
    msg = (f"{len(paths)} nicht-endliche Zahl(en) in {scope}: "
           + ", ".join(shown) + (f" (+{more} weitere)" if more else ""))
    return [_finding(f"non_finite_{scope}", CRIT, msg,
                     detail={"count": len(paths), "paths": shown})]


# ---------------------------------------------------------------------------
# 2) VOLLSTÄNDIGKEIT
# ---------------------------------------------------------------------------
def check_completeness(report: Dict, min_candidates: int = MIN_CANDIDATES
                       ) -> List[Dict]:
    """0 Einträge in einem Markt → crit; < min_candidates trotz vorhandener
    Kandidaten → warn."""
    out: List[Dict] = []
    for key, market in sorted((report.get("markets") or {}).items()):
        if not isinstance(market, dict):
            continue
        top = market.get("candidates") or []
        found = market.get("candidates_found")
        n_top = len(top)
        if n_top == 0:
            out.append(_finding(
                "completeness", CRIT,
                f"{key}: keine Top-Kandidaten im Report "
                f"({found if found is not None else '?'} gefunden)",
                market=key, detail={"top": 0, "found": found}))
        elif n_top < min_candidates and (found or 0) > 0:
            out.append(_finding(
                "completeness", WARN,
                f"{key}: nur {n_top} Top-Kandidaten (< {min_candidates}), "
                f"obwohl {found} Kandidaten gefunden wurden",
                market=key, detail={"top": n_top, "found": found,
                                    "min": min_candidates}))
    return out


# ---------------------------------------------------------------------------
# 3) FETCH-QUALITÄT
# ---------------------------------------------------------------------------
def _dead_count(market: Dict) -> int:
    diag = market.get("diag") or {}
    dead = diag.get("dead_tickers")
    return len(dead) if isinstance(dead, list) else 0


def check_fetch_quality(report: Dict, prev_report: Optional[Dict] = None,
                        max_pct: float = MAX_FETCH_ERROR_PCT,
                        max_dead_delta: int = MAX_DEAD_DELTA) -> List[Dict]:
    """Fehlanteil (``empty_data`` + ``fetch_error``) über der Schwelle → warn;
    ``dead_tickers`` gegenüber dem VORLAUF stark gestiegen → warn.

    ``prev_report`` ist der Report des letzten Laufs (von Platte, VOR dem
    Überschreiben gelesen). Fehlt er, entfällt nur der Delta-Teil.
    """
    out: List[Dict] = []
    prev_markets = (prev_report or {}).get("markets") or {}
    for key, market in sorted((report.get("markets") or {}).items()):
        if not isinstance(market, dict):
            continue
        diag = market.get("diag") or {}
        rc = diag.get("reason_counts") or {}
        universe = market.get("universe_size") or 0
        bad = int(rc.get("empty_data", 0) or 0) + int(rc.get("fetch_error", 0) or 0)
        if universe > 0:
            pct = bad / universe * 100.0
            if pct > max_pct:
                out.append(_finding(
                    "fetch_quality", WARN,
                    f"{key}: {bad}/{universe} Ticker ohne Daten "
                    f"({pct:.1f} % > {max_pct:.0f} %)",
                    market=key, detail={"bad": bad, "universe": universe,
                                        "pct": round(pct, 1), "max_pct": max_pct}))
        prev_market = prev_markets.get(key)
        if isinstance(prev_market, dict):
            delta = _dead_count(market) - _dead_count(prev_market)
            if delta > max_dead_delta:
                out.append(_finding(
                    "dead_delta", WARN,
                    f"{key}: tote Ticker um {delta} gestiegen "
                    f"(> {max_dead_delta}) — jetzt {_dead_count(market)}",
                    market=key, detail={"delta": delta,
                                        "now": _dead_count(market),
                                        "max_delta": max_dead_delta}))
    return out


# ---------------------------------------------------------------------------
# 4) SAMMLUNG (fängt Persistenz-Regressionen wie #21 wieder ein)
# ---------------------------------------------------------------------------
def collection_signature(coll: Optional[Dict]) -> Dict[str, str]:
    """{episode_id: last_seen_top5_date} — reicht, um „gewachsen" von
    „verlängert" von „gar nichts passiert" zu unterscheiden."""
    out: Dict[str, str] = {}
    for rec in ((coll or {}).get("records") or []):
        if not isinstance(rec, dict):
            continue
        key = rec.get("episode_id") or f"{rec.get('ticker')}@{rec.get('first_seen_date')}"
        out[str(key)] = str(rec.get("last_seen_top5_date"))
    return out


def check_collection_progress(report: Dict, sig_before: Optional[Dict],
                              sig_after: Optional[Dict],
                              same_day_rerun: bool = False) -> List[Dict]:
    """Top-5 vorhanden, aber die Sammlung ist WEDER gewachsen NOCH wurde ein
    Datensatz verlängert → warn.

    Genau das war der stille Fehler aus #21 (die Sammlung wurde nicht
    persistiert, n wuchs nie). Signaturen None (Sammel-Schritt gescheitert) →
    kein Befund; dieser Fall ist bereits über den Fail-soft-Log sichtbar und
    soll hier keinen Phantom-Alarm erzeugen.

    ``same_day_rerun`` (Guardian-Nit 27.07.): Beim ZWEITEN Lauf desselben
    Kalendertags — ein ausdrücklich vorgesehener Pfad (`workflow_dispatch` als
    Retry, siehe daily.yml) — ist Stillstand das KORREKTE Verhalten: die
    Episoden-Logik findet die heutigen Records bereits mit
    ``last_seen_top5_date == heute`` und setzt sie idempotent erneut. Die
    Signatur ist dann zwangsläufig identisch. Ohne diese Ausnahme meldet die
    Regel bei jedem Retry-Dispatch einen Fehlalarm (reproduziert).
    """
    if sig_before is None or sig_after is None or same_day_rerun:
        return []
    has_top5 = any(
        (m.get("candidates") or [])
        for m in (report.get("markets") or {}).values() if isinstance(m, dict)
    )
    if not has_top5:
        return []           # Leerlauf deckt Regel 2 (Vollständigkeit) ab
    grew = len(sig_after) > len(sig_before)
    extended = any(sig_after.get(k) != v for k, v in sig_before.items())
    if grew or extended:
        return []
    return [_finding(
        "collection_stalled", WARN,
        f"Top-5 vorhanden, aber die Forward-Sammlung ist weder gewachsen "
        f"({len(sig_before)} Records) noch wurde ein Datensatz verlängert",
        detail={"records": len(sig_before)})]


# ---------------------------------------------------------------------------
# 5) AGENT
# ---------------------------------------------------------------------------
def check_agent_comments(report: Dict, has_key: bool,
                         min_ok: int = AGENT_MIN_OK) -> List[Dict]:
    """Zu wenige Karten mit ``agent_comment``, OBWOHL das Secret gesetzt ist
    → warn. Ohne Secret ist der Schritt ein no-op → **kein Befund**
    (unterscheidbar, genau wie gefordert)."""
    if not has_key:
        return []
    total = ok = 0
    for market in (report.get("markets") or {}).values():
        if not isinstance(market, dict):
            continue
        for entry in (market.get("candidates") or []):
            total += 1
            if isinstance(entry, dict) and entry.get("agent_comment"):
                ok += 1
    if total == 0 or ok >= min_ok:
        return []
    return [_finding(
        "agent_comments", WARN,
        f"nur {ok}/{total} Karten mit KI-Kommentar (< {min_ok}), "
        f"obwohl ANTHROPIC_API_KEY gesetzt ist",
        detail={"ok": ok, "total": total, "min": min_ok})]


# ---------------------------------------------------------------------------
# 6) PUSH-DISZIPLIN — Flanke, gebündelt, kalender-gegated
# ---------------------------------------------------------------------------
def _key(f: Dict) -> str:
    return f"{f['rule']}:{f.get('market') or '-'}"


def overall_status(findings: Sequence[Dict]) -> str:
    if any(f["severity"] == CRIT for f in findings):
        return CRIT
    if findings:
        return WARN
    return "ok"


def evaluate_edges(findings: Sequence[Dict], state: Optional[Dict],
                   run_date: str, warn_repeat: int = WARN_REPEAT_RUNS
                   ) -> Tuple[List[Dict], Dict]:
    """Flanken-Logik. Gibt ``(zu_pushende_Befunde, neuer_State)``.

    Gepusht wird ein Befund, wenn er **neu** ist oder sich **verschlechtert**
    hat (warn→crit). Unverändert → still. Ein ``warn`` darf sich frühestens
    nach ``warn_repeat`` Läufen wiederholen (``crit`` sofort beim Auftreten,
    danach ebenfalls still, solange er unverändert steht). Verschwundene
    Befunde geben ihren Marker frei (Erholung → nächstes Auftreten ist wieder
    eine frische Flanke).
    """
    old = dict(((state or {}).get("rules") or {}))
    new: Dict[str, Dict] = {}
    to_push: List[Dict] = []
    for f in findings:
        k = _key(f)
        sev = f["severity"]
        prev = old.get(k) if isinstance(old.get(k), dict) else None
        if prev is None:
            push = True                                    # neu
            since = run_date
            runs = 0
        elif _SEV_RANK.get(sev, 0) > _SEV_RANK.get(prev.get("severity"), 0):
            push = True                                    # verschlechtert
            since = prev.get("since_run", run_date)
            runs = 0
        else:
            since = prev.get("since_run", run_date)
            runs = int(prev.get("runs_since_push", 0) or 0) + 1
            push = (sev == WARN and runs >= warn_repeat)   # gedrosselte Wdh.
            if push:
                runs = 0
        if push:
            to_push.append(f)
        # `prev` ist hier nie None, wenn nicht gepusht wird (ein neuer Befund
        # pusht immer) — der Ausdruck bleibt trotzdem defensiv lesbar statt
        # verschachtelt. `last_push_run` ist reine Diagnose für den State.
        last_push = run_date if push else (prev or {}).get("last_push_run")
        new[k] = {"severity": sev, "since_run": since,
                  "last_push_run": last_push,
                  "runs_since_push": 0 if push else runs}
    return to_push, {"schema_version": 1, "rules": new}


def push_gated(now: _dt.datetime) -> Optional[str]:
    """Grund, warum heute NICHT gepusht werden darf — oder None.

    Wochenende/gemeinsamer Feiertag: der Daily-Cron läuft dann gar nicht, ein
    ``workflow_dispatch`` aber schon. Kein Fehl-Push an solchen Tagen.
    """
    d = now.date()
    holiday = cal.is_full_closure(d)
    if holiday:
        return f"Feiertag ({holiday})"
    if d.weekday() >= 5:
        return "Wochenende"
    return None


_SEV_MARK = {CRIT: "crit", WARN: "warn"}


def push_body(findings: Sequence[Dict]) -> str:
    """Kurz und handlungsorientiert: was, welcher Markt, welche Zahl."""
    parts = []
    for f in findings:
        mk = f.get("market")
        prefix = f"[{_SEV_MARK.get(f['severity'], f['severity'])}] "
        parts.append(prefix + (f["message"] if not mk or f["message"].startswith(f"{mk}:")
                               else f"{mk}: {f['message']}"))
    return " · ".join(parts)


def send_findings(topic: str, findings: Sequence[Dict]) -> bool:
    """EIN gebündelter Push pro Lauf. Leere Liste → kein Push."""
    if not findings:
        return False
    status = overall_status(findings)
    title = ("Elliott: Lauf unplausibel (crit)" if status == CRIT
             else "Elliott: Lauf-Warnung")
    return notify.send_ntfy(
        topic, title, push_body(findings),
        priority="high" if status == CRIT else "default",
        tags="rotating_light" if status == CRIT else "warning",
    )


# ---------------------------------------------------------------------------
# I/O (fail-soft — alles hier darf den Lauf nie brechen)
# ---------------------------------------------------------------------------
def _load_json(rel: str):
    try:
        with (REPO_ROOT / rel).open(encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return None


def load_previous_report() -> Optional[Dict]:
    """Report des VORLAUFS — muss gelesen werden, BEVOR der neue ihn
    überschreibt (Delta-Regel 3)."""
    return _load_json(REPORT_PATH)


def load_state() -> Dict:
    st = _load_json(STATE_PATH)
    return st if isinstance(st, dict) else {}


def write_state(state: Dict, now_iso: str) -> bool:
    """State persistieren (fail-soft). Wird von daily.yml mitcommittet."""
    try:
        path = REPO_ROOT / STATE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(state)
        payload["updated_utc"] = now_iso
        with path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        return True
    except Exception as exc:  # noqa: BLE001
        _log(f"State nicht schreibbar (fail-soft): {type(exc).__name__}: {exc}")
        return False


# ---------------------------------------------------------------------------
# 7) TRANSPARENZ — additiver Block im Report (Lauf-Status-Ansicht)
# ---------------------------------------------------------------------------
def attach_to_report(report: Dict, findings: Sequence[Dict], now_iso: str,
                     pushed: bool = False, gated: Optional[str] = None) -> Dict:
    """Hängt ``report["health"]`` an — rein additiv, wie ``diag``.

    Der Block macht den Zustand auch OHNE Push nachlesbar (und ohne ntfy-Topic
    ist er die einzige Sichtbarkeit).
    """
    report["health"] = {
        "checked_utc": now_iso,
        "status": overall_status(findings),
        "findings": [dict(f) for f in findings],
        "pushed": bool(pushed),
        "push_gated": gated,
        "thresholds": {
            "min_candidates": MIN_CANDIDATES,
            "max_fetch_error_pct": MAX_FETCH_ERROR_PCT,
            "max_dead_delta": MAX_DEAD_DELTA,
            "agent_min_ok": AGENT_MIN_OK,
            "warn_repeat_runs": WARN_REPEAT_RUNS,
        },
    }
    return report


# ---------------------------------------------------------------------------
# Orchestrator (aus der Pipeline aufgerufen)
# ---------------------------------------------------------------------------
def collect_findings(report: Dict, prev_report: Optional[Dict],
                     finite_findings: Sequence[Dict],
                     sig_before: Optional[Dict], sig_after: Optional[Dict],
                     has_agent_key: bool,
                     same_day_rerun: bool = False) -> List[Dict]:
    """Alle Regeln zusammenführen. ``finite_findings`` kommen von außen, weil
    Regel 1 VOR den beiden Serialisierungen laufen muss (Report + Sammlung)."""
    findings: List[Dict] = list(finite_findings)
    findings.extend(check_completeness(report))
    findings.extend(check_fetch_quality(report, prev_report))
    findings.extend(check_collection_progress(report, sig_before, sig_after,
                                              same_day_rerun))
    findings.extend(check_agent_comments(report, has_agent_key))
    # Stabile Reihenfolge: crit zuerst, dann Regel, dann Markt — der Push-Text
    # und der Report-Block sind damit deterministisch.
    findings.sort(key=lambda f: (-_SEV_RANK.get(f["severity"], 0),
                                 f["rule"], f.get("market") or ""))
    return findings


def run(report: Dict, prev_report: Optional[Dict],
        finite_findings: Sequence[Dict], sig_before: Optional[Dict],
        sig_after: Optional[Dict], has_agent_key: bool, topic: str,
        run_date: str, now_iso: str, now: _dt.datetime,
        same_day_rerun: bool = False) -> Dict:
    """Kompletter Health-Check-Durchlauf. Gibt die Befund-Liste zurück und
    hängt den Report-Block an. Push + State nur an Handelstagen.

    An gegateten Tagen (Wochenende/Feiertag) wird der State **bewusst nicht**
    fortgeschrieben: sonst gälte ein Befund als „schon gesehen" und der nächste
    Handelstag würde ihn verschlucken. Der Report-Block wird trotzdem gesetzt.
    """
    findings = collect_findings(report, prev_report, finite_findings,
                                sig_before, sig_after, has_agent_key,
                                same_day_rerun)
    gated = push_gated(now)
    pushed = False
    if gated:
        _log(f"{len(findings)} Befund(e) — Push unterdrückt ({gated}), "
             f"State unverändert.")
    else:
        state = load_state()
        to_push, new_state = evaluate_edges(findings, state, run_date)
        pushed = send_findings(topic, to_push)
        write_state(new_state, now_iso)
        _log(f"{len(findings)} Befund(e), davon {len(to_push)} auf der Flanke "
             f"→ Push {'gesendet' if pushed else 'nicht gesendet'}.")
    attach_to_report(report, findings, now_iso, pushed=pushed, gated=gated)
    for f in findings:
        _log(f"  [{f['severity']}] {f['rule']}: {f['message']}")
    return report["health"]
