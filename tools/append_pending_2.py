# -*- coding: utf-8 -*-
"""append_pending_2.py - 追加 10-13 晚发现的 Pending"""
import csv
from pathlib import Path

P = Path(r"D:\HGZC\reports\stagflation_watch_2026Q3\pending_issues.csv")

new_rows = [
    ("2026-10-13", "P1", "CoinGlass返回500",
     "免费API不可用", "10-21后评估付费或替代", "10-21后"),
    ("2026-10-13", "P0", "CN_CPI_YOY严重滞后",
     "最新2025-09-10,滞后约1年", "换接口或替代源", "10-14诊断"),
    ("2026-10-13", "P0", "CN_PPI_YOY严重滞后",
     "最新2025-09-10,滞后约1年", "换接口或替代源", "10-14诊断"),
    ("2026-10-13", "P1", "CN日期格式不统一",
     "2026年09月份 vs 2026-10-06", "统一为ISO格式", "10-21后"),
    ("2026-10-13", "P1", "DAU数据在san_metrics表",
     "不在observations", "调整查询方式", "10-21后"),
    ("2026-10-13", "P2", "datetime.utcnow()警告",
     "多个采集脚本使用", "改为now(timezone.utc)", "10-21后"),
]

with P.open("a", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    for row in new_rows:
        w.writerow(row)

print(f"[ok] 追加 {len(new_rows)} 条")