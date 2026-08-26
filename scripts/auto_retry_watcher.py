#!/usr/bin/env python3
"""Selbstwartung Stufe 3 — automatischer Retry bei Fehlschlag des Tageslaufs.

ERSTE PRODUKTIVE SELBST-HANDLUNG im Repo (GO von Easy nach ausführlicher
Risikoabwägung, siehe PR-Text). Bis hierhin durfte die Selbstwartung
(Stufe 1/2: ``health_check.py`` im Tageslauf, ``maintenance_check.py``
wöchentlich) NUR MELDEN, nie HANDELN — ``tests/test_wartungs_cron.py::
test_der_wartungslauf_HANDELT_nie`` verbietet ``unlink``/``subprocess``/
``workflow_dispatch`` explizit in ``scripts/maintenance_check.py``. Dieses
Modul ist bewusst ein EIGENES, NEUES Skript — keine Erweiterung von
``maintenance_check.py``. Das Verbot dort bleibt unangetastet und gilt
weiterhin ausschließlich für den reinen Struktur-Wächter.

HARTE GRENZE, NICHT KONFIGURIERBAR: maximal ``MAX_RETRIES_PRO_TAG`` (= 3)
automatische Retries pro Kalendertag (UTC). Das ist die EINZIGE Verteidigung
gegen eine Endlosschleife (Leitplanke 1 im Bau-Auftrag) — deshalb ein
Modul-Konstante im Code, nicht per Parameter/Secret/Env veränderbar, und der
Vergleich ist bewusst ``>=`` (nicht ``>``): eine frühere Score-Schwelle, die
GENAU am Maximum lag, hat historisch nie ausgelöst — siehe
``test_entscheidung_genau_drei_liefert_erschoepft_nicht_retry``.

ZÄHLER-MECHANIK: kein State-File-Zeitstempel-Reset um Mitternacht nötig — der
Zähler ist keine Zahl, sondern eine Liste datierter Einträge
(``data/auto_retry_state.json``); "heute" wird bei jedem Lauf frisch durch
Filtern auf ``date == heute`` bestimmt. Der Mitternachts-Reset ist damit eine
Eigenschaft des Filters, kein separater Reset-Schritt, der vergessen werden
könnte.

RACE-HÄRTUNG: ``daily.yml`` läuft über seine eigene ``concurrency``-Gruppe
serialisiert — pro abgeschlossenem Lauf feuert genau ein
``workflow_run: completed``-Ereignis, das diesen Watcher startet. Der Watcher
selbst hat zusätzlich eine eigene ``concurrency``-Gruppe (siehe Workflow-YAML)
UND committet seinen State mit demselben Rebase-Retry-Muster wie
``daily.yml``/``maintenance.yml`` (mehrfach abgesichert statt einer einzelnen
Verteidigungslinie).

KENNZEICHNUNG: ein Retry-Dispatch wird NUR in ``data/auto_retry_state.json``
festgehalten (eigene Datei, eigenes Feld — keine Vermischung mit den drei
bestehenden Qualitäts-Markern ``episode_split_suspect``/
``stale_market_suspect``/``in_session_creation``, die in
``forward_collection.json`` leben). Eine spätere Auswertung verknüpft einen
Report-/Sammlungs-Lauf über den Zeitstempel ``utc_time`` mit diesem Log.
Bewusst KEIN eingebettetes Feld direkt in ``forward_collection.json``: das
hätte eine Änderung an ``evaluate.py`` oder ``daily.yml`` selbst erfordert,
und beide sind laut Auftrags-Grenzen tabu (im PR-Text als Abwägung
dokumentiert).

KEIN INPUT-PARAMETER BEIM DISPATCH: ``daily.yml`` deklariert in seinem
``workflow_dispatch`` bislang nur den Input ``push_selftest`` — die
GitHub-API weist einen Dispatch-Aufruf mit nicht deklarierten zusätzlichen
Inputs zurück. Ein `triggered_by=auto-retry`-Input hätte also eine Änderung
an ``daily.yml`` selbst erfordert (ebenfalls tabu). Die Kennzeichnung des
Laufs als automatisch ausgelöst passiert stattdessen ausschließlich über
diesen Watcher-eigenen State/Log und die ntfy-Push-Meldung — nicht über einen
Dispatch-Input.

RATE-LIMIT-REGEL: ein per Rate-Limit abgelehnter Dispatch-Versuch wird SOFORT
gemeldet, NIE automatisch wiederholt, UND zählt nicht als verbrauchter
Retry-Slot (es wurde ja tatsächlich kein Lauf ausgelöst). Ein Netzfehler
(Verbindungsabbruch) ist KEIN Rate-Limit und darf mit kurzem Backoff
wiederholt werden (``dispatch_retry``).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

import repo_path  # noqa: F401,E402 — EIN Pfad-Baustein (Repo-Root + scripts/)

REPO_ROOT = repo_path.REPO_ROOT

import notify  # noqa: E402 — EINE ntfy-Schicht, kein Nachbau

STATE_PATH = "data/auto_retry_state.json"
DAILY_WORKFLOW_DATEI = "daily.yml"

# HART, NICHT KONFIGURIERBAR (Leitplanke 1) — siehe Modul-Docstring.
MAX_RETRIES_PRO_TAG = 3


def _log(msg: str) -> None:
    print(f"[auto-retry] {msg}", flush=True)


def _warne(msg: str) -> None:
    print(f"::warning::[auto-retry] {msg}", flush=True)


# ---------------------------------------------------------------------------
# State: Laden/Schreiben (Muster aus maintenance_check.py)
# ---------------------------------------------------------------------------
def load_state(base: Optional[Path] = None) -> Dict:
    try:
        with ((base or REPO_ROOT) / STATE_PATH).open(encoding="utf-8") as fh:
            st = json.load(fh)
        return st if isinstance(st, dict) else {}
    except Exception:  # noqa: BLE001 — fehlend/unlesbar = leerer State
        return {}


def write_state(state: Dict, now_iso: str, base: Optional[Path] = None) -> bool:
    try:
        pfad = (base or REPO_ROOT) / STATE_PATH
        pfad.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(state)
        payload["schema_version"] = 1
        payload["updated_utc"] = now_iso
        with pfad.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        return True
    except Exception as exc:  # noqa: BLE001
        _warne(f"State nicht schreibbar: {type(exc).__name__}: {exc}")
        return False


# ---------------------------------------------------------------------------
# PURE Zähler-/Entscheidungslogik (deterministisch, kein I/O) — direkt testbar
# ---------------------------------------------------------------------------
def anzahl_heute(state: Dict, heute: str) -> int:
    """Anzahl bereits ausgelöster Retries für den Kalendertag ``heute``
    (ISO-Datum, UTC). Der Mitternachts-Reset ist ALLEIN dieser Filter — kein
    separater Reset-Schritt nötig."""
    eintraege = state.get("retries") or []
    return sum(1 for e in eintraege
               if isinstance(e, dict) and e.get("date") == heute)


def entscheidung(anzahl: int) -> str:
    """'retry' oder 'erschoepft'. STRIKT ``>=``, nicht ``>`` — siehe
    Modul-Docstring (Lehre aus dem historischen Score-Schwellen-Bug)."""
    return "erschoepft" if anzahl >= MAX_RETRIES_PRO_TAG else "retry"


# ---------------------------------------------------------------------------
# Dispatch: dünne HTTP-Schicht (Tests ersetzen sie ohne Netz, wie notify._post)
# ---------------------------------------------------------------------------
class RateLimitFehler(Exception):
    """GitHub-API-Rate-Limit — laut Auftrag SOFORT melden, NIE automatisch
    wiederholen."""


class NetzwerkFehler(Exception):
    """Verbindungsabbruch o.ä. — KEIN Rate-Limit, darf mit kurzem Backoff
    wiederholt werden."""


def _klassifiziere_http_fehler(status: int, reason: str,
                                rate_limit_remaining: Optional[str] = None,
                                retry_after: Optional[str] = None) -> Exception:
    """Reine Klassifikation eines HTTP-Fehlers in ein Exception-Objekt — kein
    Netz, direkt unit-testbar (Guardian-Nit 27.08.2026: die Klassifikation
    selbst war vorher nur indirekt über injizierte Fake-Exceptions getestet,
    nie über echte Status-/Header-Kombinationen).

    Primäres Rate-Limit: HTTP 403 mit `X-RateLimit-Remaining: 0`.
    Sekundäres Rate-Limit (Abuse-Detection): HTTP 403 mit `Retry-After`-Header
    (kein `X-RateLimit-Remaining` dabei) ODER HTTP 429.
    Jeder andere 403/4xx/5xx: kein Rate-Limit, sondern ein "sonstiger" Fehler
    (z. B. fehlende Berechtigung, falscher Workflow-Dateiname)."""
    ist_primaeres_limit = status == 403 and rate_limit_remaining == "0"
    ist_sekundaeres_limit = status == 403 and retry_after is not None
    if status == 429 or ist_primaeres_limit or ist_sekundaeres_limit:
        return RateLimitFehler(f"HTTP {status}: {reason}")
    return RuntimeError(f"HTTP {status}: {reason}")


def _dispatch_post(url: str, headers: Dict, payload: Dict,
                    timeout: int) -> int:  # pragma: no cover
    """Reiner HTTP-POST an die GitHub-Dispatch-API. Gibt den HTTP-Status
    zurück (Erfolg = 204, kein Body). Stdlib statt `requests` — keine neue
    Abhängigkeit für einen einzigen Aufruf. Die eigentliche Fehler-
    Klassifikation steckt in `_klassifiziere_http_fehler` (testbar ohne
    Netz) — diese Funktion holt nur die Header heraus."""
    import urllib.error
    import urllib.request

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        remaining = retry_after = None
        try:
            if exc.headers:
                remaining = exc.headers.get("X-RateLimit-Remaining")
                retry_after = exc.headers.get("Retry-After")
        except Exception:  # noqa: BLE001 — defensiv, Header-Zugriff kann variieren
            remaining = retry_after = None
        raise _klassifiziere_http_fehler(
            exc.code, exc.reason, remaining, retry_after) from exc
    except urllib.error.URLError as exc:
        raise NetzwerkFehler(str(exc.reason)) from exc


def dispatch_retry(owner: str, repo: str, token: str,
                    workflow_datei: str = DAILY_WORKFLOW_DATEI,
                    ref: str = "main", timeout: int = 15,
                    post=None, schlaf=None, versuche: int = 3) -> Dict:
    """Löst ``workflow_datei`` per ``workflow_dispatch`` aus.

    Rate-Limit: sofortiger Abbruch, KEIN Retry (Auftrags-Vorgabe).
    Netzfehler: bis zu ``versuche``-mal mit kurzem, wachsendem Backoff.
    Jeder andere Fehler: sofortiger Abbruch, gemeldet (kein blindes
    Wiederholen unbekannter Fehlerarten)."""
    post = post or _dispatch_post
    schlaf = schlaf or time.sleep
    url = (f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/"
           f"{workflow_datei}/dispatches")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    }
    payload = {"ref": ref}

    letzter_fehler = "unbekannt"
    for versuch in range(1, versuche + 1):
        try:
            status = post(url, headers, payload, timeout)
        except RateLimitFehler as exc:
            return {"ok": False, "art": "rate_limit", "fehler": str(exc),
                    "versuch": versuch}
        except NetzwerkFehler as exc:
            letzter_fehler = str(exc)
            if versuch < versuche:
                schlaf(versuch * 2)
                continue
            return {"ok": False, "art": "netzwerk", "fehler": letzter_fehler,
                    "versuch": versuch}
        except Exception as exc:  # noqa: BLE001 — jede andere Art: sofort melden
            return {"ok": False, "art": "sonstig",
                    "fehler": f"{type(exc).__name__}: {exc}", "versuch": versuch}
        else:
            if status == 204:
                return {"ok": True, "status": status, "versuch": versuch}
            return {"ok": False, "art": "sonstig",
                    "fehler": f"unerwarteter Status {status}", "versuch": versuch}
    return {"ok": False, "art": "netzwerk", "fehler": letzter_fehler,
            "versuch": versuche}


# ---------------------------------------------------------------------------
# Orchestrierung
# ---------------------------------------------------------------------------
def run(now: _dt.datetime, owner: str, repo: str, token: str, ntfy_topic: str,
        quelle_run_id, quelle_run_url: str, quelle_conclusion: str,
        base: Optional[Path] = None, schreiben: bool = True,
        post=None, schlaf=None) -> Dict:
    """Ein kompletter Watcher-Lauf. Reagiert AUSSCHLIESSLICH auf
    ``conclusion == 'failure'`` — health_check-Warnungen innerhalb eines
    technisch erfolgreichen Laufs sind bewusst außerhalb dieses Auftrags."""
    if quelle_conclusion != "failure":
        _log(f"conclusion={quelle_conclusion!r} — kein Fehlschlag, "
             f"Watcher tut nichts.")
        return {"aktion": "ignoriert", "grund": "kein_fehlschlag"}

    state = load_state(base)
    heute = now.date().isoformat()
    n_heute = anzahl_heute(state, heute)
    entscheid = entscheidung(n_heute)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    if entscheid == "erschoepft":
        text = (f"{MAX_RETRIES_PRO_TAG} automatische Retries erschöpft, kein "
                f"weiterer Versuch heute ({heute}), manuelle Prüfung nötig. "
                f"Letzter Fehlschlag: {quelle_run_url}")
        gepusht = notify.send_ntfy(
            ntfy_topic, "Elliott: Auto-Retry erschöpft", text,
            priority="high", tags="rotating_light")
        _log(f"Tagesgrenze erreicht ({n_heute}/{MAX_RETRIES_PRO_TAG}) — "
             f"kein Dispatch.")
        return {"aktion": "erschoepft", "anzahl_heute": n_heute,
                "gepusht": bool(gepusht)}

    retry_nummer = n_heute + 1
    ergebnis = dispatch_retry(owner, repo, token, DAILY_WORKFLOW_DATEI,
                               ref="main", post=post, schlaf=schlaf)

    if not ergebnis["ok"]:
        if ergebnis["art"] == "rate_limit":
            text = (f"Auto-Retry Nr. {retry_nummer} von {MAX_RETRIES_PRO_TAG} "
                     f"NICHT ausgelöst — GitHub-API-Rate-Limit erreicht: "
                     f"{ergebnis['fehler']}. Kein automatischer Wiederholungs"
                     f"versuch (Rate-Limit-Regel). Manuelle Prüfung nötig.")
        else:
            text = (f"Auto-Retry Nr. {retry_nummer} von {MAX_RETRIES_PRO_TAG} "
                     f"NICHT ausgelöst — Dispatch-Fehler ({ergebnis['art']}): "
                     f"{ergebnis['fehler']}.")
        gepusht = notify.send_ntfy(
            ntfy_topic, "Elliott: Auto-Retry fehlgeschlagen", text,
            priority="high", tags="rotating_light")
        _warne(f"Dispatch fehlgeschlagen ({ergebnis['art']}): "
               f"{ergebnis['fehler']}")
        return {"aktion": "dispatch_fehlgeschlagen", **ergebnis,
                "gepusht": bool(gepusht)}

    # Zähler steigt NUR bei tatsächlich erfolgreichem Dispatch (204) —
    # ein fehlgeschlagener Versuch hat keinen neuen daily.yml-Lauf erzeugt
    # und verbraucht deshalb keinen der drei Slots.
    eintrag = {
        "date": heute,
        "retry_number": retry_nummer,
        "utc_time": now_iso,
        "source_run_id": quelle_run_id,
        "source_run_url": quelle_run_url,
        "source_conclusion": quelle_conclusion,
    }
    retries: List[Dict] = list(state.get("retries") or [])
    retries.append(eintrag)
    neuer_state = dict(state)
    neuer_state["retries"] = retries

    zustand_geschrieben = True
    if schreiben:
        zustand_geschrieben = write_state(neuer_state, now_iso, base)

    text = (f"Automatischer Retry Nr. {retry_nummer} von "
            f"{MAX_RETRIES_PRO_TAG} ausgelöst, aufgrund Fehlschlags von "
            f"daily.yml: {quelle_run_url}")
    gepusht = notify.send_ntfy(
        ntfy_topic, "Elliott: Auto-Retry ausgelöst", text,
        priority="default", tags="arrows_counterclockwise")
    _log(f"Retry {retry_nummer}/{MAX_RETRIES_PRO_TAG} ausgelöst für "
         f"{quelle_run_url}.")

    # GUARDIAN-FUND 27.08.2026: ein Dispatch, der ausgelöst wurde, dessen
    # Zähler-Eintrag aber NICHT persistiert werden konnte, wäre die einzige
    # Verteidigung (Leitplanke 1) unbemerkt aufgeweicht — der nächste
    # Watcher-Lauf läse den zu niedrigen alten Stand und gewährte einen
    # zusätzlichen Retry über die Tagesgrenze hinaus. Deshalb: eigener,
    # lauter Push + eigene `aktion`, statt den bool-Rückgabewert von
    # `write_state` stillschweigend zu verwerfen. Der SEPARATE Fall "lokal
    # geschrieben, aber der anschließende Git-Push in der Workflow-YAML
    # schlägt fehl" liegt außerhalb der Sicht dieses Skripts — dafür hat
    # `daily_retry_watcher.yml` einen eigenen `if: steps.commit.outcome ==
    # 'failure'`-Push-Schritt (Muster aus daily.yml).
    if not zustand_geschrieben:
        warntext = (f"Auto-Retry Nr. {retry_nummer} wurde ausgelöst, aber der "
                    f"Zähler-State ({STATE_PATH}) konnte lokal NICHT "
                    f"geschrieben werden — die Tagesgrenze könnte beim "
                    f"nächsten Fehlschlag zu hoch ausfallen. Manuelle Prüfung "
                    f"nötig.")
        notify.send_ntfy(
            ntfy_topic, "Elliott: Auto-Retry State-Fehler", warntext,
            priority="high", tags="rotating_light")
        _warne("Zähler-State konnte nicht geschrieben werden — Retry wurde "
               "trotzdem ausgelöst.")
        return {"aktion": "retry_ausgeloest_state_fehler",
                "retry_number": retry_nummer, "gepusht": bool(gepusht),
                "state": neuer_state}

    return {"aktion": "retry_ausgeloest", "retry_number": retry_nummer,
            "gepusht": bool(gepusht), "state": neuer_state}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.parse_args(argv)
    now = _dt.datetime.now(_dt.timezone.utc)
    owner_repo = os.environ.get("GITHUB_REPOSITORY", "/")
    owner, _, repo = owner_repo.partition("/")
    token = os.environ.get("GITHUB_TOKEN", "")
    ntfy_topic = os.environ.get("NTFY_TOPIC", "")
    quelle_run_id = os.environ.get("SOURCE_RUN_ID", "")
    quelle_run_url = os.environ.get("SOURCE_RUN_URL", "")
    quelle_conclusion = os.environ.get("SOURCE_CONCLUSION", "")
    try:
        run(now, owner, repo, token, ntfy_topic, quelle_run_id,
            quelle_run_url, quelle_conclusion)
    except Exception as exc:  # noqa: BLE001 — fail-soft wie überall
        _warne(f"Watcher abgebrochen: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
