#!/usr/bin/env python3
"""Marker „invertiertes Risiko bei Anlage" — additiv, markiert, heilt nie.

HINTERGRUND (14.10.2026, Diagnose-Folgeauftrag, Easy-Entscheidung Variante A).
Die Diagnose vom 14.10.2026 fand 11 von 202 Records, deren ``entry_close`` bei
Anlage bereits auf oder unter der eigenen ``invalidation_price`` lag — "1R" war
für sie nie definiert (vgl. ``forward_collection._r_kennzahlen``, Zeile
746/760: dieselbe Geometrie setzt dort BEREITS seit 06.09.2026 additiv
``r_nicht_ermittelbar_grund = "invertiertes_risiko"``, Bedingung
``risiko_abstand <= 0`` — ALSO EXAKT dieselben 11 Fälle, wie die Diagnose
belegt hat; kein Operator-Unterschied in der Praxis, da kein Fall exakt auf
der Marke lag). Dieses Modul schafft dafür einen EIGENEN, unabhängig aus
``entry_close``/``invalidation_price`` berechneten Marker — bewusst NICHT nur
aus ``r_nicht_ermittelbar_grund`` abgeleitet, damit ein künftiges
Auseinanderlaufen beider Felder sichtbar würde (s. Test
``test_marker_stimmt_mit_r_nicht_ermittelbar_grund_ueberein``), statt eine
zweite, stillschweigend abhängige Quelle der Wahrheit zu sein.

OPERATOR (Teil 0b der Diagnose): ``<=`` (``entry_close <= invalidation_price``)
— identisch zur bestehenden Bedingung in ``forward_collection._r_kennzahlen``
(dort als ``risiko_raw > 0`` im Positiv-Zweig, also ``<= 0`` im Else-Zweig
formuliert — NICHT ``<``, wie eine frühere Beschreibung dieser Entscheidung
annahm; richtiggestellt in der Diagnose vom 14.10.2026). Auf dem aktuellen
Bestand (202 Records) ändert die Operator-Wahl nichts (0 Fälle mit exakter
Gleichheit), die Konsistenz zur bestehenden Regel ist dennoch der Grund für
die Wahl.

WAS DAS IST (und was nicht): reine Kennzeichnung. Score, Ranking,
Kandidaten-Auswahl, Primärwertung, eingefrorene Felder, ``evaluate.py``
(SHA256-gepinnt) und die Auswertungs-Population bleiben UNANGETASTET — wie
bei ``in_session_creation``/``episode_split_suspect``/``stale_market_suspect``.
Das Feld gehört NICHT zu ``FROZEN_FIELDS``.

TAGESLAUF (Mini-Stopp, s. Diagnose-Bericht): dieses Modul markiert NUR auf
Anfrage per Backfill-Skript (``mark_invertiertes_risiko_anlage.py``). Eine
laufende Markierung NEUER Records im Tageslauf (analog
``in_session.markiere_neue_records`` in ``elliott_pipeline.main()``) ist
BEWUSST NICHT gebaut — das würde den Tageslauf-Pfad berühren, was laut
Auftrag einen Mini-Stopp verlangt. Offener Punkt, s. SESSION_HANDOVER.md.

SENSITIVITÄTSREGEL (Teil 0d der Diagnose): dieser Marker fällt NICHT
automatisch unter die Sensitivitätsrechnung aus ``filter_sensitivity_
sammlung.py`` — deren ``MARKERS``-Tupel ist hart codiert und kennt nur die
drei namentlich genannten Marker. Die Registry-Formulierung „künftige Marker
fallen automatisch unter dieselbe Regel" ist eine GOVERNANCE-Zusage, keine
Lauf-Automatik; sie wirkt nur, wenn der Marker-Name dort eingetragen wird.
Das ist in diesem Auftrag BEWUSST NICHT geschehen (nicht Teil des Auftrags,
hätte Rückwirkung auf die bestehende (b)-Sensitivitätsrechnung) — offener
Punkt, s. SESSION_HANDOVER.md. Die separate Zeile in
``evaluate_nicht_invalidiert.py`` (Teil 1.3) hängt NICHT an diesem Mechanismus,
sondern filtert direkt auf diesen Marker.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import repo_path  # noqa: F401 — legt Repo-Root + scripts/ auf sys.path
from numeric import finite  # noqa: E402

MARKER = "invertiertes_risiko_bei_anlage"
MARKER_UTC = "invertiertes_risiko_bei_anlage_marked_utc"


def ist_invertiertes_risiko_bei_anlage(entry_close, invalidation_price) -> Optional[bool]:
    """DAS MARKER-KRITERIUM: ``entry_close <= invalidation_price`` bei Anlage.

    ``None`` = NICHT BERECHENBAR (fehlender/nicht-endlicher Wert) — der
    Aufrufer muss diesen Fall laut behandeln, nie still als "kein Treffer"
    verbuchen (gleiches Prinzip wie ``in_session.im_sitzungsfenster``)."""
    if not finite(entry_close) or not finite(invalidation_price):
        return None
    return entry_close <= invalidation_price


def record_key(rec: Dict) -> Tuple:
    """Identität wie bei ``in_session``/``mark_stale_market_records`` — nicht
    ``episode_id`` (kollidiert real, z. B. zweimal ``ADS.DE@2026-07-24``)."""
    return (rec.get("ticker"), rec.get("created_utc"))


def betroffene_records(records: Sequence[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """(zu markieren, nicht berechenbar) — rein, deterministisch, ohne I/O."""
    treffer: List[Dict] = []
    unklar: List[Dict] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        urteil = ist_invertiertes_risiko_bei_anlage(
            rec.get("entry_close"), rec.get("invalidation_price"))
        if urteil is None:
            unklar.append(rec)
        elif urteil:
            treffer.append(rec)
    return treffer, unklar


def markiere(records: Sequence[Dict], marked_utc: str) -> Tuple[int, List[Dict]]:
    """Setzt den Marker in-place. Ändert AUSSCHLIESSLICH die zwei
    Marker-Felder. Idempotent: ein bereits markierter Record behält seinen
    URSPRÜNGLICHEN ``marked_utc``-Stempel (die Markierung ist ein Ereignis,
    kein laufender Zustand)."""
    treffer, unklar = betroffene_records(records)
    gesetzt = 0
    for rec in treffer:
        if rec.get(MARKER) is True:
            continue
        rec[MARKER] = True
        rec.setdefault(MARKER_UTC, marked_utc)
        gesetzt += 1
    return gesetzt, unklar


def entferne_marker(records: Sequence[Dict]) -> int:
    """RÜCKWEG: entfernt beide Marker-Felder restlos. Sonst nichts."""
    entfernt = 0
    for rec in records:
        if not isinstance(rec, dict):
            continue
        weg = False
        for feld in (MARKER, MARKER_UTC):
            if feld in rec:
                del rec[feld]
                weg = True
        entfernt += bool(weg)
    return entfernt
