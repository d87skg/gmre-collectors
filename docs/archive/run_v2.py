"""engines_v2/run_v2.py - GMRE 2.2 完整版（含防御矩阵+SOFR监控）"""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

from engines_v2 import (
    engine_liq, engine_inf, engine_mon, engine_risk, engine_fis,
    regime_map, yen_carry_state, liquidity_alert, hedge_advisor,
    data_quality_check, dau_alert, defense_matrix, sofr_monitor
)


def main():
    asof = datetime.now().strftime('%Y-%m-%d')
    print(f"\n{'='*60}")
    print(f"  GMRE 2.2 系统运行 - {asof}")
    print(f"{'='*60}\n")

    # 0. 数据自检
    print(f"{'-'*60}")
    try:
        audit = data_quality_check.run_audit(asof)
        icon = {'PASS': '✅', 'WARN': '⚠️', 'FAIL': '❌'}.get(audit['status'], '?')
        print(f"  {icon} 数据自检: {audit['status']} "
              f"(通过{audit['pass_count']}/警告{audit['warn_count']}/严重{audit['critical_count']})")
    except Exception as e:
        print(f"  ⚠️ 数据自检异常: {e}")

    # 1. 五引擎
    print(f"\n{'-'*60}")
    for mod in [engine_inf, engine_mon, engine_fis, engine_liq, engine_risk]:
        try:
            r = mod.compute_engine(asof)
            print(f"  [{r['engine_id']}] Z={r['z_score']:+.4f} | {r['direction']}")
        except Exception as e:
            print(f"  [{mod.ENGINE_ID}] ❌ 失败: {e}")

    # 2. GMS体制
    print(f"\n{'-'*60}")
    try:
        regime = regime_map.run(asof)
        if regime:
            print(f"  GMS体制: {regime['regime_label']} ({regime['regime_name']})")
            print(f"  置信度: {regime['confidence']*100:.1f}%")
            print(f"  概率分布: {regime['regime_probs']}")
    except Exception as e:
        print(f"  ⚠️ GMS异常: {e}")

    # 3. 尾部状态机
    print(f"\n{'-'*60}")
    try:
        tail = yen_carry_state.update_state(asof)
        print(f"  尾部状态: {tail['state']}")
        print(f"  风险预算调整: {tail['risk_budget_adj']*100:.0f}%")
        print(f"  对冲动作: {tail['hedge_action']}")
    except Exception as e:
        print(f"  ⚠️ 尾部状态机异常: {e}")

    # 4. 流动性预警
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
        print(f"  ⚠️ 预警模块异常: {e}")

    # 5. DAU预警
    print(f"\n{'-'*60}")
    try:
        dau = dau_alert.check_alerts(asof)
        if 'error' in dau:
            print(f"  ℹ️ DAU: {dau['error']}")
        else:
            print(f"  DAU Z-score: {dau['z_score']:+.3f} | "
                  f"最新={dau['latest']:,} | 60日均值={dau['mean']:,}")
    except Exception as e:
        print(f"  ⚠️ DAU异常: {e}")

    # 6. SOFR vs EFFR 监控（新增）
    print(f"\n{'-'*60}")
    try:
        sofr = sofr_monitor.check_spread(asof)
        print(f"  {sofr['msg']}")
        if 'spread_now_bp' in sofr:
            print(f"  SOFR={sofr['sofr_latest']}%  EFFR={sofr['effr_latest']}%  "
                  f"利差={sofr['spread_now_bp']}bp")
    except Exception as e:
        print(f"  ⚠️ SOFR监控异常: {e}")

    # 7. 尾部对冲建议
    print(f"\n{'-'*60}")
    try:
        hedge = hedge_advisor.compute_hedge(asof)
        if hedge['action_count'] == 0:
            print(f"  ✅ 尾部对冲: 无需求")
        else:
            print(f"  🛡️ 建议对冲仓位合计: {hedge['total_hedge_pct']*100:.1f}%")
            for a in hedge['actions']:
                print(f"    [{a['rule']}] {a['action']} ({a['size_pct']*100:.1f}%)")
    except Exception as e:
        print(f"  ⚠️ 对冲模块异常: {e}")

    # 8. 4道防线矩阵（核心新增）
    print(f"\n{'='*60}")
    try:
        defense = defense_matrix.evaluate_defenses(asof)
        print(f"  🎯 4道防线: {defense['overall']}")
        print(f"  已突破: {defense['triggered_count']}/4\n")
        for d in defense['defenses']:
            icon = '🚨' if d['triggered'] else '⏸️'
            print(f"  {icon} [{d['line']}] {d['name']}: {d['indicator']}  (阈值: {d['threshold']})")
            if d['distance'] is not None and not d['triggered']:
                print(f"      距离触发: {d['distance']}")
    except Exception as e:
        print(f"  ⚠️ 防御矩阵异常: {e}")

    print(f"\n{'='*60}")
    print(f"  ✅ 全部完成，结果已写入 macro.db")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()