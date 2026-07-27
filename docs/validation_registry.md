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
- **`confluence`** (ab 23.07.2026 gesammelt) — **reines Mess-Feld**: welche breit
  beachteten Crowd-Marken (52-Wochen-Hoch, 200-Tage-Linie, nächste runde Zahl)
  innerhalb ±1 % mit Zielzone bzw. Invalidierung zusammenfallen (`{target, invalidation}`).
  **Point-in-time zum Anlage-Zeitpunkt eingefroren** (nie nachträglich geändert).
  **KEINE Score-/Ranking-Wirkung** (Registry-Vorbehalt). Zweck: die spätere
  n ≥ 100-Auswertung kann als **eigene Dimension** testen, ob Konfluenz-Zonen öfter
  treffen — eine etwaige Score-Wirkung käme **erst nach** einem Validierungsbefund.
- **`a_correction_observed`, `a_retrace_pct`, `a_observe_until`** (W5→A-Nachprüfung,
  **ab 24.07.2026 gemessen**) — **reines Mess-Feld**: folgt nach einem erfüllten
  **Ende-W4-Treffer** (`target_hit`, gereift, **nicht** PRU-ausgeschlossen) die
  theorie-gemäße Korrektur A? Nach dem Episoden-Hoch werden **`A_OBSERVE_DAYS = 10`**
  weitere Handelstage beobachtet; `a_correction_observed = true`, sobald der Kurs
  **≥ `A_RETRACE_MIN = 38,2 %`** (Fibonacci-Minimum) der W5-Strecke (P4→Hoch)
  zurückläuft, `false` bei vollem Fenster ohne Rücklauf, `null` solange das Fenster
  offen ist bzw. keine Messung greift. **Angehängtes Beobachtungsfenster** — es
  **verlängert oder ändert die bestehende Reifung nicht** (separater Durchgang,
  Reifungs-Zahlen byte-identisch). **Guard-Konsistenz:** `pre_reached`/`pre_guard`-
  Records bekommen **keine** Messung (ihr „Hoch" ist nicht interpretierbar → `null`).
  **KEINE Score-/Ranking-/Filter-Wirkung** (Registry-Vorbehalt); **Auswertung
  gemeinsam mit der n ≥ 100-Population**, dann als eigene Dimension „stimmt auch das
  Nachspiel?".

Diese Felder sind reine Anzeige-/Mess-Daten; die Auswertungs-Sperre (kein Aggregat
vor n ≥ 100) gilt unverändert.

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
- **24.07.2026 — W5→A-Nachprüfung (Lit-Check b) als Mess-Feld ergänzt.** Für gereifte
  **Ende-W4-Treffer** wird ab jetzt mitprotokolliert, ob nach dem Episoden-Hoch die
  theorie-gemäße Korrektur A einsetzt (`a_correction_observed`/`a_retrace_pct`/
  `a_observe_until`, s. Feld-Beschreibung oben; benannte Konstanten
  `A_OBSERVE_DAYS = 10`, `A_RETRACE_MIN = 0.382` in `scripts/forward_collection.py`).
  **Reines Mess-Feld, angehängtes Beobachtungsfenster** — die bestehende Reifung
  bleibt **byte-identisch** (separater Durchgang), `pre_reached`/`pre_guard`-Records
  werden **nicht** gemessen. **Bewusst NICHT geändert:** Score, Ranking, Filterung,
  `report.json`-Markt-Payload, Erfolgs-Definition. **Auswertung erst gemeinsam mit
  der n ≥ 100-Population** (dann als eigene Dimension). Revertierbar (additive Felder).
- **25.07.2026 — Universum-Hygiene: 8 Symbole entfernt** (US 239 → 236, DE 122 → 117;
  Gesamt 361 → 353). Grundlage: `market.diag.dead_tickers` aus dem committeten
  `report.json` (Lauf 2026-07-25T13:35Z), alle Grund `empty_data` (yfinance liefert
  keine Kursreihe). Entfernt aus `config.py`-Listen **und** `data/ticker_meta.json`:
  **US (3):** `MMC`, `FI`, `HES`; **DE (5):** `1COV.DE`, `CTS.DE`, `UN01.DE`,
  `SHA.DE`, `COP.DE`. **Keine Ersatz-Ticker erfunden** — das Universum schrumpft
  minimal (ehrlicher als geratene Ersetzungen). Deckt sich exakt mit den
  `empty_data`-Zählern (DE 5 / US 3); gesunde Namensvettern **erhalten** (`COP`≠`COP.DE`,
  `FI`≠`FIS`, `NEM`/`NEM.DE`). **Wirkung auf die Validierung:** die Population
  schrumpft um tote Symbole, die ohnehin nie Kandidaten wurden — **Zählweise, Score,
  Ranking, Filter unverändert**. Erwartung Folge-Lauf: `empty_data → 0` je Markt.
  Revert = die 8 Symbole in `config.py` + `ticker_meta.json` wieder eintragen.
- **25.07.2026 — Messfelder v1 (Lit-Check P2): drei literaturgestützte MESS-Felder
  point-in-time eingefroren.** REINE MESSUNG — **Score, Ranking, Filter, Population
  und die bestehende Reifung bleiben byte-identisch** (belegt: Report-Diff nur
  additive `vol_*`-Keys, gleiche Kandidaten/Reihenfolge/Scores; Reifungs-Test grün).
  Volumen steckt im **selben** yfinance-Download (kein Extra-Call), additiv aus
  `parse_download_df` als `FetchOutcome.volumes`. **STEHENDE REGEL (nicht
  verhandelbar):** eine Definition wird **nie umdefiniert** — eine Änderung erzeugt
  neue, datierte Felder (`…_v2`), damit die n≥100-Auswertung stabile Zeitreihen hat.
  Definitionen v1 (Konstanten in `scripts/forward_collection.py`):
  - **(A) Volumen-Profil** (bei Anlage, `build_candidate`): `vol_profile` = Ø-Tages­
    volumen je Welle über das Pivot-Segment **inklusive** beider Pivot-Bars
    (`end_of_w2`: W1,W2 · `end_of_w4`: W1–W4). Abgeleitet: `vol_ratio_w3_w1`,
    `vol_ratio_w4_w3` (end_of_w4) bzw. `vol_ratio_w2_w1` (end_of_w2). Division-
    Guards: fehlendes/0-Volumen → betroffenes Feld `null`. **Guideline:** Volumen
    trägt in W1/3/5, **W3 am höchsten** — `vol_ratio_w3_w1 < 1` ist der
    Zählfehler-Verdacht (einziges sichtbares Element: dezenter Chip „W3-Volumen
    schwach", kein Score-Einfluss).
  - **(B) Alternation** (bei Anlage, **nur `end_of_w4`**; `end_of_w2` → alle `null`):
    Rohwerte `w2_retrace_pct` (von W1), `w4_retrace_pct` (von W3), `w2_bars`,
    `w4_bars` aus den eingefrorenen Pivots. Flag `alternation_observed` =
    `|w2_retrace − w4_retrace| ≥ ALTERNATION_MIN_DIFF_PP (20 pp)` **ODER**
    Dauer-Verhältnis `max/min ≥ ALTERNATION_DURATION_RATIO (2×)`. Die **Rohwerte**
    machen die Auswertung definitions-unabhängig (das Flag ist nur eine mögliche
    Operationalisierung).
  - **(C) W5-Momentum-Divergenz** (bei **Reifung**, **nur `end_of_w4` + `target_hit`**,
    nicht ausgeschlossen): Momentum-Proxy = `MOMENTUM_ROC_BARS`-Tage-Rate-of-Change
    der Schlusskurse (reines Python, keine Dependency). `w5_momentum_divergence` =
    Episoden-Hoch **> W3-Hoch** **und** ROC am Episoden-Hoch **<** ROC am W3-Hoch
    (W3-Hoch per **Datum** aus den Pivots gesucht — 2-J-Fenster wandert). Roh-
    Momentum `w5_mom_w3`/`w5_mom_high` mit eingefroren. Nicht bestimmbar (zu wenig
    Bars / `pre_reached` / kein P3) → `null`. **Angehängter** Schritt wie die
    W5→A-Nachprüfung — die Reifung (Schritt 2) bleibt byte-identisch.
  Alt-Records unberührt (Felder fehlen = `null`, forward-only, **kein Backfill**).
  Revert = die additiven Felder + `volumes`-Pfad + der eine Frontend-Chip raus.
- **25.07.2026 — Ambiguität v1 (Lit-Check P3): Ambiguitäts-Ausweis.** Fach-Konsens
  ist Multi-Count (fast immer > eine valide Zählung); der Haupt-Kritikpunkt an
  Elliott ist Subjektivität — dieser Ausweis macht sie **sichtbar UND messbar**.
  **`ambiguity v1` misst Mehrdeutigkeit INNERHALB des heutigen Zähl-Vokabulars
  (2 Fenster: Ende-W4/Ende-W2), nicht den vollen Elliott-Interpretationsraum.
  Erweitert sich das Vokabular später (z. B. ABC-Erkennung aus P4), entsteht ein
  NEUES datiertes Feld (`ambiguity v2`) — v1 wird nie umdefiniert.** REINE ANZEIGE/
  MESSUNG: **Score, Ranking, Filter, `target_exceeded`, Reifung byte-identisch**
  (belegt: Report-Diff rekursiv nur additive `valid_count_total`/`alt_count`-Keys,
  gleiche Top-5/Scores/Reihenfolge; `SCHEMA_VERSION` = 1). **Befund/Zuschnitt:**
  `classify_setup` (`scripts/elliott_pipeline.py`) ist **first-fit** über genau diese
  zwei festen End-Fenster; der Ausweis **zählt beide** (statt nur den ersten) — kein
  neuer Suchraum, keine Enumeration über variable Fenster (die wäre mit den zwei
  fixen Validatoren nicht sauber abgrenzbar → bewusst NICHT gebaut). Definitionen v1:
  - **`valid_count_total`** (int, 1..2): Anzahl regelkonformer **LONG**-Counts unter
    {Ende-W4 auf den letzten 5 Pivots, Ende-W2 auf den letzten 3}. Short-Counts
    zählen **nicht** mit (Long-only, konsistent zum Board). Auf jeder erzeugten
    Zählung (Markt-Kandidat + Watchlist + alle Zeitebenen `timeframes`/`higher_degree`).
  - **`alt_count`** (nur wenn `total ≥ 2`, sonst `null`): kompakte **zweitbeste** —
    `{count_label, invalidation_price, target_zone, score_heuristic}`, geordnet nach
    **exakt derselben** `score_setup`-Formel (kein neues Ranking-Kriterium). Die
    Primär-Zählung (`counts[0]`) ist byte-identisch zu `classify_setup`.
  - **`ambiguity_n`** (Sammlung, bei **Anlage** eingefroren = `valid_count_total`):
    Auswertungs-Dimension für n≥100 — treffen **eindeutige** Zählungen (N=1) öfter
    als **mehrdeutige** (N=2)? Alt-Records `null`, forward-only, kein Backfill.
  **UI (dezent):** am Count-Label „Zählung 1 von N" **nur bei N ≥ 2** (Maximum
  **„1 von 2"**); darunter aufklappbar die Alternative (Label · Inval · Ziel · Score
  gedämpft). N = 1 zeigt nichts (Eindeutigkeit ist der Normal-Idealfall). Laufzeit-
  Impact vernachlässigbar (1 zusätzlicher fixer 5-/3-Punkt-Check je Zählung, O(1);
  synthetic-Vollreport 353 Ticker ≈ 64 ms). Revert = additive Felder + `_eval_*`/
  `enumerate_long_counts`/`ambiguity_fields` + Frontend-Block raus; `classify_setup`
  bleibt (die Helfer-Auslagerung ist verhaltensgleich).
- **25.07.2026 — Struktur-Vokabular v2 + ambiguity v2 (Lit-Check P4a): ABC-Korrektur-
  Erkennung.** Das Zähl-Vokabular wird um einfache **Zigzag-Korrekturen (A-B-C)**
  erweitert — AUSSCHLIESSLICH für (1) den Watchlist-Struktur-Befund, (2) `ambiguity
  v2` und (3) die W5→A-Strukturmessung. **HARTE SCOPE-GRENZE (Populations-Schutz):
  KEIN neuer Markt-Setup-Typ — Top-5, Score, Ranking, Filter, Episoden-Anlage
  byte-identisch** (belegt: rekursiver Report-Diff nur additive
  `valid_count_total_v2`/`alt_count_v2`-Keys; v1-Felder byte-identisch). Ein
  „Ende-ABC = Long-Einstieg" wäre eine SPÄTERE, datierte Produktentscheidung.
  Definitionen v2 (`_detect_correction`/`_corr_from` in `scripts/elliott_pipeline.py`,
  Konstanten `_ABC_IMPULSE_PIVOTS=6`, `_ABC_MAX_CORR_PIVOTS=3`):
  - **ABC-Erkennung** (nur auf BESTÄTIGTEN ZigZag-Pivots — die Pivot-Bestätigung IST
    der Signifikanzfilter, der Rest strikte Preis-Ungleichungen): nach einem per
    `validate_impulse` **validen 5er-Impuls** (6 Pivots) gilt, richtungs-normalisiert:
    **A** gegen die Impulsrichtung (`d·A < d·P5`), **B** retraced A ohne den
    Impuls-Endpunkt zu überschreiten (`d·A < d·B < d·P5`), **C** jenseits des A-Endes
    (`d·C < d·A`). **Longest-first** (A-B-C vor A-B vor A) → deterministisch.
  - **Neue `structure_state`-Kategorien** (Watchlist): `correction_running` (A oder
    A-B bestätigt; Marke = Invalidierung der Korrektur-Lesart: bei A das
    **W5-Extrem** — darüber ist die Korrektur-Lesart hinfällig —, bei A-B das
    **B-Hoch/B-Tief** — darüber/darunter wäre B kein Korrektur-Hoch mehr) und
    `correction_complete` (A-B-C komplett; Marke = **C-Tief/C-Hoch** — jenseits
    läuft die Korrektur weiter, „neuer Impuls möglich" ist Ehrlichkeits-Sprache,
    KEIN Setup-Versprechen). **Präzedenz:** eine bestätigte Korrektur-Lesart
    beschreibt die Lage vollständiger als das erneute Impuls-Lesen der letzten
    6/5/3 Pivots → sie **gewinnt** gegen die bestehenden 5 Kategorien; greift NUR
    bei ≥7 Pivots mit validem Impuls + erfüllten Ungleichungen, sonst unverändert.
  - **`valid_count_total_v2`/`alt_count_v2`** (Kandidat + alle Zeitebenen):
    Lesarten im erweiterten Vokabular = valide Impuls-Fenster (wie v1) **+ 1**,
    falls eine Korrektur-Lesart bestätigt ist. Primär bleibt die Impuls-Zählung;
    `alt_count_v2` bevorzugt die zweitbeste Impuls-Lesart (nach `score_setup`),
    sonst die Korrektur-Lesart (`kind`='correction', ohne Zielzone/Score). Die
    **Anzeige** („Zählung 1 von N") nutzt ab jetzt v2 (fail-soft-Fallback v1).
  - **`ambiguity_n_v2`** (Sammlung, bei Anlage): ZUSÄTZLICH eingefroren; **`ambiguity_n`
    (v1) wird UNVERÄNDERT weiter befüllt** (Vergleichbarkeit der Alt-Daten).
  - **W5→A strukturell** (`observe_w5_structure`, bei Reifung, nur end_of_w4 +
    target_hit): `a_structure_observed` = True, sobald nach dem Episoden-Hoch
    mindestens **ein bestätigter ZigZag-Gegen-Pivot** vorliegt (dieselbe Engine wie
    der Count); False erst nach voll beobachtetem `A_OBSERVE_DAYS`-Fenster ohne
    Gegen-Pivot; sonst null. `c_target_pct` = Tiefe des tiefsten bestätigten
    Korrektur-Pivots in % der W5-Strecke (P4→Hoch). **Angehängter Schritt** —
    Reifung + bestehende W5→A-Felder byte-identisch.
  Alt-Records: Felder fehlen = null, forward-only, kein Backfill. **v1-Felder werden
  nie umdefiniert.** Revert = `_detect_correction`/`_corr_from` + Präzedenz-Zweig +
  v2-Felder + `observe_w5_structure` + Frontend (2 CSS-States, v2-Badge-Switch,
  Methodik-Absatz) raus.
- **26.07.2026 — Agent-Kommentar v1 (KI-Entscheidung Easy): nächtlicher LLM-Kommentar
  je Markt-Top-5-Karte.** REINE KOMMENTAR-EBENE — **kein Score-/Ranking-/Filter-
  Effekt** (belegt: der Schritt läuft in `main()` NACH `build_report`, also nach
  Sortierung, Top-N-Schnitt und allen Filtern, und schreibt ausschließlich das
  additive Feld `agent_comment`; Test `test_ranking_and_scores_byte_identical`).
  Adaption der Squeeze-KI unter Elliott-Disziplin. **Bewusst NICHT übernommen:**
  Agent-Boost ins Ranking (Squeeze-Re-Test: kein Edge), KI-Score, Stunden-Ticks.
  **NEU gegenüber Squeeze:** das Urteil wird **messbar eingefroren**.
  - **Umfang:** nur die FINALEN Markt-Top-5 (~10 Aufrufe/Lauf), **Watchlist
    ausgenommen**. Ein Aufruf je Kandidat.
  - **Konstanten** (`scripts/agent_comment.py`): `AGENT_MODEL =
    "claude-haiku-4-5-20251001"`, `AGENT_TEMPERATURE = 0.0`, `AGENT_MAX_TOKENS = 500`,
    `AGENT_TIMEOUT_S = 30`, `AGENT_PARSE_RETRIES = 1`, `ANTHROPIC_VERSION = "2023-06-01"`.
  - **Input:** ausschließlich eigene Pipeline-Felder des Kandidaten (`count_label`,
    Zonen, Invalidierung, Score, `valid_count_total_v2` + Alternative, `vol_ratio_*`,
    Alternation-Rohwerte, `confluence`, `appearance_count`, `change_pct`) — **keine
    externen Fetches in v1**, keine Nachrichten/Fundamentaldaten.
  - **Output** (strukturiert erzwungen): `{lesart, gegenargument, concern_level}` mit
    `concern_level ∈ {none, low, high}`; Parse-Fehler → 1 Retry → sonst `null`.
  - **Inhalts-Netz (Guardian-Nit, 26.07.):** der Prompt verbietet Wahrscheinlichkeits-/
    Empfehlungs-Sprache, ein LLM ist aber nicht bindbar — deshalb prüft `_parse_reply`
    den Freitext zusätzlich gegen `BANNED_PHRASES` (`wahrscheinlich`, `probability`,
    `confidence`, `trefferquote`, `kaufempfehlung`, `verkaufsempfehlung`,
    `anlageberatung`; dieselben Wörter wie das Report-Sicherheitsnetz). Treffer wird
    wie ein Parse-Fehler behandelt (Retry → sonst `null`) — verbotene Sprache kann
    also **nie** in `report.json` oder die UI gelangen (Test auf Report-Ebene).
    Gespeichert als `agent_comment = {lesart, gegenargument, concern_level, model,
    generated_at}` oder `null`.
  - **Fail-soft total:** fehlendes `ANTHROPIC_API_KEY` → no-op (Feld gar nicht
    gesetzt) + Log-Zeile; jeder API-/Parse-Fehler → `null`, der Lauf läuft weiter.
    Der Key wird **nie** geloggt (Test `test_key_never_logged`). Kosten-Log je Lauf
    (Tokens in/out).
  - **Messung:** bei Episoden-ANLAGE werden `agent_concern_level` und `agent_model`
    **point-in-time eingefroren**. Begründung: **LLM-Output ist nicht
    deterministisch** — `temperature 0` mildert das, garantiert es nicht; deshalb
    muss der Wert ZUM ANLAGE-ZEITPUNKT verortbar bleiben. Alt-Records `null`,
    forward-only, kein Backfill. **Auswertungs-Frage (n≥100):** trifft
    `concern_level = "high"` seltener als `none`/`low`?
  - **Der Prompt ist Teil dieser datierten Definition** (Änderung ⇒ neue Version,
    v1 wird nie umdefiniert). System-Prompt wörtlich:

    > Du bist ein nüchterner Elliott-Wellen-Analyst und kommentierst eine bereits
    > fertig berechnete Zählung. Du bewertest NICHT neu und vergibst KEINE Punkte —
    > du erklärst und widersprichst. Sprich Klartext auf Deutsch, ohne Werbe- oder
    > Empfehlungssprache, ohne Wahrscheinlichkeits- oder Trefferquoten-Behauptungen,
    > ohne Kauf-/Verkaufsempfehlung. Nutze AUSSCHLIESSLICH die gelieferten Zahlen;
    > erfinde keine Kurse, Nachrichten oder Fundamentaldaten. Antworte NUR mit einem
    > JSON-Objekt, ohne Markdown-Codefence, mit exakt den Schlüsseln: lesart (2-3
    > Sätze: was diese Zählung im Klartext behauptet), gegenargument (1-2 Sätze: der
    > stärkste Einwand, der sich AUS DEN DATEN ergibt — z. B. Mehrdeutigkeit,
    > schwaches W3-Volumen, weite Invalidierung, fehlende Alternation),
    > concern_level (genau einer der Werte "none", "low", "high" — wie stark die
    > Daten der Zählung widersprechen).

    User-Nachricht: `Kommentiere diese Elliott-Zählung. Alle Angaben stammen aus
    unserer eigenen Pipeline (heuristisch, unvalidiert):\n\n{facts-als-JSON}`.
  - **Anzeige:** dezente Karten-Sektion „KI-Kommentar" (Lesart + Gegenargument,
    grauer „heuristisch"-Badge, Modellname klein). `concern_level` bewusst als
    **neutraler Text**, NICHT als Ampel-Farbe (das wäre Score-Optik). Fehlt das
    Feld → Sektion fehlt.
  Revert = `scripts/agent_comment.py` + der `try`-Block in `main()` + die 2
  Freeze-Felder in `_new_record` + `agentBlock`/CSS + das `env:`-Secret raus.
