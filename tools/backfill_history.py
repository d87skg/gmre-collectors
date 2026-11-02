# -*- coding: utf-8 -*-
"""backfill_history.py - 从 FRED 回填历史序列"""
import sqlite3
import requests
import csv
import io
from pathlib import Path
from datetime import datetime, timezone

DB = Path(r"D:\HGZC\data\macro.db")

FRED_MAP = {
    "DGS10":     "US_10Y",
    "DGS2":      "US_2Y",
    "DGS30":     "US_30Y",
    "VIXCLS":    "VIX",
    "BAMLH0A0HYM2": "HY_OAS",
    "DTWEXBGS":  "DXY_BROAD",
    "FEDFUNDS":  "FEDFUNDS",
    "CPIAUCSL":  "CPI",
    "PCEPI":     "PCE",
    "UNRATE":    "UNRATE",
    "PAYEMS":    "PAYROLLS",
    "ICSA":      "JOBLESS_CLAIMS",
    "RRPONTSYD": "RRP",
    "WALCL":     "FED_BS",
}

HEADERS = {"User-Agent": "Mozilla/5.0"}

def fetch_fred_csv(series_id):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.text

def main():
    con = sqlite3.connect(str(DB))
    total = 0

    for fred_id, local_id in FRED_MAP.items():
        try:
            text = fetch_fred_csv(fred_id)
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
            print(f"[ok] {local_id}: {count} rows")
            total += count
        except Exception as e:
            print(f"[fail] {local_id}: {e}")

    con.commit()
    con.close()
    print(f"\n[done] 总回填 {total} 行")

if __name__ == "__main__":
    main()