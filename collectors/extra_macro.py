# -*- coding: utf-8 -*-
"""collectors/extra_macro.py - 全量扩展宏观数据采集（包含市场宽度、离岸汇率、铁矿石等）"""
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

def fetch_yahoo(symbol, series_id, source_tag='yahoo_extra'):
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
                            rows.append({'series_id': series_id, 'date': d, 'value': float(c), 'source': source_tag})
                    return rows
        except Exception as e:
            time.sleep(2)
    print(f"  ❌ {symbol} 抓取失败")
    return []

def fetch_sina_futures(symbol, series_id):
    url = f"https://hq.sinajs.cn/list=nf_{symbol}"
    headers = {"Referer": "https://finance.sina.com.cn/"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        data_str = r.text.split('="')[1].split('"')[0]
        if not data_str:
            return []
        fields = data_str.split(',')
        price = float(fields[8])
        today = datetime.now().strftime('%Y-%m-%d')
        return [{'series_id': series_id, 'date': today, 'value': price, 'source': 'sina_futures_extra'}]
    except Exception as e:
        print(f"  ❌ {symbol} 抓取异常: {e}")
        return []

def main():
    print(f"\n{'='*60}")
    print(f"  全量扩展宏观数据采集 - {datetime.now().strftime('%Y-%m-%d')}")
    print(f"{'='*60}\n")

    all_rows = []

    # 1. 市场宽度 (SPY vs RSP)
    print("🔄 正在抓取 市场宽度 (SPY / RSP)...")
    spy_rows = fetch_yahoo('SPY', 'SPY_PRICE')
    rsp_rows = fetch_yahoo('RSP', 'RSP_PRICE')
    if spy_rows and rsp_rows:
        # 取最新一天的数据计算比值
        spy_latest = spy_rows[-1]
        rsp_latest = rsp_rows[-1]
        if spy_latest['date'] == rsp_latest['date']:
            ratio = spy_latest['value'] / rsp_latest['value']
            all_rows.append({'series_id': 'SPY_RSP_RATIO', 'date': spy_latest['date'], 'value': ratio, 'source': 'calc_breadth'})
            print(f"  ✅ 市场宽度 (SPY/RSP): {ratio:.4f} (若持续走高说明仅科技巨头撑盘)")
        all_rows.extend(spy_rows)
        all_rows.extend(rsp_rows)

    # 2. 黄金 ETF (GLD)
    print("🔄 正在抓取 黄金 ETF (GLD)...")
    gld_rows = fetch_yahoo('GLD', 'GLD_PRICE')
    if gld_rows:
        print(f"  ✅ GLD: 最新 {gld_rows[-1]['date']} = {gld_rows[-1]['value']:.2f}")
        all_rows.extend(gld_rows)

    # 3. 离岸人民币 (USD/CNH)
    print("🔄 正在抓取 离岸人民币 (USD/CNH)...")
    cnh_rows = fetch_yahoo('CNH=X', 'USD_CNH')
    if cnh_rows:
        print(f"  ✅ USD/CNH: 最新 {cnh_rows[-1]['date']} = {cnh_rows[-1]['value']:.4f}")
        all_rows.extend(cnh_rows)

    # 4. 标普 3个月波动率 (VIX3M)
    print("🔄 正在抓取 VIX3M (^VIX3M)...")
    vix3m_rows = fetch_yahoo('^VIX3M', 'VIX3M')
    if vix3m_rows:
        print(f"  ✅ VIX3M: 最新 {vix3m_rows[-1]['date']} = {vix3m_rows[-1]['value']:.2f}")
        all_rows.extend(vix3m_rows)

    # 5. 铁矿石与螺纹钢 (内外盘)
    print("🔄 正在抓取 内盘黑色系 (螺纹钢 RB0, 铁矿石 I0)...")
    rb_rows = fetch_sina_futures('RB0', 'REBAR')
    if rb_rows:
        print(f"  ✅ 螺纹钢 (RB0): 最新 = {rb_rows[-1]['value']:.1f}")
        all_rows.extend(rb_rows)
        
    i_rows = fetch_sina_futures('I0', 'IRON_ORE_DOMESTIC')
    if i_rows:
        print(f"  ✅ 铁矿石内盘 (I0): 最新 = {i_rows[-1]['value']:.1f}")
        all_rows.extend(i_rows)

    print("🔄 正在抓取 外盘铁矿石 (TIO=F)...")
    tio_rows = fetch_yahoo('TIO=F', 'IRON_ORE_FOREIGN')
    if tio_rows:
        print(f"  ✅ 铁矿石外盘 (TIO=F): 最新 {tio_rows[-1]['date']} = {tio_rows[-1]['value']:.2f}")
        all_rows.extend(tio_rows)

    save_to_db(all_rows)
    print(f"\n{'='*60}\n")

if __name__ == '__main__':
    main()