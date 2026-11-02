# -*- coding: utf-8 -*-
"""tools/backfill_usdjpy_recent.py - 补 USD_JPY 最近 30 天
数据源：Yahoo JPY=X（备用：新浪 fx_susdjpy）
目标：把 USD_JPY 补到 2026-10-21，让 contagion 用满数据
"""
import requests
import sqlite3
from datetime import datetime, timedelta

DB_PATH = 'data/macro.db'


def fetch_yahoo_jpy(days=30):
    """Yahoo Finance JPY=X 日线"""
    url = "https://query1.finance.yahoo.com/v8/finance/chart/JPY=X"
    params = {"range": f"{days}d", "interval": "1d"}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json()
        result = data['chart']['result'][0]
        timestamps = result['timestamp']
        closes = result['indicators']['quote'][0]['close']
        rows = []
        for ts, c in zip(timestamps, closes):
            if c is None:
                continue
            d = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d')
            rows.append((d, float(c)))
        return rows
    except Exception as e:
        print(f"  ❌ Yahoo JPY=X 失败: {str(e)[:80]}")
        return None


def fetch_sina_fx():
    """新浪外汇 fx_susdjpy（备用）"""
    url = ("https://stock2.finance.sina.com.cn/forex/api/jsonp.php/"
           "var%20_fx_susdjpy=/NewForexService.getDayKLine?symbol=fx_susdjpy")
    headers = {"Referer": "https://finance.sina.com.cn/"}
    try:
        r = requests.get(url, headers=headers, timeout=20)
        import re
        m = re.search(r'="([^"]+)"', r.text)
        if not m:
            return None
        rows = []
        for line in m.group(1).split(';'):
            parts = line.split(',')
            if len(parts) >= 5:
                try:
                    rows.append((parts[0], float(parts[4])))
                except Exception:
                    pass
        return rows
    except Exception as e:
        print(f"  ❌ 新浪 fx_susdjpy 失败: {str(e)[:80]}")
        return None


def write_rows(conn, rows, source_tag):
    count = 0
    for d, v in rows:
        try:
            conn.execute(
                """INSERT OR REPLACE INTO observations
                (series_id, timestamp, value, source, retrieved_at)
                VALUES ('USD_JPY', ?, ?, ?, datetime('now'))""",
                (d, float(v), source_tag)
            )
            count += 1
        except Exception:
            pass
    return count


def main():
    print(f"\n{'='*60}")
    print(f"  📥 USD_JPY 最近 30 天回填")
    print(f"{'='*60}")

    # 先看当前最新日期
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT MAX(timestamp) FROM observations WHERE series_id='USD_JPY'"
    ).fetchone()
    conn.close()
    print(f"\n  当前 USD_JPY 最新: {row[0]}")

    # 1. 尝试 Yahoo
    print(f"\n  🔄 尝试 Yahoo JPY=X ...")
    rows = fetch_yahoo_jpy(days=40)
    source = 'yahoo_JPY'
    if not rows:
        print(f"  🔄 降级到新浪 fx_susdjpy ...")
        rows = fetch_sina_fx()
        source = 'sina_fx'

    if not rows:
        print(f"\n  ❌ 两个源都失败，无法回填")
        return

    # 只保留最近 30 天
    cutoff = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    rows = [(d, v) for d, v in rows if d >= cutoff]
    print(f"  ✅ 获取 {len(rows)} 条（{source}），最近 30 天")

    # 2. 写库
    conn = sqlite3.connect(DB_PATH)
    try:
        count = write_rows(conn, rows, source)
        conn.commit()
    finally:
        conn.close()

    latest = max(rows, key=lambda x: x[0])
    print(f"  💾 写入 {count} 条，最新 {latest[0]} = {latest[1]:.4f}")

    # 3. 验证
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT COUNT(*), MIN(timestamp), MAX(timestamp) "
        "FROM observations WHERE series_id='USD_JPY'"
    ).fetchone()
    recent = conn.execute(
        "SELECT timestamp, value, source FROM observations "
        "WHERE series_id='USD_JPY' AND timestamp >= '2026-10-08' "
        "ORDER BY timestamp"
    ).fetchall()
    conn.close()

    print(f"\n  📊 回填后状态:")
    print(f"     总行数={row[0]}  范围={row[1]} → {row[2]}")
    print(f"     最近 10-08 之后的数据:")
    for r in recent:
        print(f"       {r[0]}  {r[1]:.4f}  ({r[2]})")

    print(f"\n{'='*60}")
    print(f"  ✅ USD_JPY 回填完成")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()