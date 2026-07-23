"""Zentrale Konfiguration für Elliott-Report.

Universum + alle Parameter an EINER Stelle, damit die Pipeline deterministisch
und leicht nachvollziehbar bleibt. Alles hier ist bewusst statisch (kein
Scraping) und als Startpunkt gedacht — siehe Kommentare.
"""

# ---------------------------------------------------------------------------
# UNIVERSUM (STARTLISTEN — statisch, kein Scraping)
# ---------------------------------------------------------------------------
# US: ~240 liquide S&P-500-Titel (Large/Mega Caps, sektorbreit). Statisch und
# deterministisch — KEIN Screener, keine dynamischen Quellen. Quelle: S&P-500-
# Konstituenten nach Marktkapitalisierung (Stand: 23.07.2026, Wissensbasis
# Jan 2026). Dual-Class bewusst nur EINMAL: GOOGL (nicht GOOG), FOXA (nicht
# FOX), NWSA (nicht NWS) — die liquidere/stimmberechtigte Klasse.
US_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM",
    "ADBE", "AMD", "ACN", "CSCO", "INTC", "TXN",
    "QCOM", "IBM", "NOW", "INTU", "AMAT", "MU",
    "LRCX", "KLAC", "ADI", "SNPS", "CDNS", "PANW",
    "CRWD", "FTNT", "ANET", "MSI", "ROP", "MCHP",
    "NXPI", "ADSK", "MPWR", "FICO", "IT", "HPQ",
    "DELL", "KEYS", "GLW", "ON", "GOOGL", "META",
    "NFLX", "DIS", "CMCSA", "T", "VZ", "TMUS",
    "CHTR", "EA", "TTWO", "WBD", "OMC", "FOXA",
    "NWSA", "AMZN", "TSLA", "HD", "MCD", "NKE",
    "LOW", "SBUX", "BKNG", "TJX", "ORLY", "AZO",
    "MAR", "HLT", "GM", "F", "CMG", "ROST",
    "YUM", "LULU", "DHI", "LEN", "EBAY", "APTV",
    "GRMN", "DRI", "WMT", "PG", "COST", "KO",
    "PEP", "PM", "MO", "MDLZ", "CL", "TGT",
    "KMB", "GIS", "KHC", "SYY", "KR", "STZ",
    "KVUE", "HSY", "MNST", "ADM", "UNH", "JNJ",
    "LLY", "ABBV", "MRK", "TMO", "ABT", "PFE",
    "DHR", "AMGN", "ISRG", "MDT", "BMY", "SYK",
    "VRTX", "GILD", "CI", "REGN", "BSX", "ELV",
    "ZTS", "CVS", "MCK", "BDX", "HCA", "EW",
    "HUM", "IDXX", "A", "IQV", "DXCM", "GEHC",
    "BRK-B", "JPM", "V", "MA", "BAC", "WFC",
    "GS", "MS", "C", "AXP", "SCHW", "BLK",
    "SPGI", "PGR", "CB", "MMC", "PNC", "USB",
    "AON", "ICE", "CME", "MCO", "TFC", "COF",
    "BX", "KKR", "PYPL", "AJG", "AFL", "TRV",
    "ALL", "MET", "AIG", "PRU", "FIS", "FI",
    "GE", "CAT", "RTX", "HON", "UNP", "BA",
    "ETN", "DE", "LMT", "UPS", "GD", "NOC",
    "MMM", "CSX", "FDX", "EMR", "NSC", "ITW",
    "PH", "TDG", "GEV", "CTAS", "PCAR", "CMI",
    "WM", "CARR", "OTIS", "JCI", "UBER", "XOM",
    "CVX", "COP", "SLB", "EOG", "MPC", "PSX",
    "WMB", "OXY", "VLO", "KMI", "HES", "LIN",
    "SHW", "APD", "ECL", "FCX", "NEM", "NUE",
    "DOW", "DD", "PPG", "NEE", "DUK", "SO",
    "D", "AEP", "SRE", "EXC", "XEL", "ED",
    "PEG", "PLD", "AMT", "EQIX", "WELL", "SPG",
    "PSA", "O", "CCI", "DLR", "CBRE",
]

