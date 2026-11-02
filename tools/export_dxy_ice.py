# -*- coding: utf-8 -*-
"""export_dxy_ice.py - 导出 DXY_PROXY 中的 ICE DXY 窄口径（market + with_T）"""
import sqlite3, csv
from pathlib import Path
from datetime import datetime

BASE = Path(r"D:\HGZC")
DB = BASE / "data" / "macro.db"
OUT = BASE / "exports" / f"dxy_ice_{datetime.now().strftime('%Y%m%d')}.csv"
OUT.parent.mkdir(exist_ok=True)

con = sqlite3.connect(str(DB))

# 只保留 market 源 + with_T 格式
rows = con.execute("""
    SELECT timestamp, value FROM observations
    WHERE series_id='DXY_PROXY'
      AND timestamp LIKE '%T%'
      AND value IS NOT NULL
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
print(f"[range] {rows[0][0]} → {rows[-1][0]}")
print(f"[value_range] {min(v for _, v in rows):.4f} → {max(v for _, v in rows):.4f}")
print()
print("=== 完整 CSV 内容 ===")
print("timestamp,value")
for ts, val in rows:
    print(f"{ts},{val}")