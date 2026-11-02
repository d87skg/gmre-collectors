# -*- coding: utf-8 -*-
"""tools/backfill_market_history.py - 回填 GOLD/WTI/USD_JPY 历史数据
数据源优先级：新浪历史接口（国内稳）> Yahoo（备用）
修复目标：让 contagion_engine 能用满 4 个资产、且数据截至 10-21
"""
import requests
import sqlite3
import re
import json
from datetime import datetime, timedelta

DB_PATH = 'data/macro.db'
HEADERS_SINA = {"Referer": "https://finance.sina.com.cn/"}
LOOKBACK_DAYS = 730   # 只保留最近 2 年


def _write_observations(conn, series_id, rows, source):
    """批量 INSERT OR REPLACE"""
    count = 0
    for d, v in rows:
        try:
            conn.execute(
                """INSERT OR REPLACE INTO observations
                (series_id, timestamp, value, source, retrieved_at)
                VALUES (?, ?, ?, ?, datetime('now'))""",
                (series_id, d, float(v), source)
            )
            count += 1
        except Exception:
            pass
    return count


def fetch_sina_futures_hist(symbol):
    """新浪国际期货历史日线
    symbol: 'GC' 黄金, 'CL' WTI 原油
    返回: [(date_str, close), ...] 或 None
    """
    url = (f"https://stock2.finance.sina.com.cn/futures/api/jsonp.php/"
           f"var%20_{symbol}=/GlobalFuturesService.getGlobalFuturesDailyKLine"
           f"?symbol={symbol}")
    try:
        r = requests.get(url, headers=HEADERS_SINA, timeout=20)
        # 解析 JSONP: var _GC=([{...},{...}]);
        m = re.search(r'=\s*\((\[.*\])\)', r.text, re.DOTALL)
        if not m:
            # 也尝试不带括号的情况
            m = re.search(r'=(\[.*\])', r.text, re.DOTALL)
        if not m:
            print(f"  ⚠️ {symbol}: 无法解析 JSONP，前 100 字: {r.text[:100]}")
            return None
        data = json.loads(m.group(1))
        rows = []
        for item in data:
            d = item.get('d') or item.get('date')
            c = item.get('c') or item.get('close')
            if d and c:
                rows.append((d, float(c)))
        return rows
    except Exception as e:
        print(f"  ❌ {symbol} 新浪失败: {str(e)[:80]}")
        return None


def fetch_sina_fx_hist(symbol='fx_susdjpy'):
    """新浪外汇历史日线（美元/日元）"""
    url = (f"https://stock2.finance.sina.com.cn/forex/api/jsonp.php/"
           f"var%20_{symbol}=/NewForexService.getDayKLine?symbol={symbol}")
    try:
        r = requests.get(url, headers=HEADERS_SINA, timeout=20)
        # 返回格式: var _fx_susdjpy=("date1,open,high,low,close,avg;date2,...");
        m = re.search(r'="([^"]+)"', r.text)
        if not m:
            print(f"  ⚠️ {symbol}: 无法解析，前 100 字: {r.text[:100]}")
            return None
        text = m.group(1)
        rows = []
        for line in text.split(';'):
            parts = line.split(',')
            if len(parts) >= 5:
                d = parts[0]
                close = parts[4]  # 第 5 个字段为收盘价
                try:
                    rows.append((d, float(close)))
                except Exception:
                    pass
        return rows
    except Exception as e:
        print(f"  ❌ {symbol} 新浪失败: {str(e)[:80]}")
        return None


def backfill_futures(symbol_sina, series_id, source_tag):
    """通用期货回填：拉历史 → 过滤最近 2 年 → 写库"""
    print(f"\n🔄 回填 {series_id} (新浪 {symbol_sina}) ...")
    rows = fetch_sina_futures_hist(symbol_sina)
    if not rows:
        print(f"  ❌ {series_id}: 数据源返回空")
        return

    cutoff = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime('%Y-%m-%d')
    rows = [(d, v) for d, v in rows if d >= cutoff]
    if not rows:
        print(f"  ❌ {series_id}: 最近 {LOOKBACK_DAYS} 天无数据")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        count = _write_observations(conn, series_id, rows, source_tag)
        conn.commit()
    finally:
        conn.close()

    latest = max(rows, key=lambda x: x[0])
    print(f"  ✅ {series_id}: 写入 {count} 条，最新 {latest[0]} = {latest[1]:.2f}")


def backfill_fx(symbol_sina, series_id, source_tag):
    """通用外汇回填"""
    print(f"\n🔄 回填 {series_id} (新浪 {symbol_sina}) ...")
    rows = fetch_sina_fx_hist(symbol_sina)
    if not rows:
        print(f"  ❌ {series_id}: 数据源返回空")
        return

    cutoff = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime('%Y-%m-%d')
    rows = [(d, v) for d, v in rows if d >= cutoff]
    if not rows:
        print(f"  ❌ {series_id}: 最近 {LOOKBACK_DAYS} 天无数据")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        count = _write_observations(conn, series_id, rows, source_tag)
        conn.commit()
    finally:
        conn.close()

    latest = max(rows, key=lambda x: x[0])
    print(f"  ✅ {series_id}: 写入 {count} 条，最新 {latest[0]} = {latest[1]:.4f}")


def print_series_status():
    """打印回填后三个关键序列的完整状态"""
    print(f"\n{'='*60}")
    print(f"  📊 回填后序列状态检查")
    print(f"{'='*60}")
    conn = sqlite3.connect(DB_PATH)
    for sid in ['GOLD_PRICE', 'WTI_OIL', 'USD_JPY']:
        row = conn.execute(
            "SELECT COUNT(*), MIN(timestamp), MAX(timestamp) "
            "FROM observations WHERE series_id=?",
            (sid,)
        ).fetchone()
        count, min_d, max_d = row
        print(f"  {sid:12s} 行数={count:5d}  范围={min_d} → {max_d}")
    conn.close()


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"  📥 市场历史回填 (GOLD / WTI / USD_JPY)")
    print(f"{'='*60}")

    # 1. GOLD：新浪国际期货 GC
    backfill_futures('GC', 'GOLD_PRICE', 'sina_hist_GC')

    # 2. WTI：新浪国际期货 CL
    backfill_futures('CL', 'WTI_OIL', 'sina_hist_CL')

    # 3. USD_JPY：新浪外汇
    backfill_fx('fx_susdjpy', 'USD_JPY', 'sina_hist_fx')

    # 4. 状态检查
    print_series_status()

    print(f"\n{'='*60}")
    print(f"  ✅ 回填完成")
    print(f"{'='*60}\n")