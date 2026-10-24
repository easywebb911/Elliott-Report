#!/usr/bin/env python3
"""Auswertungsskript für den 07.12.2026 (Easy-Entscheid, PR 4 von 4 der
Diagnose-Folgeaufträge; Score-Review-Wiedervorlage, s. SESSION_HANDOVER.md).

HARTE GRENZEN (wie `evaluate_cluster_sensitivity.py`, Zeile für Zeile
übernommen)
  - läuft **nie** im Tageslauf (kein Aufruf in `.github/workflows/`, kein
    Import aus `elliott_pipeline`/`notify`/`health_check` — per Test
    abgesichert),
  - sendet **keinen** Push, braucht **keinen** Netzzugriff,
  - schreibt **nie** in `data/` oder `docs/` (per Test abgesichert, auch
    nicht versehentlich über `--out`) — Ausgabe NUR auf die Konsole,
    optional zusätzlich in eine vom Aufrufer per `--out` benannte Datei
    AUSSERHALB von `data/`/`docs/`,
  - läuft **nur auf Anfrage**, nie automatisch,
  - ändert NICHTS an `scripts/evaluate.py` (SHA256-Pin), Score, Ranking,
    Filter, Zählregel, Schatten-Berechnung oder der Sammlung.

WAS DIESES SKRIPT TUT
  Acht benannte Kohorten (vier Stichtags-Varianten × mit/ohne die
  `invertiertes_risiko_bei_anlage`-Markierung) — je Kohorte: Fallzahlen,
  Trefferquote, AUC des Live-Scores mit Block-Bootstrap-Intervall
  (Tag-Block UND Ticker-Block, Muster/Konstanten aus
  `evaluate_cluster_sensitivity.py`, #166/#167/#180 — importiert, nicht
  kopiert). Für die Schatten-Kohorten zusätzlich: AUC Schatten-Score,
  gepaarte Differenz (Schatten − Live) mit Block-Bootstrap-Intervall
  (dieselben Bootstrap-Ziehungen für beide Scores — s. `_resample_paar`),
  und das vorab festgelegte Verdikt (docs/validation_registry.md, Eintrag
  zu PR #194, Abschnitt „VORAB-FESTLEGUNG der Auswertung").

  Die Trefferquote wird hier **nicht** gegen den Zufalls-Benchmark getestet
  (keine neue Holm-/Permutations-Rechnung) — das ist nicht Teil dieses
  Auftrags, s. Moduldoc von `evaluate_cluster_sensitivity.py` für dieselbe
  Entscheidung dort.

KOHORTEN (Quellenverweise)
  - ALLE: alle auswertbaren Fälle der Primärpopulation
    (`evaluate.build_population`, unverändert).
  - AB_ZAEHLREGEL_STICHTAG (#186, docs/validation_registry.md "NACHTRAG
    17.10.2026"): `created_utc >= ZAEHLREGEL_STICHTAG_UTC`.
  - AB_FILTER_STICHTAG (#190, docs/validation_registry.md "NACHTRAG
    20.10.2026"): `created_utc >= FILTER_STICHTAG_UTC`.
  - AB_SCHATTEN (#194, docs/validation_registry.md "VORAB-FESTLEGUNG"):
    `score_shadow_inval_cap20 is not None` — **kein** Zeitstempel-Schnitt,
    die Kohorte ist über das Feld selbst definiert (Feld existiert nur auf
    Records, die NACH dem #194-Merge angelegt wurden — der Stichtag-
    Zeitstempel selbst ist noch nicht belegt, s. `SCHATTEN_STICHTAG_UTC`).
  Jede der vier zusätzlich OHNE markierte Fälle
  (`invertiertes_risiko_bei_anlage is not True`) — eigener, einfacher
  Filter (der Marker steht NICHT in `filter_sensitivity_sammlung.MARKERS`,
  bewusst, docs/validation_registry.md Eintrag zu PR #189 — dieses Skript
  rührt diese Datei nicht an).

GRENZE AM STICHTAG (belegt, nicht angenommen): `created_utc >=
run_timestamp_utc` des Stichtag-Laufs — der Stichtag-Lauf selbst gehört
zur Kohorte. Belegt auf echten Daten für #186 (Lauf #153, Commit
`70b4412`) und #190 (Lauf #156, Commit `2a0f1a8`): in beiden Läufen ist
`created_utc` der NEU angelegten Records exakt gleich dem
`run_timestamp_utc` dieses Laufs (nie davor, nie danach) — `>=` schließt
den Stichtag-Lauf also korrekt ein, `>` hätte ihn fälschlich ausgeschlossen.

MODUS-SCHUTZ (zwei Modi, s. `main`)
  --zaehlung   : NUR Fallzahlen (n gesamt, n reif, Schatten gesetzt) je
                 Kohorte. KEINE Trefferquote, KEINE AUC, KEIN Verdikt.
  --auswerten  : volle Rechnung. Verweigert, wenn das heutige Datum
                 (Europe/Berlin, `--jetzt` injizierbar) vor 2026-12-07
                 liegt — AUSSER mit zusätzlichem --vorzeitig, dann trägt
                 JEDE Ausgabezeile den Zusatz "EXPLORATIV, nicht
                 präregistriert".

FESTE PARAMETER: importiert aus `evaluate_cluster_sensitivity`
  (`BOOTSTRAP_DRAWS=10_000`, `CI_NIVEAU=0.975`,
  `SEEDS=(20260728, 1, 42, 7, 999)`) — keine eigene neue Wahl.

VERWENDUNG (nur manuell):
  python scripts/auswertung_stichtage.py --zaehlung
  python scripts/auswertung_stichtage.py --auswerten [--vorzeitig]
      [--sammlung data/forward_collection.json] [--out DATEI] [--jetzt ISO]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import random
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

import repo_path  # noqa: F401 — legt Repo-Root + scripts/ auf sys.path

REPO_ROOT = repo_path.REPO_ROOT

import evaluate as ev  # noqa: E402 — NUR LESEND genutzt, s. Moduldoc oben
import evaluate_cluster_sensitivity as ecs  # noqa: E402 — Bootstrap-Maschinerie, importiert
import forward_collection as fc  # noqa: E402

BERLIN = ZoneInfo("Europe/Berlin")

# ---------------------------------------------------------------------------
# Feste Parameter (importiert, keine eigene neue Wahl — s. Moduldoc).
# ---------------------------------------------------------------------------
BOOTSTRAP_DRAWS = ecs.BOOTSTRAP_DRAWS
CI_NIVEAU = ecs.CI_NIVEAU
SEEDS = ecs.SEEDS
SECONDARY_MIN_N = ev.SECONDARY_MIN_N  # "zu wenige Fälle"-Schwelle, importiert

# Datum, ab dem --auswerten ohne --vorzeitig zulässig ist (Score-Review-
# Wiedervorlage, SESSION_HANDOVER.md).
AUSWERTUNG_FREIGABE_DATUM = _dt.date(2026, 12, 7)

# Stichtage — belegt aus docs/validation_registry.md (s. Moduldoc).
ZAEHLREGEL_STICHTAG_UTC = "2026-10-15T00:51:53Z"   # #186, Lauf #153
FILTER_STICHTAG_UTC = "2026-10-20T01:16:14Z"       # #190, Lauf #156
# #194: NOCH NICHT BELEGT — wird mit dem Stichtag-Nachtrag gesetzt (wie bei
# #186/#190, s. docs/validation_registry.md "VORAB-FESTLEGUNG"). Die
# Schatten-Kohorte selbst braucht diesen Zeitstempel NICHT (s. Moduldoc) —
# er stünde hier nur zur Vollständigkeit/späteren Doku-Verwendung.
SCHATTEN_STICHTAG_UTC: Optional[str] = None

# Verbotene Ausgabe-Ziele: JEDER Pfad unter data/ oder docs/ (breiter als
# die Einzel-Datei-Liste in evaluate_cluster_sensitivity.py — hier
# ausdrücklich verlangt).
_VERBOTENE_VERZEICHNISSE = ("data", "docs")

EXPLORATIV_ZUSATZ = "EXPLORATIV, nicht präregistriert"


# ---------------------------------------------------------------------------
# Kohorten — reine Filterfunktionen auf rohen Records.
# ---------------------------------------------------------------------------
def _ist_markiert(rec: Dict) -> bool:
    return rec.get("invertiertes_risiko_bei_anlage") is True


def _kohorte_alle(rec: Dict) -> bool:
    return True


def _kohorte_ab(stichtag: Optional[str]):
    def _pred(rec: Dict) -> bool:
        if stichtag is None:
            return False
        c = rec.get("created_utc")
        return bool(c) and c >= stichtag
    return _pred


def _kohorte_schatten(rec: Dict) -> bool:
    return rec.get("score_shadow_inval_cap20") is not None


# (name, prädikat, stichtag_text) — stichtag_text nur für den Bericht.
def _basis_kohorten() -> List[Tuple[str, "object", str]]:
    return [
        ("ALLE", _kohorte_alle, "kein Stichtag"),
        ("ab Zählregel-Stichtag (#186)", _kohorte_ab(ZAEHLREGEL_STICHTAG_UTC),
         ZAEHLREGEL_STICHTAG_UTC),
        ("ab Filter-Stichtag (#190)", _kohorte_ab(FILTER_STICHTAG_UTC),
         FILTER_STICHTAG_UTC),
        ("ab Schatten (#194, über score_shadow_inval_cap20 gesetzt)",
         _kohorte_schatten,
         SCHATTEN_STICHTAG_UTC or "noch nicht belegt"),
    ]


def alle_kohorten() -> List[Tuple[str, "object", bool]]:
    """Acht Kohorten: die vier Basis-Kohorten, je mit/ohne markierte Fälle.
    ``(name, praedikat, ist_schatten_kohorte)``."""
    out: List[Tuple[str, "object", bool]] = []
    for name, pred, _stichtag in _basis_kohorten():
        ist_schatten = name.startswith("ab Schatten")
        out.append((name, pred, ist_schatten))
        pred_ohne = (lambda rec, p=pred: p(rec) and not _ist_markiert(rec))
        out.append((f"{name}, ohne markierte Fälle", pred_ohne, ist_schatten))
    return out


# ---------------------------------------------------------------------------
# Fallzahlen (für --zaehlung UND als Basis von --auswerten).
# ---------------------------------------------------------------------------
def fallzahlen(records: Sequence[Dict], cases: Sequence[Dict],
              praedikat) -> Dict:
    """``n_gesamt`` zählt JEDEN Record (reif oder nicht), der das Prädikat
    erfüllt — ``n_reif`` nur die Teilmenge, die in ``cases`` (bereits
    gereift UND nicht PRU-ausgeschlossen, s. ``evaluate.build_population``)
    steht. Unreife Records zählen NIE in ``n_reif``."""
    n_gesamt = sum(1 for r in records if praedikat(r))
    passende_cases = [c for c in cases if praedikat(c["rec"])]
    n_reif = len(passende_cases)
    n_treffer = sum(1 for c in passende_cases if c["hit"] == 1)
    n_schatten_gesetzt = sum(1 for r in records
                            if praedikat(r) and
                            r.get("score_shadow_inval_cap20") is not None)
    return {
        "n_gesamt": n_gesamt, "n_reif": n_reif, "n_treffer": n_treffer,
        "n_schatten_gesetzt": n_schatten_gesetzt,
        "cases": passende_cases,
    }


# ---------------------------------------------------------------------------
# Block-Bootstrap — AUC einer Kohorte (unpaired, Live ODER Schatten allein).
# Wiederverwendet `ecs.bootstrap_ci` direkt (importiert, nicht kopiert).
# ---------------------------------------------------------------------------
def auc_mit_block_bootstrap(cases: Sequence[Dict], score_feld: str,
                            seed: int) -> Dict:
    """Wie ``ecs.bootstrap_ci``, aber mit wählbarem Score-Feld (``score`` für
    Live, oder einem anderen Schlüssel, den der Aufrufer vorher auf jedem
    Case gesetzt hat — s. ``_mit_schatten_score``)."""
    umbenannt = [{"score": c[score_feld], "hit": c["hit"],
                 "first_seen_date": c["first_seen_date"], "ticker": c["ticker"]}
                for c in cases]
    tag = ecs.bootstrap_ci(umbenannt, "first_seen_date", seed)
    ticker = ecs.bootstrap_ci(umbenannt, "ticker", seed)
    primaer = ecs.bootstrap_ci(umbenannt, None, seed)
    return {"primär": primaer, "Tag-Block": tag, "Ticker-Block": ticker}


def _mit_schatten_score(cases: Sequence[Dict]) -> List[Dict]:
    """Nur Fälle, bei denen ``score_shadow_inval_cap20`` gesetzt ist, mit
    einem zusätzlichen ``score_schatten``-Feld."""
    out = []
    for c in cases:
        s = c["rec"].get("score_shadow_inval_cap20")
        if s is not None:
            neu = dict(c)
            neu["score_schatten"] = float(s)
            out.append(neu)
    return out


# ---------------------------------------------------------------------------
# GEPAARTER Block-Bootstrap der Differenz (Schatten − Live) — dieselben
# Ziehungen für beide Scores, Muster wie ``ecs.bootstrap_ci`` aber für ZWEI
# Score-Spalten gleichzeitig (daher hier, nicht dort — der Unterschied zur
# unpaired-Variante ist genau der Kern dieser Rechnung).
# ---------------------------------------------------------------------------
def differenz_mit_gepaartem_bootstrap(cases_mit_schatten: Sequence[Dict],
                                      block_feld: Optional[str],
                                      seed: int, *,
                                      bootstrap: int = BOOTSTRAP_DRAWS,
                                      ci_level: float = CI_NIVEAU) -> Dict:
    live = [c["score"] for c in cases_mit_schatten]
    schatten = [c["score_schatten"] for c in cases_mit_schatten]
    labels = [c["hit"] for c in cases_mit_schatten]
    auc_live_punkt = ev.auc(live, labels)
    auc_schatten_punkt = ev.auc(schatten, labels)
    punkt = (None if auc_live_punkt is None or auc_schatten_punkt is None
            else auc_schatten_punkt - auc_live_punkt)

    rng = random.Random(seed)
    diffs: List[float] = []

    if block_feld is None:
        n = len(cases_mit_schatten)
        cluster_anzahl = n
        for _ in range(bootstrap):
            idx = [rng.randrange(n) for _ in range(n)] if n else []
            l2 = [live[i] for i in idx]
            s2 = [schatten[i] for i in idx]
            y2 = [labels[i] for i in idx]
            a_l = ev.auc(l2, y2)
            a_s = ev.auc(s2, y2)
            if a_l is not None and a_s is not None:
                diffs.append(a_s - a_l)
    else:
        bloecke: Dict[str, List[int]] = {}
        for i, c in enumerate(cases_mit_schatten):
            bloecke.setdefault(c[block_feld], []).append(i)
        keys = sorted(bloecke)
        k = len(keys)
        cluster_anzahl = k
        for _ in range(bootstrap):
            gezogen = [keys[rng.randrange(k)] for _ in range(k)] if k else []
            idx: List[int] = []
            for key in gezogen:
                idx.extend(bloecke[key])
            l2 = [live[i] for i in idx]
            s2 = [schatten[i] for i in idx]
            y2 = [labels[i] for i in idx]
            a_l = ev.auc(l2, y2)
            a_s = ev.auc(s2, y2)
            if a_l is not None and a_s is not None:
                diffs.append(a_s - a_l)

    diffs.sort()
    alpha = 1.0 - ci_level
    lo = ev._quantil(diffs, alpha / 2) if diffs else float("nan")
    hi = ev._quantil(diffs, 1 - alpha / 2) if diffs else float("nan")
    return {
        "differenz": punkt, "ci_untergrenze": lo, "ci_obergrenze": hi,
        "ci_niveau": ci_level, "cluster_anzahl": cluster_anzahl,
        "bootstrap_ziehungen": bootstrap, "faelle": len(cases_mit_schatten),
        "auc_live": auc_live_punkt, "auc_schatten": auc_schatten_punkt,
    }


def verdikt(ci_untergrenze: float, differenz: Optional[float]) -> str:
    """WÖRTLICH nach docs/validation_registry.md, Eintrag PR #194,
    "VORAB-FESTLEGUNG der Auswertung": 'Schatten besser' NUR wenn die
    Differenz > 0 UND das Intervall 0 ausschließt; SONST 'nicht
    entscheidbar' — es gibt KEINEN dritten Stempel ('Live besser' o. ä.)."""
    if differenz is None:
        return "nicht entscheidbar"
    if differenz > 0 and ci_untergrenze > 0:
        return "Schatten besser"
    return "nicht entscheidbar"


