# -*- coding: utf-8 -*-
"""collectors/fallback_collectors.py - 国内备用数据源采集探针（新浪终极版）"""
import requests
import pandas as pd
from datetime import datetime, timedelta
import time
import warnings
import re
warnings.filterwarnings('ignore')

def fetch_tencent_realtime(symbol):
    """
    兼容原函数名，但内部已全面切换为【新浪财经】实时接口。
    新浪接口格式极其稳定，彻底解决腾讯接口数字截断和乱码问题。
    """
    # 腾讯代号 -> 新浪代号 映射表
    sina_map = {
        'usINX': 'gb_$inx',         # 标普500
        'usDJI': 'gb_$dji',         # 道指
        'usIXIC': 'gb_$ixic',       # 纳指
        'hf_GC': 'hf_GC',           # 黄金
        'hf_CL': 'hf_CL',           # 原油
        'hf_SI': 'hf_SI',           # 白银
        'fx_susdjpy': 'fx_susdjpy', # 美元/日元
        'fx_susdcnh': 'fx_susdcnh', # 美元/离岸人民币
        'fx_susdcny': 'fx_susdcny', # 美元/在岸人民币
    }
    
    sina_sym = sina_map.get(symbol, symbol)
    url = f"https://hq.sinajs.cn/list={sina_sym}"
    headers = {"Referer": "https://finance.sina.com.cn/", "User-Agent": "Mozilla/5.0"}
    
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code != 200: return None
        data_str = r.text.split('="')[1].split('"')[0]
        if not data_str or "FAILED" in data_str: return None
        
        fields = data_str.split(',')
        price = None
        
        # 1. 美股指数 (gb_ 开头)
        if sina_sym.startswith('gb_'):
            # 新浪美股格式：名称, 当前价, 涨跌幅, 时间(YYYY-MM-DD HH:MM:SS)...
            price = float(fields[1])
            
        # 2. 外盘期货 (hf_ 开头)
        elif sina_sym.startswith('hf_'):
            # 新浪外盘格式：当前价, 涨跌, 买价, 卖价, 最高, 最低, 时间...
            price = float(fields[0])
            
        # 3. 外汇 (fx_ 开头)
        elif sina_sym.startswith('fx_'):
            # 新浪外汇格式：时间, 当前价, 买价, 卖价...
            price = float(fields[1])
            
        if price is None or price <= 0: return None
        
        # 日期统一用本地今天（因为是实时快照）
        date_str = datetime.now().strftime('%Y-%m-%d')
        
        return {'date': date_str, 'value': price, 'source': 'sina_fallback'}
    except Exception as e:
        print(f"  ⚠️ 新浪行情 {sina_sym} 失败: {str(e)[:40]}")
        return None

def fetch_akshare_index_us(symbol, start_date=None, limit=30):
    """AKShare 美股指数历史（用于降级补历史）"""
    try:
        import akshare as ak
        df = ak.index_us_stock_sina(symbol=symbol)
        if df.empty: return []
        df = df.rename(columns={'date': 'date', 'close': 'value'})
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        df['value'] = pd.to_numeric(df['value'], errors='coerce')
        df = df.dropna()
        if start_date:
            df = df[df['date'] > start_date]
        if len(df) > limit:
            df = df.tail(limit)
        rows = df.to_dict('records')
        for r in rows: r['source'] = 'akshare_index'
        return rows
    except Exception as e:
        print(f"  ⚠️ AKShare 指数 {symbol} 失败: {str(e)[:40]}")
        return []

def fetch_akshare_forex(pair, start_date=None, limit=30):
    """AKShare 外汇历史"""
    try:
        import akshare as ak
        df = ak.forex_hist_em(symbol=pair)
        if df.empty: return []
        df = df.rename(columns={'日期': 'date', '收盘': 'value'})
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        df['value'] = pd.to_numeric(df['value'], errors='coerce')
        df = df.dropna()
        if start_date:
            df = df[df['date'] > start_date]
        if len(df) > limit:
            df = df.tail(limit)
        rows = df.to_dict('records')
        for r in rows: r['source'] = 'akshare_forex'
        return rows
    except Exception as e:
        print(f"  ⚠️ AKShare 外汇 {pair} 失败: {str(e)[:40]}")
        return []

def fetch_akshare_commodity(symbol, start_date=None, limit=30):
    """AKShare 外盘商品期货历史"""
    try:
        import akshare as ak
        df = ak.futures_foreign_hist(symbol=symbol)
        if df.empty: return []
        df = df.rename(columns={'date': 'date', 'close': 'value'})
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        df['value'] = pd.to_numeric(df['value'], errors='coerce')
        df = df.dropna()
        if start_date:
            df = df[df['date'] > start_date]
        if len(df) > limit:
            df = df.tail(limit)
        rows = df.to_dict('records')
        for r in rows: r['source'] = 'akshare_commodity'
        return rows
    except Exception as e:
        print(f"  ⚠️ AKShare 商品 {symbol} 失败: {str(e)[:40]}")
        return []

if __name__ == "__main__":
    # 单元测试
    print("测试新浪 SP500:", fetch_tencent_realtime('usINX'))
    print("测试新浪 黄金:", fetch_tencent_realtime('hf_GC'))
    print("测试新浪 原油:", fetch_tencent_realtime('hf_CL'))
    print("测试新浪 外汇:", fetch_tencent_realtime('fx_susdjpy'))
    print("测试 AKShare 外汇:", fetch_akshare_forex('USDJPY')[:1])