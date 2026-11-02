# -*- coding: utf-8 -*-
"""append_pending.py - 安全追加 Pending（UTF-8-BOM）"""
import csv
from pathlib import Path

P = Path(r"D:\HGZC\reports\stagflation_watch_2026Q3\pending_issues.csv")

new_rows = [
    # 10-13 新增
    ("2026-10-13", "P0", "auto_daily.bat漏调用calibration_tracker",
     "prediction_log未更新", "加第9步调用log", "10-21后"),
    ("2026-10-13", "P1", "prediction_log已回填6天",
     "10-08到10-13已补", "已处理", "已关闭"),
    ("2026-10-13", "P1", "P(R4+R5)极低",
     "10-08到10-13仅0-0.02%", "待30天后验证", "持续监控"),
    ("2026-10-13", "P2", "09-12唯一高概率预测",
     "P=19.79%;Brier=0.0392", "已可评估", "已关闭"),
    ("2026-10-13", "P1", "Brier日志缺5天已补",
     "10-08到10-12已补", "已处理", "已关闭"),
    ("2026-10-13", "P2", "Brier日志缺2天",
     "09-23/09-25缺失", "不补(当时无记录)", "已关闭"),
]

# 检查文件是否已有表头
has_header = P.exists() and P.stat().st_size > 0

with P.open("a", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    if not has_header:
        w.writerow(["date", "priority", "issue", "detail", "action", "status"])
    for row in new_rows:
        w.writerow(row)

print(f"[ok] 追加 {len(new_rows)} 条到 {P}")