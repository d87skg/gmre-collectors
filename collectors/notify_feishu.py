try:
    from dotenv import load_dotenv
    load_dotenv(r'D:\HGZC\.env')
except ImportError:
    pass
# 飞书机器人通知（v22 全资产宏观雷达版）
# - 核心升级：机构级全资产宏观引擎判定
# - 包含：宏观体制、流动性状态、跨资产基调、尾部风险、战术建议
# - 保留：期权信号、HL深度、Coinbase溢价、HYG/LQD、链上估值等全量数据
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


def calc_cot_zscore(df):
    z_scores = {}
    try:
        df = df.sort_values('date')
        for sid in df['series_id'].unique():
            sub = df[df['series_id'] == sid]['net_noncommercial'].dropna()
            if len(sub) < 12:
                continue
            window = sub.tail(52)
            mean = window.mean()
            std = window.std()
            if std and std > 0:
                z_scores[sid] = (window.iloc[-1] - mean) / std
    except Exception:
        pass
    return z_scores


def build_message():
    lines = ["📊 GMRE 数据更新", ""]

    # === CFTC COT ===
    p = Path('data/cftc_cot.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            if not df.empty:
                zs = calc_cot_zscore(df)
                latest = df['date'].max()
                df_latest = df[df['date'] == latest].sort_values('series_id')
                lines.append(f"🏦 CFTC COT ({latest})")
                for _, r in df_latest.iterrows():
                    net = int(r['net_noncommercial'])
                    oi = int(r['open_interest']) if pd.notna(r.get('open_interest')) else 0
                    sid = str(r['series_id'])
                    sid_short = sid.replace('COT_', '')
                    z = zs.get(sid)
                    z_str = f" | z={z:+.2f}" if z is not None else ""
                    if oi > 0:
                        pct = net / oi * 100
                        lines.append(f"  {sid_short}: {net:+,} ({pct:+.1f}% OI){z_str}")
                    else:
                        lines.append(f"  {sid_short}: {net:+,}{z_str}")
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
                zs = calc_cot_zscore(df)
                latest = df['date'].max()
                df = df[df['date'] == latest]
                df = df[df['series_id'] != 'COT_EUR'].sort_values('series_id')
                if not df.empty:
                    lines.append(f"💱 FX COT ({latest}) [EUR 见上]")
                    for _, r in df.iterrows():
                        net = int(r['net_noncommercial'])
                        sid = str(r['series_id'])
                        sid_short = sid.replace('COT_', '')
                        z = zs.get(sid)
                        z_str = f" | z={z:+.2f}" if z is not None else ""
                        lines.append(f"  {sid_short}: {net:+,}{z_str}")
                    lines.append("")
        except Exception as e:
            lines.append(f"💱 FX COT 解析失败: {e}")
            lines.append("")

    # === BIS ===
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

    # === Eurostat ===
    p = Path('data/eurostat_hicp.csv')
    if p.exists():
        try:
            df = pd.read_csv(p).sort_values('date')
            if not df.empty:
                latest = df.iloc[-1]
                lines.append(f"🇪🇺 欧元区 HICP ({latest['date']}, Eurostat, 历史参考)")
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
                if sid == 'TOTAL_MCAP_USD_B':
                    lines.append(f"  TOTAL_MCAP: ${v:,.0f}B")
                elif sid == 'TOTAL_MCAP_USD':
                    lines.append(f"  TOTAL_MCAP: ${v/1e9:,.0f}B")
                elif sid == 'BTC_DOMINANCE':
                    lines.append(f"  BTC 市占率: {v:.2f}%")
                elif sid == 'ETH_DOMINANCE':
                    lines.append(f"  ETH 市占率: {v:.2f}%")
                elif sid == 'ACTIVE_CRYPTOS':
                    lines.append(f"  ACTIVE_CRYPTOS: {v:.0f}")
            lines.append("")
        except Exception as e:
            lines.append(f"🌐 全市场失败: {e}")
            lines.append("")

    # === CoinGecko 稳定币细分（分层展示） ===
    p = Path('data/coingecko_stablecoins.csv')
    if p.exists():
        try:
            df = pd.read_csv(p).sort_values('date')
            latest = df['date'].max()
            df = df[df['date'] == latest].sort_values('market_cap_usd', ascending=False)
            lines.append(f"🪙 稳定币细分 ({latest}, CoinGecko)")

            df['symbol_upper'] = df['symbol'].astype(str).str.upper()

            for _, r in df.iterrows():
                sym = str(r['symbol_upper'])
                mc = float(r['market_cap_usd']) / 1e9
                price = r.get('current_price')

                if sym in ('USDD', 'GHO'):
                    continue

                if pd.notna(price):
                    price = float(price)
                    dev = (price - 1.0) * 100

                    if sym == 'USDE':
                        if abs(dev) > 0.01:
                            lines.append(f"  USDE: ${mc:.2f}B 🚨 锚定 {dev:+.4f}%")
                        else:
                            lines.append(f"  USDE: ${mc:.2f}B 锚定 {dev:+.4f}%")
                    elif sym in ('USDT', 'USDC', 'DAI', 'FDUSD', 'USDS'):
                        if abs(dev) > 0.1:
                            lines.append(f"  {sym}: ${mc:.2f}B ⚠️ 锚定 {dev:+.2f}%")
                        else:
                            lines.append(f"  {sym}: ${mc:.2f}B")
                    elif sym in ('USDG', 'PYUSD', 'RLUSD'):
                        lines.append(f"  {sym}: ${mc:.2f}B 偏离 {dev:+.2f}%")
                else:
                    lines.append(f"  {sym}: ${mc:.2f}B")
            lines.append("")
        except Exception as e:
            lines.append(f"🪙 稳定币细分失败: {e}")
            lines.append("")

    # === CoinGecko 交易所量 ===
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
            df = df.sort_values(['index', 'open_interest_usd'], ascending=[True, False])

            if 'funding_rate_annual_pct' in df.columns:
                df_clean = df[df['funding_rate_annual_pct'].abs() < 30].copy()
                df_abnormal = df[df['funding_rate_annual_pct'].abs() >= 30]
            else:
                df_clean = df
                df_abnormal = pd.DataFrame()

            lines.append(f"📊 多交易所衍生品 ({latest}, CoinGecko)")
            for _, r in df_clean.iterrows():
                mkt = str(r['market']).replace(' (Futures)', '')
                idx = str(r['index'])
                fr = r['funding_rate_annual_pct']
                oi = float(r['open_interest_usd']) / 1e9
                fr_str = f"{fr:+.1f}%" if pd.notna(fr) else "N/A"
                lines.append(f"  {mkt:10s} {idx}: FR {fr_str}, OI ${oi:.2f}B")

            if not df_abnormal.empty:
                lines.append(f"  ⚠️ 已过滤 {len(df_abnormal)} 条 FR 异常（|FR| > 30%）")

            hl_frs = {}
            hl_p = Path('data/hyperliquid.csv')
            if hl_p.exists():
                try:
                    hl_df = pd.read_csv(hl_p).sort_values('datetime')
                    hl_latest = hl_df['datetime'].max()
                    hl_df = hl_df[hl_df['datetime'] == hl_latest]
                    for _, r in hl_df.iterrows():
                        hl_frs[str(r['symbol'])] = float(r['funding_rate']) * 100 * 24 * 365
                except Exception:
                    pass

            for idx in ['BTC', 'ETH']:
                sub = df_clean[df_clean['index'] == idx]
                frs = list(sub['funding_rate_annual_pct'].dropna())
                if idx in hl_frs:
                    frs.append(hl_frs[idx])
                if len(frs) >= 2:
                    diff = max(frs) - min(frs)
                    if abs(diff) > 5:
                        hl_mark = ' (含 HL)' if idx in hl_frs else ''
                        lines.append(f"  ⚠️ {idx} FR 跨所差异 {diff:.1f}%{hl_mark}")
            lines.append("")
        except Exception as e:
            lines.append(f"📊 CG 衍生品失败: {e}")
            lines.append("")

    # === Yahoo & 资产相对定价矩阵 (V19 & V20) ===
    p = Path('data/yahoo_market.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            latest_date = df['date'].max()
            df_latest = df[df['date'] == latest_date].sort_values('symbol')
            lines.append(f"📈 市场指标 ({latest_date})")

            utc_now = datetime.now(timezone.utc)
            is_weekend = utc_now.weekday() >= 5
            weekend_note = " (周末沿用周五收盘)" if is_weekend else ""

            prices = {}
            for _, r in df_latest.iterrows():
                sym = str(r['symbol'])
                v = float(r['value'])
                prices[sym] = v
                if sym in ('GOLD', 'OIL', 'COPPER'):
                    lines.append(f"  {sym}: ${v:,.2f}")
                elif sym == 'NDX':
                    lines.append(f"  {sym}: {v:,.1f}")
                elif sym == 'USDJPY':
                    lines.append(f"  {sym}: {v:.2f}{weekend_note}")
                else:
                    lines.append(f"  {sym}: {v:.2f}")

            # --- V19 核心：宏观相对定价矩阵 ---
            lines.append("")
            lines.append(f"📐 宏观相对定价矩阵")
            
            g = prices.get('GOLD')
            c = prices.get('COPPER')
            d = prices.get('DXY')
            o = prices.get('OIL')
            n = prices.get('NDX')
            s = prices.get('SILVER', None) 

            if g and c: lines.append(f"  金铜比 (避险/工业): {g/c:.0f}")
            if g and d: lines.append(f"  金美元比 (硬资产/纸币): {g/d:.2f}")
            if c and o: lines.append(f"  铜油比 (景气/滞胀): {c/o:.3f}")
            if g and o: lines.append(f"  金油比 (购买力/能源): {g/o:.2f}")
            if g and n: lines.append(f"  金纳指比 (避险/科技): {g/n:.3f}")

            # --- V20 新增：信用风险代理 HYG/LQD ---
            hyg_row = prices.get('HYG')
            lqd_row = prices.get('LQD')
            if hyg_row and lqd_row:
                if lqd_row > 0:
                    lines.append(f"  HYG/LQD (信用/投资级): {hyg_row/lqd_row:.3f}")

            # --- V19 核心：20D 收益率动量 (收益曲线) ---
            lines.append("")
            lines.append(f"📈 市场动量 (20D收益率)")
            for sym in ['GOLD', 'COPPER', 'OIL', 'NDX', 'BTC']:
                if sym == 'BTC':
                    continue 
                sub = df[df['symbol'] == sym].sort_values('date')
                if len(sub) >= 21:
                    cur = float(sub.iloc[-1]['value'])
                    prev = float(sub.iloc[-21]['value'])
                    chg = (cur / prev - 1) * 100
                    lines.append(f"  {sym} 20D: {chg:+.1f}%")

            lines.append("")
        except Exception as e:
            lines.append(f"📈 Yahoo 失败: {e}")
            lines.append("")

    # === 美国机构与补充 FR (V20) ===
    p = Path('data/us_institution.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            lines.append(f"🇺🇸 机构与跨所验证")
            for _, r in df.iterrows():
                m = str(r['metric'])
                v = float(r['value'])
                if m == 'COINBASE_PREMIUM':
                    flag = " 🇺🇸 机构买盘" if v > 0.05 else (" 🇺🇸 机构抛压" if v < -0.05 else "")
                    lines.append(f"  Coinbase溢价: {v:+.3f}%{flag} ({r['extra']})")
                elif m == 'BITGET_FR':
                    lines.append(f"  Bitget BTC FR: {v:+.2f}% 年化")
            lines.append("")
        except Exception as e:
            lines.append(f"🇺🇸 机构指标失败: {e}")
            lines.append("")

    # === Binance 多空博弈 ===
    p = Path('data/binance_sentiment.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            lines.append(f"⚔️ Binance 资金多空博弈")
            for _, r in df.iterrows():
                m = str(r['metric'])
                v = float(r['value'])
                if m == 'RETAIL_LONG_SHORT_RATIO':
                    bias = "偏多" if v > 1 else "偏空"
                    lines.append(f"  散户人数比: {v:.2f} ({bias}) | {r['extra']}")
                elif m == 'TOP_LONG_SHORT_RATIO':
                    bias = "偏多" if v > 1 else "偏空"
                    lines.append(f"  大户持仓比: {v:.2f} ({bias}) | {r['extra']}")
            lines.append("")
        except Exception as e:
            lines.append(f"⚔️ 多空博弈数据失败: {e}")
            lines.append("")

    # === Hyperliquid 链上 & 加密比价 ===
    p = Path('data/hyperliquid.csv')
    if p.exists():
        try:
            df = pd.read_csv(p).sort_values('datetime')
            latest_dt = df['datetime'].max()
            df = df[df['datetime'] == latest_dt]
            df['_order'] = df['symbol'].map({'BTC': 0, 'ETH': 1, 'SOL': 2})
            df = df.sort_values('_order')
            lines.append(f"⛓️ Hyperliquid 链上 ({latest_dt} UTC)")
            
            hl_prices = {}
            for _, r in df.iterrows():
                sym = str(r['symbol'])
                mid = float(r['mid_px'])
                hl_prices[sym] = mid
                fr = float(r['funding_rate']) if pd.notna(r.get('funding_rate')) else None
                oi = float(r['open_interest']) if pd.notna(r.get('open_interest')) else None
                fr_str = f"{fr*100*24*365:+.2f}% 年化" if fr is not None else "N/A"
                oi_str = f"${oi * mid / 1e9:.2f}B" if oi else "N/A"
                lines.append(f"  {sym}: mid=${mid:,.2f} | FR {fr_str} | OI {oi_str}")

            # --- V19 核心：加密资产比价 ---
            btc = hl_prices.get('BTC')
            eth = hl_prices.get('ETH')
            if 'g' in locals() and btc:
                lines.append(f"  金BTC比 (传统避险/数字黄金): {g/btc:.2f}")
            if btc and eth:
                lines.append(f"  ETH/BTC比 (山寨/核心): {eth/btc:.4f}")
            lines.append("")
        except Exception as e:
            lines.append(f"⛓️ Hyperliquid 失败: {e}")
            lines.append("")

    # === Hyperliquid 订单簿深度 (V19.5 新增) ===
    p = Path('data/hyperliquid_depth.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            if not df.empty:
                lines.append(f"📊 HL 订单簿深度 (20档)")
                for _, r in df.iterrows():
                    coin = str(r['coin'])
                    imbalance = float(r['bid_ask_imbalance'])
                    d2_b = float(r['d2_bid'])
                    d2_a = float(r['d2_ask'])
                    flag = " ⚠️ 卖压厚" if imbalance < -0.2 else (" ⚠️ 买盘薄" if imbalance < -0.1 else "")
                    lines.append(f"  {coin}: 2%内买盘 {d2_b:.1f} / 卖盘 {d2_a:.1f} | 不平衡 {imbalance:+.3f}{flag}")
                lines.append("")
        except Exception as e:
            lines.append(f"📊 HL 深度失败: {e}")
            lines.append("")

    # === Hyperliquid 清算 ===
    p = Path('data/hyperliquid_liquidation.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            df['dt'] = pd.to_datetime(df['datetime'], utc=True)
            latest = df['dt'].max()
            recent = df[df['dt'] >= latest - pd.Timedelta(hours=24)]
            lines.append(f"⚡ Hyperliquid 清算 (最近 24h, 链上真实)")
            if recent.empty:
                lines.append(f"  过去 24h 无清算事件（市场平静）")
            else:
                total_usd = recent['notional_usd'].sum() / 1e6
                lines.append(f"  总额: ${total_usd:.2f}M ({len(recent)} 事件)")
                for coin in recent['coin'].unique():
                    sub = recent[recent['coin'] == coin]
                    long_liq = sub[sub['side'] == 'A']['notional_usd'].sum() / 1e6
                    short_liq = sub[sub['side'] == 'B']['notional_usd'].sum() / 1e6
                    lines.append(f"  {coin}: 多爆 ${long_liq:.2f}M / 空爆 ${short_liq:.2f}M")
            lines.append("")
        except Exception as e:
            lines.append(f"⚡ Hyperliquid 清算失败: {e}")
            lines.append("")
    else:
        lines.append("⚡ Hyperliquid 清算 (首次采集，无历史)")
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

    # === FRED ===
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

            def yoy(sid):
                sub = df[df['series'] == sid].sort_values('date')
                if len(sub) < 13:
                    return None, None
                cur = float(sub.iloc[-1]['value'])
                prev = float(sub.iloc[-13]['value'])
                if prev and prev > 0:
                    return (cur / prev - 1) * 100, sub.iloc[-1]['date']
                return None, None

            v, d = la('WRESBAL')
            if v is not None:
                lines.append(f"  准备金: ${v/1e6:.2f}T ({d})")

            v, d = yoy('CPIAUCSL')
            if v is not None:
                lines.append(f"  CPI 同比: {v:.2f}% ({d})")
            v, _ = yoy('CPILFESL')
            if v is not None:
                lines.append(f"  核心 CPI 同比: {v:.2f}%")
            v, _ = yoy('PCEPI')
            if v is not None:
                lines.append(f"  PCE 同比: {v:.2f}%")
            v, _ = yoy('PCEPILFE')
            if v is not None:
                lines.append(f"  核心 PCE 同比: {v:.2f}%")

            for sid, label in [
                ('CPIENGSL', '能源'), ('CPIFABSL', '食品'),
                ('CUSR0000SAH1', '住房'), ('CUSR0000SASLE', '核心服务')
            ]:
                v, _ = yoy(sid)
                if v is not None:
                    lines.append(f"    {label}: {v:.2f}%")

            v, d = la('MICH')
            if v is not None:
                lines.append(f"  通胀预期(MICH): {v:.1f}% ({d})")

            v, d = la('UNRATE')
            if v is not None:
                lines.append(f"  失业率: {v:.1f}% ({d})")
            sub = df[df['series'] == 'PAYEMS'].sort_values('date')
            if len(sub) >= 2:
                diff = float(sub.iloc[-1]['value']) - float(sub.iloc[-2]['value'])
                lines.append(f"  非农: {diff:+,.0f}K ({sub.iloc[-1]['date']})")
            v, d = la('ICSA')
            if v is not None:
                lines.append(f"  初请: {v:,.0f} ({d})")

            sub_man = df[df['series'] == 'MANEMP'].sort_values('date')
            if len(sub_man) >= 2:
                diff_man = float(sub_man.iloc[-1]['value']) - float(sub_man.iloc[-2]['value'])
                lines.append(f"  制造业就业: {diff_man:+,.0f}K ({sub_man.iloc[-1]['date']})")
            
            v, d = la('UMCSENT')
            if v is not None:
                lines.append(f"  消费者信心: {v:.1f} ({d})")

            v, _ = la('CES0500000003')
            if v is not None:
                lines.append(f"  平均时薪: ${v:.2f}")
            v, _ = la('ECIALLCIV')
            if v is not None:
                lines.append(f"  雇佣成本 ECI: {v:.2f}")

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

            sub_hy = df[df['series'] == 'BAMLH0A0HYM2'].sort_values('date')
            if len(sub_hy) >= 21:
                cur_hy = float(sub_hy.iloc[-1]['value'])
                prev_hy = float(sub_hy.iloc[-21]['value'])
                if prev_hy > 0:
                    chg = (cur_hy / prev_hy - 1) * 100
                    lines.append(f"  HY OAS 20D: {chg:+.1f}%")

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
            
            iorb_val, _ = la('IORB')
            sofr_nyfed = None
            if p_nyfed.exists():
                df_nf = pd.read_csv(p_nyfed)
                sub_nf = df_nf[df_nf['series'] == 'SOFR'].sort_values('date')
                if not sub_nf.empty:
                    sofr_nyfed = float(sub_nf.iloc[-1]['value'])
            
            if sofr_nyfed is not None and iorb_val is not None:
                lines.append(f"  SOFR-IORB: {(sofr_nyfed-iorb_val)*100:+.1f}bp")

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

    # === 稳定币 Mint/Burn 流量 (V19) ===
    p = Path('data/defillama_flows.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            snap = df[df['source'] == 'flow_snapshot'].copy()
            if not snap.empty:
                lines.append(f"💧 稳定币净流量 (24h, DefiLlama)")
                for _, r in snap.sort_values('net_flow_24h', ascending=False).iterrows():
                    sym = str(r['symbol'])
                    flow = float(r['net_flow_24h']) / 1e9
                    direction = "🟢 铸造" if flow > 0 else "🔴 赎回"
                    lines.append(f"  {sym}: {flow:+.3f}B {direction}")
                lines.append("")
        except Exception as e:
            lines.append(f"💧 稳定币流量失败: {e}")
            lines.append("")

    # === Deribit / OKX ===
    for fname, title in [
        ('deribit_funding.csv', '💰 Deribit 永续 Funding'),
        ('deribit_oi.csv', '📊 Deribit OI'),
        ('okx_funding.csv', '💰 OKX 永续 Funding'),
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
                lines.append("💥 爆仓（最近 24h, 仅 OKX ≈5-10% 市场）")
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

    # === Deribit 期权信号 (V18.5) ===
    p = Path('data/deribit_skew.csv')
    if p.exists():
        try:
            df = pd.read_csv(p)
            if not df.empty:
                lines.append(f"📐 期权信号 (Deribit, 25Δ)")
                for _, r in df.iterrows():
                    cur = str(r['currency'])
                    rr = float(r['rr25'])
                    pcr = float(r['pcr']) if pd.notna(r.get('pcr')) else None
                    term = float(r['term_ratio']) if pd.notna(r.get('term_ratio')) else None
                    rr_flag = " ⚠️ 负偏斜" if rr < -3 else ""
                    lines.append(f"  {cur} RR25: {rr:+.2f}%{rr_flag}")
                    if pcr is not None:
                        lines.append(f"    PCR: {pcr:.3f}")
                    if term is not None:
                        lines.append(f"    期限结构: {term:.3f} (>1=近月溢价)")
                lines.append("")
        except Exception as e:
            lines.append(f"📐 期权信号失败: {e}")
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

    # === BGeometrics 链上估值 (V18 新增) ===
    p = Path('data/bgeometrics_onchain.csv')
    if p.exists():
        try:
            df = pd.read_csv(p).sort_values('date')
            if not df.empty:
                latest_date = df['date'].max()
                df_latest = df[df['date'] == latest_date]
                lines.append(f"🔗 链上估值 ({latest_date}, BGeometrics)")
                for _, r in df_latest.iterrows():
                    metric = str(r['metric'])
                    val = float(r['value'])
                    if metric == 'MVRV':
                        lines.append(f"  MVRV: {val:.3f} (周期位置：>3.5 顶部 / <1.0 底部)")
                    elif metric == 'SOPR':
                        lines.append(f"  SOPR: {val:.4f} (>1 盈利卖出 / <1 亏损割肉)")
                    elif metric == 'REALIZED-PRICE':
                        lines.append(f"  实现价格: ${val:,.0f}")
                lines.append("")
        except Exception as e:
            lines.append(f"🔗 BGeometrics 失败: {e}")
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
    for fname, title in [('farside_btc_etf.csv', '📈 BTC ETF'),
                          ('farside_eth_etf.csv', '📈 ETH ETF')]:
        p = Path(f'data/{fname}')
        if not p.exists():
            continue
        try:
            df = pd.read_csv(p)
            mask = df.iloc[:, 0].astype(str).str.match(r'\d{2} \w{3} \d{4}')
            df = df[mask].copy()
            total_col = pd.to_numeric(df.iloc[:, -2], errors='coerce')
            valid = df[total_col.notna()].copy()
            if not valid.empty:
                valid['total'] = total_col[total_col.notna()].values
                last = valid.iloc[-1]
                lines.append(f"{title} 净流")
                lines.append(f"  {last.iloc[0]}: US${last['total']}m")
                if len(valid) >= 5:
                    sum5 = valid['total'].tail(5).sum()
                    lines.append(f"  5d 滚动: US${sum5:+.1f}m")
                lines.append("")
        except Exception as e:
            lines.append(f"{title} 失败: {e}")
            lines.append("")

    # ==========================================
    # 🏛️ 机构级全资产宏观引擎 (Macro Regime Engine)
    # ==========================================
    regime_growth = "中性"
    regime_inflation = "中性"
    liquidity_state = "中性"
    cross_asset_bias = "中性"
    tail_risk = "正常"

    # 1. 判定增长与通胀 (Growth & Inflation)
    try:
        p_fred = Path('data/fred_macro.csv')
        if p_fred.exists():
            df_f = pd.read_csv(p_fred)
            unrate = df_f[df_f['series'] == 'UNRATE']['value'].iloc[-1]
            cpi = df_f[df_f['series'] == 'CPIENGSL']['value'].iloc[-1]
            umcsent = df_f[df_f['series'] == 'UMCSENT']['value'].iloc[-1]
            
            if umcsent < 60:
                regime_growth = "衰退风险 (增长极弱)"
            elif umcsent > 80:
                regime_growth = "扩张 (增长强劲)"

            if cpi > 10:
                regime_inflation = "高通胀 (能源驱动)"
            elif cpi < 2:
                regime_inflation = "通缩风险"
    except Exception:
        pass

    # 2. 判定流动性 (Liquidity)
    try:
        p_tga = Path('data/treasury_tga.csv')
        p_nyfed = Path('data/nyfed_rates.csv')
        if p_tga.exists() and p_nyfed.exists():
            df_tga = pd.read_csv(p_tga)
            df_nf = pd.read_csv(p_nyfed)
            tga = df_tga['value'].iloc[-1]
            rrp = df_nf[df_nf['series'] == 'RRP_BALANCE']['value'].iloc[-1]
            if tga > 900 and rrp < 10:
                liquidity_state = "极度紧缩 (TGA抽水, RRP枯竭)"
            elif tga < 700:
                liquidity_state = "边际宽松 (TGA释放)"
    except Exception:
        pass

    # 3. 判定跨资产偏好 (Cross-Asset)
    try:
        p_yahoo = Path('data/yahoo_market.csv')
        if p_yahoo.exists():
            df_y = pd.read_csv(p_yahoo)
            latest_y = df_y['date'].max()
            gold = df_y[(df_y['date'] == latest_y) & (df_y['symbol'] == 'GOLD')]['value'].iloc[-1]
            oil = df_y[(df_y['date'] == latest_y) & (df_y['symbol'] == 'OIL')]['value'].iloc[-1]
            if (gold/oil) > 40:
                cross_asset_bias = "避险主导 (商品通胀/股市承压)"
    except Exception:
        pass

    # 4. 判定尾部风险 (Tail Risk)
    try:
        p_deriv = Path('data/coingecko_derivatives.csv')
        if p_deriv.exists():
            df_d = pd.read_csv(p_deriv).sort_values('date')
            df_d = df_d[df_d['date'] == df_d['date'].max()]
            btc_frs = df_d[df_d['index'] == 'BTC']['funding_rate_annual_pct'].dropna()
            if len(btc_frs) >= 2 and (btc_frs.max() - btc_frs.min()) > 10:
                tail_risk = f"高 (杠杆极端撕裂 {btc_frs.max()-btc_frs.min():.1f}%)"
    except Exception:
        pass

    # 生成机构晨报头部
    lines.insert(2, "====================================")
    lines.insert(3, f"⚖️ 宏观体制: {regime_growth} + {regime_inflation}")
    lines.insert(4, f"💧 流动性状态: {liquidity_state}")
    lines.insert(5, f"🌐 跨资产基调: {cross_asset_bias}")
    lines.insert(6, f"🚨 加密尾部风险: {tail_risk}")
    lines.insert(7, "🎯 战术建议: 避险为主，做多硬资产(黄金/油)，股指维持防守，加密市场逢高做空或观望。")
    lines.insert(8, "====================================")
    lines.insert(9, "")

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
    last_err = None
    for attempt in range(3):
        try:
            r = requests.post(WEBHOOK, json=payload, timeout=60)
            print(f'Feishu: HTTP {r.status_code} (attempt {attempt+1})')
            print(r.text)
            if r.status_code == 200:
                return
            last_err = f'HTTP {r.status_code}'
        except Exception as e:
            print(f'attempt {attempt+1} 失败: {e}')
            last_err = e
            time.sleep(5)
    print(f'❌ 飞书推送 3 次均失败: {last_err}')
    sys.exit(1)


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