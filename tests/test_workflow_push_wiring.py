"""Push-Verdrahtung: jeder Workflow-Step, der pushen KANN, braucht das Topic.

FUND 27.07.2026 (Easy): Das Secret `NTFY_TOPIC` war gesetzt und funktionierte
nachweislich (Stufe-1-Pushes kamen am 23.07. real an) — aber der Step
**„Run pipeline"** in `daily.yml` reichte es nicht durch. GitHub Actions
vererbt Secrets **nicht** automatisch in Steps; nur was im `env:`-Block des
Steps steht, landet im Prozess.

Folge: `os.environ.get("NTFY_TOPIC", "")` war in der Pipeline **leer**, und
damit waren BEIDE Push-Zweige, die INNERHALB der Pipeline leben, still:
  • **Score-Alert >90** (#24, `notify.send_score_alert`) — seit dem Bau,
  • **Health-Check Stufe 2** (#51, `health_check.run`) — von Anfang an.
Beide sind fail-soft: leeres Topic → `send_ntfy` loggt „kein NTFY_TOPIC" und
gibt `False` zurück. Also **kein Fehler, keine rote CI, kein Hinweis** — genau
die Sorte Defekt, gegen die der Health-Check gebaut wurde, eine Ebene tiefer.

Der Variablenname war nie das Problem (überall identisch `NTFY_TOPIC`) — es
fehlte allein das Mapping. Deshalb prüft dieser Test nicht Namen gegen Namen,
sondern die **Verdrahtung**: liest ein Skript das Topic, muss der Step, der
dieses Skript startet, es auch setzen.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github/workflows"
SCRIPTS = ROOT / "scripts"

TOPIC_VAR = "NTFY_TOPIC"


def _scripts_reading_topic() -> set[str]:
    """Alle scripts/*.py, die das Topic aus der Umgebung lesen — direkt oder
    über einen Import (die Pipeline pusht über `notify`/`health_check`)."""
    direct = {p.name for p in SCRIPTS.glob("*.py")
              if TOPIC_VAR in p.read_text(encoding="utf-8")}
    return direct


def _steps(workflow_text: str):
    """(name, block) je Step — grobe, aber ausreichende YAML-Segmentierung
    entlang der `- name:`-Marken (kein PyYAML nötig, keine neue Dependency)."""
    parts = re.split(r"\n      - name: ", "\n" + workflow_text)
    for part in parts[1:]:
        yield part.split("\n", 1)[0].strip(), part


def test_pipeline_step_maps_the_topic():
    """Der Kern des Funds: der Step, der die Pipeline startet, MUSS das Topic
    durchreichen — dort leben Score-Alert und Health-Check-Push."""
    text = (WORKFLOWS / "daily.yml").read_text(encoding="utf-8")
    for name, block in _steps(text):
        if "python scripts/elliott_pipeline.py" in block:
            assert f"{TOPIC_VAR}: ${{{{ secrets.{TOPIC_VAR} }}}}" in block, (
                f"Step '{name}' startet die Pipeline, reicht aber {TOPIC_VAR} "
                f"nicht durch — Score-Alert und Health-Check-Push sind dann "
                f"STILL, ohne jede Fehlermeldung (fail-soft).")
            return
    raise AssertionError("Kein Step gefunden, der elliott_pipeline.py startet")


def test_every_step_running_a_pushing_script_maps_the_topic():
    """Verallgemeinert: startet ein Step ein Skript, das das Topic liest, muss
    er es auch setzen. Fängt denselben Fehler bei künftigen Skripten ab."""
    pushing = _scripts_reading_topic()
    # Nur DIESE beiden lesen die Umgebung selbst. `health_check.py` bekommt das
    # Topic als Parameter von der Pipeline gereicht (deshalb steht der Name dort
    # nicht im Quelltext) — es ist genau deswegen auf das Mapping am
    # Pipeline-Step angewiesen und kann sich nicht selbst helfen.
    assert {"notify.py", "elliott_pipeline.py"} <= pushing, (
        f"Erwartete Push-Skripte fehlen in {sorted(pushing)}")
    assert TOPIC_VAR not in (SCRIPTS / "health_check.py").read_text(
        encoding="utf-8"), (
        "health_check.py soll das Topic NICHT selbst aus der Umgebung lesen — "
        "es kommt als Parameter aus der Pipeline (eine Quelle, ein Mapping)")
    missing = []
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        text = wf.read_text(encoding="utf-8")
        for name, block in _steps(text):
            run = block.split("run:", 1)[1] if "run:" in block else ""
            started = {s for s in pushing if f"scripts/{s}" in run}
            if started and TOPIC_VAR not in block:
                missing.append(f"{wf.name} :: {name} (startet {sorted(started)})")
    assert not missing, (
        "Steps starten ein pushendes Skript OHNE " + TOPIC_VAR + ":\n  "
        + "\n  ".join(missing))


def test_topic_is_never_hardcoded():
    """Das Topic ist ein Secret — es darf nirgends im Klartext stehen."""
    for path in list(WORKFLOWS.glob("*.yml")) + list(SCRIPTS.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(rf"{TOPIC_VAR}\s*[:=]\s*(\S+)", text):
            val = m.group(1)
            ok = (val.startswith("${{") or val.startswith("os.environ")
                  or val in ('""', "''", '"",'))
            assert ok, f"{path.name}: {TOPIC_VAR} sieht hardcodiert aus: {val}"


def test_all_known_push_steps_still_wired():
    """Die drei Stellen, die das Mapping schon immer hatten, bleiben verdrahtet
    (kein Rückschritt beim Aufräumen)."""
    daily = (WORKFLOWS / "daily.yml").read_text(encoding="utf-8")
    stale = (WORKFLOWS / "staleness_check.yml").read_text(encoding="utf-8")
    assert daily.count(f"{TOPIC_VAR}: ${{{{ secrets.{TOPIC_VAR} }}}}") == 4, (
        "daily.yml braucht das Mapping an VIER Steps: Run pipeline, "
        "Self-monitor push, Push-Verdrahtung testen, Push bei Lauf-Fehlschlag")
    assert f"{TOPIC_VAR}: ${{{{ secrets.{TOPIC_VAR} }}}}" in stale


def test_selftest_mode_sends_exactly_one_push(monkeypatch):
    """Der Bestätigungs-Push: genau EINER, harmlos, low priority."""
    import datetime as _dt

    import notify

    sent = []
    monkeypatch.setattr(
        notify, "_post",
        lambda url, data, headers, timeout: sent.append(
            {"url": url, "title": headers.get("Title"),
             "prio": headers.get("Priority"), "body": data.decode("utf-8")}))
    now = _dt.datetime(2026, 7, 27, 21, 45, tzinfo=_dt.timezone.utc)
    assert notify.run_selftest("easy-elliott-report", now) is True
    assert len(sent) == 1
    assert sent[0]["url"].endswith("/easy-elliott-report")
    assert sent[0]["prio"] == "low"          # Bestätigung, kein Alarm
    assert "Verdrahtung ok" in sent[0]["title"]
    # Ohne Topic bleibt auch der Selbsttest still (kein Crash, kein Push).
    sent.clear()
    assert notify.run_selftest("", now) is False and sent == []


def test_selftest_is_opt_in_only():
    """Der Schritt darf NUR auf ausdrücklichen Dispatch-Schalter laufen —
    niemals im nächtlichen Cron."""
    text = (WORKFLOWS / "daily.yml").read_text(encoding="utf-8")
    for name, block in _steps(text):
        if "--mode selftest" in block:
            assert "if:" in block and "push_selftest" in block, (
                f"Step '{name}' ist nicht auf den Dispatch-Schalter begrenzt")
            assert "workflow_dispatch" in block
            return
    raise AssertionError("Kein Selbsttest-Step gefunden")
