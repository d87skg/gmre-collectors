# -*- coding: utf-8 -*-
import csv
from pathlib import Path

P = Path(r"D:\HGZC\reports\stagflation_watch_2026Q3\pending_issues.csv")

new_rows = [
    ("2026-10-17", "P1", "历史序列库建设完成",
     "series_history 已建，7宏观+4信用入库", "已处理", "已关闭"),
    ("2026-10-17", "P1", "计算层分位系统完成",
     "分位/z-score已算，支持月频/日频", "已处理", "已关闭"),
    ("2026-10-17", "P1", "数据新鲜度SLA上线",
     "check_freshness.py已跑通", "已处理", "已关闭"),
    ("2026-10-17", "P0", "CPI 5年分位达100%",
     "CPI历史最高，通胀顽固", "10-21后接入INF引擎", "10-21后"),
    ("2026-10-17", "P0", "HY_CCC 5年分位达99.9%",
     "信用风险极值", "10-21后接入S6引擎", "10-21后"),
    ("2026-10-17", "P2", "HY_OAS仅3年历史",
     "FRED API限额，暂无法拉30年", "先用3年，10-21后找替代", "10-21后"),
]

with P.open("a", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    for row in new_rows:
        w.writerow(row)

print(f"[ok] 追加 {len(new_rows)} 条")