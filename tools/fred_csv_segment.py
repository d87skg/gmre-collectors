# -*- coding: utf-8 -*-
"""fred_csv_segment.py - 分段拉取 FRED CSV（绕过 3 年限制）"""
import sqlite3
import requests
import csv
import io
import time
import sys
from pathlib import Path
from datetime import datetime, timezone

DB = Path(r"D:\HGZC\data\macro.db")

FRED_MAP = {
    "BAMLH0A0HYM2":   "HY_OAS",
    "BAMLH0A1HYBB":   "HY_BB",
    "BAMLH0A3HYC":    "HY_CCC",
    "BAMLC0A0CM":     "IG_OAS",
    "BAMLC0A4CBBB":   "IG_BBB",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "text/csv,*/*",
}

SEGMENTS = [
    ("1996-12-31", "2001-12-31"),
    ("2002-01-01", "2006-12-31"),
    ("2007-01-01", "2011-12-31"),
    ("2012-01-01", "2016-12-31"),
    ("2017-01-01", "2021-12-31"),
    ("2022-01-01", "2026-12-31"),
]

def fetch_segment(series_id, cosd, coed, retries=3):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={cosd}&coed={coed}"
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=60)
            r.raise_for_status()
            return r.text
        except Exception as e:
            print(f"    [retry {i+1}/{retries}] {e}")
            time.sleep(5 * (i + 1))
    return None

def parse_and_write(con, local_id, csv_text):
    reader = csv.reader(io.StringIO(csv_text))
    next(reader)
    count = 0
    for row in reader:
        if len(row) < 2:
            continue
        date, val = row[0], row[1]
        if val in ("", "."):
            continue
        try:
            v = float(val)
        except ValueError:
            continue
        con.execute("""
            INSERT OR REPLACE INTO series_history
            (series_id, as_of_date, value, source, data_type, retrieved_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (local_id, date, v, "fred_csv_seg", "observed",
              datetime.now(timezone.utc).isoformat()))
        count += 1
    return count

def main():
    target = sys.argv[1] if len(sys.argv) > 1 else None
    con = sqlite3.connect(str(DB))
    total = 0

    for fred_id, local_id in FRED_MAP.items():
        if target and target != local_id:
            continue
        print(f"\n[fetch] {fred_id} -> {local_id}")
        series_total = 0
        for cosd, coed in SEGMENTS:
            text = fetch_segment(fred_id, cosd, coed)
            if text is None:
                print(f"    [fail] {cosd} ~ {coed}")
                continue
            n = parse_and_write(con, local_id, text)
            print(f"    [ok] {cosd} ~ {coed}: {n} rows")
            series_total += n
            time.sleep(1)
        print(f"  [total] {local_id}: {series_total} rows")
        total += series_total
        con.commit()

    con.close()
    print(f"\n[done] 总拉取 {total} 行")

if __name__ == "__main__":
    main()