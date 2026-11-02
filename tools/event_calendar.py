# -*- coding: utf-8 -*-
"""event_calendar.py - 事件日历"""
import sqlite3
from pathlib import Path

DB = Path(r"D:\HGZC\data\macro.db")

# 未来 2 个月关键事件（手工录入，每日可补充）
EVENTS = [
    ("2026-10-17", "DATA", "美国零售销售", "MEDIUM"),
    ("2026-10-24", "DATA", "美国PMI初值", "MEDIUM"),
    ("2026-10-29", "DATA", "美国PCE", "HIGH"),
    ("2026-11-05", "FOMC", "FOMC会议", "HIGH"),
    ("2026-11-06", "FOMC", "FOMC会议第2天", "HIGH"),
    ("2026-11-12", "DATA", "美国CPI", "HIGH"),
    ("2026-11-14", "DATA", "美国PPI", "MEDIUM"),
    ("2026-11-20", "DATA", "美国非农", "HIGH"),
    ("2026-12-10", "FOMC", "FOMC会议", "HIGH"),
    ("2026-12-11", "DATA", "美国CPI", "HIGH"),
    ("2026-12-17", "DATA", "美国PCE", "HIGH"),
]

def main():
    con = sqlite3.connect(str(DB))
    con.execute("""
    CREATE TABLE IF NOT EXISTS event_calendar (
        event_date TEXT,
        event_type TEXT,
        event_name TEXT,
        importance TEXT,
        notes TEXT,
        PRIMARY KEY (event_date, event_name)
    )
    """)
    for d, t, n, imp in EVENTS:
        con.execute("""
            INSERT OR REPLACE INTO event_calendar
            (event_date, event_type, event_name, importance)
            VALUES (?, ?, ?, ?)
        """, (d, t, n, imp))
    con.commit()
    con.close()
    print(f"[ok] 录入 {len(EVENTS)} 个事件")

if __name__ == "__main__":
    main()