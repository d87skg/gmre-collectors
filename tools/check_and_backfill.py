# -*- coding: utf-8 -*-
"""tools/check_and_backfill.py - 智能缺口检查与增量回填网关（v4.1 适配版）"""
import os
import time
import sqlite3
import subprocess
from datetime import datetime

DB_PATH = 'data/macro.db'
LAST_RUN_FILE = 'data/.last_backfill_ts'
MIN_HOURS_BETWEEN_RUNS = 4
MIN_GAP_DAYS_TO_BACKFILL = 1
MAX_GAP_DAYS_BEFORE_FULL = 30

def get_latest_date(conn, series_id):
    for tbl, col in [('observations_v2', 'obs_date'), ('observations', 'timestamp')]:
        try:
            row = conn.execute(f"SELECT MAX({col}) FROM {tbl} WHERE series_id=?", (series_id,)).fetchone()
            if row and row[0]:
                return str(row[0]).split(' ')[0].split('T')[0]
        except Exception:
            pass
    return None

def days_since(date_str):
    if not date_str: return 9999
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d')
        return (datetime.now() - d).days
    except Exception: return 9999

def check_should_run():
    if not os.path.exists(LAST_RUN_FILE): return True, "首次运行"
    try:
        with open(LAST_RUN_FILE, 'r') as f:
            last_ts = float(f.read().strip())
        hours_since = (time.time() - last_ts) / 3600
        if hours_since < MIN_HOURS_BETWEEN_RUNS:
            return False, f"距上次运行仅 {hours_since:.1f} 小时 (阈值 {MIN_HOURS_BETWEEN_RUNS}h)"
        return True, f"距上次运行 {hours_since:.1f} 小时"
    except Exception: return True, "时间戳文件损坏，按首次处理"

def mark_ran():
    try:
        os.makedirs(os.path.dirname(LAST_RUN_FILE), exist_ok=True)
        with open(LAST_RUN_FILE, 'w') as f:
            f.write(str(time.time()))
    except Exception as e: print(f"  ⚠️ 无法写入时间戳: {e}")

def main():
    print(f"\n{'='*60}\n  🔍 智能缺口检查 - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n{'='*60}\n")
    should_run, reason = check_should_run()
    if not should_run:
        print(f"  ⏭️  跳过：{reason}")
        return
    print(f"  ✅ 频率检查通过：{reason}")

    conn = sqlite3.connect(DB_PATH, timeout=15)
    try:
        gaps = {}
        for sid in ['GOLD_PRICE', 'WTI_OIL', 'USD_JPY']:
            latest = get_latest_date(conn, sid)
            gap = days_since(latest)
            gaps[sid] = gap
            flag = "⚠️" if gap > 1 else "✅"
            print(f"  {flag} {sid:15s} 最新={latest} 缺口={gap} 天")
    finally:
        conn.close()

    max_gap = max(gaps.values())
    if max_gap < MIN_GAP_DAYS_TO_BACKFILL:
        print(f"\n  ⏭️  所有序列缺口 < {MIN_GAP_DAYS_TO_BACKFILL} 天，无需回填 (0 请求)")
        return

    weekday = datetime.now().weekday()
    if weekday < 5 and max_gap < MAX_GAP_DAYS_BEFORE_FULL:
        print(f"\n  ⏭️  工作日缺口小 ({max_gap} 天)，跳过全量回填，避免高负荷请求")
        return

    print(f"\n  🔄 触发回填 (最大缺口 {max_gap} 天)...")
    result = subprocess.run([".venv\\Scripts\\python.exe", "-X", "utf8", "tools\\backfill_market_history.py"], capture_output=False)

    if result.returncode == 0:
        mark_ran()
        print(f"\n  ✅ 回填完成，已更新运行时间戳")
    else:
        print(f"\n  ❌ 回填失败 (exit={result.returncode})，保留旧时间戳")

if __name__ == '__main__':
    main()