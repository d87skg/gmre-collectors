# -*- coding: utf-8 -*-
import csv
from pathlib import Path

P = Path(r"D:\HGZC\reports\stagflation_watch_2026Q3\pending_issues.csv")

new_rows = [
    ("2026-10-14", "P0", "CN_CPI_YOY接口滞后",
     "AKShare全部滞后到2025-09,今值为NaN",
     "换Trading Economics或其他源", "10-21后"),
    ("2026-10-14", "P2", "CN_PPI_YOY已修复",
     "改用macro_china_ppi,最新2026-08",
     "已处理", "已关闭"),
    ("2026-10-14", "P1", "CN_CPI替代方案评估",
     "Trading Economics/iFinD/统计局",
     "10-21后评估", "10-21后"),
]

with P.open("a", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    for row in new_rows:
        w.writerow(row)

print(f"[ok] 追加 {len(new_rows)} 条")