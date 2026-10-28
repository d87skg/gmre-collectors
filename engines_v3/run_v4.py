"""engines_v3/run_v4.py - GMRE 3.3 完整集成版（防弹 + 宏观事件 + 完整轨道）"""
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

# 引入事件日历
try:
    from tools.check_events import check_upcoming_events
except ImportError:
    check_upcoming_events = lambda **kwargs: []

DB_PATH = 'data/macro.db'

def get_git_commit():
    try: return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=os.path.dirname(__file__)).decode('utf-8').strip()[:8]
    except: return "UNKNOWN"

def get_series_meta(sid):
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT timestamp, value FROM observations WHERE series_id=? ORDER BY timestamp DESC LIMIT 1", (sid,)).fetchone()
        conn.close()
        if row: return row[0].split(' ')[0].split('T')[0], float(row[1])
    except: pass
    return "N/A", None

def compute_risk_gate(frag_level, stress_overall, contagion_status, systemic_confirmed):
    """Risk Gate v4.1 - Fail-Closed 增强安全版"""
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
        
    if frag_score >= 80 or ('FUNDING' in stress_overall and 'CREDIT' in stress_overall):
        return 'RED', '🔴 高风险：多压力层共振'
    elif frag_score >= 65 or stress_overall.count('+') >= 1:
        return 'ORANGE', '🟠 中高风险：结构性脆弱'
    elif frag_score >= 50:
        return 'YELLOW', '🟡 中等：需监控'
    else:
        return 'GREEN', '🟢 低风险'

