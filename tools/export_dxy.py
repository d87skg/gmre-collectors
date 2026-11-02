# -*- coding: utf-8 -*-
"""export_dxy.py - 导出本地 DXY_PROXY 最近 90 天"""
import sqlite3, csv
from pathlib import Path
from datetime import datetime, timedelta

BASE = Path(r"D:\HGZC")
DB = BASE / "data" / "macro.db"
OUT = BASE / "exports" / f"dxy_proxy_{datetime.now().strftime('%Y%m%d')}.csv"
OUT.parent.mkdir(exist_ok=True)

con = sqlite3.connect(str(DB))
rows = con.execute("""
    SELECT timestamp, value FROM observations
    WHERE series_id='DXY_PROXY'
      AND timestamp >= date('now', '-120 days')
    ORDER BY timestamp
""").fetchall()
con.close()

with OUT.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["timestamp", "value"])
    for ts, val in rows:
        w.writerow([ts, val])

print(f"[export] {OUT}")
print(f"[rows] {len(rows)}")
print(f"[head] {rows[:3]}")
print(f"[tail] {rows[-3:]}")