# -*- coding: utf-8 -*-
"""init_series_history.py - 建历史序列表"""
import sqlite3
from pathlib import Path

DB = Path(r"D:\HGZC\data\macro.db")
con = sqlite3.connect(str(DB))

con.execute("""
CREATE TABLE IF NOT EXISTS series_history (
    series_id TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    value REAL,
    source TEXT,
    data_type TEXT DEFAULT 'observed',
    lag_days INTEGER,
    retrieved_at TEXT,
    PRIMARY KEY (series_id, as_of_date)
)
""")

con.execute("""
CREATE TABLE IF NOT EXISTS series_percentile (
    series_id TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    value REAL,
    z_score_1y REAL,
    z_score_5y REAL,
    pct_1y REAL,
    pct_5y REAL,
    PRIMARY KEY (series_id, as_of_date)
)
""")

con.execute("CREATE INDEX IF NOT EXISTS idx_sh_series ON series_history(series_id, as_of_date)")
con.execute("CREATE INDEX IF NOT EXISTS idx_sp_series ON series_percentile(series_id, as_of_date)")

con.commit()
con.close()
print("[ok] series_history + series_percentile 已建")