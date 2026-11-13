# -*- coding: utf-8 -*-
"""tools/send_local_feishu.py - GMRE 4.1 全息推送（代理层适配版）"""
import os, sys, requests, json, hmac, hashlib, base64, time, sqlite3
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engines_v3.portfolio_optimizer import get_portfolio_advice, get_data_health
from core.data_proxy import load

load_dotenv(r'D:\HGZC\.env')
WEBHOOK = os.environ.get('FEISHU_WEBHOOK')
SECRET = os.environ.get('FEISHU_SECRET')
DB_PATH = 'data/macro.db'

def gen_sign(timestamp, secret):
    string_to_sign = f'{timestamp}\n{secret}'
    return base64.b64encode(hmac.new(string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()).decode('utf-8')

def get_latest_data():
    asof = datetime.now().strftime('%Y-%m-%d')
    data = {
        'asof': asof, 'frag_score': 0.0, 'frag_level': 'N/A',
        'risk_gate': 'UNKNOWN', 'stress_layers': 'NONE',
        'p_high_risk': 0.0, 'p_r4': 0.0, 'p_r5': 0.0,
        'rrp_source': 'N/A', 'caps_al': 'N/A', 'caps_cu': 'N/A', 'cu_spread': 0.0,
        'lti_score': 0.0, 'lti_level': 'UNKNOWN', 'y10': 0.0, 'us10y_rt': 0.0, 
        'rrp': 0.0, 'hy_oas': 0.0, 'vix': 0.0, 'bitget_fr': 0.0, 'coinbase_prem': 0.0, 
        'hl_imb': 0.0, 'btc_etf_flow': 0.0, 'fear_greed': 0, 'lti_raw_fr': 0.0, 'lti_raw_imb': 0.0,
        'gold': 'N/A', 'silver': 'N/A', 'oil': 'N/A', 'copper': 'N/A',
        'dxy': 0.0, 'usdjpy': 0.0, 'usdcny': 0.0, 'usdcnh': 0.0, 'spx': 0.0,
        'cn10y': 0.0, 'jp10y': 0.0, 'de10y': 0.0,
        'us_cn_spread': 0.0, 'us_jp_spread': 0.0, 'us_de_spread': 0.0,
        'breadth_momentum': 0.0, 'iron_ore': 0.0, 'rebar': 0.0,
        'dxy_5y_pct': None, 'dollar_scenario': 'N/A', 'dollar_assets': {},
        'cali_score': 0.0, 'cali_level': 'N/A', 'cali_detail': {},
        'crowding_score': 0.0, 'crowding_level': 'N/A',
        'micro_status': 'N/A', 'micro_score': 0.0, 'micro_details': {},
        'factor_status': 'N/A', 'factor_msg': 'N/A', 'lti_details': {},
        'event_perm': 'N/A', 'event_reason': 'N/A',
    }

    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute("SELECT risk_gate, stress_state, frag_level FROM daily_summary WHERE asof_date=?", (asof,)).fetchone()
        if row:
            data['risk_gate'], data['stress_layers'], data['frag_level'] = row[0], row[1], row[2]
            try: data['frag_score'] = float(row[2].split('(')[1].split(')')[0])
            except: pass

        prob_row = conn.execute("SELECT p_r4, p_r5, high_risk_prob FROM probability_engine WHERE asof_date=?", (asof,)).fetchone()
        if not prob_row: prob_row = conn.execute("SELECT p_r4, p_r5, high_risk_prob FROM probability_engine ORDER BY asof_date DESC LIMIT 1").fetchone()
        if prob_row:
            data['p_r4'], data['p_r5'], data['p_high_risk'] = float(prob_row[0] or 0), float(prob_row[1] or 0), float(prob_row[2] or 0)

        try:
            micro_row = conn.execute("SELECT details_json FROM predictions_log WHERE forecast_date=?", (asof,)).fetchone()
            if micro_row and micro_row[0]:
                detail_json = json.loads(micro_row[0])
                micro_res = detail_json.get('micro_trigger', {})
                data['micro_status'], data['micro_score'], data['micro_details'] = micro_res.get('status', 'N/A'), micro_res.get('score', 0.0), micro_res.get('details', {})
                factor_res = detail_json.get('factor_concentration', {})
                data['factor_status'], data['factor_msg'] = factor_res.get('status', 'N/A'), factor_res.get('msg', 'N/A')
                event_res = detail_json.get('event_interceptor', {})
                data['event_perm'], data['event_reason'] = event_res.get('perm', 'N/A'), event_res.get('reason', 'N/A')
        except: pass

        da_row = conn.execute("SELECT dxy, dxy_5y_pct, scenario, detail FROM dollar_anchor WHERE asof_date=?", (asof,)).fetchone()
        if not da_row: da_row = conn.execute("SELECT dxy, dxy_5y_pct, scenario, detail FROM dollar_anchor ORDER BY asof_date DESC LIMIT 1").fetchone()
        if da_row:
            data['dxy_5y_pct'] = float(da_row[1]) if da_row[1] is not None else None
            data['dollar_scenario'] = da_row[2] or 'N/A'
            try: data['dollar_assets'] = json.loads(da_row[3]).get('assets', {})
            except: pass

        cali_row = conn.execute("SELECT cali_score, level, detail FROM cali_engine WHERE asof_date=?", (asof,)).fetchone()
        if not cali_row: cali_row = conn.execute("SELECT cali_score, level, detail FROM cali_engine ORDER BY asof_date DESC LIMIT 1").fetchone()
        if cali_row:
            data['cali_score'], data['cali_level'] = float(cali_row[0] or 0), cali_row[1] or 'N/A'
            try: data['cali_detail'] = json.loads(cali_row[2]) if len(cali_row) > 2 and cali_row[2] else {}
            except: data['cali_detail'] = {}

        cr_row = conn.execute("SELECT score, level FROM crowding_engine WHERE asof_date=?", (asof,)).fetchone()
        if not cr_row: cr_row = conn.execute("SELECT score, level FROM crowding_engine ORDER BY asof_date DESC LIMIT 1").fetchone()
        if cr_row: data['crowding_score'], data['crowding_level'] = float(cr_row[0] or 0), cr_row[1] or 'N/A'

        row = conn.execute("SELECT caps_score FROM caps_engine WHERE symbol='SHFE_ALUMINUM' ORDER BY asof_date DESC LIMIT 1").fetchone()
        data['caps_al'] = round(row[0], 1) if row and row[0] is not None else 'N/A'
        row = conn.execute("SELECT caps_score FROM caps_engine WHERE symbol='SHFE_COPPER' ORDER BY asof_date DESC LIMIT 1").fetchone()
        data['caps_cu'] = round(row[0], 1) if row and row[0] is not None else 'N/A'

        row = conn.execute("SELECT lti_score, level FROM lti_engine ORDER BY asof_date DESC LIMIT 1").fetchone()
        if row: data['lti_score'], data['lti_level'] = round(row[0], 1), row[1]

        # 🆕 采用代理层获取最新的数据
        def get_val(sid):
            try:
                s = load(conn, sid, limit=1, verbose=False)
                return float(s.iloc[-1]) if not s.empty else 0.0
            except: return 0.0

        rrp_nyfed = get_val('RRP_NYFED')
        if rrp_nyfed > 0:
            data['rrp'], data['rrp_source'] = rrp_nyfed, 'NYFED'
        else:
            data['rrp'], data['rrp_source'] = get_val('RRP_BALANCE'), 'FRED(降级)'

        data['y10'] = get_val('YC10Y')
        data['us10y_rt'] = get_val('US10Y_RT_TRADEWEB')
        data['cn10y'] = get_val('CN_10Y_YIELD')
        data['jp10y'] = get_val('JP_10Y')
        data['de10y'] = get_val('DE_10Y')

        if data['y10'] and data['cn10y']: data['us_cn_spread'] = data['y10'] - data['cn10y']
        if data['y10'] and data['jp10y']: data['us_jp_spread'] = data['y10'] - data['jp10y']
        if data['y10'] and data['de10y']: data['us_de_spread'] = data['y10'] - data['de10y']

        data['hy_oas'] = get_val('HY_SPREAD')
        data['vix'] = get_val('VIX')
        data['breadth_momentum'] = get_val('BREADTH_20D_MOMENTUM')
        data['iron_ore'] = get_val('IRON_ORE_DOMESTIC')
        data['rebar'] = get_val('REBAR')
        data['usdcnh'] = get_val('USD_CNH')
        data['dxy'] = get_val('DXY_PROXY')
        data['usdjpy'] = get_val('USD_JPY')
        data['spx'] = get_val('NDX') or get_val('SP500')
        data['cu_spread'] = get_val('CU_SPREAD_PCT')

        fr_series = load(conn, 'BTC_FUNDING_RATE_1H', limit=1, verbose=False)
        data['bitget_fr'] = float(fr_series.iloc[-1]) * 3 * 365 * 100 if not fr_series.empty else 0.0
        data['lti_raw_fr'] = data['bitget_fr']

        oi_series = load(conn, 'BTC_OI_VALUE_HIST', limit=289, verbose=False)
        data['hl_imb'] = ((oi_series.iloc[-1] - oi_series.iloc[0]) / oi_series.iloc[0] * 100) if len(oi_series) >= 289 and oi_series.iloc[0] else 0.0
        data['lti_raw_imb'] = data['hl_imb']

        # 保留 feishu_snapshot 作为某些聚合数据（如 ETF 流向）的兜底
        row = conn.execute("SELECT * FROM feishu_snapshot ORDER BY timestamp DESC LIMIT 1").fetchone()
        if row:
            cols = [d[0] for d in conn.execute("SELECT * FROM feishu_snapshot LIMIT 1").description]
            f_data = dict(zip(cols, row))
            data['coinbase_prem'] = min(max(float(f_data.get('coinbase_premium', 0) or 0), -10.0), 10.0)
            data['btc_etf_flow'] = float(f_data.get('btc_etf_flow_usd_m', 0) or 0)
            data['fear_greed'] = int(float(f_data.get('fear_greed', 0) or 0))
            silver_val = float(f_data.get('silver', 0) or 0)
            data['silver'] = silver_val if silver_val > 0 else 'N/A'
            copper_val = float(f_data.get('copper', 0) or 0)
            data['copper'] = copper_val if copper_val > 0 else 'N/A'
            gold_val = get_val('GOLD_PRICE') or float(f_data.get('gold', 0) or 0)
            data['gold'] = gold_val if gold_val > 0 else 'N/A'
            oil_val = get_val('WTI_OIL') or float(f_data.get('oil', 0) or 0)
            data['oil'] = oil_val if oil_val > 0 else 'N/A'
            
            raw_cny = float(f_data.get('usdcny_mid', 0) or 0)
            if raw_cny == 0: raw_cny = get_val('USDCNY_MID')
            data['usdcny'] = raw_cny / 100.0 if raw_cny > 10 else raw_cny
    except Exception as e: print(f"⚠️ 读取数据库失败: {e}")
    finally: conn.close()
    return data

def get_dual_phase(data):
    if data['cali_score'] >= 60: return '🔴 上半场（去杠杆中）', '50-70%'
    elif data['dxy_5y_pct'] is not None and data['dxy_5y_pct'] < 10: return '🟠 上半场尾部（流动性枯竭末期）', '50-70%'
    elif data['risk_gate'] in ('ORANGE', 'YELLOW'): return '🟡 过渡期（政策底已现，市场底待确认）', '40-60%'
    else: return '🟢 下半场（降息重估）', '10-20%'

def main():
    if not WEBHOOK or not SECRET: return
    d = get_latest_data()
    try:
        weights, cash_pct = get_portfolio_advice(d['risk_gate'], d['frag_score'], caps_cu=d['caps_cu'] if isinstance(d['caps_cu'], float) else 0)
        health_text = get_data_health()
    except Exception as e:
        weights, cash_pct, health_text = {'BTC': 0, 'GOLD': 0, 'SHY': 0}, 100, f"❌ 仓位引擎异常: {e}"

    if d['caps_cu'] != 'N/A' and isinstance(d['caps_cu'], float) and d['caps_cu'] >= 80:
        action_guide = "🚨 极度危险：沪铜发生史诗级逼仓，宏观流动性枯竭，现金为王，切勿进场！"
    elif d['risk_gate'] == 'RED':
        action_guide = "⚠️ 行动指南：现金为王，久期与杠杆降至最低。"
    elif d['risk_gate'] == 'ORANGE':
        action_guide = "⚖️ 行动指南：保持防守，控制仓位，等待右侧信号。"
    else:
        action_guide = "🟢 行动指南：可适度提升风险敞口，顺势而为。"

    micro_text = "\n".join([a for a in [
        f"🚨 资金费率极度拥挤: {d['bitget_fr']:+.2f}% 年化" if d['bitget_fr'] > 50 else "",
        f"🇺🇸 机构现货抛压: {d['coinbase_prem']:+.3f}%" if d['coinbase_prem'] < -0.1 else "",
        f"📊 持仓量剧增: 24H变幅 {d['hl_imb']:+.2f}%" if d['hl_imb'] > 3.0 else "",
    ] if a]) or "  · 微观结构暂无极端异动"

    bj_time = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
    prob_icon = "🔴" if d['p_high_risk'] >= 0.5 else "🟠" if d['p_high_risk'] >= 0.3 else "🟡" if d['p_high_risk'] >= 0.15 else "🟢"
    phase_text, _ = get_dual_phase(d)
    
    hedge_text = "• SPX: Buy 3M 5% OTM Put\n• BTC: Buy 1M 10% OTM Put" if d['risk_gate'] == 'RED' or d['cali_score'] > 70 else "• SPX: Collar 成本≈0" if d['risk_gate'] == 'ORANGE' else "• 当前无需对冲"
    
    text = f"""📊 **GMRE 4.1 全息风控晨报** - {d['asof']}
====================================
🚦 **Risk Gate**: {d['risk_gate']}
⚠️ **Fragility**: {d['frag_level']}
{prob_icon} **概率引擎**: P(R4+R5) = {d['p_high_risk']*100:.2f}%
😱 **情绪指数**: {d['fear_greed']} (Fear & Greed)
{action_guide}
====================================
🚦 **事件拦截器**: {d['event_perm']}
  • 判决原因: {d['event_reason']}
====================================
💵 **美元锚定区**:
  • DXY: {d['dxy']:.2f} (5y_pct={f"{d['dxy_5y_pct']:.1f}%" if d['dxy_5y_pct'] is not None else "N/A"})
  • 情景判定: {d['dollar_scenario']}
====================================
💼 **风险平价仓位建议**:
  • 现金留存: {cash_pct:.1f}%
  • BTC: {weights.get('BTC', 0):.1f}% | 黄金: {weights.get('GOLD', 0):.1f}% | 短债: {weights.get('SHY', 0):.1f}%
====================================
🌍 **大类资产**:
  • 黄金: ${d['gold'] if isinstance(d['gold'], str) else f"{d['gold']:.2f}"} | 原油: ${d['oil'] if isinstance(d['oil'], str) else f"{d['oil']:.2f}"}
  • 美股: {d['spx']:.1f} | 美元指数: {d['dxy']:.2f} | 美元/日元: {d['usdjpy']:.2f}
🌐 **宏观监控**:
  • 10Y 美债: {d['y10']:.2f}% | RRP: {d['rrp']:.2f}B [{d['rrp_source']}] | HY OAS: {d['hy_oas']*100:.0f}bp | VIX: {d['vix']:.2f}
🚨 **压力层**: {d['stress_layers']}
🔬 **微观异动**: 
{micro_text}
📦 **商品逼仓**: 沪铜 {d['caps_cu']} (价差 {d['cu_spread']:+.2f}%) | 沪铝 {d['caps_al']}
🛡️ **对冲建议**: {hedge_text}
====================================
📊 **数据健康度**: {health_text}
⏱️ 生成时间: {bj_time} (北京时间)
"""
    ts = str(int(time.time()))
    payload = {"timestamp": ts, "sign": gen_sign(ts, SECRET), "msg_type": "text", "content": {"text": text}}
    r = requests.post(WEBHOOK, json=payload, timeout=10)
    if r.status_code == 200 and r.json().get('code') == 0: print("✅ GMRE 4.1 全息晨报已成功推送到飞书！")
    else: print(f"❌ 飞书推送失败: {r.text}")

if __name__ == "__main__":
    main()