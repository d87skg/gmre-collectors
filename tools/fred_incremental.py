# -*- coding: utf-8 -*-
"""fred_incremental.py - FRED 增量拉取（带重试 + 延时）"""
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
    "DGS10": "US_10Y",
    "DGS2": "US_2Y",
    "DGS30": "US_30Y",
    "VIXCLS": "VIX",
    "BAMLH0A0HYM2": "HY_OAS",
    "FEDFUNDS": "FEDFUNDS",
    "CPIAUCSL": "CPI",
    "UNRATE": "UNRATE",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "text/csv,*/*",
}

def fetch(series_id, retries=3):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=90)
            r.raise_for_status()
            return r.text
        except Exception as e:
            print(f"  [retry {i+1}/{retries}] {e}")
            time.sleep(10 * (i + 1))
    return None

def main():
    # 接收命令行参数：series 名（可选，全部跑就留空）
    target = sys.argv[1] if len(sys.argv) > 1 else None

    con = sqlite3.connect(str(DB))
    total = 0

    for fred_id, local_id in FRED_MAP.items():
        if target and target != local_id:
            continue

        print(f"\n[fetch] {fred_id} -> {local_id}")
        text = fetch(fred_id)
        if text is None:
            print(f"  [fail] 放弃")
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
        time.sleep(3)  # 每个 series 之间停 3 秒

    con.close()
    print(f"\n[done] 总拉取 {total} 行")

if __name__ == "__main__":
    main()