# -*- coding: utf-8 -*-
"""collectors/realtime_market.py - 强力实时行情覆写（Yahoo原生 + 腾讯兜底）"""
import sqlite3
import requests
import re
from datetime import datetime, timezone

DB_PATH = 'data/macro.db'

def fetch_yahoo_raw(symbol):
    """直接请求 Yahoo 底层 JSON，绕过第三方库限流"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"interval": "1d", "range": "5d"} 
    # 必须伪装成浏览器
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            result = data.get('chart', {}).get('result', [])
            if result:
                timestamps = result[0].get('timestamp', [])
                closes = result[0].get('indicators', {}).get('quote', [{}])[0].get('close', [])
                for ts, c in zip(reversed(timestamps), reversed(closes)):
                    if c is not None:
                        d = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d')
                        return d, float(c)
    except Exception:
        pass
    return None, None

def fetch_tencent_realtime(code, name):
    """腾讯财经接口兜底（国内极稳）"""
    url = f"http://qt.gtimg.cn/q={code}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            # 返回格式: v_usINX="100~标普500~.INX~7554.23~..."
            match = re.search(r'~([\d.]+)~', r.text)
            if match:
                # 腾讯接口不返回日期，默认用今天
                today = datetime.now().strftime('%Y-%m-%d')
                return today, float(match.group(1))
    except Exception:
        pass
    return None, None

def fetch_realtime():
    print("🔄 正在通过原生接口拉取最新行情...")
    
    # 1. 尝试 Yahoo 原生
    spx_date, spx_val = fetch_yahoo_raw('^GSPC')
    vix_date, vix_val = fetch_yahoo_raw('^VIX')
    
    # 2. 如果 Yahoo 挂了，用腾讯兜底
    if spx_val is None or vix_val is None:
        print("  ⚠️ Yahoo 接口不可用，降级到腾讯财经...")
        if spx_val is None: spx_date, spx_val = fetch_tencent_realtime('usINX', '标普500')
        if vix_val is None: vix_date, vix_val = fetch_tencent_realtime('usVIX', 'VIX')

    if spx_val is not None and vix_val is not None:
        conn = sqlite3.connect(DB_PATH)
        # 强制覆写
        conn.execute("INSERT OR REPLACE INTO observations (series_id, timestamp, value, source, retrieved_at) VALUES (?, ?, ?, ?, datetime('now'))",
                     ('SP500', spx_date, spx_val, 'realtime_fix'))
        conn.execute("INSERT OR REPLACE INTO observations (series_id, timestamp, value, source, retrieved_at) VALUES (?, ?, ?, ?, datetime('now'))",
                     ('VIX', vix_date, vix_val, 'realtime_fix'))
        conn.commit()
        conn.close()
        print(f"  ✅ SP500 ({spx_date}): {spx_val:.2f} | VIX ({vix_date}): {vix_val:.2f} (已强行覆盖)")
    else:
        print("  ❌ 所有免费接口均失败，将保留历史值")

if __name__ == "__main__":
    fetch_realtime()