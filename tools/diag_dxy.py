# -*- coding: utf-8 -*-
"""diag_dxy.py - 诊断 DXY_PROXY 数据质量问题"""
import sqlite3
from pathlib import Path

DB = Path(r"D:\HGZC\data\macro.db")
con = sqlite3.connect(str(DB))

print("=== DXY_PROXY 总量 ===")
total = con.execute("SELECT COUNT(*) FROM observations WHERE series_id='DXY_PROXY'").fetchone()[0]
print(f"总行数: {total}")

print("\n=== value 分布 ===")
nulls = con.execute("SELECT COUNT(*) FROM observations WHERE series_id='DXY_PROXY' AND value IS NULL").fetchone()[0]
narrow = con.execute("SELECT COUNT(*) FROM observations WHERE series_id='DXY_PROXY' AND value BETWEEN 90 AND 115").fetchone()[0]
broad = con.execute("SELECT COUNT(*) FROM observations WHERE series_id='DXY_PROXY' AND value BETWEEN 115 AND 130").fetchone()[0]
other = con.execute("SELECT COUNT(*) FROM observations WHERE series_id='DXY_PROXY' AND value IS NOT NULL AND (value < 90 OR value > 130)").fetchone()[0]
print(f"NULL: {nulls}")
print(f"窄口径 (90-115): {narrow}")
print(f"宽口径 (115-130): {broad}")
print(f"其它 (<90 或 >130): {other}")

print("\n=== timestamp 格式样本 ===")
rows = con.execute("SELECT timestamp, value FROM observations WHERE series_id='DXY_PROXY' ORDER BY timestamp LIMIT 10").fetchall()
for ts, val in rows:
    print(f"  {repr(ts)}  {val}")

print("\n=== timestamp 格式样本（末尾）===")
rows = con.execute("SELECT timestamp, value FROM observations WHERE series_id='DXY_PROXY' ORDER BY timestamp DESC LIMIT 10").fetchall()
for ts, val in rows:
    print(f"  {repr(ts)}  {val}")

print("\n=== 按 timestamp 格式分组统计 ===")
rows = con.execute("""
    SELECT 
        CASE 
            WHEN timestamp LIKE '%T%' THEN 'with_T'
            ELSE 'no_T'
        END as fmt,
        COUNT(*) as cnt,
        MIN(value) as min_v,
        MAX(value) as max_v
    FROM observations
    WHERE series_id='DXY_PROXY' AND value IS NOT NULL
    GROUP BY fmt
""").fetchall()
for fmt, cnt, mn, mx in rows:
    print(f"  {fmt}: {cnt} 行, value 范围 [{mn:.2f}, {mx:.2f}]")

print("\n=== 最近 30 条（按 timestamp DESC）===")
rows = con.execute("""
    SELECT timestamp, value, source 
    FROM observations 
    WHERE series_id='DXY_PROXY' 
    ORDER BY timestamp DESC LIMIT 30
""").fetchall()
for ts, val, src in rows:
    print(f"  {repr(ts)}  {val}  [{src}]")

con.close()