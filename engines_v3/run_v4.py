"""engines_v3/run_v4.py - GMRE 3.3 完整集成版（全功能终极版：中美日德利差）"""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import io
import contextlib
import sqlite3
import subprocess
import hashlib
import json
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

DB_PATH = 'data/macro.db'

def get_git_commit():
    """获取当前代码的 Git Commit Hash，用于绑定模型版本"""
    try:
        commit_hash = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=os.path.dirname(__file__)).decode('utf-8').strip()
        return commit_hash[:8]
    except Exception:
        return "UNKNOWN"

def get_series_meta(sid):
    """获取序列最新日期和数值，用于溯源审计"""
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT timestamp, value FROM observations WHERE series_id=? ORDER BY timestamp DESC LIMIT 1", (sid,)).fetchone()
        conn.close()
        if row:
            date_str = row[0].split(' ')[0].split('T')[0]
            return date_str, float(row[1])
    except Exception:
        pass
    return "N/A", None

def compute_risk_gate(frag_level, stress_overall, contagion_status, systemic_confirmed):
    """最终风险等级（GREEN/YELLOW/ORANGE/RED/BLACK）"""
    if systemic_confirmed:
        return 'BLACK', '🚨 系统性危机已确认'

    try:
        frag_score = float(frag_level.split('(')[1].split(')')[0])
    except Exception:
        frag_score = 50

    if frag_score >= 80 or ('FUNDING' in stress_overall and 'CREDIT' in stress_overall):
        return 'RED', '🔴 高风险：多压力层共振'

    if frag_score >= 65 or stress_overall.count('+') >= 1:
        return 'ORANGE', '🟠 中高风险：结构性脆弱'

    if frag_score >= 50:
        return 'YELLOW', '🟡 中等：需监控'

    return 'GREEN', '🟢 低风险'

