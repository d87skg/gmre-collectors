# -*- coding: utf-8 -*-
"""tools/send_local_feishu.py - 全息推演版（含核心资产矩阵 + N/A兜底）"""
import os
import requests
import json
import hmac
import hashlib
import base64
import time
import sqlite3
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv(r'D:\HGZC\.env')
WEBHOOK = os.environ.get('FEISHU_WEBHOOK')
SECRET = os.environ.get('FEISHU_SECRET')
DB_PATH = 'data/macro.db'

def gen_sign(timestamp, secret):
    string_to_sign = f'{timestamp}\n{secret}'
    hmac_code = hmac.new(string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
    return base64.b64encode(hmac_code).decode('utf-8')

def get_latest_data():
    asof = datetime.now().strftime('%Y-%m-%d')
    data = {
        'asof': asof,
        'frag_score': 0.0, 'frag_level': 'N/A',
        'risk_gate': 'UNKNOWN', 'stress_layers': 'NONE',
        'caps_al': 'N/A', 'caps_cu': 'N/A', 
        'lti_score': 0.0, 'lti_level': 'UNKNOWN',
        'y10': 0.0, 'rrp': 0.0, 'hy_oas': 0.0, 'vix': 0.0,
        'bitget_fr': 0.0, 'coinbase_prem': 0.0, 'hl_imb': 0.0,
        'btc_etf_flow': 0.0, 'fear_greed': 0,
        'lti_raw_fr': 0.0, 'lti_raw_imb': 0.0,
        # 新增：大类资产与汇率
        'gold': 0.0, 'silver': 0.0, 'oil': 0.0, 'copper': 0.0,
        'dxy': 0.0, 'usdjpy': 0.0, 'usdcny': 0.0, 'spx': 0.0
    }
    
    try:
        conn = sqlite3.connect(DB_PATH)
        
        # 1. 每日结论
        row = conn.execute("SELECT risk_gate, stress_state, frag_level FROM daily_summary WHERE asof_date=?", (asof,)).fetchone()
        if row:
            data['risk_gate'] = row[0]
            data['stress_layers'] = row[1]
            data['frag_level'] = row[2]
            try:
                data['frag_score'] = float(row[2].split('(')[1].split(')')[0])
            except:
                pass
            
        # 2. CAPS / LTI
        row = conn.execute("SELECT caps_score FROM caps_engine WHERE asof_date=? AND symbol='SHFE_ALUMINUM'", (asof,)).fetchone()
        data['caps_al'] = round(row[0], 1) if row and row[0] is not None else 'N/A'
        
        row = conn.execute("SELECT caps_score FROM caps_engine WHERE asof_date=? AND symbol='SHFE_COPPER'", (asof,)).fetchone()
        data['caps_cu'] = round(row[0], 1) if row and row[0] is not None else 'N/A'
        
        row = conn.execute("SELECT lti_score, level FROM lti_engine WHERE asof_date=?", (asof,)).fetchone()
        if row:
            data['lti_score'] = round(row[0], 1)
            data['lti_level'] = row[1]

        # 3. 核心宏观数据 (从 observations 兜底)
        def get_val(sid):
            r = conn.execute("SELECT value FROM observations WHERE series_id=? ORDER BY timestamp DESC LIMIT 1", (sid,)).fetchone()
            return r[0] if r else 0.0
            
        data['y10'] = get_val('YC10Y')
        data['rrp'] = get_val('RRP_BALANCE')
        data['hy_oas'] = get_val('HY_SPREAD')
        data['vix'] = get_val('VIX')
        
        # 4. 最新飞书快照（包含大类资产、汇率与微观异动）
        row = conn.execute("SELECT * FROM feishu_snapshot ORDER BY timestamp DESC LIMIT 1").fetchone()
        if row:
            cols = [d[0] for d in conn.execute("SELECT * FROM feishu_snapshot LIMIT 1").description]
            f_data = dict(zip(cols, row))
            
            # 微观异动
            data['bitget_fr'] = float(f_data.get('bitget_btc_fr', 0) or 0)
            data['coinbase_prem'] = float(f_data.get('coinbase_premium', 0) or 0)
            data['hl_imb'] = float(f_data.get('hl_imbalance_btc', 0) or 0)
            data['btc_etf_flow'] = float(f_data.get('btc_etf_flow_usd_m', 0) or 0)
            data['fear_greed'] = int(float(f_data.get('fear_greed', 0) or 0))
            data['lti_raw_fr'] = data['bitget_fr']
            data['lti_raw_imb'] = data['hl_imb']
            
            # 新增：从快照读取大类资产和汇率
            data['gold'] = float(f_data.get('gold', 0) or 0)
            data['silver'] = float(f_data.get('silver', 0) or 0)
            data['oil'] = float(f_data.get('oil', 0) or 0)
            data['copper'] = float(f_data.get('copper', 0) or 0)
            data['dxy'] = float(f_data.get('dxy', 0) or 0)
            data['usdjpy'] = float(f_data.get('usdjpy', 0) or 0)
            data['usdcny'] = float(f_data.get('usdcny_mid', 0) or 0)  # 注意：快照字段可能是 usdcny_mid 或者没抓到
            if data['usdcny'] == 0:
                data['usdcny'] = get_val('USDCNY_MID') # 如果快照没抓到，去宏观库里找
            data['spx'] = float(f_data.get('ndx', 0) or 0) # 快照里的 NDX 纳指通常代表美股

    except Exception as e:
        print(f"⚠️ 读取数据库失败: {e}")
    finally:
        if 'conn' in locals():
            conn.close()
            
    return data

def main():
    if not WEBHOOK or not SECRET:
        print("❌ 缺少飞书 WEBHOOK 或 SECRET")
        return

    d = get_latest_data()
    
    # 构造微观异动警报
    micro_alerts = []
    if d['bitget_fr'] > 50:
        micro_alerts.append(f"🚨 资金费率极度拥挤: {d['bitget_fr']:+.2f}% 年化")
    if d['coinbase_prem'] < -0.1:
        micro_alerts.append(f"🇺🇸 机构现货抛压: {d['coinbase_prem']:+.3f}%")
    if d['hl_imb'] > 0.3:
        micro_alerts.append(f"📊 盘口买盘堆积 (诱多风险): 不平衡 {d['hl_imb']:+.3f}")
    elif d['hl_imb'] < -0.3:
        micro_alerts.append(f"📊 盘口卖压厚 (踩踏风险): 不平衡 {d['hl_imb']:+.3f}")
    if d['btc_etf_flow'] > 500:
        micro_alerts.append(f"💰 BTC ETF 大额流入: ${d['btc_etf_flow']:.1f}M")
    elif d['btc_etf_flow'] < -500:
        micro_alerts.append(f"💰 BTC ETF 大额流出: ${d['btc_etf_flow']:.1f}M")

    micro_text = "\n".join(micro_alerts) if micro_alerts else "  · 微观结构暂无极端异动"

    # 图标动态判断
    icon_cu = "🟡" if d['caps_cu'] == 'N/A' else ("🚨" if isinstance(d['caps_cu'], float) and d['caps_cu'] >= 60 else "🟡")
    icon_al = "🚨" if d['caps_al'] == 'N/A' else ("🚨" if isinstance(d['caps_al'], float) and d['caps_al'] >= 60 else "🟡")

    # 获取北京时间
    bj_time = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')

    text = f"""📊 **GMRE 3.3 全息风控晨报** - {d['asof']}
====================================
🚦 **Risk Gate**: {d['risk_gate']}
⚠️ **Fragility**: {d['frag_level']}
😱 **情绪指数**: {d['fear_greed']} (Fear & Greed)

🌍 **大类资产与汇率矩阵**:
  • 黄金: ${d['gold']:.2f} | 白银: ${d['silver']:.2f}
  • 原油 (WTI): ${d['oil']:.2f} | 铜: ${d['copper']:.2f}
  • 美股 (纳指): {d['spx']:.1f}
  • 美元指数: {d['dxy']:.2f} | 美元/日元: {d['usdjpy']:.2f}
  • 美元/人民币: {d['usdcny']:.2f}

🌐 **核心宏观数据**:
  • 10Y 美债: {d['y10']:.2f}%
  • RRP 余额: {d['rrp']:.2f} B USD (枯竭)
  • HY OAS: {d['hy_oas']*100:.0f} bp
  • VIX: {d['vix']:.2f}

🚨 **压力层 (S 状态机)**:
  {d['stress_layers']}

🔬 **微观异动警报**:
{micro_text}

📦 **商品逼仓 (CAPS)**:
  • 沪铜: {icon_cu} {d['caps_cu']}
  • 沪铝: {icon_al} {d['caps_al']}

💧 **清算透明度 (LTI)**:
  • {d['lti_level']} ({d['lti_score']})
  • FR极值分: {d['lti_raw_fr']:.1f} | 盘口不平衡: {d['lti_raw_imb']:.3f}
====================================
⏱️ 生成时间: {bj_time} (北京时间)
"""
    
    ts = str(int(time.time()))
    payload = {
        "timestamp": ts,
        "sign": gen_sign(ts, SECRET),
        "msg_type": "text",
        "content": {"text": text}
    }
    
    r = requests.post(WEBHOOK, json=payload, timeout=10)
    if r.status_code == 200 and r.json().get('code') == 0:
        print("✅ 全息晨报已成功推送到飞书！")
    else:
        print(f"❌ 飞书推送失败: {r.text}")

if __name__ == "__main__":
    main()