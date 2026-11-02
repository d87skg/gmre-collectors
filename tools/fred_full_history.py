# -*- coding: utf-8 -*-
"""fred_full_history.py - FRED 全历史拉取（带 cosd）"""
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
    "BAMLH0A0HYM2":   ("HY_OAS",  "1996-12-31"),
    "BAMLH0A1HYBB":   ("HY_BB",   "1996-12-31"),
    "BAMLH0A3HYC":    ("HY_CCC",  "1996-12-31"),
    "BAMLC0A0CM":     ("IG_OAS",  "1996-12-31"),
    "BAMLC0A4CBBB":   ("IG_BBB",  "1996-12-31"),
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "text/csv,*/*",
}

def fetch(series_id, cosd, retries=3):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={cosd}"
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=120)
            r.raise_for_status()
            return r.text
        except Exception as e:
            print(f"  [retry {i+1}/{retries}] {e}")
            time.sleep(10 * (i + 1))
    return None

def main():
    target = sys.argv[1] if len(sys.argv) > 1 else None
    con = sqlite3.connect(str(DB))
    total = 0

    for fred_id, (local_id, cosd) in FRED_MAP.items():
        if target and target != local_id:
            continue
        print(f"\n[fetch] {fred_id} -> {local_id} (从 {cosd})")
        text = fetch(fred_id, cosd)
        if text is None:
            print(f"  [fail]")
            continue
        reader = csv.reader(io.StringIO(text))
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
            """, (local_id, date, v, "fred_csv", "observed",
                  datetime.now(timezone.utc).isoformat()))
            count += 1
        print(f"  [ok] {count} rows")
        total += count
        con.commit()
        time.sleep(3)

    con.close()
    print(f"\n[done] 总拉取 {total} 行")

if __name__ == "__main__":
    main()