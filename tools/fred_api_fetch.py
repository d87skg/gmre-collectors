# -*- coding: utf-8 -*-
"""fred_api_fetch.py - 用 FRED API 拉全历史"""
import os
import sqlite3
import requests
import csv
import io
import time
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

# 加载 .env
BASE = Path(r"D:\HGZC")
load_dotenv(BASE / ".env")
API_KEY = os.environ.get("FRED_API_KEY")

if not API_KEY:
    print("[error] 未找到 FRED_API_KEY，请检查 .env 文件")
    raise SystemExit(1)

print(f"[ok] FRED_API_KEY 已加载: {API_KEY[:8]}...")

DB = BASE / "data" / "macro.db"

FRED_MAP = {
    "BAMLH0A0HYM2":   ("HY_OAS",  "1996-12-31"),
    "BAMLH0A1HYBB":   ("HY_BB",   "1996-12-31"),
    "BAMLH0A3HYC":    ("HY_CCC",  "1996-12-31"),
    "BAMLC0A0CM":     ("IG_OAS",  "1996-12-31"),
    "BAMLC0A4CBBB":   ("IG_BBB",  "1996-12-31"),
    "CPIAUCSL":       ("CPI",     "1947-01-01"),
    "FEDFUNDS":       ("FEDFUNDS","1954-07-01"),
    "UNRATE":         ("UNRATE",  "1948-01-01"),
}

def fetch(series_id, cosd, retries=3):
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": API_KEY,
        "file_type": "json",
        "observation_start": cosd,
    }
    for i in range(retries):
        try:
            r = requests.get(url, params=params, timeout=60)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  [retry {i+1}/{retries}] {e}")
            time.sleep(5 * (i + 1))
    return None

def main():
    con = sqlite3.connect(str(DB))
    total = 0

    for fred_id, (local_id, cosd) in FRED_MAP.items():
        print(f"\n[fetch] {fred_id} -> {local_id} (从 {cosd})")
        data = fetch(fred_id, cosd)
        if not data or "observations" not in data:
            print(f"  [fail]")
            continue

        count = 0
        for obs in data["observations"]:
            date = obs.get("date")
            val = obs.get("value")
            if val in ("", ".", None):
                continue
            try:
                v = float(val)
            except ValueError:
                continue
            con.execute("""
                INSERT OR REPLACE INTO series_history
                (series_id, as_of_date, value, source, data_type, retrieved_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (local_id, date, v, "fred_api", "observed",
                  datetime.now(timezone.utc).isoformat()))
            count += 1

        print(f"  [ok] {count} rows")
        total += count
        con.commit()
        time.sleep(1)

    con.close()
    print(f"\n[done] 总拉取 {total} 行")

if __name__ == "__main__":
    main()