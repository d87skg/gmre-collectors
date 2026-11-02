# -*- coding: utf-8 -*-
"""tools/send_local_feishu.py - GMRE 4.1 全息推送（日频决策 + 盘中参考分离）"""
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
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engines_v3.portfolio_optimizer import get_portfolio_advice, get_data_health

load_dotenv(r'D:\HGZC\.env')
WEBHOOK = os.environ.get('FEISHU_WEBHOOK')
SECRET = os.environ.get('FEISHU_SECRET')
DB_PATH = 'data/macro.db'


def gen_sign(timestamp, secret):
    string_to_sign = f'{timestamp}\n{secret}'
    return base64.b64encode(
        hmac.new(string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
    ).decode('utf-8')


def get_latest_data():
    asof = datetime.now().strftime('%Y-%m-%d')
    data = {
        'asof': asof, 'frag_score': 0.0, 'frag_level': 'N/A',
        'risk_gate': 'UNKNOWN', 'stress_layers': 'NONE',
        'p_high_risk': 0.0, 'p_r4': 0.0, 'p_r5': 0.0,
        'rrp_source': 'N/A',
        'caps_al': 'N/A', 'caps_cu': 'N/A', 'cu_spread': 0.0,
        'lti_score': 0.0, 'lti_level': 'UNKNOWN',
        'y10': 0.0, 'us10y_rt': 0.0, 'rrp': 0.0, 'hy_oas': 0.0, 'vix': 0.0,
        'bitget_fr': 0.0, 'coinbase_prem': 0.0, 'hl_imb': 0.0,
        'btc_etf_flow': 0.0, 'fear_greed': 0,
        'lti_raw_fr': 0.0, 'lti_raw_imb': 0.0,
        'gold': 0.0, 'silver': 0.0, 'oil': 0.0, 'copper': 0.0,
        'dxy': 0.0, 'usdjpy': 0.0, 'usdcny': 0.0, 'usdcnh': 0.0, 'spx': 0.0,
        'cn10y': 0.0, 'jp10y': 0.0, 'de10y': 0.0,
        'us_cn_spread': 0.0, 'us_jp_spread': 0.0, 'us_de_spread': 0.0,
        # 扩展指标（修正：市场广度用 20D 动量，不再用 SPY/RSP 绝对比值）
        'breadth_momentum': 0.0, 'iron_ore': 0.0, 'rebar': 0.0,
        # GMRE 4.1
        'dxy_5y_pct': None, 'dollar_scenario': 'N/A', 'dollar_assets': {},
        'cali_score': 0.0, 'cali_level': 'N/A', 'cali_detail': {},
        'crowding_score': 0.0, 'crowding_level': 'N/A',
        'micro_status': 'N/A', 'micro_score': 0.0, 'micro_details': {},
        'factor_status': 'N/A', 'factor_msg': 'N/A',
        'lti_details': {},
    }

    try:
        conn = sqlite3.connect(DB_PATH)

        row = conn.execute(
            "SELECT risk_gate, stress_state, frag_level FROM daily_summary WHERE asof_date=?",
            (asof,)
        ).fetchone()
        if row:
            data['risk_gate'], data['stress_layers'], data['frag_level'] = row[0], row[1], row[2]
            try:
                data['frag_score'] = float(row[2].split('(')[1].split(')')[0])
            except Exception:
                pass

        prob_row = conn.execute(
            "SELECT p_r4, p_r5, high_risk_prob FROM probability_engine WHERE asof_date=?",
            (asof,)
        ).fetchone()
        if not prob_row:
            prob_row = conn.execute(
                "SELECT p_r4, p_r5, high_risk_prob FROM probability_engine ORDER BY asof_date DESC LIMIT 1"
            ).fetchone()
        if prob_row:
            data['p_r4'] = float(prob_row[0] or 0)
            data['p_r5'] = float(prob_row[1] or 0)
            data['p_high_risk'] = float(prob_row[2] or 0)

        try:
            micro_row = conn.execute(
                "SELECT details_json FROM predictions_log WHERE forecast_date=?", (asof,)
            ).fetchone()
            if micro_row and micro_row[0]:
                detail_json = json.loads(micro_row[0])
                micro_res = detail_json.get('micro_trigger', {})
                data['micro_status'] = micro_res.get('status', 'N/A')
                data['micro_score'] = micro_res.get('score', 0.0)
                data['micro_details'] = micro_res.get('details', {})

                factor_res = detail_json.get('factor_concentration', {})
                data['factor_status'] = factor_res.get('status', 'N/A')
                data['factor_msg'] = factor_res.get('msg', 'N/A')
        except Exception:
            pass

        da_row = conn.execute(
            "SELECT dxy, dxy_5y_pct, scenario, detail FROM dollar_anchor WHERE asof_date=?",
            (asof,)
        ).fetchone()
        if not da_row:
            da_row = conn.execute(
                "SELECT dxy, dxy_5y_pct, scenario, detail FROM dollar_anchor ORDER BY asof_date DESC LIMIT 1"
            ).fetchone()
        if da_row:
            data['dxy_5y_pct'] = float(da_row[1]) if da_row[1] is not None else None
            data['dollar_scenario'] = da_row[2] or 'N/A'
            try:
                data['dollar_assets'] = json.loads(da_row[3]).get('assets', {})
            except Exception:
                pass

        cali_row = conn.execute(
            "SELECT cali_score, level, detail FROM cali_engine WHERE asof_date=?",
            (asof,)
        ).fetchone()
        if not cali_row:
            cali_row = conn.execute(
                "SELECT cali_score, level, detail FROM cali_engine ORDER BY asof_date DESC LIMIT 1"
            ).fetchone()
        if cali_row:
            data['cali_score'] = float(cali_row[0] or 0)
            data['cali_level'] = cali_row[1] or 'N/A'
            try:
                data['cali_detail'] = json.loads(cali_row[2]) if len(cali_row) > 2 and cali_row[2] else {}
            except Exception:
                data['cali_detail'] = {}

        cr_row = conn.execute(
            "SELECT score, level FROM crowding_engine WHERE asof_date=?",
            (asof,)
        ).fetchone()
        if not cr_row:
            cr_row = conn.execute(
                "SELECT score, level FROM crowding_engine ORDER BY asof_date DESC LIMIT 1"
            ).fetchone()
        if cr_row:
            data['crowding_score'] = float(cr_row[0] or 0)
            data['crowding_level'] = cr_row[1] or 'N/A'

        row = conn.execute(
            "SELECT caps_score FROM caps_engine WHERE symbol='SHFE_ALUMINUM' ORDER BY asof_date DESC LIMIT 1"
        ).fetchone()
        data['caps_al'] = round(row[0], 1) if row and row[0] is not None else 'N/A'
        row = conn.execute(
            "SELECT caps_score FROM caps_engine WHERE symbol='SHFE_COPPER' ORDER BY asof_date DESC LIMIT 1"
        ).fetchone()
        data['caps_cu'] = round(row[0], 1) if row and row[0] is not None else 'N/A'

        row = conn.execute(
            "SELECT lti_score, level FROM lti_engine ORDER BY asof_date DESC LIMIT 1"
        ).fetchone()
        if row:
            data['lti_score'], data['lti_level'] = round(row[0], 1), row[1]
        try:
            from engines_v3 import lti_engine as _lti_mod
            _lti_full = _lti_mod.compute_lti(asof)
            data['lti_details'] = _lti_full.get('details', {})
        except Exception:
            data['lti_details'] = {}

        def get_val(sid):
            r = conn.execute(
                "SELECT value FROM observations WHERE series_id=? ORDER BY timestamp DESC LIMIT 1",
                (sid,)
            ).fetchone()
            return r[0] if r else 0.0

        rrp_nyfed = get_val('RRP_NYFED')
        if rrp_nyfed and rrp_nyfed > 0:
            data['rrp'] = rrp_nyfed
            data['rrp_source'] = 'NYFED'
        else:
            data['rrp'] = get_val('RRP_BALANCE')
            data['rrp_source'] = 'FRED(降级)'

        # 日频决策口径：10Y 只用 YC10Y
        data['y10'] = get_val('YC10Y')
        # 盘中实时参考：不参与利差、不参与决策
        data['us10y_rt'] = get_val('US10Y_RT_TRADEWEB')

        data['cn10y'] = get_val('CN_10Y_YIELD')
        data['jp10y'] = get_val('JP_10Y')
        data['de10y'] = get_val('DE_10Y')

        # 利差计算只用日频 YC10Y
        if data['y10'] and data['cn10y']:
            data['us_cn_spread'] = data['y10'] - data['cn10y']
        if data['y10'] and data['jp10y']:
            data['us_jp_spread'] = data['y10'] - data['jp10y']
        if data['y10'] and data['de10y']:
            data['us_de_spread'] = data['y10'] - data['de10y']

        data['hy_oas'] = get_val('HY_SPREAD')
        data['vix'] = get_val('VIX')

        # 扩展数据（修正：市场广度 20D 动量）
        data['breadth_momentum'] = get_val('BREADTH_20D_MOMENTUM')
        data['iron_ore'] = get_val('IRON_ORE_DOMESTIC')
        data['rebar'] = get_val('REBAR')
        data['usdcnh'] = get_val('USD_CNH')

        fr_row = conn.execute(
            "SELECT value FROM observations WHERE series_id='BTC_FUNDING_RATE_1H' ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        data['bitget_fr'] = (fr_row[0] if fr_row else 0.0) * 3 * 365 * 100
        data['lti_raw_fr'] = data['bitget_fr']

        oi_rows = conn.execute(
            "SELECT value FROM observations WHERE series_id='BTC_OI_VALUE_HIST' ORDER BY timestamp DESC LIMIT 289"
        ).fetchall()
        data['hl_imb'] = (
            ((oi_rows[0][0] - oi_rows[288][0]) / oi_rows[288][0] * 100)
            if len(oi_rows) >= 288 and oi_rows[288][0] else 0.0
        )
        data['lti_raw_imb'] = data['hl_imb']

        row = conn.execute("SELECT * FROM feishu_snapshot ORDER BY timestamp DESC LIMIT 1").fetchone()
        if row:
            cols = [d[0] for d in conn.execute("SELECT * FROM feishu_snapshot LIMIT 1").description]
            f_data = dict(zip(cols, row))
            data['coinbase_prem'] = min(max(float(f_data.get('coinbase_premium', 0) or 0), -10.0), 10.0)
            data['btc_etf_flow'] = float(f_data.get('btc_etf_flow_usd_m', 0) or 0)
            data['fear_greed'] = int(float(f_data.get('fear_greed', 0) or 0))
            data['silver'] = float(f_data.get('silver', 0) or 0)
            data['copper'] = float(f_data.get('copper', 0) or 0)

            data['gold'] = get_val('GOLD_PRICE') or float(f_data.get('gold', 0) or 0)
            data['oil'] = get_val('WTI_OIL') or float(f_data.get('oil', 0) or 0)
            data['dxy'] = get_val('DXY_PROXY') or float(f_data.get('dxy', 0) or 0)
            data['usdjpy'] = get_val('USD_JPY') or float(f_data.get('usdjpy', 0) or 0)
            data['spx'] = get_val('NDX') or get_val('SP500') or float(f_data.get('ndx', 0) or 0)
            data['cu_spread'] = get_val('CU_SPREAD_PCT')

            raw_cny = float(f_data.get('usdcny_mid', 0) or 0)
            if raw_cny == 0:
                r_cny = conn.execute(
                    "SELECT value FROM observations WHERE series_id='USDCNY_MID' AND value > 0 ORDER BY timestamp DESC LIMIT 1"
                ).fetchone()
                raw_cny = r_cny[0] if r_cny else 0.0
            data['usdcny'] = raw_cny / 100.0 if raw_cny > 10 else raw_cny
        else:
            data['spx'] = get_val('NDX') or get_val('SP500')
            data['cu_spread'] = get_val('CU_SPREAD_PCT')

    except Exception as e:
        print(f"⚠️ 读取数据库失败: {e}")
    finally:
        if 'conn' in locals():
            conn.close()
    return data


def get_dual_phase(data):
    if data['cali_score'] >= 60:
        return '🔴 上半场（去杠杆中）', '50-70%'
    elif data['dxy_5y_pct'] is not None and data['dxy_5y_pct'] < 10:
        return '🟠 上半场尾部（流动性枯竭末期）', '50-70%'
    elif data['risk_gate'] in ('ORANGE', 'YELLOW'):
        return '🟡 过渡期（政策底已现，市场底待确认）', '40-60%'
    else:
        return '🟢 下半场（降息重估）', '10-20%'


def main():
    if not WEBHOOK or not SECRET:
        return
    d = get_latest_data()

    try:
        caps_cu_val = d['caps_cu'] if isinstance(d['caps_cu'], float) else 0
        weights, cash_pct = get_portfolio_advice(d['risk_gate'], d['frag_score'], caps_cu=caps_cu_val)
        health_text = get_data_health()
    except Exception as e:
        weights = {'BTC': 0, 'GOLD': 0, 'US10Y': 0}
        cash_pct = 100
        health_text = f"❌ 仓位引擎异常: {e}"

    if d['caps_cu'] != 'N/A' and isinstance(d['caps_cu'], float) and d['caps_cu'] >= 80:
        action_guide = "🚨 极度危险：沪铜发生史诗级逼仓，宏观流动性枯竭，现金为王，切勿进场！"
    elif d['risk_gate'] == 'RED':
        reasons = []
        if d['frag_score'] >= 80:
            reasons.append(f"Fragility={d['frag_score']:.1f}")
        if d['p_high_risk'] >= 0.50:
            reasons.append(f"P(R4+R5)={d['p_high_risk']*100:.1f}%")
        action_guide = f"⚠️ 行动指南：现金为王，久期与杠杆降至最低。触发：{', '.join(reasons) or '多压力层共振'}"
    elif d['risk_gate'] == 'ORANGE':
        reasons = []
        if d['frag_score'] >= 65:
            reasons.append(f"Fragility={d['frag_score']:.1f}")
        if d['p_high_risk'] >= 0.30:
            reasons.append(f"P(R4+R5)={d['p_high_risk']*100:.1f}%")
        action_guide = f"⚖️ 行动指南：保持防守，控制仓位，等待右侧信号。触发：{', '.join(reasons) or '结构性脆弱'}"
    else:
        action_guide = "🟢 行动指南：可适度提升风险敞口，顺势而为。"

    micro_alerts = []
    if d['bitget_fr'] > 50:
        micro_alerts.append(f"🚨 资金费率极度拥挤: {d['bitget_fr']:+.2f}% 年化")
    if d['coinbase_prem'] < -0.1:
        micro_alerts.append(f"🇺🇸 机构现货抛压: {d['coinbase_prem']:+.3f}%")
    if d['hl_imb'] > 3.0:
        micro_alerts.append(f"📊 持仓量剧增: 24H变幅 {d['hl_imb']:+.2f}%")
    elif d['hl_imb'] < -3.0:
        micro_alerts.append(f"📊 持仓量剧减: 24H变幅 {d['hl_imb']:+.2f}%")
    micro_text = "\n".join(micro_alerts) if micro_alerts else "  · 微观结构暂无极端异动"

    liquidity_warning = ""
    if d.get('micro_status') == 'CRITICAL':
        liquidity_warning = "\n🚨 **执行阻断**: 微观结构极度恶化，盘口深度枯竭，禁止使用市价单，请使用限价单或观望！"

    icon_cu = "⚪" if d['caps_cu'] == 'N/A' else ("🚨" if isinstance(d['caps_cu'], float) and d['caps_cu'] >= 60 else "🟡")
    icon_al = "⚪" if d['caps_al'] == 'N/A' else ("🚨" if isinstance(d['caps_al'], float) and d['caps_al'] >= 60 else "🟡")
    cny_display = f"{d['usdcny']:.4f}" if d['usdcny'] > 0 else "N/A"
    cnh_display = f"{d['usdcnh']:.4f}" if d['usdcnh'] > 0 else "N/A"
    spx_display = f"{d['spx']:.1f}" if d['spx'] > 0 else "N/A"
    bj_time = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')

    if d['p_high_risk'] >= 0.50:
        prob_icon = "🔴"
    elif d['p_high_risk'] >= 0.30:
        prob_icon = "🟠"
    elif d['p_high_risk'] >= 0.15:
        prob_icon = "🟡"
    else:
        prob_icon = "🟢"

    phase_text, cash_rec = get_dual_phase(d)

    if d['risk_gate'] == 'RED' or d['cali_score'] > 70:
        hedge_text = "• SPX: Buy 3M 5% OTM Put\n• BTC: Buy 1M 10% OTM Put"
    elif d['risk_gate'] == 'ORANGE':
        hedge_text = "• SPX: Collar 成本≈0"
    else:
        hedge_text = "• 当前无需对冲"

    dxy_pct_str = f"{d['dxy_5y_pct']:.1f}%" if d['dxy_5y_pct'] is not None else "N/A"
    scenario_map = {
        'RATE_CUT_FORCED': '🔴 降息倒逼路径',
        'HIGH_RATE_MAINTAINED': '🟢 高利率维持路径',
        'MIXED': '🟡 混合信号',
        'LIQUIDITY_SQUEEZE': '🚨 流动性挤压',
        'N/A': '⚪ 数据不足'
    }
    scenario_text = scenario_map.get(d['dollar_scenario'], '⚪ ' + str(d['dollar_scenario']))

    # 市场广度：20D 动量
    breadth_display = f"{d['breadth_momentum']:+.2f}%"
    breadth_note = "负=小盘拖累/宽度恶化" if d['breadth_momentum'] < 0 else "正=小盘相对走强/宽度改善"

    # 10Y 美债：日频决策 + 盘中参考分离
    us10y_rt_display = f"{d['us10y_rt']:.3f}%" if d['us10y_rt'] and d['us10y_rt'] > 0 else "N/A"

    text = f"""📊 **GMRE 4.1 全息风控晨报** - {d['asof']}
====================================
🚦 **Risk Gate**: {d['risk_gate']}
⚠️ **Fragility**: {d['frag_level']}
{prob_icon} **概率引擎**: P(R4+R5) = {d['p_high_risk']*100:.2f}%
😱 **情绪指数**: {d['fear_greed']} (Fear & Greed)
{action_guide}
{liquidity_warning}
====================================
💵 **美元锚定区**:
  • DXY: {d['dxy']:.2f} (5y_pct={dxy_pct_str})
  • 情景判定: {scenario_text}
  • 四资产5D: WTI {d.get('dollar_assets',{}).get('WTI_5D','N/A')}% | GOLD {d.get('dollar_assets',{}).get('GOLD_5D','N/A')}% | 10Y {d.get('dollar_assets',{}).get('Y10_5D','N/A')}% | DXY {d.get('dollar_assets',{}).get('DXY_5D','N/A')}%

🌡️ **CALI 流动性**: {d['cali_score']:.1f}/100 ({d['cali_level']})
  • MOVE={d.get('cali_detail',{}).get('MOVE',{}).get('value','N/A')} | HY斜率={d.get('cali_detail',{}).get('HY_slope','N/A')} | 期限溢价={d.get('cali_detail',{}).get('Term_Premium','N/A')} | VIX={d.get('cali_detail',{}).get('VIX','N/A')}

🔬 **微观结构扳机**: {d.get('micro_status', 'N/A')} (评分={d.get('micro_score', 0.0)})
  • 期权/盘口: {d.get('micro_details', {})}

📐 **因子集中度**: {d.get('factor_status', 'N/A')} | {d.get('factor_msg', 'N/A')}
====================================
💼 **风险平价仓位建议**:
  • 现金留存: {cash_pct:.1f}%
  • BTC: {weights.get('BTC', 0):.1f}% | 黄金: {weights.get('GOLD', 0):.1f}% | 美债: {weights.get('US10Y', 0):.1f}%

🌍 **大类资产与汇率矩阵**:
  • 黄金: ${d['gold']:.2f} | 白银: ${d['silver']:.2f}
  • 原油 (WTI): ${d['oil']:.2f} | 铜: ${d['copper']:.2f}
  • 市场广度 20D 动量: {breadth_display} ({breadth_note})
  • 黑色系: 铁矿石 {d['iron_ore']:.1f} | 螺纹钢 {d['rebar']:.1f}
  • 美股: {spx_display}
  • 美元指数: {d['dxy']:.2f} | 美元/日元: {d['usdjpy']:.2f} | 离岸人民币: {cnh_display} | 在岸人民币: {cny_display}

🌐 **全球宏观与利差监控**:
  • 10Y 美债(日频YC10Y/决策): {d['y10']:.2f}% | 盘中Tradeweb(参考): {us10y_rt_display}
  • 中国10Y: {d['cn10y']:.2f}% | 日本10Y: {d['jp10y']:.2f}% | 德国10Y: {d['de10y']:.2f}%
  • 中美利差: {d['us_cn_spread']:+.2f}% | 美日利差: {d['us_jp_spread']:+.2f}% | 美德利差: {d['us_de_spread']:+.2f}%
  • 注：盘中实时10Y不参与上述利差与 Risk Gate 计算
  • RRP 余额: {d['rrp']:.2f} 十亿美元（约 {d['rrp']*10:.1f} 亿美元）[{d['rrp_source']}] | HY OAS: {d['hy_oas']*100:.0f} bp | VIX: {d['vix']:.2f}

🚨 **压力层 (S 状态机)**:
  {d['stress_layers']}

🔬 **微观异动警报**:
{micro_text}

📦 **商品逼仓 (CAPS)**:
  • 沪铜: {icon_cu} {d['caps_cu']} (内外价差: {d['cu_spread']:+.2f}%)
  • 沪铝: {icon_al} {d['caps_al']}

💧 **清算透明度 (LTI)**:
  • {d['lti_level']} ({d['lti_score']})
  • FR极值分: {d['lti_raw_fr']:.1f} | 持仓24H变幅: {d['lti_raw_imb']:+.2f}%
  • Gold_Stock: {d.get('lti_details',{}).get('Gold_Stock','N/A')}

🛡️ **对冲建议**:
{hedge_text}
====================================
📊 **数据健康度**: {health_text}
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
        print("✅ GMRE 4.1 全息晨报已成功推送到飞书！")
    else:
        print(f"❌ 飞书推送失败: {r.text}")


if __name__ == "__main__":
    main()