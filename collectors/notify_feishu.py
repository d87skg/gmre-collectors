"""
飞书机器人通知（带签名校验）
环境变量: FEISHU_WEBHOOK, FEISHU_SECRET
"""
import os
import sys
import time
import hmac
import base64
import hashlib
import requests
import pandas as pd
from pathlib import Path

WEBHOOK = os.environ.get('FEISHU_WEBHOOK')
SECRET = os.environ.get('FEISHU_SECRET')


def gen_sign(timestamp, secret):
    """飞书签名算法"""
    string_to_sign = f'{timestamp}\n{secret}'
    hmac_code = hmac.new(
        string_to_sign.encode('utf-8'),
        digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(hmac_code).decode('utf-8')


def build_message():
    lines = ["📊 GMRE 数据更新", ""]

    # === CFTC ===
    p = Path('data/cftc_cot.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            if not df.empty:
                latest = df['date'].max()
                df = df[df['date'] == latest].sort_values('series_id')
                lines.append(f"🏦 CFTC COT ({latest})")
                for _, r in df.iterrows():
                    net = int(r['net_noncommercial'])
                    sid = str(r['series_id']).replace('COT_', '')
                    lines.append(f"  {sid}: {net:+,}")
                lines.append("")
        except Exception as e:
            lines.append(f"🏦 CFTC 解析失败: {e}")
            lines.append("")

    # === Deribit DVOL ===
    p = Path('data/deribit_dvol.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            latest_date = df['date'].max()
            df = df[df['date'] == latest_date]
            lines.append(f"📉 Deribit DVOL ({latest_date})")
            for _, r in df.iterrows():
                ccy = r['currency']
                close = float(r['close'])
                lines.append(f"  {ccy}: {close:.2f}")
            lines.append("")
        except Exception as e:
            lines.append(f"📉 DVOL 解析失败: {e}")
            lines.append("")

    # === Blockchain.com On-chain ===
    p = Path('data/blockchain_com.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            latest = df.sort_values('date').iloc[-1]
            date = latest['date']
            price = latest.get('market-price')
            txs = latest.get('n-transactions')
            addr = latest.get('n-unique-addresses')
            lines.append(f"⛓️ BTC On-chain ({date})")
            if pd.notna(price):
                lines.append(f"  价格: ${float(price):,.0f}")
            if pd.notna(txs):
                lines.append(f"  日交易: {int(txs):,}")
            if pd.notna(addr):
                lines.append(f"  活跃地址: {int(addr):,}")
            lines.append("")
        except Exception as e:
            lines.append(f"⛓️ On-chain 解析失败: {e}")
            lines.append("")

    # === Fear & Greed ===
    p = Path('data/fear_greed.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            latest = df.sort_values('date').iloc[-1]
            date = latest['date']
            value = int(latest['value'])
            cls = latest['classification']
            lines.append(f"😱 Fear & Greed ({date})")
            lines.append(f"  {value} - {cls}")
            lines.append("")
        except Exception as e:
            lines.append(f"😱 FearGreed 解析失败: {e}")
            lines.append("")

    # === Farside BTC ETF Flow ===
    p = Path('data/farside_btc_etf.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            # 只保留日期行（如 "01 Oct 2026"）
            mask = df.iloc[:, 0].astype(str).str.match(r'\d{2} \w{3} \d{4}')
            df = df[mask]
            # 第 13 列是 Total，只保留有数字且非 0 的行
            total_col = pd.to_numeric(df.iloc[:, 13], errors='coerce')
            df = df[total_col.notna() & (total_col != 0)]
            if not df.empty:
                last = df.iloc[-1]
                date = last.iloc[0]
                total = last.iloc[13]
                lines.append(f"📈 BTC ETF Flow")
                lines.append(f"  {date}: {total}")
                lines.append("")
        except Exception as e:
            lines.append(f"📈 Farside 解析失败: {e}")
            lines.append("")

    lines.append("🔗 github.com/d87skg/gmre-collectors")
    return "\n".join(lines)


def send(content):
    timestamp = str(int(time.time()))
    payload = {
        "timestamp": timestamp,
        "sign": gen_sign(timestamp, SECRET),
        "msg_type": "text",
        "content": {
            "text": content
        }
    }
    r = requests.post(WEBHOOK, json=payload, timeout=30)
    print(f'Feishu: HTTP {r.status_code}')
    print(r.text)


def main():
    if not WEBHOOK or not SECRET:
        print('❌ 缺 FEISHU_WEBHOOK 或 FEISHU_SECRET')
        sys.exit(1)

    msg = build_message()
    print('===== 消息内容 =====')
    print(msg)
    print('===================')

    send(msg)


if __name__ == '__main__':
    main()