"""Push-Paket Stufe 1 — reine Selbstüberwachung per ntfy. Bewusst fast stumm.

Meldet sich NUR, wenn etwas kaputt ist oder eine Entscheidung fällig wird:
  - Lauf-Fehlschlag  → eigener `if: failure()`-Step in daily.yml (nicht hier;
                       ein gebrochener Python-Pfad soll den Push nicht mitreißen).
  - Staleness        → separater Check-Cron erkennt den NICHT stattgefundenen Lauf
                       (`--mode staleness`).
  - Meilenstein n≥100 → einmaliger Push, Marker-Datei gegen Wiederholung.
  - Review-Wecker    → überfälliges `review_by` erinnert ~1×/Woche (Wochentag-
                       gedrosselt, KEIN State — Squeeze-Muster).
  - Score-Alert      → EINMALIGER Push je Episode, wenn ein Kandidat NEU die
                       TYP-Schwelle erreicht (`send_score_alert`, aus dem
                       Daily-Lauf; Flanke, nicht Zustand — die Kopplung an die
                       Episoden-Logik liegt in forward_collection.score_alert_edges).
                       Ausdrücklich ein Aufmerksamkeits-Hinweis, KEIN Signal.

KEINE Invalidierungs-Riss-/Tages-Pushes (Risse bleiben lautloser ✗-Status im
Backtesting). Der Score-Alert ist der EINZIGE kandidaten­bezogene Push und bewusst
flankengetriggert + fast stumm: über die gesamte committete Report-Historie
(Universum 361) erreichte KEIN Kandidat je >90 (Höchststand 89,84). Erwartete
Gesamt-Frequenz weiterhin sehr gering (< 1 Push/Monat).

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

import market_calendar as cal  # gemeinsamer Kalender (Gate + Staleness)  # noqa: E402

NTFY_BASE = "https://ntfy.sh"
# Pfade aus der config (health_check macht es bereits so) — ein zweiter,
# hartkodierter Pfad ist eine stille Divergenz, sobald einer umzieht.
REPORT_PATH = getattr(config, "REPORT_PATH", "data/report.json")
COLLECTION_PATH = "data/forward_collection.json"
MILESTONE_MARKER = "data/validation_milestone_fired.flag"

# EVAL_MIN_N lebt in forward_collection (Single Source), NICHT in config —
# von dort lesen, damit eine spätere Änderung hier nicht still divergiert.
EVAL_MIN_N = getattr(_fc, "EVAL_MIN_N", getattr(config, "EVAL_MIN_N", 100))
# Der Vorbehalt steht EINMAL in der config; keine Zweitfassung im Push-Text.
CARD_STATUS = getattr(config, "CARD_STATUS", "heuristisch · unvalidiert")
# Staleness-Entscheidung liegt komplett in market_calendar (kalenderbewusst) —
# notify hält KEINE eigene Stunden-Schwelle mehr.
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


_MARKET_FLAG = {"US": "🇺🇸", "DE": "🇩🇪"}


def score_alert_body(edges) -> str:
    """Gebündelter Alert-Text aus den neu-überschrittenen Kandidaten.

    ``edges`` = Liste {ticker, market, score, setup, threshold} (aus
    forward_collection.score_alert_edges). EIN Push pro Lauf, egal wie viele
    Ticker neu an ihrer Schwelle sind — Markt steht im Text. Trägt bewusst
    „heuristisch · unvalidiert": ein Aufmerksamkeits-Hinweis, KEIN Signal.

    Seit 31.07.2026 nennt der Text den SETUP-TYP und die KONKRETE Schwelle:
    die Schwelle ist typ-relativ, eine Zahl ohne ihren Bezug wäre irreführend
    (89 ist an der W4-Schwelle knapp, an der W2-Schwelle weit darüber)."""
    parts = []
    for e in edges:
        markt = _MARKET_FLAG.get(e.get("market"), e.get("market"))
        typ = config.SETUP_LABEL_MARKER.get(e.get("setup"), "Typ offen")
        schwelle = e.get("threshold")
        stueck = f"{e['ticker']} ({markt}) {e['score']:.0f} · {typ}"
        if isinstance(schwelle, (int, float)):
            stueck += f" (Schwelle {schwelle:.1f})"
        parts.append(stueck)
    return " · ".join(parts) + f" — {CARD_STATUS} (kein Signal)"


def send_score_alert(topic: str, edges) -> bool:
    """EIN gebündelter Push für die heute NEU an ihrer Schwelle angekommenen
    Kandidaten. Leere Liste -> kein Push. Fail-soft via send_ntfy.

    Die Schwelle steht seit 31.07.2026 JE KANDIDAT im Edge (typ-relativ), nicht
    mehr als ein Wert im Titel — deshalb ist der Parameter entfallen."""
    if not edges:
        return False
    return send_ntfy(
        topic,
        "Elliott: Score an der Typ-Schwelle",
        score_alert_body(edges),
        priority="default",  # Aufmerksamkeit, kein Alarm — Elliott bleibt fast stumm
        tags="chart_with_upwards_trend",
    )


# ---------------------------------------------------------------------------
# PURE Prüf-Funktionen (deterministisch, kein I/O) — direkt unit-testbar
# ---------------------------------------------------------------------------
def milestone_reached(evaluable: int, marker_exists: bool, min_n=EVAL_MIN_N) -> bool:
    """n≥min_n **auswertbar** UND noch nicht gemeldet (Marker fehlt).

    ``auswertbar`` = gereift UND nicht per PRU-Guard ausgeschlossen. Registry
    und Frontend zählen so; ``gereift`` ist die größere Menge und würde den
    Push zu früh auslösen (siehe forward_collection.eval_counts)."""
    return evaluable >= min_n and not marker_exists


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


def _evaluable_count(coll) -> int:
    """AUSWERTBARE Records (gereift UND nicht per PRU-Guard ausgeschlossen).

    Gezählt wird ausschließlich über ``forward_collection.eval_counts`` — keine
    zweite Zähl-Implementierung, die von der Registry-Definition wegdriften
    kann. Fehlt ``forward_collection``, wird 0 gemeldet (kein Push) statt auf
    eine Ersatzzählung auszuweichen: ein verpasster Meilenstein ist harmlos,
    ein zu früher nicht (der Marker macht ihn einmalig — und damit endgültig)."""
    if not coll or not isinstance(coll.get("records"), list):
        return 0
    if _fc is None or not hasattr(_fc, "eval_counts"):
        _log("forward_collection nicht verfügbar — Meilenstein-Zählung "
             "übersprungen (kein Push).")
        return 0
    try:
        return _fc.eval_counts(coll)[2]
    except Exception as exc:  # noqa: BLE001 — fail-soft, nie den Lauf reißen
        _log(f"eval_counts fehlgeschlagen (fail-soft, kein Push): {exc}")
        return 0


def _run_url() -> str:
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repo = os.environ.get("GITHUB_REPOSITORY", "easywebb911/Elliott-Report")
    rid = os.environ.get("GITHUB_RUN_ID", "")
    return f"{server}/{repo}/actions/runs/{rid}" if rid else f"{server}/{repo}/actions"


# ---------------------------------------------------------------------------
# Modi (von den Workflows aufgerufen)
# ---------------------------------------------------------------------------
def run_staleness(topic: str, now: _dt.datetime) -> bool:
    """Separater Cron: erkennt auch den NICHT stattgefundenen Lauf.

    KALENDERBEWUSST (market_calendar): stale nur, wenn der letzte ERWARTETE
    Handelstags-Lauf keinen frischen Report hinterlassen hat. Wochenende/
    Feiertag erzeugen KEINEN Fehlalarm (kein Lauf war erwartet)."""
    report = _load_json(REPORT_PATH)
    ts = (report or {}).get("run_timestamp_utc")
    if not cal.is_stale(ts, now):
        age = cal.age_hours(ts, now)
        _log(f"Report aktuell zum Kalender ({(age or 0):.1f} h) → kein Push.")
        return False
    age = cal.age_hours(ts, now)
    age_txt = f"{age:.0f} h" if age is not None else "unbekannt (report.json unlesbar)"
    exp = cal.last_expected_run(now)
    exp_txt = exp.strftime("%Y-%m-%d %H:%M UTC") if exp else "?"
    day = now.strftime("%Y-%m-%d")
    return send_ntfy(
        topic,
        "Elliott: Report veraltet",
        f"Kein frischer Report seit dem letzten erwarteten Lauf ({exp_txt}) · "
        f"Report {age_txt} alt · {day} · Lauf ausgefallen? {_run_url()}",
        priority="high", tags="warning,hourglass",
    )


def run_daily(topic: str, now: _dt.datetime) -> dict:
    """Im Daily-Lauf NACH der Pipeline: Meilenstein + Review-Wecker.

    Legt bei Meilenstein-Push die Marker-Datei an (der Commit-Schritt in
    daily.yml committet sie → einmalig). Gibt {milestone, review} (bool) zurück.
    """
    out = {"milestone": False, "review": False}
    coll = _load_json(COLLECTION_PATH)
    evaluable = _evaluable_count(coll)
    marker = REPO_ROOT / MILESTONE_MARKER

    if milestone_reached(evaluable, marker.exists()):
        sent = send_ntfy(
            topic,
            "Elliott: Validierungs-Auswertung faellig",
            f"n≥{EVAL_MIN_N} auswertbare Setups erreicht ({evaluable}). "
            f"Auswertung gemäß validation_registry.md fällig.",
            priority="high", tags="tada,white_check_mark",
        )
        # Marker IMMER setzen, sobald die Schwelle erreicht ist (auch wenn Topic
        # leer war) → kein Dauer-Push, sobald Easy das Topic später scharfschaltet
        # wäre der Meilenstein bereits „verbucht"; bewusst so (Einmaligkeit vor
        # Zustellgarantie). Kommentar im PR.
        try:
            marker.write_text(
                f"milestone n>={EVAL_MIN_N} erreicht ({evaluable} auswertbar) "
                f"am {now.strftime('%Y-%m-%dT%H:%M:%SZ')}\n", encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            _log(f"Marker konnte nicht geschrieben werden (fail-soft): {exc}")
        out["milestone"] = bool(sent)
    else:
        _log(f"Meilenstein: {evaluable}/{EVAL_MIN_N} auswertbar, Marker "
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


def run_selftest(topic: str, now: _dt.datetime) -> bool:
    """EIN harmloser Bestätigungs-Push — beweist die Verdrahtung Ende zu Ende.

    Anlass (27.07.2026): Das Secret `NTFY_TOPIC` war gesetzt und funktionierte,
    aber der Step „Run pipeline" in daily.yml reichte es nicht durch — GitHub
    Actions vererbt Secrets nicht in Steps. Score-Alert (#24) und Health-Check
    (#51) leben INNERHALB der Pipeline und waren dadurch still. Fail-soft heißt:
    kein Fehler, keine rote CI, kein Hinweis. Genau deshalb braucht die
    Verdrahtung einen Weg, sich EINMAL bewusst zu beweisen.

    Wird nur per `workflow_dispatch`-Schalter ausgelöst, nie automatisch.
    """
    return send_ntfy(
        topic,
        "Elliott: Push-Verdrahtung ok",
        f"Selbsttest {now.strftime('%Y-%m-%d %H:%M UTC')} — dieser Push kam aus "
        f"demselben Prozess wie Score-Alert und Health-Check. Kein Befund, "
        f"keine Handlung nötig.",
        priority="low", tags="white_check_mark",
    )


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", required=True,
                   choices=["staleness", "daily", "selftest"])
    args = p.parse_args(argv)
    topic = os.environ.get("NTFY_TOPIC", "")
    now = _dt.datetime.now(_dt.timezone.utc)
    try:
        if args.mode == "staleness":
            run_staleness(topic, now)
        elif args.mode == "selftest":
            run_selftest(topic, now)
        else:
            run_daily(topic, now)
    except Exception as exc:  # noqa: BLE001 — Selbstüberwachung darf nie brechen
        _log(f"notify übersprungen (fail-soft): {type(exc).__name__}: {exc}")
    return 0  # IMMER 0 — ein Push-Problem darf den Workflow nie rot färben


if __name__ == "__main__":
    raise SystemExit(main())
