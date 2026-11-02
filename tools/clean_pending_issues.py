# -*- coding: utf-8 -*-
"""
clean_pending_issues.py
用途：清理 pending_issues.csv，去重 + 统一为 6 列。
纪律：只清洗数据文件，不改引擎代码。
"""
from pathlib import Path
import csv
from datetime import datetime
import shutil

BASE = Path(r"D:\HGZC")
P = BASE / "reports" / "stagflation_watch_2026Q3" / "pending_issues.csv"

TS = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = P.parent / f"pending_issues.bak_{TS}.csv"
shutil.copy2(P, backup)
print(f"[backup] {backup}")

with P.open("r", encoding="utf-8-sig") as f:
    rows = list(csv.reader(f))

# 去重
seen = set()
unique = []
for row in rows:
    key = tuple(row)
    if key in seen:
        continue
    seen.add(key)
    unique.append(row)

# 规范化：跳过表头，统一为 6 列
fieldnames = ["date", "priority", "issue", "detail", "action", "status"]
normalized = []
for row in unique:
    if not row:
        continue
    if row[0].lower() == "date":
        continue
    r = (list(row) + ["", "", "", "", "", ""])[:6]
    normalized.append(r)

with P.open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(fieldnames)
    w.writerows(normalized)

print(f"[write] {P}")
print(f"[rows] {len(normalized)}")
for r in normalized:
    print(r)