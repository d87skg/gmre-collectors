# -*- coding: utf-8 -*-
"""collectors/extra_macro.py - 全量扩展（v3.2：拉取5年历史以支持正确分位计算）"""
import sys
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
        conn.execute(
            "INSERT OR REPLACE INTO observations (series_id, timestamp, value, source, retrieved_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            (row['series_id'], row['date'], row['value'], row['source'])
        )
    conn.commit()
    conn.close()
    print(f"  ✅ 已保存 {len(rows)} 条数据")


def save_realtime_us10y(value: float, quote_time_bj: str, source='Tradeweb'):
    """
    实时10Y美债入库：只做盘中参考，不覆盖日频 YC10Y。
    series_id = US10Y_RT_TRADEWEB
    用途：盘中监控/预警，不参与 Risk Gate、不参与中美/美日/美德利差计算。
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT OR REPLACE INTO observations "
            "(series_id, timestamp, value, source, retrieved_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            ('US10Y_RT_TRADEWEB', quote_time_bj, float(value), source)
        )
        conn.commit()
        conn.close()
        print(f"✅ 已写入实时10Y: {value:.3f}% @ {quote_time_bj} [{source}]")
    except Exception as e:
        print(f"❌ 实时10Y入库失败: {e}")


def fetch_yahoo(symbol, series_id):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    # 🆕 核心修复：将 range 从 1mo 改为 5y，为分位数计算提供足够长的历史窗口
    params = {"interval": "1d", "range": "5y"} 
    headers = {"User-Agent": "Mozilla/5.0"}
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
        print(f"  ❌ {symbol} 抓取失败: {e}")
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
        return [{
            'series_id': series_id,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'value': float(fields[8]),
            'source': 'sina_futures'
        }]
    except:
        return []


def main():
    print(f"\n{'='*60}\n  扩展宏观数据采集\n{'='*60}\n")
    all_rows = []

    # 1. 市场广度 (算 20日动量差：RSP收益率 - SPY收益率)
    print("🔄 正在抓取 市场广度 (SPY / RSP)...")
    spy_rows = fetch_yahoo('SPY', 'SPY_PRICE')
    rsp_rows = fetch_yahoo('RSP', 'RSP_PRICE')
    if spy_rows and rsp_rows:
        all_rows.extend(spy_rows)
        all_rows.extend(rsp_rows)
        if len(spy_rows) >= 20 and len(rsp_rows) >= 20:
            spy_ret = (spy_rows[-1]['value'] / spy_rows[-20]['value']) - 1
            rsp_ret = (rsp_rows[-1]['value'] / rsp_rows[-20]['value']) - 1
            breadth_momentum = (rsp_ret - spy_ret) * 100
            all_rows.append({
                'series_id': 'BREADTH_20D_MOMENTUM',
                'date': spy_rows[-1]['date'],
                'value': breadth_momentum,
                'source': 'calc_breadth'
            })
            print(f"  ✅ 市场广度 20D 动量: {breadth_momentum:+.2f}% (负数说明小盘股拖累大盘)")

    # 2. 黄金 ETF (GLD)
    print("🔄 正在抓取 黄金 ETF (GLD)...")
    gld_rows = fetch_yahoo('GLD', 'GLD_PRICE')
    if gld_rows:
        print(f"  ✅ GLD: {gld_rows[-1]['value']:.2f}")
        all_rows.extend(gld_rows)

    # 3. 离岸人民币 (USD/CNH)
    print("🔄 正在抓取 离岸人民币 (USD/CNH)...")
    cnh_rows = fetch_yahoo('CNH=X', 'USD_CNH')
    if cnh_rows:
        print(f"  ✅ USD/CNH: {cnh_rows[-1]['value']:.4f}")
        all_rows.extend(cnh_rows)

    # 4. VIX3M
    print("🔄 正在抓取 VIX3M (^VIX3M)...")
    vix3m_rows = fetch_yahoo('^VIX3M', 'VIX3M')
    if vix3m_rows:
        print(f"  ✅ VIX3M: {vix3m_rows[-1]['value']:.2f}")
        all_rows.extend(vix3m_rows)

    # 5. 黑色系
    print("🔄 正在抓取 螺纹钢/铁矿石...")
    rb = fetch_sina_futures('RB0', 'REBAR')
    if rb:
        all_rows.extend(rb)
        print(f"  ✅ 螺纹钢: {rb[-1]['value']:.1f}")
    i0 = fetch_sina_futures('I0', 'IRON_ORE_DOMESTIC')
    if i0:
        all_rows.extend(i0)
        print(f"  ✅ 铁矿石内盘: {i0[-1]['value']:.1f}")
    tio = fetch_yahoo('TIO=F', 'IRON_ORE_FOREIGN')
    if tio:
        all_rows.extend(tio)
        print(f"  ✅ 铁矿石外盘: {tio[-1]['value']:.2f}")

    save_to_db(all_rows)


if __name__ == '__main__':
    # 用法1：常规日频采集
    #   python extra_macro.py
    # 用法2：写入盘中实时10Y（不覆盖 YC10Y，只做参考）
    #   python extra_macro.py realtime_us10y 4.917 "2026-11-02 22:16"
    if len(sys.argv) >= 3 and sys.argv[1] == 'realtime_us10y':
        _val = float(sys.argv[2])
        _ts = sys.argv[3] if len(sys.argv) > 3 else datetime.now().strftime('%Y-%m-%d %H:%M')
        save_realtime_us10y(_val, _ts, source='Tradeweb')
    else:
        main()