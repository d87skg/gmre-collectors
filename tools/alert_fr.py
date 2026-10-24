# -*- coding: utf-8 -*-
import sqlite3, os, requests, json, hmac, hashlib, base64, time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(r'D:\HGZC\.env')
WEBHOOK = os.environ.get('FEISHU_WEBHOOK')
SECRET = os.environ.get('FEISHU_SECRET')

def gen_sign(ts, secret):
    s = f'{ts}\n{secret}'
    return base64.b64encode(hmac.new(s.encode('utf-8'), digestmod=hashlib.sha256).digest()).decode('utf-8')

def check_and_alert():
    conn = sqlite3.connect('data/macro.db')
    row = conn.execute("SELECT bitget_btc_fr, hl_imbalance_btc FROM feishu_snapshot ORDER BY timestamp DESC LIMIT 1").fetchone()
    conn.close()
    
    if not row: return
    fr, hl = float(row[0]), float(row[1])
    
    # 触发阈值：费率 > 50% 或 < -20%，或者盘口极度失衡
    if abs(fr) > 50 or hl < -0.4 or hl > 0.4:
        text = f"🚨 **结算节点微观异动** ({datetime.now().strftime('%H:%M')})\n"
        text += f"• Bitget 资金费率: {fr:+.2f}% 年化\n"
        text += f"• HL 盘口不平衡: {hl:+.3f}\n"
        text += "⚠️ 杠杆正在撕裂，警惕连环爆仓！"
        
        ts = str(int(time.time()))
        payload = {"timestamp": ts, "sign": gen_sign(ts, SECRET), "msg_type": "text", "content": {"text": text}}
        requests.post(WEBHOOK, json=payload)
        print("✅ 微观异动已报警")

if __name__ == "__main__":
    check_and_alert()