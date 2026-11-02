"""engines_v3/run_v4.py - GMRE 4.0 完整集成版（Fragility 提前 + 新引擎调用）"""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import io
import contextlib
import sqlite3
import subprocess
import hashlib
import json
import math
import re
from datetime import datetime

from engines_v2 import (
    engine_liq, engine_inf, engine_mon, engine_risk, engine_fis,
    regime_map, yen_carry_state, liquidity_alert, hedge_advisor,
    data_quality_check, dau_alert
)
from engines_v3 import (
    stress_overlay_v2, defense_v4,
    engine_mon_v2, engine_fis_v2, engine_inf_expect,
    invalidation_conditions
)

try:
    from tools.check_events import check_upcoming_events
except ImportError:
    check_upcoming_events = lambda **kwargs: []

try:
    from tools.rrp_guard import run_rrp_guard
except ImportError:
    run_rrp_guard = None

DB_PATH = 'data/macro.db'


def get_git_commit():
    try:
        return subprocess.check_output(['git', 'rev-parse', 'HEAD'],
                                       cwd=os.path.dirname(__file__)).decode('utf-8').strip()[:8]
    except Exception:
        return "UNKNOWN"


def get_series_meta(sid, override_value=None):
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT timestamp, value FROM observations WHERE series_id=? ORDER BY timestamp DESC LIMIT 1",
            (sid,)
        ).fetchone()
        conn.close()
        if row:
            date_str = row[0].split(' ')[0].split('T')[0]
            value = override_value if override_value is not None else float(row[1])
            return date_str, value
    except Exception:
        pass
    if override_value is not None:
        return datetime.now().strftime('%Y-%m-%d'), override_value
    return "N/A", None


def compute_risk_gate(frag_level, stress_overall, contagion_status, systemic_confirmed, p_r4_r5=None):
    """Risk Gate v4.3 - 组合原因"""
    if frag_level == 'N/A' or frag_level is None:
        return 'UNKNOWN', '🚨 数据缺失：Fragility 状态无法计算'
    try:
        frag_score = float(frag_level.split('(')[1].split(')')[0])
        if not math.isfinite(frag_score):
            return 'UNKNOWN', '🚨 数值异常：Fragility 得分为 NaN 或 Inf'
    except Exception:
        return 'SAFE_MODE', '🚨 核心计算故障：Fragility 解析失败'

    if systemic_confirmed:
        return 'BLACK', '🚨 系统性危机已确认'

    red_reasons = []
    if frag_score >= 80:
        red_reasons.append(f"Fragility={frag_score:.1f}≥80")
    if 'FUNDING' in stress_overall and 'CREDIT' in stress_overall:
        red_reasons.append("FUNDING+CREDIT 共振")
    if p_r4_r5 is not None and p_r4_r5 >= 0.50:
        red_reasons.append(f"P(R4+R5)={p_r4_r5*100:.1f}%≥50%")
    if red_reasons:
        return 'RED', f'🔴 高风险：{", ".join(red_reasons)}'

    orange_reasons = []
    if frag_score >= 65:
        orange_reasons.append(f"Fragility={frag_score:.1f}≥65")
    if stress_overall.count('+') >= 1:
        orange_reasons.append(f"Stress={stress_overall}")
    if p_r4_r5 is not None and p_r4_r5 >= 0.30:
        orange_reasons.append(f"P(R4+R5)={p_r4_r5*100:.1f}%≥30%")
    if orange_reasons:
        return 'ORANGE', f'🟠 中高风险：{", ".join(orange_reasons)}'

    if frag_score >= 50:
        return 'YELLOW', f'🟡 中等：Fragility={frag_score:.1f}'
    return 'GREEN', f'🟢 低风险：Fragility={frag_score:.1f}'


