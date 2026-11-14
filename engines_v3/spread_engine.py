# engines_v3/spread_engine.py
import requests
import sqlite3
import re
from datetime import datetime

DB_PATH = 'data/macro.db'

def fetch_sina_price(symbol):
    url = f"https://hq.sinajs.cn/list={symbol}"
    headers = {"Referer": "https://finance.sina.com.cn/"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        match = re.search(r'"([^"]+)"', r.text)
        if not match:
            return None
            
        fields = match.group(1).split(',')
        
        if symbol.startswith('nf_'):
            for idx in [8, 2, 3, 4, 5]:
                if len(fields) > idx:
                    try:
                        val = float(fields[idx])
                        if val > 0: return val
                    except ValueError:
                        continue
        elif symbol.startswith('hf_'):
            for idx in [0, 1, 2, 3]:
                try:
                    val = float(fields[idx])
                    if val > 0: return val
                except (ValueError, IndexError):
                    continue
        elif symbol.startswith('fx_'):
            for idx in [1, 2, 3]:
                try:
                    val = float(fields[idx])
                    if val > 0: return val
                except (ValueError, IndexError):
                    continue
    except Exception as e:
        print(f"❌ {symbol} 抓取异常: {e}")
    return None

def main():
    print("⏳ 正在计算内外盘铜价差...")
    
    shfe_cu = fetch_sina_price("nf_CU0")
    lme_cu = fetch_sina_price("hf_CAD")
    usdcny = fetch_sina_price("fx_susdcny")
    
    if not usdcny:
        usdcny = 7.12 
        
    if shfe_cu and lme_cu:
        lme_cu_cny = lme_cu * usdcny
        
        spread = shfe_cu - lme_cu_cny
        spread_pct = (spread / lme_cu_cny) * 100
        
        print(f"✅ 沪铜连续: {shfe_cu:,.0f} 元/吨")
        print(f"✅ LME 铜: ${lme_cu:,.0f}/吨 (折合人民币: {lme_cu_cny:,.0f} 元/吨)")
        print(f"✅ 内外盘价差: {spread:+,.0f} 元/吨 ({spread_pct:+.2f}%)")
        
        conn = sqlite3.connect(DB_PATH)
        today = datetime.now().strftime('%Y-%m-%d')
        
        # 🆕 适配新表结构：替换 timestamp 为 obs_ts，并补充 obs_date 与 ingest_at
        conn.execute("INSERT OR REPLACE INTO observations (series_id, obs_ts, obs_date, value, source, ingest_at) VALUES (?, ?, ?, ?, ?, datetime('now'))", 
                     ('SHFE_COPPER_PRICE', today, today, shfe_cu, 'sina_CU0'))
        conn.execute("INSERT OR REPLACE INTO observations (series_id, obs_ts, obs_date, value, source, ingest_at) VALUES (?, ?, ?, ?, ?, datetime('now'))", 
                     ('LME_COPPER_PRICE', today, today, lme_cu, 'sina_LME'))
        conn.execute("INSERT OR REPLACE INTO observations (series_id, obs_ts, obs_date, value, source, ingest_at) VALUES (?, ?, ?, ?, ?, datetime('now'))", 
                     ('CU_SPREAD_PCT', today, today, spread_pct, 'spread_engine'))
        conn.commit()
        conn.close()
        
        if spread_pct > 2.0:
            print("🚨 [警报] 沪铜大幅升水，进口盈利窗口打开，可能存在逼空风险！")
        elif spread_pct < -2.0:
            print("🚨 [警报] 沪铜大幅贴水，出口窗口打开，或国内需求极度疲软。")
    else:
        print("❌ 数据获取不全，跳过内外盘价差计算。")

if __name__ == '__main__':
    main()