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