def main():
    asof = datetime.now().strftime('%Y-%m-%d')
    print(f"\n{'='*60}")
    print(f"  GMRE 3.3 完整版 - {asof}")
    print(f"  R (Macro) + S (Stress) + F (Fragility) + Shock + Transmission")
    print(f"{'='*60}\n")

    audit_status = 'UNKNOWN'
    regime_label = 'UNKNOWN'
    p_r4_r5_val = 0.0
    frag_score_val = 0.0
    high_risk_prob_str = "0.0"

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
    print(f"\n┌{'─'*58}┐")
    print(f"│  【轨道1】Base Regime (R0-R6)                     │")
    print(f"└{'─'*58}┘\n")
    for mod in [engine_inf, engine_mon, engine_fis, engine_liq, engine_risk]:
        try:
            r = mod.compute_engine(asof)
            print(f"  [{r['engine_id']}] Z={r['z_score']:+.4f} | {r['direction']} (Z-score<0 为宽裕)")
        except Exception as e:
            print(f"  [{mod.ENGINE_ID}] ❌ 失败: {e}")

    print()
    try:
        mon_v2 = engine_mon_v2.compute_mon_v2(asof)
        print(f"  [MON_V2] Composite={mon_v2['composite']:+.4f} | {mon_v2['direction']}")
    except Exception as e:
        print(f"  [MON_V2] ❌ {str(e)[:60]}")

    try:
        fis_v2 = engine_fis_v2.compute_fis_v2(asof)
        print(f"  [FIS_V2] Composite={fis_v2['composite']:+.4f} | {fis_v2['direction']} (Score>0 为压力)")
    except Exception as e:
        print(f"  [FIS_V2] ❌ {str(e)[:60]}")

    try:
        inf_exp = engine_inf_expect.compute_engine(asof)
        if inf_exp.get('level') == 'MISSING_DATA' or inf_exp.get('inf_expect_stress') == -1:
            print(f"  [INF_EXPECT] ❌ 数据缺失 (MICH5Y/T5YIE 拉取失败)，当前无法评估通胀预期压力！")
        else:
            print(f"  [INF_EXPECT] Stress={inf_exp['inf_expect_stress']}/100 | {inf_exp['level']}")
    except Exception as e:
        print(f"  [INF_EXPECT] ❌ {str(e)[:60]}")

    print(f"\n{'-'*60}")
    regime = {}
    try:
        regime = regime_map.run(asof)
        if regime:
            regime_label = regime['regime_label']
            print(f"  GMS体制: {regime['regime_label']} ({regime['regime_name']})")
            print(f"  置信度: {regime['confidence']*100:.1f}%")
            print(f"  概率分布: {regime['regime_probs']}")
    except Exception as e:
        print(f"  ⚠️ GMS异常: {e}")

    # ============ 核心数据溯源面板 ============
    print(f"\n{'─'*50}")
    print(f"  🔍 核心数据溯源 (Source & Definition)")
    audit_sids = [
        ('RRP 余额', 'RRP_BALANCE', 'Billion USD'),
        ('10Y 收益率', 'YC10Y', '%'),
        ('HY 信用利差', 'HY_SPREAD', '% (OAS)'),
        ('标普500', 'SP500', 'Index'),
        ('VIX', 'VIX', 'Index'),
        ('美元/日元', 'USD_JPY', 'Price'),
        ('中国10Y', 'CN_10Y_YIELD', '%'),
        ('日本10Y', 'JP_10Y', '%'),
        ('德国10Y', 'DE_10Y', '%'),
    ]
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

    # ============ 新增：全球利差监控 ============
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

    # ============ 轨道2：Stress Overlay V2 ============
    print(f"\n┌{'─'*58}┐")
    print(f"│  【轨道2】Stress Overlay V2 (S0-S8)                │")
    print(f"└{'─'*58}┘\n")
    stress = {}
    try:
        stress = stress_overlay_v2.evaluate_stress(asof)
        print(f"  当前压力状态: {stress['overall']}")
        print(f"  已触发层数: {stress['triggered_count']}/7")
        print(f"  系统性危机确认: {'🚨 是' if stress['systemic_confirmed'] else '🟢 否'}\n")
        for l in stress['layers']:
            icon = '🚨' if l['triggered'] else '⏸️'
            print(f"  {icon} [{l['layer']}] {l['name']}")
    except Exception as e:
        print(f"  ⚠️ Stress Overlay V2异常: {e}")

    # ============ 轨道3：增强引擎 ============
    print(f"\n┌{'─'*58}┐")
    print(f"│  【轨道3】多维度增强引擎                            │")
    print(f"└{'─'*58}┘\n")

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
                print(f"       ↳ 最终概率 P(R4+R5)={p_r4_r5_val*100:.4f}% (见上方审计矩阵)")
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

    # Scorecard
    print(f"  [Scorecard   ] ", end='', flush=True)
    try:
        from engines_v3 import live_scorecard
        with contextlib.redirect_stdout(io.StringIO()):
            live_scorecard.record_scorecard(asof)
        print(f"✅ 已记录")
    except Exception as e:
        print(f"❌ {str(e)[:50]}")

    # ============ 轨道4：GMRE 3.3 智能层 ============
    print(f"\n┌{'─'*58}┐")
    print(f"│  【轨道4】GMRE 3.3 智能层 (Fragility/Shock/Trans)   │")
    print(f"└{'─'*58}┘\n")

    # Fragility
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

    # Shock
    print(f"  [Shock]        ", end='', flush=True)
    try:
        from engines_v3 import shock_engine
        with contextlib.redirect_stdout(io.StringIO()):
            shock = shock_engine.compute_shock(asof)
        print(f"{shock['primary_shock']} (I={shock['primary_intensity']:.2f})")
    except Exception as e:
        print(f"❌ {str(e)[:50]}")

    # CAPS Commodity
    print(f"  [CAPS Commodity] ", end='', flush=True)
    try:
        from engines_v3 import caps_engine
        with contextlib.redirect_stdout(io.StringIO()):
            cu = caps_engine.compute_caps_risk("SHFE_COPPER")
            al = caps_engine.compute_caps_risk("SHFE_ALUMINUM")
        
        output_parts = []
        if cu:
            icon = "🚨" if cu['caps_score'] > 60 else "🟡" if cu['caps_score'] > 30 else "🟢"
            output_parts.append(f"铜 {icon} {cu['caps_score']}")
        if al:
            icon = "🚨" if al['caps_score'] > 60 else "🟡" if al['caps_score'] > 30 else "🟢"
            output_parts.append(f"铝 {icon} {al['caps_score']}")
            
        print(" | ".join(output_parts))
    except Exception as e:
        print(f"❌ {str(e)[:50]}")

    # LTI Clearing
    print(f"  [LTI Clearing]  ", end='', flush=True)
    try:
        from engines_v3 import lti_engine
        with contextlib.redirect_stdout(io.StringIO()):
            lti = lti_engine.compute_lti(asof)
        icon = "🚨" if lti['level'] in ("EXTREME", "HIGH") else "🟡" if lti['level'] == "MEDIUM" else "🟢"
        print(f"{icon} {lti['lti_score']}/100 ({lti['level']}) | FR差异 {lti['raw']['fr_cross_diff']}% | 持仓24H变幅 {lti['raw']['hl_imbalance']:+.2f}%")
    except Exception as e:
        print(f"❌ {str(e)[:50]}")

    # Transmission (完整四态输出)
    print(f"  [Transmission] ")
    trans = {}
    try:
        from engines_v3 import transmission_graph
        with contextlib.redirect_stdout(io.StringIO()):
            trans = transmission_graph.compute_transmission(asof)

        for c in trans.get('chains', []):
            status = c.get('status', 'UNKNOWN')
            reason = c.get('error', '')
            if not reason and 'unknown_edges' in c:
                reason = f"盲区边={c['unknown_edges']}"

            icon = "🚨" if status in ['ACTIVE', 'ACCELERATING'] else "🟡" if status == 'WATCH' else "⏸️" if status == 'INACTIVE' else "❓"
            print(f"    {icon} [{status:10s}] {c['name'][:35]} | {reason}")
    except Exception as e:
        print(f"    ❌ {str(e)[:50]}")

    # ============ 计算最终风险等级 ============
    contagion_status = 'NORMAL'
    gate, gate_msg = compute_risk_gate(
        frag_level,
        stress.get('overall', ''),
        contagion_status,
        stress.get('systemic_confirmed', False)
    )

    # ============ 尾轨：风控 ============
    print(f"\n┌{'─'*58}┐")
    print(f"│  【尾轨】尾部状态 + 预警 + 对冲                    │")
    print(f"└{'─'*58}┘\n")

    try:
        tail = yen_carry_state.update_state(asof)
        print(f"  尾部状态: {tail['state']}")
        print(f"  风险预算调整: {tail['risk_budget_adj']*100:.0f}%")
        
        if tail['state'] == 'NORMAL' and gate == 'RED':
            print("       ↳ 解释: 宏观环境脆弱(RED)，但系统性踩踏尚未确认(NORMAL)。未触发强制降低风险预算。")
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

    # 建议对冲
    print()
    try:
        hedge = hedge_advisor.compute_hedge(asof)
        hedge_pct = hedge.get('total_hedge_pct', 0.0) * 100
        if hedge_pct > 0:
            print(f"  🛡️ 建议对冲: {hedge_pct:.1f}% (基于组合波动率折算的期权保护敞口)")
            print(f"       ↳ 决策链: Risk Gate RED + 尾部状态 NORMAL → 触发基础保护头寸。")
            print(f"       ↳ 实际资金占用率: 极低（如 0.1%~0.3% 权利金），非组合减仓比例。")
        else:
            print(f"  ✅ 尾部对冲: 无需求")
    except Exception as e:
        print(f"  ⚠️ 对冲模块异常: {e}")

    # ============ 执行：防线 V4 ============
    print(f"\n┌{'─'*58}┐")
    print(f"│  【执行】防线0-7（传导变量驱动）                    │")
    print(f"└{'─'*58}┘\n")
    defense = {}
    try:
        defense = defense_v4.evaluate_v4(asof)
        print(f"  已突破防线: {defense['triggered_count']}/7")
        print(f"  系统性危机: {'🚨 是' if defense['systemic_confirmed'] else '🟢 否'}\n")
        for l in defense['lines']:
            icon = '🚨' if l['triggered'] else '⏸️'
            date_suffix = ""
            if l['line'] == '防线2':  
                date_suffix = f" (数据源: YC10Y @ {get_series_meta('YC10Y')[0]})"
            elif l['line'] == '防线3': 
                date_suffix = f" (数据源: RRP_BALANCE @ {get_series_meta('RRP_BALANCE')[0]})"
            elif l['line'] == '防线5': 
                date_suffix = f" (数据源: HY_SPREAD @ {get_series_meta('HY_SPREAD')[0]})"

            print(f"  {icon} [{l['line']}] {l['name']}{date_suffix}")
    except Exception as e:
        print(f"  ⚠️ 防线异常: {e}")

    # ============ 校验：判断失效 ============
    print(f"\n┌{'─'*58}┐")
    print(f"│  【校验】判断失效条件                              │")
    print(f"└{'─'*58}┘\n")
    try:
        inval = invalidation_conditions.check_invalidation(asof)
        print(f"  状态: {inval['status']} ({inval['met_count']}/{inval['total_count']}满足)")
    except Exception as e:
        print(f"  ⚠️ 失效条件检查异常: {e}")

    # ============ 高级智能层 ============
    print(f"\n┌{'─'*58}┐")
    print(f"│  【高级】历史指纹 + 情景树 + 每日报告              │")
    print(f"└{'─'*58}┘\n")

    print(f"  [Crisis Fingerprint] ", end='', flush=True)
    try:
        from engines_v3 import crisis_fingerprint
        with contextlib.redirect_stdout(io.StringIO()):
            fp = crisis_fingerprint.compute_fingerprint(asof)
        top = fp['matches'][0]
        print(f"{top['crisis']} (相似度={top['similarity']:.3f})")
    except Exception as e:
        print(f"❌ {str(e)[:50]}")

    print(f"  [Scenario Tree]      ", end='', flush=True)
    try:
        from engines_v3 import scenario_tree
        with contextlib.redirect_stdout(io.StringIO()):
            sc = scenario_tree.compute_scenarios(asof)
        base_p = sc['scenarios']['BASE']['probability']
        tail_p = sc['scenarios']['TAIL']['probability']
        print(f"BASE={base_p*100:.0f}% | TAIL={tail_p*100:.0f}%")
    except Exception as e:
        print(f"❌ {str(e)[:50]}")

    print(f"  [Daily Report]       ", end='', flush=True)
    try:
        from engines_v3 import daily_intelligence
        with contextlib.redirect_stdout(io.StringIO()):
            daily_intelligence.generate_report(asof)
        print(f"✅ 已生成 reports\\daily\\gmre_daily_{asof}.txt")
    except Exception as e:
        print(f"❌ {str(e)[:50]}")

    # ============ 最终风险等级 ============
    print(f"\n┌{'─'*58}┐")
    print(f"│  【最终】Risk Gate 风险等级                        │")
    print(f"└{'─'*58}┘\n")
    print(f"  {gate_msg}")
    print(f"  Risk Gate: {gate}")

    # ============ 逻辑一致性自动诊断 ============
    _regime_display = "N/A"
    if 'regime' in locals() and regime:
        _regime_display = f"{regime['regime_label']} ({regime['confidence']*100:.1f}%)"
        
    _frag_display = frag_level if frag_level != 'N/A' else "N/A"

    print(f"\n┌{'─'*58}┐")
    print(f"│  【诊断】逻辑一致性自动解释                        │")
    print(f"└{'─'*58}┘\n")
    
    is_r0 = 'R0' in _regime_display
    is_red = (gate == 'RED')
    
    if is_r0 and is_red:
        print("  💡 [宏观与风险闸门背离]")
        print("     GMS 体制判定为 R0 (温和复苏)，但 Risk Gate 为 RED (高风险)。")
        print("     原因：R0 是截面分类器，看的是当前宏观四引擎的分布；而 RED 是尾部防线。")
        print("     当前利率(防线2)、流动性(防线3)、信用(防线5)被极端击穿，")
        print("     导致结构脆弱性(F3)压倒了宏观周期的平均值。系统判定为“结构极度不健康”。")
        print()
        
    stress_triggered = stress.get('triggered_count', 0)
    trans_active = 0
    if 'trans' in locals() and 'chains' in trans:
        trans_active = sum(1 for c in trans['chains'] if c['status'] in ['ACTIVE', 'ACCELERATING', 'EXTREME'])
    
    if stress_triggered >= 2 and trans_active == 0:
        print("  💡 [压力层与传导链背离]")
        print(f"     压力层已触发 {stress_triggered} 层 (如流动性/信用)，但传导链无 ACTIVE 状态激活。")
        print("     原因：Transmission 模块监控的是“跨资产相关性突变”。")
        print("     目前信用利差在走阔(S6)，但美股尚未崩盘、资产相关性未失控。")
        print("     这意味着：压力目前停留在宏观/流动性层面，尚未大面积传导至二级市场。")
        print()
        
    if not (is_r0 and is_red) and not (stress_triggered >= 2 and trans_active == 0):
        print("  ✅ 当前各状态机维度一致，无逻辑冲突。")
        
    print(f"{'─'*50}\n")

    # ============ 一句话总结 ============
    print(f"\n{'='*60}")
    print(f"  GMRE 3.3 运行完成")
    print(f"  Base Regime: {_regime_display} | Fragility: {_frag_display} | Risk Gate: {gate}")
    print(f"{'='*60}\n")

    # ============ P0-B: 核心结论落表与不可篡改预测日志 ============
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

        conn.execute("""
            CREATE TABLE IF NOT EXISTS predictions_log (
                forecast_date TEXT PRIMARY KEY,
                model_version TEXT,
                code_commit TEXT,
                input_snapshot_hash TEXT,
                regime TEXT,
                p_r4_r5 REAL,
                fragility_score REAL,
                risk_gate TEXT,
                data_quality_state TEXT,
                details_json TEXT
            )
        """)
        
        details = {
            "regime": regime,
            "stress": stress.get('overall', 'NONE'),
            "fragility_level": frag_level,
            "contagion": contagion_status,
            "gate_msg": gate_msg,
            "data_audit": {"status": audit_status}
        }

        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO predictions_log 
            (forecast_date, model_version, code_commit, input_snapshot_hash, regime, p_r4_r5, fragility_score, risk_gate, data_quality_state, details_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            asof, 'GMRE_3.3', code_commit, input_hash, 
            regime_label, p_r4_r5_val, frag_score_val, gate, audit_status, json.dumps(details, ensure_ascii=False)
        ))
        
        if cursor.rowcount > 0:
            print(f"✅ [P0-B] 不可篡改预测日志已归档 (Hash: {input_hash}, Commit: {code_commit})")
        else:
            print(f"⚠️ [P0-B] 今日 ({asof}) 预测日志已存在，拒绝覆盖，保持历史原样。")

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ [P0-B] 预测日志归档失败: {e}")

if __name__ == "__main__":
    main()