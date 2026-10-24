# -*- coding: utf-8 -*-
"""tools/send_local_feishu.py - 全息推演版（直接读取最终结论）"""
import os
import requests
import json
import hmac
import hashlib
import base64
import time
import sqlite3
from datetime import datetime
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
        'caps_al': 0.0, 'caps_cu': 0.0,
        'lti_score': 0.0, 'lti_level': 'UNKNOWN',
        'y10': 0.0, 'rrp': 0.0, 'hy_oas': 0.0, 'vix': 0.0,
        'bitget_fr': 0.0, 'coinbase_prem': 0.0, 'hl_imb': 0.0,
        'btc_etf_flow': 0.0, 'fear_greed': 0,
        'lti_raw_fr': 0.0, 'lti_raw_imb': 0.0  # 新增默认值
    }
    
    try:
        conn = sqlite3.connect(DB_PATH)
        
        # 1. 直接读取每日结论表
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
        if row: data['caps_al'] = row[0]
        row = conn.execute("SELECT caps_score FROM caps_engine WHERE asof_date=? AND symbol='SHFE_COPPER'", (asof,)).fetchone()
        if row: data['caps_cu'] = row[0]
        
        row = conn.execute("SELECT lti_score, level FROM lti_engine WHERE asof_date=?", (asof,)).fetchone()
        if row:
            data['lti_score'] = round(row[0], 1)
            data['lti_level'] = row[1]

        # 3. 核心宏观数据
        def get_val(sid):
            r = conn.execute("SELECT value FROM observations WHERE series_id=? ORDER BY timestamp DESC LIMIT 1", (sid,)).fetchone()
            return r[0] if r else 0.0
            
        data['y10'] = get_val('YC10Y')
        data['rrp'] = get_val('RRP_BALANCE')
        data['hy_oas'] = get_val('HY_SPREAD')
        data['vix'] = get_val('VIX')
        
        # 4. 微观异动
        row = conn.execute("SELECT * FROM feishu_snapshot ORDER BY timestamp DESC LIMIT 1").fetchone()
        if row:
            cols = [d[0] for d in conn.execute("SELECT * FROM feishu_snapshot LIMIT 1").description]
            f_data = dict(zip(cols, row))
            data['bitget_fr'] = float(f_data.get('bitget_btc_fr', 0) or 0)
            data['coinbase_prem'] = float(f_data.get('coinbase_premium', 0) or 0)
            data['hl_imb'] = float(f_data.get('hl_imbalance_btc', 0) or 0)
            data['btc_etf_flow'] = float(f_data.get('btc_etf_flow_usd_m', 0) or 0)
            data['fear_greed'] = int(float(f_data.get('fear_greed', 0) or 0))
            
            # 赋值给 LTI 的原始变量
            data['lti_raw_fr'] = data['bitget_fr']
            data['lti_raw_imb'] = data['hl_imb']

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

    text = f"""📊 **GMRE 3.3 全息风控晨报** - {d['asof']}
====================================
🚦 **Risk Gate**: {d['risk_gate']}
⚠️ **Fragility**: {d['frag_level']}
😱 **情绪指数**: {d['fear_greed']} (Fear & Greed)

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
  • 沪铜: 🟡 {d['caps_cu']}
  • 沪铝: 🚨 {d['caps_al']}

💧 **清算透明度 (LTI)**:
  • {d['lti_level']} ({d['lti_score']})
  • FR极值分: {d['lti_raw_fr']:.1f} | 盘口不平衡: {d['lti_raw_imb']:.3f}
====================================
⏱️ 生成时间: {datetime.now().strftime('%H:%M')}
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