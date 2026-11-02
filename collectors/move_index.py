# -*- coding: utf-8 -*-
"""collectors/move_index.py - MOVE 指数采集（带日级缓存 + 重试 + 代理）"""
import requests
import sqlite3
import time
import os
from datetime import datetime, timezone

DB_PATH = 'data/macro.db'
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5EMOVE"

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

PROXY = os.environ.get('YAHOO_PROXY', '')
PROXIES = {"http": PROXY, "https": PROXY} if PROXY else None


def fetch_move(retries=3):
    params = {"interval": "1d", "range": "3mo"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }
    for attempt in range(retries):
        try:
            r = requests.get(YAHOO_URL, params=params, headers=headers,
                             timeout=30, proxies=PROXIES)
            r.raise_for_status()
            data = r.json()
            result = data.get('chart', {}).get('result', [])
            if result:
                timestamps = result[0].get('timestamp', [])
                closes = result[0].get('indicators', {}).get('quote', [{}])[0].get('close', [])
                rows = []
                for ts, c in zip(timestamps, closes):
                    if c is not None:
                        d = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d')
                        rows.append((d, float(c)))
                return rows
        except Exception as e:
            if attempt < retries - 1:
                print(f"  ⚠️ MOVE 第 {attempt+1}/{retries} 次失败: {str(e)[:60]}，重试...")
                time.sleep(3)
            else:
                print(f"  ❌ MOVE 连续 {retries} 次失败: {str(e)[:60]}")
    return None


def main():
    print(f"\n{'='*60}")
    print(f"  MOVE 指数采集 - {datetime.now().strftime('%Y-%m-%d')}")
    print(f"{'='*60}\n")

    # 🆕 缓存检查：如果今天已经有数据，跳过网络请求
    try:
        conn = sqlite3.connect(DB_PATH)
        last_date = conn.execute("SELECT MAX(timestamp) FROM observations WHERE series_id='MOVE'").fetchone()[0]
        conn.close()
        today_str = datetime.now().strftime('%Y-%m-%d')
        if last_date == today_str:
            print(f"  ⏭️ MOVE 今日已更新 ({last_date})，跳过网络请求 (0 请求)")
            return
    except Exception:
        pass

    rows = fetch_move()
    if not rows:
        print("  ❌ 无数据（可能网络问题，明天再试）")
        return

    conn = sqlite3.connect(DB_PATH)
    count = 0
    for d, v in rows:
        try:
            conn.execute("""INSERT OR REPLACE INTO observations
                (series_id, timestamp, value, source, retrieved_at)
                VALUES ('MOVE', ?, ?, 'yahoo_move', datetime('now'))""", (d, v))
            count += 1
        except Exception:
            pass
    conn.commit()
    conn.close()

    print(f"  ✅ MOVE: 写入 {count} 条")
    print(f"  最新: {rows[-1][0]} = {rows[-1][1]:.2f}")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()