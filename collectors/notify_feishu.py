"""
飞书机器人通知（带签名校验）
环境变量: FEISHU_WEBHOOK, FEISHU_SECRET

显示层约定（v4，2026-10-05）：
- 流动性段：SOFR / EFFR / 利差 / ON RRP / TGA
- CFTC COT：自动包含 COT_BTC_CME
- 新增：全球央行利率（BIS）+ ECB + Yahoo 市场指标
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
from datetime import datetime, timezone, timedelta

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

    # === CFTC 金融期货 COT（含 CME BTC） ===
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
                    oi = int(r['open_interest']) if pd.notna(r.get('open_interest')) else 0
                    sid = str(r['series_id']).replace('COT_', '')
                    if oi > 0:
                        pct = net / oi * 100
                        lines.append(f"  {sid}: {net:+,} ({pct:+.1f}% OI)")
                    else:
                        lines.append(f"  {sid}: {net:+,}")
                lines.append("")
        except Exception as e:
            lines.append(f"🏦 CFTC 解析失败: {e}")
            lines.append("")

    # === CFTC FX COT（排除 EUR） ===
    p = Path('data/cftc_fx.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            if not df.empty:
                latest = df['date'].max()
                df = df[df['date'] == latest]
                df = df[df['series_id'] != 'COT_EUR']
                df = df.sort_values('series_id')
                if not df.empty:
                    lines.append(f"💱 FX COT ({latest}) [EUR 见上]")
                    for _, r in df.iterrows():
                        net = int(r['net_noncommercial'])
                        sid = str(r['series_id']).replace('COT_', '')
                        lines.append(f"  {sid}: {net:+,}")
                    lines.append("")
        except Exception as e:
            lines.append(f"💱 FX COT 解析失败: {e}")
            lines.append("")

    # === 全球央行政策利率（BIS） ===
    p = Path('data/bis_cbpol.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            if not df.empty:
                latest = df['date'].max()
                df = df[df['date'] == latest].sort_values('series')
                lines.append(f"🏛️ 全球央行利率 ({latest}, BIS, 月度)")
                for _, r in df.iterrows():
                    name = str(r['series']).replace('CB_', '')
                    v = float(r['value'])
                    lines.append(f"  {name}: {v:.2f}%")
                lines.append("")
        except Exception as e:
            lines.append(f"🏛️ BIS 解析失败: {e}")
            lines.append("")

    # === ECB 利率 ===
    p = Path('data/ecb_rates.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            latest = df['date'].max()
            df = df[df['date'] == latest]
            lines.append(f"🇪🇺 ECB 利率 ({latest})")
            for sid in ['ECB_MRR', 'ECB_DFR']:
                sub = df[df['series'] == sid]
                if sub.empty:
                    continue
                v = float(sub.iloc[0]['value'])
                label = sid.replace('ECB_', '')
                lines.append(f"  {label}: {v:.2f}%")
            lines.append("")
        except Exception as e:
            lines.append(f"🇪🇺 ECB 解析失败: {e}")
            lines.append("")

    # === Yahoo 市场指标（VIX / DXY / GOLD / OIL） ===
    p = Path('data/yahoo_market.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            latest_date = df['date'].max()
            df = df[df['date'] == latest_date].sort_values('symbol')
            lines.append(f"📈 市场指标 ({latest_date})")
            for _, r in df.iterrows():
                sym = str(r['symbol'])
                v = float(r['value'])
                if sym in ('GOLD', 'OIL'):
                    lines.append(f"  {sym}: ${v:,.2f}")
                else:
                    lines.append(f"  {sym}: {v:.2f}")
            lines.append("")
        except Exception as e:
            lines.append(f"📈 Yahoo 解析失败: {e}")
            lines.append("")

    # === 流动性（NY Fed + Treasury TGA） ===
    p_nyfed = Path('data/nyfed_rates.csv')
    p_tga = Path('data/treasury_tga.csv')
    if p_nyfed.exists() or p_tga.exists():
        try:
            lines.append("💵 流动性")

            if p_nyfed.exists():
                df = pd.read_csv(p_nyfed)

                def latest_by_series(sid):
                    sub = df[df['series'] == sid].sort_values('date')
                    if sub.empty:
                        return None, None
                    return float(sub.iloc[-1]['value']), sub.iloc[-1]['date']

                s, d_s = latest_by_series('SOFR')
                e, d_e = latest_by_series('EFFR')
                r, d_r = latest_by_series('RRP_BALANCE')

                if s is not None:
                    lines.append(f"  SOFR: {s:.2f}% ({d_s})")
                if e is not None:
                    lines.append(f"  EFFR: {e:.2f}% ({d_e})")
                if s is not None and e is not None:
                    lines.append(f"  利差: {(s-e)*100:+.1f}bp")
                if r is not None:
                    lines.append(f"  ON RRP: ${r:.2f}B ({d_r})")

            if p_tga.exists():
                df_tga = pd.read_csv(p_tga).sort_values('date')
                if not df_tga.empty:
                    tga_val = float(df_tga.iloc[-1]['value'])
                    tga_date = df_tga.iloc[-1]['date']
                    lines.append(f"  TGA: ${tga_val:.1f}B ({tga_date})")

            lines.append("")
        except Exception as ex:
            lines.append(f"💵 流动性 解析失败: {ex}")
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
                lines.append(f"  准备金: ${v/1e6:.2f}T ({d}, H.4.1)")

            v, d = latest('BAMLH0A0HYM2')
            if v is not None:
                lines.append(f"  HY OAS: {v*100:.0f}bp ({d}, ICE BofA)")

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
                lines.append(f"  10Y 期限溢价: {v:.2f}% (ACM, 可修订)")

            cp, _ = latest('CPF3M')
            tb, _ = latest('TB3MS')
            if cp is not None and tb is not None:
                lines.append(f"  CP-Tbill: {(cp-tb)*100:+.0f}bp (3M)")

            cp60, _ = latest('RIFSPPNA2P2D60NB')
            if cp60 is not None and tb is not None:
                lines.append(f"  CP60-Tbill: {(cp60-tb)*100:+.0f}bp (60D CP)")

            v, d = latest('DRCRELEXFACBS')
            if v is not None:
                lines.append(f"  商业地产拖欠率: {v:.2f}% ({d}, 季度, 滞后约 6 月)")

            lines.append("")
        except Exception as e:
            lines.append(f"💵 FRED 解析失败: {e}")
            lines.append("")

    # === DefiLlama 稳定币 ===
    p = Path('data/defillama_stablecoin.csv')
    if p.exists():
        try:
            df = pd.read_csv(p).sort_values('date').reset_index(drop=True)
            if len(df) >= 1:
                cur = float(df.iloc[-1]['total_usd']) / 1e9
                cur_date = df.iloc[-1]['date']
                lines.append(f"🪙 稳定币总市值 ({cur_date})")
                lines.append(f"  ${cur:.1f}B")

                if len(df) >= 2:
                    prev1 = float(df.iloc[-2]['total_usd']) / 1e9
                    d1 = (cur - prev1)
                    lines.append(f"  1d: {d1:+.2f}B")

                if len(df) >= 8:
                    prev7 = float(df.iloc[-8]['total_usd']) / 1e9
                    d7 = (cur - prev7)
                    lines.append(f"  7d: {d7:+.2f}B")

                if len(df) >= 31:
                    prev30 = float(df.iloc[-31]['total_usd']) / 1e9
                    d30 = (cur - prev30)
                    lines.append(f"  30d: {d30:+.2f}B")

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
                rate_8h = float(r['funding_rate']) * 100
                rate_annual = rate_8h * 3 * 365
                lines.append(f"  {sym}: {rate_annual:+.2f}% 年化 ({rate_8h:+.4f}%/8h)")
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
            lines.append(f"📊 Deribit OI ({latest_dt} UTC, perp only)")
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
                rate_8h = float(r['funding_rate']) * 100
                rate_annual = rate_8h * 3 * 365
                lines.append(f"  {sym}: {rate_annual:+.2f}% 年化 ({rate_8h:+.4f}%/8h)")
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
            lines.append(f"📊 OKX OI ({latest_dt} UTC, perp only)")
            for _, r in df.iterrows():
                sym = str(r['symbol']).replace('USDT', '')
                oi_usd = float(r['oi_usd']) / 1e9
                lines.append(f"  {sym}: ${oi_usd:.2f}B")
            lines.append("")
        except Exception as e:
            lines.append(f"📊 OKX OI 解析失败: {e}")
            lines.append("")

    # === OKX 爆仓 ===
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
                    sub = recent[recent['uly'] == uly].copy()
                    contract_size = 0.01 if 'BTC' in uly else 0.1
                    sub['usd'] = sub['size'] * contract_size * sub['price']
                    longs_size = sub[sub['pos_side'] == 'long']['size'].sum()
                    shorts_size = sub[sub['pos_side'] == 'short']['size'].sum()
                    longs_usd = sub[sub['pos_side'] == 'long']['usd'].sum() / 1e6
                    shorts_usd = sub[sub['pos_side'] == 'short']['usd'].sum() / 1e6
                    sym = uly.replace('-USDT', '')
                    lines.append(
                        f"  {sym}: 多 {longs_size:.0f}张 (${longs_usd:.1f}M) / "
                        f"空 {shorts_size:.0f}张 (${shorts_usd:.1f}M)"
                    )
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
            lines.append(f"📉 Deribit DVOL ({latest_date}, 30d IV)")
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
                lines.append(f"⛓️ BTC On-chain ({date}, Blockchain.com)")
                if pd.notna(latest.get('market-price')):
                    lines.append(f"  价格: ${float(latest['market-price']):,.0f}")
                if pd.notna(latest.get('n-transactions')):
                    lines.append(f"  日交易: {int(latest['n-transactions']):,}")
                if pd.notna(latest.get('n-unique-addresses')):
                    lines.append(f"  活跃地址: {int(latest['n-unique-addresses']):,}")
                if pd.notna(latest.get('hash-rate')):
                    hr = float(latest['hash-rate']) / 1e6
                    lines.append(f"  算力: {hr:.1f} EH/s (7d MA)")
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
            lines.append(f"😱 Fear & Greed ({date}, alternative.me)")
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
                    lines.append(f"  当前目标区间: {target}")
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
                lines.append(f"📈 BTC 现货 ETF 净流")
                lines.append(f"  {date}: US${total}m (Farside)")
                lines.append("")
        except Exception as e:
            lines.append(f"📈 Farside 解析失败: {e}")
            lines.append("")

        now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(timezone(timedelta(hours=8)))
    lines.append(f"⏱️ 数据生成: {now_utc.strftime('%Y-%m-%d %H:%M')} UTC / {now_local.strftime('%H:%M')} 北京")
    lines.append("")
        now_utc = datetime.now(timezone.utc)
    now_kr = now_utc.astimezone(timezone(timedelta(hours=9)))
    lines.append(f"⏱️ 数据生成: {now_utc.strftime('%Y-%m-%d %H:%M')} UTC / {now_kr.strftime('%H:%M')} 韩国")
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