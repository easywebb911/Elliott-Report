# Validierungs-Register — Score-Validierung (Forward-Sammlung)

**Registriert am 22.07.2026 — VOR der ersten gesammelten Zahl.**
Diese Erfolgs-Definition ist vorab festgeschrieben (Präregistrierung). Sie darf
nicht nachträglich zugunsten eines gewünschten Ergebnisses geändert werden.

> **Der Score ist bis auf Weiteres `heuristisch · unvalidiert`.** Dieses Register
> legt fest, was „validiert" überhaupt bedeuten würde — und dass ein
> Punktschätzer allein das nie belegt.

## Was gesammelt wird (forward-only, je Kandidat ab Karten-Erscheinen)

Ab dem Tag, an dem ein Kandidat auf einer Karte erscheint, werden über einen
Horizont von **10 Handelstagen** ausschließlich vorwärts (forward-only)
gesammelt:

- **`target_hit`** — Basis-Zielzone erreicht **VOR** der Invalidierung (binär).
- **`ext_hit`** — Extension-Zone erreicht **VOR** der Invalidierung (binär).

> **Entry-Regel (Prinzip, festgeschrieben 23.07.2026 — PRU-Befund).** Ein Kandidat
> ist nur **auswertbar**, wenn bei Record-Anlage der Schlusskurs **UNTER
> `target_zone.low`** liegt — das Ziel darf erst **nach** der Anlage erreicht
> werden, sonst ist der „Treffer" ein Look-ahead-Artefakt und keine Vorhersage.
> Analog für `ext_hit` mit `extension.low`. **Hintergrund:** die stillschweigenden
> Annahmen der Backtest-Literatur (ein Signal wird zum Signalzeitpunkt eröffnet,
> das Ziel liegt noch voraus) müssen hier als **explizite Regeln** stehen — der
> PRU-Befund vom 23.07. zeigte, dass sie sonst still verletzt werden. Umsetzung:
> Guard in `mature_record` ab 23.07. (s. u. „Änderungs-Log").
- **`invalidated`** — Invalidierung zuerst gerissen (binär).
- **`max_gain_10d`** — maximaler Gewinn im Horizont (relativ zum Einstiegskurs).
- **`max_drawdown_10d`** — maximaler Rückgang im Horizont (relativ).
- **`r_multiple`** — max. Gewinn ÷ Abstand Kurs→Invalidierung (Reward in R).

## Wann Erfolg als BELEGT gilt

Erfolg gilt **NUR** als belegt, wenn **BEIDES** zutrifft:

1. Die **Trefferquote** schlägt einen **Zufalls-Benchmark** (gleiche Aktien,
   zufällige Einstiegstage, gleiche relative Ziel-/Stop-Distanzen)
   **Holm-korrigiert signifikant**, UND
2. die **Bootstrap-CI-Untergrenze der AUC** (Score vs. `target_hit`) liegt
   **> 0,5**.

## Regeln (nicht verhandelbar)

- Auswertung **erst ab n ≥ 100 AUSWERTBAREN Setups** (gereift **und nicht**
  vom PRU-Guard ausgeschlossen — siehe nächster Punkt). „Gereift" allein reicht
  nicht; die n-Schwelle zählt `eval_counts(...)[2]` (auswertbar).
- **PRU-Guard / „Kurs schon bei Anlage über der Zone" (ab 23.07.2026, s. u.):**
  War der Schlusskurs am Anlage-Tag bereits **≥ Zonen-Unterkante**, ist ein
  späterer „Treffer" ein **Look-ahead-Artefakt** (das Ziel war zum Anlage-
  Zeitpunkt schon erreicht, keine Vorhersage). Solche Records reifen **normal**
  aus (Invalidierung, `max_gain/drawdown/r_multiple` voll gültig), aber
  `target_hit`/`ext_hit` sind **gesperrt** (auf 0, nie 1) und `pre_reached_target`
  / `pre_reached_ext` markieren sie. Records mit `pre_reached_*` **oder**
  `pre_guard_contaminated` sind aus **Trefferquote UND AUC** ausgeschlossen —
  sie zählen NICHT zur n ≥ 100-Population. Die Invalidierungs-Statistik bleibt
  von ihnen unberührt gültig.
