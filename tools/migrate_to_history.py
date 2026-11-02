# -*- coding: utf-8 -*-
"""migrate_to_history.py - 从 observations 迁移到 series_history"""
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB = Path(r"D:\HGZC\data\macro.db")

# observations.series_id -> series_history.series_id 映射
MIGRATE_MAP = {
    "YC10Y":            "US_10Y",
    "YC2Y":             "US_2Y",
    "YC30Y":            "US_30Y",
    "VIX":              "VIX",
    "BAMLH0A0HYM2":     "HY_OAS",
    "DXY_PROXY":        "DXY_BROAD",
    "FEDFUNDS":         "FEDFUNDS",
    "CPIAUCSL":         "CPI",
    "PCEPI":            "PCE",
    "UNRATE":           "UNRATE",
    "PAYEMS":           "PAYROLLS",
    "ICSA":             "JOBLESS_CLAIMS",
    "RRPONTSYD":        "RRP",
    "WALCL":            "FED_BS",
    "SP500":            "SP500",
    "DCOILWTICO":       "WTI",
    "DCOILBRENTEU":     "BRENT",
}

def main():
    con = sqlite3.connect(str(DB))
    total = 0

    for obs_id, hist_id in MIGRATE_MAP.items():
        rows = con.execute("""
            SELECT timestamp, value, source FROM observations
            WHERE series_id = ?
              AND value IS NOT NULL
            ORDER BY timestamp
        """, (obs_id,)).fetchall()

        if not rows:
            print(f"[skip] {obs_id} -> {hist_id}: no data")
            continue

        count = 0
        for ts, val, src in rows:
            # 标准化日期格式
            date = ts[:10] if len(ts) >= 10 else ts
            try:
                con.execute("""
                    INSERT OR REPLACE INTO series_history
                    (series_id, as_of_date, value, source, data_type, retrieved_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (hist_id, date, val, src or "migrated", "observed",
                      datetime.now(timezone.utc).isoformat()))
                count += 1
            except Exception as e:
                print(f"[warn] {hist_id} {date}: {e}")

        print(f"[ok] {obs_id} -> {hist_id}: {count} rows")
        total += count

    con.commit()
    con.close()
    print(f"\n[done] 总迁移 {total} 行")

if __name__ == "__main__":
    main()