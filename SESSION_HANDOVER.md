# SESSION_HANDOVER — Elliott-Report

**Kanonische, allein tragfähige Projekt-Quelle.** Eine frische Code-Session soll
allein mit diesem Dokument (plus Repo) weiterarbeiten können. Stand: **05.08.2026**,
nach PR #71 (**Kurs-Stand-Wächter**, gemerged `ef0d564`); dieser PR:
**Sammlungs-Schutz bei veraltetem Kurs-Stand** (Variante C, markt-bewusste
Anker), offen. Das **EXZELLENZ-AUDIT P1–P4** ist mit #47 komplett.
Alle Zahlen/Hashes sind gegen `git log` und den Code geprüft, nicht aus dem
Gedächtnis.

> **BRANCH-BASIS:** frisch von `main` (`ef0d564` = #71-Merge) abgezweigt —
> ausdrücklich **nicht** auf den Wächter-Zweig gestapelt (Easys Auflage).

> **FAHRPLAN (Easy, 04.08.2026) — in dieser Reihenfolge, nicht auf Zuruf:**
> 1. ~~**Kurs-Stand-Wächter**~~ — **erledigt**, PR #71 gemerged `ef0d564`.
> 2. **Sammlungs-Schutz, Variante C** (dieser PR) — markt-bewusste Anker (`last_fresh_run_date`
>    je Markt), Gate nur auf die ANLAGE neuer Episoden, `appearance_count` zieht
>    mit, Registry-Eintrag zuerst. Reifung bleibt **ungegated** (belegt: idempotent,
>    rechnet je Lauf aus der Kursreihe neu, Endzustand mit und ohne stale Tag
>    identisch). `skipped_bars` nach **Variante (b)** mitnehmen: setzen wenn > 0,
>    sonst entfernen — Daten-Diff heute leer, während der Einzeiler (a) allen
>    56 Records (Stand 04.08.) ein Feld angehängt hätte. Marker-Replay für die Alt-Records
>    (mindestens KKR), `evaluate.py` byte-identisch, Purge mit Byte-Identitäts-Test.
> 3. **Sitzungs-Ende-PR** — Erwartung des Wächters auf den letzten Handelstag
>    umstellen, dessen Sitzung zur Lauf-Zeit BEENDET ist (markt-eigene
>    Schlusszeiten, ordentliche DST-Behandlung). Beseitigt den Vormittags-
>    Fehlalarm; die **crit→warn-Herabstufung des 04.08.-04:46-Falls** gehört
>    ausdrücklich in den PR-Text.
> 4. **Invalidierungs-Abstand** — gleiches Muster wie der Zonen-Abstand,
>    dieselbe neutrale Farbe (kein Grün/Rot beim Risiko-Wert).
> 5. **Watchlist-Sync-Fix** — Befund vom 04.08.: `_pendingTokenCb` ist ein
>    Slot für EINEN Auftrag und wird von Recalculate überschrieben; Abbrechen
>    löscht ihn ersatzlos; der Grund erscheint nur als flüchtiger Toast, die
>    Badge kennt keinen Grund. Fix muss LAUT werden (persistierter Zustand mit
>    Grund + Zeitpunkt), die Warteschlange statt Slot, Wiederanlauf ohne
>    Listenänderung, Rückwärts-Bremse gegen die 3-Sekunden-Endlosschleife.
> Die stehenden Regeln „Rebase vor Ready-for-Review" **und** „Realdaten-Review nach
> Strukturänderung" (Abschnitt 8) vor dem Ready-Setzen prüfen.

> **PFLEGE-REGEL (nicht verhandelbar):** Dieses Dokument wird bei **JEDEM Merge im
> selben PR** aktualisiert — mindestens Abschnitte **2 (PR-Historie)**, **3
> (Offene Verifikationen)** und **4 (Roadmap)**. Ein PR ohne Handover-Update ist
> **unvollständig**; der Guardian prüft das mit.

---

## 1. PROJEKT-KERN

**Was:** Tägliches **Top-5-Elliott-Wellen-Screening je Markt** (🇺🇸 USA + 🇩🇪
Deutschland) als dunkle GitHub-Pages-**PWA**. Rein regelbasierte Wellen-
Auszählung aus Kursdaten → je Markt die 5 höchstbewerteten **Long**-Setups als
Karten, plus persönliche Watchlist.

**Nordstern:** ein **selbstüberwachendes System** — es sammelt seine eigenen
Vorhersagen forward-only ein, misst sich an einer vorab festgeschriebenen
Erfolgs-Definition und legt seinen Status transparent offen (Methodik /
Validierung / Lauf-Status im Menü).

**Auffanglinie (die rote Linie):** Der Score ist **`heuristisch · unvalidiert`**
bis ein Registry-Beweis vorliegt (Abschnitt 6). Das Tool ist ein
**Attention-Router** (wohin lohnt der Blick), **kein Alpha-Generator**. **Keine
Wahrscheinlichkeits-/Erfolgs-Sprache** irgendwo — nicht im JSON, nicht im UI.

---

## 2. PR-HISTORIE #1–#29

Format: `#N` · Feature-Commit-Hash (auf `main`) · Kern · Merge-Klasse.
Merge-Klassen: **manual** = Easy merged; **+G** = Guardian-Zweitblick vorab;
**+Bild** = Screenshot-Freigabe durch Easy. Guardian-Subagent eingeführt in #6,
durchgängig ab #13.

| PR | Hash | Kern | Merge |
|----|------|------|-------|
| #1 | `f4a8bc6` | Grundgerüst: Pipeline (ZigZag→Regeln→Score→JSON), PWA, `daily.yml`, Tests | manual |
| #2 | `6be7e9f` | Diag: Skip-Gründe instrumentieren (reines Logging) | manual |
| #3 | `fecb148` | **fix:** yfinance-MultiIndex-Spalten normalisieren (99/99-Skip-Bug) | manual |
| #4 | `202c30e` | Long-only: Short-Setups VOR dem Ranking filtern (`short_setup_excluded`) | manual |
| #5 | `906770e` | CI (`ci.yml`, pytest je PR) + Reload-Button | manual |
| #6 | `c4ee0d6` | Guardian-Zweitblick-Subagent (`.claude/agents/guardian.md`) + CI/Guardian-Doku | manual |
| #7 | `2272d0c` | Karten-Redesign im Squeeze-Stil + dunkelgrüne Sparkline | manual +Bild |
| #8 | `670ddc1` | additive Extension-Zielzone `target_zone_extended` (score-neutral) | manual |
| #9 | `c5ba450` | Karten-Header Squeeze (Rang, Name, Sektor, Chart-Link, Kurs+Δ) | manual +Bild |
| #10 | `bd33edf` | Live-Quote-Polling im Karten-Header (Cloudflare-Worker, 15 s) | manual +Bild |
| #11 | `c3eeeba` | Score als Donut in der Kartenmitte + Sparkline mit Pivot-Punkten | manual +Bild |
| #12 | `1c0d555` | großer Wellengrad (Wochen-Count `higher_degree`) + Wellen-Ziffern + Flaggen-Header | manual |
| #13 | `bec83fa` | **Forward-Sammlung** (präregistriert, separat, fail-soft) + `validation_registry.md` | +G manual |
| #14 | `7f67a6f` | Backtesting-Ansicht hinterm Hamburger (Episoden reviewen, eingefrorene Pivots + `price_path`) | +G manual +Bild |
| #15 | `69abd91` | Recalculate-Button (`workflow_dispatch`, Master-PW-AES-GCM-Token) | +G manual +Bild |
| #16 | `f029f73` | Menü-Ausbau: Methodik · Validierung · Lauf-Status (lesend) | +G manual +Bild |
| #17 | `f65f2f8` | persönliche Watchlist (Contents-API-Sync, `report["watchlist"]`) | +G manual +Bild |
| #18 | `f89e4c7` | N×-Zähler (`appearance_count`, Episoden nicht Tage) | +G manual +Bild |
| #19 | `f5e3dac` | Universum 99→361 (statisch) + Listen-Hygiene-Diag (`dead_tickers`) | +G manual |
| #20 | `d40a1d6` | **docs:** `SESSION_HANDOVER.md` (diese Datei) + Pflege-Regel | self (CI grün) |
| #21 | `cf2bd9f` | **fix:** `daily.yml` persistiert `forward_collection.json` (Sammlung akkumuliert, Push race-gehärtet) — **live bestätigt** (10 Records auf main) | manual |
| #22 | `efb57a1` | **Push-Paket Stufe 1** (ntfy, fast stumm): Lauf-Fehlschlag · Staleness-Cron · Meilenstein n≥100 · Review-Wecker | +G manual |
| #23 | `664952f` | **Mini-Sammler:** Disclaimer-Banner (einklappbar) · Wochenend-/Feiertags-Gate · kalenderbewusste Staleness (`market_calendar.py`) | +G manual +Bild |
| #24 | `d217d61` | **Score-Alert >90** (Flanke, nicht Zustand): EINMALIGER Push je Episode beim Neu-Überschreiten, gebündelt (1 Push/Lauf), an die vorhandene Episoden-Logik gekoppelt · `SCORE_ALERT_THRESHOLD=90` · Watchlist ausgenommen · fail-soft | +G manual |
| #25 | `408abe4` | **Watchlist-Sofortkarte** (Frontend): neu hinzugefügter Ticker zeigt sofort Live-Kurs-Karte statt leer/nur Chip; volle Elliott-Analyse weiter aus dem Lauf | manual |
| #26 | `5fb1188` | **Multi-Timeframe-Analyse Watchlist** (PR B): je Watchlist-Titel drei Zählungen `timeframes`{day,week,month}; Monatsgrad (`1mo`, `MIN_BARS_MONTHLY=60`) additiv; Analyse-Panel + Watchlist nach oben; Markt-Top-5 unberührt | +G manual +Bild |
| #27 | `a2d23bb` | **Token-Session-Remember** (Frontend): einmal Master-PW → 28 Tage still (`TOKEN_SESSION_DAYS=28`); IndexedDB-Wrap mit **non-extractable** Session-Key; „Sperren" im ☰; kein Klartext-Token persistiert | +G manual +Bild |
| #28 | `2bed684` | **Validierungs-Integrität (PRU-Guard)**: `mature_record`-Guard sperrt `target_hit`/`ext_hit`, wenn Kurs schon bei Anlage ≥ Zone (`pre_reached_*`); 3 Alt-Records `pre_guard_contaminated` ausgewiesen; Registry-Ausschluss datiert; Badge „Zielzone erreicht/überschritten". Kein Filter/Score-Eingriff, Ranking byte-identisch | +G manual +Bild |
| #29 | `3e59b4e` | **Filter `target_exceeded`** (Produkt): Setups mit `close ≥ target_zone.low` fliegen VOR dem Ranking aus den Markt-Top-5 (Skip-Grund + Diag-Zähler, Rang 6+ rückt nach); Watchlist zeigt weiter alles (Badge). Populations-Änderung datiert; #28-Guard bleibt als zweites Netz — **live: US 15 / DE 6 gefiltert** | +G manual +Bild |
| #30 | `e9727d6` | **Konfluenz-Marker** (Lit-Check a): je Kandidat `confluence`{target,invalidation} — 52W-Hoch / 200d-Linie / runde Zahl innerhalb ±1 % der Zielzone/Invalidierung; Chips (Markt + Watchlist), point-in-time in der Sammlung eingefroren. **Reine Anzeige/Messung, kein Score/Ranking** | +G manual +Bild |
| #31 | `3ad9473` | **W5→A-Nachprüfung** (Lit-Check b): gereifte Ende-W4-Treffer bekommen `a_correction_observed`/`a_retrace_pct`/`a_observe_until` — setzt nach dem Episoden-Hoch die theorie-gemäße Korrektur (≥ 38,2 % Rücklauf der W5-Strecke) binnen `A_OBSERVE_DAYS=10` ein? **Angehängtes** Beobachtungsfenster, bestehende Reifung byte-identisch; `pre_reached`/`pre_guard` ungemessen. **Reines Mess-Feld, kein Score/Ranking/Filter** | +G manual +Bild |
| #32 | `8d2ac29` | **☰-Menü an Squeeze angeglichen**: Struktur/Design des ☰-Panels ans Schwester-Repo angeglichen (abgerundete Icon-Kacheln + Label, großzügige Zeilen, Fuß-Trennung), **eigene Farbwelt** (Sparkline-Grün `--grn` statt Squeeze-Blau). Reihenfolge Squeeze-analog, aber NUR echte Funktionen: **Reload NEU im Menü** (Header-Button „↻ Neu laden" entfällt, gleiche `refresh()`-Funktion + Cache-Buster), Recalculate, Backtesting, Methodik, Validierung, Lauf-Status, Sperren (abgesetzt). Einheitliche inline-SVG-Icons (keine externe Bibliothek). Reines Frontend | self (CI grün) +Bild |
| #33 | `d6bfa1f` | **Watchlist-Kompakt-Grid**: Watchlist-Karten als kompaktes Grid (~3/Reihe @390px), Kacheln standardmäßig eingeklappt (Mini-Donut/„—", Ticker, Trend-Punkt, ×, ▾), volle Karte beim Aufklappen; Zustand pro Gerät (localStorage). Sofortkarte (#25) bleibt. Reines Frontend | self (CI grün) +Bild |
| #34 | `d543303` | **Recalculate-Status mit Zeitzähler** (Squeeze-Muster): nach 204-Dispatch ein Header-Banner „Neuberechnung läuft … N s" (Sekunden live); pollt den **Report-Stand** (frische Baseline vom Server, „fertig" nur bei **strikt neuerem** `run_timestamp_utc`, `RECALC_POLL_MS=10s`) → bei Erfolg **automatisch in-place rendern** (kein Reload) + grünes „fertig" + Toast; Timeout `RECALC_TIMEOUT_MS=10min` → neutraler Hinweis; Feiertag (`MARKET_FULL_CLOSURE`) → sofort-Hinweis; visibilitychange-Pause, getrennte Timer. **Bugfix Baseline-Falle** (`0f14d9a`). Reines Frontend | self (CI grün) +Bild |
| #35 | `ff411c7` | **Watchlist-Mehrwert**: (A) **Top-5-Historie** je Kachel aus `forward_collection` (Datum · Markt · Zählung · Anlage-Kurs · Zielzone · Status, max 3, neueste zuerst; Klick öffnet die bestehende Backtesting-Detail-Ansicht); (B) **Struktur-Befund** je Zeitebene statt binärem „kein Count" — additives Feld `structure` (5 Kategorien), reine Watchlist-Diagnostik, **Markt/Score/Ranking/Sammlung beweisbar unberührt** | +G +Bild manual |
| #36 | `a06f200` | **Struktur-Marke präzisiert + A-Orientierung** (Read-only-Diagnose PANW): additives `mark_label` sagt WAS die Marke ist (`Impuls-Start`/`W1-Hoch`/`W1-Start`); bei `impulse_complete` zusätzlich `orientation_price` = **W4-Extrem** als nahe **A-Ziel-Region**. Reine Watchlist-Anzeige, additiv | +G +Bild manual |
| #37 | `b891efa` | **Watchlist-Auto-Sync**: der manuelle „Für die Pipeline speichern"-Button (#17) entfällt — jede add/remove synct automatisch nach `watchlist_personal.json` (PUT), **Debounce `WL_SYNC_DEBOUNCE_MS=3000`** (EIN Commit), idempotent, gesperrte Session → Dialog + „noch nicht gesynct"-Chip, 409 → sha frisch + 1× Retry. Reines Frontend | +G self (CI grün) +Bild |
| #38 | `e5b04c1` | **3D-Karten-Look + blaue Watchlist-Tönung** (Squeeze „Variante 1B" portiert): Markt-Karten, Watchlist-Kacheln UND aufgeklappte Karten bekommen die einheitliche Tiefen-Sprache (2-Stop-Gradient + Drop-Schatten + **Inset-Kanten-Highlight** + 1px-Licht-Grat, Hover-Lift auf Kacheln); aufgeklappte Watchlist-Karten zusätzlich **dezent blaustichig** (Akzent-Blau). Reines CSS, Kontrast belegt | self (CI grün) +Bild |
| #39 | `7946dad` | **Header-Layout**: Disclaimer-Banner aus dem Kopf entfernt → dezenter statischer **Footer-Disclaimer** am Seitenende (kein Einklappen mehr, `elliott_disc_collapsed`+JS entfallen); **☰ von oben links nach oben RECHTS** (Squeeze-Position, Panel öffnet rechtsbündig `right:12px`), Titel/Stand-Zeile links. Alle Menü-Funktionen unverändert. Reines Frontend | self (CI grün) +Bild |
| #40 | `c5b14ca` | **„Ziel erreicht/überschritten" je Zeitebenen-Zeile**: jede Tag/Woche/Monat-Zeile mit Zielzone (Markt + Watchlist) bekommt einen kompakten `.tf-hint`-Chip — Kurs ≥ `ziel.low` → „Ziel erreicht", ≥ `ziel.high` → „Ziel überschritten" (**Schwellen identisch zum #28-Badge**, `_setTfHint` = Zwilling von `_setZoneBadge`, live via `quotePatch`). Macht sichtbar, dass ältere Zählungen auf großen Zeitebenen (Monats-Pivot-Trägheit) längst gelaufene Ziele zeigen (Live-Fall AMAT: Monat Ziel 296–391 bei Kurs 536). Methodik ergänzt. Reines Frontend | self (CI grün) +Bild |
| #41 | `2320157` | **P1-Audit: A11y-Kontrast + Universum-Hygiene**. (2) Mikro-/Uppercase-Labels von ~3,1–3,7:1 auf **WCAG AA ≥ 4,5:1** gehoben — ein Token `--txt-dim` `#64748b`→`#8b97a8` (4,97–5,90:1 auf allen Flächen inkl. blauer WL-Tönung), bleibt < `--txt-sub` (Hierarchie). (3) **8 tote Ticker** (`empty_data`: US `MMC`/`FI`/`HES`, DE `1COV.DE`/`CTS.DE`/`UN01.DE`/`SHA.DE`/`COP.DE`) aus `config.py` + `ticker_meta.json` entfernt (**361→353**), Registry-Log ergänzt. Folge-Lauf belegt `empty_data → 0`. Audit-Punkt 1 via #40 schon auf main → übersprungen | Guardian + manual +Bild |
| #42 | `e9101d3` | **P2-Audit: Messfelder v1** (Volumen-Profil, Alternation, W5-Momentum-Divergenz) — drei literaturgestützte MESS-Felder point-in-time in die Forward-Sammlung eingefroren. **Reine Messung: Score/Ranking/Filter/Population/Reifung byte-identisch** (Report-Diff nur additive `vol_*`-Keys). Volumen aus DEMSELBEN yfinance-Download (`FetchOutcome.volumes`, kein Extra-Call). Einziges UI: Chip „W3-Volumen schwach". 17 neue Tests | Guardian + manual, keine Screenshots |
| #43 | `c41658f` | **P3-Audit: Ambiguitäts-Ausweis v1** — je Zählung `valid_count_total` (1..2, Long-Counts unter den 2 festen Fenstern Ende-W4/Ende-W2) + `alt_count` (zweitbeste nach `score_setup`); `ambiguity_n` bei Anlage eingefroren. `classify_setup` in 2 Fenster-Helfer refaktoriert (**Primär byte-identisch**). **Score/Ranking/Filter/Reifung byte-identisch**, `SCHEMA_VERSION`=1. UI: „Zählung 1 von N" (max „1 von 2") + aufklappbare Alternative. Registry „Ambiguität v1". Live: US 2×N2 / DE 1×N2. 8 Tests | Guardian + manual |
| #44 | `efa3f87` | **Textgrößen-Steuerung** (Squeeze-Vorbild `app.html:3511`): − / + im ☰-Menü-Fuß skalieren die **ganze rem-basierte UI** über `--app-fs`. 5 Stufen `[14,16,18,20,22]`px (Default 16px = unveränderte Optik), Persistenz, Grenzen. Alle CSS-`font-size:px`→`rem` (SVG-Text bleibt px). Reines Frontend | self (CI grün) |
| #45 | `6f6d98c` | **P4a-Audit: ABC-Korrektur-Erkennung** (Struktur-Vokabular v2): `_detect_correction` (strikte Ungleichungen, longest-first) → 2 neue `structure_state` (`correction_running`/`complete`, **Präzedenz vor Impuls-Lesarten**); `valid_count_total_v2`/`alt_count_v2` (Anzeige nutzt v2); `ambiguity_n_v2` zusätzlich eingefroren (v1 unverändert); W5→A strukturell (`a_structure_observed`/`c_target_pct`, fenstergebunden nach Guardian-Nit). **Markt byte-identisch**, kein neuer Setup-Typ. Live: 3 Korrektur-Lesarten (PANW/AMAT Monat, IONQ Tag short-symm.), v2-Gewinne CVS/SPG/ADS.DE. 18 Tests (245) | Guardian (Nits, behoben) + manual |
| #46 | `29d1e1e` | **P4b-Audit: Grad-Sparklines** — `_count_from_series` liefert additiv `chart_points` (letzte `DEGREE_CHART_PIVOTS=8` ZigZag-Pivots) + `count_wave_labels`; `degreeSpark()` reust `drawSparkline` (`data-h=36`), Minis im Großer-Grad-Block + je Zeitebenen-Zeile mit Count, direkt sichtbar. Report-Diff nur additive Keys. **Live: 4 Sparklines (US 2 hd, AMAT Tag+Monat), Payload real +6,6 KB**, Ziffern-Stichproben AMAT [Monat]/VRTX [Woche] korrekt | Guardian (OK) + manual |
| #47 | `0ac6d92` | **P4c-Audit: Sparkline-Achsen** (LETZTER Audit-Punkt → **P1–P4 komplett**): dezente Eck-Werte an der GROSSEN Tages-Sparkline — Hoch-/Tief-Preis + Zeitspanne (`TT.MM.JJ`), `.spark-axis` 7px SVG-px, `--txt-dim` (AA), Halo (`paint-order`), Kollisions-Nudge gegen Wellen-Ziffern; **Minis bewusst ohne**; keine Gitter/Striche. Verifiziert am echten AMAT (723 / 322,72 / 25.02.26–07.07.26), 0 Kollisionen | self (CI grün) |
| #48 | `90577a7` | **Elliott-Wellen-Banner + Chip-Zeile entfernt**: (1) freigegebenes SVG (v3) **inline** unter der Stand-Zeile / über der Watchlist — dekorativ (`aria-hidden`), responsive über viewBox; alle 6 ids mit **`ewb-`-Präfix** (Kollisionsschutz, headless auf doppelte ids geprüft). (2) **Chip-Zeile `#wl-chips` entfernt** (doppelt zu den Kacheln), ersetzt durch `renderWatchlistCount`; Empty-State in der Kachel-Fläche. Watchlist-Flows headless durchgespielt | self (CI grün) |
| #49 | `48665a4` | **Agent-Kommentar v1** (KI-Entscheidung Easy 26.07.): nächtlich EIN Anthropic-Aufruf je **finaler Markt-Top-5**-Karte (~10/Lauf, Watchlist ausgenommen) → `agent_comment {lesart, gegenargument, concern_level, model, generated_at}` \| null. **REINE Kommentar-Ebene:** Schritt läuft NACH `build_report` (nach Sortierung/Filtern), Score/Ranking/Filter/Reifung byte-identisch (Test). **Fail-soft total:** ohne `ANTHROPIC_API_KEY` no-op, API-/Parse-Fehler → null (1 Retry), Key nie geloggt; Token-Kosten-Log. **Messung:** `agent_concern_level`+`agent_model` bei Anlage eingefroren (LLM nicht deterministisch). Registry datiert **inkl. wörtlichem Prompt**. UI: dezente „KI-Kommentar"-Sektion, concern_level als **neutraler Text** (keine Ampel). **Live: 10/10 Kommentare, 7×high/3×low, real ~$0,011/Lauf ≈ $2,66/Jahr.** 19 neue Tests (264) | Guardian (Nits, behoben) + manual |
| #50 | `4c7b7d4` | **KI-Kommentar standardmäßig eingeklappt**: `agentBlock` rendert die Sektion als **`<details>` ohne `open`** — `<summary>` trägt kompakt „KI-Kommentar · heuristisch" + Chevron; Lesart/Gegenargument/Modell erst nach aktivem Öffnen. Squeeze-Muster: Chevron-Rotation per CSS über `[open]`, **kein animiertes height → kein Layout-Sprung**, `prefers-reduced-motion`-tolerant, Tap-Ziel `min-height:44px`. Zustand je Karte unabhängig, **keine Persistenz** über Reload. null-Fall unverändert: **gar keine Sektion**. Headless am ECHTEN Lauf belegt | self (CI grün), keine Screenshots |
| #51 | `85589a5` | **Health-Check Stufe 2 — Plausibilitäts-Regeln mit Push**: sechs Regeln am Lauf-Ende (`scripts/health_check.py`), gebündelt in EINEN flankengetriggerten ntfy-Push. Kern: **Nicht-finit-Prüfung** (`math.isfinite`, rekursiv über Report **und** Sammlung, **vor** beiden Serialisierungen) — Lehre aus dem Schwester-Repo (NaN passiert `is not None`). Elliotts Schadensbild ist ein **hartes Frontend-Aus** (literales `NaN` = ungültiges JSON, `JSON.parse` wirft), empirisch belegt. Dazu Vollständigkeit / Fetch-Qualität + Tote-Ticker-Delta / Sammlungs-Fortschritt (#21-Netz) / Agent-Abdeckung. Flanke: neu oder verschlechtert → Push, unverändert still, `warn` erst nach 3 Läufen erneut, Marker `data/health_state.json`, Wochenend-/Feiertags-Gate. **Transparenz** ohne Push: additiver Block `report["health"]` in der Lauf-Status-Ansicht. **Grenzen bewiesen:** ändert nie Daten, bricht den Lauf nie ab, Report identisch bis auf den `health`-Schlüssel. **Regeln über die letzten 15 committeten Reports zurückgespielt: 0 Fehlalarme.** 48 neue Tests (312) | Guardian + manual, keine Screenshots |
| #52 | `79375fb` | **NTFY_TOPIC-Verdrahtung**: das Secret war gesetzt und stellte real zu, aber der Step **Run pipeline** in `daily.yml` reichte es nicht durch (Actions vererbt Secrets NICHT in Steps) — beide Push-Zweige INNERHALB der Pipeline waren still: **Score-Alert >90 (#24) seit seinem Bau** und Health-Check (#51) von Anfang an; fail-soft, also ohne jede Fehlermeldung. Fix: eine Zeile (derselbe Name, dasselbe Mapping) + **Bestätigungs-Push** (`notify.py --mode selftest`, nur über den Dispatch-Schalter `push_selftest`, mit Secret-Diagnose ohne Leak) + Commit-Schritt nur auf `main` (ein Dispatch vom Feature-Branch färbte den Lauf sonst rot) + Regressionsnetz `tests/test_workflow_push_wiring.py`. **Live bestätigt:** Secret gesetzt (Länge 25) und `Push gesendet: Elliott: Push-Verdrahtung ok` | self (CI grün) |
| #53 | `87ed590` | **Nicht-finit-Härtung (Ursachen-Fix zu #51)**: EIN Prädikat `scripts/numeric.finite` für alle Zahlen-Guards. **Berichtigung 29.07.:** hier stand „geteilt mit `health_check`“ — das stimmte nicht, `health_check` trug bis zum Hygiene-PR eine eigene, wortgleiche Fassung. Seither ist es wirklich EINE Implementierung. **Quelle:** `_extract_bars` filtert Bars ohne endlichen Close in EINEM ausgerichteten Durchgang — dabei fielen zwei stille Quell-Defekte auf: `dropna` schnitt die Datumsliste nur vorne ab (**eine Lücke in der Mitte verschob jedes Datum danach** — Pivot-Daten, `chart_points`, Sparkline-Achsen, eingefrorene Pivots) und die Volumen kamen aus dem **ungefilterten** Frame. **Reifung:** Fehlbar ist kein Treffer-Nein — er wird übersprungen und als `skipped_bars` ausgewiesen, gereift wird über 10 **gültige** Bars (kein ewig offener Record). **Messfelder** werden `null` statt still weiterzurechnen. **Population belegt unverändert:** ALT vs. NEU über 25 Sammlungs-Stände / 341 Reifungs-Läufe → **0 Abweichungen**. Registry datiert. 45 neue Tests (364) | Guardian (OK, Nit eingearbeitet) + manual, keine Screenshots |
| #54 | `7393971` | **Heartbeat-Push**: nach jedem ERFOLGREICHEN Werktags-Lauf auf `main` genau EIN leiser Push (`Elliott: Lauf ok`, prio `low`) mit echten Zahlen — Kandidaten je Markt, Top-Ticker + Score, Sammlung (gesammelt/gereift/auswertbar), plus Meilenstein-Hinweis beim Überschreiten eines Vielfachen von `HEARTBEAT_MILESTONE_STEP` (25). **Zweck ist der HERZSCHLAG, nicht das Lob:** bleibt der Puls aus, ist der Lauf ausgefallen — unabhängig vom Staleness-Wächter, der selbst am GitHub-Scheduler hängt (am 27.07. fiel der Werktags-Cron aus, ohne dass etwas meldete). **HARTE REGEL: nie zwei Pushes pro Lauf** — jeder Befund, auch ein reines `warn`, ersetzt den Herzschlag; auch ein still gewordener Dauer-Befund lässt ihn NICHT einspringen. Gates: Wochenende/Feiertag (bestehend) und **nur `main`** (`GITHUB_REF`), damit ein Test-Dispatch vom Branch keinen Puls erfindet. `HEARTBEAT_ENABLED` / `HEARTBEAT_FREQUENCY` (daily|weekly) als benannte Konstanten. Ohne Secret sauberer no-op. 26 neue Tests (390) | Guardian (OK, Nit eingearbeitet) + manual, keine Screenshots |
| #55 | `ba457cd` | **Validierungs-Seite in Klartext**: Die Ansicht war das komplette Register als Fließtext — fachlich korrekt, am Handy unbrauchbar. Jetzt oben **drei große Zahlen** (gesammelt / fertig beobachtet / auswertbar), **zwei Sätze** (was beobachtet wird, ab wann ausgewertet wird), ein **Fortschrittsbalken** statt Prozent-Rechnerei, der Stempel `heuristisch · unvalidiert`. Alles Fachliche inklusive des vollständigen Registers steckt zugeklappt in **Details für Nerds** (`<details>`-Muster wie beim KI-Kommentar, Tap-Ziel 44 px). Der Ausschluss-Hinweis erscheint nur, wenn es Ausschlüsse gibt — in Alltagssprache statt `pre_guard_contaminated`. **Nichts weggefallen, nur umsortiert.** Verifiziert @390 px: sichtbarer Teil endet bei 291 px (Panel 365 px) → kein Scrollen; **null Fachbegriffe** im sichtbaren Teil (Liste geprüft); Zahlen gegen die echten Daten gegengerechnet (32/0/0) **und** gegen einen befüllten Fall (60/45/40, Balken 40 %, 5 Ausschlüsse). Reines Frontend | self (CI grün) |
| #56 | `5cd59f7` | **Methodik: doppelte Konfluenz-Erklärung entfernt**: „Konfluenz" stand zweimal auf der Methodik-Seite — einmal als **Legenden-Zeile** (kompakt, technisch: „±1 % … 52W-Hoch, 200-Tage-Linie, runde Zahl … kein Score-Einfluss") und einmal als **eigener Abschnitt „Konfluenz-Marken"**. **Bleibt: der Abschnitt** — er ist der verständlichere und der einzige, der das **Warum** trägt (Crowd-Marken wirken über Aufmerksamkeit, nicht über Ratio-Magie) und den fehlenden Score-Einfluss begründet. **Weicht: die Legenden-Zeile**, gekürzt auf einen Halbsatz mit Verweis — neuer Wortlaut: „Chips an Zielzone/Invalidierung, wenn dort eine breit beachtete Marke liegt — ausführlich unten unter **Konfluenz-Marken**." (119 statt 217 Zeichen). Eine Zeile geändert, sonst nichts; die 11 übrigen Legenden-Zeilen und der Abschnitt selbst sind unberührt. Verifiziert @390 px: kein Querscrollen, keine JS-Fehler, Verweis-Ziel existiert, „kein Score-Einfluss" weiterhin im Text. Reines Frontend/Text | self (CI grün), keine Screenshots |
| #57 | `89c5602` | **Zählweise vereinheitlicht + Klartext auf der Methodik-Seite**: (1) **Fehlerkorrektur** — `notify.run_daily` zählte für den Meilenstein-Push `gereift`, Registry und Frontend beziehen `n≥100` seit dem PRU-Guard (23.07.) aber auf **auswertbar** (gereift UND nicht ausgeschlossen). Der Push wäre also **zu früh** gekommen — und der Einmal-Marker hätte ihn danach **für immer** verbraucht. `_matured_count` → `_evaluable_count`, das ausschließlich über `forward_collection.eval_counts(...)[2]` zählt (kein zweiter Zähl-Pfad, der wegdriften kann); ohne `forward_collection` **0 statt Ersatzzählung** (verpasster Meilenstein ist harmlos, zu früher nicht). Push-Text, Marker-Text und Log sagen jetzt „auswertbar". **Keine Definitions-Änderung → keine Registry-Notiz**, die Registry war schon die Referenz. Regressionsnetz: 4 Tests, per Mutationsprobe belegt (alte Zählung eingesetzt → 3 davon rot). (2) **Sprache**: „self-fulfilling" und „Ratio-Magie" im Abschnitt *Konfluenz-Marken* durch Alltagssprache ersetzt — „Solche Level wirken, weil **viele Händler auf diese Marke schauen** und dort handeln — nicht, weil an der Zahl selbst etwas Besonderes wäre." Sinn unverändert (Wirkung über Aufmerksamkeit, nicht über die Zahl), „kein Score-Einfluss" bleibt. 394 Tests | Guardian + manual, keine Screenshots |
| #58 | `89c5602` | **Auswertungs-Programm v1** (`scripts/evaluate.py`): das Register in Code — **blind gebaut bei 0 gereiften Fällen**, damit die Auswertung nicht später an den Ergebnissen entlang gebogen wird. Eigenes Kommando, **nie im Tageslauf**, kein Push, schreibt nur seine Ergebnis-Datei. Population = `is_excluded` + Prüfung gegen `eval_counts[2]` (Drift ⇒ Abbruch); nur eingefrorene Felder (`FROZEN_FIELDS`, per Zugriffs-Protokoll bewiesen). Sperre unter n<100: nur `--vorschau`, alles als NICHT GÜLTIG gestempelt. Primär: Trefferquote gegen Zufalls-Benchmark (gleicher Ticker, zufälliger Tag, gleiche relative Abstände, gleicher Horizont, gleiche Treffer-Definition) + AUC mit Bootstrap-Intervall, **Holm** über beide. Sekundär explorativ mit Mindest-Fallzahl 30 („zu wenige Fälle" statt Zahl). Ausgabe zweiteilig: Klartext ohne Fachbegriffe + Zahlenanhang. **Vier Selbsttests mit bekannter Antwort** (Rauschen ⇒ kein Signal · starker Zusammenhang ⇒ erkannt · Punktzahl verkehrt ⇒ Untergrenze < 0,5 · Grenzfall 99/100) — sie fanden einen echten Fehler: eine selbstgeschriebene binäre Suche lieferte still AUC 0,5. **Guardian fuhr eine eigene Mutationsprobe** und fand zwei Testlücken (Sperre auf `gereift` statt `auswertbar`; der Gleichstands-Test prüfte in Wahrheit zwei aufeinanderfolgende Tage) — beide mit echten Regressionstests geschlossen und per Mutation belegt. 32 neue Tests (426) | Guardian (Nits eingearbeitet) + manual, keine Screenshots |
| #59 | `3112f42` | **Code-Hygiene: EINE ZÄHL-QUELLE**: die Aggregate (gesammelt/gereift/auswertbar/Schwelle) stehen ab jetzt als additiver Block `report["validation"]` im Report, befüllt über `eval_counts`. Das Frontend rechnete sie in **JavaScript nach** (`_evalCounts` + hartkodiertes `EVAL_MIN_N = 100`) — dieselbe Registry-Regel in zwei Sprachen, genau die Klasse, an der `notify.py` in #57 auseinandergelaufen ist. **`_recExcluded` bleibt** (wird JE FALL gebraucht: Episoden-Status, W5→A-Filter), aber ein Test hält seine Feldliste mit `is_excluded` deckungsgleich. Dazu: **ein Finit-Prädikat** (`health_check._finite` → `numeric.finite`; Gleichheits-Test über 26 Eingaben **vor** dem Ersetzen, Test-Doppelung aufgelöst, falsche Handover-Aussage berichtigt), `evaluate._is_end_of_w4` per Import statt Nachbau (Gruppen-Gleichheit getestet, **keine** Definitionsänderung), Streichliste mit Einzelbeleg (`zigzag.pivot_prices`, `forward_collection.counts`, CSS `.score-mini`/`.card-foot`, `notify.REPORT_PATH` und die zwei hartkodierten Vorbehalts-Strings auf `config`). **Neu statt Umbau:** ein Test hält die Zahlen im Methodik-Fließtext an `config.py` (Basispunkte, Fibonacci, Toleranz, Kappung, Maximum, Konfluenz ±1 %, 200-Tage-Linie, Horizont) — der Text bleibt handgeschrieben, kann aber nicht mehr still veralten. **Belege:** Zähler an allen drei Anzeigestellen vor/nach **identisch** (headless, echter Stand), Report-Diff ALT/NEU über einen vollen Lauf → nur der `validation`-Block kommt hinzu, Sammlung unverändert. **Guardian-Nit eingearbeitet:** mein Pipeline-Test prüfte nur Quelltext-Nähe — die Mutation `evaluable` → `matured` im Block blieb grün, also exakt die #57-Klasse. Jetzt ein **Laufzeit-Test**, der `main()` wirklich ausführt und `eval_counts` drei **unterscheidbare** Zahlen (7/5/2) liefern lässt; jede Vertauschung im Block wird rot (nachgestellt). 49 neue Tests (474) | Guardian (Nit eingearbeitet) + manual, keine Screenshots |
| #60 | `5c6feae` | **Abruf-Robustheit + Ehrlichkeit der Ausgabe** (Folge des **Trockenlaufs** an der echten Sammlung, 29.07.): (1) `--kurse-holen` **scheitert jetzt sichtbar** — yfinance meldet einen Fehlschlag als **leeren DataFrame**, nicht als Ausnahme; der landete als Schein-Eintrag mit 0 Bars in der Datei, das Log meldete Erfolg, der Rückgabewert war 0. Jetzt: keine Schein-Einträge, `ticker_ohne_kurse` namentlich, Zusammenfassung im Log, **Rückgabewert 3** sobald ein Ticker fehlt; zusätzlich verworfen wird ein Datum/Kurs-**Versatz** (der #53-Defekt). (2) **Jede** der 10 Sekundär-Dimensionen erscheint, auch leere (`hinweis: "keine Fälle"`) — im Trockenlauf fehlte `momentum_divergenz` ersatzlos, weil das Feld überall `null` war. Liste fest in `SECONDARY_DIMS`. (3) `ausgeschlossen_gruende` sind **Nennungen**, nicht Fälle (13 Nennungen für 5 Fälle im Trockenlauf) — neuer Hinweis-Text mit der Fallzahl. **„Auswertung v1" inhaltlich unberührt, belegt:** an vollständigen Kunstdaten sind `primaer`, `holm`, `urteil`, `fazit_klartext`, `reproduzierbarkeit` und `definitionen` **identisch** vor/nach. Registry-Klarstellung datiert, inkl. der offenen Frage zur **zeitlichen Überlappung** der Zufallsziehungen (wird vor der echten Auswertung an Kunstdaten geprüft). 7 neue Tests (481) | Guardian + manual, keine Screenshots |
| #61 | `16a4c90` | **Trade-Journal** — eigener Menüpunkt „Journal", angebunden an Markt- und Watchlist-Karten. **STRIKT GETRENNT von der Validierung:** die Pipeline liest `data/trade_journal.json` **nie** (Test greppt alle Backend-Module und Workflows); ein Lauf **mit** vorhandener Journal-Datei erzeugt Report und Sammlung **byte-identisch** wie einer ohne. **KEINE Beträge, keine Stückzahlen** — weder Eingabe noch Speicherung (Repo ist öffentlich); Feldliste im Test ausgeschrieben, Formular hat genau drei Eingaben (Ausstiegsdatum/-kurs, Notiz). Ergebnis in Prozent wird **berechnet**. Je Eintrag beim Anlegen **eingefroren**: Setup, Score, Zielzone, Invalidierung, Report-Stand. **Sync wiederverwendet, nicht nachgebaut:** der GitHub-PUT ist aus der Watchlist zu `_ghPutFile` herausgelöst — der 409/422-Retry steht jetzt **genau einmal** im Frontend (Test), Watchlist und Journal nutzen ihn beide; Debounce 3 s, zwei Ablagen (`data/` + `docs/`-Spiegel). Gesperrte Session → Eintrag bleibt lokal und synct beim nächsten Entsperren. Headless @390 px komplett durchgeklickt: 10 Markt- + 5 Watchlist-Knöpfe (Tap 44 px), Übernahme → Toast, Ausstieg eintragen → **+10,00 %** exakt gerechnet, Status/Übersicht aktualisiert, Neuladen übersteht, Löschen → Leer-Text, kein Querscrollen, keine Konsolenfehler. Sync-Pfad separat belegt: 409 → sha-Refresh → **genau ein** Retry, beide Pfade geschrieben. **Revert =** `tests/test_trade_journal.py` + beide `trade_journal.json` + der `tj-`-Block (CSS, Overlay, Menüpunkt, JS, `tjAddBtn`, die drei Verdrahtungszeilen) raus; `_ghPutFile` kann bleiben (die Watchlist nutzt es) oder wird in `_wlDoPut` zurückgefaltet — kein Datenstand wird ungültig, `report.json` und Sammlung sind nie beteiligt. 13 neue Tests (496) | Guardian (Nits eingearbeitet) + manual, keine Screenshots |
| #62 | `24cd0f9` | **Drei Kleinigkeiten**: (1) **Journal schreibt genau EINEN Commit** pro Änderung. Die kanonische Kopie `data/trade_journal.json` ist **entfernt** — sie hatte keinen Leser; per Netzwerk-Mitschnitt belegt, dass die Seite genau einen Pfad abfragt (`data/trade_journal.json` relativ zu /docs = der docs-Spiegel, HTTP 200; der Fallback wurde nie angefragt). (2) **Kurs-Abruf dispatchbar**: neuer Workflow `eval_prices.yml`, **nur** `workflow_dispatch`, `contents: read`, kein Commit-Schritt, **kein** `continue-on-error` — der Rückgabewert 3 aus #60 färbt den Lauf **rot**, sobald ein Ticker ohne Kurse zurückkommt. Ergebnis nur als **Artefakt** (30 Tage), nie committet; ein eigener Schritt beweist, dass keine Repo-Datei angefasst wurde. Der Test „nie im Tageslauf" wurde **präzisiert statt aufgeweicht**: ein Workflow, der `evaluate` nennt, muss dispatch-only sein, darf nichts committen und kein `continue-on-error` tragen (Kommentare werden dabei ausgeblendet — mein eigener Kommentar „KEIN continue-on-error" hatte den Test genarrt). (3) **Bar-Diagnose mit Datum und Position**: je Ticker `dropped_dates` (gekappt auf `MAX_DROPPED_DATES = 5`) + `dropped_last_row`/`dropped_mid_row`, je Markt das Histogramm `dropped_bar_dates`. Im Lauf-Status als Zusatzzeile: **ein** Datum mit der Anzahl betroffener Ticker = unfertige Tages-Zeile, verstreute Daten oder „mitten in der Reihe" = echte Lücke. Genau diese Unterscheidung fehlte beim DE-Lauf vom 29.07. **Belege:** Report-Diff ALT/NEU über einen vollen Lauf → **genau die 6 neuen Diag-Felder** (3 je Markt), sonst nichts; Sammlung gleiche MD5; Journal-Durchklick @390 px → **1 PUT pro Änderung**, Anzeige/Übersicht/Hinweis vollständig, keine Konsolenfehler. **Revert =** `eval_prices.yml` löschen, die Diag-Felder + `MAX_DROPPED_DATES` + die `dropped_*`-Rückgaben aus `_extract_bars`/`FetchOutcome` zurücknehmen, `TJ_GH_PATH` wieder auf zwei Pfade und `data/trade_journal.json` (`[]`) neu anlegen; kein Datenstand wird ungültig. **Guardian-Nit eingearbeitet:** die Diagnose selbst war von keinem Test mit tatsächlich verworfenen Zeilen gedeckt — Mutation „`dropped_mid`-Zweig entfernt" blieb **grün**, obwohl genau diese Unterscheidung der Zweck der Änderung ist. Jetzt vier Tests (Mitte + letzte Zeile getrennt erkannt, Daten korrekt, gesunde Reihe still, Markt-Histogramm und `MAX_DROPPED_DATES`-Kappung am vollen Report); beide Mutationen nachgestellt → rot. 5 neue Tests (501) | Guardian (Nit eingearbeitet) + manual, keine Screenshots |
| #63 | `8380f88` | **Abruf-Endlichkeit + `last_bar_date` + Registry-Notiz zum Ein-Tag-Versatz** (Folge der read-only-Klärung vom 30.07.): (1) **`evaluate.fetch_prices` prüft die Kurse jetzt auf Endlichkeit** — bisher landete ein `NaN` als literales `NaN` in der Kursbasis-Datei: **ungültiges JSON**, das Python still zurückliest und `JSON.parse` verwirft; der Lauf meldete GRÜN. Jetzt werden nicht-endliche Schlusskurse **mit dem passenden Datum** verworfen (EIN ausgerichteter Durchgang, die #53-Lehre), betroffene Ticker stehen namentlich in `ticker_mit_luecken`, das Log fasst zusammen, und der Modus endet mit **Rückgabewert 3** — der dispatchbare Workflow aus #62 färbt damit **rot**. **Nebenbefund, den ein bestehender Test fing:** der Versatz-Guard aus #60 war **wirkungslos** — er verglich die Längen **nach** `zip`, und `zip` schneidet eine Ungleichheit still ab. Der Vergleich steht jetzt auf den **ROH-Längen vor** dem `zip`, die spätere unerreichbare Prüfung ist entfallen. (2) **`markets[].last_bar_date` additiv im Report**, im Lauf-Status als Zeile „**Kurse vom** <Datum>" **vor** der Bars-Zeile — sie steht **immer** da, nicht nur im Problemfall (eine Angabe, die nur bei Auffälligkeiten erscheint, wird beim Lesen leicht für „alles normal" genommen). Vorher war der Kursstand nur aus `price_path` rekonstruierbar. (3) **Registry datiert (30.07.): der Ein-Tag-Versatz als bekannte Eigenschaft** — je Lauf kann der letzte Handelstag zwischen den Märkten abweichen, abhängig vom **Abrufzeitpunkt**; er wirkt über `closes[-1]` auf **Score** (Invalidierungs-Distanz-Bonus, bis +15), **`target_exceeded`-Filter**, **Anzeige** und `entry_close`/`first_seen_date`; **innerhalb** eines Marktes konsistent, **zwischen** den Märkten nicht. Kein fester Versatz (ein Lauf um 18:14 UTC legte `ADS.DE` mit `first_seen_date = 2026-07-29` an, während der Lauf um 03:55 UTC genau diese Zeile verworfen hatte). **Bewusst NICHT geändert:** Abrufzeit und Abschneiden der letzten Zeile — beides würde die Population verschieben. **Belege:** Report-Diff ALT/NEU über einen vollen Lauf → **genau 2 Abweichungen**, beide `markets.{DE,US}.diag.last_bar_date` (neu), sonst **nichts** — Score, Ranking, Filter, Reifung und Sammlung unberührt (Sammlung gleiche MD5). Neuer Test schreibt eine Reihe mit zwei `NaN`, prüft die Datei mit `json.loads(..., parse_constant=…)` auf **gültiges** JSON (kein `NaN`/`Infinity` im Rohtext), den namentlichen Ticker, 38 **ausgerichtete** Kurse und Rückgabewert ≠ 0. Frontend headless @390 px in vier Ständen: mit Datum (beide Märkte, Werte `2026-07-29`/`2026-07-28`, Zeile vor der Bars-Zeile), `null`, Feld fehlt (**legacy tolerant**, keine Zeile) und Injektions-Probe (`<img …>` erscheint als Text, **0** img-Knoten) — kein Querscrollen, keine Konsolenfehler. **Revert =** die Endlichkeitsprüfung in `fetch_prices` + `ticker_mit_luecken` zurücknehmen (der Roh-Längen-Vergleich sollte bleiben — er ist der reparierte #60-Guard), `last_bar_date` aus `_scan_market`/Report und `barDateRow` aus `docs/index.html` entfernen; die Registry-Notiz bleibt gültig, kein Datenstand wird ungültig. **Guardian-Nit eingearbeitet:** der Wert von `last_bar_date` war von keinem Test gedeckt — nur seine Anwesenheit im Diag-Vertrag (`test_schema.py`). Die Mutation `dates[0]` statt `dates[-1]` — ein stiller Vertausch von ERSTEM und LETZTEM Handelstag — blieb über alle 502 Tests **grün**; dieselbe Klasse wie der #59-Nit (Quelltext-Nähe statt Laufzeit). Jetzt `tests/test_last_bar_date.py` mit fünf Tests: jüngster Tag im Markt bei **gegenläufig** geordneten Anfangs- und Enddaten, Ticker **ohne** Kandidat zählt mit (der Kursstand hängt an den Daten, nicht an der Kandidatur), `None` wenn kein Ticker Kurse liefert, das letzte **gültige** Bar bei verworfenen Zeilen (kein Vordatieren), und der unveränderte Durchlauf bis in `markets[].diag`. Vier Mutationen nachgestellt → `dates[0]` **4 rot**, `>`→`<` **3 rot**, Update entfernt **4 rot**, Update erst nach `build_candidate` **1 rot**. **Offener Nit (nicht dieser PR):** `evaluate.fetch_prices` normalisiert keine MultiIndex-Spalten wie `parse_download_df` — es trägt heute nur, weil je Ticker genau eine Close-Spalte kommt und `.to_numpy().ravel()` sie flach macht. Vorbestehend, durch diesen Diff nicht verschlimmert; Kandidat für einen Folge-PR. 5 neue Tests (507) | Guardian (Nit eingearbeitet) + manual, keine Screenshots |
| #64 | `e0feedd` | **Kursspalten im Abruf absichern** (der offene Nit aus #63, erledigt): `evaluate.fetch_prices` bringt die Spalten jetzt **zuerst auf die Normalform der Pipeline** — `from elliott_pipeline import _normalize_columns`, **dieselbe Funktion, kein Nachbau** (ein Test verbietet `get_level_values` in `evaluate.py`; Mutation „nachgebaut statt importiert" → rot). Der Import steht **lokal in der Funktion** wie `yfinance`: der AUSWERTUNGS-Modus bleibt damit frei von der Pipeline, die ihrerseits `notify` zieht — die Auswertung darf nie in die Nähe eines Pushes kommen. Danach prüft `_close_spalte`, dass genau **eine** Close-Spalte übrig ist (`ndim == 1`); jede andere Form ist ein **Grund** und macht den Ticker **namentlich** „ohne Kurse" (`mehrdeutige Close-Spalte: shape=…`), Rückgabewert unverändert ≠ 0. `ravel()` ist **weg** — ein Flachmacher, der nie greifen darf, ist nur eine stille Falle. **BERICHTIGUNG zum Nit-Text aus #63:** dort stand, mehrere Spalten würden „still verformt". Das war zu scharf. Nachgemessen an `origin/main`: zwei Close-Spalten landeten **schon** als „ohne Kurse", weil der Roh-Längen-Guard aus #63 greift (8 Kurse gegen 4 Daten) — bei einem echten DataFrame ist die Spaltenzahl k≥2 immer ein Längenversatz, also war **keine stille Verformung erreichbar**. Was wirklich fehlte: (a) der GRUND war irreführend (Längenversatz statt Spaltenform), (b) der MultiIndex-Einzelticker-Fall trug nur über eine **zufällige** Eigenschaft von `ravel()` (ein Block mit einer Spalte wird korrekt flach), nicht über die Normalform. Das ist eine Klarheits- und Explizitheits-Härtung, **kein Bugfix** — so steht es auch im PR-Text. **Belege:** 4 neue Tests — mehrspaltige Antwort (Vorbedingung ausgeschrieben: der ALTE Ausdruck hätte `[10, 90, 11, 91, …]` verschränkt) → leere `kurse`, Ticker namentlich, die verschränkten Zahlen stehen **nirgends** in der Datei; derselbe Fall über `main()` → rc ≠ 0 **und** der richtige Grund im Log (der Rückgabewert allein belegt nichts, s. o. — die #63-Lehre); Normalfall **bit für bit wie vorher**, gegengerechnet mit dem ALTEN Ausdruck an denselben Beispieldaten in **beiden** realen Formen (flach und MultiIndex); eine Normalform-Quelle. **Auswertung unverändert:** an vollständigen Kunstdaten (150 Records, 2000 Ziehungen) sind `primaer`, `holm`, `urteil`, `fazit_klartext`, `reproduzierbarkeit`, `definitionen`, `sekundaer_explorativ`, `population` und `ausgeschlossen_gruende` **identisch** vor/nach. **Mutationsproben:** ndim-Guard weg + `ravel()` zurück → **2 rot**, Normalisierung weggelassen → **3 rot**, Normalform nachgebaut → **1 rot**. **Revert =** `_close_spalte` löschen und die eine Zeile `df["Close"].to_numpy().ravel().tolist()` zurücksetzen; kein Datenstand wird ungültig, die Auswertungs-Definition war nie berührt. **Guardian-Nits eingearbeitet:** (1) die Code-Begründung für den lokalen Import war stärker als die Sache — `notify` importiert `requests` selbst erst im Sendepfad, ein Modul-Import könnte also gar nichts senden; der Kommentar sagt jetzt ausdrücklich „Stil-Entscheidung, KEINE Sicherheitsmaßnahme". Der Guardian hat auch bestätigt, dass **kein Test** diese Import-Richtung erzwingt (nur die Gegenrichtung, `tests/test_evaluate.py:553`). (2) Der Satz „dieselbe Funktion, kein Nachbau" gilt für `evaluate.py`, **nicht repo-weit**: `forward_collection.market_regimes` (~Zeile 124) macht dieselbe `nlevels`/`get_level_values`-Reduktion **inline** — nachgeprüft und bestätigt. Vorbestehend, hier bewusst nicht angefasst (der Auftrag war „nur der Abruf"), und es liegt im **Sammlungs**-Pfad: Aufräumen dort braucht den Beweis, dass sich die Population nicht verschiebt. **OFFENER NIT für einen Folge-PR.** Der Guardian bestätigte außerdem meine Berichtigung (bei k≥2 echten Spalten greift der #63-Längen-Guard zwingend, `n·k ≠ n`) und fuhr vier eigene Mutationen: `ndim>2` **2 rot**, Normalisierung entfernt **3 rot**, Nachbau **1 rot**, Reason-Text geändert **2 rot**; `.T.tolist()` blieb grün — ein **äquivalenter** Mutant (Transpose auf 1D ist Identität), keine Testlücke. 4 neue Tests (511) | Guardian (OK, Nits eingearbeitet) + manual, keine Screenshots |
| #65 | `1c9c3fe` | **Trade-Journal mit Lebenszyklus**: aus der Ablage von #61/#62 wird ein echtes Handels-Journal. **(1) Eröffnen** — „ins Journal" legt nicht mehr sofort an, sondern öffnet ein Formular: Einstiegskurs (vom Karten-Kurs vorbefüllt, editierbar — nachgetragene Einstiege), Einstiegsdatum (heute, editierbar) und die **These** (max. 500 Zeichen). Die eingefrorenen Werkzeug-Werte (Setup, Score, Zielzone, Invalidierung, Report-Stand) bleiben wie bisher. **(2) Schließen** — am offenen Eintrag: Ausstiegskurs, Ausstiegsdatum (heute vorbefüllt), **Lesson**; die These steht **vorbefüllt daneben**, damit man sie gegen das Ergebnis hält und ergänzen kann. Berechnet werden `pnl_pct` und die Dauer in Tagen. **(3) Statistik** über die **gefilterten** geschlossenen Trades: Trades, Trefferquote (≥50 % grün, sonst rot), Ø Rendite, Ø Gewinner, Ø Verlierer, Bester/Schlechtester mit Ticker, und die **Score-Korrelation** (Ø eingefrorener Score der Gewinner gegen den der Verlierer). Offene Einträge weiter **separat** und ungefiltert gezählt. **(4) Filter**: Zeitraum (Alle/7/30/90/365 Tage nach Ausstiegsdatum) und Ergebnis (Alle/Gewinner/Verlierer). **(5) Liste**: geschlossene neueste zuerst, Kopfzeile Ticker · Einstieg→Ausstieg · Dauer · P&L farbig, Meta-Zeile Kurs→Kurs · Score (Setup), Details-Klappe nur wenn es Text gibt (These blau, Lesson gelb). **GELD-GRENZE unverändert hart:** keine Stückzahlen, keine Beträge, nirgends — Ergebnis ausschließlich in Prozent, **berechnet**. **Additiv:** `these`/`lesson` kommen hinzu, `note` aus #61 **bleibt im Schema** und wird angezeigt („Notiz (frühere Fassung)") — kein Eintrag verliert etwas. EIN Commit-Pfad (docs) wie #62, Pipeline liest die Datei weiter nie, Disclaimer-Box unverändert. **Belege (headless @390 px, gemischter Testbestand aus 2 ALT- und 2 NEU-Einträgen):** kompletter Durchlauf Eröffnen→Schließen; Statistik **gegengerechnet** — Alle: 3 Trades/67 %/+6,67 %/Ø G +15,00/Ø V −10,00/Score 85,0 vs. 60,0; 30 Tage: 2 Trades/100 %/+15,00 %; nur Verlierer: 1 Trade/0 %; nach dem Durchlauf 5 Trades/80 %/+10,00 %/Score 82,3 vs. 60,0. **XSS:** `<script>`+`<img onerror>` in These UND Lesson → **0** script-Knoten, **0** img-Knoten, `window.__xss` nie gesetzt, Text erscheint wörtlich. **Validierungs-Fehler verwirft nichts:** Kurs 0 → Fehlermeldung, getippte These steht unverändert im Feld, kein Eintrag angelegt. **Alt-Eintrag ohne neue Felder:** geöffnet, angezeigt, geschlossen — leere These/Lesson, alte Notiz sichtbar, keine Fehler. **Kanten:** `entry ≤ 0`, nicht-numerisch, fehlend → `null` statt Unsinn; Datums-Parser liefert für `31.07.2026` und `2026-07-31` dasselbe. Keine Konsolenfehler, kein Querscrollen. **Mutationsproben (7):** `esc()` bei der Lesson weg → rot · Statistik über den Gesamtbestand → rot · Eingaben erst nach der Fehlermeldung gesichert → rot · `entry ≤ 0`-Guard weg → rot · Status schon bei EINEM Wert geschlossen → rot · `maxlength` weg → rot · **Zeitfilter umgeht `_tjISO` → blieb erst GRÜN** (mein Test prüfte nur, ob `_tjISO` irgendwo im Rumpf vorkommt — die #63-Lehre, Anwesenheit statt Wert); jetzt prüft er JEDE Datums-Lesestelle, beide Mutationen nachgestellt → rot. **BERICHTIGTER TEST:** `test_es_gibt_genau_EINE_journal_ablage` behauptete `== []` — eine Aussage über den INHALT statt über die Ablage. Sie wurde rot, sobald Easy am 31.07. den ersten echten Eintrag anlegte (`4b4f654`), **schon vor diesem PR**. Jetzt geprüft: eine Datei, gültige Liste, keine zweite Ablage. **Revert =** `docs/index.html` auf den Vorzustand (additives Schema → die alte Anzeige ist wieder da, `these`/`lesson` bleiben in der Datei stehen und werden schlicht nicht angezeigt) und die neuen Tests entfernen; **kein Eintrag geht verloren**, `report.json` und Sammlung sind nie beteiligt. **Guardian-Nits eingearbeitet — und sie haben einen echten Fehler gehoben:** der Guardian fuhr fünf weitere Mutationen, **alle blieben grün**, weil die Statistik nur einen „wird mit der gefilterten Liste aufgerufen"-Test hatte und keinen WERTE-Test: Breakeven als Gewinner · Bester/Schlechtester vertauscht · `>= 50` zu `> 50` (genau die im Auftrag genannte Grün-Schwelle) · Score-Korrelation vertauscht · Zeitfilter-Randtag. Also zwei Netze ergänzt: die entscheidenden Vergleiche stehen als **Literal** fest (läuft ohne jede Zusatz-Abhängigkeit), **und** die Rechenkerne `_tjPct`/`_tjISO`/`_tjTage`/`_tjStats`/`_tjGefiltert` werden mit **node wirklich ausgeführt** (feste Beispielliste, von Hand nachgerechnet; fehlt node, greift der Literal-Test allein — deshalb `skip` statt Fehler, die Suite bekommt keine neue harte Abhängigkeit). Alle fünf Mutationen nachgestellt → rot, vier davon durch **zwei** unabhängige Tests. **Dabei fand mein eigener Randtag-Test einen echten Defekt:** das Zeitfenster rechnete ab `Date.now()`, also ab der aktuellen UHRZEIT — ein vor genau N Tagen geschlossener Trade fiel je nach Tageszeit mal rein und mal raus. Jetzt ab Mitternacht (`Math.floor(Date.now()/86400000)*86400000`), damit „30 Tage" 30 Kalendertage heißt. Kosmetischer Nit ebenfalls behoben: ein Trade mit genau 0 % wurde grün gefärbt, zählte in der Statistik aber zu keiner Seite — jetzt neutral. 12 neue Tests (523) | Guardian (Nits eingearbeitet) + manual, keine Screenshots |
| #66 | `8846717` | **Score-Alarm typ-relativ — die feste Schwelle 90 war KONSTRUKTIV TOT**: der Score ist die Summe dreier **gedeckelter** Komponenten, das erreichbare Maximum ist `SETUP_BASE_POINTS[typ] + 20 + 15` — für `end_of_w4` exakt **90,00**, für `end_of_w2` **80,00**, für `end_of_c` **75,00**. Die Schwelle war eine feste `90` mit Vergleich **strikt größer**: sie lag für den besten Typ **auf** dem Maximum, für die anderen **darüber**. Der Alarm konnte **nie** auslösen — an keinem Tag, für keinen Kandidaten. Über 53 committete Report-Stände (500 Einzel-Scores) war der Höchststand **89,84**; die Cluster liegen jeweils **am** Typ-Deckel (89,84 von 90,00 · 79,55 von 80,00), nicht darunter. Der Kommentar an der Konstante nannte die Empirie korrekt und schloss daraus „bewusst fast stumm" — richtig war **„unmöglich"**. **Jetzt:** `SCORE_ALERT_FRACTION = 0,98` ist die **einzige** neue Zahl; die Schwelle wird zur **Laufzeit** je Setup-Typ berechnet (`config.score_alert_threshold(typ)` → **88,20 / 78,40 / 73,50**), Vergleich `>=`. Ändert jemand einen Deckel, wandert die Schwelle mit. Der Setup-Typ kommt aus dem `count_label` (`config.SETUP_LABEL_MARKER` + `fc.setup_typ_aus_label`) — der Report bekommt **kein** neues Feld, eine Alarm-Justierung darf ihn nicht verändern. **Unlesbares Label → strengste Schwelle (88,20), NICHT „kein Alarm"** — genau daran ist er schon einmal still gestorben. Flanken-Logik, Bündel-Push und Watchlist-Ausnahme unverändert; der Push-Text nennt jetzt **Setup-Typ und die konkrete Schwelle** (89 ist an der W4-Schwelle knapp, an der W2-Schwelle weit darüber — die nackte Zahl wäre irreführend). **Belege:** Report-Diff ALT/NEU über einen vollen Lauf → **0 Abweichungen**, Sammlung → **0**. Am ECHTEN Stand (31.07., 46 Records) gegengerechnet: ALT **0 Alarme**, NEU **genau 1** — `GE 89,00 >= 88,20 (end_of_w4)`; zweiter Lauf bei unverändertem Score **0** (Flanke, nicht Zustand); in der Sammlung änderte sich **genau ein Feld**, `records[34].score_alert_fired: None → '2026-07-31'`, und das steht **nicht** in `evaluate.FROZEN_FIELDS` — die Auswertung ist beweisbar unberührt. Push-Text real erzeugt: `GE (🇺🇸) 89 · Ende W4 (Schwelle 88.2) — heuristisch · unvalidiert (kein Signal)`. **Erreichbarkeits-Test** (`tests/test_score_alert_reachable.py`, 8 Tests): für **jeden** Typ „Schwelle < Typ-Maximum", Sollwerte **von Hand** ausgeschrieben statt aus der Formel abgeleitet, plus ein **Laufzeit**-Test, der echte `classify_setup`-Labels durch die Typ-Zuordnung schickt. **Mutationsproben (6):** Faktor auf 1,0 → **6 rot** · Deckel gesenkt → **6 rot** · `>=` zu `>` → **1 rot** · unbekannter Typ feuert gar nicht → **1 rot** · Rückfall auf die mildeste statt strengste Schwelle → **2 rot** · Label-Marker vertauscht → **4 rot**. **Datum berichtigt:** der Auftrag nannte „22.07."; `git log -S` weist die Einführung auf **23.07.** (`d217d61`) — die Registry-Notiz sagt 23.07. **Revert =** die typ-relative Schwelle zurücknehmen und die feste `90` wiederherstellen; der Alarm ist dann wieder tot, aber **keine Datenfolgen**. **Guardian-Nits eingearbeitet:** er fand **zwei** Mutationen, die grün blieben — beide reine Test-Präzision, ohne heutige Fehlwirkung, aber genau die Klasse, die still veraltet. (a) Die Schwelle im Push-Text mit `.2f` statt `.1f` rutschte durch, weil `"Schwelle 88.2" in body` auch `88.20` matcht — der Test prüft den Baustein jetzt **wörtlich und vollständig**. (b) `round(schwelle, 2)` → `round(…, 1)` blieb unsichtbar, weil 88,2 / 78,4 / 73,5 zufällig schon auf EINE Stelle glatt sind — ein neuer Test setzt den Anteil auf 0,977 (→ 87,93) und macht den Unterschied messbar. Beide nachgestellt → rot. Der Guardian bestätigte außerdem unabhängig: Deckel unangetastet, `0.98*90.0 == 88.2` exakt als Double (kein Fließkomma-Kipprand), Watchlist **strukturell** ausgenommen (eigenes Top-Level-Feld, nicht in `market["candidates"]`), und die Datumskorrektur auf den 23.07. stimmt. 19 neue/geänderte Tests (536) | Guardian (Nits eingearbeitet) + manual, keine Screenshots |
| #67 | `7cb8c1b` | **Dispatch-Kollision im Tageslauf** (Vorfall 31.07., Lauf `30626433741`): zwei Dispatches 33 Sekunden auseinander → der zweite Lauf rot, Push „Elliott-Lauf fehlgeschlagen" mit Sirene, obwohl die **Analyse fehlerfrei** war und die Daten vier Minuten später vollständig aus einem dritten Lauf kamen. **BERICHTIGUNG meiner eigenen Empfehlung:** ich hatte im Befund geschrieben, eine `concurrency`-Gruppe sei „die eigentliche Lösung, eine Zeile" — sie steht seit `f4a8bc6` (22.07.) im Workflow und war beim Vorfall **aktiv und korrekt**: der zweite Job wurde **eine Sekunde nach** dem Ende des ersten angelegt (Job-Zeitstempel 11:19:01 / 11:19:02). Sie serialisiert, aber sie **aktualisiert den Stand nicht**. **Die echte Ursache:** `actions/checkout` nimmt ohne `ref` den beim Auslösen eingefrorenen `github.sha` — der wartende Lauf rechnete auf dem ALTEN Commit und kollidierte beim `git pull --rebase` in fünf Datendateien. **A** `ref: ${{ github.ref_name }}` (nicht hart `main` — der Push-Verdrahtungstest bleibt auf SEINEM Branch). **B** `git rebase --abort` vor jedem Push-Versuch: die Wiederholungen waren keine, nach dem ersten Konflikt brachen 2 und 3 sofort mit „Pulling is not possible because you have unmerged files" ab. **C** Fehlschlag-Push unterscheidet jetzt „Daten-Push-Konflikt — Analyse lief fehlerfrei" (Priorität `default`, **keine** Sirene) von echtem Ausfall (unverändert `high` + Sirene), entschieden über `steps.{pipeline,validate,commit}.outcome`. **Belege:** A **nachgestellt** an echten Git-Repos — Auscheckart „SHA" → ALTER Stand → **Konflikt, Push gescheitert**; Auscheckart „Zweig" → AKTUELLER Stand → **Push erfolgreich** (der Vorfall exakt reproduziert und geheilt); dazu das `actions/checkout`-README wörtlich: „*When checking out the repository that triggered a workflow, this defaults to the reference or SHA for that event.*" B **nachgestellt**: ohne `abort` scheitert der zweite Versuch am hängenden Zustand, nach `abort` ist der Baum sauber, der eigene Commit erhalten und der Versuch läuft wieder echt. C **beide Pfade durchgerechnet** über alle fünf Status-Kombinationen. **Wechselwirkung geprüft:** Recalculate-Knopf startet `daily.yml` → **dieselbe** Warteschlange → wartet (gewollt); Staleness-Wächter (`elliott-staleness`) und Kurs-Abruf (`eval-prices`) haben **eigene** Gruppen → unberührt. **Mutationsproben (8), alle rot:** hart `main` · `ref` entfernt · `cancel-in-progress: true` · Gruppe je Ref · `rebase --abort` raus · Sirene zurück im Konflikt-Fall · Konflikt auf `high` · `id:` am Commit-Schritt raus. Registry datiert (31.07.): **ein Lauf führt ab jetzt den AKTUELLEN Zweig-Stand aus, nicht den auslösenden Commit** — der auslösende Commit ist damit **nicht** mehr zwingend der Code, der lief. Cron-Zeit, Pipeline, Score, Sammlung, Report-Inhalte und Alarm-Logik unangetastet; **keine** Konflikt-Gewinner-Regel (`-X ours`), sie würde still entscheiden, welcher Datenstand überlebt. **Revert =** `ref:` aus dem Checkout entfernen, `rebase --abort` und die Fallunterscheidung zurücknehmen; keine Datenfolgen. **Guardian-Nits eingearbeitet:** (1) eine **neunte** Mutation blieb grün — den `curl`-Aufruf auf feste Werte zurückdrehen, während der if/else-Block unangetastet bleibt. Die Fallunterscheidung wäre damit korrekt und **wirkungslos** gewesen; geprüft wurde nur der Block, nie die Zeile, die den Alarm absetzt. Jetzt pinnt ein Test die `curl`-Zeile auf `${TITEL}/${PRIO}/${TAGS}/${TEXT}` **und** verbietet dort jedes Literal; nachgestellt → rot. (2) Die Nachstellungen von A und B lagen nur als Prosa im PR-Text — sie sind jetzt **echte Tests** (`subprocess`-git in `tmp_path`): SHA-Checkout → alter Stand → Konflikt, Zweig-Checkout → aktueller Stand → Push erfolgreich; und ohne `rebase --abort` scheitert der zweite Versuch am hängenden Zustand, danach läuft er wieder echt und der eigene Daten-Commit überlebt. Damit ist die Begründung des PRs im Repo nachprüfbar statt behauptet. Der Guardian hat A zusätzlich **im Quelltext von `actions/checkout`** bestätigt (ohne `ref` wird `commit = github.sha` gesetzt und genau dieser SHA gefetcht; mit kurzem Branchnamen bleibt `commit` leer und der aktuelle Tip wird geholt) und den Tag-Dispatch-Randfall geprüft: `github.ref` ist dann nicht `refs/heads/main`, der Commit-Schritt wird sauber übersprungen. 18 neue Tests (554) | Guardian (Nits eingearbeitet) + manual, keine Screenshots |
| #68 | `ff07e78` | **Episoden-Anschluss zählt KALENDERTAGE statt Läufe** (mein Befund (b) aus dem Check-in vom 31.07.): der Anschluss hing an `coll["last_run_date"]` — dem Datum des letzten **Laufs**. Bei einem Lauf pro Tag ist das dasselbe wie der Kalendertag; bei mehreren nicht. Der erste Lauf setzte das Datum schon auf heute, und ein Record von **gestern** fand im zweiten Lauf desselben Tages keinen Anschluss mehr: er wurde zu einer **zweiten Episode zerschnitten**, obwohl der Ticker an zwei konsekutiven Kalendertagen in den Top 5 stand. Das widersprach der eigenen Registry-Regel „konsekutive Top-5-Tage verlängern dieselbe Episode". **Neu:** `episode_anchor_dates(coll, run_date)` liefert **zwei** Anker — das heutige Lauf-Datum **und** das jüngste davorliegende Lauf-Datum mit ANDEREM Kalenderdatum; dafür das additive Sammlungs-Feld `prev_distinct_run_date` (Schema v1, wird nur beim **Tageswechsel** fortgeschrieben, sonst ginge genau der Anker verloren, den der zweite Lauf braucht). `_open_episode()` wählt deterministisch das **jüngste** `last_seen`, bei Gleichstand die Listen-Reihenfolge — bei bereits zerschnittenen Alt-Episoden ist der jüngere Record der richtige Anschluss. **Unterbrechung bleibt Unterbrechung**, Fr→Mo und Feiertags-Brücken tragen unverändert. **Einfrier-Invariante:** eine Verlängerung schreibt **ausschließlich** `last_seen_top5_date`. **`appearance_count`** benutzt dieselben Anker (sonst zählte der zweite Lauf eines Tages eine fortgesetzte Erscheinung doppelt); wirkt nur vorwärts, der Zähler wird je Lauf neu in den Report geschrieben und nie gespeichert. **Wirkung auf den Alarm:** eine verlängerte Episode **erbt** `score_alert_fired` — der Doppel-Alarm-Weg (Flanke gesetzt → Ticker fehlt im Zwischenlauf → neuer Record ohne Flanke → zweiter Push) ist zu. **Alt-Records: MARKIERT, NIEMALS GEHEILT** (wie MET/D und der PRU-Guard) — `scripts/mark_episode_splits.py` findet sie per **Replay über die 44 committeten Sammlungs-Stände** (nach `updated_utc` sortiert, **nicht** nach Git-Reihenfolge: die Rebase-Schleife des Tageslaufs verdreht die Commit-Ordnung) und setzt additiv `episode_split_suspect`. Identität über `(ticker, created_utc)`, **nicht** `episode_id` — das kollidiert bei genau diesen Splits (real zweimal `ADS.DE@2026-07-24`). **Zehn Fälle, namentlich:** HAG.DE (24.07.), ADS.DE (25./29./30.07.), MTX.DE (28./31.07.), ANET (28.07.), EVK.DE (29.07.), KKR und G1A.DE (31.07.). **Belege:** realer 31.07.-Fall nachgestellt (drei Vormittags-Dispatches + Abendlauf → je **EIN** Record statt zwei), 30.07. und 25./29.07. ebenso; am **echten** Stand gegengerechnet: alte Regel **50→53** Records, neue **50→50**; Feld-für-Feld-Diff Alt/Neu über alle 50 Records = **nur** `episode_split_suspect` auf **10**; Purge → **byte-identisch** zu `HEAD` (git-Diff leer); Markieren **idempotent**; `evaluate.build_population` liefert mit und ohne Marker **identische** Population, Diagnose und Fall-Liste; `scripts/evaluate.py` **byte-identisch** (SHA-256 im Test gepinnt **und** ein git-Test, der die Datei im Diff verbietet). **EHRLICH ZUR BEWEISLAGE:** der im Auftrag geforderte Äquivalenz-Beweis „über die Ein-Lauf-Tage der realen Historie" wäre **leer** — die Historie enthält **keinen einzigen** Ein-Lauf-Tag (jeder der neun Kalendertage seit 23.07. trägt 2–7 Lauf-Stände). Geführt wird er stattdessen über die **acht ersten Läufe eines Kalendertags** (dieselbe Lage) mit **197** Ticker-Vergleichen, alle deckungsgleich; ein eigener Test hält fest, dass es keine Ein-Lauf-Tage gibt, und wird rot, sobald es welche gibt. **Mutationsproben (eigene, vor dem Guardian):** die alte Regel wiederhergestellt → **12 von 21** Tests rot, darunter alle realen Fälle, der Alarm-Beweis und beide `appearance_count`-Tests. **Dabei zwei eigene grün-blinde Tests gefunden und ersetzt:** der Alarm-Test und die Einfrier-Invariante prüften eine Lage, in der der Ticker in **jedem** Lauf dabei war — dort greift auch die alte Regel. Der Doppel-Alarm entsteht erst, wenn die Flanke **schon gesetzt** war und der Ticker im **Zwischenlauf fehlt**; genau so steht der Test jetzt da (inkl. JSON-Round-Trip für den committeten Zwischenstand), die Einfrier-Invariante läuft parametrisiert über **beide** Lagen. **Grenzen eingehalten:** Reifung, Score, Ranking, Filter, Report-Werte, Frontend unangetastet. **Revert =** die Anschluss-Regel per PR-Revert (dann gilt wieder `last_run_date`, der Schnitt kann wiederkehren); Marker entfernt `python scripts/mark_episode_splits.py --purge --live` **byte-identisch**. Kein Datenstand wird ungültig, keine gemessene Zahl ändert sich. **CI-ROT, zweimal, beide Male meiner — und beide Male dieselbe Klasse: in einer Umgebung gemessen, in einer anderen behauptet.** (1) Ich meldete „596 grün", gemessen **bevor** die Marker in den echten Datendateien standen; danach waren vier Marker-Tests rot, weil sie einen unmarkierten Ist-Zustand **voraussetzten** — falsch unabhängig vom Marker, denn der Tageslauf schreibt die Datei in jedem Lauf fort. Sie **normalisieren** den Bestand jetzt aktiv (`_unmarkierter_bestand` / `_basis_ohne_marker`), plus ein Gegen-Test, dass die ausgelieferte Datei die zehn Marker wirklich trägt. (2) Danach fiel die CI erneut um: `actions/checkout` klont per Default **flach** (`fetch-depth: 1`), der Replay über die committeten Stände fand **einen** Stand statt 44, `finde_splits` lieferte `[]` — acht Tests rot, lokal alle grün. Behoben in `ci.yml` mit `fetch-depth: 0`, damit der forensische Beweis wirklich läuft; dazu ein Wächter `braucht_historie`, der die Replay-Tests in einem flachen Klon **mit Grund überspringt** statt still leer grün zu sein, und ein `>= 44`-Anspruch an die Fixture. Die Marker-**Mechanik** (ändert nur das Marker-Feld, idempotent, Rückweg byte-identisch, Auswertung unbeeindruckt) hängt nicht mehr an Git — `treffer_aus_erwartung()` baut die Liste aus `ERWARTETE_FAELLE`. **Beide Klon-Tiefen gegengeprüft:** flach 596 grün + 7 begründete Skips, voll **603 grün**. 50 neue Tests (603) | Guardian (Blocker + Nits eingearbeitet) + manual, keine Screenshots |
| #69 | `bbca810` | **notify-Skriptstart + Score-Dezimale — zwei Pushes, die nicht feuern konnten** (meine Befunde (c) und (a)). **(c) Der Pfad-Defekt:** `config.py` liegt im **Repo-Root**, `notify.py` legte aber nur `REPO_ROOT/"scripts"` auf `sys.path`. Beim Start **als Skript** — genau so ruft `daily.yml` es auf (`python scripts/notify.py --mode daily`) — setzt Python `sys.path[0]` auf das **Skript-Verzeichnis**, nicht auf das Arbeitsverzeichnis. Der Repo-Root stand nirgends auf dem Pfad, `import config` scheiterte, und weil `forward_collection` seinerseits `config` importiert, scheiterte auch der. Beide in `try/except` gekapselt → **still**. **Zwei Folgen, die zweite war beim ersten Befund noch nicht quantifiziert:** (1) `_evaluable_count` lieferte dauerhaft 0 → der **Meilenstein-Push bei n≥100 konnte nie feuern**; (2) `SCORE_REVIEW_BY` fiel auf `None` zurück → der **Review-Wecker war ebenfalls tot** (`review_due(None, …)` ist immer False). Im Actions-Log vom 31.07. steht wörtlich `review_by=None`, obwohl in `config.py` der 07.12.2026 steht — den zweiten Ausfall hat erst der echte Skript-Lauf nach dem Fix sichtbar gemacht. **Warum es niemandem auffiel:** die Pipeline importiert `notify` als **Modul** und legt beide Verzeichnisse selbst auf den Pfad, der Score-Alarm war deshalb nie betroffen; und jede lokale Nachstellung über `python -c` hat das Arbeitsverzeichnis auf dem Pfad. Die übrigen `getattr(config, …)`-Rückfälle (`REPORT_PATH`, `CARD_STATUS`, `EVAL_MIN_N`) stimmten **zufällig** mit den echten Werten überein — nur die zwei ohne passenden Rückfall fielen aus. **Jetzt** liegen beide Verzeichnisse auf dem Pfad, wie in `elliott_pipeline.py`; die „nicht verfügbar"-Logzeile nennt zusätzlich den **gemerkten Import-Fehler** (`_IMPORT_FEHLER`) — fail-soft bleibt fail-soft, aber eine stille Fehlstelle darf nicht noch einmal acht Tage unbemerkt bleiben. **(a) Score-Dezimale:** der Push-Text schrieb `{score:.0f}` neben `{threshold:.1f}`. Ein Score von 88,34 wurde zu „88" und stand neben „Schwelle 88.2" scheinbar **unter** seiner eigenen Schwelle, obwohl der Alarm zu Recht feuerte. Das Fenster **88,20–88,49 ist der Bereich direkt über der W4-Schwelle**, also der **häufigste** Alarm-Fall, nicht der seltenste; am 31.07. blieb es folgenlos, weil QIA.DE bei 88,69 lag. Der Vergleich lief immer auf den **Rohwerten** — es war ausschließlich ein Anzeige-Widerspruch, keine Fehlauslösung. **SICHERHEITS-PRÜFUNG (der Fix erweckt zwei Pushes, keiner geht los):** am Stand vom 01.08. 50 gesammelt, **0 gereift, 0 auswertbar** bei Schwelle 100 → `milestone_reached` bleibt False; der **Einmal-Marker `data/validation_milestone_fired.flag` existiert nicht und wird an einem echten Skript-Lauf nicht angelegt** (nachgemessen, nicht behauptet). Der Review-Wecker braucht `review_by` überschritten **und** Montag: der 07.12. ist selbst ein Montag, aber noch nicht „überschritten" — erster wirklicher Auslöser ist **Montag, 14.12.2026**. **Belege:** der (c)-Test startet `notify.py` als **echten Subprozess** mit neutralem Arbeitsverzeichnis (`cwd=sys.prefix`) und geleertem `PYTHONPATH`/`NTFY_TOPIC` — ein `import notify` in pytest hätte den Fehler **garantiert verfehlt**, weil pytest den Repo-Root längst auf dem Pfad hat; genau diese Bequemlichkeit hat den Defekt acht Tage verdeckt. Dazu eine **Negativ-Kontrolle**, die den alten Pfad-Aufbau nachstellt und belegt, dass `config` und `forward_collection` dort wirklich mit `ModuleNotFoundError` scheitern, `market_calendar` (liegt in `scripts/`) dagegen gelingt — das ist der Grund, warum der Staleness-Modus nie auffiel. Push-Text real erzeugt: `QIA.DE (🇩🇪) 88.7 · Ende W4 (Schwelle 88.2) — heuristisch · unvalidiert (kein Signal)`. **Wert-Tests mit von Hand ausgeschriebenem Soll:** 88,20→„88.2", 88,25→„88.2" (Bankers Rounding, kein Tippfehler), 88,34→„88.3", 88,49→„88.5", 88,69→„88.7", 93,0→„93.0"; plus ein Test, der aus dem fertigen Text Zahl und Schwelle **zurückliest** und `gezeigt >= schwelle` prüft. **Mutationsproben (3):** Repo-Root aus dem `sys.path`-Aufbau entfernt → **3 rot** · `.1f` zurück auf `.0f` → **9 rot** · Grund aus der Fehlzeile entfernt → **2 rot**. **Grenzen eingehalten:** Alarm-Logik, Schwellen, Flanken-/Bündel-Mechanik und der Einmal-Marker unangetastet; keine weiteren notify-Umbauten (die `REPO_ROOT`-Pfad-Hygiene aus der Inventur bleibt Backlog). **Revert =** PR zurücknehmen; dann sind beide Pushes wieder tot und der Alarm-Text wieder ganzzahlig, **keine Datenfolgen**. 22 neue/geänderte Tests (624) | Guardian + manual, keine Screenshots |
| #70 | `b127d22` | **Zonen-Abstand in Prozent** (Easy-Wunsch, reines Frontend): an Zielzone und Extension jeder Live-Karte steht eine kleine Prozentangabe, wie weit die Zone vom aktuell angezeigten Kurs entfernt liegt — `(Zonen-Unterkante / Kurs − 1) × 100`. **Bezugskante ist bewusst die UNTERKANTE:** dieselbe Kante, an der die Pipeline `target_exceeded` schneidet und an der die Erfolgsmessung der Forward-Sammlung einen Treffer zählt. Eine andere Kante wäre eine **zweite, stille Definition von „Ziel"** — dieselbe Zahl müsste dann an zwei Stellen etwas Verschiedenes heißen. **Bezugskurs ist der ANGEZEIGTE Kurs:** beim Rendern der Report-Kurs, danach rechnet **jeder Live-Quote-Tick mit** (`quotePatch` → `_setZoneDist`, gleiche Verdrahtung wie Zonen-Badge und Zeitebenen-Hinweis). Ohne das stünde auf derselben Karte ein frischer Kurs neben einer Prozentzahl, die noch den Report-Stand meint. **Kein Kurs / Kurs 0 / nicht-finit → gar keine Angabe**, nie „NaN". **Darstellung:** eine Dezimale, deutsches Komma, echtes Minus (−), `tabular-nums` (damit die Spalten beim Tick nicht springen), `white-space:nowrap`, **neutrale Farbe `--txt-dim`** — der Abstand ist ein **Fakt, keine Bewertung**, deshalb bewusst kein Grün/Rot und keine Vorzeichen-Farbe. **Kein „−0,0 %":** die Vorzeichen-Prüfung läuft auf dem **gerundeten** Wert (JS rundet −0,04 auf −0, und `−0 < 0` ist false). **Vier Render-Stellen** — alle, die Zielzone/Extension auf einer Karte **mit Live-Kurs** zeigen: Zielzone-Kachel, Extension-Zeile, Großer-Grad-Block und die Zeitebenen-Paare. Im `tf-pair` steht der Abstand **neben** `.tf-v`, nicht darin: `.tf-v` ist `white-space:nowrap`, eingebettet wären Zone und Prozentzahl **ein** unumbrechbarer Block und die 390px-Kachel risse auf. **BEWUSST AUSGELASSEN, mit Grund:** `showEpisodeDetail` und die Backtesting-Zeilen zeigen **historische** Episoden mit eingefrorenem Einstiegskurs und **ohne** Live-Kurs — ein „Abstand zum aktuellen Kurs" hätte dort keinen Bezugspunkt. Und die **Sofortkarte** (`_wlInstantCard`) rendert **gar keine Zone** (nur Live-Kurs + Chart-Link, die Analyse folgt beim nächsten Lauf) — der Auftrag nennt sie ausdrücklich, dort gibt es aber nichts zu annotieren. **Invalidierungs-Abstand nicht angefasst** (nicht beauftragt). **EIGENER DEFEKT BEIM TESTSCHREIBEN GEHOBEN:** `Number(null)` ist `0` und damit **endlich** — eine **fehlende** Zonenkante ergab brav „−100,0 %" statt gar nichts. `zoneDistPct` fängt `null`/`undefined`/`''` jetzt **zuerst** ab, bevor irgendetwas in eine Zahl umgewandelt wird. **Belege:** am **echten DOM** mit Chromium bei **390 px** gemessen — 40 Abstände gerendert, alle sichtbar, **kein** NaN/leeres Prozentzeichen/„−0,0 %", Body `scrollWidth/clientWidth = 390/390`, **keine** Karte mit Überlauf; **Live-Tick-Beweis** am echten IONQ-Fall: Kante 38,5944, Kurs auf 36,7566 gesetzt → Anzeige `+5,0 %`, von Hand gegengerechnet, und das Kurs-Feld wanderte im selben Tick mit. **Wert-Tests in node ausgeführt**, Soll ausgeschrieben: 107,4/100 → `+7,4 %` · 98,8/100 → `−1,2 %` · 100,0/100 → `0,0 %` (**kein** Vorzeichen) · 99,96/100 → `0,0 %` · 100,04/100 → `0,0 %` · 100,06/100 → `+0,1 %` · 150/100 → `+50,0 %` · 50/100 → `−50,0 %`; fehlender Kurs, Kurs 0, nicht-numerisch, `Infinity`, fehlende Kante → **gar nichts**. **Mutationsproben (7), alle rot:** Bezugskante `.low`→`.high` · Poller-Verdrahtung entfernt · Vorzeichen auf Rohwert statt gerundet · zwei Dezimalen · Abstand **in** `.tf-v` statt daneben · Farbe auf `--grn` · null-Guard entfernt. **Methodik-Glossar** erklärt Formel, Bezugskante, Live-Mitrechnung und die neutrale Färbung. **Grenzen eingehalten:** Report-Schema, Score, Filter, Sammlung, Pipeline **unberührt** (ein Test verbietet `scripts/`, `config.py`, `data/`, `.github/` im Diff). **Revert =** PR zurücknehmen; **keine Datenfolgen**, die Zahl war nie gespeichert. **ZWEITER COMMIT, anderer Vorgang:** mein eigener Stolperdraht aus #68 (`test_die_reale_historie_hat_KEINEN_ein_lauf_tag`) ist **planmäßig ausgelöst** — am 01.08. trug jeder Kalendertag 2–7 Lauf-Stände, der **04.08. trägt genau einen**. Der Test führt den Äquivalenz-Beweis jetzt **wirklich** (an Ein-Lauf-Tagen darf keine Abweichung liegen), statt die Abwesenheit zu behaupten; ein Wachhund verhindert, dass er still leerläuft. Die **datierte Registry-Notiz vom 01.08. bleibt unangetastet** — sie beschreibt korrekt, was an jenem Tag galt. **Nebenbefund, nur gemeldet:** der **03.08. trug VIER Lauf-Stände und erzeugte KEINEN neuen Split**, die Splits stehen weiter bei genau zehn — die erste **Live-Bestätigung der #68-Reparatur** an einem echten Mehrfach-Lauf-Tag. 27 neue Tests (653) | Guardian-Kurzblick + SELF-MERGE bei grünem CI, keine Screenshots |
| #71 | `43d1afc` | **Kurs-Stand-Wächter — der Report darf nicht still auf veralteten Kursen rechnen** (Punkte 1+2 aus dem Montags-Befund). **Anlass:** am 04.08. standen **beide** Märkte auf dem Kursstand vom 31.07.; die Montags-Zeile kam von der Quelle **nicht-finit** und wurde von der Härtung vom 27.07. zu Recht verworfen (`dropped_bar_dates {'2026-08-03': 116}` DE bzw. `{…: 236}` US, `dropped_last_row` = alle, `dropped_mid_row` = 0). Danach rechneten Score, Filter **und** Anzeige auf Freitags-Kursen; je ein Ticker fiel aus den Top 5 (DE NOEJ.DE→TKA.DE, US COF→KKR), `target_exceeded` verschob sich (DE 16→15, US 37→32), und die Sammlung legte **eine Episode an** (KKR), die es bei aktuellen Kursen nicht gäbe — und der Health-Check meldete `status: ok`. **Warum es niemand merkte:** die vorhandenen Regeln prüfen Kandidatenzahl, Fetch-Fehlerquote und tote Ticker, **nicht das Bar-Datum**; `cal.is_stale` misst den **Report-Zeitstempel**, nicht die Kurse — ein taufrischer Lauf auf drei Tage alten Kursen galt als frisch. **Neu:** `market_calendar.letzter_handelstag` + `handelstage_rueckstand` (dort, wo schon das Feiertags-Gate und der Staleness-Wächter wohnen — **eine** Kalender-Quelle) und `health_check.check_bar_freshness`: je Markt `diag.last_bar_date` gegen den letzten Handelstag bis einschließlich des Lauf-Datums, **1 Handelstag → `warn`**, ab `HEALTH_BAR_LAG_CRIT` = 2 → **`crit`**. Läuft im **normalen** Befund-Pfad (Lauf-Status, Report-Block, gebündelter Push, unverändertes Flanken-Verhalten) — **kein neuer Push-Kanal**. **Fail-soft:** ohne `last_bar_date` oder Lauf-Zeitstempel meldet die Regel **nichts**; ein Wächter, der aus Unwissen Alarm schlägt, färbt Alt-Stände und Fixtures grundlos rot. **Additiv im Report:** `diag.expected_bar_date` + `diag.bar_lag_trading_days`, in `build_report` aus derselben Kalender-Funktion gerechnet; das Frontend liest **die fertige Zahl** und hängt an „Kurse vom" einen `--ora`-Hinweis („⚠ 2 Handelstage zurück"), der von selbst verschwindet — der Handelskalender existiert damit **nicht** ein zweites Mal in JavaScript. **Belege:** der echte 04.08.-Report ergibt **DE+US `crit`** (damals `ok`), der gesunde 03.08.-Lauf (21:29) bleibt **still**, und der DE-Nebenbefund vom 03.08. abends (DE stand auf Donnerstag 30.07., weil die Freitags-Zeile in der Quelle fehlte) wird als `crit` erkannt. **390 px in drei Zuständen** am echten DOM gemessen (Rückstand 2 → Hinweis zweimal, Farbe `rgb(245,158,11)` = `--ora`; lag 0 → kein Hinweis; Alt-Report ohne das Feld → kein Hinweis; Body 390/390, keine Seitenfehler). **Mutationsproben (11), alle rot:** Regel aus `collect_findings` · Regel liefert `[]` · crit-Schwelle auf 3 · sev-Zweig gedreht · Wochenende zählt als Handelstag · Rückstand zählt Kalendertage · Frontend-Hinweis immer sichtbar · Warnfarbe grün · `diag`-Guard entfernt · `datetime`-Zweig entfernt · Schwelle umgangen. **ZWEI BEKANNTE GRENZEN, beide getestet und in der Registry benannt:** (1) **Einzelmarkt-Feiertage** — `FULL_CLOSURE` listet nur die *gemeinsamen* Schließtage; am Ostermontag/1. Mai (nur Xetra) bzw. Thanksgiving/July 4 (nur NYSE) meldet der geschlossene Markt ein `warn`, das sich am Folgetag von selbst heilt (~6–8 Tage/Jahr je Markt). (2) **Läufe vor Handelsschluss** — die Regel liest vom Zeitstempel nur das Datum; ein Vormittags-Lauf erwartet eine Bar, die es zur Uhrzeit nicht geben kann. **GUARDIAN-BLOCKER, mein Fehler:** die Registry behauptete „die übrigen Läufe still" — falsch, die Hand-Dispatches am **31.07. 11:16 und 11:22 UTC** hätten je ein `US: Kurse 1 Handelstag zurück` gemeldet (NYSE öffnet erst 13:30 UTC). **Beide Zeilen standen in meinem eigenen Rückblick** und wurden von mir wegzusammengefasst; der Guardian hat es an der echten Report-Historie nachgerechnet. Rückblick jetzt vollständig samt ausdrücklicher Berichtigung, Verhalten per Test festgenagelt. **FEST EINGEPLANT (Easy, 04.08.):** eigener kleiner PR **nach Variante C**, der die Erwartung auf den letzten Handelstag umstellt, dessen Sitzung zur Lauf-Zeit **beendet** ist (markt-eigene Schlusszeiten, ordentliche DST-Behandlung) — Grund: Easy dispatcht regelmäßig tagsüber, der Fehlalarm käme oft, und ein Wächter, den man ignoriert, ist wertlos. Die **crit→warn-Herabstufung des 04:46-Falls** gehört ausdrücklich in jenen PR-Text; die Abend-Cron-Läufe bleiben unverändert bewertet. **Zwei Guardian-Nits** (ungetestete fail-soft-Pfade): Markt **ohne** `diag`-Schlüssel (ohne den `or {}`-Guard `AttributeError` statt Schweigen) und der `datetime`-Zweig in `_als_datum` (ohne ihn wirft `date < datetime` `TypeError`, nachgemessen); `HEALTH_BAR_LAG_CRIT` jetzt zentral in `config.py` wie alle Schwester-Schwellen. **ZWEI VORBESTEHENDE TESTFEHLER** dabei behoben, beide hätten die CI getroffen: `test_trade_journal` popte `checked_at` — ein Feld, das es nicht gibt (der Health-Block trägt `checked_utc`, denselben Zeitstempel wie `run_timestamp_utc`); der Pop war ein No-op und der Test rot, sobald die zwei Pipeline-Läufe über eine **Sekundengrenze** fielen (~5 %). Und `test_zonen_abstand` behauptete eine **PR-Momentaufnahme als Dauer-Invariante** (`git diff origin/main -- scripts/` muss leer sein) — beim ersten Backend-PR danach rot, hätte ab dann jeden weiteren blockiert; ersetzt durch die Invariante, die wirklich gelten soll. **Grenzen eingehalten:** Abruf, Verwerfungs-Logik, Score, Filter, Sammlung, Cron-Zeit unberührt; der **Sammlungs-Schutz ist bewusst draußen** (eigener PR, Variante C). **Revert =** PR zurücknehmen; die beiden `diag`-Felder bleiben in committeten Reports stehen und werden nicht gelesen, **kein Datenstand wird ungültig**. 53 neue Tests (708) | Guardian (Blocker + Nits eingearbeitet) + manual, keine Screenshots |
| #(dieser) | `(offen)` | **Sammlungs-Schutz bei veraltetem Kurs-Stand — markt-bewusste Anker** (Easys Beschluss vom 04.08., Variante C). Steht ein Markt laut Kurs-Stand-Wächter hinter dem letzten erwarteten Handelstag zurück, legt der Lauf für **diesen Markt** keine neuen Episoden an. Anlass: der Quellen-Aussetzer vom 04.08. erzeugte einen Record aus veraltetem Stand (**KKR**, `first_seen 2026-07-31`, angelegt vom 04:46-Lauf). **REGISTRY-EINTRAG ZUERST**, als eigener erster Commit (`b19b910`), dann der Code. **DIE HARTE INVARIANTE war die eigentliche Denkarbeit:** ein naives Gate zerschneidet genau die Episoden, die es schützen soll — der übersprungene Lauf schreibt `last_run_date` fort, und der nächste saubere Lauf findet die Records von vorgestern nicht mehr unter seinen Ankern. **Reproduziert, nicht erschlossen:** sauber → stale → sauber ergab **zwei** Records statt einem. Auch die naheliegende Abmilderung („nur verlängern, nie anlegen") schließt das Loch **nicht** — sie hilft nur für Ticker, die zufällig auch in den *veralteten* Top 5 stehen, und genau diese Information hat der Aussetzer zerstört. **Lösung:** neues Sammlungs-Feld `last_fresh_run_date` **je Markt** (additiv, Schema v1); `episode_anchor_dates(coll, run_date, market)` ankert auf den letzten **frischen** Lauf dieses Markts; ein gegateter Markt wird **komplett** übersprungen — weder Anlage noch Verlängerung. Beides gehört zusammen: liefe nur die Anlage nicht, wanderte `last_seen_top5_date` auf einen Tag, den der markt-eigene Anker gar nicht kennt. **Ohne Markt-Angabe oder ohne das Feld gilt unverändert #68** (Migration alter Stände). **Schwelle ≥ 1 Handelstag**, wörtlich wie in der Registry — vorher geprüft, ob das die Sammlung aushungert: über die **gepaarte committete Historie** (52 Sammlungs-Stände × die Märkte ihres Laufs = **104 Markt-Läufe**) hätte das Gate **7×** gegriffen (6,7 %), bei Schwelle ≥ 2 nur **3×** (2,9 %). **Die sieben zerfallen in zwei Klassen:** vier sind **Vormittags-Dispatches vor Börsenöffnung** (31.07. 11:16 + 11:22 US, 04.08. 04:46 DE+US) — genau die Klasse, die der bereits eingeplante Sitzungs-Ende-PR beseitigt; drei sind **echter Rückstand**, abends gemessen (DE am 30.07., 31.07., 03.08.). Aus diesen dreien stammen drei der vier Alt-Records — deshalb ≥ 1 und nicht ≥ 2. Die sieben laufen im Test durch den **echten** `stale_markets`-Code, nicht am Kalender vorbei. `stale_markets(report)` liest `diag.bar_lag_trading_days` — **dieselbe Zahl** wie der Wächter, keine zweite Definition; fail-soft: fehlt das Feld, gilt der Markt als **frisch** (ein Gate, das aus Unwissen sperrt, hielte die Sammlung still an). **`appearance_count` zieht mit denselben Ankern mit.** **REIFUNG BLEIBT UNGEGATED — und das ist eine Entscheidung, keine Auslassung:** `mature_record` ist kein Akkumulator, es rechnet je Lauf aus der Kursreihe neu. Belegt an der Sequenz sauber → stale → nachgeliefert: `bars_elapsed` rührt sich am stale Tag nicht (die nicht-finite Zeile wird aussortiert und verbraucht keinen Slot), kein Datum steht doppelt im `price_path`, und der Endzustand ist **in jedem gemessenen Feld identisch** mit dem ohne den stale Zwischenlauf. Ein Gate dort wäre **schädlich** — es zerstörte genau die Selbstkorrektur. **`skipped_bars` klebt nicht mehr** (Variante b: setzen wenn > 0, sonst **entfernen**): vorher behauptete ein Record nach der Nachlieferung dauerhaft einen übersprungenen Bar. Bewusst nicht „immer setzen" — das hätte allen Records ein `skipped_bars: 0` angehängt; so bleibt der Daten-Diff dafür **leer**. **Easys erste Empfehlung (der Einzeiler) war hier falsch, er hat sie auf meinen Nachweis hin selbst zurückgezogen.** **LAUT statt still:** Log-Zeile im Lauf, `diag.new_episodes_gated` im Report, eine Zeile im Lauf-Status („keine neuen Episoden — Kurs-Stand veraltet", `--ora`). **KEIN eigener Push** — der Wächter meldet dieselbe Lage bereits, ein zweiter Alarm wäre ein Doppel-Alarm (ein Test verbietet `new_episodes_gated`/`stale_market` in `health_check.py`). **ALT-RECORDS MARKIERT, NIEMALS GEHEILT:** `scripts/mark_stale_market_records.py` verknüpft die committeten Sammlungs- und Report-Stände über den Lauf-Zeitstempel (`updated_utc` == `run_timestamp_utc`) und findet **vier** Records: **ADS.DE** (30.07., lag 1) · **MTX.DE** und **G1A.DE** (31.07., lag 1) · **KKR** (04.08. 04:46, lag 2). Feld-für-Feld geprüft: von 56 Records ändern sich genau diese vier, an ihnen ausschließlich `stale_market_suspect`; Purge stellt **Byte-Identität** her; `evaluate.py` byte-identisch (SHA gepinnt), Marker nicht in `FROZEN_FIELDS`. **ÜBERLAPPUNG AUSDRÜCKLICH FESTGEHALTEN: drei der vier tragen zusätzlich `episode_split_suspect`** — die Marker-Entscheidung vor der ersten Auswertung muss beide **zusammen** behandeln, sonst würde ein Record je nach Reihenfolge zweimal oder gar nicht ausgeschlossen. **ÄQUIVALENZ:** über die reale Historie **97 frische Markt-Läufe** (frisch = Rückstand 0 **oder nicht messbar**, fail-soft wie im Gate), Anker-**Mengen** verglichen → **null Abweichungen** — jetzt als **Dauer-Test**, der die Zahlen bei jedem Lauf neu rechnet statt eine Momentaufnahme zu pinnen. **ZWEI EIGENE BERICHTIGUNGEN, beide vor dem Ready gefunden:** (1) ein erster Vergleich meldete drei Abweichungen — er verglich den Anker-*Eingang* statt der resultierenden *Menge* und war zu grob. (2) Eine frühere Fassung **dieser Zeile** nannte „40 Läufe, 80 Markt-Läufe, 9 % / 4 %“ und „115 frische Markt-Läufe“. Diese Zahlen ließen sich am committeten Stand **nicht reproduzieren** — sie stammten aus einer Ad-hoc-Auswertung, deren Population ich nicht mehr belegen kann, und **kein Test deckte sie**. Ersetzt durch die oben genannten, jeweils nachrechenbaren Zahlen samt Test. Der `chart_points`-Umweg, der als Ersatzquelle naheliegt, ist **untauglich**: er ist eine gekürzte Reihe und meldet für Juli Rückstände von 5–9 Tagen, die es nie gab — der Rückstand ist nur dort messbar, wo `diag.last_bar_date` steht, also seit dem 30.07.) **Mutationsproben (7), alle rot:** Gate entfernt · Anker nicht markt-bewusst · `last_fresh` auch für stale Märkte fortgeschrieben · Gate-Schwelle auf 2 · `skipped_bars` klebt wieder · `appearance_count` ohne Markt · Frontend-Notiz immer sichtbar. **390 px** am echten DOM: Gate-Zeile in beiden Märkten, Farbe `rgb(245,158,11)`, Body 390/390, keine Seitenfehler; bei lag 0 nichts. **Grenzen eingehalten:** Score, Ranking, Filter, Report-Werte, Reifungs-**Definition** und Wächter-Schwellen unverändert; Frontend nur die eine Lauf-Status-Zeile; keine Cron-Änderung. **Revert =** PR zurücknehmen; Marker entfernt `python scripts/mark_stale_market_records.py --purge --live` byte-identisch. 43 neue Tests (751) | Guardian + manual, keine Screenshots |

(Merge-Commits/tägliche `chore(data)`-Commits ausgelassen. Der tägliche
`report.json`-Commit trägt `[skip ci]`.)

---

## 3. OFFENE VERIFIKATIONEN (nicht schönreden — bleiben OFFEN bis belegt)

Aus der Sandbox **nicht** verifizierbar (kein Yahoo/EDGAR/externer Host, CORS):

- **✅ ERLEDIGT (#21, live bestätigt) — Forward-Sammlung wird persistiert:**
  `daily.yml` committet ab #21 auch `data/forward_collection.json` (+ Spiegel);
  der erste Lauf danach committete **10 Records** auf main (`c972403`). Die
  Sammlung akkumuliert über die Läufe; n wächst, `appearance_count`/N×-Badge und
  Reifung greifen. Push race-gehärtet (`git pull --rebase` + 3× Retry).
- **✅ ERLEDIGT (#67, live bestätigt 31.07.) — Zweig-Checkout:** der erste geplante Lauf mit dem #67-Stand (`30670670145`, 22:40:18Z, `head_sha c572a4c`) lief **sauber durch**: alle Schritte grün, Push im **ersten** Versuch (`c572a4c..15aec42`), keine Retry-Zeile, Schritt „Push bei Lauf-Fehlschlag" **skipped**. Der **Konflikt-Pfad** des Fehlschlag-Pushes bleibt **live ungesehen** — er ist nur durchgerechnet und als pytest-Nachstellung belegt, nie ausgelöst worden. **BLEIBT OFFEN.**
- **✅ ERLEDIGT (#66, live bestätigt 31.07.) — Score-Alarm feuert:** derselbe Lauf meldete `[elliott] Score-Alert (typ-relativ): 1 neu — QIA.DE 88.69>=88.20 (end_of_w4)`, **genau ein** Record trägt `score_alert_fired` mit dem Lauf-Datum. Nicht GE, wie am 31.07. vormittags gegengerechnet: GE war abends **nicht mehr in den Top 5** (US-Spitze AJG 87,70), und der Alarm bewertet ausschließlich `markets[].candidates` mit dem AKTUELLEN Score — die 89,00 im GE-Record ist der eingefrorene Anlage-Score vom 29.07. Verhalten also korrekt, Erwartung war an einem älteren Report-Stand gebildet.
- **✅ ERLEDIGT (dieser PR) — Score im Alarm-Push trägt eine Dezimale.** Der Widerspruch „88 (Schwelle 88.2)" ist ausgeschlossen; das Fenster 88,20–88,49 ist der Bereich direkt über der W4-Schwelle und damit der häufigste Alarm-Fall. Der Vergleich lief immer auf den Rohwerten — es war reine Anzeige, keine Fehlauslösung.
- **✅ ERLEDIGT (dieser PR) — `notify.py` findet `config` beim Skript-Start.** Beide Verzeichnisse liegen auf dem Pfad (wie in `elliott_pipeline.py`); die „nicht verfügbar"-Zeile nennt jetzt den Import-Fehler. **Zweiter Ausfall dabei gefunden:** nicht nur der Meilenstein-Push war tot, auch der **Review-Wecker** — `SCORE_REVIEW_BY` fiel auf `None` zurück, und `review_due(None, …)` ist immer False. Beide gehen durch den Fix NICHT los: 0 von 100 auswertbar, Einmal-Marker existiert nicht und wird an einem echten Skript-Lauf nicht angelegt, Review-Wecker erst Montag **14.12.2026**.
- **OFFEN (Backlog, kein Auftrag) — Rückfallwerte in `notify.py` können still divergieren:** `REPORT_PATH`, `CARD_STATUS` und `EVAL_MIN_N` haben `getattr(config, …, <Literal>)`-Rückfälle, deren Literale **zufällig** mit den echten Werten übereinstimmen. Genau deshalb blieb der Import-Ausfall unsichtbar — nur die zwei Werte ohne passenden Rückfall fielen auf. Die Pfad-Hygiene aus der Inventur (ein gemeinsamer `sys.path`-Baustein statt drei Fassungen) bleibt vorgemerkt.
- **OFFEN — Kurs-Abruf mit Löchern (Rot-Fall):** zweimal dispatcht (29.07. `bd2f63a`, 30.07. `c37a5dc`), **beide Male 33/33 Ticker ohne Lücken** → zu Recht grün, Artefakt hochgeladen, „Arbeitsbaum sauber". Der ROT-Fall ist damit live **noch nicht gesehen**, nur offline nachgestellt; er bleibt offen, bis ein echter Abruf einen Ticker in `ticker_mit_luecken` schreibt.
- **BEFUND 30.07. (Registry-Notiz bestätigt, mit einer Präzisierung) — der Ein-Tag-Versatz hat ZWEI Wege:** der Dispatch um 07:04 UTC zeigte alle 17 US-Ticker auf `2026-07-29`, alle 16 `.DE`-Ticker auf `2026-07-28`. Dabei wurde **keine** Zeile verworfen — die 29.07.-Zeile für `.DE` war **gar nicht vorhanden**. Der Versatz entsteht also (a) über eine noch nicht endliche Tages-Zeile, die die Härtung verwirft (so am 29.07. um 03:55), **und** (b) über eine Zeile, die die Quelle für `.DE` später liefert. Die Registry-Notiz vom 30.07. beschreibt Wirkung und Folgen korrekt, ihr Ursachen-Satz nennt aber nur (a) — Ergänzung ist Easys Entscheidung, nicht still nachgetragen.
- **OFFEN (laufend) — `last_bar_date` je Markt:** Stand 31.07. (Lauf 22:40Z): **DE `2026-07-30`**, **US `2026-07-31`** — der Ein-Tag-Versatz ist wieder da, in der Form aus der Registry-Notiz vom 30.07.: die letzte Zeile war für **alle 116** DE-Ticker nicht-finit (`dropped_bars: 116`, `dropped_bar_dates: {'2026-07-31': 116}`, je Ticker `(-1/0)` = letzte Zeile verworfen, keine mitten in der Reihe). US `dropped_bars: 0`. Bleibt in Beobachtung.
- **✅ ERLEDIGT (live bestätigt 03./04.08.) — Episoden-Anschluss:** der Tageslauf hat `prev_distinct_run_date` korrekt gesetzt (Stand `2026-08-03` beim Lauf vom 04.08.), die zehn `episode_split_suspect`-Marker haben die Läufe unbeschadet überstanden, und der **03.08. mit VIER Lauf-Ständen erzeugte KEINEN neuen Split** — die Splits stehen weiter bei genau zehn. Erste Live-Bestätigung der #68-Reparatur an einem echten Mehrfach-Lauf-Tag.
- **OFFEN (Beobachtung) — beide Märkte hingen am 04.08. auf dem 31.07.:** der Lauf vom 04.08. (04:46 UTC) meldet `last_bar_date` **DE und US je `2026-07-31`**, bei `dropped_bars` **116 (DE)** und **236 (US)** — erstmals auch US vollständig. Der Handelstag Montag 03.08. fehlt damit in beiden Märkten. Ob das der bekannte Ein-Tag-Versatz in größerer Form ist oder etwas Neues, ist **weiterhin nicht geklärt** — Easys Entscheidung, ob das eine eigene Untersuchung wert ist. **Die URSACHE bleibt offen; nur die FOLGEN sind seither eingedämmt:** #71 macht den Zustand laut (Health-Regel + Hinweis im Lauf-Status), dieser PR hindert einen solchen Lauf daran, neue Episoden anzulegen. Ein Lauf auf veralteten Kursen ist damit sichtbar und für die Sammlung folgenlos — er passiert aber unverändert.
- **OFFEN (laufend, ab diesem PR) — das Gate live noch nie ausgelöst:** der Sammlungs-Schutz ist ausschließlich gegen die **committete Historie** und nachgestellte Läufe belegt (Äquivalenz über 115 frische Markt-Läufe, sieben rote Mutationsproben). In einem **echten** Lauf hat er noch nie gegriffen. Zu prüfen, sobald ein Markt wieder zurückhängt: steht die Zeile „keine neuen Episoden — Kurs-Stand veraltet“ im Lauf-Status, bleibt die Sammlungsgröße für diesen Markt unverändert, und ist die Episode am **nächsten** frischen Tag durchgehend (kein neuer Record für einen Ticker, der schon lief)?
- **OFFEN (ab diesem PR) — `last_fresh_run_date` im echten Lauf:** das Feld entsteht erst beim ersten Lauf nach dem Merge (die committete Sammlung kennt es noch nicht) und der Anker fällt bis dahin per Migration auf #68 zurück. Zu prüfen: trägt `data/forward_collection.json` nach dem ersten Tageslauf beide Märkte mit dem Lauf-Datum?
- **OFFEN — `.DE`-Chart-Link:** `stockanalysis.com/quote/etr/{SYMBOL ohne .DE}/`
  ist **Best-Guess** (`docs/index.html` `chartUrl`), nie live geöffnet. US-Muster
  `/stocks/{lower}/`.
- **OFFEN — `.DE`-Live-Quote:** der Worker `quote-proxy.easywebb.workers.dev`
  erlaubt nur Origin `easywebb911.github.io`; ein echter `SAP.DE`-Quote-Check steht
  aus (localhost trifft nur den Fail-soft-Pfad = grauer Punkt).
- **OFFEN — Recalculate-Live-Test (inkl. Status-Banner dieser PR):** Token hinterlegen
  (Fine-grained, **Actions: write**) → Recalculate → in *Actions* muss ein Lauf
  erscheinen, UND das neue **Status-Banner** „Neuberechnung läuft … N s" muss laufen,
  bei fertigem Lauf automatisch die frischen Daten rendern (grünes „fertig" + Toast,
  kein manueller Reload). Real-POST + Report-Stand-Polling in der Sandbox CORS-/Netz-
  geblockt; **offline voll durchgespielt** (Playwright: läuft/fertig/Timeout/Feiertag,
  Mock-Report altert → Poll erkennt). **Endbeweis = echter Recalculate durch Easy.**
- **OFFEN — Token-Session am echten iPhone (#26/dieser PR):** einmal Master-PW →
  danach Recalculate/Watchlist-Speichern **ohne** erneutes PW (28 Tage) → „Sperren"
  fragt sofort wieder. Offline vollständig durchgespielt (Playwright 14/15, secure
  context http://localhost); die **iOS-ITP-Realität** (räumt Safari nach ~7 Tagen
  Inaktivität die Website-Daten, ist die Session früher weg → PW-Dialog) ist nur
  am echten Gerät beobachtbar.
- **OFFEN — Watchlist-Live-Test:** Ticker add/remove → **Auto-Sync** (seit diesem PR,
  Token zusätzlich **Contents: write**) → nach ~3 s Debounce PUT auf
  `watchlist_personal.json` (Toast „✓ Watchlist gesynct") → nach Lauf erscheint die
  **volle** (analysierte) Karte. Live zu prüfen: echter PUT am Gerät, gesperrte-Session-
  Dialog, „noch nicht gesynct"-Chip bei Offline. **Teil-Entschärft (dieser PR,
  „Sofort-Karte"):** ein neu hinzugefügter Ticker zeigt ab sofort eine Karte mit
  **Live-Kurs** (client-seitig, Quote-Worker) statt leer/nur Chip — die
  Elliott-Analyse (Setup/Score/Wellen) folgt weiterhin erst aus dem Lauf. Die
  Server-Runde (Token + Lauf) bleibt unverändert live zu prüfen.
- **OFFEN — Multi-Timeframe-Panel live (#PR-B):** greift erst mit echten
  Watchlist-Tickern (`watchlist_personal.json` aktuell `[]`) nach einem Lauf mit
  echten Monatsdaten. Offline/synthetisch belegt (Node-Harness + pytest): Panel
  rendert drei Zeilen Tag/Woche/Monat, null → „kein valider Long-Count". **Live zu
  prüfen:** echte yfinance-`1mo`-Daten je `.DE`/US-Titel (Datenlage ≥ 60 Monate),
  Panel-Optik am realen Ticker, `.DE`-Monatshistorie-Verfügbarkeit.
- **✅ ERLEDIGT — Push-Paket Stufe 1 scharfgeschaltet (#22):** Das Secret
  **`NTFY_TOPIC`** ist gesetzt und **funktioniert nachweislich** — Easy hat das
  Topic seit 23.07. abonniert, es kamen real 2 Benachrichtigungen an.
- **⚠️ FUND 27.07. — das Secret war nur in DREI von vier Steps verdrahtet.**
  `daily.yml` reichte `NTFY_TOPIC` an „Self-monitor push", „Push bei
  Lauf-Fehlschlag" und (in `staleness_check.yml`) an den Staleness-Step durch —
  **nicht** an den Step **„Run pipeline"**. GitHub Actions vererbt Secrets
  **nicht** automatisch in Steps: nur was im `env:`-Block des Steps steht,
  landet im Prozess. Der Name war nie das Problem (überall identisch
  `NTFY_TOPIC`), es fehlte allein das Mapping.
  **Folge:** beide Push-Zweige, die INNERHALB der Pipeline leben, waren still —
  der **Score-Alert >90** (#24) **seit seinem Bau** und der **Health-Check
  Stufe 2** (#51) von Anfang an. Beide sind fail-soft: leeres Topic →
  `send_ntfy` loggt „kein NTFY_TOPIC" und gibt `False` zurück. **Kein Fehler,
  keine rote CI, kein Hinweis** — genau die Defekt-Klasse, gegen die der
  Health-Check gebaut wurde, eine Ebene tiefer.
  **Praktisch verloren ging nie ein Push:** kein Kandidat erreichte je >90
  (Höchststand 89,84) und der erste Health-Lauf meldete `ok`. Die Verdrahtung
  war trotzdem tot. Behoben + Regressionsnetz
  (`tests/test_workflow_push_wiring.py`: startet ein Step ein Skript, das das
  Topic liest, muss er es setzen — der Test wurde gegen den kaputten Zustand
  gegengeprüft und schlägt dort fehl). Zusätzlich ein **Bestätigungs-Push**
  (`notify.py --mode selftest`, nur per `workflow_dispatch`-Schalter
  `push_selftest`, nie automatisch, priority `low`).
- **OFFEN — Score-Alert >90 live beobachten (dieser PR):** greift erst, wenn ein
  Kandidat real **>90** erreicht. **Frequenz-Messung über die GESAMTE committete
  Report-Historie (Universum 361): 0 Kandidaten je >90**, Höchststand **89,84**
  (PANW, aktueller Lauf) — also **de facto stumm** (aligned mit „bewusst fast
  stumm", KEIN Mini-Stopp nötig). Scharfschalten = dasselbe Secret **`NTFY_TOPIC`**
  wie #22. Zustellung aus der Sandbox nicht testbar (Netz).
- **TEILWEISE — Lauf-Status-Ansicht:** der #19-Dispatch-Lauf (`8a7d390`) hat
  `report.json` **mit** `diag` committet → die Ansicht sollte jetzt echte Zahlen
  zeigen (im UI noch gegenzuprüfen).
- **OFFEN — Health-Check Stufe 2 im echten Lauf (dieser PR):** nach dem Merge
  `daily.yml` dispatchen und nachtragen: **welche Regeln real feuerten (Soll:
  keine)**, **Laufzeit-Delta** (erwartet ~0 — die Prüfung ist ein Baum-Durchlauf
  über ~80 KB, plus EIN zusätzlicher `write_report`) und ein **Beweis-Lauf mit
  künstlich injiziertem NaN**, dass die Prüfung `crit` meldet. Offline
  vorbereitet: die Regeln wurden über die **letzten 15 committeten Reports
  zurückgespielt → 0 Fehlalarme**, der synthetische Voll-Lauf meldet `ok`, und
  der UI-Block ist headless in allen Zuständen (ok/warn/crit/gated/legacy)
  belegt. **Push-Zustellung** braucht wie #22/#24 das Secret **`NTFY_TOPIC`** —
  ohne Topic ist der Health-Check **still**, aber der `health`-Block im
  Lauf-Status zeigt den Zustand trotzdem (bewusst: Sichtbarkeit hängt nicht am
  Push).
- **✅ ERLEDIGT — Nicht-finit-Härtung (Folge-PR zu #51, 27.07.).** Die
  #51-Fundstellen-Liste ist **vollständig abgearbeitet**; alle Guards laufen
  jetzt über EIN Prädikat (`scripts/numeric.finite`). **`health_check` nutzt es
  seit dem 29.07. wirklich** (bis dahin eine eigene, wortgleiche Fassung —
  die frühere Formulierung „geteilt mit `health_check`“ war falsch). Abgehakt:
  `elliott_pipeline._volume_profile` (`s <= 0` / `vb <= 0` → `finite`, Segment
  mit Lücke liefert `null` statt gemitteltem Wert) ·
  `elliott_pipeline` Z. 901/903/981/983 (`round(x,4) if x is not None` →
  `if finite(x)`) · `elliott_pipeline._invalidation_bonus` (`close <= 0`) ·
  `elliott_pipeline._fib_proximity_bonus` (NaN-Retrace → NaN-Bonus → NaN-Score) ·
  `forward_collection.mature_record` (`c <= inval` — Fehlbar wird übersprungen
  und gezählt, gereift wird über 10 **gültige** Bars) ·
  `forward_collection` `if entry` (truthy) und `risk > 0` ·
  `forward_collection._alternation_fields` (`retr`-Nenner + `diff`) ·
  `forward_collection._roc` (`prev == 0`) ·
  `forward_collection.observe_a_correction`/`observe_w5_structure`
  (`w5_len <= 0` + Fenster-Finitheit) · `forward_collection.market_regimes`
  (`dropna` ließ ±Inf durch).
  **Zusätzlich zwei Quell-Defekte gefunden, die niemand auf der Liste hatte:**
  `dropna` schnitt die Datumsliste nur **vorne** ab → eine Lücke in der Mitte
  verschob **jedes** Datum danach (Pivot-Daten, `chart_points`,
  Sparkline-Achsen, eingefrorene Pivots); und die Volumen kamen aus dem
  **ungefilterten** Frame (zweiter Versatz). Beide behoben durch EINEN
  ausgerichteten Parse-Durchgang (`_extract_bars`).
  **Population belegt unverändert:** ALT vs. NEU über **25 committete
  Sammlungs-Stände / 341 Reifungs-Läufe** → **0 Abweichungen** (Registry-Eintrag
  27.07.). Diag: `dropped_bars` / `invalid_volume_bars` je Markt, sichtbar im
  Lauf-Status (Zeile erscheint nur, wenn es etwas zu melden gibt).
  **Guardian-Nit eingearbeitet:** `observe_w5_structure` fehlte das
  `all_finite(fwd)`-Pendant seiner beiden Schwester-Funktionen (gleiche
  Fenster-Logik `high = max(fwd)`); nachgezogen samt Test, der die drei
  Funktionen ab jetzt auf dieselbe Fenster-Regel festnagelt.
- **✅ ERLEDIGT — `dead_tickers`-Hygiene nach #19-Lauf** (Run 30002584301,
  Pipeline 85 s / Job ~1,7 min): `fetch_error=0` beide Märkte. `empty_data`
  namentlich — US: `MMC`, `FI`, `HES`; DE: `1COV.DE`, `CTS.DE`, `UN01.DE`,
  `SHA.DE`, `COP.DE`. **Achtung:** Mix aus echten Delistings (`HES`→Chevron,
  `1COV.DE`→ADNOC) und **transienter Yahoo-Drosselung** bei gültigen Größen
  (`MMC`,`FI`,`CTS.DE`,`SHA.DE`). **Nicht nach einem Lauf löschen** — über 2–3
  Läufe beobachten, nur konsistent Leere entfernen.

---

## 4. WARTESCHLANGE / ROADMAP (Stand 27.07.2026)

**AKTUELLE WARTESCHLANGE (Stand 05.08.2026) — der Fahrplan ganz oben ist die
verbindliche Reihenfolge, nicht diese historisch gewachsene Liste.** Offen sind
danach noch drei Punkte, in dieser Reihenfolge: **(3) Sitzungs-Ende-PR**
(Wächter-Erwartung auf den letzten *beendeten* Handelstag, markt-eigene
Schlusszeiten mit DST; crit→warn-Herabstufung des 04:46-Falls gehört in den
PR-Text) → **(4) Invalidierungs-Abstand** (gleiches Muster wie der
Zonen-Abstand, dieselbe neutrale Farbe) → **(5) Watchlist-Sync-Fix** (Befund
vom 04.08., muss LAUT werden). Zusätzlich **ohne Auftrag** vorgemerkt: die
**Marker-Entscheidung** vor der ersten echten Auswertung — `episode_split_suspect`
und `stale_market_suspect` gehören in **eine** Entscheidung, drei Records tragen
beide Marker.

**✅ Health-Check Stufe 2 — erledigt (dieser PR, `scripts/health_check.py`):**
Stufe 1 meldet **Absturz** und **Ausfall**. Stufe 2 schließt die Lücke
**„technisch erfolgreich, inhaltlich Unsinn"** — sechs Plausibilitäts-Regeln am
Lauf-Ende, gebündelt in **EINEN** flankengetriggerten ntfy-Push.
**Anlass (Lehre aus dem Schwester-Repo, 27.07.):** dort erzeugte ein Fetch-Pfad
**NaN statt None**; NaN passiert **alle** `is not None`-Guards und **jeden**
Vergleich (`nan <= 0` ist False), der Fehler lief zwei Tage still weiter.
**Elliotts Schadensbild ist ein anderes und schlimmeres** (empirisch geprüft):
`json.dump` schreibt `NaN` literal → **kein gültiges JSON** → `JSON.parse` im
Browser wirft → die PWA lädt gar nicht mehr. Deshalb prüft Regel 1 mit
`math.isfinite` (nicht `is not None`) und **vor** beiden Serialisierungen
(Report **und** Sammlung).
**Regeln:** (1) nicht-finit `crit`; (2) Vollständigkeit — 0 Top-Einträge `crit`,
< `HEALTH_MIN_CANDIDATES` `warn`; (3) Fetch-Qualität > `HEALTH_MAX_FETCH_ERROR_PCT`
und Tote-Ticker-Delta > `HEALTH_MAX_DEAD_DELTA` `warn`; (4) Sammlung weder
gewachsen noch verlängert `warn` (**#21-Netz**); (5) < `HEALTH_AGENT_MIN_OK`
KI-Kommentare **trotz** gesetztem Secret `warn` (ohne Secret: kein Befund).
(6) **Push-Disziplin:** Flanke statt Zustand — neu **oder verschlechtert** →
Push; unverändert **still**; `warn` frühestens nach `HEALTH_WARN_REPEAT_RUNS`
Läufen erneut; `crit` sofort, danach still bis zur Änderung; Erholung gibt den
Marker frei. State in `data/health_state.json` (von `daily.yml` mitcommittet —
**ohne Persistenz wäre jeder Lauf eine neue Flanke**). Wochenend-/Feiertags-Gate;
an gegateten Tagen wird der State **bewusst nicht** fortgeschrieben, sonst
verschluckt der nächste Handelstag den Befund.
(7) **Transparenz:** additiver Block `report["health"]` (Status, Befunde,
Schwellen) in der **Lauf-Status-Ansicht** — ohne `NTFY_TOPIC` die einzige
Sichtbarkeit.
**Grenzen (bewiesen):** ändert **nie** Daten; bricht den Lauf **nie** ab (drei
eigene `try`-Blöcke, der Report ist längst geschrieben, bevor der Health-Block
in einem **zweiten** `write_report` ergänzt wird); Score/Ranking/Filter/Reifung
unberührt — der Report ist mit und ohne Health-Check identisch **bis auf den
`health`-Schlüssel** (Test). **Schwellen sind Betriebs-Parameter, keine
Auswertungs-Definitionen** (Registry-Notiz 27.07.).
**Zusatz außerhalb der Aufgabe (bewusst, im PR begründet):** der bestehende
`daily.yml`-Schritt „Validate report JSON" liest jetzt **strikt** (`parse_constant`)
— NaN/Infinity lassen den Lauf dort **laut scheitern**, statt unparsebare Daten
zu committen. Der letzte gute Report bleibt dann stehen (Staleness-Hinweis im
Frontend) — besser als eine PWA, die gar nicht mehr lädt.
**Guardian-Nits (27.07., alle eingearbeitet):** (1) **Regel 4 feuerte beim
zweiten Dispatch DESSELBEN Kalendertags** — ein ausdrücklich vorgesehener
Retry-Pfad, an dem die Episoden-Logik die heutigen Records idempotent erneut
setzt, die Signatur also zwangsläufig gleich bleibt. Reproduziert und gefixt
(`same_day_rerun`, aus `coll["last_run_date"]` VOR dem Update). (2)
`write_report` war **nicht atomar** (`open("w")` truncierte sofort) — dieser PR
verdoppelt das Zeitfenster durch den zweiten Schreibvorgang, also jetzt
Temp-Datei + `os.replace`; Ergebnis-Bytes unverändert. (3) toter Ternär-Zweig in
`evaluate_edges` entschärft.
**Bekanntes, akzeptiertes Rauschen (Guardian, nicht gefixt — bewusst):**
Regel 2 meldet an ruhigen Markttagen mit nur 1–2 echten Setups ein `warn`
(genau so gewollt: „wenige Kandidaten aus hunderten Titeln" IST der Fall, für
den diese Stufe existiert). Und wenn die strikte `daily.yml`-Validierung greift,
kommen an dem Tag **zwei** Pushes (spezifischer Health-Push + generischer
Lauf-Fehlschlag) und `health_state.json` wird **nicht** committet (der
Commit-Schritt läuft bei rotem Job nicht) — Folge: Befunde dieses Tages gelten
beim nächsten Auftreten wieder als „neu". Konsequenz ist mehr Sichtbarkeit,
nicht weniger.
**Belege:** 48 neue Tests (264 → **312**); Regeln über die **letzten 15
committeten Reports** zurückgespielt → **0 Fehlalarme**; synthetischer Voll-Lauf
`ok`, auch der **zweite Lauf am selben Tag** (Retry-Pfad) meldet `ok`;
**NaN-Injektions-Beweis am echten committeten Report**: `crit` mit exakten
Pfaden → high-Priority-Push → literales `NaN` im serialisierten JSON → strikte
`daily.yml`-Validierung lehnt ab (ganze Kette offline durchgespielt);
UI headless in allen Zuständen (ok/warn/crit/gated/legacy, XSS-Escaping,
390 px, kein H-Scroll). Revert = `scripts/health_check.py` + die drei
`try`-Blöcke in `main()` + `HEALTH_*` in `config.py` + `.health-box`-CSS/Renderer
+ die zwei `daily.yml`-Zeilen raus (rein additiv, keine Datenreste außer
`data/health_state.json`).
**Nach Merge:** `daily.yml` dispatchen → welche Regeln feuerten (Soll: keine),
Laufzeit-Delta, NaN-Injektions-Beweislauf (Abschnitt 3).

**✅ Heartbeat-Push — erledigt (dieser PR, `scripts/health_check.py`):**
Bisher meldete sich das Tool NUR bei Problemen. Der OK-Push schließt die
Lücke — und zwar als **Herzschlag**: bleibt er aus, ist der Lauf
ausgefallen. Das ist bewusst NICHT dieselbe Mechanik wie der
Staleness-Wächter: der läuft in einem eigenen Cron und hängt damit an
derselben Infrastruktur wie das Bewachte — fällt der GitHub-Scheduler aus,
schweigen beide (beobachtet 27.07.).
**Genau EIN Push pro Lauf** (harte Regel, testgesichert): Befund-Meldung
(prio high/default) ODER Herzschlag (prio low), nie beides. Ein anhaltender
Befund, dessen Flanke schon gemeldet wurde, lässt den Herzschlag ebenfalls
NICHT einspringen — sonst käme ausgerechnet bei einem laufenden Problem ein
„Lauf ok".
**Inhalt** (gegen den echten Lauf gegengerechnet): `🇺🇸 43 Kandidaten (Top
AMAT 86) · 🇩🇪 23 Kandidaten (Top TKA.DE 77) · Sammlung 27 / 0 gereift / 0
auswertbar — heuristisch · unvalidiert`, bei Meilenstein eine zweite Zeile.
Der Vorbehalt steht an der Zahlen-Zeile (Projekt-Invariante: keine Zahl
ohne ihn nach außen).
**Gates:** Wochenende/Feiertag (bestehendes `push_gated`) **und nur `main`**
(`GITHUB_REF == refs/heads/main`) — ein Test-Dispatch vom Feature-Branch
darf keinen Puls erfinden, sonst ist „kein Push = Lauf ausgefallen" wertlos.
Lokal (ohne `GITHUB_REF`) ebenfalls still.
**Meilensteine:** Überschreiten eines Vielfachen von
`HEARTBEAT_MILESTONE_STEP` (25) bei gesammelt/gereift/auswertbar. Der
Zähler-Stand wird im bestehenden `health_state.json` fortgeschrieben — aber
**nur wenn ein Herzschlag wirklich rausging**, sonst verschluckt ein
übersprungener Lauf den Meilenstein für immer (Test).
**Konstanten:** `HEARTBEAT_ENABLED` (true), `HEARTBEAT_FREQUENCY`
(`daily`|`weekly`) + `HEARTBEAT_WEEKDAY`, `HEARTBEAT_MILESTONE_STEP`.
Revert = `heartbeat_*`/`send_heartbeat`/`is_main_run` + der Herzschlag-Zweig
in `run()` + der `HEARTBEAT_*`-Block in `config.py` + `counts=`-Durchreichung
raus (rein additiv, der `heartbeat`-Schlüssel im State ist folgenlos).
**Guardian-Nit eingearbeitet (28.07.):** Tages-Bremse — EIN Puls pro
Kalendertag, nicht pro Lauf. Mehrere Dispatches am selben Tag sind ein
vorgesehener Pfad (Retry, Recalculate-Button); ein Herzschlag, der bei
jedem Tap erneut schlaegt, ist als Taktgeber wertlos. Die Bremse gilt NUR
fuer den Puls: ein spaeterer echter Befund am selben Tag wird gemeldet.
**Bekannte Systemgrenze (Guardian, bewusst nicht geaendert):** an dem
einen Tag, an dem gleichzeitig ein Sammlungs-Meilenstein und der
n>=100-Meilenstein aus #22 (`notify.py --mode daily`, eigener
Workflow-Step) faellt, kommen zwei leise Pushes. Einmalig, kein
Fehlsignal — eine Zusammenlegung wuerde die #22-Logik anfassen.
**Nach Merge:** `daily.yml` von `main` dispatchen und den erzeugten
Push-Text wörtlich nachtragen.

**✅ Push-Paket Stufe 1 — erledigt (#22, `scripts/notify.py`):** ntfy, bewusst
fast stumm. Anlässe: **Lauf-Fehlschlag** (`if: failure()` in daily.yml),
**Staleness** (separater Cron `staleness_check.yml`, erkennt den ausgefallenen
Lauf), **Meilenstein n ≥ 100** (einmalig, Marker-Datei), **`review_by`-Wecker**
(~1×/Woche). **Bewusst NICHT gebaut:** Invalidierungs-Riss-/Kandidaten-/Tages-
Pushes (Risse bleiben lautloser ✗-Status im Backtesting). Scharfschalten:
Secret `NTFY_TOPIC` setzen (Abschnitt 3).

**✅ Mini-Sammler — erledigt (#23):** Disclaimer-Banner (dezent, einklappbar,
localStorage `elliott_disc_collapsed`) · Wochenend-Gate (Cron `45 21 * * 1-5`) ·
Feiertags-Gate (gemeinsame NYSE∩Xetra-Voll-Schließtage in
`scripts/market_calendar.py`, mit Ablauf-Warnung ab 01.12.2027) ·
**kalenderbewusste Staleness** (Wächter rechnet gegen den letzten *erwarteten*
Lauf → kein Wochenend-/Feiertags-Fehlalarm).

**✅ Score-Alert >90 — erledigt (dieser PR, `forward_collection.score_alert_edges`
+ `notify.send_score_alert`):** EINMALIGER Push, wenn ein Kandidat in SEINER
Episode **neu** über `SCORE_ALERT_THRESHOLD` (=90) steigt (**Flanke, nicht
Zustand**). An DIESELBE Episoden-Erkennung wie der N×-Zähler gekoppelt (kein
Parallel-State): der Record der heutigen Erscheinung trägt `last_seen == run_date`,
das Flag `score_alert_fired` wird je Episode **einmalig** gesetzt und in der
Sammlung persistiert. Gebündelt (**1 Push/Lauf**), Markt im Text, trägt
„heuristisch · unvalidiert". Watchlist ausgenommen, fail-soft. **Lektion aus dem
Schwester-Repo (dortiger PR #471, 23.07.): Cooldowns ohne Flanken-Logik
re-alarmieren bei anhaltendem Zustand → Push-Flut.** Deshalb hier von Tag 1:
Flanke. Revert = Konstante entfernen / `edges`-Aufruf in `main` streichen (rein
additiv, Feld verschwindet beim nächsten Purge-Lauf).

**✅ Watchlist-Sofortkarte — erledigt (#25, Frontend):** lokal hinzugefügter Ticker
zeigt sofort eine Live-Kurs-Karte (`_wlInstantCard`) statt leer/nur Chip; volle
Elliott-Analyse weiter aus dem Lauf.

**✅ Multi-Timeframe-Analyse Watchlist — erledigt (dieser PR = „PR B", Herkunft:
Code-Vorschlag aus der #25-Session, von Easy freigegeben 23.07.):** je Watchlist-
Titel DREI Zählungen — Tag (bestehende Swing-Logik), Woche (bestehender Wochengrad),
NEU **Monat** (`interval=1mo`, `period=max`; Mindest-Datenlage
`config.MIN_BARS_MONTHLY=60` Monatskerzen = 5 Jahre → sonst fail-soft null).
Additives Feld `timeframes`{day,week,month} je Eintrag (jeweils {count_label,
invalidation_price, target_zone, target_zone_extended} oder null); Analyse-Panel
(`tfPanel`) auf der Karte mit drei Zeilen, null → dezent „kein valider Long-Count".
Reuse der ZigZag-/Regel-/Zielzonen-Mechanik über die geteilten Helfer
`_count_from_series`/`_count_from_fetch`. **Markt-Top-5, Score, Ranking,
forward_collection, Score-Alarm beweisbar unberührt** (Monatsgrad NUR Watchlist,
Watchlist bleibt außerhalb der Validierungs-Population). Laufzeit: bis zu **+2
Fetches je Watchlist-Titel** (Woche+Monat; Tag reust die geladene Tagesreihe) —
bei aktueller Liste (`watchlist_personal.json` = `[]`, 0 Titel) heute +0; Cap
`WATCHLIST_MAX=30` → höchstens +60. Revert = reiner Diff-Revert (Feld additiv).

**✅ Token-Session-Remember — erledigt (dieser PR, `docs/index.html`):** einmal
Master-PW entsperren → **28 Tage** (`TOKEN_SESSION_DAYS`) still, danach schlicht
wieder der PW-Dialog. IndexedDB-Session-Wrap nach Squeeze-Vorbild
(easywebb911/Aktien-Update), aber mit **non-extractable** Session-Key (sicherer
als Squeeze's rohe Key-Bytes) und **fester Frist** statt Rolling. Greift für
Recalculate UND Watchlist-Speichern (kein Doppel-Dialog); „Sperren"-Menüpunkt
beendet sofort. Klartext-Token nie persistiert. **Herkunft: Option 1 (Session-
Entsperrung) nach Risiko-Abwägung, Easy 23.07.** — bei PR #15 bewusst weggelassen,
jetzt portiert. Verifiziert: 14/15-Playwright-Zyklus (der eine „Fail" = externe
Quote-Worker-Netzfehler, nicht der Code). Revert = reiner Frontend-Diff-Revert.

**✅ Validierungs-Integrität / PRU-Guard — erledigt (dieser PR):** Grundlage =
Read-only-Diagnose 23.07. (PRU stand mit Kurs 117,4 **über** Zielzone 112,4–116,2,
rankte auf Platz 3, Score 84; die Reifung zählte solche Fälle als `target_hit` an
**Tag 1** — Treffer-Aufblähung der Validierung; 3 Records MET/D/PRU real betroffen).
Easy 23.07.: **Stufe 1 = Guard + Ausweisung + Badge** (Filter separat/später,
Score-Malus verworfen). Gebaut: (1) **Guard** in `mature_record` — `target_hit`/
`ext_hit` nur wenn `entry_close < Zonen-Low`, sonst gesperrt (0) + `pre_reached_*`;
Invalidierung/Kennzahlen bleiben voll gültig. (2) **Pre-guard-Ausweisung**
(forward-only, nichts gelöscht): MET/D/PRU mit `pre_guard_contaminated: true` im
Datenbestand markiert; `is_excluded`/`eval_counts` (auswertbar = gereift ohne
Ausschluss); Registry datiert (23.07.). (3) **Badge** „Zielzone erreicht"
(≥ low) / „überschritten" (≥ high), dezent, kein Alarm-Rot, Live-Quote aktualisiert
(`_setZoneBadge` in `quotePatch`); Panel zeigt „…· N auswertbar" + Tooltip.
**Grenzen:** kein Filter, kein Score-/Ranking-Eingriff (report.json byte-identisch,
belegt), SCHEMA_VERSION bleibt 1. Revert = Guard-Zeilen/Feld/Badge entfernen; die
`pre_guard_contaminated`-Marker sind rein additiv.

**✅ ENTSCHIEDEN & gebaut (dieser PR) — Filter `target_exceeded`:** Easys Produkt-
entscheidung (23.07., PRU-Diagnose). Setup mit Lauf-Schlusskurs **`≥ target_zone.low`**
(„Zielzone erreicht" = nicht mehr handelbar) wird in `build_candidate` VOR dem
Ranking verworfen (Skip-Grund `target_exceeded`, eigener Diag-Zähler, Lauf-Status-
Chip); Rang 6+ rückt nach. **NUR Markt-Top-5** — die Watchlist ruft
`build_candidate(..., exclude_target_reached=False)` und zeigt weiter alles (#28-
Badge markiert den Zustand). Schwelle **identisch** zur #28-Guard-/Entry-Regel.
**Verteidigung in der Tiefe:** Filter verhindert Neuanlagen über Zone, der
#28-Guard bleibt als zweites Netz (schützt die Messung, falls doch je einer
durchkommt). Registry: Populations-Änderung **datiert** (23.07.). Score/Ranking-
Formel unverändert; nur die Grundgesamtheit verengt sich auf handelbare Setups.
Revert = `exclude_target_reached`-Zweig + Konstante `TARGET_EXCEEDED` entfernen
(rein subtraktiver Filter, keine Datenreste). Nach Merge: `daily.yml` dispatchen,
`target_exceeded`-Zähler + neue Top-5-Besetzung + Nachrücker-Scores nachtragen.

**✅ ☰-Menü an Squeeze angeglichen — erledigt (#32, `docs/index.html`):**
Easy 24.07.: Struktur + Design des ☰-Panels ans Schwester-Repo (Aktien-Update,
`app.html`) angleichen — abgerundete Icon-Kacheln + Label, großzügige Zeilen,
Fuß-Trennung — aber **eigene Farbwelt** (das Karten-/Sparkline-Grün `--grn` statt
Squeeze-Blau) und **nur real vorhandene** Elliott-Funktionen (keine Platzhalter).
Neue Reihenfolge: **Reload** (neu im Menü, primär hervorgehoben — der Header-Button
„↻ Neu laden" entfällt, gleiche `refresh()`+Cache-Buster) · Recalculate · Backtesting
· Methodik · Validierung · Lauf-Status · Trenner · Sperren. Einheitliche inline-SVGs
(lucide-Vorbild, **keine** externe Lib). Panel-Verhalten (öffnen/schließen, Overlay-
Navigation) unverändert; Live-Poller/`data-quote`-Anker unberührt. **Bewusst NICHT
gebaut** (Squeeze-Funktionen ohne Elliott-Pendant): Agent Run, Trade-Journal,
Push-Historie, Score-Sortierung, Chat, Schrift-/Theme-Buttons. Verifiziert: alle 7
Einträge headless durchgeklickt (Reload → Toast + frischer Stand; Recalc → Token-
Modal; Backtesting/Methodik/Validierung/Lauf-Status → Overlay; Sperren → kein Crash);
Konsole nur mit erwarteten externen Quote-Netzfehlern (Sandbox). Revert = reiner
Frontend-Diff-Revert (Header-Button + alte Emoji-Einträge zurück).

**✅ Watchlist im Kompakt-Grid — erledigt (#33, `docs/index.html`):** Easy 24.07.
(Bild-Freigabe-Runde zu #32): die Watchlist-Karten im Squeeze-Kompakt-Stil. Grid
`repeat(auto-fill, minmax(112px,1fr))` (~3 Kacheln/Reihe @390px); je Kachel ein
**Mini-Score-Donut** (`wlMiniDonut`, 32px, `scoreColor`-Skala) **oder dezentes „—"**
ohne validen Count (kein Fake-Score), **Mono-Ticker**, **Trend-Punkt** (grün/rot aus
`chart_points`-Richtung), **×** (entfernen), **▾** (aufklappen). **Standard
EINGEKLAPPT** — die volle Elliott-Karte (via bestehende `watchlistCard`/`card`/
`_wlInstantCard`, unverändert) erscheint erst beim Aufklappen im `.wl-tbody`, die
Kachel spannt dann eine ganze Grid-Reihe (`[data-open]`), mit „▴ Einklappen"-Leiste.
**Zustand pro Gerät** in `localStorage['elliott_wl_expanded']` (Set von Tickern);
`_wlToggle` schaltet den DOM direkt (kein Re-Render → Live-Quotes/Scroll bleiben),
zeichnet beim Aufklappen die Sparkline neu. **Sofortkarte (#25) bleibt:** neuer
Ticker wird beim Hinzufügen auto-aufgeklappt → Live-Kurs sofort sichtbar. Farbe
Elliott-eigen (`--grn`, grün getönte Kachel-Ränder). Poller unberührt — die
`.card[data-ticker]`-Einheit lebt weiter im `.wl-tbody`, das Tile-Wrapper trägt nur
`data-tile`. Verifiziert headless (390px): 3 Kacheln eingeklappt, Donut vs. „—",
Auf-/Zuklappen, Persistenz über Reload, Add→auto-offen (pending), Remove über ×;
keine Konsolen-Fehler (außer externem Quote-Netz). Revert = reiner Frontend-Diff-
Revert (Kacheln zurück zu vollen `.card`s, `wl-grid`→`grid`).

**✅ 3D-Karten-Look + blaue Watchlist-Tönung — erledigt (dieser PR, `docs/index.html`,
reines CSS):** Squeeze-Vorbild „Variante 1B" (Aktien-Update `app.html`) portiert —
abgelesene Stilmittel: 2-Stop-Vertikal-Gradient (`rgba(255,255,255,.05)`→`rgba(0,0,0,.10)`,
app.html:556), Drop-Schatten + **Inset-Kanten-Highlight** (`0 2px 8px … , inset 0 0 0
.5px rgba(255,255,255,.05)`, app.html:558) und der Hover-Lift der Kachel (app.html:695).
**Einheitliche Tiefen-Sprache** auf drei Flächen: `.card` (Markt + Setup-Watchlist),
`.wl-tile` (Kompakt-Grid, Hover hebt an), `.wl-tile[data-open]` (aufgeklappt). Elliott
hatte den Gradient schon — NEU ist überall das Inset-Highlight (der eigentliche 3D-Reiz);
Drop-Alpha an den dunkleren Elliott-Canvas angepasst (Struktur portiert, nicht erfunden).
Tiefe auf Easys Wunsch **einen Tick angehoben**: tieferer Drop (`0 4px 14px rgba(0,0,0,.45)`)
+ zusätzlicher oberer **1px-Licht-Grat** (`inset 0 1px 0 rgba(255,255,255,.07)`); Hover kräftiger.
**Aufgeklappte Watchlist-Karte:** dezent **blaustichige** Tönung (`rgba(96,165,250,.06)`
+ Blau-Border `.40`; Technik wie Squeeze `.card-manual`-Tönung app.html:698, Farbe
Elliott-eigen = Akzent-Blau) → auf einen Blick von den neutralen Markt-Karten
unterscheidbar; innere `.card` transparent, damit die Tönung durchscheint. **Kontrast
belegt** (WCAG auf der Tönung: txt 11:1, txt-sub 5,4:1, grn 6,1:1, ora 6,5:1; die
dezenten Mikro-Labels `--txt-dim` ~2,9:1 wie schon auf der neutralen Karte — Blau senkt
sie nur marginal, daher .06 statt .08). `prefers-reduced-motion` respektiert (Hover-/
Caret-Transition aus). Keine Dauer-Animation auf Schatten, iOS-Safari-tauglich (nur
box-shadow/gradient, kein filter/backdrop-filter). Verifiziert: Vorher/Nachher-
Screenshots aller drei Flächen (390px), Konsole sauber, Tests grün (202). Revert =
reiner CSS-Diff-Revert (box-shadow/background der drei Regeln + reduced-motion-Block).

**✅ KI-Kommentar standardmäßig eingeklappt — erledigt (dieser PR, `docs/index.html`,
reines Frontend):** Der Agent-Kommentar ist ein **Zusatz** — die ruhige Karte bleibt
der Normalzustand. `agentBlock` rendert die Sektion jetzt als **`<details>` OHNE
`open`-Attribut** (Default eingeklappt): `<summary class="agent-summary">` trägt
kompakt „KI-Kommentar · heuristisch" + Chevron; **Lesart, Gegenargument und
Modellname erscheinen erst nach aktivem Öffnen** (`.agent-body`). **Muster** (aus dem
Squeeze-Schwester-Repo bestätigt: „Score-Methodik-Panel UX (Accordion-Redesign)";
im Elliott-Report bereits Haus-Muster bei der Ambiguitäts-Alternative aus #43):
HTML5 `<details>/<summary>`, **Chevron-Rotation per CSS über den `[open]`-Selector**
(`.agent-block[open] .agent-summary::after {transform:rotate(90deg)}`) — **kein
animiertes `height`**, deshalb **kein Layout-Sprung**; `list-style:none` +
`::-webkit-details-marker{display:none}`; **Tap-Ziel `min-height:44px`**;
`prefers-reduced-motion` schaltet die Chevron-Transition ab (gemeinsame Regel mit
`.amb-summary`). Zustand je Karte **unabhängig**, bewusst **ohne Persistenz** über
Reload. **null-Fall unverändert:** kein Kommentar → **gar keine Sektion**, auch keine
leere Kopfzeile. **Verifiziert (390px, headless, am ECHTEN Lauf `48665a4`):** 5 Karten
/ 4 Sektionen (die auf `null` gesetzte Karte zeigt nichts); alle default `open=null`,
Body unsichtbar; Summary-Höhe exakt **44px**; Öffnen von Karte 2 lässt Karte 1 und 3
zu (unabhängig) und verschiebt **nichts oberhalb** (Dokument-Koordinaten 416→416 bzw.
1065→1065); Chevron dreht (`matrix(0,1,-1,0,0,0)` vs. `none`); Schließen funktioniert;
kein H-Scroll; Konsole sauber. Tests grün (264). Revert = `<details>/<summary>` zurück
zu `<div class="agent-block">`/`<div class="agent-head">` + die `.agent-summary`/
`.agent-body`-Regeln raus (Inhalt unverändert).

**✅ Agent-Kommentar v1 (KI) — erledigt (#49, `scripts/agent_comment.py` +
Pipeline/Sammlung/Frontend):** Easys KI-Entscheidung vom 26.07. — nächtlich **ein**
Anthropic-Aufruf je **finaler Markt-Top-5**-Karte (~10/Lauf; **Watchlist
ausgenommen**) liefert Klartext-**Lesart**, **stärkstes Gegenargument** und ein
messbares **`concern_level`** (`none`/`low`/`high`). Adaption der Squeeze-KI unter
Elliott-Disziplin; **bewusst NICHT übernommen:** Agent-Boost ins Ranking
(Squeeze-Re-Test: kein Edge), KI-Score, Stunden-Ticks.
**HARTE GRENZE (bewiesen):** der Schritt läuft in `main()` **NACH `build_report`**
— also nach Sortierung, Top-N-Schnitt und allen Filtern — und schreibt
ausschließlich das additive Feld `agent_comment`; Score/Ranking/Filter/Reifung
byte-identisch (`test_ranking_and_scores_byte_identical`; `set(nachher)-set(vorher)
== {"agent_comment"}`). **Modell/Konstanten:** `AGENT_MODEL =
claude-haiku-4-5-20251001`, `temperature 0`, `max_tokens 500`, `timeout 30 s`,
`AGENT_PARSE_RETRIES = 1`; HTTP über **stdlib-`urllib`** (keine neue Dependency —
`requests` steht nicht in `requirements.txt`). **Input:** ausschließlich eigene
Pipeline-Felder des Kandidaten (`build_facts`: Zählung, Zonen, Inval, Score,
`valid_count_total_v2`+Alternative, `vol_ratio_*`, Alternation-Rohwerte über die
geteilte `_alternation_fields`, Konfluenz, `appearance_count`, `change_pct`) —
**keine externen Fetches in v1**. **Output** strukturiert erzwungen (JSON,
Codefence-tolerant geparst); Parse-Fehler → 1 Retry → sonst `null`.
**Fail-soft total (ntfy-Muster):** fehlendes `ANTHROPIC_API_KEY` → **no-op**, Feld
gar nicht gesetzt + Log-Zeile; jeder API-Fehler → `null`, Lauf läuft weiter (der
Aufruf ist zusätzlich in `main()` in `try/except` gekapselt). **Key nie geloggt**
(Test mit Fake-Key + `capsys`). **Kosten-Log** je Lauf (Tokens in/out); Schätzung
**~$0,02/Lauf ≈ $0,42/Monat ≈ $5/Jahr** (Haiku-Tarif, ~1,1 k in / 180 out je
Kandidat). **Messung:** `agent_concern_level` + `agent_model` bei Episoden-**Anlage**
point-in-time eingefroren (LLM-Output ist **nicht deterministisch**; `temperature 0`
mildert, garantiert nicht) → Auswertungs-Frage n≥100: trifft `high` seltener?
Alt-Records `null`, kein Backfill. **Inhalts-Netz (Guardian-Nit):** `_parse_reply`
prüft den LLM-Freitext zusätzlich gegen `BANNED_PHRASES` (Wahrscheinlichkeits-/
Empfehlungs-Sprache) — Treffer = wie Parse-Fehler (Retry → `null`), belegt auf
Report-Ebene. **Registry datiert inkl. WÖRTLICHEM Prompt**
(auch der Prompt ist eine datierte Definition — Änderung ⇒ neue Version).
**Frontend:** dezente Sektion „KI-Kommentar" (Lesart + Gegenargument, grauer
`heuristisch`-Badge, Modellname klein); `concern_level` als **neutraler Text**
(„deutliche Einwände aus den Daten"), **NICHT als Ampel-Farbe** — das wäre
Score-Optik; fehlt das Feld, fehlt die Sektion. Verifiziert: 15 neue Tests
(Parse/Codefence/Retry/null/no-op/Token-Zähler/Freeze/Key-Leak/Grenze/
Bann-Wörter/kaputte API-Antwort), Suite
**245 → 264**, headless-Render (Sektion nur bei Kommentar, neutraler Stil, kein
Overflow @390px), Konsole sauber. `daily.yml` reicht das Secret durch (fehlt es →
Lauf verhält sich exakt wie vorher). Revert = `scripts/agent_comment.py` + der
`try`-Block in `main()` + die 2 Freeze-Felder + `agentBlock`/CSS + das `env:` raus.
**Nach Merge + gesetztem Secret:** `daily.yml` → 10 Kommentare? Beispiel wörtlich,
`concern_level`-Verteilung, reale Token-Kosten.

**✅ Elliott-Wellen-Banner + Chip-Zeile entfernt — erledigt (#48,
`docs/index.html`, reines Frontend):** (1) **Banner:** das von Easy freigegebene
SVG (v3) liegt **inline** im Markup (kein Asset, kein Fetch) zwischen Staleness-
Banner und Watchlist-Sektion — im Normalfall also direkt unter der Stand-Zeile,
Warnungen bleiben zuoberst. Dekorativ: `aria-hidden="true"`, `focusable="false"`,
`role`/`aria-label` entfernt, keine Interaktion. Responsive über die viewBox
(`svg{width:100%;height:auto}`), Wrapper `.ew-banner` mit `--radius` +
`overflow:hidden` (SVG-`rx:16` + Clip) und dezentem Abstand. **Alle 6 SVG-ids mit
`ewb-`-Präfix** (`ewb-bg/-wave/-fill/-glow/-fadeL/-fadeR`) — Kollisionsschutz
gegenüber den Sparkline-Defs (die zwar `sg…`-Zufalls-ids nutzen, aber die
generischen Namen wären eine Falle); per Grep vorab **und** headless auf doppelte
DOM-ids geprüft. (2) **Chip-Zeile entfernt:** `#wl-chips`-Markup, die `.wl-chip*`-
CSS-Regeln und `renderWatchlistChips()` sind raus — sie duplizierten nur die
Kacheln (deren `×`/`data-wl-remove` die eigentliche Entfernen-Geste ist). Ersatz:
`renderWatchlistCount()` (setzt weiter den Zähler `#wl-count` im Titel, 3 Call-
Sites umgestellt); der Empty-State „Noch keine eigenen Ticker." wandert in die
Kachel-Fläche (`renderWatchlistCards`, Guard bei leerer Liste). **Verifiziert**
(headless, echter Report `29d1e1e`): Banner @390px **und** Desktop unverzerrt
(ratio 6,16 == 1170/190), über der Watchlist, 6 `ewb-`-ids **ohne** Duplikate,
37 Sparkline-Pfade unverändert gezeichnet; Watchlist-Flows komplett grün — Add
(Sofortkarte + Auto-Sync geplant + persistiert), Reload-Persistenz, Entfernen über
Kachel-× (Kachel erst einklappen — bestehendes Design, `.wl-x` ist an der offenen
Kachel `display:none`); Konsole sauber, Tests grün (245). Revert = `.ew-banner`-
Block (Markup+CSS) raus; Chip-Zeile zurück = Markup `<div class="wl-chips">`,
`.wl-chip*`-CSS und `renderWatchlistChips()` aus der Historie (`git show`).

**✅ P4c-Audit: Sparkline-Achsen — erledigt (#47, `docs/index.html`, reines
Frontend; damit ist das EXZELLENZ-AUDIT P1–P4 KOMPLETT):** Die große Tages-Sparkline
(Markt + Watchlist) bekommt **dezente Eck-Werte** — minimale Verortung ohne
Chart-Bombast: **Hoch-/Tief-Preis** (rechts oben/unten) + **Zeitspanne** (Datum
erster/letzter Pivot, unten links/rechts, Kurzformat `TT.MM.JJ`). KEINE Gitterlinien,
KEINE Achsen-Striche. Umsetzung: `data-dates` an den 2 Big-Sparkline-Call-Sites
(aus den vorhandenen `chart_points`-Daten, kein neues Backend-Feld); im Renderer
NUR im `!el.dataset.h`-Zweig (→ **Grad-Minis (36px, P4b) bewusst OHNE** — zu klein);
`.spark-axis` = 7px SVG-px (skaliert nicht mit der Textgrößen-Steuerung, wie
`.wave-num`), Farbe `--txt-dim` (**WCAG AA** 5,9:1 seit #41), **Halo**
(`paint-order:stroke` in `--bg-card`) hält die Werte über Linie/Inval-Strich lesbar.
**Kollisions-Disziplin wie bei den Ziffern:** Preis-Labels prüfen gegen die gesetzten
`digitPos` (erste freie y-Kandidatin, sonst weglassen); die Datums-Zeile liegt unter
dem Plot (digit-frei, Ziffern nahe dem Rand wandern unter den Punkt).
`prefers-reduced-motion` unberührt (keine neue Animation). **Verifiziert** (390px,
headless, ECHTER committeter Report `29d1e1e`): AMAT-Eck-Werte exakt = Pivot-Daten
(Hoch 723 · Tief 322,72 · 25.02.26–07.07.26), **0 sichtbare Achse↔Ziffer-
Überschneidungen** über alle Karten, Minis ohne Achsen, Konsole sauber, Tests grün
(245). Revert = `data-dates`-Attribute + `axes`-Block + `digitPos`-Sammlung +
`.spark-axis`-CSS raus. Merge: reines Frontend → **self-merge bei grünem CI**.

**✅ P4b-Audit: Grad-Sparklines — erledigt (#46, `scripts/elliott_pipeline.py`
+ `docs/index.html`):** Wochen-/Monats-Zählungen bekommen die bewährte Tages-
Visualisierung als **Mini-Sparkline** — genau das Bild, dessen Fehlen Easys
AMAT-Monats-Verwirrung auslöste. **Pipeline (additiv, Schema v1):**
`_count_from_series` liefert zusätzlich `chart_points` = die letzten
**`DEGREE_CHART_PIVOTS = 8`** ZigZag-Pivots (Datum+Preis via `Pivot.as_dict`,
gezählte Struktur ≤5 + wenige Vorlauf-Pivots — bewusst klein, Tages-Sparkline
bleibt bei ihren 12) + `count_wave_labels` (index relativ zu chart_points, wave 0
= P0). Wirkt auf `timeframes.day/week/month` UND `higher_degree` (geteilter Pfad).
**Frontend:** `degreeSpark(count)` erzeugt `.spark-svg.spark-mini` mit `data-h=36`
— `drawSparkline` wurde um GENAU einen parametrisierten Höhen-Read erweitert
(ohne `data-h` byte-identisch 56) → **dieselbe Render-Technik** (Pivot-Punkte,
Wellen-Ziffern mit Kollisions-Weglassen, Inval-Linie im Sichtbereich, Count-
Abschnitt farblich abgesetzt). Einbau: Großer-Grad-Block der Markt-Karten + jede
Zeitebenen-Zeile mit Count. **Direkt sichtbar** statt ausklappbar (Begründung:
36px hoch stört @390px nicht, erspart Interaktion; verifiziert kein Overflow).
Fail-soft: <2 Punkte → kein Markup (nie leere Fläche). **Beweise:** Ziffern-
Invarianten am echten Pipeline-Pfad (Ziffer sitzt auf P0..Pk-1, chart_points ==
letzte ZigZag-Pivots, Setup-Konsistenz W2/W4; echte yfinance-Daten aus der Sandbox
nicht erreichbar → Realdaten-Stichprobe im Nach-Merge-Lauf); **Report-Diff rekursiv
nur additive `chart_points`/`count_wave_labels`** (Scores/Reihenfolge identisch);
Payload 51,7→79,2 KB formatiert (+27,5 KB synthetic — real nach Merge beziffern);
Tages-Sparkline H=56 unberührt, Minis H=36, Konsole sauber, Tests grün (245).
Revert = Konstante+2 Keys in `_count_from_series`, `degreeSpark` + 2 Einbau-Stellen
+ `data-h`-Read + `.spark-mini`-CSS raus. Merge: Guardian + Manual, keine Screenshots.
**Nach Merge:** `daily.yml` → Anzahl Live-Grad-Sparklines + realer Payload-Zuwachs.

**✅ P4a-Audit: ABC-Korrektur-Erkennung (Struktur-Vokabular v2) — erledigt (#45,
`scripts/` + `docs/index.html`):** Das Zähl-Vokabular kennt jetzt einfache
**Zigzag-Korrekturen (A-B-C)** — NUR für Watchlist-Struktur-Befund, ambiguity v2 und
die W5→A-Strukturmessung; **HARTE SCOPE-GRENZE eingehalten:** kein neuer Markt-Setup-
Typ, Markt-Report/v1-Felder/Reifung **byte-identisch** (rekursiver Diff: nur
`valid_count_total_v2`/`alt_count_v2` additiv). **Befund:** `_classify_structure`
(`elliott_pipeline.py`, 5 Kategorien, Präzedenz 6→5→3 Pivots), ambiguity v1
(`ambiguity_fields`), W5→A (`observe_a_correction`, forward_collection). **Gebaut:**
(1) `_detect_correction` (nach `validate_impulse`-validem 6-Pivot-Impuls: A gegen
Impulsrichtung, B in (0,1) ohne P5-Überschreitung, C jenseits A; **longest-first**
3→2→1, Konstanten `_ABC_IMPULSE_PIVOTS=6`/`_ABC_MAX_CORR_PIVOTS=3`; bewusst OHNE
Magnituden-Schwelle — die ZigZag-Bestätigung ist der Filter). Neue States
`correction_running` (Marke: W5-Extrem bzw. B-Hoch/B-Tief) / `correction_complete`
(Marke: C-Tief/C-Hoch, „neuer Impuls möglich" = Ehrlichkeits-Sprache); **Präzedenz
VOR den 5 Impuls-Kategorien** (bestätigte Korrektur beschreibt die Lage vollständiger;
greift nur bei ≥7 Pivots + validem Impuls). (2) **ambiguity v2**: `ambiguity_v2_fields`
= Impuls-Lesarten + 1 bei Korrektur; `valid_count_total_v2`/`alt_count_v2` auf
Kandidat + allen Zeitebenen; Anzeige nutzt v2 (fail-soft v1-Fallback); Sammlung friert
`ambiguity_n_v2` ZUSÄTZLICH ein, **v1 läuft unverändert weiter**. (3) **W5→A
strukturell**: `observe_w5_structure` (Schritt 5, angehängt) → `a_structure_observed`
(bestätigter ZigZag-Gegen-Pivot nach dem Episoden-Hoch; False erst nach vollem
`A_OBSERVE_DAYS`-Fenster) + `c_target_pct` (% der W5-Strecke). (4) Frontend: 2 CSS-
States (`--txt-sub` gedämpft / Akzent-Blau — bewusst nicht Grün), v2-Badge, Korrektur-
Alternative ohne Ziel/Score, Methodik-Absatz „ABC-Korrektur". **Verifiziert:**
konstruierte Fälle (komplett/A-B/B>P5 ungültig/C nicht jenseits A/Short symmetrisch/
Präzedenz/Determinismus), Byte-Identität (Markt + v1 + Reifung), headless-Render der
neuen Kategorien, Konsole sauber. **16 neue Tests, Suite 227 → 243 grün**; Laufzeit
synthetic-Vollreport ≈ 51 ms (ABC = O(3) Fenster-Checks je Struktur-Befund). Registry
„Struktur-Vokabular v2 + ambiguity v2" datiert. Revert = Detector + Präzedenz-Zweig +
v2-Felder + `observe_w5_structure` + Frontend-Teile raus.

**✅ Textgrößen-Steuerung (− / + im ☰-Menü-Fuß) — erledigt (#44,
`docs/index.html`, reines Frontend):** Squeeze-Vorbild (`Aktien-Update/app.html`)
**belegt** portiert: `--base-font-size:15px`+`html{font-size:var(...)}` (app.html:25/27),
`_FS_SIZES=[13,15,17,19,21]`, key `squeeze_fs`, Clamp+Persist+Disable-an-den-Enden,
`.menu-footer` mit − / + (app.html:3511–3531, 1565). **NUR − und +** übernommen (kein
Settings-Zahnrad/Theme-Mond — Funktionen, die Elliott nicht hat). Elliott-Umsetzung:
`html{font-size:var(--app-fs,16px)}`; die **ganze UI ist rem** → Root-Fontsize skaliert
Karten/Menü/Overlays. Dafür **alle CSS-`font-size:px` → `rem`** konvertiert (exakt /16,
Default 16px = **byte-identische Optik**: h1 20px→1.25rem, `.setup` blieb .78rem etc.);
`body`-Fallback `15px`→`0.9375rem`. **Ausgenommen (bleiben px):** die 4 **SVG-Text**-
Klassen `.wave-num` (8/9px), `.wl-mini-num` (11px), `.wl-mini-dash` (14px) — SVG-User-
Units, sonst würden Sparkline/Donut-Ziffern aus dem fixen viewBox laufen (genau so löst
Squeeze „fixe Elemente"). `_FS_SIZES=[14,16,18,20,22]` (Squeeze-Proportion @16px-Basis),
Default idx 1, key `elliott_fs`, `changeFontSize(±1)` an `#fs-down`/`#fs-up`, sofort
beim Laden angewandt (kein Flash), fail-soft. **Verifiziert (390px, Playwright):** Default
`--app-fs`=16px + h1=20px (byte-identisch), Max 22px `#fs-up` disabled, Min 14px
`#fs-down` disabled, Persistenz über Reload, **kein Overflow/H-Scroll** bei min/std/max
(auch mit Watchlist+tf+alt+Metric-Boxen), Konsole sauber, Tests grün (227). Merge:
reines Frontend → **self-merge** bei grünem CI (keine Screenshots). Revert = `html`-Regel
+ `.menu-fs`-CSS + `.menu-fs`-Markup + FS-JS-Block raus; die px→rem-Konvertierung ist
default-neutral und kann bleiben (oder mit-reverten).

**✅ P3-Audit: Ambiguitäts-Ausweis v1 — erledigt (#43, `scripts/` +
`docs/index.html`):** Multi-Count sichtbar+messbar machen. **Read-only-Befund
(mit Datei:Zeile):** `classify_setup` (`elliott_pipeline.py`) ist **first-fit** über
genau **zwei feste End-Fenster** (`_eval_end_of_w4` auf letzte 5, `_eval_end_of_w2`
auf letzte 3 Pivots) — keine Enumeration über variablen Suchraum. **Zuschnitt (Easy:
Option 1):** der einzige sauber abgrenzbare Suchraum sind genau diese 2 Fenster
(Grad-Ambiguität W4-vs-W2), die `classify_setup` ohnehin beide auswertet → **mitzählen**
statt first-fit; ein „gleitendes" N≥3-Fenster wäre mit den 2 fixen Validatoren nicht
sauber abgrenzbar (bewusst NICHT gebaut, Mini-Stopp-Kriterium). `classify_setup` in
die 2 Helfer refaktoriert → `classify_setup = _eval_end_of_w4() or _eval_end_of_w2()`
(**verhaltensgleich**, alle Bestandstests grün). **Felder:** `valid_count_total` (1..2,
Long-only) + `alt_count` (nur ≥2: zweitbeste nach `score_setup`, Primär byte-identisch)
auf **jeder** Zählung (`build_candidate` + `_count_from_series` → Markt/Watchlist/
timeframes/higher_degree); `ambiguity_n` bei Anlage in die Sammlung eingefroren
(`_new_record`). **UI:** „Zählung 1 von N" nur bei N≥2 (max „1 von 2"), aufklappbare
Alternative (Label·Inval·Ziel·Score gedämpft), N=1 zeigt nichts. **Byte-Identität
bewiesen** (rekursiver Report-Diff: nur `valid_count_total`/`alt_count` neu, gleiche
Top-5/Scores/Reihenfolge; `SCHEMA_VERSION`=1). Laufzeit O(1)/Count (synthetic 353
Ticker ≈ 64 ms). Registry „Ambiguität v1" datiert (nie umdefinieren → v2). **8 neue
Tests** (N=1/N=2/alt/short-nicht-gezählt/Primär-identisch/Determinismus/Freeze),
Suite **219 → 227** grün. Revert = additive Felder + `_eval_*`/`enumerate_long_counts`/
`ambiguity_fields` + Frontend-Block raus (`classify_setup` bleibt). Merge: Guardian +
Manual, keine Screenshots. **Nach Merge:** `daily.yml` → N-Verteilung + Beispiel.

**✅ P2-Audit: Messfelder v1 (Volumen/Alternation/W5-Momentum) — erledigt (#42,
`scripts/` + `docs/index.html`):** Drei literaturgestützte MESS-Felder point-in-time
in die Forward-Sammlung eingefroren — **reine Messung, kein Score/Ranking/Filter/
Population-Einfluss**, die bestehende Reifung **byte-identisch** (belegt: Report-Diff
nur additive `vol_*`-Keys bei gleicher Kandidaten-Menge/Reihenfolge/Scores; Reifungs-
Test grün). **Vorab-Prüfung bestanden:** Volumen steckt im **selben** yfinance-Download
→ additiv als `FetchOutcome.volumes` aus `parse_download_df` (KEIN Extra-Call), durch
`volume_sink` (parallel zu `price_sink`) zu `build_candidate` gefädelt. **(A)
Volumen-Profil** (`_volume_profile`, bei Anlage): `vol_profile` je Welle + `vol_ratio_*`
(Division-Guards → null). **(B) Alternation** (`_alternation_fields`, nur end_of_w4):
Rohwerte `w2/w4_retrace_pct`+`w2/w4_bars` + Flag `alternation_observed`
(`|ΔRetrace|≥20pp` ODER Dauer≥2×); end_of_w2 → null. **(C) W5-Momentum-Divergenz**
(`observe_w5_divergence`, bei Reifung, nur end_of_w4+target_hit): ROC-14-Proxy, W3-Hoch
per **Datum** (2-J-Fenster wandert), angehängter Schritt wie W5→A → Reifung unberührt.
Alle bei `_new_record` gefroren/initialisiert; Konstanten in `forward_collection.py`,
datiert in der Registry („Messfelder v1", stehende Regel: **nie umdefinieren →
neue datierte Felder**). **UI:** einziges sichtbares Element = dezenter Chip
„W3-Volumen schwach" (`vol_ratio_w3_w1 < 1`, `w3VolChip`, neutral, kein Alarm).
Alt-Records unberührt (Felder=null, kein Backfill). **17 neue Tests** (Profil stark/
schwach/guards, Alternation ja/nein/null, Divergenz true/false/null, Freeze, Idempotenz,
Reifung byte-identisch, Volume-Parse aligned/NaN/kein-Volume). Tests grün (**219**).
Revert = additive Felder + `volumes`-Pfad + `_volume_profile`/`_alternation_fields`/
`observe_w5_divergence` + Chip raus. Merge: **Guardian + Manual-Merge**, keine Vorschau-
Screenshots (neue Regel). **Nach Merge:** `daily.yml` → Füllquote + 1 Beispiel-Record
nachtragen.

**✅ P1-Audit: A11y-Kontrast (Mikro-Labels WCAG AA) — erledigt (#41,
`docs/index.html`, reines Frontend):** Audit-Befund: alle Mikro-/Uppercase-Labels
(MONAT/WOCHE/TAG, INVAL/ZIEL/EXT, INVALIDIERUNG/ZIELZONE, Mark-Labels, Kachel-Labels)
lagen mit `--txt-dim` `#64748b` bei nur **3,1–3,7:1** (gemessen, WCAG-Blend über die
realen Flächen) — unter AA (4,5:1 für kleinen Text). **Ein-Token-Fix** (eine Wahrheit):
`--txt-dim` → **`#8b97a8`**. Gemessen nachher (Python-WCAG-Rechner, sRGB-Linearisierung):
Karte 5,90 · Karte-oben 5,25 · Metric-Box 5,58 · tf/hd-Block 5,52 · **blaue WL-Kachel
4,97** — **AA auf allen fünf Flächen** (inkl. der `.05`-über-`.06`-Blau-Stapelung).
Hierarchie **erhalten:** neues `--txt-dim` bleibt auf jeder Fläche **< `--txt-sub`**
(5,74–6,82:1) und weit unter den `--txt`-Werten — Helligkeit angehoben, **Größe/Gewicht
unverändert**. Verifiziert: Vorher/Nachher-Screenshots (390px) neutraler tf-Block **und**
blaue WL-Kachel, `getComputedStyle` bestätigt `#8b97a8`. Revert = ein Zeichenketten-Wert
im `:root`. Reine Anzeige.

**✅ P1-Audit: Universum-Hygiene (8 tote Ticker) — erledigt (#41, `config.py`
+ `data/ticker_meta.json` + Registry):** Grundlage = `market.diag.dead_tickers` aus dem
committeten `report.json` (Lauf 25.07. 13:35Z), alle Grund `empty_data`. Entfernt: **US
(3)** `MMC`, `FI`, `HES`; **DE (5)** `1COV.DE`, `CTS.DE`, `UN01.DE`, `SHA.DE`, `COP.DE`.
Aus `config.py`-Listen (US 239→236, DE 122→117; gesamt **361→353**) **und**
`ticker_meta.json` (361→353 Einträge, reine Löschungen). **Keine Ersatz erfunden**
(ehrlicher als geratene). Deckt sich exakt mit den `empty_data`-Zählern (DE 5 / US 3);
gesunde Namensvettern erhalten (`COP`≠`COP.DE`, `FI`≠`FIS`, `NEM`/`NEM.DE`). Registry-
Log „Universum-Hygiene 25.07." ergänzt. **Zählweise/Score/Ranking/Filter unverändert**,
Tests grün (202). Erwartung Folge-Lauf: `empty_data → 0` je Markt (im PR nachzutragen).
Revert = die 8 Symbole wieder eintragen. Universums-Berührung → **Guardian + Manual-Merge**.

**✅ „Ziel erreicht/überschritten" je Zeitebenen-Zeile — erledigt (#40,
`docs/index.html`, reines Frontend):** Live-Befund AMAT (25.07.): Monats-Zeile zeigte
„Ende W2 · Ziel 296–391" bei Kurs **536** — die Projektion war längst gelaufen (Monats-
Pivot-Trägheit), die Zeile sagte es nicht; das #28-Badge existierte nur an der Haupt-
Zielzonen-Kachel, nicht je Zeitebene. Jetzt trägt **jede** Zeitebenen-Zeile mit `target_zone`
einen kompakten `.tf-hint`-Chip (Markt- UND Watchlist-Karten, da `tfPanel` der einzige
Render-Pfad ist). **Schwellen identisch zu #28** (`_setTfHint` = Zwilling von `_setZoneBadge`):
Kurs ≥ `ziel.low` → „Ziel erreicht", ≥ `ziel.high` → „Ziel überschritten", sonst versteckt.
Bezugskurs: Karten-Kurs `c.close` (3. Arg an `tfPanel`) als Anfangszustand, **live** über
`quotePatch` → `card.querySelectorAll('[data-tf-hint]')` aktualisiert (wie das Haupt-Badge).
EXT ohne eigenen Chip (`ext.high ≥ ziel.high` → „überschritten" deckt es ab). Methodik-
Legende um die Pivot-Trägheits-Erklärung ergänzt. Verifiziert (390px, Playwright, AMAT-
Realfall): **Monat „Ziel überschritten", Tag ohne Hinweis** (Ziel 593–617 > Kurs 536),
Schwellen-Gegenprobe `_setTfHint` (reached/over/below), Zeile bricht nicht um, Konsole
sauber, Tests grün (202). Revert = `.tf-hint`-CSS + Chip-Zweig in `tfPanel` + `_setTfHint`
+ die eine `quotePatch`-Zeile raus. Reine Anzeige — keine Pipeline/Score/Population berührt.

**✅ Header-Layout: Disclaimer ans Seitenende, ☰ oben rechts — erledigt (#39,
`docs/index.html`, reines Frontend):** Zwei Squeeze-nahe Umbauten. (1) **Disclaimer:**
das einklappbare Banner **oben im Kopf** ist komplett entfernt (inkl. `.disclaimer`/
`.disc-*`-CSS und der Einklapp-JS: `DISC_KEY`/`_applyDisc`/localStorage-Merker entfielen).
Stattdessen dezenter **statischer `<footer>` am echten Seitenende** (unter dem letzten
Panel): „Nur zu Informationszwecken — **keine Anlageberatung** … Scores **heuristisch ·
unvalidiert** (siehe ☰ → Methodik / Validierung)"; klein (11px), `--txt-dim`, zentriert,
`border-top`, kein Einklapp-Mechanismus mehr. (2) **Hamburger:** `☰`-Button von oben
links nach **oben rechts** (Squeeze-Squeeze-Position); Kopf jetzt `.head-row` (Titel +
Stand-Zeile links, `☰` rechts), `.menu-panel` öffnet **rechtsbündig** (`right:12px`).
Alle 7 Menü-Funktionen unverändert; Recalculate-Banner, Toasts, Watchlist, 3D-Look (#38)
und `prefers-reduced-motion` unberührt. Verifiziert (390px, Playwright): Kopf ohne
Disclaimer (`h1.x`≈16 / `☰.x`≈334 rechts), Panel rechtsbündig (`right_gap`≈12px), alle
7 Einträge geöffnet/geschlossen, Footer am Scroll-Ende mit „keine Anlageberatung /
heuristisch", Konsole sauber, Tests grün (202). Revert = reiner Frontend-Diff-Revert
(Header-Markup + `.menu-panel`-Position zurück, Footer raus, Disclaimer-Block wieder rein).

**✅ Watchlist-Auto-Sync — erledigt (#37, `docs/index.html`):** Seit #27 ist das
Token 28 Tage entsperrt → der manuelle „Für die Pipeline speichern"-Schritt (#17) war
überholt. Easy: Ticker add/remove = fertig. Gebaut: jede Änderung persistiert lokal
und triggert `_wlScheduleSync` (**Debounce `WL_SYNC_DEBOUNCE_MS=3000`** → mehrere
schnelle Änderungen = **EIN** PUT/Commit). `_wlSyncNow` **idempotent** (kein PUT ohne
echte Änderung, `_wlSyncedJson`-Marker); `_ensureToken(_wlDoPut)` → bei entsperrter
Session stiller PUT, sonst Passwort-/Setup-Dialog (wie Recalculate) und die Änderung
bleibt lokal + **`#wl-sync`-Chip „noch nicht gesynct"** bis zum nächsten Gelingen.
`_wlDoPut` snapshot-basiert, 409/422 → sha frisch + **genau 1× Retry** (Squeeze-Muster),
`_wlSyncedJson` erst bei `r.ok` gesetzt; Erfolg = kurzer Toast „✓ Watchlist gesynct",
PUT-Fehler/offline → Chip bleibt, **kein Datenverlust, kein Retry-Sturm**. **Button +
Erklär-Absatz entfernt** (Hinweise situativ; Sofortkarte trägt den „volle Analyse beim
nächsten Lauf"-Hinweis). Verifiziert (Playwright): 3 Adds → 1 PUT, Idempotenz (no-op →
0 PUT), 409 → 1 Retry, gesperrt → Dialog + Chip (0 PUT) → nach Unlock nachgesynct;
Konsole sauber (außer dem bewusst injizierten 409-Status). Guardian: erwartet. Revert =
Button/`.wl-hint` zurück, `saveWatchlistToPipeline` statt `_wlSyncNow`/`_wlDoPut`, Sync-
Aufrufe aus add/remove entfernen.

**✅ Struktur-Marke präzisiert + A-Orientierung — erledigt (#36):** Read-only-
Diagnose (PANW, Lauf 25.07.): die „Marke" beim Struktur-Befund war eine **nackte,
unbeschriftete Zahl** — bei `impulse_complete` der Impuls-Start (PANW 155,73, > 50 %
unter Kurs), was wie eine nahe Orientierung wirkte, aber der Zählungs-Ungültigkeitspunkt
ist. Easys Wahl: **(c) beides**. Gebaut: (1) additives **`mark_label`** benennt die
Marke je Kategorie (`Impuls-Start`/`W1-Hoch`/`W1-Start`); (2) bei `impulse_complete`
additives **`orientation_price`** = **W4-Extrem** (P4) als nahe **A-Ziel-Region**
(typisches erstes Korrektur-A-Ziel; PANW 320,59 — Kurs stand schon dort). Frontend
`tfPanel` zeigt „<mark_label> <inval>" + ggf. „A-Ziel-Region ~<W4>" statt nacktem
„Marke". **Rein additive Watchlist-Anzeige** — Markt/Score/Ranking/Sammlung unberührt,
`SCHEMA_VERSION` bleibt 1. Verifiziert: 15 Struktur-Tests (mark_label/orientation je
Kategorie, Grenzfall), Real-Check PANW (Impuls-Start 155,73 · A-Ziel ~320,59),
Playwright (alle drei Ebenen beschriftet). Guardian: erwartet. Revert = `mark_label`/
`orientation_price` + Frontend-Zweig entfernen (rein additiv).

**✅ Watchlist-Mehrwert — erledigt (#35):** Easys Befund: eine Ex-Top-5-Karte
(PANW) zeigte auf der Watchlist nur „kein regelkonformes Long-Setup", ihr Kontext
war unsichtbar; Nicht-Setup-Ticker (IONQ) sagten nicht, WO sie in der Struktur stehen.
- **(A) Top-5-Historie (reines Frontend, `docs/index.html`):** die aufgeklappte
  Watchlist-Kachel liest die (schon geladene) `forward_collection` und zeigt je
  Episode eine kompakte Zeile — **Datum · Markt · `count_label` · Anlage-Kurs ·
  Zielzone · Status** (Symbole via `episodeStatus`: offen / Ziel ✓ / Extension ✓✓ /
  invalidiert ✗ / ausgeschlossen). Neueste zuerst, **max 3**, Rest „…N weitere im
  Backtesting". Klick öffnet die **bestehende** `showEpisodeDetail`-Ansicht
  (`openEpisodeFromWatchlist`, kein Neubau). Records werden nach Collection-Load in
  `_wlColl` gecacht und per `_wlInjectHistory` in die `.wl-hist[data-hist]`-Platzhalter
  gespielt (kein Karten-Re-Render → Live-Quotes/Expand bleiben). Fail-soft ohne Episoden.
- **(B) Struktur-Befund (Pipeline, NUR Watchlist-Zweig):** additives Feld `structure`
  {day,week,month}, je Ebene `_classify_structure` → **5 Kategorien** (`long_setup`,
  `impulse_running` „vermutlich W3/W5", `impulse_complete` „5 komplett · Korrektur A
  erwartet" = W5→A-Perspektive, `short_structure`, `no_structure`). Operationalisierung:
  Priorität kompletter Impuls (6 Pivots, `validate_impulse`) → Teil-Impuls bis W4 (5,
  `validate_partial_to_w4`) → Ende W2 (3); Long/Short aus P0→P1; „läuft" vs. „Setup"
  über Schlusskurs vs. zuletzt bestätigte Impulsspitze (W1-/W3-Hoch gebrochen → Folge-
  Welle läuft). Ein Fetch je Ebene liefert Count UND Struktur (`_analyze_from_fetch`,
  kein Doppelabruf). Frontend: `tfPanel(tf, structure)` zeigt bei null-Count den
  Struktur-Befund + Orientierungsmarke statt „kein valider Long-Count". **Ehrlichkeit,
  keine Wahrscheinlichkeit, kein Score.** **Markt-Pipeline/Score/Ranking/Filter/
  forward_collection-Population byte-identisch** (Tests: `structure` nie auf
  `markets[].candidates`, Märkte identisch mit/ohne). Verifiziert: 15 Struktur-Tests
  (alle 5 Kategorien + Grenzfall W5 komplett), Real-Check an PANW-Pivots
  (→ long_setup, Inval 300,48 = P1), Playwright (PANW-Historie klickbar, IONQ-Struktur
  je Ebene). **Live-Verify:** IONQ am echten Lauf (Sandbox-Watchlist leer). Revert =
  Feld + `_classify_structure`/`_structure_from_series`/`_analyze_from_fetch` +
  Historie-Block/`tfPanel`-Struktur-Zweig entfernen (rein additiv).

**✅ Recalculate-Status mit Zeitzähler — erledigt (#34, `docs/index.html`):**
Easy 24.07.: nach dem Recalculate nicht mehr nur „Lauf gestartet · ~2–3 Min" +
manueller Reload, sondern ein **live laufendes Status-Banner** (Squeeze-Muster). Nach
204-Dispatch: Header-Banner „Neuberechnung läuft … N s" (Sekunden live, Elliott-Grün);
`_startRecalcWatch` pollt den **Report-Stand** (`loadReport()`, Cache-Buster+no-store)
alle `RECALC_POLL_MS=10 s` — sobald `run_timestamp_utc` **neuer** als der Stand beim
Start ist, gilt der Lauf als fertig → **`_renderReport(r)` in-place** (kein Page-
Reload, gemeinsame Render-Funktion mit `refresh()`) + grünes „fertig · Stand …" +
Toast wie beim Reload. **Grenzen:** Timeout `RECALC_TIMEOUT_MS=10 min` (Squeeze-Wert)
→ neutraler (nicht-roter) Hinweis „dauert länger — später ☰ → Reload"; **Feiertag**
(`MARKET_FULL_CLOSURE` — die #23-Gate-Tage) → **sofort** ehrlicher Hinweis statt
Warten (der Lauf schreibt nichts); **visibilitychange-Pause** (im inaktiven Tab kein
Fetch), beim Zurückkehren sofort-Check. **Getrennte Timer** vom Quote-Poller
(`_rcPollTimer`/`_rcTick` vs. `quotePollers`) — kein Konflikt. Fail-soft, gedeckelt,
kein Request-Sturm. **Bugfix (live von Easy gesehen, 24.07.): Baseline-Falle** — das
Banner verschwand sofort, weil als Vergleich der im Browser **geladene** (evtl.
CDN-gecachte/ältere) Stand diente; war der Server beim Dispatch schon neuer, meldete
der erste Poll fälschlich „fertig". Fix: Baseline **frisch vom Server** holen
(`_rcBaselineMs`) und „fertig" nur bei **STRIKT neuerem** Report (`Date.parse(ts) >
_rcBaselineMs`, Server-Zeitstempel → kein Client-Uhr-Bezug); `_renderReport` im
Done-Pfad gekapselt, „fertig" bleibt ~6 s sichtbar. Verifiziert (Playwright, 390px):
laufen (≥ 35 s ohne Sofort-fertig trotz vor-gealtertem Server-Stand) / fertig (erst
strikt neuerer Report) / Timeout / Feiertag; Mock-Report altert → Poll rendert frisch;
Konsole sauber; Tests grün (187). **Endbeweis = echter Recalculate durch Easy**
(Abschnitt 3). Revert = reiner Frontend-Diff-Revert (Banner + `_startRecalcWatch`/
`_rcPoll` + Konstanten; `_renderReport`-Extraktion kann bleiben, ist rein strukturell).

**→ WARTESCHLANGE LEER.** Alle Bau-Punkte durch. Nächste Schritte brauchen einen
ausdrücklichen Startschuss von Easy (siehe GEPARKT). Naheliegend: Live-Verifikationen
aus Abschnitt 3 abarbeiten (NTFY_TOPIC scharfschalten, .DE-Chart/Quote, Recalculate/
Watchlist), dann irgendwann die KI-Entscheidung.

**Push-Paket spätere Stufen (geparkt):** die **Invalidierungs-Riss-Pushes** bleiben
bewusst **weg** (Rauschen); erst wieder aufgreifen, wenn Easy es ausdrücklich will.

**GEPARKT (mit Datum):**

> **Lit-Check-Liste damit LEER.** Beide aus dem Literatur-Abgleich geparkten Punkte
> sind gebaut: **Punkt a (Konfluenz-Marker)** = #30, **Punkt b (W5→A-Nachprüfung)** =
> dieser PR. Kein offener Lit-Check-Punkt mehr.

- **KI-Agent** — Easy 23.07.: **weglassen**. Zuschnitts-Optionen für später
  notieren: (a) reiner Kommentator je Karte, (b) Research-Digest-Lauf, (c)
  Chat-Q&A über den Report. Keine Score-Beeinflussung.
- **✅ Konfluenz-Marker — erledigt (#30, Lit-Check-Punkt a):** je Kandidat
  additives Feld `confluence`{`target`,`invalidation`} aus `compute_confluence`
  (`elliott_pipeline.py`, aus den bereits geladenen Tagesschlusskursen — KEINE
  neuen Fetches): **52-Wochen-Hoch**, **200-Tage-Linie** (Einzelwerte → Band-
  Mitgliedschaft ±1 %), **nächste runde Zahl** (dicht → nur an den Kanten geprüft,
  Stufen `CONFLUENCE_ROUND_STEPS` 1/5/10/50 je Preisklasse). Toleranz
  `CONFLUENCE_TOLERANCE_PCT=1.0`. **Chips** an Zielzone/Invalidierung (Markt +
  Watchlist, dezent, kein Alarm), Methodik +3 Sätze. **Point-in-time in der
  Sammlung eingefroren** (`_new_record`) → spätere n≥100-Auswertung kann Konfluenz
  als eigene Dimension testen; Registry datiert (23.07., reines Mess-Feld).
  **Beweisbar kein Score/Ranking/Filter-Eingriff** (Test: erzwungene Konfluenz
  ändert Score/Reihenfolge nicht), SCHEMA_VERSION bleibt 1. Revert = Feld +
  `compute_confluence` + Chips + Konstanten entfernen (rein additiv).
- **✅ W5→A-Nachprüfung — erledigt (dieser PR, Lit-Check-Punkt b):** die Forward-
  Sammlung hält jetzt nach, ob nach einem erfüllten **Ende-W4-Treffer** die theorie-
  gemäße Korrektur A folgt. `observe_a_correction` (`forward_collection.py`,
  **separater 3. Durchgang** nach der Reifung) misst für gereifte, nicht PRU-
  ausgeschlossene end_of_w4-`target_hit`-Records: nach dem Episoden-Hoch werden
  `A_OBSERVE_DAYS=10` Tage beobachtet; `a_correction_observed=true`, sobald der Kurs
  **≥ `A_RETRACE_MIN=38,2 %`** (Fib-Minimum) der W5-Strecke (P4→Hoch) zurückläuft
  (`false` bei vollem Fenster ohne Rücklauf, `null` = offen/keine Messung). Felder
  `a_correction_observed`/`a_retrace_pct`/`a_observe_until` **rein additiv**;
  **angehängtes Fenster — bestehende Reifung byte-identisch** (Test), berührt NUR
  `a_*`. **Guard-Konsistenz:** `pre_reached`/`pre_guard` bleiben ungemessen (null).
  Backtesting-Detail-Zeile „Korrektur nach W5: beobachtet/nicht/offen" (nur eligible
  end_of_w4). **Beweisbar kein Score/Ranking/Filter/report.json-Eingriff**
  (`observe_a_correction` nur in `update_forward_collection`, nie in `build_report`),
  SCHEMA_VERSION bleibt 1. Registry datiert (24.07.). Revert = Felder +
  `observe_a_correction`/3. Loop + Konstanten + Detail-Zeile entfernen (rein additiv).
- **Universum-Option B (Screener)** — nur mit **`source`-Markierung** UND
  **Populations-Ausschluss** (wie Watchlist: Screener-Ticker dürfen nie in die
  n ≥ 100-Population).
- **Score v1** — echte Kalibrierung, **erst nach** Validierungsbefund.
- **Robustere W5-Ext-Formel** — 2 bekannte Degenerierer (kurze Netto-Strecke
  P0→P3 drückt die Ext unter die Basis; Frontend blendet sie dann ehrlich aus,
  siehe `test_schema` W4-Kommentar).
- **Score-Smoothing** — erst nach Validierungsbefund.

---

## 5. ARCHITEKTUR-ANKER

### Pipeline (`scripts/elliott_pipeline.py`, `scripts/zigzag.py`, `scripts/rules.py`, `config.py`)
- **ZigZag:** `ZIGZAG_WINDOW = 5` (symmetrisches Fenster, alternierende Pivots).
  Wochen-Grad separat: `DATA_PERIOD_WEEKLY = "10y"`, `DATA_INTERVAL_WEEKLY = "1wk"`.
  Tagesdaten `DATA_PERIOD = "2y"` / `"1d"`, `MIN_BARS = 60`. **Monatsgrad (NUR
  Watchlist, #PR-B):** `DATA_PERIOD_MONTHLY = "max"`, `DATA_INTERVAL_MONTHLY = "1mo"`,
  `MIN_BARS_MONTHLY = 60` (5 Jahre — darunter kein Monats-Count, fail-soft null).
  `parse_download_df(df, min_bars=None)` teilt die Schwelle (Default = `MIN_BARS`).
- **3 harte Regeln (K.o., `rules.py`):** W2-Retracement ≤ 100 % · W3 nie die
  kürzeste von 1/3/5 · W4 überlappt W1 nicht.
- **Setups:** `end_of_w2` (letzte 3 Pivots P0–P2) und `end_of_w4` (letzte 5 Pivots
  P0–P4). Priorität W4 > W2. `end_of_c` existiert in config, wird aber nicht
  erzeugt.
- **Score** (`score_setup`, Gewichte `SCORE_WEIGHTS` je **1,0**, Summe):
  Basispunkte (`SETUP_BASE_POINTS`: **w2=45, w4=55**) + Fibonacci-Nähe (max
  **20**, Toleranz **±0,15**; Ziele w2 0,5/0,618 · w4 0,382/0,5) + Invalidierungs-
  Abstand (max **15**, linear bis Cap **10 %**). Max ≈ **90**. **Keine**
  Wahrscheinlichkeit.
- **Zielzonen (`TARGET_EXTENSIONS`, `_target_zone`):** W3 = P2 + [1,0–1,618]×W1 ·
  W5 = P4 + [0,618–1,0]×W1. **Extension (Variante b, additiv, nur Anzeige):**
  W3-Ext = P2 + [1,618–2,618]×W1 · W5-Ext = P4 + [0,382–0,618]×|P3−P0|.
- **Invalidierung:** W2-Setup → P0; W4-Setup → P1.
- **Long-only:** Short-Setups (direction < 0) VOR dem Ranking verworfen.
- **`target_exceeded`-Filter (#28-Folge, dieser PR):** in `build_candidate`
  (Param `exclude_target_reached`, Default True für Markt-Top-5, False für
  Watchlist) verwirft Setups mit `close ≥ target_zone.low` VOR dem Ranking —
  Skip-Grund `target_exceeded` (in `SKIP_REASONS`, Diag-Zähler + Lauf-Status-Chip
  „Zielzone erreicht"). Rang 6+ rückt nach. Schwelle = Guard-/Entry-Regel-Schwelle.
- **Universum (`config.py`, statisch):** **US 236** (S&P-Breite) · **DE 117**
  (DAX/MDAX/SDAX, `.DE`) = **353** (Stand 25.07., nach Hygiene-PR: 8 tote `empty_data`-
  Symbole entfernt, vorher 361). Dual-Class nur einmal (GOOGL/FOXA/NWSA,
  BRK-B). Ticker-Meta `data/ticker_meta.json` (Name+Sektor, 353/353 = 100 %,
  fail-soft).
- **Ranking:** `sort key = (-score_heuristic, ticker)`, dann `[:TOP_N]` (`TOP_N=5`).
- **Report-Felder:** `schema_version` (**=1**, additiv), `run_timestamp_utc`,
  `generated_in_seconds` (nur `main`), `markets[US|DE]` (`candidates` + `diag`
  {reason_counts, higher_degree_count, top_count, **dead_tickers**}),
  **`watchlist`** {entries, diag}. Kandidat trägt u. a. `count_label`,
  `invalidation_price`, `target_zone(_extended)`, `score_heuristic`,
  `chart_points`, `count_wave_labels`, `higher_degree`, `appearance_count`
  (in `main` gesetzt), **`confluence`**{target,invalidation}, `status="heuristisch
  · unvalidiert"`.
- **Konfluenz (Markt + Watchlist, dieser PR):** `compute_confluence(closes,
  target_zone, invalidation)` in `build_candidate` (NACH dem Score) — Crowd-Marken
  `52w_high`/`200d`/`round` vs. Zielzone/Invalidierung innerhalb
  `CONFLUENCE_TOLERANCE_PCT=1 %`. 52w/200d = Band-Mitgliedschaft; `round` nur an
  den Kanten (dicht), Stufen `CONFLUENCE_ROUND_STEPS`. Aus den geladenen `closes`
  (keine neuen Fetches). **Kein Score/Ranking** (nach `score_setup`). In der
  Sammlung point-in-time eingefroren (`_new_record` → `confluence`); reines
  Mess-Feld (Registry 23.07.).
- **W5→A-Nachprüfung (NUR Forward-Sammlung, dieser PR):** `observe_a_correction(rec,
  dates, closes, now_iso)` in `forward_collection.py`, aufgerufen im **separaten 3.
  Durchgang** von `update_forward_collection` (nach der Reifungs-Schleife, damit die
  Reifung byte-identisch bleibt). Misst NUR für gereifte, nicht `is_excluded`-
  end_of_w4-`target_hit`-Records: Episoden-Hoch = `max` der Reifungs-10 (`fwd`);
  W5-Strecke = Hoch − `_p4_price` (chart_point mit `count_wave_labels.wave==4`);
  A-Fenster = die `A_OBSERVE_DAYS=10` Schlusskurse NACH dem Hoch; `a_correction_
  observed=true`, sobald `min(A-Fenster) ≤ Hoch − A_RETRACE_MIN·W5-Strecke`
  (`A_RETRACE_MIN=0.382`), `false` bei vollem Fenster ohne Trigger, `null` = offen.
  Schreibt **ausschließlich** `a_correction_observed`/`a_retrace_pct`/`a_observe_until`
  (Test `test_only_a_fields_touched`), deterministisch/idempotent. Braucht Kurse
  ÜBER `HORIZON_DAYS` hinaus, die über die Läufe akkumulieren (`price_sink` hält alle
  Universum-Closes). **Nie in `build_report`** → report.json/Score/Ranking unberührt.
- **Multi-Timeframe (NUR Watchlist-Einträge, #PR-B):** additives Feld
  `timeframes`{`day`,`week`,`month`}, jede Ebene `null` **oder** {`count_label`,
  `invalidation_price`, `target_zone`, `target_zone_extended`}. Aufbau in
  `build_watchlist_entry` über die geteilten Helfer `_count_from_series` (Tag,
  reust die geladene Tagesreihe — kein Extra-Fetch) / `_count_from_fetch` (Woche
  via `get_weekly_fetcher`, Monat via `get_monthly_fetcher` — je +1 Fetch).
  `higher_degree` == `timeframes.week` (Wochen-Count EINMAL geholt, kein Doppel-
  Fetch). `build_report(..., monthly_fetcher=None, price_sink=None)` reicht den
  Monats-Fetcher **nur** an `build_watchlist` weiter — `build_market` bekommt ihn
  NICHT (Top-5 bleiben Tag+Woche, `timeframes` fehlt dort bewusst). Frontend
  `tfPanel()` rendert das Panel NUR bei vorhandenem `c.timeframes` (Markt-Karten
  behalten den reinen Wochen-`hd-block`).
- **„Ziel erreicht/überschritten" je Zeitebene (dieser PR, reines Frontend):**
  jede Zeitebenen-Zeile mit `target_zone` trägt einen kompakten `.tf-hint`-Chip
  (`data-tf-hint`, `data-zl`/`data-zh`). Schwellen **identisch** zum #28-Zonen-Badge
  (`_setZoneBadge`): Bezugskurs ≥ `ziel.low` → „Ziel erreicht", ≥ `ziel.high` →
  „Ziel überschritten", sonst `hidden`. `tfPanel(tf, structure, cardClose)` bekommt
  den Karten-Kurs als 3. Arg (Anfangszustand = Lauf-Schlusskurs `c.close`); `quotePatch`
  aktualisiert live via `card.querySelectorAll('[data-tf-hint]')` → `_setTfHint`
  (Zwilling von `_setZoneBadge`). EXT braucht **keinen** eigenen Chip: `ext.high ≥
  ziel.high`, ein Kurs ≥ `ext.high` zeigt also ohnehin „Ziel überschritten". Motiv:
  Pivot-Bestätigungs-Trägheit (Monatskerzen ±5 Balken) → alte Zählung zeigt „W3
  erwartet", obwohl der Kurs die Projektion längst durchlaufen hat (Live-Fall AMAT
  25.07.: Monat Ziel 296–391 bei Kurs 536). Methodik-Legende um genau diese
  Erklärung ergänzt. Revert = `.tf-hint`-CSS + Chip-Zweig in `tfPanel` + `_setTfHint`
  + die eine `quotePatch`-Zeile raus, `cardClose`-Arg entfällt.
- **Struktur-Befund (NUR Watchlist, #35):** additives Feld `structure`
  {`day`,`week`,`month`}, je Ebene `null` **oder** {`state`,`label`,
  `invalidation_price`,`mark_label`,`orientation_price`,`direction`}.
  `_classify_structure(prices, close)` (reine Logik, direkt testbar) → 5 `state`:
  `long_setup` / `impulse_running` / `impulse_complete` / `short_structure` /
  `no_structure`. Priorität kompletter Impuls (letzte 6 Pivots, `validate_impulse`)
  → Teil-Impuls bis W4 (5, `validate_partial_to_w4`) → Ende W2 (3). `_analyze_from_fetch`
  holt je Ebene EINEN Fetch und liefert (Long-Count, Struktur) — **kein** Doppelabruf.
  Gesetzt **nur** in `build_watchlist_entry` (+ Default in `_wl_base_entry`) →
  `build_market`/Score/Ranking/Sammlung unberührt (Tests). Frontend:
  `tfPanel(tf, structure)` zeigt bei null-Count den Struktur-Befund statt „kein Count".
- **Marke präzisiert + A-Orientierung (dieser PR):** `invalidation_price` = struktureller
  **Zählungs-Ungültigkeitspunkt**; `mark_label` sagt WELCHER Pivot das ist
  (`Impuls-Start` = P0 bei complete, `W1-Hoch` = P1 bei W4, `W1-Start` = P0 bei W2)
  — die nackte Zahl allein (z. B. PANW 155,73, > 50 % unter Kurs) wirkte sonst wie eine
  nahe Orientierung. Bei **`impulse_complete`** zusätzlich `orientation_price` = **W4-
  Extrem** (P4) als nahe **A-Ziel-Region** (typisches erstes Ziel der erwarteten
  Korrektur A; für PANW 320,59 — Kurs stand schon dort). Frontend `tfPanel` zeigt
  `mark_label`+Wert (statt nacktem „Marke") und, wenn vorhanden, „A-Ziel-Region ~<W4>".
  Ehrlichkeits-Sprache, **keine Wahrscheinlichkeit**.
- **Workflow:** `.github/workflows/daily.yml` — Cron **`45 21 * * 1-5`** (Werktage,
  #23) + `workflow_dispatch: {}`, `timeout-minutes: 30`, `concurrency:
  daily-elliott`, committet **report + collection** (#21) sowie den einmaligen
  `data/validation_milestone_fired.flag`.
- **Handelskalender (#23, `scripts/market_calendar.py`):** EINE Quelle für Gate +
  Staleness. `FULL_CLOSURE` = gemeinsame NYSE∩Xetra-Voll-Schließtage (Neujahr,
  Karfreitag, 1. Weihnachtstag) 2026–2027; `HOLIDAY_LIST_EXPIRES = 2027-12-01`
  (Ablauf-Warnung). Feiertags-Gate sitzt in `elliott_pipeline.main()` (nur echter
  Modus): an Voll-Schließtagen → log + `return 0`, nichts geschrieben.
  `last_expected_run(now)`/`is_stale(...)` überspringen Wochenende + Voll-
  Schließtage → **kein Staleness-Fehlalarm**. Einzelmarkt-Feiertage laufen normal.
- **CI:** `.github/workflows/ci.yml`, Check **`test`**, Offline-`pytest` je PR.
- **Push / Selbstüberwachung (#22, `scripts/notify.py`):** ntfy, `POST
  https://ntfy.sh/{NTFY_TOPIC}` + Title/Priority/Tags, fail-soft (`main()` immer
  exit 0). Topic aus **Secret `NTFY_TOPIC`** (leer → still). Modi: `--mode daily`
  (Meilenstein + Review-Wecker, in daily.yml VOR dem Commit) und `--mode staleness`
  (`.github/workflows/staleness_check.yml`, Cron **06:00 UTC**). Lauf-Fehlschlag =
  inline `if: failure()`-`curl`-Step in daily.yml. Config: `SCORE_REVIEW_BY`
  (menschlich, **07.12.2026**), `STATUS_REVIEW_WEEKDAY=0`, `EVAL_MIN_N=100`,
  `STALENESS_HOURS=30`.
  **VORMERKUNG für die Score-Überprüfung am 07.12.2026** (Befund 31.07.2026,
  read-only erhoben, nichts davon geändert): der **Invalidierungs-Bonus steht
  bei 55,4 % aller Kandidaten am Anschlag**, bei den Spitzenkandidaten
  praktisch immer — zwei der drei Score-Komponenten sind dort also konstant,
  und die **gesamte Streuung an der Spitze kommt allein aus dem
  Fibonacci-Bonus**. Der Score diskriminiert oben deutlich schwächer, als drei
  Komponenten vermuten lassen. Dazu: `end_of_c` steht in
  `SETUP_BASE_POINTS`, wird von `classify_setup` aber **nie erzeugt**.
- **Score-Alert typ-relativ (#24, berichtigt 31.07.2026):** IM Daily-Lauf, in `elliott_pipeline.main()`
  **nach** `update_forward_collection` (Episoden existieren) und **vor**
  `write_collection` (Flag persistiert). `fc.score_alert_edges(coll, report, run_date)`
  findet Kandidaten, die in ihrer Episode **neu** an der Schwelle IHRES
  Setup-Typs sind (`>=`, berechnet aus `config.score_alert_threshold(typ)`) (Record mit `last_seen == run_date`, Flag
  `score_alert_fired` noch None → feuern + Flag setzen), gebündelt →
  `notify.send_score_alert(NTFY_TOPIC, edges)` = **1 Push/Lauf**. Flanke,
  nicht Zustand (Bleiben/Dip-Recross derselben Episode = stumm; neue Episode feuert
  erneut). Watchlist ausgenommen (nur `markets[].candidates`). Push **nach** dem
  Persistieren → Einmaligkeit vor Zustellgarantie (wie Meilenstein-Marker).

### Frontend (`docs/index.html`, Vanilla-JS, kein Framework, **kein** Service Worker)
- **Daten:** liest `data/report.json` (Fallback `../data/report.json`);
  `forward_collection.json` analog. Pages aus `/docs` → Report wird nach
  `docs/data/` gespiegelt.
- **Live-Quote-Anker:** `data-quote="price|dot|time"` (NICHT über CSS-Klassen
  ankern — Squeeze-Lesson). Worker **`https://quote-proxy.easywebb.workers.dev`**,
  Poll **15 s** (`QUOTE_POLL_MS`), `visibilitychange` pausiert.
- **Token-Krypto (aus Aktien-Update portiert):** PBKDF2-SHA256 **600000** Iter →
  **AES-GCM-256**, Salt **16 B**, IV **12 B**. `localStorage['elliott_gh_token_enc']`
  = nur verschlüsselter Blob `{v,salt,iv,ct}`; Master-PW nie persistiert.
  `GH_OWNER/REPO='easywebb911'/'Elliott-Report'`, `GH_WORKFLOW='daily.yml'`.
- **Token-Session-Remember (#26/dieser PR, `_ensureToken`-Layer):** nach EINEM
  Master-PW-Unlock bleibt die Token-Nutzung `TOKEN_SESSION_DAYS = 28` Tage still.
  Der Klartext-Token wird mit einem frisch generierten **non-extractable**
  AES-GCM-Key verschlüsselt und `{v, key(CryptoKey), iv, ct, expires_at_ms}` in
  **IndexedDB** (`elliott_session`/`session_wrap`/`tok`) via structured-clone
  abgelegt (`_persistSession`). `_ensureToken` probiert erst `_trySessionUnlock`
  (kein PW) — greift für **Recalculate UND Watchlist-Speichern** (kein Doppel-
  Dialog); Ablauf/Fehler → still Passwort-Dialog (fail-soft). **Feste Frist ab
  Unlock** (kein Rolling; Nutzung schreibt frischen Wrap mit SELBER Frist → nur
  ITP-Timer-Reset). „Sperren" (`mi-lock`) löscht den Record sofort. `_clearToken`
  löscht ihn mit (kein Geist-Session). **Klartext-Token NIE persistiert** —
  localStorage nur PW-Blob, IndexedDB nur ct + non-extractable Key. **Abweichung
  vom Squeeze-Vorbild** (dort rohe Key-Bytes b64 + 7-Tage-Rolling): non-extractable
  Key (sicherer) + feste 28-Tage-Frist (Easy-Vorgabe). iOS: Safari-Data-Clear →
  Session weg → normaler PW-Dialog.
- **Watchlist:** `localStorage['elliott_watchlist']`; Repo-Datei
  `watchlist_personal.json` via Contents-API (GET sha → PUT base64+sha, 409-Retry);
  Token zusätzlich **Contents: write**.
- **Watchlist-Auto-Sync (dieser PR, ersetzt den #17-Button):** add/remove → lokal +
  `_wlScheduleSync` (Debounce `WL_SYNC_DEBOUNCE_MS=3000` → EIN Commit). `_wlSyncNow`
  ist **idempotent** (`JSON.stringify(_wlArr) === _wlSyncedJson` → kein PUT) und ruft
  `_ensureToken(_wlDoPut)`; gesperrte Session → Passwort-/Setup-Dialog (wie Recalculate),
  Änderung bleibt lokal + `#wl-sync`-Chip „noch nicht gesynct", synct beim nächsten
  Gelingen. `_wlDoPut` snapshot-basiert (PUT genau die erfasste Liste; 409/422 → sha
  frisch + **1× Retry**), setzt `_wlSyncedJson` erst bei `r.ok`; Erfolg = kurzer Toast
  „✓ Watchlist gesynct", Fehler → Chip bleibt, kein Retry-Sturm, kein Datenverlust.
  Baseline `_wlSyncedJson` = letzter Lauf (kein Auto-PUT beim Laden). Kein Button,
  kein Erklär-Absatz mehr (Hinweise situativ; Sofortkarte erklärt „nächster Lauf").
- **Watchlist-Kompakt-Grid (Squeeze-Vorbild, seit dieser PR):** `#wl-cards` ist ein
  `.wl-grid` aus `.wl-tile`-Kacheln (`wlTile`). Jede Kachel: `.wl-thead` (Mini-Donut
  `wlMiniDonut`/„—", Ticker, Trend-Punkt) + `.wl-tbody` mit der **vollen** Karte
  (`watchlistCard`/`_wlInstantCard`, unverändert). **Default eingeklappt**; Aufklappen
  setzt `[data-open]` (Kachel spannt die Reihe, kompakter Kopf ausgeblendet, „▴
  Einklappen"-Leiste). Zustand in `localStorage['elliott_wl_expanded']` (Ticker-Set);
  `_wlToggle` schaltet den DOM direkt (kein Re-Render) und ruft beim Öffnen
  `drawAllSparklines`. **Poll-Einheit bleibt `.card[data-ticker]`** (im Body) — der
  Tile-Wrapper trägt nur `data-tile`, also kein Doppel-Poll; der Trend-Punkt im Kopf
  ist statisch (nicht live). Neuer Ticker startet aufgeklappt (Sofortkarte #25).
  Kein-valider-Count → Kopf zeigt „—" (kein Fake-Score). Toggle/Remove via Delegation
  auf `#wl-cards` (`data-wl-toggle`/`data-wl-remove`).
- **Top-5-Historie in der Kachel (dieser PR):** `.wl-hist[data-hist]`-Platzhalter im
  Tile-Body; nach Collection-Load werden die Records in `_wlColl` gecacht und via
  `_wlInjectHistory` gefüllt (`_wlEpisodesFor` → neueste zuerst, max 3, `_wlHistRow`
  mit `episodeStatus`-Symbolen). Klick (`data-ep-i`) → `openEpisodeFromWatchlist` →
  bestehende `showEpisodeDetail`; „…N weitere" → `openBacktesting`. Kein Karten-Re-
  Render (Quotes/Expand bleiben); fail-soft ohne Episoden. `tfPanel(tf, structure)`
  zeigt bei null-Count den Struktur-Befund (Part B) statt „kein valider Long-Count".
- **Menü (☰, 7 Punkte, Squeeze-analog):** `☰`-Button sitzt **oben rechts**
  (Squeeze-Position) neben Titel/Stand-Zeile (`.head-row` flex), das `.menu-panel`
  öffnet **rechtsbündig** (`position:fixed; top:64px; right:12px`). Reihenfolge
  `mi-reload` (**NEU**, primär hervorgehoben) · `mi-recalc` · `mi-backtesting` ·
  `mi-methodik` · `mi-validierung` · `mi-laufstatus` · Trenner · `mi-lock`
  („Sperren", abgesetzt am Fuß). Jeder Eintrag = abgerundete **Icon-Kachel** (`.mi-tile`, Sparkline-Grün
  `--grn`) + `.mi-label`; Icons als **inline-SVG** (lucide-Vorbild, keine externe
  Lib). **`mi-reload`** ruft `refresh({announce:true})` (Cache-Buster/no-store) —
  der frühere Header-Button „↻ Neu laden" ist **entfallen** (`refresh` hält den
  optionalen `#reload`-Button-Block fail-soft). `_setRecalcBtn` ändert nur noch das
  `.mi-label` (Kachel bleibt). Escape-Priorität: Token-Modal > Menü > Info-Overlay
  > Backtesting.
- **Recalculate-Status-Banner (`#recalc-banner`, seit dieser PR):** nach 204 startet
  `_startRecalcWatch` einen **eigenen** Poll-/Tick-Timer (`_rcPollTimer`/`_rcTick`,
  getrennt von `quotePollers`). Fertig-Erkennung über den **Report-Stand**
  (`run_timestamp_utc` ≠ Baseline `_lastReportTs`), nicht die Actions-API (tokenlos).
  Konstanten `RECALC_POLL_MS=10000` / `RECALC_TIMEOUT_MS=600000`. Erfolg →
  `_renderReport(r)` (dieselbe In-place-Render-Funktion wie `refresh()`, gesetzt auch
  `_lastReportTs`). Feiertags-Kurzschluss über `MARKET_FULL_CLOSURE`;
  visibilitychange-Pause; alles fail-soft.
- **Konstanten:** `EVAL_MIN_N = 100`, `COLLECTION_START = '22.07.2026'` (N×-Tooltip,
  an die Präregistrierung gebunden), `STALENESS_HOURS`-Banner bei > 30 h.
- **Disclaimer (seit dieser PR):** kein Banner oben mehr — **statischer Footer-Text
  am Seitenende** (`<footer>`, gedämpft, zentriert): Informationszwecke · keine
  Anlageberatung · Scores heuristisch·unvalidiert. Kein Einklapp-Mechanismus,
  `elliott_disc_collapsed`/`.disclaimer`/`.disc-*` + JS entfallen. (Vorher #23:
  einklappbarer Kopf-Banner.)
- **Chart-Link:** `chartUrl` — US `/stocks/{lower}/`, DE `/quote/etr/{ohne .DE}/`
  (Best-Guess, unverifiziert).

### Merge-Policy & QS-Kette
- **Draft-PR → Guardian-Zweitblick (bei Workflow/Schema/Score/Filter/Pipeline) →
  Manual-Merge durch Easy → Live-Verify.** **Keine Vorschau-Screenshots zur
  Optik-Freigabe mehr** (Easy-Regel 25.07., s. Abschnitt 8) — Optik am Live-Deploy.
  Reine Doku-/Daten-PRs: kein Guardian; Doku-only darf bei grünem CI self-merge.
- Guardian = **Zweitblick, kein Gatekeeper** (Urteil OK / Nits / Blocker).
- **QS-Kette:** CI (`test`, required empfohlen) + Guardian + Easy.
- Modell-ID `claude-opus-4-8` **nie** in Commits/PRs/Artefakten.

---

## 6. VALIDIERUNG (`docs/validation_registry.md`)

**Präregistriert 22.07.2026 — VOR der ersten Zahl.** Erfolgs-Definition **wörtlich**:
Erfolg gilt **NUR** als belegt, wenn **BEIDES** zutrifft — (1) die **Trefferquote**
schlägt einen **Zufalls-Benchmark** (gleiche Aktien, zufällige Einstiegstage,
gleiche relative Ziel-/Stop-Distanzen) **Holm-korrigiert signifikant**, UND (2) die
**Bootstrap-CI-Untergrenze der AUC** (Score vs. `target_hit`) liegt **> 0,5**.

**Regeln (nicht verhandelbar):**
- Auswertung **erst ab n ≥ 100 AUSWERTBAREN** Setups (`EVAL_MIN_N`, `eval_counts`):
  gereift **und nicht** vom PRU-Guard ausgeschlossen.
- **Entry-Regel (PRU-Guard, 23.07.):** ein Record zählt in Trefferquote/AUC nur,
  wenn `entry_close < target_zone.low` (Ziel erst NACH Anlage); analog `ext_hit`
  mit `extension.low`. `pre_reached_*` / `pre_guard_contaminated` → ausgeschlossen
  (nie gelöscht). Invalidierung/Kennzahlen bleiben gültig.
- Marktregime je Record (SPY/DAX über/unter 200-Tage-Linie).
- Forward-Daten **nie** mit Backfill gepoolt.
- **Populations-Regel „veralteter Kurs-Stand" (05.08.2026, Registry-Eintrag):**
  hängt ein Markt hinter dem letzten erwarteten Handelstag zurück, legt der Lauf
  für **diesen Markt** keine neuen Episoden an — ein Setup, das es bei aktuellen
  Kursen nicht gäbe, gehört nicht in die Population. Bestehende Episoden laufen
  über den Tag hinweg **durch** (markt-bewusste Anker), die Reifung bleibt
  bewusst **ungegated** (idempotent, korrigiert sich am Folgetag selbst).
- **Zwei Marker warten auf EINE Entscheidung, vor der ersten Auswertung:**
  `episode_split_suspect` (#68, Mehrfach-Läufe am selben Kalendertag) und
  `stale_market_suspect` (05.08., Anlage auf veraltetem Stand). **Drei Records
  tragen beide** — getrennt entschieden würde derselbe Record je nach
  Reihenfolge doppelt oder gar nicht ausgeschlossen. Beide Marker sind heute
  **zählungs-neutral**; `evaluate.py` ist als v1 eingefroren.
- **Populations-Schutz (baulich):** **Watchlist**-, per-`appearance_count`-,
  **Score-Alert**- UND **Multi-Timeframe**-Logik berühren die Population nicht;
  alle lesen/schreiben **nur** außerhalb von `markets[].candidates` bzw. rein
  additiv. Watchlist (inkl. `timeframes`/Monatsgrad) lebt in `report["watchlist"]`
  und wird nie gesammelt/alarmiert; der Monats-Fetcher erreicht `build_market`
  nicht. Der Score-Alert setzt nur ein additives, anzeige-/push-neutrales Flag
  (`score_alert_fired`) — Score/Ranking/Reifung unberührt. Ein Punktschätzer
  allein ist nie Bestätigung.
- **Daten je forward-Kandidat (10 Handelstage):** `target_hit`, `ext_hit`,
  `invalidated` (binär), `max_gain_10d`, `max_drawdown_10d`, `r_multiple`.

**AUSWERTUNGS-PROGRAMM (v1, 28.07.2026, blind gebaut):** `scripts/evaluate.py`
setzt genau dieses Register um. Aufruf:

```bash
python3 scripts/evaluate.py                 # offiziell — verweigert unter n<100
python3 scripts/evaluate.py --vorschau      # Zwischenstand, ausdrücklich NICHT gültig
python3 scripts/evaluate.py --kurse-holen   # NUR die Kursbasis des Benchmarks holen
```

Standardpfade: Sammlung `data/forward_collection.json`, Kursbasis
`data/eval_prices.json`, Ergebnis `data/evaluation/ergebnis.json`. Es läuft
**nie** im Tageslauf, sendet **keinen** Push und schreibt weder Sammlung noch
Report. Ohne Kursbasis meldet der Zufalls-Vergleich „nicht durchführbar“ —
und ohne ihn kann ein Ergebnis nie „belegt“ lauten. Seed `20260728` fest,
zwei Läufe ergeben dieselbe Datei. Details + die zwei bewusst getroffenen
Operationalisierungen (Kursbasis, Holm auf ein Intervall-Kriterium) stehen im
Registry-Eintrag vom 28.07.

**Datumsanker:** Sammlungs-Beginn/`COLLECTION_START` **22.07.2026**; **Universums-
Wechsel 23.07.2026** (99→361, Zählweise unverändert, im Register geloggt).

**Aktueller Zählerstand:** committete `forward_collection.json` = **0 Records** bis
zum ersten Lauf nach dem Persistenz-Fix (#21). Ab #21 akkumuliert die Sammlung —
der erste echte Lauf schreibt ~10 Records, danach wächst n Lauf für Lauf. (Live-
Beleg = Abschnitt 3.)

---

## 7. LESSONS (teuer gelernt)

- **CSS-Klassennamen kollidieren still** (28.07., Validierungs-Seite):
  Eine neue Regel `.val-note` traf zusätzlich ein **bestehendes** Element
  im Validierungs-Panel der Hauptseite (`<span class="val-note">`) — die
  alte Regel war `.validation .val-note` gescopet, die neue nicht. Im
  Headless-Test fiel es auf, weil der Selektor den falschen Text zurückgab.
  Konsequenz wie bei den SVG-ids in #48: **neue Klassen bekommen ein
  eigenes Präfix** (hier `vsum-`), statt sich auf ein freies Wort zu
  verlassen. Vor jeder neuen Klasse einmal greppen.

- **Look-ahead in der Reifung (PRU, 23.07., → PR-Guard):** ein Setup, dessen Kurs
  schon BEI ANLAGE über der Zielzone stand, zählte als `target_hit` an Tag 1 — ein
  Look-ahead-Artefakt, das die Validierungs-Trefferquote aufbläht. Regel: Hits nur
  zählen, wenn das Ziel NACH der Anlage erreicht wird (`entry_close < Zonen-Low`),
  und schon-erreichte Fälle aus der Population ausschließen (nie löschen —
  ausweisen). Der Score „belohnt" das Davonlaufen zusätzlich (inval_bonus wächst
  mit dem Abstand zum K.o. bis zum Cap) — dort wurde bewusst NICHT eingegriffen.
- **yfinance-MultiIndex:** `download` liefert MultiIndex-Spalten; Test-Mocks
  müssen diese Form spiegeln (`get_level_values(0)`), sonst grüne Tests + 99/99-Skip
  live (PR #3). Guardian prüft: „Spiegeln die Mocks die echte Form?"
- **Sandbox-Stale-Base:** die Sandbox startet auf altem Stand → **immer zuerst
  `origin/main` fetchen und davon branchen** (steht in jedem Aufgaben-Prompt).
- **Proxy-Rechte:** `workflow_dispatch` geht; Branch-Delete / Branch-Protection-
  Änderungen → **403**. Nicht dagegen anrennen.
- **Sandbox erreicht kein Yahoo/EDGAR/externe Hosts** → alles Externe bleibt
  **Live-Verify durch Easy** (Abschnitt 3); Playwright-Tests mocken die GitHub-API.
- **iOS-Cache:** Design-Änderungen greifen sofort, **Daten** hängen im Safari-Cache
  → `cache:'no-store'` + Cache-Buster; **kein Service Worker**. `localStorage`
  räumt iOS-WebKit nach **~7 Tagen** Inaktivität (Token/Watchlist ggf. neu setzen).
- **Sequenz-Regel:** pro Runde **ein** Anzeige-/Optik-PR (Review-Last klein halten).
- **Keine Vorschau-Screenshots mehr (Easy-Regel 25.07.):** Es werden **keine**
  Vorschau-Screenshots/Renderings zur Optik-**Freigabe** mehr erzeugt und an Easy
  geschickt — die Optik wird am **Live-Deploy** beurteilt. Verifikations-Renders
  (Playwright) für die **eigenen** Checks bleiben erlaubt, wandern aber **nicht** in
  den Chat. Optik-PRs laufen als Draft → Manual-Merge durch Easy → Live-Verify.
  (Ersetzt die frühere „Draft-Bild-Freigabe"-Runde.)
- **Alert-Flanke statt Zustand (Schwester-Repo PR #471, 23.07.):** Cooldowns/
  Schwellen ohne **Flanken-Logik** re-alarmieren, solange der Zustand anhält →
  Push-Flut. Regel: edge-triggered (einmal je Episode, Flag), NICHT
  level-triggered. Beim Score-Alert an die vorhandene Episoden-Erkennung koppeln,
  **kein** zweites State-System.
- **Determinismus:** `report.json` byte-identisch belassen (Realdaten macht nur CI);
  nicht-deterministische Felder (`generated_in_seconds`, `appearance_count`) nur in
  `main` setzen, nicht in `build_report` (Tests bleiben deterministisch).

---

## 8. ARBEITSWEISE

- **Drei-Rollen-Disziplin:** **Claude** (in Easys Slack/Chat) formuliert Prompts &
  berät; **die Code-Session** (dieses Repo) baut; **Easy** entscheidet & merged.
  Kein Selbst-Merge außer reiner Doku bei grünem CI.
- **Exzellenz-Selbstprüfung** je Aufgabe: Ziel-Mechanik statt „nichts kaputt";
  Fakten/Hashes belegen statt behaupten; Unverifiziertes bleibt **OFFEN** markiert.
- **Rate-Limit:** **kein Retry-Sturm** — bei Limit/Fehler **melden**, nicht blind
  wiederholen. Netz-Push mit Backoff (2/4/8/16 s), max 4 Versuche.
- **Mini-Stopp** bei fragilen Annahmen (z. B. Laufzeit-Hochrechnung > 25 min,
  nicht identifizierbarer toter Ticker, mehrdeutiger Review-Kommentar): kurz
  innehalten + Rückfrage statt bauen.
- **Guardian vor Manual-Merge** laufen lassen (Diff-Review), Urteil in den PR-Text.
- **Rebase vor Ready-for-Review (stehende Regel):** Vor jedem Ready-for-Review
  `origin/main` fetchen und **rebasen, wenn `main` sich seit Branch-Erstellung
  bewegt hat** — Handover-Konflikte **proaktiv auflösen** statt sie im PR-UI
  auflaufen zu lassen. Der Guardian prüft das künftig mit.
- **Realdaten-Review nach Strukturänderung (stehende Regel):** Nach jedem Eingriff,
  der **Population oder Datenlage** ändert (Universum, neue Wellengrade, neue
  Sammel-/Anzeige-Felder), folgt **binnen eines Laufs** ein bewusster Diagnose-Blick
  auf **ECHTE** Ergebnisse mit der Leitfrage **„Was ist hier absurd?"** —
  konstruierte Testfälle genügen NICHT. **Lesson:** der PRU-/`target_exceeded`-Fall
  blieb in allen Mocks unsichtbar, weil niemand den Fall konstruiert hatte; erst
  der Blick auf den echten Lauf (Kurs über Zielzone) deckte ihn auf.
- **Absolute Vorsicht, kein Risiko:** additiv, fail-soft, `report.json`/Score/
  Ranking/Population unberührt, Revert-Weg im PR-Text.

---

*Pflege: bei jedem Merge Abschnitte 2–4 (mind.) aktualisieren. Siehe README.*
