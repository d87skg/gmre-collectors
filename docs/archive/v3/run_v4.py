"""engines_v3/run_v4.py - GMRE 3.2 完整集成（审计对齐版）"""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import io
import contextlib
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


def main():
    asof = datetime.now().strftime('%Y-%m-%d')
    print(f"\n{'='*60}")
    print(f"  GMRE 3.2 完整版 - {asof}")
    print(f"  Base Regime + S0-S8 + 增强引擎 + 防线0-7")
    print(f"{'='*60}\n")

    # ============ 数据自检 ============
    print(f"{'-'*60}")
    try:
        audit = data_quality_check.run_audit(asof)
        icon = {'PASS': '✅', 'WARN': '⚠️', 'FAIL': '❌'}.get(audit['status'], '?')
        print(f"  {icon} 数据自检: {audit['status']} "
              f"(通过{audit['pass_count']}/警告{audit['warn_count']}/严重{audit['critical_count']})")
    except Exception as e:
        print(f"  ⚠️ 数据自检异常: {e}")

    # ============ 轨道1：Base Regime ============
    print(f"\n┌{'─'*58}┐")
    print(f"│  【轨道1】Base Regime - 经济周期定位               │")
    print(f"└{'─'*58}┘\n")
    for mod in [engine_inf, engine_mon, engine_fis, engine_liq, engine_risk]:
        try:
            r = mod.compute_engine(asof)
            print(f"  [{r['engine_id']}] Z={r['z_score']:+.4f} | {r['direction']}")
        except Exception as e:
            print(f"  [{mod.ENGINE_ID}] ❌ 失败: {e}")

    # 升级版 MON/FIS
    print()
    try:
        mon_v2 = engine_mon_v2.compute_mon_v2(asof)
        print(f"  [MON_V2] Composite={mon_v2['composite']:+.4f} | {mon_v2['direction']}")
    except Exception as e:
        print(f"  [MON_V2] ❌ {str(e)[:60]}")

    try:
        fis_v2 = engine_fis_v2.compute_fis_v2(asof)
        print(f"  [FIS_V2] Composite={fis_v2['composite']:+.4f} | {fis_v2['direction']}")
    except Exception as e:
        print(f"  [FIS_V2] ❌ {str(e)[:60]}")

    try:
        inf_exp = engine_inf_expect.compute_engine(asof)
        print(f"  [INF_EXPECT] Stress={inf_exp['inf_expect_stress']}/100 | {inf_exp['level']}")
    except Exception as e:
        print(f"  [INF_EXPECT] ❌ {str(e)[:60]}")

    # GMS
    print(f"\n{'-'*60}")
    try:
        regime = regime_map.run(asof)
        if regime:
            print(f"  GMS体制: {regime['regime_label']} ({regime['regime_name']})")
            print(f"  置信度: {regime['confidence']*100:.1f}%")
            print(f"  概率分布: {regime['regime_probs']}")
    except Exception as e:
        print(f"  ⚠️ GMS异常: {e}")

    # ============ 轨道2：Stress Overlay V2 ============
    print(f"\n┌{'─'*58}┐")
    print(f"│  【轨道2】Stress Overlay V2 (S0-S8)                │")
    print(f"└{'─'*58}┘\n")
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

    # ============ 轨道3：增强引擎（静默） ============
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
            with contextlib.redirect_stdout(io.StringIO()):
                r = fn()
            if name == 'Positioning':
                print(f"Stress={r['positioning_stress']}/100 ({r['level']})")
            elif name == 'Velocity':
                print(f"Breadth={r['breadth']['breadth_pct']}%")
            elif name == 'Probability':
                print(f"P(R4+R5)={r['high_risk_prob']*100:.2f}%")
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

    # ============ 尾轨：风控 ============
    print(f"\n┌{'─'*58}┐")
    print(f"│  【尾轨】尾部状态 + 预警 + 对冲                    │")
    print(f"└{'─'*58}┘\n")

    try:
        tail = yen_carry_state.update_state(asof)
        print(f"  尾部状态: {tail['state']}")
        print(f"  风险预算调整: {tail['risk_budget_adj']*100:.0f}%")
    except Exception as e:
        print(f"  ⚠️ 尾部状态机异常: {e}")

    print()
    try:
        alert_result = liquidity_alert.check_alerts(asof)
        if alert_result['alert_count'] == 0:
            print(f"  ✅ 流动性预警: 无异常")
        else:
            print(f"  ⚠️ 触发 {alert_result['alert_count']} 条预警:")
            for a in alert_result['alerts']:
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

    # ============ 执行：防线 V4 ============
    print(f"\n┌{'─'*58}┐")
    print(f"│  【执行】防线0-7（传导变量驱动）                    │")
    print(f"└{'─'*58}┘\n")
    try:
        defense = defense_v4.evaluate_v4(asof)
        print(f"  已突破防线: {defense['triggered_count']}/7")
        print(f"  系统性危机: {'🚨 是' if defense['systemic_confirmed'] else '🟢 否'}\n")
        for l in defense['lines']:
            icon = '🚨' if l['triggered'] else '⏸️'
            print(f"  {icon} [{l['line']}] {l['name']}")
    except Exception as e:
        print(f"  ⚠️ 防线异常: {e}")

    # ============ 判断失效条件 ============
    print(f"\n┌{'─'*58}┐")
    print(f"│  【校验】判断失效条件                              │")
    print(f"└{'─'*58}┘\n")
    try:
        inval = invalidation_conditions.check_invalidation(asof)
        print(f"  状态: {inval['status']} ({inval['met_count']}/{inval['total_count']}满足)")
    except Exception as e:
        print(f"  ⚠️ 失效条件检查异常: {e}")

    # 对冲建议
    print()
    try:
        hedge = hedge_advisor.compute_hedge(asof)
        if hedge['action_count'] > 0:
            print(f"  🛡️ 建议对冲: {hedge['total_hedge_pct']*100:.1f}%")
        else:
            print(f"  ✅ 尾部对冲: 无需求")
    except Exception as e:
        print(f"  ⚠️ 对冲模块异常: {e}")

    print(f"\n{'='*60}")
    print(f"  ✅ GMRE 3.2 运行完成")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()