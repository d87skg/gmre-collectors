"""engines_v3/run_v3.py - GMRE 3.0 双轨架构主入口（静默增强引擎版）"""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import io
import contextlib
from datetime import datetime

# 复用 v2 的五引擎、体制映射、尾部状态机、预警、对冲、自检
from engines_v2 import (
    engine_liq, engine_inf, engine_mon, engine_risk, engine_fis,
    regime_map, yen_carry_state, liquidity_alert, hedge_advisor,
    data_quality_check, dau_alert
)

# 引入 v3 新模块
from engines_v3 import stress_overlay, defense_v3


def main():
    asof = datetime.now().strftime('%Y-%m-%d')
    print(f"\n{'='*60}")
    print(f"  GMRE 3.0 双轨架构 - {asof}")
    print(f"  Base Regime (R0-R5)  +  Stress Overlay (S0-S5)")
    print(f"{'='*60}\n")

    # ============ 轨道1：Base Regime ============
    print(f"┌{'─'*58}┐")
    print(f"│  【轨道1】Base Regime - 经济周期定位               │")
    print(f"└{'─'*58}┘\n")

    # 数据自检
    print(f"{'-'*60}")
    try:
        audit = data_quality_check.run_audit(asof)
        icon = {'PASS': '✅', 'WARN': '⚠️', 'FAIL': '❌'}.get(audit['status'], '?')
        print(f"  {icon} 数据自检: {audit['status']} "
              f"(通过{audit['pass_count']}/警告{audit['warn_count']}/严重{audit['critical_count']})")
    except Exception as e:
        print(f"  ⚠️ 数据自检异常: {e}")

    # 五引擎
    print(f"\n{'-'*60}")
    for mod in [engine_inf, engine_mon, engine_fis, engine_liq, engine_risk]:
        try:
            r = mod.compute_engine(asof)
            print(f"  [{r['engine_id']}] Z={r['z_score']:+.4f} | {r['direction']}")
        except Exception as e:
            print(f"  [{mod.ENGINE_ID}] ❌ 失败: {e}")

    # GMS体制
    print(f"\n{'-'*60}")
    try:
        regime = regime_map.run(asof)
        if regime:
            print(f"  GMS体制: {regime['regime_label']} ({regime['regime_name']})")
            print(f"  置信度: {regime['confidence']*100:.1f}%")
            print(f"  概率分布: {regime['regime_probs']}")
    except Exception as e:
        print(f"  ⚠️ GMS异常: {e}")

    # ============ 轨道2：Stress Overlay ============
    print(f"\n┌{'─'*58}┐")
    print(f"│  【轨道2】Stress Overlay - 跨资产传导链            │")
    print(f"└{'─'*58}┘\n")

    try:
        stress = stress_overlay.evaluate_stress(asof)
        print(f"  当前压力状态: {stress['overall']}")
        print(f"  已触发层数: {stress['triggered_count']}/5\n")
        for l in stress['layers']:
            icon = '🚨' if l['triggered'] else '⏸️'
            print(f"  {icon} [{l['layer']}] {l['name']}")
            print(f"      {l['description']}")
            for c in l['conditions']:
                mark = '✓' if c['met'] else '✗'
                print(f"        [{mark}] {c['name']}: {c['value']}")
    except Exception as e:
        print(f"  ⚠️ Stress Overlay异常: {e}")

    # ============ 轨道3：5个增强引擎（静默+汇总）============
    print(f"\n┌{'─'*58}┐")
    print(f"│  【轨道3】多维度增强引擎                            │")
    print(f"└{'─'*58}┘\n")

    # Positioning
    print(f"  [Positioning] ", end='', flush=True)
    try:
        from engines_v3 import positioning_engine
        with contextlib.redirect_stdout(io.StringIO()):
            pos = positioning_engine.evaluate_positioning(asof)
        print(f"Stress={pos['positioning_stress']}/100 ({pos['level']})")
    except Exception as e:
        print(f"❌ {str(e)[:50]}")

    # Velocity
    print(f"  [Velocity]    ", end='', flush=True)
    try:
        from engines_v3 import velocity_engine
        with contextlib.redirect_stdout(io.StringIO()):
            vel = velocity_engine.evaluate_velocity(asof)
        breadth = vel['breadth']['breadth_pct']
        corr = vel['correlation']['corr_60d'] if vel.get('correlation') else 'N/A'
        print(f"Breadth={breadth}%  股债相关性60D={corr}")
    except Exception as e:
        print(f"❌ {str(e)[:50]}")

    # Probability
    print(f"  [Probability] ", end='', flush=True)
    try:
        from engines_v3 import probability_engine
        with contextlib.redirect_stdout(io.StringIO()):
            prob = probability_engine.evaluate_probability(asof)
        print(f"P(R4+R5)={prob['high_risk_prob']*100:.2f}%")
    except Exception as e:
        print(f"❌ {str(e)[:50]}")

    # Contagion
    print(f"  [Contagion]   ", end='', flush=True)
    try:
        from engines_v3 import contagion_engine
        with contextlib.redirect_stdout(io.StringIO()):
            cont = contagion_engine.compute_contagion(asof)
        print(f"状态={cont.get('status', 'N/A')}")
    except Exception as e:
        print(f"❌ {str(e)[:50]}")

    # Scorecard
    print(f"  [Scorecard]   ", end='', flush=True)
    try:
        from engines_v3 import live_scorecard
        with contextlib.redirect_stdout(io.StringIO()):
            live_scorecard.record_scorecard(asof)
        print(f"✅ 已记录快照")
    except Exception as e:
        print(f"❌ {str(e)[:50]}")

    # ============ 尾轨：尾部风控 ============
    print(f"\n┌{'─'*58}┐")
    print(f"│  【尾轨】尾部状态 + 预警 + 对冲                    │")
    print(f"└{'─'*58}┘\n")

    # 尾部状态机
    print(f"{'-'*60}")
    try:
        tail = yen_carry_state.update_state(asof)
        print(f"  尾部状态: {tail['state']}")
        print(f"  风险预算调整: {tail['risk_budget_adj']*100:.0f}%")
        print(f"  对冲动作: {tail['hedge_action']}")
    except Exception as e:
        print(f"  ⚠️ 尾部状态机异常: {e}")

    # 流动性预警
    print(f"\n{'-'*60}")
    try:
        alert_result = liquidity_alert.check_alerts(asof)
        if alert_result['alert_count'] == 0:
            print(f"  ✅ 流动性预警: 无异常")
        else:
            print(f"  ⚠️ 触发 {alert_result['alert_count']} 条预警:")
            for a in alert_result['alerts']:
                print(f"    [{a['level']}] {a['type']}: {a['msg'][:80]}")
    except Exception as e:
        print(f"  ⚠️ 流动性预警异常: {e}")

    # DAU预警
    print(f"\n{'-'*60}")
    try:
        dau = dau_alert.check_alerts(asof)
        if 'error' not in dau:
            print(f"  DAU Z-score: {dau['z_score']:+.3f} | "
                  f"最新={dau['latest']:,} | 60日均值={dau['mean']:,}")
    except Exception as e:
        print(f"  ⚠️ DAU异常: {e}")

    # ============ 执行：防线矩阵 ============
    print(f"\n┌{'─'*58}┐")
    print(f"│  【执行】传导变量防线矩阵                          │")
    print(f"└{'─'*58}┘\n")

    try:
        defense = defense_v3.evaluate(asof)
        print(f"  总体: {defense['overall']}\n")
        for l in defense['lines']:
            icon = '🚨' if l['triggered'] else '⏸️'
            print(f"  {icon} [{l['line']}] {l['name']}: {l['indicator']}")
            print(f"      阈值: {l['threshold']}")
    except Exception as e:
        print(f"  ⚠️ 防线异常: {e}")

    # 对冲建议
    print(f"\n{'-'*60}")
    try:
        hedge = hedge_advisor.compute_hedge(asof)
        if hedge['action_count'] > 0:
            print(f"  🛡️ 建议对冲: {hedge['total_hedge_pct']*100:.1f}%")
            for a in hedge['actions']:
                print(f"    [{a['rule']}] {a['action']} ({a['size_pct']*100:.1f}%)")
        else:
            print(f"  ✅ 尾部对冲: 无需求")
    except Exception as e:
        print(f"  ⚠️ 对冲模块异常: {e}")

    print(f"\n{'='*60}")
    print(f"  ✅ GMRE 3.0 运行完成")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()