- Das **Marktregime** wird je Record mitprotokolliert (z. B. SPY/DAX über/unter
  der 200-Tage-Linie).
- Forward-Daten werden **NIE mit Backfill gepoolt**.
- **Persönliche Watchlist-Ticker gehören NICHT zur Population.** Sie sind eine
  eigene Selektion, keine Tool-Auswahl; sie einzumischen würde die Auswahl-
  Verzerrung messen statt den Score. Der Schutz ist **baulich**: die Sammlung
  liest ausschließlich die Markt-Top-5 (`markets[].candidates`); die Watchlist
  lebt im separaten Feld `watchlist` und wird nie gesammelt. Ein Watchlist-Ticker
  zählt nur, wenn er **unabhängig** einen Top-5-Platz verdient.
- Ein **Punktschätzer allein ist nie Bestätigung**.

## Score-Status & Review-Wecker (`review_by`)

**Status:** `heuristisch · unvalidiert` — bleibt so, **bis** die obige
Erfolgs-Definition BELEGT ist. Der Status-Wechsel ist **rein menschlich**; nichts
automatisiert ihn.

**`review_by` (menschliche Kopie):** aktuell **2026-12-07** (grob projiziert, wann
n ≥ 100 gereift erreicht sein könnte). Die maschinenlesbare Quelle liegt in
`config.SCORE_REVIEW_BY`; **beide bei einer Änderung zusammen pflegen.** Ein
schlanker Wecker (`scripts/notify.py`) erinnert ~1×/Woche per ntfy, wenn das Datum
überschritten ist — er **ändert nichts**, weckt nur. Nach einer Auswertung wird
`review_by` **menschlich** neu gesetzt (Datum in die Zukunft) oder auf `None`
(abgeschaltet). Der Meilenstein-Push (n ≥ 100 tatsächlich gereift) feuert
zusätzlich datengetrieben genau einmal.

## Sammel-Mechanik (Kurzfassung)

- Ein Record **pro Ticker-Episode**. Kein Doppel-Record, wenn derselbe Ticker am
  Folgetag wieder in den Top-5 ist. **Wiederauftauchen nach Verschwinden = neue
  Episode.**
- Ein aus den Top-5 gefallener Ticker ändert **nichts** an offenen Records — die
  Episode reift trotzdem aus (kein Survivorship-Bias).
- Gesammelt wird in `data/forward_collection.json` (separat von
  `report.json`, additiv, revertierbar via `scripts/purge_forward_collection.py`).
- Fail-soft: ein Sammel-Fehler darf den Report nie brechen.

## Zusätzlich mitprotokollierte Felder (nur Anzeige/Backtesting)