# DE: DAX 40 + Auswahl MDAX + SDAX (.DE / Xetra-Konvention bei yfinance).
# Statisch, Stand: 23.07.2026 (Wissensbasis Jan 2026). Einzelne .DE-Ticker
# können bei yfinance zeitweise ohne Daten sein — fail-soft fängt das ab, und
# der Diag-Log benennt tote Symbole namentlich (Listen-Hygiene).
DE_UNIVERSE = [
    "SAP.DE", "SIE.DE", "ALV.DE", "DTE.DE", "AIR.DE", "MBG.DE",
    "BMW.DE", "BAS.DE", "BAYN.DE", "ADS.DE", "DBK.DE", "DB1.DE",
    "MUV2.DE", "IFX.DE", "VOW3.DE", "RWE.DE", "EOAN.DE", "MRK.DE",
    "HEN3.DE", "FRE.DE", "HEI.DE", "CON.DE", "DHL.DE", "PAH3.DE",
    "P911.DE", "QIA.DE", "SHL.DE", "SY1.DE", "VNA.DE", "ZAL.DE",
    "BEI.DE", "1COV.DE", "MTX.DE", "RHM.DE", "CBK.DE", "SRT3.DE",
    "ENR.DE", "HNR1.DE", "FME.DE", "BNR.DE", "AFX.DE", "LHA.DE",
    "SDF.DE", "EVK.DE", "FRA.DE", "G1A.DE", "HFG.DE", "KGX.DE",
    "LEG.DE", "NDA.DE", "PUM.DE", "SZG.DE", "TEG.DE", "WCH.DE",
    "AT1.DE", "BOSS.DE", "CTS.DE", "DUE.DE", "FNTN.DE", "GXI.DE",
    "JUN3.DE", "KRN.DE", "LXS.DE", "NEM.DE", "RAA.DE", "TLX.DE",
    "UN01.DE", "WAF.DE", "AIXA.DE", "COK.DE", "EVT.DE", "KCO.DE",
    "PSM.DE", "SAX.DE", "TMV.DE", "SHA.DE", "BC8.DE", "UTDI.DE",
    "G24.DE", "DHER.DE", "NDX1.DE", "RDC.DE", "TKA.DE", "FPE3.DE",
    "KBX.DE", "HAG.DE", "GBF.DE", "DWNI.DE", "8TRA.DE", "1U1.DE",
    "HOT.DE", "R3NK.DE", "COP.DE", "S92.DE", "DRW3.DE", "GFT.DE",
    "HAB.DE", "INH.DE", "KWS.DE", "PFV.DE", "SFQ.DE", "VBK.DE",
    "WUW.DE", "ADN1.DE", "BFSA.DE", "DEQ.DE", "ELG.DE", "GYC.DE",
    "HYQ.DE", "JEN.DE", "KTN.DE", "NOEJ.DE", "PBB.DE", "SMHN.DE",
    "SIX2.DE", "STM.DE", "TPE.DE", "VOS.DE", "WAC.DE", "AOF.DE",
    "SGL.DE", "DBAN.DE",
]

# Markt-Metadaten. Reihenfolge = Anzeige-Reihenfolge im Frontend.
MARKETS = {
    "US": {"label": "USA", "universe": US_UNIVERSE},
    "DE": {"label": "Deutschland", "universe": DE_UNIVERSE},
}

# ---------------------------------------------------------------------------
# KURSDATEN
# ---------------------------------------------------------------------------
DATA_PERIOD = "2y"       # 2 Jahre Historie
DATA_INTERVAL = "1d"     # Tageskerzen
MIN_BARS = 60            # Ticker mit weniger Kerzen werden übersprungen

# Großer Wellengrad (zweite Zählung, Wochen-Ebene) — NUR für die finalen Top-5
# je Markt, damit die Extra-Fetches bei ~10 Tickern bleiben (nicht ganzes
# Universum). Lange Historie, damit die großen Züge sichtbar werden.
DATA_PERIOD_WEEKLY = "10y"
DATA_INTERVAL_WEEKLY = "1wk"

# Monatsgrad (dritte Zählung, NUR für Watchlist-Titel — Easys gezielte
# Studienobjekte). Zeigt die ganz großen, mehrjährigen Wellen. "max" holt die
# volle verfügbare Historie (Monatskerzen sind billig: wenige hundert Werte
# selbst über Jahrzehnte). NICHT für die Markt-Top-5 (die bleiben Tag+Woche).
DATA_PERIOD_MONTHLY = "max"
DATA_INTERVAL_MONTHLY = "1mo"
# Mindest-Datenlage für einen Monats-Count: 60 Monatskerzen = 5 Jahre. Begründung:
# der Monatsgrad SOLL mehrjährige Wellen zeigen — mit < 5 Jahren Historie gibt es
# schlicht keine große Struktur zu zählen, und ZigZag (Fenster 5) braucht links/
# rechts Raum für bestätigte Pivots. Darunter fail-soft KEIN Monats-Count (null),
# statt eine Struktur aus zu wenig Kerzen zu erzwingen.
MIN_BARS_MONTHLY = 60

