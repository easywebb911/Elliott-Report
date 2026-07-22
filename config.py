"""Zentrale Konfiguration für Elliott-Report.

Universum + alle Parameter an EINER Stelle, damit die Pipeline deterministisch
und leicht nachvollziehbar bleibt. Alles hier ist bewusst statisch (kein
Scraping) und als Startpunkt gedacht — siehe Kommentare.
"""

# ---------------------------------------------------------------------------
# UNIVERSUM (STARTLISTEN — statisch, kein Scraping)
# ---------------------------------------------------------------------------
# US: ~50 liquide Large/Mid Caps als Startliste. Bewusst breit gestreut,
# keine Gewichtung, keine Sektor-Balance — nur ein sinnvoller Ausgangspunkt.
# Später erweiterbar / durch echte Index-Konstituenten ersetzbar.
US_UNIVERSE = [
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA", "AVGO", "JPM",
    "V", "MA", "UNH", "HD", "PG", "JNJ", "XOM", "CVX", "KO", "PEP", "COST",
    "WMT", "MCD", "DIS", "CSCO", "ADBE", "CRM", "NFLX", "INTC", "AMD", "QCOM",
    "TXN", "ORCL", "IBM", "GE", "BA", "CAT", "GS", "MS", "BAC", "WFC", "C",
    "PFE", "MRK", "ABBV", "TMO", "NKE", "SBUX", "LOW", "PYPL", "UBER",
]

# DE: DAX + MDAX Ticker mit .DE-Suffix (Yahoo-Finance-Konvention, Xetra).
# Startliste — nicht garantiert vollständig/aktuell; einzelne .DE-Ticker
# können bei yfinance zeitweise ohne Daten sein (fail-soft fängt das ab).
DE_UNIVERSE = [
    # DAX (Auswahl der 40)
    "SAP.DE", "SIE.DE", "ALV.DE", "DTE.DE", "AIR.DE", "MBG.DE", "BMW.DE",
    "BAS.DE", "BAYN.DE", "ADS.DE", "DBK.DE", "DB1.DE", "MUV2.DE", "IFX.DE",
    "VOW3.DE", "RWE.DE", "EOAN.DE", "MRK.DE", "HEN3.DE", "FRE.DE", "FME.DE",
    "HEI.DE", "CON.DE", "DHL.DE", "PAH3.DE", "QIA.DE", "SHL.DE", "SY1.DE",
    "VNA.DE", "ZAL.DE", "BEI.DE", "1COV.DE", "MTX.DE", "RHM.DE", "CBK.DE",
    # MDAX (Auswahl)
    "AFX.DE", "LHA.DE", "SDF.DE", "EVK.DE", "FRA.DE", "G1A.DE", "HFG.DE",
    "KGX.DE", "LEG.DE", "NDA.DE", "PUM.DE", "SZG.DE", "TEG.DE", "WCH.DE",
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

# Kuratierte Ticker-Metadaten (Klartext-Name + Sektor). Bewusst als committete
# Mapping-Datei statt yfinance .info je Ticker (teuer/ratelimit-anfällig).
# Fail-soft: fehlt die Datei oder ein Ticker, wird auf den Ticker
# zurückgefallen (Name = Ticker, Sektor = "").
TICKER_META_PATH = "data/ticker_meta.json"

# ---------------------------------------------------------------------------
# STALENESS
# ---------------------------------------------------------------------------
STALENESS_HOURS = 30            # Frontend-Banner ab diesem Alter
