"""Push-Paket Stufe 1 — reine Selbstüberwachung per ntfy. Bewusst fast stumm.

Meldet sich NUR, wenn etwas kaputt ist oder eine Entscheidung fällig wird:
  - Lauf-Fehlschlag  → eigener `if: failure()`-Step in daily.yml (nicht hier;
                       ein gebrochener Python-Pfad soll den Push nicht mitreißen).
  - Staleness        → separater Check-Cron erkennt den NICHT stattgefundenen Lauf
                       (`--mode staleness`).
  - Meilenstein n≥100 → einmaliger Push, Marker-Datei gegen Wiederholung.
  - Review-Wecker    → überfälliges `review_by` erinnert ~1×/Woche (Wochentag-
                       gedrosselt, KEIN State — Squeeze-Muster).

KEINE Invalidierungs-Riss-/Kandidaten-/Tages-Pushes (Risse bleiben lautloser
✗-Status im Backtesting). Erwartete Frequenz: < 1 Push/Monat.

ntfy-Mechanik exakt aus easywebb911/Aktien-Update (`ki_agent.send_ntfy_alert` /
`status_review_reminder.py`): `POST https://ntfy.sh/{topic}` + Title/Priority/
Tags-Header, timeout 5, **fail-soft**. Topic kommt aus `NTFY_TOPIC` (Repo-
Secret); leer → no-op (nie hardcoden). Ein Push-Fehler bricht NIE den Lauf.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

try:
    import config  # noqa: E402
except Exception:  # pragma: no cover — config immer vorhanden, defensiv
    config = None

try:
    import forward_collection as _fc  # kanonische Quelle für EVAL_MIN_N  # noqa: E402
except Exception:  # pragma: no cover
    _fc = None

NTFY_BASE = "https://ntfy.sh"
REPORT_PATH = "data/report.json"
COLLECTION_PATH = "data/forward_collection.json"
MILESTONE_MARKER = "data/validation_milestone_fired.flag"

# EVAL_MIN_N lebt in forward_collection (Single Source), NICHT in config —
# von dort lesen, damit eine spätere Änderung hier nicht still divergiert.
EVAL_MIN_N = getattr(_fc, "EVAL_MIN_N", getattr(config, "EVAL_MIN_N", 100))
STALENESS_HOURS = getattr(config, "STALENESS_HOURS", 30)
SCORE_REVIEW_BY = getattr(config, "SCORE_REVIEW_BY", None)
STATUS_REVIEW_WEEKDAY = getattr(config, "STATUS_REVIEW_WEEKDAY", 0)  # 0 = Montag


def _log(msg: str) -> None:
    print(f"[notify] {msg}", flush=True)


def _ascii_title(s: str) -> str:
    """ntfy-Title-Header verträgt kein UTF-8 zuverlässig → ASCII-strippen."""
    return s.encode("ascii", "ignore").decode("ascii") or "Elliott-Report"


# Dünne Sende-Schicht, damit Tests sie ohne Netz ersetzen können.
def _post(url: str, data: bytes, headers: dict, timeout: int):  # pragma: no cover
    import requests  # noqa: WPS433 — nur im echten Lauf importiert
    return requests.post(url, data=data, headers=headers, timeout=timeout)


def send_ntfy(topic: str, title: str, body: str,
              priority: str = "default", tags: str = "") -> bool:
    """Ein ntfy-Push. Fail-soft: leeres Topic → no-op; Fehler → nur Log.

    Gibt True zurück, wenn tatsächlich gesendet wurde (für Tests/State)."""
    if not topic:
        _log("kein NTFY_TOPIC gesetzt → kein Push (graceful).")
        return False
    try:
        _post(
            f"{NTFY_BASE}/{topic}",
            body.encode("utf-8"),
            {"Title": _ascii_title(title), "Priority": priority, "Tags": tags},
            5,
        )
        _log(f"Push gesendet: {title} — {body}")
        return True
    except Exception as exc:  # noqa: BLE001 — Push darf den Lauf NIE brechen
        _log(f"ntfy-Push fehlgeschlagen (fail-soft): {type(exc).__name__}: {exc}")
        return False


# ---------------------------------------------------------------------------
# PURE Prüf-Funktionen (deterministisch, kein I/O) — direkt unit-testbar
# ---------------------------------------------------------------------------
def staleness_age_hours(report_ts_iso, now: _dt.datetime):
    """Alter des Reports in Stunden. None, wenn nicht parsebar."""
    if not report_ts_iso:
        return None
    try:
        ts = _dt.datetime.strptime(report_ts_iso, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=_dt.timezone.utc)
    except Exception:  # noqa: BLE001
        return None
    return (now - ts).total_seconds() / 3600.0


def is_stale(report_ts_iso, now, max_hours=STALENESS_HOURS) -> bool:
    age = staleness_age_hours(report_ts_iso, now)
    if age is None:
        return True  # unlesbar/fehlend ist selbst ein Staleness-Signal
    return age > max_hours


def milestone_reached(matured: int, marker_exists: bool, min_n=EVAL_MIN_N) -> bool:
    """n≥min_n gereift UND noch nicht gemeldet (Marker fehlt)."""
    return matured >= min_n and not marker_exists


def review_due(review_by, now: _dt.datetime, weekday=STATUS_REVIEW_WEEKDAY) -> bool:
    """`review_by` überschritten UND heute der Drossel-Wochentag (~1×/Woche).

    review_by None/leer → nie (falsifiziert/menschlich abgeschaltet). Ungültiges
    Datum → nie (fail-soft)."""
    if not review_by:
        return False
    if now.weekday() != weekday:
        return False
    try:
        due = _dt.date.fromisoformat(str(review_by))
    except Exception:  # noqa: BLE001
        return False
    return now.date() > due


# ---------------------------------------------------------------------------
# I/O-Helfer (fail-soft)
# ---------------------------------------------------------------------------
def _load_json(rel: str):
    try:
        with (REPO_ROOT / rel).open(encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return None


def _matured_count(coll) -> int:
    if not coll or not isinstance(coll.get("records"), list):
        return 0
    return sum(1 for r in coll["records"] if r and r.get("matured"))


def _run_url() -> str:
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repo = os.environ.get("GITHUB_REPOSITORY", "easywebb911/Elliott-Report")
    rid = os.environ.get("GITHUB_RUN_ID", "")
    return f"{server}/{repo}/actions/runs/{rid}" if rid else f"{server}/{repo}/actions"


# ---------------------------------------------------------------------------
# Modi (von den Workflows aufgerufen)
# ---------------------------------------------------------------------------
def run_staleness(topic: str, now: _dt.datetime) -> bool:
    """Separater Cron: erkennt auch den NICHT stattgefundenen Lauf."""
    report = _load_json(REPORT_PATH)
    ts = (report or {}).get("run_timestamp_utc")
    if not is_stale(ts, now):
        age = staleness_age_hours(ts, now)
        _log(f"Report frisch ({age:.1f} h ≤ {STALENESS_HOURS} h) → kein Push.")
        return False
    age = staleness_age_hours(ts, now)
    age_txt = f"{age:.0f} h" if age is not None else "unbekannt (report.json unlesbar)"
    day = now.strftime("%Y-%m-%d")
    return send_ntfy(
        topic,
        "Elliott: Report veraltet",
        f"Report ist {age_txt} alt (> {STALENESS_HOURS} h) · {day} · "
        f"Lauf ausgefallen? {_run_url()}",
        priority="high", tags="warning,hourglass",
    )


def run_daily(topic: str, now: _dt.datetime) -> dict:
    """Im Daily-Lauf NACH der Pipeline: Meilenstein + Review-Wecker.

    Legt bei Meilenstein-Push die Marker-Datei an (der Commit-Schritt in
    daily.yml committet sie → einmalig). Gibt {milestone, review} (bool) zurück.
    """
    out = {"milestone": False, "review": False}
    coll = _load_json(COLLECTION_PATH)
    matured = _matured_count(coll)
    marker = REPO_ROOT / MILESTONE_MARKER

    if milestone_reached(matured, marker.exists()):
        sent = send_ntfy(
            topic,
            "Elliott: Validierungs-Auswertung faellig",
            f"n≥{EVAL_MIN_N} gereifte Setups erreicht ({matured}). "
            f"Auswertung gemäß validation_registry.md fällig.",
            priority="high", tags="tada,white_check_mark",
        )
        # Marker IMMER setzen, sobald die Schwelle erreicht ist (auch wenn Topic
        # leer war) → kein Dauer-Push, sobald Easy das Topic später scharfschaltet
        # wäre der Meilenstein bereits „verbucht"; bewusst so (Einmaligkeit vor
        # Zustellgarantie). Kommentar im PR.
        try:
            marker.write_text(
                f"milestone n>={EVAL_MIN_N} erreicht ({matured} gereift) "
                f"am {now.strftime('%Y-%m-%dT%H:%M:%SZ')}\n", encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            _log(f"Marker konnte nicht geschrieben werden (fail-soft): {exc}")
        out["milestone"] = bool(sent)
    else:
        _log(f"Meilenstein: {matured}/{EVAL_MIN_N} gereift, Marker "
             f"{'vorhanden' if marker.exists() else 'fehlt'} → kein Push.")

    if review_due(SCORE_REVIEW_BY, now):
        out["review"] = send_ntfy(
            topic,
            "Elliott: Score-Status-Review faellig",
            f"review_by {SCORE_REVIEW_BY} überschritten — Validierungsstand "
            f"prüfen (Status bleibt heuristisch·unvalidiert bis Registry-Beleg).",
            priority="default", tags="alarm_clock",
        )
    else:
        _log(f"Review-Wecker: review_by={SCORE_REVIEW_BY}, "
             f"Wochentag={now.weekday()} → kein Push.")
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", required=True, choices=["staleness", "daily"])
    args = p.parse_args(argv)
    topic = os.environ.get("NTFY_TOPIC", "")
    now = _dt.datetime.now(_dt.timezone.utc)
    try:
        if args.mode == "staleness":
            run_staleness(topic, now)
        else:
            run_daily(topic, now)
    except Exception as exc:  # noqa: BLE001 — Selbstüberwachung darf nie brechen
        _log(f"notify übersprungen (fail-soft): {type(exc).__name__}: {exc}")
    return 0  # IMMER 0 — ein Push-Problem darf den Workflow nie rot färben


if __name__ == "__main__":
    raise SystemExit(main())