# ---------------------------------------------------------------------------
# ZIGZAG / PIVOT-ENGINE
# ---------------------------------------------------------------------------
# Symmetrisches Bestätigungs-Fenster: ein Bar i ist erst dann ein bestätigter
# Pivot, wenn er das Extremum in [i-WINDOW, i+WINDOW] ist. Größeres Fenster =
# gröbere, robustere Pivots; kleineres = mehr, feinere Pivots.
# DEFAULT = 5 (Handelswoche links + rechts). Bewusst konservativ.
ZIGZAG_WINDOW = 5

# ---------------------------------------------------------------------------
# SCORE (v0) — HEURISTISCH, KEINE Wahrscheinlichkeit.
# ---------------------------------------------------------------------------
# Der Score ist eine bewusst simple, transparente Heuristik zur Sortierung.
# Er ist KEINE Wahrscheinlichkeits- oder Trefferquoten-Aussage. Deshalb heißt
# das Ausgabefeld ausdrücklich "score_heuristic" und jede Karte trägt den
# Status "heuristisch · unvalidiert".
#
# Zusammensetzung (Summe der drei Komponenten, Gewichte hier zentral):
#   1) Setup-Basis  : validierter Impuls + Kandidat am Ende W2 / W4 / Korr.-C
#   2) Fibonacci-Nähe: weicher Bonus, wenn Retracement nahe an Schlüssel-Fib
#   3) Invalidierungs-Abstand: Abstand des aktuellen Kurses zum K.o.-Level
SCORE_WEIGHTS = {
    "setup_base": 1.0,        # Multiplikator für die Setup-Basispunkte
    "fib_proximity": 1.0,     # Multiplikator für den Fibonacci-Bonus
    "invalidation_distance": 1.0,  # Multiplikator für den Abstands-Bonus
}

# Basispunkte je Setup-Typ (heuristische Rangordnung, kein Erwartungswert).
SETUP_BASE_POINTS = {
    "end_of_w2": 45.0,   # nach W1 + W2-Retracement, W3 erwartet
    "end_of_w4": 55.0,   # nach W1–W4, W5 erwartet (mehr Struktur bestätigt)
    "end_of_c": 40.0,    # nach A-B-C-Korrektur, Trendfortsetzung erwartet
}

# Schlüssel-Fibonacci-Level je Wellen-Typ (für den Nähe-Bonus).
FIB_TARGETS = {
    "w2_retrace": [0.5, 0.618],     # typische W2-Retracements
    "w4_retrace": [0.382, 0.5],     # typische W4-Retracements
    "c_retrace": [0.618, 1.0],      # typische C-Retracements
}
FIB_PROXIMITY_MAX_BONUS = 20.0      # max. Bonus bei perfekter Fib-Nähe
FIB_PROXIMITY_TOLERANCE = 0.15      # Retracement-Toleranz (±) für den Bonus

# Invalidierungs-Abstand: moderater Abstand = handelbares Risiko.
# Bonus skaliert linear bis INVALIDATION_DISTANCE_CAP (in %), danach flach.
INVALIDATION_DISTANCE_MAX_BONUS = 15.0
INVALIDATION_DISTANCE_CAP = 10.0    # % Abstand, ab dem der Bonus maximal ist

# Fibonacci-Extensions für Zielzonen (auf W1-Länge bezogen).
TARGET_EXTENSIONS = {
    "w3": [1.0, 1.618],   # Zielzone W3 = P2 + [1.0 .. 1.618] * len(W1)
    "w5": [0.618, 1.0],   # Zielzone W5 = P4 + [0.618 .. 1.0] * len(W1)
    "c_resume": [0.618, 1.0],
    # Ambitioniertere EXTENSION-Zielzonen (additiv, nur Anzeige — kein Einfluss
    # auf Score/Ranking). W3-Ext bezieht sich weiter auf die W1-Länge; W5-Ext
    # bewusst auf die NETTO-Strecke P0->P3 (nicht auf W1), damit das Ziel nicht
    # an einer kleinen W1 klebt.
    "w3_ext": [1.618, 2.618],  # Zielzone-Ext W3 = P2 + [1.618 .. 2.618] * len(W1)
    "w5_ext": [0.382, 0.618],  # Zielzone-Ext W5 = P4 + [0.382 .. 0.618] * |P3-P0|
}