def main():
    asof = datetime.now().strftime('%Y-%m-%d')
    print(f"\n{'='*60}\n  GMRE 3.3 完整版 - {asof}\n{'='*60}\n")

    # ============ 事件日历 ============
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
        print(f"  {icon} 数据自检: {audit['status']} (通过{audit['pass_count']}/警告{audit['warn_count']}/严重{audit['critical_count']})")
    except Exception as e:
        print(f"  ⚠️ 数据自检异常: {e}")

    # ============ 轨道1 ============
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
    except Exception: pass
    try:
        fis_v2 = engine_fis_v2.compute_fis_v2(asof)
        print(f"  [FIS_V2] Composite={fis_v2['composite']:+.4f} | {fis_v2['direction']}")
    except Exception: pass
    try:
        inf_exp = engine_inf_expect.compute_engine(asof)
        if inf_exp.get('level') != 'MISSING_DATA': print(f"  [INF_EXPECT] Stress={inf_exp['inf_expect_stress']}/100 | {inf_exp['level']}")
    except Exception: pass

    print(f"\n{'-'*60}")
    regime = {}
    try:
        regime = regime_map.run(asof)
        if regime:
            regime_label = regime['regime_label']
            print(f"  GMS体制: {regime['regime_label']} ({regime['regime_name']})")
            print(f"  置信度: {regime['confidence']*100:.1f}%")
    except Exception as e: print(f"  ⚠️ GMS异常: {e}")

    # ============ 核心数据溯源 ============
    print(f"\n{'─'*50}\n  🔍 核心数据溯源 (Source & Definition)")
    audit_sids = [('RRP 余额', 'RRP_BALANCE', 'Billion USD'), ('10Y 收益率', 'YC10Y', '%'), ('HY 信用利差', 'HY_SPREAD', '%'), ('标普500', 'SP500', 'Index'), ('VIX', 'VIX', 'Index'), ('美元/日元', 'USD_JPY', 'Price'), ('中国10Y', 'CN_10Y_YIELD', '%'), ('日本10Y', 'JP_10Y', '%'), ('德国10Y', 'DE_10Y', '%')]
    input_snapshot = {}
    for name, sid, unit in audit_sids:
        d, v = get_series_meta(sid)
        if v is not None:
            print(f"    {name:12s}: {d} | 值 = {v:.4f} {unit}")
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
        if us10y and cn10y: print(f"  [宏观联动] 中美10Y利差: {us10y - cn10y:+.2f}% (美 {us10y:.2f}% - 中 {cn10y:.2f}%)")
        if us10y and jp10y: print(f"  [宏观联动] 美日10Y利差: {us10y - jp10y:+.2f}% (美 {us10y:.2f}% - 日 {jp10y:.2f}%)")
        if us10y and de10y: print(f"  [宏观联动] 美德10Y利差: {us10y - de10y:+.2f}% (美 {us10y:.2f}% - 德 {de10y:.2f}%)")
    except Exception: pass
    print(f"{'─'*50}")

    # ============ 轨道2：Stress Overlay V2 ============
    print(f"\n┌{'─'*58}┐\n│  【轨道2】Stress Overlay V2 (S0-S8)                │\n└{'─'*58}┘\n")
    stress = {}
    try:
        stress = stress_overlay_v2.evaluate_stress(asof)
        print(f"  当前压力状态: {stress['overall']}")
        print(f"  已触发层数: {stress['triggered_count']}/7")
        for l in stress['layers']:
            icon = '🚨' if l['triggered'] else '⏸️'
            print(f"  {icon} [{l['layer']}] {l['name']}")
    except Exception as e: print(f"  ⚠️ Stress异常: {e}")

    # ============ 轨道3：增强引擎 ============
    print(f"\n┌{'─'*58}┐\n│  【轨道3】多维度增强引擎                            │\n└{'─'*58}┘\n")
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
                if name == 'Positioning': print(f"Stress={r['positioning_stress']}/100 ({r['level']})")
                elif name == 'Velocity': print(f"Breadth={r['breadth']['breadth_pct']}%")
                elif name == 'Contagion': print(f"状态={r.get('status', 'N/A')}")
        except Exception as e: print(f"❌ {str(e)[:50]}")

    # ============ 轨道4：智能层 ============
    print(f"\n┌{'─'*58}┐\n│  【轨道4】GMRE 3.3 智能层                            │\n└{'─'*58}┘\n")
    frag_level = 'N/A'
    print(f"  [Fragility]    ", end='', flush=True)
    try:
        from engines_v3 import fragility_engine
        with contextlib.redirect_stdout(io.StringIO()):
            frag = fragility_engine.compute_fragility(asof)
        frag_level = f"{frag['level']} ({frag['fragility_score']})"
        frag_score_val = frag['fragility_score']
        print(frag_level)
    except Exception as e:
        print(f"❌ {str(e)[:50]}")
        frag_level = 'N/A'

    cu_spread = get_series_meta('CU_SPREAD_PCT')[1]
    if cu_spread:
        if abs(cu_spread) > 2.0: print(f"  [CU Spread]  🚨 内外盘极值价差: {cu_spread:+.2f}% (逼仓风险)")
        else: print(f"  [CU Spread]  🟢 内外盘价差: {cu_spread:+.2f}% (正常)")

    print(f"  [CAPS Commodity] ", end='', flush=True)
    try:
        from engines_v3 import caps_engine
        with contextlib.redirect_stdout(io.StringIO()):
            cu = caps_engine.compute_caps_risk("SHFE_COPPER")
            al = caps_engine.compute_caps_risk("SHFE_ALUMINUM")
        output_parts = []
        if cu: output_parts.append(f"铜 {'🚨' if cu['caps_score'] > 60 else '🟡'} {cu['caps_score']}")
        if al: output_parts.append(f"铝 {'🚨' if al['caps_score'] > 60 else '🟡'} {al['caps_score']}")
        print(" | ".join(output_parts))
    except Exception as e: print(f"❌ {str(e)[:50]}")

    # ============ LTI Clearing (加入兜底) ============
    print(f"  [LTI Clearing]  ", end='', flush=True)
    try:
        from engines_v3 import lti_engine
        with contextlib.redirect_stdout(io.StringIO()):
            lti = lti_engine.compute_lti(asof)
        icon = "🚨" if lti.get('level') in ("EXTREME", "HIGH") else "🟡" if lti.get('level') == "MEDIUM" else "🟢"
        
        # 核心修复：安全提取 raw 字典，防止空数据把主引擎带崩
        raw_data = lti.get('raw', {})
        fr_diff = raw_data.get('fr_cross_diff', 0.0)
        hl_imb = raw_data.get('hl_imbalance', 0.0)
        
        print(f"{icon} {lti.get('lti_score', 0)}/100 ({lti.get('level', 'UNKNOWN')}) | FR差异 {fr_diff}% | 持仓24H变幅 {hl_imb:+.2f}%")
    except Exception as e: print(f"❌ {str(e)[:50]}")

    # ============ 尾轨：风控 ============
    print(f"\n┌{'─'*58}┐\n│  【尾轨】尾部状态 + 预警 + 对冲                    │\n└{'─'*58}┘\n")
    try:
        tail = yen_carry_state.update_state(asof)
        print(f"  尾部状态: {tail['state']} | 风险预算调整: {tail['risk_budget_adj']*100:.0f}%")
    except Exception as e: print(f"  ⚠️ 尾部状态机异常: {e}")

    print()
    try:
        alert_result = liquidity_alert.check_alerts(asof)
        valid_alerts = [a for a in alert_result['alerts'] if a['type'] != 'RRP_DATA_UNAVAILABLE']
        if len(valid_alerts) == 0: print(f"  ✅ 流动性预警: 无异常")
        else:
            print(f"  ⚠️ 触发 {len(valid_alerts)} 条预警:")
            for a in valid_alerts: print(f"    [{a['level']}] {a['type']}: {a['msg'][:70]}")
    except Exception as e: print(f"  ⚠️ 流动性预警异常: {e}")

    print()
    try:
        dau = dau_alert.check_alerts(asof)
        if 'error' not in dau: print(f"  DAU Z-score: {dau['z_score']:+.3f} | 最新={dau['latest']:,}")
    except Exception as e: print(f"  ⚠️ DAU异常: {e}")

    print()
    try:
        hedge = hedge_advisor.compute_hedge(asof)
        hedge_pct = hedge.get('total_hedge_pct', 0.0) * 100
        if hedge_pct > 0: print(f"  🛡️ 建议对冲: {hedge_pct:.1f}%")
        else: print(f"  ✅ 尾部对冲: 无需求")
    except Exception as e: print(f"  ⚠️ 对冲模块异常: {e}")

    # ============ 防线 V4 ============
    print(f"\n┌{'─'*58}┐\n│  【执行】防线0-7                                    │\n└{'─'*58}┘\n")
    defense = {}
    try:
        defense = defense_v4.evaluate_v4(asof)
        print(f"  已突破防线: {defense['triggered_count']}/7 | 系统性危机: {'🚨 是' if defense['systemic_confirmed'] else '🟢 否'}\n")
        for l in defense['lines']:
            icon = '🚨' if l['triggered'] else '⏸️'
            print(f"  {icon} [{l['line']}] {l['name']}")
    except Exception as e: print(f"  ⚠️ 防线异常: {e}")

    # ============ 计算最终风险 ============
    contagion_status = 'NORMAL'
    gate, gate_msg = compute_risk_gate(
        frag_level, 
        stress.get('overall', ''), 
        contagion_status, 
        stress.get('systemic_confirmed', False)
    )

    print(f"\n┌{'─'*58}┐\n│  【最终】Risk Gate 风险等级                        │\n└{'─'*58}┘\n")
    print(f"  {gate_msg}")
    print(f"  Risk Gate: {gate}")

    _regime_display = f"{regime['regime_label']} ({regime['confidence']*100:.1f}%)" if 'regime' in locals() and regime else "N/A"
    _frag_display = frag_level if frag_level != 'N/A' else "N/A"

    print(f"\n{'='*60}")
    print(f"  GMRE 3.3 运行完成")
    print(f"  Base Regime: {_regime_display} | Fragility: {_frag_display} | Risk Gate: {gate}")
    print(f"{'='*60}\n")

    # ============ P0-B 落表 ============
    try:
        snapshot_str = json.dumps(input_snapshot, sort_keys=True)
        input_hash = hashlib.sha256(snapshot_str.encode('utf-8')).hexdigest()[:16]
        code_commit = get_git_commit()

        conn = sqlite3.connect(DB_PATH)
        conn.execute("""CREATE TABLE IF NOT EXISTS daily_summary (asof_date TEXT PRIMARY KEY, risk_gate TEXT, stress_state TEXT, frag_level TEXT)""")
        conn.execute("""INSERT OR REPLACE INTO daily_summary (asof_date, risk_gate, stress_state, frag_level) VALUES (?, ?, ?, ?)""", (asof, gate, stress.get('overall', 'NONE'), frag_level))

        conn.execute("""CREATE TABLE IF NOT EXISTS predictions_log (forecast_date TEXT PRIMARY KEY, model_version TEXT, code_commit TEXT, input_snapshot_hash TEXT, regime TEXT, p_r4_r5 REAL, fragility_score REAL, risk_gate TEXT, data_quality_state TEXT, details_json TEXT)""")
        details = {"regime": regime, "stress": stress.get('overall', 'NONE'), "fragility_level": frag_level, "gate_msg": gate_msg, "data_audit": {"status": audit_status}}

        cursor = conn.cursor()
        cursor.execute("""INSERT OR IGNORE INTO predictions_log (forecast_date, model_version, code_commit, input_snapshot_hash, regime, p_r4_r5, fragility_score, risk_gate, data_quality_state, details_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (asof, 'GMRE_3.3', code_commit, input_hash, regime_label, p_r4_r5_val, frag_score_val, gate, audit_status, json.dumps(details, ensure_ascii=False)))
        
        if cursor.rowcount > 0: print(f"✅ [P0-B] 不可篡改预测日志已归档 (Hash: {input_hash})")
        else: print(f"⚠️ [P0-B] 今日预测日志已存在，拒绝覆盖。")
        conn.commit()
        conn.close()
    except Exception as e: print(f"❌ [P0-B] 预测日志归档失败: {e}")

if __name__ == "__main__":
    main()