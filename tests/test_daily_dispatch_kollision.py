"""Der Tageslauf darf sich nicht selbst in die Quere kommen (31.07.2026).

VORFALL Lauf 30626433741: zwei Dispatches 33 Sekunden auseinander. Die
concurrency-Gruppe hat korrekt serialisiert — der zweite Job wurde EINE
Sekunde nach dem Ende des ersten angelegt. Trotzdem scheiterte er, weil
`actions/checkout` ohne `ref` den beim Auslösen eingefrorenen `github.sha`
nimmt: der wartende Lauf rechnete auf dem ALTEN Stand und kollidierte beim
`git pull --rebase` mit dem Daten-Commit des Laufs davor.

Drei Festlegungen, die das verhindern bzw. ehrlich melden — hier gepinnt,
weil ein Workflow keine Unit-Tests hat und ein stilles Zurückdrehen sonst
erst beim nächsten Vorfall auffiele.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github/workflows"
DAILY = (WF / "daily.yml").read_text(encoding="utf-8")


def _ohne_kommentare(text: str) -> str:
    """Kommentarzeilen raus — sonst prüft der Test die Begründung statt der Sache.

    Genau daran ist der `continue-on-error`-Test in #62 einmal gescheitert.
    """
    return "\n".join(z for z in text.splitlines()
                     if not z.strip().startswith("#"))


# ---------------------------------------------------------------------------
# A · Der Lauf checkt den ZWEIG aus, nicht den eingefrorenen Dispatch-SHA
# ---------------------------------------------------------------------------
def test_checkout_nimmt_den_zweig_und_nicht_den_dispatch_sha():
    block = re.search(r"- name: Checkout\n(.*?)\n      - name:", DAILY, re.S).group(1)
    sauber = _ohne_kommentare(block)
    assert "uses: actions/checkout@v4" in sauber
    assert "ref: ${{ github.ref_name }}" in sauber, (
        "ohne `ref` nimmt actions/checkout den beim Auslösen eingefrorenen "
        "github.sha — genau der Defekt vom 31.07.2026")
    # Hart "main" wäre falsch: der Push-Verdrahtungstest wird von einem
    # Feature-Branch gestartet und muss auf SEINEM Branch bleiben.
    assert "ref: main" not in sauber


def test_die_warteschlange_bleibt_und_bricht_nie_ab():
    """Ein Cron-Lauf darf NIEMALS von einem Hand-Tap gecancelt werden."""
    block = re.search(r"^concurrency:\n(.*?)\n\n", DAILY, re.S | re.M).group(1)
    assert "cancel-in-progress: false" in block, (
        "cancel-in-progress: true würde einen laufenden Cron-Lauf abbrechen — "
        "der Tageslauf wäre dann vom Zufall des Antippens abhängig")
    gruppe = re.search(r"group:\s*(\S+)", block).group(1)
    # Die Gruppe muss konstant sein: eine Gruppe mit ${{ github.ref }} würde
    # Cron und Dispatch in VERSCHIEDENE Warteschlangen legen — sie liefen
    # wieder parallel.
    assert "${{" not in gruppe, f"Gruppe darf nicht variabel sein: {gruppe}"


def test_kein_anderer_workflow_teilt_die_warteschlange():
    """Wechselwirkung: Staleness-Wächter und Kurs-Abruf bleiben unabhängig."""
    gruppen = {}
    for pfad in sorted(WF.glob("*.yml")):
        text = pfad.read_text(encoding="utf-8")
        m = re.search(r"^concurrency:\n\s+group:\s*(.+)$", text, re.M)
        if m:
            gruppen[pfad.name] = m.group(1).strip()
    assert gruppen["daily.yml"] == "daily-elliott"
    # Jede Gruppe genau einmal — sonst warten Workflows unbeabsichtigt
    # aufeinander.
    assert len(set(gruppen.values())) == len(gruppen), gruppen
    assert gruppen["staleness_check.yml"] != gruppen["daily.yml"]
    assert gruppen["eval_prices.yml"] != gruppen["daily.yml"]


def test_der_recalculate_knopf_landet_in_derselben_warteschlange():
    """Erwartet und gewollt: der Knopf wartet, statt parallel zu laufen."""
    html = (ROOT / "docs/index.html").read_text(encoding="utf-8")
    m = re.search(r"const GH_WORKFLOW = '([^']+)'", html)
    assert m and m.group(1) == "daily.yml", (
        "der Recalculate-Knopf startet einen anderen Workflow als erwartet — "
        "dann greift die Warteschlange für ihn nicht")


# ---------------------------------------------------------------------------
# B · Die Wiederholungen sind echte Wiederholungen
# ---------------------------------------------------------------------------
def test_vor_jedem_push_versuch_wird_ein_haengender_rebase_aufgeloest():
    schleife = re.search(r"for i in 1 2 3; do\n(.*?)\n            done",
                         DAILY, re.S).group(1)
    sauber = _ohne_kommentare(schleife).strip().splitlines()
    assert sauber[0].strip().startswith("git rebase --abort"), (
        "der Abbruch muss die ERSTE Anweisung der Schleife sein — sonst "
        "scheitern Versuche 2 und 3 am hängenden Konflikt statt es erneut zu "
        "versuchen (beobachtet 31.07.2026)")
    # Und danach wird aufgeräumt, damit kein halber Zustand stehen bleibt.
    nach = DAILY[DAILY.index("            done"):]
    assert "git rebase --abort" in nach[:400]


def test_keine_konflikt_gewinner_regel():
    """Bewusst KEIN `-X ours`/`theirs`: mit der Warteschlange plus dem
    Zweig-Checkout entsteht der Fall gar nicht mehr, und eine stille
    Gewinner-Regel würde entscheiden, welcher Datenstand überlebt."""
    for verboten in ("-X ours", "-X theirs", "--strategy-option"):
        assert verboten not in DAILY, verboten


# ---------------------------------------------------------------------------
# C · Der Fehlschlag-Push sagt, WAS kaputt war
# ---------------------------------------------------------------------------
# Die Fallunterscheidung, ausgeschrieben statt aus dem Workflow abgeleitet.
# (pipeline, validate, commit) -> (Titel, Priorität, Tags)
FAELLE = [
    (("success", "success", "failure"),
     ("Elliott: Daten-Push-Konflikt", "default", "information_source")),
    (("failure", "", ""), ("Elliott-Lauf fehlgeschlagen", "high", "rotating_light")),
    (("success", "failure", ""), ("Elliott-Lauf fehlgeschlagen", "high", "rotating_light")),
    (("success", "success", "skipped"),
     ("Elliott-Lauf fehlgeschlagen", "high", "rotating_light")),
    (("", "", ""), ("Elliott-Lauf fehlgeschlagen", "high", "rotating_light")),
]


def _entscheide(pipeline: str, validate: str, commit: str):
    """Dieselbe Bedingung wie im Workflow — hier in Python nachgebaut.

    Der Test darunter prüft, dass die Bedingung im Workflow WÖRTLICH diese
    ist; damit ist der Nachbau kein zweites, driftendes Regelwerk.
    """
    if pipeline == "success" and validate == "success" and commit == "failure":
        return ("Elliott: Daten-Push-Konflikt", "default", "information_source")
    return ("Elliott-Lauf fehlgeschlagen", "high", "rotating_light")


@pytest.mark.parametrize("eingabe,erwartet", FAELLE)
def test_fehlschlag_push_waehlt_den_richtigen_text(eingabe, erwartet):
    assert _entscheide(*eingabe) == erwartet


def test_die_bedingung_im_workflow_ist_genau_diese():
    """Wert-Prüfung statt Anwesenheit: die Bedingung steht wörtlich fest."""
    # Zeilenfortsetzungen auflösen, dann Weißraum vereinheitlichen — geprüft
    # wird die Bedingung, nicht ihr Umbruch.
    einzeilig = " ".join(_ohne_kommentare(DAILY).replace("\\\n", " ").split())
    assert ('if [ "$PIPELINE" = "success" ] && [ "$VALIDATE" = "success" ] '
            '&& [ "$COMMIT" = "failure" ]; then') in einzeilig
    # Beide Zweige mit ihren Werten — ein stilles Hochstufen des Konflikt-
    # Falls auf `high` wäre sonst unsichtbar.
    for stueck in ('TITEL="Elliott: Daten-Push-Konflikt"', 'PRIO="default"',
                   'TAGS="information_source"',
                   'TITEL="Elliott-Lauf fehlgeschlagen"', 'PRIO="high"',
                   'TAGS="rotating_light"'):
        assert stueck in DAILY, stueck


def test_die_schritte_tragen_die_ids_die_der_push_liest():
    """Ohne id ist `steps.X.outcome` leer — der Konflikt-Fall wäre tot."""
    for schritt, kennung in (("Run pipeline", "pipeline"),
                             ("Validate report JSON", "validate"),
                             ("Commit report + collection if changed", "commit")):
        block = re.search(rf"- name: {re.escape(schritt)}\n(.*?)\n      - name:",
                          DAILY, re.S)
        assert block, schritt
        assert f"id: {kennung}" in block.group(1), f"{schritt} ohne id: {kennung}"
    for kennung in ("pipeline", "validate", "commit"):
        assert f"steps.{kennung}.outcome" in DAILY


def test_der_konflikt_fall_bleibt_leise():
    """Kein Sirenen-Tag und keine hohe Priorität für einen reinen Push-Konflikt."""
    block = re.search(r"- name: Push bei Lauf-Fehlschlag\n(.*)", DAILY, re.S).group(1)
    konflikt = block[block.index('TITEL="Elliott: Daten-Push-Konflikt"'):
                     block.index("else")]
    assert "rotating_light" not in konflikt and "high" not in konflikt


def test_cron_zeit_unangetastet():
    assert 'cron: "45 21 * * 1-5"' in DAILY


def test_der_curl_aufruf_nutzt_die_variablen_und_keine_literale():
    """Guardian-Nit 31.07.: die Fallunterscheidung kann richtig sein und
    trotzdem wirkungslos, wenn der `curl`-Aufruf darunter feste Werte sendet.

    Genau diese Mutation blieb über alle 15 Tests grün — geprüft wurde nur der
    if/else-Block, nie die Zeile, die den Alarm wirklich absetzt.
    """
    block = re.search(r"- name: Push bei Lauf-Fehlschlag\n(.*)", DAILY, re.S).group(1)
    aufruf = block[block.index("curl -s -m 10"):]
    aufruf = aufruf[:aufruf.index("https://ntfy.sh/")]
    for stueck in ('-H "Title: ${TITEL}"', '-H "Priority: ${PRIO}"',
                   '-H "Tags: ${TAGS}"', '-d "${TEXT}"'):
        assert stueck in aufruf, f"curl sendet nicht {stueck}"
    # Und ausdrücklich KEIN festverdrahteter Wert mehr im Aufruf selbst.
    for literal in ("Elliott-Lauf fehlgeschlagen", "rotating_light", "high",
                    "information_source", "default"):
        assert literal not in aufruf, (
            f"{literal!r} steht fest im curl-Aufruf — die Fallunterscheidung "
            f"darüber wäre wirkungslos")


# ---------------------------------------------------------------------------
# DIE MECHANIK SELBST — an echtem git nachgestellt, nicht behauptet
# ---------------------------------------------------------------------------
# Der Workflow verlässt sich auf zwei Eigenschaften von git. Sie hier
# auszuführen macht die Begründung des PRs dauerhaft nachprüfbar, statt sie
# nur in Prosa zu behaupten (Guardian-Nit 31.07.).
import subprocess  # noqa: E402


def _git(*args, cwd, pruefen=True):
    r = subprocess.run(("git",) + args, cwd=cwd, capture_output=True, text=True)
    if pruefen:
        assert r.returncode == 0, f"{args}: {r.stderr}"
    return r


def _welt(tmp_path):
    """Fern-Repo + ein Lauf, der seinen Daten-Commit schon gepusht hat."""
    fern = tmp_path / "fern.git"
    _git("init", "-q", "--bare", str(fern), cwd=tmp_path)
    seed = tmp_path / "seed"
    _git("init", "-q", str(seed), cwd=tmp_path)
    for k, v in (("user.email", "s@x"), ("user.name", "S")):
        _git("config", k, v, cwd=seed)
    _git("checkout", "-q", "-b", "main", cwd=seed)
    (seed / "report.json").write_text('{"stand":"basis"}\n')
    _git("add", "report.json", cwd=seed)
    _git("commit", "-qm", "basis", cwd=seed)
    _git("remote", "add", "origin", str(fern), cwd=seed)
    _git("push", "-q", "origin", "main", cwd=seed)
    _git("symbolic-ref", "HEAD", "refs/heads/main", cwd=fern)
    basis = _git("rev-parse", "HEAD", cwd=seed).stdout.strip()

    lauf1 = tmp_path / "lauf1"
    _git("clone", "-q", str(fern), str(lauf1), cwd=tmp_path)
    for k, v in (("user.email", "1@x"), ("user.name", "L1")):
        _git("config", k, v, cwd=lauf1)
    (lauf1 / "report.json").write_text('{"stand":"lauf1"}\n')
    _git("commit", "-qam", "chore(data) lauf 1", cwd=lauf1)
    _git("push", "-q", "origin", "main", cwd=lauf1)
    neu = _git("rev-parse", "HEAD", cwd=lauf1).stdout.strip()
    return fern, basis, neu


def _lauf2(tmp_path, fern, ziel, name):
    """Ein zweiter Lauf, der `ziel` auscheckt und seinen Daten-Commit pusht."""
    wd = tmp_path / name
    _git("clone", "-q", str(fern), str(wd), cwd=tmp_path)
    for k, v in (("user.email", "2@x"), ("user.name", "L2")):
        _git("config", k, v, cwd=wd)
    _git("checkout", "-q", ziel, cwd=wd)
    kopf = _git("rev-parse", "HEAD", cwd=wd).stdout.strip()
    (wd / "report.json").write_text('{"stand":"lauf2"}\n')
    _git("add", "report.json", cwd=wd)
    _git("commit", "-qm", "chore(data) lauf 2", cwd=wd)
    _git("rebase", "--abort", cwd=wd, pruefen=False)
    zog = _git("pull", "--rebase", "origin", "main", cwd=wd, pruefen=False)
    ok = zog.returncode == 0 and _git(
        "push", "origin", "HEAD:main", cwd=wd, pruefen=False).returncode == 0
    _git("rebase", "--abort", cwd=wd, pruefen=False)
    return kopf, ok


def test_zweig_checkout_vermeidet_den_konflikt_den_der_sha_checkout_ausloest(tmp_path):
    """Der Kern von A, an echtem git: ALTER Stand kollidiert, AKTUELLER nicht.

    Genau der Vorfall vom 31.07. (Lauf 30626433741) — und seine Behebung.
    """
    fern, basis, neu = _welt(tmp_path)

    kopf_sha, ok_sha = _lauf2(tmp_path, fern, basis, "wie_bisher")
    assert kopf_sha == basis, "Vorbedingung: der SHA-Checkout nimmt den ALTEN Stand"
    assert not ok_sha, "der alte Weg müsste am Rebase-Konflikt scheitern"

    # Stand zurücksetzen und denselben Fall mit Zweig-Checkout fahren.
    _git("update-ref", "refs/heads/main", neu, cwd=fern)
    kopf_zweig, ok_zweig = _lauf2(tmp_path, fern, "main", "mit_ref")
    assert kopf_zweig == neu, "der Zweig-Checkout muss den AKTUELLEN Stand nehmen"
    assert ok_zweig, "mit dem aktuellen Stand darf kein Konflikt entstehen"


def test_rebase_abort_macht_den_naechsten_versuch_wieder_moeglich(tmp_path):
    """Der Kern von B: ohne `abort` ist der zweite Versuch keiner."""
    fern, basis, _neu = _welt(tmp_path)
    wd = tmp_path / "lauf2"
    _git("clone", "-q", str(fern), str(wd), cwd=tmp_path)
    for k, v in (("user.email", "2@x"), ("user.name", "L2")):
        _git("config", k, v, cwd=wd)
    _git("checkout", "-q", basis, cwd=wd)
    (wd / "report.json").write_text('{"stand":"lauf2"}\n')
    _git("add", "report.json", cwd=wd)
    _git("commit", "-qm", "chore(data) lauf 2", cwd=wd)
    eigener = _git("rev-parse", "HEAD", cwd=wd).stdout.strip()

    erst = _git("pull", "--rebase", "origin", "main", cwd=wd, pruefen=False)
    assert erst.returncode != 0
    assert (wd / ".git/rebase-merge").exists() or (wd / ".git/rebase-apply").exists()

    # OHNE abort: der zweite Versuch scheitert am hängenden Zustand, nicht am Inhalt.
    zweit = _git("pull", "--rebase", "origin", "main", cwd=wd, pruefen=False)
    assert "unmerged files" in (zweit.stderr + zweit.stdout)

    _git("rebase", "--abort", cwd=wd)
    assert not (wd / ".git/rebase-merge").exists()
    assert not (wd / ".git/rebase-apply").exists()
    assert _git("status", "--porcelain", cwd=wd).stdout.strip() == ""
    assert _git("rev-parse", "HEAD", cwd=wd).stdout.strip() == eigener, \
        "der eigene Daten-Commit muss den Abbruch überleben"

    # MIT abort davor: der Versuch läuft wieder echt (und meldet den ECHTEN Grund).
    dritt = _git("pull", "--rebase", "origin", "main", cwd=wd, pruefen=False)
    text = dritt.stdout + dritt.stderr
    assert "unmerged files" not in text
    assert "CONFLICT" in text, "der Versuch muss den Inhalt erreichen, nicht am Zustand hängen"
    _git("rebase", "--abort", cwd=wd, pruefen=False)
