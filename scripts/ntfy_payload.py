#!/usr/bin/env python3
"""ntfy-Weiterleitung (Easy-Entscheid 30.10.2026, Auftrag 4 von 6) —
baut aus Umgebungsvariablen ein sicheres JSON-Payload für ntfys
JSON-Publish-API (`POST https://ntfy.sh/` mit Content-Type
application/json; Felder `topic`/`title`/`message`/`tags`/`priority`,
belegt gegen die ntfy-Dokumentation) und schreibt es in eine temporäre
Datei. ABHÄNGIGKEITSFREI (nur Stdlib) — bewusst NICHT an
`scripts/repo_path.py`/`config.py` gekoppelt, dieses Skript hat keinen
Bezug zu Score/Ranking/Sammlung.

SICHERHEITSZIEL (wörtlich aus dem Auftrag): kein Eingabetext darf
Befehle ausführen oder HTTP-Header manipulieren, nichts Vertrauliches
landet im Protokoll. Erreicht durch:
  1. Eingaben kommen NUR über Umgebungsvariablen herein (nie über
     `${{ inputs.* }}`/`${{ github.event.* }}` direkt in einem
     `run:`-Block des Workflows — das verhindert Shell-Injektion
     strukturell, nicht nur durch Filterung hier).
  2. Das Ergebnis ist ausschließlich JSON (per `json.dumps`, nie
     String-Konkatenation) — es gibt dadurch keinen HTTP-Header, den
     ein Eingabetext manipulieren könnte (anders als bei ntfys
     Header-Modus, den `scripts/notify.py` nutzt, s. dort).
  3. `NTFY_TOPIC` wird gelesen und ins JSON geschrieben, aber an
     KEINER Stelle geloggt/ausgegeben (dieses Skript gibt im
     Erfolgsfall nur den Pfad der temporären Datei aus, bei Fehlern
     nur eine generische Meldung ohne Eingabewerte).

FRAGILE ANNAHME (Schritt 0a/6, belegt): ntfy unterstützt JSON-Publish
am SERVER-ROOT (`https://ntfy.sh/`, NICHT `https://ntfy.sh/{topic}` —
das ist der bestehende Header-Modus-Pfad in `scripts/notify.py` und
bleibt dort unverändert), mit `topic` als Pflichtfeld im JSON-Body,
`priority` als Ganzzahl 1–5 (Default 3), `tags` als Liste von Strings.
Secret-Name `NTFY_TOPIC` identisch zu `scripts/notify.py`/den
bestehenden Workflows — KEIN neues Secret.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile

NTFY_BASE = "https://ntfy.sh"  # JSON-Publish-Endpunkt ist die ROOT, kein /{topic}

TITLE_MAX_ZEICHEN = 100
TAGS_MAX = 5
MESSAGE_MAX_BYTES = 3900
GEKUERZT_HINWEIS = "\n[gekürzt]"

# C0-Steuerzeichen (inkl. CR/LF) UND DEL — title/tags sind einzeilig, ein
# eingeschleustes "\r\n" könnte sonst wie ein zweiter Header/eine zweite
# Zeile aussehen, sobald ein Aufrufer diese Werte je in Header-Form nutzt.
_STEUERZEICHEN = re.compile(r"[\x00-\x1f\x7f]")
_TAG_UNERLAUBT = re.compile(r"[^a-z0-9_,-]")


class NtfyPayloadFehler(ValueError):
    """Eingabe konnte nicht zu einem gültigen Payload werden (z. B. leere
    message). Der Aufrufer (CLI-`main`) übersetzt das in einen Abbruch OHNE
    die Eingabe selbst auszugeben."""


def _ohne_steuerzeichen(roh: str) -> str:
    return _STEUERZEICHEN.sub("", roh)


def sanitize_title(roh: str) -> str:
    """CR/LF/Steuerzeichen entfernen, auf 100 Zeichen kürzen."""
    return _ohne_steuerzeichen(roh)[:TITLE_MAX_ZEICHEN]


def sanitize_tags(roh: str) -> list:
    """Komma-getrennt; je Tag CR/LF/Steuerzeichen entfernen, nur
    [a-z0-9_,-] behalten (Rest verwerfen), leere Tags verwerfen, höchstens
    5 Tags — in Eingabe-Reihenfolge, überzählige werden verworfen."""
    ergebnis: list = []
    for teil in _ohne_steuerzeichen(roh).split(","):
        tag = _TAG_UNERLAUBT.sub("", teil.strip())
        if tag:
            ergebnis.append(tag)
        if len(ergebnis) >= TAGS_MAX:
            break
    return ergebnis


def sanitize_priority(roh: str) -> int:
    """Nur 1..5 (Ganzzahl) ist gültig, sonst Default 3 — auch bei leerem
    String, nicht-numerischem Text oder float-artigen Werten ("3.0")."""
    try:
        wert = int(str(roh).strip())
    except (TypeError, ValueError):
        return 3
    return wert if 1 <= wert <= 5 else 3


def sanitize_message(roh: str) -> str:
    """UTF-8-sicher auf höchstens `MESSAGE_MAX_BYTES` kürzen (Hinweis
    inklusive) — niemals mitten in einem Mehrbyte-Zeichen abschneiden.
    Leere message (nach Strip) ist ein Fehler, s. `NtfyPayloadFehler`."""
    if not roh.strip():
        raise NtfyPayloadFehler("message ist leer")
    kodiert = roh.encode("utf-8")
    if len(kodiert) <= MESSAGE_MAX_BYTES:
        return roh
    hinweis_bytes = GEKUERZT_HINWEIS.encode("utf-8")
    grenze = MESSAGE_MAX_BYTES - len(hinweis_bytes)
    gekuerzt = kodiert[:max(grenze, 0)]
    # Byte-Grenze kann mitten in einem Mehrbyte-UTF-8-Zeichen liegen —
    # byteweise zurückgehen, bis der Rest wieder gültiges UTF-8 ist.
    while gekuerzt:
        try:
            text = gekuerzt.decode("utf-8")
            break
        except UnicodeDecodeError:
            gekuerzt = gekuerzt[:-1]
    else:
        text = ""
    return text + GEKUERZT_HINWEIS


def build_payload(topic: str, title: str, message: str, tags: str,
                   priority: str) -> dict:
    """Reine Funktion: Umgebungswerte -> fertiges, sicheres JSON-Objekt für
    ntfys JSON-Publish-API. Wirft `NtfyPayloadFehler` bei leerer message —
    KEIN Fallback-Text, der Aufruf soll sichtbar scheitern."""
    return {
        "topic": topic,
        "title": sanitize_title(title),
        "message": sanitize_message(message),
        "tags": sanitize_tags(tags),
        "priority": sanitize_priority(priority),
    }


def schreibe_payload_datei(payload: dict) -> str:
    """Schreibt `payload` als JSON in eine neue temporäre Datei und gibt
    deren Pfad zurück. Eigene Datei (statt stdout), damit der Aufrufer
    (curl --data-binary @datei) die Werte nie über eine Kommandozeile oder
    einen Log-Stream reichen muss."""
    fd, pfad = tempfile.mkstemp(prefix="ntfy_payload_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception:
        os.unlink(pfad)
        raise
    return pfad


def main(argv=None) -> int:
    topic = os.environ.get("NTFY_TOPIC", "")
    if not topic:
        print("Fehler: NTFY_TOPIC ist nicht gesetzt.", file=sys.stderr)
        return 1

    titel = os.environ.get("NTFY_IN_TITLE", "")
    nachricht = os.environ.get("NTFY_IN_MESSAGE", "")
    tags = os.environ.get("NTFY_IN_TAGS", "")
    prioritaet = os.environ.get("NTFY_IN_PRIORITY", "")

    try:
        payload = build_payload(topic, titel, nachricht, tags, prioritaet)
    except NtfyPayloadFehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1

    pfad = schreibe_payload_datei(payload)
    print(pfad)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
