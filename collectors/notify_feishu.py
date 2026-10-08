"""
飞书机器人通知（v9，2026-10-08）
- 删掉 Coinalyze（单位混乱 + 需 key）
- 保留 CoinGecko 全市场 / 稳定币细分 / 交易所量 / 多交易所衍生品
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

    # === CFTC COT ===
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

    # === FX COT ===
    p = Path('data/cftc_fx.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            if not df.empty:
                latest = df['date'].max()
                df = df[df['date'] == latest]
                df = df[df['series_id'] != 'COT_EUR'].sort_values('series_id')
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

    # === BIS 全球央行利率 ===
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

    # === Eurostat HICP ===
    p = Path('data/eurostat_hicp.csv')
    if p.exists():
        try:
            df = pd.read_csv(p).sort_values('date')
            if not df.empty:
                latest = df.iloc[-1]
                lines.append(f"🇪🇺 欧元区 HICP ({latest['date']}, Eurostat)")
                lines.append(f"  CPI 年率: {float(latest['value']):.1f}%")
                lines.append("")
        except Exception as e:
            lines.append(f"🇪🇺 Eurostat 解析失败: {e}")
            lines.append("")

    # === ECB ===
    p = Path('data/ecb_rates.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            latest = df['date'].max()
            df = df[df['date'] == latest]
            lines.append(f"🇪🇺 ECB 利率 ({latest})")
            for sid in ['ECB_MRR', 'ECB_DFR']:
                sub = df[df['series'] == sid]
                if not sub.empty:
                    v = float(sub.iloc[0]['value'])
                    label = sid.replace('ECB_', '')
                    lines.append(f"  {label}: {v:.2f}%")
            lines.append("")
        except Exception as e:
            lines.append(f"🇪🇺 ECB 解析失败: {e}")
            lines.append("")

    # === BOJ ===
    p = Path('data/boj_rates.csv')
    if p.exists():
        try:
            df = pd.read_csv(p).sort_values('date')
            if not df.empty:
                latest = df.iloc[-1]
                lines.append(f"🇯🇵 BOJ 隔夜拆借 ({latest['date']})")
                lines.append(f"  {float(latest['value']):.3f}%")
                lines.append("")
        except Exception as e:
            lines.append(f"🇯🇵 BOJ 解析失败: {e}")
            lines.append("")

    # === CoinGecko 全市场 ===
    p = Path('data/coingecko_global.csv')
    if p.exists():
        try:
            df = pd.read_csv(p).sort_values('date')
            latest = df['date'].max()
            df = df[df['date'] == latest]
            lines.append(f"🌐 全市场 ({latest}, CoinGecko)")
            for _, r in df.iterrows():
                sid = str(r['series'])
                v = float(r['value'])
                if 'USD' in sid:
                    lines.append(f"  {sid.replace('_USD', '')}: ${v/1e12:.2f}T")
                elif 'DOMINANCE' in sid:
                    lines.append(f"  {sid.replace('_DOMINANCE', '')} 市占率: {v:.2f}%")
                else:
                    lines.append(f"  {sid}: {v:.0f}")
            lines.append("")
        except Exception as e:
            lines.append(f"🌐 全市场解析失败: {e}")
            lines.append("")

    # === CoinGecko 稳定币细分 ===
    p = Path('data/coingecko_stablecoins.csv')
    if p.exists():
        try:
            df = pd.read_csv(p).sort_values('date')
            latest = df['date'].max()
            df = df[df['date'] == latest].sort_values('market_cap_usd', ascending=False)
            lines.append(f"🪙 稳定币细分 ({latest}, CoinGecko)")
            for _, r in df.iterrows():
                sym = str(r['symbol'])
                mc = float(r['market_cap_usd']) / 1e9
                lines.append(f"  {sym}: ${mc:.2f}B")
            lines.append("")
        except Exception as e:
            lines.append(f"🪙 稳定币细分失败: {e}")
            lines.append("")

    # === CoinGecko 交易所成交量 ===
    p = Path('data/coingecko_exchange_vol.csv')
    if p.exists():
        try:
            df = pd.read_csv(p).sort_values('date')
            latest = df['date'].max()
            df = df[df['date'] == latest].sort_values('volume_24h_btc', ascending=False)
            lines.append(f"🏦 交易所 24h 量 ({latest}, BTC计价)")
            for _, r in df.head(5).iterrows():
                name = str(r['exchange_name'])
                v = float(r['volume_24h_btc'])
                lines.append(f"  {name}: {v:,.0f} BTC")
            lines.append("")
        except Exception as e:
            lines.append(f"🏦 交易所量失败: {e}")
            lines.append("")

    # === CoinGecko 多交易所衍生品 ===
    p = Path('data/coingecko_derivatives.csv')
    if p.exists():
        try:
            df = pd.read_csv(p).sort_values('date')
            latest = df['date'].max()
            df = df[df['date'] == latest]
            lines.append(f"📊 多交易所衍生品 ({latest}, CoinGecko)")
            for _, r in df.iterrows():
                mkt = str(r['market']).replace(' (Futures)', '')
                idx = str(r['index'])
                fr = r['funding_rate_annual_pct']
                oi = float(r['open_interest_usd']) / 1e9
                fr_str = f"{fr:+.1f}%" if pd.notna(fr) else "N/A"
                lines.append(f"  {mkt:10s} {idx}: FR {fr_str}, OI ${oi:.2f}B")
            lines.append("")
        except Exception as e:
            lines.append(f"📊 CG 衍生品失败: {e}")
            lines.append("")

    # === Yahoo 市场指标 ===
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
                elif sym == 'NDX':
                    lines.append(f"  {sym}: {v:,.1f}")
                else:
                    lines.append(f"  {sym}: {v:.2f}")
            lines.append("")
        except Exception as e:
            lines.append(f"📈 Yahoo 解析失败: {e}")
            lines.append("")

    # === 流动性 ===
    p_nyfed = Path('data/nyfed_rates.csv')
    p_tga = Path('data/treasury_tga.csv')
    if p_nyfed.exists() or p_tga.exists():
        try:
            lines.append("💵 流动性")
            if p_nyfed.exists():
                df = pd.read_csv(p_nyfed)

                def lbs(sid):
                    sub = df[df['series'] == sid].sort_values('date')
                    if sub.empty:
                        return None, None
                    return float(sub.iloc[-1]['value']), sub.iloc[-1]['date']

                s, d_s = lbs('SOFR')
                e, d_e = lbs('EFFR')
                r, d_r = lbs('RRP_BALANCE')
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
                    lines.append(f"  TGA: ${float(df_tga.iloc[-1]['value']):.1f}B ({df_tga.iloc[-1]['date']})")
            lines.append("")
        except Exception as ex:
            lines.append(f"💵 流动性失败: {ex}")
            lines.append("")

    # === FRED 宏观 ===
    p = Path('data/fred_macro.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            lines.append("💵 FRED 宏观")

            def la(sid):
                sub = df[df['series'] == sid].sort_values('date')
                if sub.empty:
                    return None, None
                return float(sub.iloc[-1]['value']), sub.iloc[-1]['date']

            v, d = la('WRESBAL')
            if v is not None:
                lines.append(f"  准备金: ${v/1e6:.2f}T ({d})")

            t2, _ = la('DGS2')
            t10, _ = la('DGS10')
            t30, _ = la('DGS30')
            if t2 is not None:
                lines.append(f"  2Y: {t2:.2f}%")
            if t10 is not None:
                lines.append(f"  10Y: {t10:.2f}%")
            if t30 is not None:
                lines.append(f"  30Y: {t30:.2f}%")
            if t2 is not None and t10 is not None:
                lines.append(f"  2s10s: {(t10-t2)*100:+.0f}bp")

            v, _ = la('T10Y3M')
            if v is not None:
                lines.append(f"  10Y-3M: {v*100:+.0f}bp")

            v, _ = la('DFII10')
            if v is not None:
                lines.append(f"  10Y TIPS: {v:.2f}%")
            v, _ = la('T5YIE')
            if v is not None:
                lines.append(f"  5Y Breakeven: {v:.2f}%")
            v, _ = la('T10YIE')
            if v is not None:
                lines.append(f"  10Y Breakeven: {v:.2f}%")

            v, _ = la('BAMLH0A0HYM2')
            if v is not None:
                lines.append(f"  HY OAS: {v*100:.0f}bp")
            v, _ = la('BAMLH0A1HYBB')
            if v is not None:
                lines.append(f"    BB: {v*100:.0f}bp")
            v, _ = la('BAMLH0A2HYB')
            if v is not None:
                lines.append(f"    B: {v*100:.0f}bp")
            v, _ = la('BAMLH0A3HYC')
            if v is not None:
                lines.append(f"    CCC: {v*100:.0f}bp")

            v, _ = la('BAMLC0A0CM')
            if v is not None:
                lines.append(f"  IG OAS: {v*100:.0f}bp")
            v, _ = la('BAMLC0A1CAAA')
            if v is not None:
                lines.append(f"    AAA: {v*100:.0f}bp")
            v, _ = la('BAMLC0A4CBBB')
            if v is not None:
                lines.append(f"    BBB: {v*100:.0f}bp")

            v, _ = la('THREEFYTP10')
            if v is not None:
                lines.append(f"  10Y 期限溢价: {v:.2f}%")

            cp, _ = la('CPF3M')
            tb, _ = la('TB3MS')
            if cp is not None and tb is not None:
                lines.append(f"  CP-Tbill: {(cp-tb)*100:+.0f}bp")
            cp60, _ = la('RIFSPPNA2P2D60NB')
            if cp60 is not None and tb is not None:
                lines.append(f"  CP60-Tbill: {(cp60-tb)*100:+.0f}bp")

            v, d = la('DRTSCILM')
            if v is not None:
                lines.append(f"  SLOOS: {v:.1f}% ({d})")
            v, d = la('DRCRELEXFACBS')
            if v is not None:
                lines.append(f"  商业地产拖欠率: {v:.2f}% ({d})")

            lines.append("")
        except Exception as e:
            lines.append(f"💵 FRED 失败: {e}")
            lines.append("")

    # === 稳定币总市值 ===
    p = Path('data/defillama_stablecoin.csv')
    if p.exists():
        try:
            df = pd.read_csv(p).sort_values('date').reset_index(drop=True)
            if len(df) >= 1:
                cur = float(df.iloc[-1]['total_usd']) / 1e9
                lines.append(f"🪙 稳定币总市值 ({df.iloc[-1]['date']})")
                lines.append(f"  ${cur:.1f}B")
                if len(df) >= 2:
                    lines.append(f"  1d: {(cur - float(df.iloc[-2]['total_usd'])/1e9):+.2f}B")
                if len(df) >= 8:
                    lines.append(f"  7d: {(cur - float(df.iloc[-8]['total_usd'])/1e9):+.2f}B")
                if len(df) >= 31:
                    lines.append(f"  30d: {(cur - float(df.iloc[-31]['total_usd'])/1e9):+.2f}B")
                lines.append("")
        except Exception as e:
            lines.append(f"🪙 稳定币失败: {e}")
            lines.append("")

    # === Deribit / OKX ===
    for fname, title in [
        ('deribit_funding.csv', '💰 Deribit Funding'),
        ('deribit_oi.csv', '📊 Deribit OI'),
        ('okx_funding.csv', '💰 OKX Funding'),
        ('okx_oi.csv', '📊 OKX OI'),
    ]:
        p = Path(f'data/{fname}')
        if not p.exists():
            continue
        try:
            df = pd.read_csv(p).sort_values('datetime')
            latest_dt = df['datetime'].max()
            df = df[df['datetime'] == latest_dt]
            lines.append(f"{title} ({latest_dt} UTC)")
            for _, r in df.iterrows():
                sym = str(r['symbol']).replace('USDT', '').replace('-SWAP', '')
                if 'funding' in fname:
                    rate_8h = float(r['funding_rate']) * 100
                    lines.append(f"  {sym}: {rate_8h * 3 * 365:+.2f}% 年化 ({rate_8h:+.4f}%/8h)")
                else:
                    oi_col = 'oi_usd' if 'oi_usd' in r else 'oi'
                    lines.append(f"  {sym}: ${float(r[oi_col])/1e9:.2f}B")
            lines.append("")
        except Exception as e:
            lines.append(f"{title} 失败: {e}")
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
                lines.append("💥 OKX 爆仓（最近 24h）")
                for uly in recent['uly'].unique():
                    sub = recent[recent['uly'] == uly].copy()
                    cs = 0.01 if 'BTC' in uly else 0.1
                    sub['usd'] = sub['size'] * cs * sub['price']
                    longs = sub[sub['pos_side'] == 'long']['size'].sum()
                    shorts = sub[sub['pos_side'] == 'short']['size'].sum()
                    lu = sub[sub['pos_side'] == 'long']['usd'].sum() / 1e6
                    su = sub[sub['pos_side'] == 'short']['usd'].sum() / 1e6
                    sym = uly.replace('-USDT', '')
                    lines.append(f"  {sym}: 多 {longs:.0f}张 (${lu:.1f}M) / 空 {shorts:.0f}张 (${su:.1f}M)")
                lines.append("")
        except Exception as e:
            lines.append(f"💥 爆仓失败: {e}")
            lines.append("")

    # === DVOL ===
    p = Path('data/deribit_dvol.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            latest_date = df['date'].max()
            df = df[df['date'] == latest_date]
            lines.append(f"📉 Deribit DVOL ({latest_date}, 30d IV)")
            for _, r in df.iterrows():
                lines.append(f"  {r['currency']}: {float(r['close']):.2f}")
            lines.append("")
        except Exception as e:
            lines.append(f"📉 DVOL 失败: {e}")
            lines.append("")

    # === On-chain ===
    p = Path('data/blockchain_com.csv')
    if p.exists():
        try:
            df = pd.read_csv(p).sort_values('date')
            if 'n-transactions' in df.columns:
                df = df[df['n-transactions'].notna()]
            if not df.empty:
                latest = df.iloc[-1]
                lines.append(f"⛓️ BTC On-chain ({latest['date']})")
                if pd.notna(latest.get('market-price')):
                    lines.append(f"  价格: ${float(latest['market-price']):,.0f}")
                if pd.notna(latest.get('n-transactions')):
                    lines.append(f"  日交易: {int(latest['n-transactions']):,}")
                if pd.notna(latest.get('n-unique-addresses')):
                    lines.append(f"  活跃地址: {int(latest['n-unique-addresses']):,}")
                if pd.notna(latest.get('hash-rate')):
                    lines.append(f"  算力: {float(latest['hash-rate'])/1e6:.1f} EH/s")
                lines.append("")
        except Exception as e:
            lines.append(f"⛓️ On-chain 失败: {e}")
            lines.append("")

    # === Fear & Greed ===
    p = Path('data/fear_greed.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            latest = df.sort_values('date').iloc[-1]
            lines.append(f"😱 Fear & Greed ({latest['date']})")
            lines.append(f"  {int(latest['value'])} - {latest['classification']}")
            lines.append("")
        except Exception as e:
            lines.append(f"😱 F&G 失败: {e}")
            lines.append("")

    # === CME FedWatch ===
    p = Path('data/cme_fedwatch.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            if not df.empty:
                latest = df.iloc[-1]
                lines.append(f"🏛️ CME FedWatch ({latest['date']})")
                if pd.notna(latest.get('current_target')):
                    lines.append(f"  目标区间: {latest['current_target']}")
                if pd.notna(latest.get('effr')):
                    lines.append(f"  EFFR: {float(latest['effr']):.2f}%")
                lines.append("")
        except Exception as e:
            lines.append(f"🏛️ CME 失败: {e}")
            lines.append("")

    # === Farside ETF ===
    for fname, title in [('farside_btc_etf.csv', '📈 BTC ETF'), ('farside_eth_etf.csv', '📈 ETH ETF')]:
        p = Path(f'data/{fname}')
        if not p.exists():
            continue
        try:
            df = pd.read_csv(p)
            mask = df.iloc[:, 0].astype(str).str.match(r'\d{2} \w{3} \d{4}')
            df = df[mask]
            total_col = pd.to_numeric(df.iloc[:, -2], errors='coerce')
            df2 = df[total_col.notna() & (total_col != 0)]
            if not df2.empty:
                last = df2.iloc[-1]
                lines.append(f"{title} 净流")
                lines.append(f"  {last.iloc[0]}: US${last.iloc[-2]}m")
                lines.append("")
        except Exception as e:
            lines.append(f"{title} 失败: {e}")
            lines.append("")

    # === 时间戳 ===
    now_utc = datetime.now(timezone.utc)
    now_kr = now_utc.astimezone(timezone(timedelta(hours=9)))
    lines.append(f"⏱️ 数据生成: {now_utc.strftime('%Y-%m-%d %H:%M')} UTC / {now_kr.strftime('%H:%M')} 韩国")
    lines.append("")
    lines.append("🔗 github.com/d87skg/gmre-collectors")
    return "\n".join(lines)


def send(content):
    ts = str(int(time.time()))
    payload = {
        "timestamp": ts,
        "sign": gen_sign(ts, SECRET),
        "msg_type": "text",
        "content": {"text": content}
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