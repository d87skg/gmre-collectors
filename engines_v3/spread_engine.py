# engines_v3/spread_engine.py
import requests
import sqlite3
import re
from datetime import datetime

DB_PATH = 'data/macro.db'

def fetch_sina_price(symbol):
    """去新浪抓期货价格，进行智能解析"""
    url = f"https://hq.sinajs.cn/list={symbol}"
    headers = {"Referer": "https://finance.sina.com.cn/"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        match = re.search(r'"([^"]+)"', r.text)
        if not match:
            return None
            
        fields = match.group(1).split(',')
        
        # 特殊处理：内盘期货 (nf_)
        if symbol.startswith('nf_'):
            # 通常索引 8 是买一价，索引 2 是开盘价，索引 3 是最高价
            for idx in [8, 2, 3, 4, 5]:
                if len(fields) > idx:
                    try:
                        val = float(fields[idx])
                        if val > 0: return val
                    except ValueError:
                        continue
        # 特殊处理：外盘期货 (hf_)
        elif symbol.startswith('hf_'):
            for idx in [0, 1, 2, 3]:
                try:
                    val = float(fields[idx])
                    if val > 0: return val
                except (ValueError, IndexError):
                    continue
        # 特殊处理：外汇 (fx_)
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
    
    # 1. 抓取价格
    # nf_CU0: 沪铜连续；hf_CAD: LME 铜 3 个月
    shfe_cu = fetch_sina_price("nf_CU0")
    lme_cu = fetch_sina_price("hf_CAD")
    usdcny = fetch_sina_price("fx_susdcny")
    
    if not usdcny:
        usdcny = 7.12 # 兜底汇率
        
    if shfe_cu and lme_cu:
        # 统一单位: LME 是美元/吨，沪铜是人民币/吨
        # 注意：LME 铜的报价单位通常是美元/吨。
        lme_cu_cny = lme_cu * usdcny
        
        # 计算价差 (人民币/吨)
        spread = shfe_cu - lme_cu_cny
        spread_pct = (spread / lme_cu_cny) * 100
        
        print(f"✅ 沪铜连续: {shfe_cu:,.0f} 元/吨")
        print(f"✅ LME 铜: ${lme_cu:,.0f}/吨 (折合人民币: {lme_cu_cny:,.0f} 元/吨)")
        print(f"✅ 内外盘价差: {spread:+,.0f} 元/吨 ({spread_pct:+.2f}%)")
        
        # 3. 存入数据库
        conn = sqlite3.connect(DB_PATH)
        today = datetime.now().strftime('%Y-%m-%d')
        
        conn.execute("INSERT OR REPLACE INTO observations (series_id, timestamp, value, source, retrieved_at) VALUES (?, ?, ?, ?, datetime('now'))", 
                     ('SHFE_COPPER_PRICE', today, shfe_cu, 'sina_CU0'))
        conn.execute("INSERT OR REPLACE INTO observations (series_id, timestamp, value, source, retrieved_at) VALUES (?, ?, ?, ?, datetime('now'))", 
                     ('LME_COPPER_PRICE', today, lme_cu, 'sina_LME'))
        conn.execute("INSERT OR REPLACE INTO observations (series_id, timestamp, value, source, retrieved_at) VALUES (?, ?, ?, ?, datetime('now'))", 
                     ('CU_SPREAD_PCT', today, spread_pct, 'spread_engine'))
        conn.commit()
        conn.close()
        
        # 预警判定
        if spread_pct > 2.0:
            print("🚨 [警报] 沪铜大幅升水，进口盈利窗口打开，可能存在逼空风险！")
        elif spread_pct < -2.0:
            print("🚨 [警报] 沪铜大幅贴水，出口窗口打开，或国内需求极度疲软。")
    else:
        print("❌ 数据获取不全，跳过内外盘价差计算。")

if __name__ == '__main__':
    main()