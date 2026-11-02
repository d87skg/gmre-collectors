# -*- coding: utf-8 -*-
"""
probe_db.py
探测本地 macro.db 实际表名和字段名。
"""
import sqlite3
from pathlib import Path

DB = Path(r"D:\HGZC\data\macro.db")

con = sqlite3.connect(str(DB))
con.row_factory = sqlite3.Row

# 所有表
tables = con.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
).fetchall()

print(f"=== {DB} ===")
print(f"表数量: {len(tables)}\n")

for t in tables:
    name = t["name"]
    try:
        cols = con.execute(f"PRAGMA table_info({name})").fetchall()
        col_names = [c["name"] for c in cols]
        # 记录数
        try:
            cnt = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        except Exception:
            cnt = "?"
        print(f"[{name}] ({cnt} 行)")
        print(f"  字段: {', '.join(col_names)}")
        # 最新一行（如果有时间戳字段）
        ts_field = None
        for cand in ["date", "asof", "created_at", "timestamp", "ts", "dt"]:
            if cand in col_names:
                ts_field = cand
                break
        if ts_field:
            try:
                row = con.execute(
                    f"SELECT * FROM {name} ORDER BY {ts_field} DESC LIMIT 1"
                ).fetchone()
                print(f"  最新: {dict(row)}")
            except Exception as e:
                print(f"  (取最新失败: {e})")
        print()
    except Exception as e:
        print(f"[{name}] 探测失败: {e}\n")

con.close()