def get_dual_phase_guide(gate, frag_score, cali_score, scenario, dxy_pct):
    """🆕 双阶段操作指南"""
    if cali_score and cali_score >= 60:
        phase, emoji = '上半场（去杠杆中）', '🔴'
    elif dxy_pct and dxy_pct < 10:
        phase, emoji = '上半场尾部（流动性枯竭末期）', '🟠'
    elif gate in ('ORANGE', 'YELLOW'):
        phase, emoji = '过渡期（政策底已现，市场底待确认）', '🟡'
    else:
        phase, emoji = '下半场（降息重估）', '🟢'

    if phase.startswith('上半场'):
        cash, gold, note = '50-70%', '5-10%', '现金为王，等右侧信号'
    elif phase.startswith('过渡'):
        cash, gold, note = '40-60%', '7-10%', '保持防守，分批左侧埋伏'
    else:
        cash, gold, note = '10-20%', '5-10%', '子弹打出去，享受估值重估'

    return {'phase': phase, 'phase_emoji': emoji,
            'cash_recommendation': cash, 'gold_recommendation': gold, 'note': note}


def main():
    asof = datetime.now().strftime('%Y-%m-%d')
    print(f"\n{'='*60}\n  GMRE 4.0 完整版 - {asof}\n{'='*60}\n")

    print(f"{'-'*50}\n  📅 宏观事件倒计时检查\n{'-'*50}")
    check_upcoming_events(config_path="config/events_calendar.yaml")
    print(f"{'-'*50}\n")

    audit_status, regime_label, p_r4_r5_val, frag_score_val = 'UNKNOWN', 'UNKNOWN', 0.0, 0.0

    # ============ 数据自检 ============
    print(f"{'-'*60}")
    try:
        audit = data_quality_check.run_audit(asof)
        audit_status = audit['status']
        icon = {'PASS': '✅', 'WARN': '⚠️', 'FAIL': '❌'}.get(audit['status'], '?')
        print(f"  {icon} 数据自检: {audit['status']} "
              f"(通过{audit['pass_count']}/警告{audit['warn_count']}/严重{audit['critical_count']})")
    except Exception as e:
        print(f"  ⚠️ 数据自检异常: {e}")

    # ============ 轨道1：Base Regime ============
    print(f"\n┌{'─'*58}┐\n│  【轨道1】Base Regime (R0-R6)                     │\n└{'─'*58}┘\n")
    for mod in [engine_inf, engine_mon, engine_fis, engine_liq, engine_risk]:
        try:
            r = mod.compute_engine(asof)
            print(f"  [{r['engine_id']}] Z={r['z_score']:+.4f} | {r['direction']}")
        except Exception as e:
            print(f"  [{mod.ENGINE_ID}] ❌ 失败: {e}")

    try:
        mon_v2 = engine_mon_v2.compute_mon_v2(asof)
        print(f"  [MON_V2] Composite={mon_v2['composite']:+.4f} | {mon_v2['direction']}")
    except Exception:
        pass
    try:
        fis_v2 = engine_fis_v2.compute_fis_v2(asof)
        print(f"  [FIS_V2] Composite={fis_v2['composite']:+.4f} | {fis_v2['direction']}")
    except Exception:
        pass
    try:
        inf_exp = engine_inf_expect.compute_engine(asof)
        if inf_exp.get('level') != 'MISSING_DATA':
            print(f"  [INF_EXPECT] Stress={inf_exp['inf_expect_stress']}/100 | {inf_exp['level']}")
    except Exception:
        pass

    print(f"\n{'-'*60}")
    regime = {}
    try:
        regime = regime_map.run(asof)
        if regime:
            regime_label = regime['regime_label']
            print(f"  GMS体制: {regime['regime_label']} ({regime['regime_name']})")
            print(f"  置信度: {regime['confidence']*100:.1f}%")
    except Exception as e:
        print(f"  ⚠️ GMS异常: {e}")

    # ============ 🆕 预轨：Fragility（提前计算）============
    print(f"\n┌{'─'*58}┐\n│  【预轨】Fragility（提前计算）                       │\n└{'─'*58}┘\n")
    frag_level = 'N/A'
    try:
        from engines_v3 import fragility_engine
        with contextlib.redirect_stdout(io.StringIO()):
            _frag_pre = fragility_engine.compute_fragility(asof)
        frag_level = f"{_frag_pre['level']} ({_frag_pre['fragility_score']})"
        frag_score_val = _frag_pre['fragility_score']
        print(f"  [Fragility] {frag_level}")
    except Exception as e:
        print(f"  ⚠️ Fragility 提前计算失败: {e}")

    # ============ 核心数据溯源 ============
    print(f"\n{'─'*50}\n  🔍 核心数据溯源")
    rrp_override = None
    rrp_source_tag = ""
    if run_rrp_guard is not None:
        try:
            _g = run_rrp_guard(verbose=False)
            if _g.primary_value is not None:
                rrp_override = float(_g.primary_value)
                rrp_source_tag = f" [{_g.primary_source}]"
        except Exception:
            pass

    audit_sids = [
        ('RRP 余额', 'RRP_BALANCE', 'Billion USD', rrp_override),
        ('10Y 收益率', 'YC10Y', '%', None),
        ('HY 信用利差', 'HY_SPREAD', '%', None),
        ('标普500', 'SP500', 'Index', None),
        ('VIX', 'VIX', 'Index', None),
        ('美元/日元', 'USD_JPY', 'Price', None),
        ('中国10Y', 'CN_10Y_YIELD', '%', None),
        ('日本10Y', 'JP_10Y', '%', None),
        ('德国10Y', 'DE_10Y', '%', None),
    ]
    input_snapshot = {}
    for name, sid, unit, override in audit_sids:
        d, v = get_series_meta(sid, override_value=override)
        if v is not None:
            source_note = rrp_source_tag if name == 'RRP 余额' else ""
            print(f"    {name:12s}: {d} | 值 = {v:.4f} {unit}{source_note}")
            input_snapshot[sid] = v
        else:
            print(f"    {name:12s}: {d} | 值 = N/A")
            input_snapshot[sid] = None
    print(f"{'─'*50}")

    try:
        cn10y = get_series_meta('CN_10Y_YIELD')[1]
        jp10y = get_series_meta('JP_10Y')[1]
        de10y = get_series_meta('DE_10Y')[1]
        us10y = get_series_meta('YC10Y')[1]
        if us10y and cn10y:
            print(f"  [宏观联动] 中美10Y利差: {us10y - cn10y:+.2f}% (美 {us10y:.2f}% - 中 {cn10y:.2f}%)")
        if us10y and jp10y:
            print(f"  [宏观联动] 美日10Y利差: {us10y - jp10y:+.2f}% (美 {us10y:.2f}% - 日 {jp10y:.2f}%)")
        if us10y and de10y:
            print(f"  [宏观联动] 美德10Y利差: {us10y - de10y:+.2f}% (美 {us10y:.2f}% - 德 {de10y:.2f}%)")
    except Exception:
        pass
    print(f"{'─'*50}")

    # ============ 轨道2：Stress Overlay V2 (S0-S10) ============
    print(f"\n┌{'─'*58}┐\n│  【轨道2】Stress Overlay V2 (S0-S10)               │\n└{'─'*58}┘\n")
    stress = {}
    try:
        stress = stress_overlay_v2.evaluate_stress(asof)
        print(f"  当前压力状态: {stress['overall']}")
        print(f"  已触发层数: {stress['triggered_count']}/9")
        for l in stress['layers']:
            icon = '🚨' if l['triggered'] else '⏸️'
            print(f"  {icon} [{l['layer']}] {l['name']}")
    except Exception as e:
        print(f"  ⚠️ Stress异常: {e}")

    # ============ 轨道3：增强引擎 ============
    print(f"\n┌{'─'*58}┐\n│  【轨道3】多维度增强引擎                            │\n└{'─'*58}┘\n")

    # 🆕 Dollar_Anchor
    dollar_result = {}
    print(f"  [Dollar_Anchor] ", end='', flush=True)
    try:
        from engines_v3 import dollar_anchor
        with contextlib.redirect_stdout(io.StringIO()):
            dollar_result = dollar_anchor.compute_dollar_anchor(asof)
        print(f"{dollar_result.get('scenario_msg', 'N/A')}")
    except Exception as e:
        print(f"❌ {str(e)[:50]}")

    # 🆕 Chain E
    chain_e_result = {}
    print(f"  [Chain_E]       ", end='', flush=True)
    try:
        from engines_v3 import transmission_graph
        with contextlib.redirect_stdout(io.StringIO()):
            trans = transmission_graph.compute_transmission(asof)
        # 找 Chain E
        for c in trans.get('chains', []):
            if 'Chain E' in c.get('name', ''):
                chain_e_result = c
                break
        if chain_e_result:
            print(f"{chain_e_result.get('status', 'N/A')} (激活度={chain_e_result.get('activation', 0):.3f})")
        else:
            print("N/A")
    except Exception as e:
        print(f"❌ {str(e)[:50]}")

    # 🆕 CALI
    cali_result = {}
    print(f"  [CALI]          ", end='', flush=True)
    try:
        from engines_v3 import cali_engine
        with contextlib.redirect_stdout(io.StringIO()):
            cali_result = cali_engine.compute_cali(asof)
        print(f"{cali_result.get('cali_score', 0):.1f}/100 ({cali_result.get('level', 'N/A')})")
    except Exception as e:
        print(f"❌ {str(e)[:50]}")

    # 🆕 Crowding
    crowding_result = {}
    print(f"  [Crowding]      ", end='', flush=True)
    try:
        from engines_v3 import crowding_engine
        with contextlib.redirect_stdout(io.StringIO()):
            crowding_result = crowding_engine.compute_crowding(asof)
        print(f"{crowding_result.get('score', 0):.1f}/100 ({crowding_result.get('level', 'N/A')})")
    except Exception as e:
        print(f"❌ {str(e)[:50]}")

    # 其他（Positioning / Velocity / Probability / Contagion）
    for name, fn in [
        ('Positioning', lambda: __import__('engines_v3.positioning_engine', fromlist=['evaluate_positioning']).evaluate_positioning(asof)),
        ('Velocity', lambda: __import__('engines_v3.velocity_engine', fromlist=['evaluate_velocity']).evaluate_velocity(asof)),
        ('Probability', lambda: __import__('engines_v3.probability_engine', fromlist=['evaluate_probability']).evaluate_probability(asof)),
        ('Contagion', lambda: __import__('engines_v3.contagion_engine', fromlist=['compute_contagion']).compute_contagion(asof)),
    ]:
        print(f"  [{name:12s}] ", end='', flush=True)
        try:
            if name == 'Probability':
                r = fn()
                p_r4_r5_val = r['high_risk_prob']
                print(f"       ↳ 最终概率 P(R4+R5)={p_r4_r5_val*100:.4f}%")
            else:
                with contextlib.redirect_stdout(io.StringIO()):
                    r = fn()
                if name == 'Positioning':
                    print(f"Stress={r['positioning_stress']}/100 ({r['level']})")
                elif name == 'Velocity':
                    print(f"Breadth={r['breadth']['breadth_pct']}%")
                elif name == 'Contagion':
                    print(f"状态={r.get('status', 'N/A')}")
        except Exception as e:
            print(f"❌ {str(e)[:50]}")

    # ============ 轨道4：智能层（Fragility 已在预轨算过）============
    print(f"\n┌{'─'*58}┐\n│  【轨道4】GMRE 4.0 智能层                            │\n└{'─'*58}┘\n")

    cu_spread = get_series_meta('CU_SPREAD_PCT')[1]
    if cu_spread:
        if abs(cu_spread) > 2.0:
            print(f"  [CU Spread]  🚨 内外盘极值价差: {cu_spread:+.2f}% (逼仓风险)")
        else:
            print(f"  [CU Spread]  🟢 内外盘价差: {cu_spread:+.2f}% (正常)")

    print(f"  [CAPS Commodity] ", end='', flush=True)
    try:
        from engines_v3 import caps_engine
        with contextlib.redirect_stdout(io.StringIO()):
            cu = caps_engine.compute_caps_risk("SHFE_COPPER")
            al = caps_engine.compute_caps_risk("SHFE_ALUMINUM")
        output_parts = []
        if cu:
            output_parts.append(f"铜 {'🚨' if cu['caps_score'] > 60 else '🟡'} {cu['caps_score']}")
        if al:
            output_parts.append(f"铝 {'🚨' if al['caps_score'] > 60 else '🟡'} {al['caps_score']}")
        print(" | ".join(output_parts))
    except Exception as e:
        print(f"❌ {str(e)[:50]}")

    print(f"  [LTI Clearing]  ", end='', flush=True)
    try:
        from engines_v3 import lti_engine
        with contextlib.redirect_stdout(io.StringIO()):
            lti = lti_engine.compute_lti(asof)
        icon = "🚨" if lti.get('level') in ("EXTREME", "HIGH") else "🟡" if lti.get('level') == "MEDIUM" else "🟢"
        raw_data = lti.get('raw', {})
        fr_diff = raw_data.get('fr_cross_diff', 0.0)
        hl_imb = raw_data.get('hl_imbalance', 0.0)
        print(f"{icon} {lti.get('lti_score', 0)}/100 ({lti.get('level', 'UNKNOWN')}) | "
              f"FR差异 {fr_diff}% | 持仓24H变幅 {hl_imb:+.2f}%")
    except Exception as e:
        print(f"❌ {str(e)[:50]}")

    # ============ 尾轨 ============
    print(f"\n┌{'─'*58}┐\n│  【尾轨】尾部状态 + 预警 + 对冲                    │\n└{'─'*58}┘\n")
    try:
        tail = yen_carry_state.update_state(asof)
        print(f"  尾部状态: {tail['state']} | 风险预算调整: {tail['risk_budget_adj']*100:.0f}%")
    except Exception as e:
        print(f"  ⚠️ 尾部状态机异常: {e}")

    print()
    try:
        alert_result = liquidity_alert.check_alerts(asof)
        valid_alerts = [a for a in alert_result['alerts'] if a['type'] != 'RRP_DATA_UNAVAILABLE']
        if len(valid_alerts) == 0:
            print(f"  ✅ 流动性预警: 无异常")
        else:
            print(f"  ⚠️ 触发 {len(valid_alerts)} 条预警:")
            for a in valid_alerts:
                print(f"    [{a['level']}] {a['type']}: {a['msg'][:70]}")
    except Exception as e:
        print(f"  ⚠️ 流动性预警异常: {e}")

    print()
    try:
        dau = dau_alert.check_alerts(asof)
        if 'error' not in dau:
            print(f"  DAU Z-score: {dau['z_score']:+.3f} | 最新={dau['latest']:,}")
    except Exception as e:
        print(f"  ⚠️ DAU异常: {e}")

    print()
    try:
        hedge = hedge_advisor.compute_hedge(asof)
        hedge_pct = hedge.get('total_hedge_pct', 0.0) * 100
        if hedge_pct > 0:
            print(f"  🛡️ 建议对冲: {hedge_pct:.1f}%")
        else:
            print(f"  ✅ 尾部对冲: 无需求")
    except Exception as e:
        print(f"  ⚠️ 对冲模块异常: {e}")

    # ============ 防线 V4 ============
    print(f"\n┌{'─'*58}┐\n│  【执行】防线0-7                                    │\n└{'─'*58}┘\n")
    defense = {}
    try:
        defense = defense_v4.evaluate_v4(asof)
        print(f"  已突破防线: {defense['triggered_count']}/7 | "
              f"系统性危机: {'🚨 是' if defense['systemic_confirmed'] else '🟢 否'}\n")
        for l in defense['lines']:
            icon = '🚨' if l['triggered'] else '⏸️'
            print(f"  {icon} [{l['line']}] {l['name']}")
    except Exception as e:
        print(f"  ⚠️ 防线异常: {e}")

    # ============ 计算最终风险 ============
    contagion_status = 'NORMAL'
    gate, gate_msg = compute_risk_gate(
        frag_level,
        stress.get('overall', ''),
        contagion_status,
        stress.get('systemic_confirmed', False),
        p_r4_r5=p_r4_r5_val
    )

    print(f"\n┌{'─'*58}┐\n│  【最终】Risk Gate 风险等级                        │\n└{'─'*58}┘\n")
    print(f"  {gate_msg}")
    print(f"  Risk Gate: {gate}")

    # ============ 🆕 双阶段操作指南 ============
    dxy_pct = dollar_result.get('dxy_5y_pct') if dollar_result else None
    cali_score = cali_result.get('cali_score') if cali_result else None
    scenario = dollar_result.get('scenario', 'N/A') if dollar_result else 'N/A'
    try:
        phase_guide = get_dual_phase_guide(gate, frag_score_val, cali_score, scenario, dxy_pct)
        print(f"\n┌{'─'*58}┐\n│  【双阶段】当前所处阶段                            │\n└{'─'*58}┘\n")
        print(f"  {phase_guide['phase_emoji']} {phase_guide['phase']}")
        print(f"  💰 现金建议: {phase_guide['cash_recommendation']}")
        print(f"  🥇 黄金建议: {phase_guide['gold_recommendation']}")
        print(f"  💡 {phase_guide['note']}")
    except Exception as e:
        print(f"  ⚠️ 双阶段指南异常: {e}")

    _regime_display = "N/A"
    try:
        if p_r4_r5_val >= 0.50:
            _regime_display = f"R4/R5 (高危, P={p_r4_r5_val*100:.1f}%)"
        elif p_r4_r5_val >= 0.30:
            _regime_display = f"R3/R4 (警戒, P(R4+R5)={p_r4_r5_val*100:.1f}%)"
        elif regime:
            _regime_display = f"{regime.get('regime_label', 'N/A')} ({regime.get('confidence', 0)*100:.1f}%)"
    except Exception:
        pass

    _frag_display = frag_level if frag_level != 'N/A' else "N/A"

    print(f"\n{'='*60}")
    print(f"  GMRE 4.0 运行完成")
    print(f"  Base Regime: {_regime_display} | Fragility: {_frag_display} | Risk Gate: {gate}")
    print(f"{'='*60}\n")

    # ============ P0-B 落表 ============
    try:
        snapshot_str = json.dumps(input_snapshot, sort_keys=True)
        input_hash = hashlib.sha256(snapshot_str.encode('utf-8')).hexdigest()[:16]
        code_commit = get_git_commit()

        conn = sqlite3.connect(DB_PATH)
        conn.execute("""CREATE TABLE IF NOT EXISTS daily_summary (
            asof_date TEXT PRIMARY KEY, risk_gate TEXT, stress_state TEXT, frag_level TEXT)""")
        conn.execute("""INSERT OR REPLACE INTO daily_summary
            (asof_date, risk_gate, stress_state, frag_level) VALUES (?, ?, ?, ?)""",
            (asof, gate, stress.get('overall', 'NONE'), frag_level))

        conn.execute("""CREATE TABLE IF NOT EXISTS predictions_log (
            forecast_date TEXT PRIMARY KEY, model_version TEXT, code_commit TEXT,
            input_snapshot_hash TEXT, regime TEXT, p_r4_r5 REAL, fragility_score REAL,
            risk_gate TEXT, data_quality_state TEXT, details_json TEXT)""")
        details = {
            "regime": regime,
            "stress": stress.get('overall', 'NONE'),
            "fragility_level": frag_level,
            "gate_msg": gate_msg,
            "p_r4_r5": p_r4_r5_val,
            "dollar_anchor": dollar_result.get('scenario') if dollar_result else None,
            "cali_score": cali_result.get('cali_score') if cali_result else None,
            "crowding_score": crowding_result.get('score') if crowding_result else None,
            "data_audit": {"status": audit_status}
        }

        cursor = conn.cursor()
        cursor.execute("""INSERT OR IGNORE INTO predictions_log
            (forecast_date, model_version, code_commit, input_snapshot_hash, regime,
             p_r4_r5, fragility_score, risk_gate, data_quality_state, details_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (asof, 'GMRE_4.0', code_commit, input_hash, regime_label,
             p_r4_r5_val, frag_score_val, gate, audit_status,
             json.dumps(details, ensure_ascii=False)))

        if cursor.rowcount > 0:
            print(f"✅ [P0-B] 不可篡改预测日志已归档 (Hash: {input_hash})")
        else:
            print(f"⚠️ [P0-B] 今日预测日志已存在，拒绝覆盖。")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ [P0-B] 预测日志归档失败: {e}")


if __name__ == "__main__":
    main()