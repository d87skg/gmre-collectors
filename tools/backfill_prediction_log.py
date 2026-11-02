# -*- coding: utf-8 -*-
"""backfill_prediction_log.py - 补录 prediction_log 历史数据"""
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from engines_v3 import calibration_tracker

# 要补的日期（根据实际情况调整）
DATES = [
    "2026-10-08",
    "2026-10-09",
    "2026-10-10",
    "2026-10-11",
    "2026-10-12",
    "2026-10-13",
]

def main():
    for d in DATES:
        print(f"\n=== Backfilling {d} ===")
        try:
            state = calibration_tracker.log_today(asof=d)
            print(f"[ok] {d}: regime={state.get('regime')}, gate={state.get('risk_gate')}")
        except Exception as e:
            print(f"[fail] {d}: {e}")

if __name__ == "__main__":
    main()