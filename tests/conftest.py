"""Pytest-Setup: Repo-Root und scripts/ auf den Importpfad legen."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
for p in (str(ROOT), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)


# Umgebungsvariablen, die der PRODUKTIONSCODE liest. Wer sie nicht wegräumt,
# lässt die Tests von der Umgebung abhängen, in der sie zufällig laufen.
NEUTRALE_UMGEBUNG = (
    "GITHUB_REF",          # health_check.is_main_run()
    "ELLIOTT_OFFLINE",     # elliott_pipeline: Abruf-Abschaltung
    "ANTHROPIC_API_KEY",   # elliott_pipeline.main(): Agent-Kommentare
    "NTFY_TOPIC",          # elliott_pipeline.main(): Push-Ziel
    # notify._run_url(): in der CI steht hier die echte Lauf-URL, lokal nicht.
    # Dieselbe Falle wie GITHUB_REF, nur noch ungezündet — ein Test über einen
    # Push-Text würde je nach Läufer verschieden ausfallen.
    "GITHUB_SERVER_URL",
    "GITHUB_REPOSITORY",
    "GITHUB_RUN_ID",
)


#: Lebenszeichen des Wartungs-Crons für Sandbox-Repos.
#:
#: Seit der Regel ``health_check.check_maintenance`` (09.08.2026) ist ein Repo
#: OHNE ``data/maintenance_state.json`` ein Repo mit einem Befund — zu Recht:
#: dann weiß niemand, ob der Wartungs-Cron je lief. Ein Sandbox-Repo, das einen
#: GESUNDEN Lauf darstellen soll, braucht die Datei deshalb genauso wie das
#: echte. Sie hier zu erzeugen ist kein Zurechtbiegen des Tests, sondern das
#: Nachstellen der realen Ausgangslage.
#:
#: Der Vorgabewert liegt drei Tage vor dem Lauf-Zeitstempel, den beide
#: Health-Test-Reihen benutzen (``NOW_ISO = 2026-07-27T21:45:00Z``) — deutlich
#: unter der 10-Tage-Grenze, also gesund. Wer eine ANDERE Lage braucht
#: (überfällig, fehlend, unlesbar), setzt sie im Test selbst; genau das tun die
#: Regel-Tests in ``tests/test_wartungs_cron.py``.
WARTUNGS_STATE_FRISCH = "2026-07-24T06:30:00Z"


def schreibe_wartungs_state(root, last_run_utc: str = WARTUNGS_STATE_FRISCH):
    """Legt ``data/maintenance_state.json`` in einem Sandbox-Repo an."""
    import json
    ziel = Path(root) / "data" / "maintenance_state.json"
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(json.dumps(
        {"schema_version": 1, "last_run_utc": last_run_utc,
         "updated_utc": last_run_utc, "rules": {}}, indent=2) + "\n",
        encoding="utf-8")
    return ziel


@pytest.fixture(autouse=True)
def _neutrale_umgebung(monkeypatch):
    """Kein Test erbt die Umgebung seines Läufers.

    ANLASS (06.08.2026, gefunden beim Mess-Workflow-PR): Die CI auf `main` war
    bei **15 von 16** Läufen rot, PR-Läufe dagegen grün — wochenlang, ohne dass
    es jemandem auffiel, weil der grüne Haken am PR hängt und niemand die
    Push-Läufe ansieht.

    Ursache: ``health_check.is_main_run()`` liest ``GITHUB_REF``. Bei einem
    Push auf `main` steht dort ``refs/heads/main``, also feuerte der Herzschlag
    **mitten im Unit-Test** und ``test_healthy_run_yields_zero_findings`` fiel
    („gesunder Lauf ist absolut still"). Bei einem PR-Lauf steht
    ``refs/pull/N/merge``, lokal steht gar nichts — überall sonst grün.

    Ein Test, dessen Ergebnis davon abhängt, WO er läuft, ist kein Test. Diese
    Fixture räumt deshalb alle Variablen weg, die der Produktionscode liest.
    Ein Test, der eine davon BRAUCHT, setzt sie selbst (`monkeypatch.setenv`) —
    das gewinnt, weil die Fixture vorher läuft. Genau so arbeitet
    ``test_heartbeat.py`` schon immer; nur ``test_health_check.py`` tat es
    nicht, und dort schlug es zu.
    """
    for name in NEUTRALE_UMGEBUNG:
        monkeypatch.delenv(name, raising=False)