Rein für die Review-Ansicht (Hamburger-Menü → „Validierung / Backtesting"),
**ohne** Einfluss auf die obige Erfolgs-Definition oder auf Score/Ranking:

- **`count_label`, `chart_points`, `count_wave_labels`** — die Auszählung zum
  **Anlage-Zeitpunkt** (Pivots Datum/Kurs/Art + Wellen-Ziffern). **Point-in-time
  eingefroren:** werden bei späteren Läufen nie geändert, damit die damalige
  Zählung exakt verortbar bleibt.
- **`price_path`** — die Folgetags-Schlusskurse (max. `HORIZON_DAYS`), je Lauf
  deterministisch aus der vollen Historie neu aufgebaut.

Diese Felder sind reine Anzeige-Daten; die Auswertungs-Sperre (kein Aggregat vor
n ≥ 100) gilt unverändert.

## Änderungs-Log der Population

- **23.07.2026 — Universum erweitert von 99 auf 361 Ticker** (US ~50 → 239
  S&P-500-Titel; DE ~49 → 122 DAX/MDAX/SDAX). Statische Listen, kein Screener.
  **Wirkung auf die Validierung:** die Population (Kandidaten-Grundgesamtheit)
  wächst — die **Zählweise** ändert sich NICHT. Episoden-Definition,
  `appearance_count` (Episoden, nicht Tage) und die n ≥ 100-Sperre bleiben
  unverändert. Ab jetzt gesammelte Episoden entstammen dem größeren Universum;
  das ist transparent zu halten, wenn später ausgewertet wird (der Score-Test
  misst weiterhin den Score, nicht die Universums-Auswahl).
- **23.07.2026 — PRU-Guard: „Kurs schon bei Anlage über der Zone" von der
  Trefferquote ausgeschlossen.** Befund (Read-only-Diagnose 23.07.): PRU (Lauf
  2026-07-23) stand mit Kurs 117,4 **über** Zielzone 112,4–116,2 (Ende-W4), rankte
  aber mit Score 84 auf Platz 3 — und die Reifung zählte solche Fälle als
  `target_hit` **an Tag 1** (das Ziel war bei Anlage schon erreicht). Empirisch
  betroffen im Bestand: **MET, D, PRU** (`entry_close ≥ Zonen-Low`, `target_hit=1`
  nach 1 Bar). **Maßnahme (forward-only, nichts gelöscht):** (1) Guard in
  `mature_record` — `target_hit`/`ext_hit` nur, wenn `entry_close < Zonen-Low`
  (sonst gesperrt + `pre_reached_*`); (2) die 3 Alt-Records mit
  `pre_guard_contaminated: true` **ausgewiesen** (bleiben im Datenbestand,
  reifen weiter, zählen aber nicht in Trefferquote/AUC); (3) n ≥ 100 zählt ab
  jetzt **auswertbare** Records (`eval_counts`). **Bewusst NICHT geändert:** Score,
  Ranking, Filterung der Kandidaten. Ein **Filter** (verbrauchte Setups gar nicht
  erst ranken, Skip-Grund `target_exceeded`) ist eine **separate, spätere Produkt-
  Entscheidung** (offen), kein Teil dieses Registry-Eintrags. Score-Malus verworfen.
- **23.07.2026 — Filter `target_exceeded` aktiv (Populations-Änderung).** Easys
  Produktentscheidung auf Basis der PRU-Diagnose: ein Setup, dessen Lauf-
  Schlusskurs die Zielzone bereits erreicht hat (**`close ≥ target_zone.low`** =
  „Zielzone erreicht" = nicht mehr handelbar), wird **VOR dem Ranking** aus den
  **Markt-Top-5** verworfen (Skip-Grund `target_exceeded`, eigener Diag-Zähler);
  Rang 6+ rückt nach. **Wirkung auf die Population:** ab jetzt entstehen forward-
  Episoden **nur noch für handelbare** (nicht-verbrauchte) Top-5 — die Grundgesamt-
  heit verengt sich bewusst auf einsteigbare Setups. Die **Watchlist** ist
  ausgenommen (zeigt alles, Badge markiert den Zustand) und war ohnehin nie Teil
  der Population. **Verteidigung in der Tiefe:** der Filter verhindert die Neuanlage
  über Zone, der **#28-Guard bleibt** als zweites Netz (schützt die Messung, falls
  doch je eine Episode über Zone durchkommt — `pre_reached_*`/Ausschluss).
  Schwelle **identisch** zur Guard-/Entry-Regel (`target_zone.low`). Score/Ranking-
  Formel **unverändert**; nur die Kandidaten-Grundgesamtheit ändert sich (transparent
  zu halten, wenn ausgewertet wird — der Score-Test misst weiter den Score).
