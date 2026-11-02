"""tools/export_snapshot.py - GMRE 3.3 快照导出（供人工验证）
只读数据库，不修改任何核心代码
输出：reports/audit/gmre_snapshot_YYYY-MM-DD.md
"""
import sqlite3
import json
import os
from datetime import datetime

DB_PATH = 'D:/HGZC/data/macro.db'
OUT_DIR = 'D:/HGZC/reports/audit'


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _latest(table, cols='*'):
    conn = _conn()
    try:
        row = conn.execute(
            f"SELECT {cols} FROM {table} ORDER BY asof_date DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
    except Exception:
        return None
    finally:
        conn.close()


def _latest_obs(series_id):
    """最新观测值 + 时间戳"""
    conn = _conn()
    try:
        row = conn.execute("""
            SELECT timestamp, value, source FROM observations
            WHERE series_id = ? ORDER BY timestamp DESC LIMIT 1
        """, (series_id,)).fetchone()
        return dict(row) if row else None
    except Exception:
        return None
    finally:
        conn.close()


def export():
    asof = datetime.now().strftime('%Y-%m-%d')
    lines = []
    L = lines.append

    L(f"# GMRE 3.3 快照导出 - {asof}")
    L(f"\n导出时间: {datetime.now().isoformat()}\n")
    L("---\n")

    # ========== 1. 关键原始数据 ==========
    L("## 1. 关键原始数据（Observations 表）\n")
    L("| 序列ID | 最新值 | 时间戳 | 数据源 |")
    L("|:---|---:|:---|:---|")

    series_map = {
        'YC10Y': '10Y美债收益率(%)',
        'YC2Y': '2Y美债收益率(%)',
        'YC30Y': '30Y美债收益率(%)',
        'FEDFUNDS': '联邦基金利率(%)',
        'USD_JPY': 'USDJPY',
        'RRP_BALANCE': 'RRP余额($B)',
        'TGA_BALANCE': 'TGA余额($B)',
        'FED_WALCL': '美联储总资产($M)',
        'RESERVE_BALANCE': '银行准备金($M)',
        'SOFR': 'SOFR(%)',
        'EFFR': 'EFFR(%)',
        'HY_SPREAD': 'HY信用利差(%)',
        'VIX': 'VIX',
        'WTI_OIL': 'WTI原油($)',
        'BRENT_OIL': 'Brent原油($)',
        'SP500': 'S&P500',
        'DXY_PROXY': '美元指数',
        'CPIAUCSL': 'CPI季调',
        'MICH_1Y_EXPECT': '1Y通胀预期(%)',
        'JOBLESS_CLAIMS': '初请失业金',
        'UNEMPLOYMENT': '失业率(%)',
    }

    for sid, name in series_map.items():
        row = _latest_obs(sid)
        if row:
            L(f"| {sid} ({name}) | {row['value']:.4f} | {row['timestamp']} | {row['source']} |")
        else:
            L(f"| {sid} ({name}) | N/A | N/A | N/A |")

    L("")

    # ========== 2. Base Regime ==========
    L("## 2. Base Regime（宏观周期）\n")
    regime = _latest('gms_regimes')
    if regime:
        L(f"- **Regime**: {regime.get('regime_label')} ({regime.get('regime_name')})")
        L(f"- **置信度**: {regime.get('confidence')}")
        L(f"- **概率分布**: {regime.get('regime_probs')}")
    else:
        L("- 无数据")
    L("")

    # ========== 3. 5引擎 Z-score ==========
    L("## 3. 5引擎 Z-score（最新）\n")
    L("| 引擎 | Z-score | 方向 | 组件 |")
    L("|:---|---:|:---|:---|")

    conn = _conn()
    try:
        rows = conn.execute("""
            SELECT engine_id, z_score, direction, components
            FROM engine_latents
            WHERE asof_date = (SELECT MAX(asof_date) FROM engine_latents)
        """).fetchall()
        for r in rows:
            L(f"| {r['engine_id']} | {r['z_score']:.4f} | {r['direction']} | {r['components']} |")
    finally:
        conn.close()
    L("")

    # ========== 4. Stress Overlay ==========
    L("## 4. Stress Overlay V2 (S0-S8)\n")
    stress = _latest('stress_overlay_v2')
    if stress:
        L(f"- **当前状态**: {stress.get('overall')}")
        L(f"- **已触发层数**: {stress.get('triggered_count')}/7")
        L(f"- **系统性危机**: {stress.get('systemic_confirmed')}")
        detail = stress.get('detail')
        if detail:
            layers = json.loads(detail)
            L("\n| 层级 | 名称 | 触发 | 条件 |")
            L("|:---:|:---|:---:|:---|")
            for l in layers:
                conds = "; ".join([f"{c['name']}={c['value']}" for c in l.get('conditions', [])])
                L(f"| {l['layer']} | {l['name']} | {'🚨' if l['triggered'] else '⏸️'} | {conds} |")
    else:
        L("- 无数据")
    L("")

    # ========== 5. Fragility ==========
    L("## 5. Fragility Engine (F0-F5)\n")
    frag = _latest('fragility_engine')
    if frag:
        L(f"- **Level**: {frag.get('level')}")
        L(f"- **Score**: {frag.get('fragility_score')}")
        L(f"- **Base Fragility**: {frag.get('base_fragility')}")
        L(f"- **Amplification**: {frag.get('amplification')}")
        detail = frag.get('detail')
        if detail:
            dims = json.loads(detail)
            L("\n| 维度 | 得分 | 权重 | 组件 |")
            L("|:---|---:|---:|:---|")
            for name, d in dims.items():
                comp = d.get('components', {})
                L(f"| {name} | {d.get('score', 0):.1f} | {d.get('weight', 0)*100:.0f}% | {comp} |")
    else:
        L("- 无数据")
    L("")

    # ========== 6. Shock Engine ==========
    L("## 6. Shock Engine\n")
    shock = _latest('shock_engine')
    if shock:
        L(f"- **Primary**: {shock.get('primary_shock')} (I={shock.get('primary_intensity')})")
        L(f"- **Secondary**: {shock.get('secondary_shock')}")
        detail = shock.get('detail')
        if detail:
            shocks = json.loads(detail)
            L("\n| 冲击类型 | 强度 | 速度 | 持续性 |")
            L("|:---|---:|---:|---:|")
            for s in shocks:
                L(f"| {s['shock_type']} | {s['intensity']:.3f} | {s.get('velocity', 0):.3f} | {s.get('persistence', 0):.3f} |")
    else:
        L("- 无数据")
    L("")

    # ========== 7. Transmission Graph ==========
    L("## 7. Transmission Graph\n")
    trans = _latest('transmission_graph')
    if trans:
        chains = json.loads(trans.get('detail', '[]'))
        L("| 主链 | 状态 | 激活度 | 完备度 | 边详情 |")
        L("|:---|:---:|---:|---:|:---|")
        for c in chains:
            edges_str = "; ".join([f"{e['edge']}={e['activation']:.2f}" for e in c.get('edges', [])])
            L(f"| {c['name'][:40]} | {c['status']} | {c.get('activation', 0):.3f} | {c.get('completeness', 0):.3f} | {edges_str} |")
    else:
        L("- 无数据")
    L("")

    # ========== 8. Probability ==========
    L("## 8. Probability Engine\n")
    prob = _latest('probability_engine')
    if prob:
        L(f"- P(R0)={prob.get('p_r0')}, P(R1)={prob.get('p_r1')}, P(R2)={prob.get('p_r2')}")
        L(f"- P(R3)={prob.get('p_r3')}, P(R4)={prob.get('p_r4')}, P(R5)={prob.get('p_r5')}")
        L(f"- P(R4+R5) = {prob.get('high_risk_prob')}")
    else:
        L("- 无数据")
    L("")

    # ========== 9. Defense V4 ==========
    L("## 9. Defense 0-7\n")
    defense = _latest('defense_v4')
    if defense:
        L(f"- **已突破**: {defense.get('triggered_count')}/7")
        L(f"- **系统性**: {defense.get('systemic_confirmed')}")
        detail = defense.get('detail')
        if detail:
            lines_d = json.loads(detail)
            L("\n| 防线 | 名称 | 触发 | 条件 |")
            L("|:---:|:---|:---:|:---|")
            for l in lines_d:
                conds = "; ".join([f"{c[0]}={'✓' if c[1] else '✗'}({c[2]})" for c in l.get('conditions', [])])
                L(f"| {l['line']} | {l['name']} | {'🚨' if l['triggered'] else '⏸️'} | {conds} |")
    else:
        L("- 无数据")
    L("")

    # ========== 10. Crisis Fingerprint ==========
    L("## 10. Crisis Fingerprint\n")
    fp = _latest('crisis_fingerprint')
    if fp:
        fingerprints = json.loads(fp.get('detail', '[]'))
        L("| 历史危机 | 相似度 | 机制 |")
        L("|:---|---:|:---|")
        for f in fingerprints[:5]:
            L(f"| {f['crisis']} | {f['similarity']:.3f} | {f.get('mechanism', '')} |")
    else:
        L("- 无数据")
    L("")

    # ========== 11. Scenario Tree ==========
    L("## 11. Scenario Tree\n")
    sc = _latest('scenario_tree')
    if sc:
        scenarios = json.loads(sc.get('detail', '{}'))
        for key in ['BASE', 'UPSIDE', 'DOWNSIDE', 'TAIL']:
            s = scenarios.get(key, {})
            L(f"### {s.get('name', key)} - P={s.get('probability', 0)*100:.1f}%")
            L(f"- 触发: {s.get('trigger', '')}")
            L(f"- 传导: {s.get('transmission', '')}")
            L(f"- 目标 Regime: {s.get('expected_regime', '')}")
            L(f"- 失效条件: {s.get('invalidation', '')}")
            L("")
    else:
        L("- 无数据")
    L("")

    # ========== 12. Tail States ==========
    L("## 12. Tail State (CARRY)\n")
    tail = _latest('tail_states')
    if tail:
        L(f"- **State**: {tail.get('state')}")
        L(f"- **风险预算**: {tail.get('risk_budget_adj')}")
        L(f"- **对冲动作**: {tail.get('hedge_action')}")
        L(f"- **指标**: {tail.get('metrics')}")
    L("")

    # ========== 13. Liquidity Alerts ==========
    L("## 13. Liquidity Alerts\n")
    conn = _conn()
    try:
        alerts = conn.execute("""
            SELECT level, alert_type, message, metric FROM liquidity_alerts
            WHERE asof_date = (SELECT MAX(asof_date) FROM liquidity_alerts)
        """).fetchall()
        if alerts:
            L("| 等级 | 类型 | 消息 |")
            L("|:---|:---|:---|")
            for a in alerts:
                L(f"| {a['level']} | {a['alert_type']} | {a['message']} |")
        else:
            L("- 无预警")
    finally:
        conn.close()
    L("")

    # ========== 14. MON_V2 / FIS_V2 ==========
    L("## 14. 升级引擎详情\n")
    mon = _latest('engine_mon_v2')
    if mon:
        L(f"**MON_V2**: {mon.get('composite')} ({mon.get('direction')})")
        L(f"- 组件: {mon.get('detail')}")
    fis = _latest('engine_fis_v2')
    if fis:
        L(f"\n**FIS_V2**: {fis.get('composite')} ({fis.get('direction')})")
        L(f"- 组件: {fis.get('detail')}")
    L("")

    # ========== 15. Prediction Log ==========
    L("## 15. Prediction Log (校准记录)\n")
    conn = _conn()
    try:
        rows = conn.execute("""
            SELECT asof_date, regime, p_high_risk, fragility_level, risk_gate
            FROM prediction_log ORDER BY asof_date DESC LIMIT 10
        """).fetchall()
        if rows:
            L("| 日期 | Regime | P(R4+R5) | Fragility | Gate |")
            L("|:---|:---:|---:|:---|:---:|")
            for r in rows:
                L(f"| {r['asof_date']} | {r['regime']} | {r['p_high_risk']} | {r['fragility_level']} | {r['risk_gate']} |")
    finally:
        conn.close()
    L("")

    L("---\n")
    L(f"**导出完成** | 数据源: D:/HGZC/data/macro.db")

    # 保存
    os.makedirs(OUT_DIR, exist_ok=True)
    filename = f"{OUT_DIR}/gmre_snapshot_{asof}.md"
    content = "\n".join(lines)
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"✅ 快照已导出: {filename}")
    print(f"\n{'='*60}")
    print(f"  文件路径: {filename}")
    print(f"  文件行数: {len(lines)}")
    print(f"  文件大小: {len(content)} 字符")
    print(f"{'='*60}\n")

    return filename


if __name__ == "__main__":
    export()