# ---------------------------------------------------------------------------
# Bericht
# ---------------------------------------------------------------------------
def _zusatz(explorativ: bool) -> str:
    return f" [{EXPLORATIV_ZUSATZ}]" if explorativ else ""


def bericht_zaehlung(records: Sequence[Dict], cases: Sequence[Dict]) -> str:
    zeilen = ["Auswertungsskript — Stichtage, Modus: --zaehlung "
             "(nur Fallzahlen, keine weiteren Kennzahlen)",
             "=" * 70, ""]
    zeilen.append(f"Schatten-Stichtag (#194): "
                 f"{SCHATTEN_STICHTAG_UTC or 'noch nicht belegt'}")
    zeilen.append("")
    for name, pred, _ist_schatten in alle_kohorten():
        fz = fallzahlen(records, cases, pred)
        zeilen.append(
            f"- {name}: n gesamt={fz['n_gesamt']}, n reif={fz['n_reif']}, "
            f"Schatten gesetzt={fz['n_schatten_gesetzt']}")
    return "\n".join(zeilen)


def bericht_auswertung(records: Sequence[Dict], cases: Sequence[Dict],
                       explorativ: bool) -> str:
    zusatz = _zusatz(explorativ)
    zeilen = [f"Auswertungsskript — Stichtage, Modus: --auswerten{zusatz}",
             f"{'=' * 70}{zusatz}", ""]
    zeilen.append(
        "HINWEIS: die Trefferquote wird NICHT gegen den Zufalls-Benchmark "
        f"getestet (keine neue Holm-Rechnung).{zusatz}")
    zeilen.append(
        f"Schatten-Stichtag (#194): "
        f"{SCHATTEN_STICHTAG_UTC or 'noch nicht belegt'}{zusatz}")
    zeilen.append("")

    for name, pred, ist_schatten in alle_kohorten():
        fz = fallzahlen(records, cases, pred)
        zeilen.append(f"--- {name}{zusatz} ---")
        zeilen.append(
            f"  n gesamt={fz['n_gesamt']}, n reif={fz['n_reif']}, "
            f"n Treffer={fz['n_treffer']}, Schatten gesetzt="
            f"{fz['n_schatten_gesetzt']}{zusatz}")
        kohorten_cases = fz["cases"]
        if fz["n_reif"] < SECONDARY_MIN_N:
            zeilen.append(
                f"  Trefferquote/AUC: zu wenige Fälle (< {SECONDARY_MIN_N})"
                f"{zusatz}")
        else:
            quote = fz["n_treffer"] / fz["n_reif"]
            zeilen.append(f"  Trefferquote={quote:.4f}{zusatz}")
            for seed in SEEDS:
                r = auc_mit_block_bootstrap(kohorten_cases, "score", seed)
                zeilen.append(
                    f"  Seed {seed}: AUC Live {r['primär']['auc']:.4f} "
                    f"(Untergrenze {r['primär']['ci_untergrenze']:.4f}); "
                    f"Tag-Block Untergrenze "
                    f"{r['Tag-Block']['ci_untergrenze']:.4f}; "
                    f"Ticker-Block Untergrenze "
                    f"{r['Ticker-Block']['ci_untergrenze']:.4f}{zusatz}")

        if ist_schatten:
            mit_schatten = _mit_schatten_score(kohorten_cases)
            zeilen.append(
                f"  Records mit Schatten != Live: "
                f"{sum(1 for c in mit_schatten if c['score_schatten'] != c['score'])}"
                f" von {len(mit_schatten)}{zusatz}")
            if len(mit_schatten) < SECONDARY_MIN_N:
                zeilen.append(
                    f"  Schatten-Vergleich: zu wenige Fälle "
                    f"(< {SECONDARY_MIN_N}) — Teststärke begrenzt, "
                    f"'nicht entscheidbar' ist ein zulässiges Ergebnis"
                    f"{zusatz}")
            else:
                for seed in SEEDS:
                    d = differenz_mit_gepaartem_bootstrap(
                        mit_schatten, "ticker", seed)
                    v = verdikt(d["ci_untergrenze"], d["differenz"])
                    zeilen.append(
                        f"  Seed {seed} (Ticker-Block, gepaart): "
                        f"AUC Live {d['auc_live']:.4f}, AUC Schatten "
                        f"{d['auc_schatten']:.4f}, Differenz "
                        f"{d['differenz']:.4f} "
                        f"[Untergrenze {d['ci_untergrenze']:.4f}, "
                        f"Obergrenze {d['ci_obergrenze']:.4f}] -> {v}{zusatz}")
                zeilen.append(
                    f"  Teststärke begrenzt, 'nicht entscheidbar' ist ein "
                    f"zulässiges Ergebnis; ein Wechsel des Live-Scores "
                    f"erfolgt nur nach Easys eigener Entscheidung"
                    f"{zusatz}")
        zeilen.append("")
    return "\n".join(zeilen)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _heute_berlin(jetzt: Optional[_dt.datetime]) -> _dt.date:
    if jetzt is None:
        jetzt = _dt.datetime.now(_dt.timezone.utc)
    if jetzt.tzinfo is None:
        jetzt = jetzt.replace(tzinfo=_dt.timezone.utc)
    return jetzt.astimezone(BERLIN).date()


