# -*- coding: utf-8 -*-
"""collectors/move_index.py - MOVE 指数采集（ICE 官方免费 CSV）"""
import requests
import sqlite3
import csv
import io
from datetime import datetime, timezone

DB_PATH = 'data/macro.db'

# ICE MOVE 指数 - Yahoo Finance 兜底
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5EMOVE"


def fetch_move():
    """优先 Yahoo Finance（免费且稳定）"""
    url = YAHOO_URL
    params = {"interval": "1d", "range": "3mo"}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=20)
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
        print(f"  ❌ MOVE Yahoo 失败: {e}")
    return None


def main():
    print(f"\n{'='*60}")
    print(f"  MOVE 指数采集 - {datetime.now().strftime('%Y-%m-%d')}")
    print(f"{'='*60}\n")

    rows = fetch_move()
    if not rows:
        print("  ❌ 无数据")
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