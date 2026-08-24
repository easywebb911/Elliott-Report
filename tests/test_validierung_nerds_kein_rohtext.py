"""Rohtext-Registry raus aus "Details für Nerds" (24.08.2026, Easy-Wunsch:
"Wirr Warr" raus).

KONTEXT: #107 hat "Details für Nerds" um eine klare Erklärung der sechs
Status-Kategorien + den "Zwei Rechnungen, nicht eine"-Absatz ergänzt — dieser
Text bleibt UNVERÄNDERT. Direkt darunter rendete die App aber weiterhin den
kompletten, rohen Inhalt von `docs/validation_registry.md`
("Validierungs-Register — Score-Validierung (Forward-Sammlung)…") ungefiltert
im Frontend (`openValidierung()`: `fetch('validation_registry.md')` +
`_renderMarkdown(md)` in `mdHtml`, angehängt ans Ende des `nerds`-Templates).

WICHTIG (GRENZEN): `docs/validation_registry.md` selbst bleibt als Datei im
Repo VOLLSTÄNDIG UND UNGEKÜRZT bestehen — nur die Frontend-Darstellung
ändert sich. Dieser Test prüft NICHT den Dateiinhalt (unverändert, s.
`git diff` auf die `.md`-Datei selbst — leer), sondern ausschließlich, WAS
das Frontend daraus rendert.

Isolierbarkeit geprüft (Auftrag Punkt "STOPP falls nicht sauber isolierbar"):
`mdHtml`/die fetch-Schleife/`_renderMarkdown()` wurden AUSSCHLIESSLICH für
diesen einen Rohtext-Block verwendet (`grep -rn "mdHtml\\|_renderMarkdown"
docs/index.html` vor der Änderung: nur die Definition + der eine Einsatzort)
— sauber isolierbar, kein Mischinhalt, kein Stopp nötig. `_renderMarkdown()`
wurde deshalb komplett entfernt (sonst toter Code), NICHT nur der Aufruf.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "docs/index.html").read_text(encoding="utf-8")
REGISTRY_MD = (ROOT / "docs/validation_registry.md").read_text(encoding="utf-8")


def _fn(name: str, tiefe: str = "    ") -> str:
    for prefix in ("function", "async function"):
        marke = f"{tiefe}{prefix} {name}("
        if marke in HTML:
            start = HTML.index(marke)
            return HTML[start:HTML.index(f"\n{tiefe}}}", start) + len(f"\n{tiefe}}}")]
    raise AssertionError(f"Funktion {name!r} nicht gefunden")


# ---------------------------------------------------------------------------
# GRENZEN: die Datei selbst ist tabu
# ---------------------------------------------------------------------------
def test_validation_registry_md_selbst_unangetastet():
    """Reine Frontend-Änderung — die Registry-Datei bleibt vollständig und
    ungekürzt im Repo. (Git-Diff-Beleg steht im PR-Text; hier nur eine
    Plausibilitäts-Gegenprobe, dass die Datei weiterhin ihren bekannten,
    langen Inhalt hat statt leer/gekürzt zu sein.)"""
    assert "Validierungs-Register" in REGISTRY_MD
    assert len(REGISTRY_MD) > 5000, "Registry-Datei wirkt gekürzt"


# ---------------------------------------------------------------------------
# Rohtext-Block raus aus dem Frontend
# ---------------------------------------------------------------------------
def test_kein_fetch_der_registry_datei_mehr_im_frontend():
    """"validation_registry.md" taucht in `openValidierung()` weiterhin auf
    — jetzt aber NUR noch als Link-Text/href auf die Repo-Datei (s.
    `test_verweis_auf_die_datei_ist_vorhanden_und_verlinkt`), nicht mehr als
    fetch-Ziel. Gegenprobe hier: der fetch-Aufruf/die Fallback-Pfad-Schleife
    sind komplett weg."""
    assert "fetch(p + bust" not in HTML
    assert "for (const p of ['validation_registry.md'" not in HTML
    assert "'../docs/validation_registry.md'" not in HTML


def test_renderMarkdown_komplett_entfernt_kein_toter_code():
    assert "_renderMarkdown" not in HTML
    assert "function _renderMarkdown(" not in HTML


def test_mdHtml_variable_verschwunden():
    assert "mdHtml" not in HTML


def test_kein_registry_ueberschrift_text_mehr_im_gerenderten_nerds_block():
    """Der Rohtext begann im Original mit dieser Überschrift — sie darf im
    `nerds`-Template nicht mehr auftauchen (Beleg, dass wirklich nichts vom
    Rohtext übrig blieb, nicht nur der fetch-Aufruf entfernt wurde)."""
    nerds_block = HTML[HTML.index("const nerds ="):HTML.index("const nerds =") + 4000]
    assert "Validierungs-Register — Score-Validierung" not in nerds_block
    assert "BLIND GEBAUT" not in nerds_block


# ---------------------------------------------------------------------------
# Verweis auf die Repo-Datei stattdessen
# ---------------------------------------------------------------------------
def test_verweis_auf_die_datei_ist_vorhanden_und_verlinkt():
    nerds_block = _fn("openValidierung")
    assert ("Das vollständige, ungekürzte Validierungsprotokoll mit allen datierten"
            in nerds_block)
    assert "docs/validation_registry.md" in nerds_block
    # Klickbarer Link, dasselbe sichere Attribut-Muster wie der bestehende
    # externe "Chart"-Link (target=_blank + rel=noopener noreferrer) —
    # wiederverwendet, nicht neu erfunden.
    assert 'target="_blank" rel="noopener noreferrer"' in nerds_block
    assert "https://github.com/${GH_OWNER}/${GH_REPO}/blob/${GH_BRANCH}/docs/validation_registry.md" in nerds_block


def test_link_nutzt_die_bestehenden_gh_konstanten_nicht_hardcodiert():
    """Dieselbe Repo-Identität wie die bestehende GitHub-API-Anbindung
    (Trade-Journal-Persistenz) — kein zweites, unabhängiges Literal."""
    assert "const GH_OWNER = 'easywebb911';" in HTML
    assert "const GH_REPO = 'Elliott-Report';" in HTML
    assert "const GH_BRANCH = 'main';" in HTML
    # Der Link-Code selbst referenziert die Konstanten, nicht die Strings direkt.
    nerds_block = _fn("openValidierung")
    assert "'easywebb911'" not in nerds_block
    assert "'Elliott-Report'" not in nerds_block


def test_status_erklaerung_aus_107_bleibt_wortgleich_bestehen():
    """GRENZEN: keine erneute Kürzung/inhaltliche Änderung der #107-Texte."""
    nerds_block = _fn("openValidierung")
    for satz in (
        "<li><b>offen</b> — die 10 Handelstage laufen noch, es gibt noch kein Ergebnis.</li>",
        "<li><b>Extension</b> — sogar die weiter entfernte Extension-Zone wurde erreicht.</li>",
        "<li><b>Zone</b> — die Beobachtungszone wurde erreicht, bevor die Zählung ungültig wurde.</li>",
        "<li><b>invalidiert</b> — die Zählung wurde ungültig, bevor eine Zone erreicht wurde.</li>",
        "<li><b>gereift · neutral</b> — die 10 Tage sind um, aber weder eine Zone noch die Invalidierung wurde erreicht.</li>",
    ):
        assert satz in nerds_block
    assert "<strong>Zwei Rechnungen, nicht eine:</strong>" in nerds_block
    assert "Haupt-Rechnung zählt erst ab" in nerds_block


def test_status_verteilung_und_kennzahlen_unangetastet():
    """GRENZEN: keine Änderung an den #107-Statuskategorien-Erklärungen oder
    der Prozent-Verteilung — nur eine strukturelle Gegenprobe hier, die
    eigentlichen Wert-Tests dafür leben in test_status_verteilung.py."""
    koerper = _fn("openValidierung")
    assert "statusDistributionHtml" in koerper
    assert "<b>${collected}</b><span>gesammelt</span>" in koerper
    assert "<b>${matured}</b><span>fertig beobachtet</span>" in koerper
    assert "<b>${evaluable}</b><span>auswertbar</span>" in koerper
