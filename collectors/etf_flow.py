# -*- coding: utf-8 -*-
"""collectors/etf_flow.py - ETF 成交量采集（TLT/GLD/HYG/SPY）"""
import requests
import sqlite3
from datetime import datetime, timezone

DB_PATH = 'data/macro.db'

ETF_MAP = {
    'TLT': 'TLT_VOLUME',
    'GLD': 'GLD_VOLUME',
    'HYG': 'HYG_VOLUME',
    'SPY': 'SPY_VOLUME',
    'LQD': 'LQD_VOLUME',
}


def fetch_etf_volume(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"interval": "1d", "range": "3mo"}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json()
        result = data.get('chart', {}).get('result', [])
        if result:
            timestamps = result[0].get('timestamp', [])
            volumes = result[0].get('indicators', {}).get('quote', [{}])[0].get('volume', [])
            rows = []
            for ts, v in zip(timestamps, volumes):
                if v is not None and v > 0:
                    d = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d')
                    rows.append((d, float(v)))
            return rows
    except Exception as e:
        print(f"  ❌ {symbol} 失败: {str(e)[:60]}")
    return None


def main():
    print(f"\n{'='*60}")
    print(f"  ETF 成交量采集 - {datetime.now().strftime('%Y-%m-%d')}")
    print(f"{'='*60}\n")

    conn = sqlite3.connect(DB_PATH)
    total = 0
    for symbol, sid in ETF_MAP.items():
        rows = fetch_etf_volume(symbol)
        if not rows:
            print(f"  ❌ {symbol}: 无数据")
            continue
        count = 0
        for d, v in rows:
            try:
                conn.execute("""INSERT OR REPLACE INTO observations
                    (series_id, timestamp, value, source, retrieved_at)
                    VALUES (?, ?, ?, 'yahoo_etf', datetime('now'))""", (sid, d, v))
                count += 1
            except Exception:
                pass
        total += count
        print(f"  ✅ {symbol} → {sid}: {count} 条 (最新 {rows[-1][0]} = {rows[-1][1]:,.0f})")

    conn.commit()
    conn.close()
    print(f"\n  总计: {total} 条")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()