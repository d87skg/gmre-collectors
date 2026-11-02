# -*- coding: utf-8 -*-
"""backfill_brier_log.py - 补齐缺失的 Brier 日志"""
import csv
from pathlib import Path

P = Path(r"D:\HGZC\reports\stagflation_watch_2026Q3\brier_daily_log.csv")

# 表头：date,risk_gate,base_regime,gms_r0,stress,defense,fragility,10y,vix,dxy,rrp,notes
NEW_ROWS = {
    "2026-10-08": ["ORANGE", "R0", "49.6", "S4+S5+S6", "3/7", "F3", "5.28", "15.08", "102.36", "2.34", "早盘RED晚盘ORANGE"],
    "2026-10-09": ["ORANGE", "R0", "50.0", "S4+S6", "3/7", "F2", "5.22", "15.08", "102.36", "0.34", "S5解除;美股收盘后基准"],
    "2026-10-10": ["ORANGE", "R0", "50.5", "S4+S6+S7", "3/7", "F2", "5.24", "14.84", "102.19", "0.30", "S7首次触发;RRP新低"],
    "2026-10-11": ["ORANGE", "R0", "50.5", "S4+S6+S7", "3/7", "F2", "5.24", "14.84", "102.21", "0.30", "周日数据同前"],
    "2026-10-12": ["ORANGE", "R0", "50.5", "S4+S6+S7", "3/7", "F2", "5.24", "14.84", "102.25", "0.30", "ETH_FR跨所差异"],
    "2026-10-13": ["ORANGE", "R0", "47.5", "S4+S6+S7", "3/7", "F2", "5.24", "15.21", "102.39", "0.30", "R4概率上升至12.17%"],
    "2026-10-14": ["ORANGE", "R0", "50.5", "S4+S6+S7", "3/7", "F2", "5.19", "17.86", "102.55", "0.20", "CPI冲击;纳指大跌"],
    "2026-10-15": ["ORANGE", "R4", "27.6", "S4+S6+S7", "3/7", "F2", "5.19", "17.86", "102.55", "0.20", "R4首次成为最大概率;RISK_OFF"],
    "2026-10-16": ["ORANGE", "R4", "24.4", "S4+S6", "2/7", "F2", "5.10", "16.46", "102.05", "1.20", "S7解除;Fragility改善"],
    "2026-10-17": ["ORANGE", "R0", "31.4", "S4+S6", "2/7", "F1", "5.09", "19.99", "101.78", "0.10", "R0反超;F1首次出现;VIX飙升"],
}

def main():
    # 读取现有所有行
    existing = {}
    header = None
    
    if P.exists():
        with P.open("r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader)
            for row in reader:
                if row:
                    existing[row[0]] = row

    # 更新缺失的
    for date, data in NEW_ROWS.items():
        existing[date] = [date] + data

    # 按日期排序
    sorted_dates = sorted(existing.keys())
    
    # 覆盖写回
    with P.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if not header:
            header = ["date","risk_gate","base_regime","gms_r0","stress","defense","fragility","10y","vix","dxy","rrp","notes"]
        w.writerow(header)
        for d in sorted_dates:
            w.writerow(existing[d])

    print(f"[ok] Brier 日志已补齐，当前共 {len(sorted_dates)} 天数据。")

if __name__ == "__main__":
    main()