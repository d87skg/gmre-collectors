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
    string_to_sign = f'{timestamp}\n{secret}'
    hmac_code = hmac.new(
        string_to_sign.encode('utf-8'),
        digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(hmac_code).decode('utf-8')


def build_message():
    lines = ["📊 GMRE 数据更新", ""]

    # === CFTC 金融期货 COT ===
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

    # === CFTC FX COT ===
    p = Path('data/cftc_fx.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            if not df.empty:
                latest = df['date'].max()
                df = df[df['date'] == latest].sort_values('series_id')
                lines.append(f"💱 FX COT ({latest})")
                for _, r in df.iterrows():
                    net = int(r['net_noncommercial'])
                    sid = str(r['series_id']).replace('COT_', '')
                    lines.append(f"  {sid}: {net:+,}")
                lines.append("")
        except Exception as e:
            lines.append(f"💱 FX COT 解析失败: {e}")
            lines.append("")

    # === NY Fed SOFR / EFFR / RRP ===
    p = Path('data/nyfed_rates.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            latest = df['date'].max()
            df = df[df['date'] == latest]
            lines.append(f"🏛️ NY Fed ({latest})")
            sofr = df[df['series'] == 'SOFR']['value']
            effr = df[df['series'] == 'EFFR']['value']
            rrp = df[df['series'] == 'RRP_BALANCE']['value']
            if not sofr.empty:
                s = float(sofr.iloc[0])
                lines.append(f"  SOFR: {s:.2f}%")
            if not effr.empty:
                e = float(effr.iloc[0])
                lines.append(f"  EFFR: {e:.2f}%")
            if not sofr.empty and not effr.empty:
                spread = (float(sofr.iloc[0]) - float(effr.iloc[0])) * 100
                lines.append(f"  利差: {spread:+.1f}bp")
            if not rrp.empty:
                r = float(rrp.iloc[0])
                lines.append(f"  RRP: ${r:.2f}B")
            lines.append("")
        except Exception as e:
            lines.append(f"🏛️ NY Fed 解析失败: {e}")
            lines.append("")

    # === FRED 宏观 ===
    p = Path('data/fred_macro.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            lines.append("💵 FRED 宏观")

            def latest(sid):
                sub = df[df['series'] == sid].sort_values('date')
                if sub.empty:
                    return None, None
                return float(sub.iloc[-1]['value']), sub.iloc[-1]['date']

            v, d = latest('WRESBAL')
            if v is not None:
                lines.append(f"  准备金: ${v/1e6:.2f}T ({d})")

            v, d = latest('BAMLH0A0HYM2')
            if v is not None:
                lines.append(f"  HY OAS: {v*100:.0f}bp ({d})")

            v, d = latest('BAMLC0A0CM')
            if v is not None:
                lines.append(f"  IG OAS: {v*100:.0f}bp")

            t2, _ = latest('DGS2')
            t10, _ = latest('DGS10')
            t30, _ = latest('DGS30')
            if t2 is not None:
                lines.append(f"  2Y: {t2:.2f}%")
            if t10 is not None:
                lines.append(f"  10Y: {t10:.2f}%")
            if t30 is not None:
                lines.append(f"  30Y: {t30:.2f}%")
            if t2 is not None and t10 is not None:
                lines.append(f"  2s10s: {(t10-t2)*100:+.0f}bp")

            v, _ = latest('THREEFYTP10')
            if v is not None:
                lines.append(f"  10Y 期限溢价: {v:.2f}%")

            cp, _ = latest('CPF3M')
            tb, _ = latest('TB3MS')
            if cp is not None and tb is not None:
                lines.append(f"  CP-Tbill: {(cp-tb)*100:+.0f}bp")

            cp60, _ = latest('RIFSPPNA2P2D60NB')
            if cp60 is not None and tb is not None:
                lines.append(f"  CP60-Tbill: {(cp60-tb)*100:+.0f}bp")

            v, d = latest('DRCRELEXFACBS')
            if v is not None:
                lines.append(f"  商业地产拖欠率: {v:.2f}% ({d})")

            lines.append("")
        except Exception as e:
            lines.append(f"💵 FRED 解析失败: {e}")
            lines.append("")

    # === DefiLlama 稳定币 ===
    p = Path('data/defillama_stablecoin.csv')
    if p.exists():
        try:
            df = pd.read_csv(p).sort_values('date')
            if len(df) >= 2:
                cur = float(df.iloc[-1]['total_usd']) / 1e9
                prev = float(df.iloc[-2]['total_usd']) / 1e9
                change = (cur - prev) / prev * 100
                lines.append(f"🪙 稳定币总市值 ({df.iloc[-1]['date']})")
                lines.append(f"  ${cur:.1f}B ({change:+.2f}% 日变)")
                lines.append("")
        except Exception as e:
            lines.append(f"🪙 DefiLlama 解析失败: {e}")
            lines.append("")

    # === Deribit Funding ===
    p = Path('data/deribit_funding.csv')
    if p.exists():
        try:
            df = pd.read_csv(p).sort_values('datetime')
            latest_dt = df['datetime'].max()
            df = df[df['datetime'] == latest_dt]
            lines.append(f"💰 Deribit Funding ({latest_dt} UTC)")
            for _, r in df.iterrows():
                sym = str(r['symbol'])
                rate = float(r['funding_rate']) * 100
                lines.append(f"  {sym}: {rate:+.4f}%")
            lines.append("")
        except Exception as e:
            lines.append(f"💰 Deribit Funding 解析失败: {e}")
            lines.append("")

    # === Deribit OI ===
    p = Path('data/deribit_oi.csv')
    if p.exists():
        try:
            df = pd.read_csv(p).sort_values('datetime')
            latest_dt = df['datetime'].max()
            df = df[df['datetime'] == latest_dt]
            lines.append(f"📊 Deribit OI ({latest_dt} UTC)")
            for _, r in df.iterrows():
                sym = str(r['symbol'])
                oi_usd = float(r['oi_usd']) / 1e9
                lines.append(f"  {sym}: ${oi_usd:.2f}B")
            lines.append("")
        except Exception as e:
            lines.append(f"📊 Deribit OI 解析失败: {e}")
            lines.append("")

    # === OKX Funding ===
    p = Path('data/okx_funding.csv')
    if p.exists():
        try:
            df = pd.read_csv(p).sort_values('datetime')
            latest_dt = df['datetime'].max()
            df = df[df['datetime'] == latest_dt]
            lines.append(f"💰 OKX Funding ({latest_dt} UTC)")
            for _, r in df.iterrows():
                sym = str(r['symbol']).replace('USDT', '')
                rate = float(r['funding_rate']) * 100
                lines.append(f"  {sym}: {rate:+.4f}%")
            lines.append("")
        except Exception as e:
            lines.append(f"💰 OKX Funding 解析失败: {e}")
            lines.append("")

    # === OKX OI ===
    p = Path('data/okx_oi.csv')
    if p.exists():
        try:
            df = pd.read_csv(p).sort_values('datetime')
            latest_dt = df['datetime'].max()
            df = df[df['datetime'] == latest_dt]
            lines.append(f"📊 OKX OI ({latest_dt} UTC)")
            for _, r in df.iterrows():
                sym = str(r['symbol']).replace('USDT', '')
                oi_usd = float(r['oi_usd']) / 1e9
                lines.append(f"  {sym}: ${oi_usd:.2f}B")
            lines.append("")
        except Exception as e:
            lines.append(f"📊 OKX OI 解析失败: {e}")
            lines.append("")

    # === OKX 爆仓（最近 24h） ===
    p = Path('data/okx_liquidation.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            df['dt'] = pd.to_datetime(df['datetime'], utc=True)
            latest = df['dt'].max()
            recent = df[df['dt'] >= latest - pd.Timedelta(hours=24)]
            if not recent.empty:
                lines.append(f"💥 OKX 爆仓（最近 24h）")
                for uly in recent['uly'].unique():
                    sub = recent[recent['uly'] == uly]
                    longs = sub[sub['pos_side'] == 'long']['size'].sum()
                    shorts = sub[sub['pos_side'] == 'short']['size'].sum()
                    sym = uly.replace('-USDT', '')
                    lines.append(f"  {sym}: 多 {longs:.0f} / 空 {shorts:.0f} 张")
                lines.append("")
        except Exception as e:
            lines.append(f"💥 爆仓解析失败: {e}")
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
            df = pd.read_csv(p).sort_values('date')
            if 'n-transactions' in df.columns:
                df = df[df['n-transactions'].notna()]
            if not df.empty:
                latest = df.iloc[-1]
                date = latest['date']
                lines.append(f"⛓️ BTC On-chain ({date})")
                if pd.notna(latest.get('market-price')):
                    lines.append(f"  价格: ${float(latest['market-price']):,.0f}")
                if pd.notna(latest.get('n-transactions')):
                    lines.append(f"  日交易: {int(latest['n-transactions']):,}")
                if pd.notna(latest.get('n-unique-addresses')):
                    lines.append(f"  活跃地址: {int(latest['n-unique-addresses']):,}")
                if pd.notna(latest.get('hash-rate')):
                    hr = float(latest['hash-rate']) / 1e6
                    lines.append(f"  算力: {hr:.1f} EH/s")
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

    # === CME FedWatch ===
    p = Path('data/cme_fedwatch.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            if not df.empty:
                latest = df.iloc[-1]
                date = latest['date']
                effr = latest.get('effr')
                target = latest.get('current_target')
                lines.append(f"🏛️ CME FedWatch ({date})")
                if pd.notna(target):
                    lines.append(f"  目标区间: {target}")
                if pd.notna(effr):
                    lines.append(f"  EFFR: {float(effr):.2f}%")
                lines.append("")
        except Exception as e:
            lines.append(f"🏛️ CME 解析失败: {e}")
            lines.append("")

    # === Farside BTC ETF Flow ===
    p = Path('data/farside_btc_etf.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            mask = df.iloc[:, 0].astype(str).str.match(r'\d{2} \w{3} \d{4}')
            df = df[mask]
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