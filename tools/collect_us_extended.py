# -*- coding: utf-8 -*-
"""collect_us_extended.py - 补美国 P0/P1 数据"""
import sqlite3, requests, csv, io
from pathlib import Path
from datetime import datetime

DB = Path(r"D:\HGZC\data\macro.db")

# FRED series → 本地 series_id
FRED_MAP = {
    # P0
    "GOLDPMGBD228NLBM": "GOLD_PRICE",
    "DCOILWTICO":       "WTI_OIL",
    "DCOILBRENTEU":     "BRENT_OIL",
    "DFII10":           "US_10Y_TIPS_REAL",
    "T5YIE":            "US_5Y_BREAKEVEN",
    "T10YIE":           "US_10Y_BREAKEVEN",
    # P1
    "BAMLH0A1HYBB":     "HY_BB_OAS",
    "BAMLH0A2HYB":      "HY_B_OAS",
    "BAMLH0A3HYC":      "HY_CCC_OAS",
    "BAMLC0A1CAAA":     "IG_AAA_OAS",
    "BAMLC0A4CBBB":     "IG_BBB_OAS",
    "T10Y3M":           "US_10Y_3M_SPREAD",
    "DRTSCILM":         "SLOOS_C_AND_I_LOANS",
}

def fetch_fred_csv(series_id):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.text

def parse_and_write(con, series_id, local_id, csv_text):
    reader = csv.reader(io.StringIO(csv_text))
    header = next(reader)
    count = 0
    for row in reader:
        if len(row) < 2: continue
        date, val = row[0], row[1]
        if val in ("", "."): continue
        try:
            v = float(val)
        except ValueError:
            continue
        con.execute("""
            INSERT OR REPLACE INTO observations
            (series_id, timestamp, value, source, retrieved_at, availability_type)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (local_id, date, v, "fred_csv_ext", datetime.now().isoformat(), "OBSERVED"))
        count += 1
    return count

con = sqlite3.connect(str(DB))
for fred_id, local_id in FRED_MAP.items():
    try:
        text = fetch_fred_csv(fred_id)
        n = parse_and_write(con, fred_id, local_id, text)
        print(f"[ok] {fred_id} -> {local_id} ({n} rows)")
    except Exception as e:
        print(f"[fail] {fred_id}: {e}")
con.commit()
con.close()
print("done")