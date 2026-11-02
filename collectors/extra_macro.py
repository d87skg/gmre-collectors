# -*- coding: utf-8 -*-
"""collectors/extra_macro.py - 补充采集：天然气/螺纹钢/VXV"""
import requests
import pandas as pd
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = 'data/macro.db'

def save_to_db(rows):
    if not rows:
        return
    conn = sqlite3.connect(DB_PATH)
    for row in rows:
        conn.execute("""
            INSERT OR REPLACE INTO observations (series_id, timestamp, value, source, retrieved_at)
            VALUES (?, ?, ?, ?, datetime('now'))
        """, (row['series_id'], row['date'], row['value'], row['source']))
    conn.commit()
    conn.close()
    print(f"  ✅ 已保存 {len(rows)} 条数据至数据库")

def fetch_yahoo(symbol, series_id):
    """通用 Yahoo 接口抓取"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"interval": "1d", "range": "5d"}
    headers = {"User-Agent": "Mozilla/5.0"}
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json()
                result = data.get('chart', {}).get('result', [])
                if result:
                    timestamps = result[0].get('timestamp', [])
                    closes = result[0].get('indicators', {}).get('quote', [{}])[0].get('close', [])
                    rows = []
                    for ts, c in zip(timestamps, closes):
                        if c is not None:
                            d = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d')
                            rows.append({'series_id': series_id, 'date': d, 'value': float(c), 'source': 'yahoo_extra'})
                    return rows
        except Exception as e:
            time.sleep(2)
    print(f"  ❌ {symbol} 抓取失败")
    return []

def fetch_sina_futures(symbol, series_id):
    """新浪国内期货接口抓取（如螺纹钢 RB0）"""
    url = f"https://hq.sinajs.cn/list=nf_{symbol}"
    headers = {"Referer": "https://finance.sina.com.cn/"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        # 格式: var hq_str_nf_RB0="螺纹钢连续,...."
        data_str = r.text.split('="')[1].split('"')[0]
        if not data_str:
            return []
        fields = data_str.split(',')
        # 期货字段中，索引 8 通常是当前最新价
        price = float(fields[8])
        today = datetime.now().strftime('%Y-%m-%d')
        return [{'series_id': series_id, 'date': today, 'value': price, 'source': 'sina_futures_extra'}]
    except Exception as e:
        print(f"  ❌ {symbol} 抓取异常: {e}")
        return []

def main():
    print(f"\n{'='*60}")
    print(f"  扩展宏观数据采集 - {datetime.now().strftime('%Y-%m-%d')}")
    print(f"{'='*60}\n")

    all_rows = []

    # 1. 天然气 (Yahoo: NG=F)
    print("🔄 正在抓取 天然气 (NG=F)...")
    ng_rows = fetch_yahoo('NG=F', 'NATURAL_GAS')
    if ng_rows:
        print(f"  ✅ 天然气: 最新 {ng_rows[-1]['date']} = {ng_rows[-1]['value']:.3f}")
        all_rows.extend(ng_rows)

    # 2. VXV (Yahoo: ^VXV)
    print("🔄 正在抓取 VXV (^VXV)...")
    vxv_rows = fetch_yahoo('^VXV', 'VXV')
    if vxv_rows:
        print(f"  ✅ VXV: 最新 {vxv_rows[-1]['date']} = {vxv_rows[-1]['value']:.2f}")
        all_rows.extend(vxv_rows)

    # 3. 螺纹钢连续 (新浪: RB0)
    print("🔄 正在抓取 螺纹钢 (RB0)...")
    rb_rows = fetch_sina_futures('RB0', 'REBAR')
    if rb_rows:
        print(f"  ✅ 螺纹钢: 最新 = {rb_rows[-1]['value']:.1f}")
        all_rows.extend(rb_rows)

    save_to_db(all_rows)
    print(f"\n{'='*60}\n")

if __name__ == '__main__':
    main()