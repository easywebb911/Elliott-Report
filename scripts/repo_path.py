#!/usr/bin/env python3
"""EIN Pfad-Baustein für alle Skripte, die `config` importieren.

DAS PROBLEM, zweimal teuer bezahlt (#69 und die Inventur vom 08.08.2026):
`config.py` liegt im **Repo-Root**, die Module in `scripts/`. Beim Start **als
Skript** — genau so ruft `daily.yml` sie auf (`python scripts/notify.py …`) —
setzt Python `sys.path[0]` auf das **Skript-Verzeichnis**, nicht auf das
Arbeitsverzeichnis. Wer den Repo-Root nicht selbst auf den Pfad legt, findet
`config` nicht.

WARUM DAS SO LANGE UNSICHTBAR BLIEB: die betroffenen Module fangen den
Import-Fehler ab und fallen auf `getattr(config, …, <Literal>)`-Werte zurück.
Diese Literale stimmen mit den echten Werten überein — der Ausfall sieht also
aus wie Normalbetrieb. In #69 hat das den **Meilenstein-Push** und den
**Review-Wecker** acht Tage lang totgestellt; die Inventur vom 08.08. fand
dieselbe Konstruktion in `health_check` wieder, dort mit **13** solchen
Rückfällen und **ohne jede Logzeile**.

DESHALB EINE STELLE STATT VIELER KOPIEN. Wer hier etwas ändert, ändert es für
alle.

STAND 08.08.2026 — ehrlich gezählt, nicht geschätzt: dieser Block existierte in
`scripts/` **neunmal**. Genutzt wird der gemeinsame Baustein bisher von
`health_check.py` und `notify.py` (Auftrags-Rahmen); **sieben** Eigenkopien
stehen noch. Die Liste ist kein Kommentar, der altert — ein Test vergleicht sie
mit der Wirklichkeit und wird rot, sobald sie nicht mehr stimmt:

EIGENKOPIEN-ANFANG
    elliott_pipeline.py · evaluate.py · in_session.py ·
    mark_in_session_creation.py · collect_in_session_evidence.py ·
    mark_stale_market_records.py · source_timing_probe.py
EIGENKOPIEN-ENDE

Dass Kopien auseinanderlaufen, ist dort keine Vermutung mehr, sondern schon
passiert: fünf legen beide Verzeichnisse mit Dubletten-Schutz auf den Pfad,
`source_timing_probe.py` beide **ohne** Schutz, `mark_stale_market_records.py`
nur `scripts/` (dort heute unschädlich — es importiert `config` nicht). Der
Umbau der sieben ist bewusst NICHT Teil dieser Änderung; er gehört in einen
eigenen Auftrag, weil `elliott_pipeline.py` zum Messlauf-Pfad zählt.

BENUTZUNG — als erste Zeile vor `import config`:

    import repo_path  # noqa: F401 — legt Repo-Root + scripts/ auf sys.path
    import config

Der Import **wirkt beim Importieren** (Nebenwirkung, keine Aufruf-Pflicht),
damit die eine Zeile genügt und niemand `ensure()` vergessen kann.

WARUM DIESES MODUL SELBST IMMER GEFUNDEN WIRD: es liegt in `scripts/`, also
neben seinen Aufrufern. Bei einem Skript-Start ist `sys.path[0]` genau dieses
Verzeichnis; bei einem Import aus einem anderen `scripts/`-Modul hat der
Importeur `scripts/` bereits auf dem Pfad. Ein Bootstrap-Problem kann es also
nicht geben — `tests/test_pfad_baustein_und_laute_ausfaelle.py` fährt die
Einstiege als Kindprozess mit neutralem Arbeitsverzeichnis durch.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"


def ensure() -> None:
    """Legt Repo-Root und `scripts/` vorne auf ``sys.path`` (idempotent).

    Reihenfolge wie in der gewachsenen Fassung: erst der Root, dann `scripts/`
    — beide werden vorne eingefügt, `scripts/` landet also davor. Das ist
    dasselbe Ergebnis wie bisher; ein Test hält die Menge fest.
    """
    for pfad in (str(REPO_ROOT), str(SCRIPTS)):
        if pfad not in sys.path:
            sys.path.insert(0, pfad)


ensure()