# ---------------------------------------------------------------------------
# OUTPUT
# ---------------------------------------------------------------------------
TOP_N = 5                       # Top-N Kandidaten je Markt
SCHEMA_VERSION = 1              # additiv erweiterbar; bei Breaking-Change +1
CARD_STATUS = "heuristisch · unvalidiert"

# Kanonischer Report + veröffentlichte Kopie im Pages-Root (/docs).
# Siehe README/PR: GitHub Pages aus /docs sieht Dateien AUSSERHALB /docs nicht,
# darum wird der Report zusätzlich nach docs/data/ gespiegelt.
REPORT_PATH = "data/report.json"
REPORT_PATH_PUBLISHED = "docs/data/report.json"

# Persönliche Watchlist (Squeeze-Muster): committete Datei im Repo-Root, aus dem
# Browser via GitHub-Contents-API gepflegt. Die Pipeline liest sie und läuft die
# Ticker durch die VOLLE Analyse — unabhängig vom Top-5-Ranking der Märkte.
# Fail-soft: fehlt/kaputt -> leere Watchlist. Watchlist-Einträge fließen NIE in
# die Forward-Sammlung (Populations-Schutz, siehe docs/validation_registry.md).
WATCHLIST_PATH = "watchlist_personal.json"
WATCHLIST_MAX = 30              # harte Obergrenze (Schutz gegen Fetch-Flut)

# Kuratierte Ticker-Metadaten (Klartext-Name + Sektor). Bewusst als committete
# Mapping-Datei statt yfinance .info je Ticker (teuer/ratelimit-anfällig).
# Fail-soft: fehlt die Datei oder ein Ticker, wird auf den Ticker
# zurückgefallen (Name = Ticker, Sektor = "").
TICKER_META_PATH = "data/ticker_meta.json"

# ---------------------------------------------------------------------------
# STALENESS
# ---------------------------------------------------------------------------
# Alters-Untergrenze für den sichtbaren Frontend-Staleness-Hinweis. Die
# EIGENTLICHE Staleness-Entscheidung (Banner UND Push-Wächter) ist zusätzlich
# KALENDERBEWUSST (scripts/market_calendar.py): kein Wochenend-/Feiertags-
# Fehlalarm — es wird gegen den letzten ERWARTETEN Werktags-Lauf gerechnet.
STALENESS_HOURS = 30

# ---------------------------------------------------------------------------
# PUSH / SELBSTÜBERWACHUNG (Stufe 1 — bewusst fast stumm, siehe scripts/notify.py)
# ---------------------------------------------------------------------------
# ntfy-Topic kommt aus der Umgebung (NTFY_TOPIC, als Repo-Secret gesetzt); leer
# -> kein Push (graceful). NIE hardcoden.
#
# Score-Status-Review-Wecker: Datum, bis zu dem eine Validierungs-Auswertung
# fällig ist (grob projiziert, wenn n>=100 gereifte Setups erreicht sind). NACH
# der Auswertung MENSCHLICH neu setzen (Datum in die Zukunft) oder auf None.
# Automatisiert wird NUR das ERINNERN — nie der Status-Wechsel. Auch in
# docs/validation_registry.md dokumentiert (dort die menschliche Kopie).
SCORE_REVIEW_BY = "2026-12-07"   # ISO-Datum oder None
STATUS_REVIEW_WEEKDAY = 0        # 0 = Montag; Drossel ~1x/Woche (Daily läuft 1x/Tag)

# Score-Alert: EINMALIGER Push, wenn ein Kandidat in SEINER Episode NEU über
# diese Schwelle steigt (Flanke, nicht Zustand — siehe forward_collection.
# score_alert_edges). Bewusst fast stumm: über die gesamte committete
# Report-Historie (Universum 361) erreichte KEIN Kandidat je >90 (Höchststand
# 89.84). Schwelle als benannte Konstante, damit sie an EINER Stelle justierbar
# ist. Watchlist-Karten sind ausgenommen (eigene Auswahl, nicht Teil der
# gerankten Population). Bewusst ein Aufmerksamkeits-Hinweis, KEIN Signal.
SCORE_ALERT_THRESHOLD = 90       # strikt größer als (>90) löst aus