def _pfad_verboten(pfad: Path) -> bool:
    try:
        rel = pfad.resolve().relative_to(REPO_ROOT.resolve())
    except ValueError:
        return False  # außerhalb des Repos — nicht unser Problem, aber auch nicht verboten
    return rel.parts and rel.parts[0] in _VERBOTENE_VERZEICHNISSE


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Auswertungsskript für den 07.12.2026 (PR 4 von 4). "
                    "Nur lesend, nur manuell, schreibt nie in data/ oder "
                    "docs/.")
    modus = ap.add_mutually_exclusive_group(required=True)
    modus.add_argument("--zaehlung", action="store_true",
                       help="Nur Fallzahlen, keine Trefferquote/AUC/Verdikt.")
    modus.add_argument("--auswerten", action="store_true",
                       help="Volle Rechnung (verweigert vor 2026-12-07 ohne "
                            "--vorzeitig).")
    ap.add_argument("--vorzeitig", action="store_true",
                    help="Erlaubt --auswerten vor dem 07.12.2026 — jede "
                         "Zeile trägt dann 'EXPLORATIV, nicht präregistriert'.")
    ap.add_argument("--sammlung", default="data/forward_collection.json")
    ap.add_argument("--out", default=None,
                    help="Zusätzlich den Bericht in diese Datei schreiben "
                         "(außerhalb von data/ und docs/).")
    ap.add_argument("--jetzt", default=None,
                    help="ISO-Zeitstempel für die Freigabe-Prüfung "
                         "(Tests/--vorzeitig-Entscheidung) statt der echten Uhr.")
    args = ap.parse_args(argv)

    if args.out:
        out_aufgeloest = (REPO_ROOT / args.out).resolve()
        if _pfad_verboten(Path(args.out) if Path(args.out).is_absolute()
                          else REPO_ROOT / args.out):
            print(f"[auswertung_stichtage] VERWEIGERT: --out zeigt auf "
                  f"data/ oder docs/ ({args.out}) — das darf dieses Skript "
                  f"nie beschreiben.", file=sys.stderr)
            return 2
    else:
        out_aufgeloest = None

    if args.auswerten and not args.vorzeitig:
        jetzt = (_dt.datetime.fromisoformat(args.jetzt) if args.jetzt
                else None)
        heute = _heute_berlin(jetzt)
        if heute < AUSWERTUNG_FREIGABE_DATUM:
            print(f"[auswertung_stichtage] VERWEIGERT: heute ({heute}, "
                  f"Europe/Berlin) liegt vor dem Freigabe-Datum "
                  f"{AUSWERTUNG_FREIGABE_DATUM} — die Score-Review-"
                  f"Wiedervorlage ist noch nicht fällig. Mit --vorzeitig "
                  f"erzwingbar (jede Zeile wird dann als "
                  f"'{EXPLORATIV_ZUSATZ}' markiert).", file=sys.stderr)
            return 1

    sammlung_pfad = REPO_ROOT / args.sammlung
    coll = json.loads(sammlung_pfad.read_text(encoding="utf-8"))
    records = coll.get("records") or []
    cases, _zaehlwerk = ev.build_population(coll)

    if args.zaehlung:
        text = bericht_zaehlung(records, cases)
    else:
        text = bericht_auswertung(records, cases, explorativ=args.vorzeitig)

    print(text)
    if out_aufgeloest:
        out_aufgeloest.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
