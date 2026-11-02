# -*- coding: utf-8 -*-
"""collect_us_extended_v2.py - 加强重试 + 延时 + User-Agent"""
import sqlite3, requests, csv, io, time
from pathlib import Path
from datetime import datetime

DB = Path(r"D:\HGZC\data\macro.db")

FRED_MAP = {
    "GOLDPMGBD228NLBM": "GOLD_PRICE",
    "DCOILWTICO":       "WTI_OIL",
    "DCOILBRENTEU":     "BRENT_OIL",
    "DFII10":           "US_10Y_TIPS_REAL",
    "T5YIE":            "US_5Y_BREAKEVEN",
    "T10YIE":           "US_10Y_BREAKEVEN",
    "BAMLH0A1HYBB":     "HY_BB_OAS",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/csv,*/*",
}

def fetch_fred_csv(series_id, retries=3):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=60)
            r.raise_for_status()
            return r.text
        except Exception as e:
            print(f"  [retry {i+1}/{retries}] {series_id}: {e}")
            time.sleep(5 * (i + 1))  # 递增延时
    return None

def parse_and_write(con, local_id, csv_text):
    reader = csv.reader(io.StringIO(csv_text))
    next(reader)  # skip header
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
        """, (local_id, date, v, "fred_csv_ext_v2", datetime.now().isoformat(), "OBSERVED"))
        count += 1
    return count

con = sqlite3.connect(str(DB))
for fred_id, local_id in FRED_MAP.items():
    print(f"[fetch] {fred_id} -> {local_id}")
    text = fetch_fred_csv(fred_id)
    if text is None:
        print(f"  [fail] {fred_id}")
        continue
    try:
        n = parse_and_write(con, local_id, text)
        print(f"  [ok] {n} rows")
    except Exception as e:
        print(f"  [parse fail] {e}")
    time.sleep(2)  # 每次请求间延时
con.commit()
con.close()
print("done")