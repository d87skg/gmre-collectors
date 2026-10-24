"""engines_v3/daily_intelligence.py - VS7: 每日情报报告 [修复版]"""
import sqlite3
import json
import os
from datetime import datetime

DB_PATH = 'data/macro.db'


def _load_detail(conn, table, asof):
    try:
        r = conn.execute(f"SELECT detail FROM {table} WHERE asof_date=?", (asof,)).fetchone()
        return json.loads(r[0]) if r else None
    except Exception:
        return None


def _load_col(conn, table, col, asof):
    try:
        r = conn.execute(f"SELECT {col} FROM {table} WHERE asof_date=?", (asof,)).fetchone()
        return r[0] if r else None
    except Exception:
        return None


def generate_report(asof: str = None) -> str:
    if asof is None:
        asof = datetime.now().strftime('%Y-%m-%d')

    conn = sqlite3.connect(DB_PATH)
    try:
        # Regime
        regime = _load_col(conn, 'gms_regimes', 'regime_label', asof) or 'N/A'

        # Probability
        p_r4 = _load_col(conn, 'probability_engine', 'p_r4', asof)
        p_r5 = _load_col(conn, 'probability_engine', 'p_r5', asof)
        p_high = _load_col(conn, 'probability_engine', 'high_risk_prob', asof)

        # Fragility
        frag_level = _load_col(conn, 'fragility_engine', 'level', asof)
        frag_score = _load_col(conn, 'fragility_engine', 'fragility_score', asof)

        # Stress Overlay V2
        stress_overall = _load_col(conn, 'stress_overlay_v2', 'overall', asof)
        stress_triggered = _load_col(conn, 'stress_overlay_v2', 'triggered_count', asof)
        stress_systemic = _load_col(conn, 'stress_overlay_v2', 'systemic_confirmed', asof)

        # Shock（从独立列读取）
        shock_primary = _load_col(conn, 'shock_engine', 'primary_shock', asof)
        shock_intensity = _load_col(conn, 'shock_engine', 'primary_intensity', asof)
        shock_secondary = _load_col(conn, 'shock_engine', 'secondary_shock', asof)

        # Transmission（list格式）
        trans = _load_detail(conn, 'transmission_graph', asof)

        # Crisis Fingerprint（list格式）
        fingerprint = _load_detail(conn, 'crisis_fingerprint', asof)

        # Scenario Tree（dict格式）
        scenarios = _load_detail(conn, 'scenario_tree', asof)

        # Invalidation
        inval_status = _load_col(conn, 'invalidation_conditions', 'status', asof)
        inval_met = _load_col(conn, 'invalidation_conditions', 'met_count', asof)
        inval_total = _load_col(conn, 'invalidation_conditions', 'total_count', asof)

        # Defense
        defense_count = _load_col(conn, 'defense_v4', 'triggered_count', asof)
        defense_systemic = _load_col(conn, 'defense_v4', 'systemic_confirmed', asof)
        defense_detail = _load_detail(conn, 'defense_v4', asof)
    finally:
        conn.close()

    # ============ 生成报告 ============
    lines = []
    lines.append("╔" + "═" * 70 + "╗")
    lines.append(f"║{'GMRE 3.3 DAILY INTELLIGENCE'.center(70)}║")
    lines.append(f"║{asof.center(70)}║")
    lines.append("╚" + "═" * 70 + "╝")
    lines.append("")

    # 1. 宏观体制
    lines.append("┌─ 【1】宏观体制 (Macro Regime) " + "─" * 37)
    lines.append(f"│ Regime:   {regime}")
    if p_high is not None:
        lines.append(f"│ P(R4+R5): {p_high*100:.2f}%")
    if p_r4 is not None:
        lines.append(f"│ P(R4) =   {p_r4*100:.2f}%")
    if p_r5 is not None:
        lines.append(f"│ P(R5) =   {p_r5*100:.2f}%")
    lines.append("└" + "─" * 62)
    lines.append("")

    # 2. 脆弱性
    lines.append("┌─ 【2】脆弱性 (Fragility) " + "─" * 37)
    if frag_level:
        lines.append(f"│ Level: {frag_level}")
    if frag_score is not None:
        lines.append(f"│ Score: {frag_score:.1f}/100")
    lines.append("└" + "─" * 62)
    lines.append("")

    # 3. 压力层
    lines.append("┌─ 【3】压力层 (S0-S8) " + "─" * 41)
    if stress_overall:
        lines.append(f"│ 当前状态: {stress_overall}")
    if stress_triggered is not None:
        lines.append(f"│ 已触发层数: {stress_triggered}/7")
    if stress_systemic:
        lines.append(f"│ 系统性危机: 🚨 已确认")
    else:
        lines.append(f"│ 系统性危机: 🟢 未确认")
    lines.append("└" + "─" * 62)
    lines.append("")

    # 4. 主要冲击
    lines.append("┌─ 【4】主要冲击 (Shock) " + "─" * 39)
    if shock_primary:
        lines.append(f"│ Primary:   {shock_primary}" +
                     (f" (I={shock_intensity:.2f})" if shock_intensity else ""))
    if shock_secondary:
        lines.append(f"│ Secondary: {shock_secondary}")
    lines.append("└" + "─" * 62)
    lines.append("")

    # 5. 传导链
    lines.append("┌─ 【5】传导链 (Transmission Graph) " + "─" * 30)
    if trans and isinstance(trans, list):
        for chain in trans:
            status = chain.get('status', 'INACTIVE')
            if status in ['ACTIVE', 'ACCELERATING', 'EXTREME']:
                icon = {'ACTIVE': '🟠', 'ACCELERATING': '🔴', 'EXTREME': '🚨'}.get(status, '?')
                lines.append(f"│ {icon} {chain['name'][:52]}")
                lines.append(f"│     激活度={chain.get('activation', 0):.3f} ({status})")
        if not any(c.get('status') in ['ACTIVE', 'ACCELERATING', 'EXTREME'] for c in trans):
            lines.append(f"│ ⚪ 无主链激活")
    else:
        lines.append(f"│ N/A")
    lines.append("└" + "─" * 62)
    lines.append("")

    # 6. 历史指纹
    lines.append("┌─ 【6】历史指纹 (Top 3) " + "─" * 39)
    if fingerprint and isinstance(fingerprint, list):
        for r in fingerprint[:3]:
            lines.append(f"│ {r['crisis']:25s} {r['similarity']:.3f}")
    lines.append(f"│ ⚠️ 相似 ≠ 预测")
    lines.append("└" + "─" * 62)
    lines.append("")

    # 7. 情景树
    lines.append("┌─ 【7】情景树 (Scenario Tree) " + "─" * 35)
    if scenarios and isinstance(scenarios, dict):
        for key in ['BASE', 'UPSIDE', 'DOWNSIDE', 'TAIL']:
            s = scenarios.get(key, {})
            prob = s.get('probability', 0)
            name = s.get('name', key)
            trigger = s.get('trigger', '')[:40]
            lines.append(f"│ {name:8s} P={prob*100:5.1f}% | {trigger}")
    lines.append("└" + "─" * 62)
    lines.append("")

    # 8. 防线
    lines.append("┌─ 【8】4道防线 (Defense) " + "─" * 39)
    if defense_count is not None:
        lines.append(f"│ 已突破: {defense_count}/7")
    if defense_detail and isinstance(defense_detail, list):
        for l in defense_detail:
            if l.get('triggered'):
                lines.append(f"│ 🚨 {l['line']} {l['name']}")
    lines.append("└" + "─" * 62)
    lines.append("")

    # 9. 判断失效
    lines.append("┌─ 【9】判断失效条件 (Invalidation) " + "─" * 30)
    if inval_status:
        lines.append(f"│ 状态: {inval_status}")
    if inval_met is not None and inval_total is not None:
        lines.append(f"│ 满足: {inval_met}/{inval_total}")
    lines.append("└" + "─" * 62)
    lines.append("")

    # 10. 最终 Risk Gate
    lines.append("┌─ 【10】最终风险等级 (Risk Gate) " + "─" * 31)
    if defense_systemic:
        gate = 'BLACK'
        desc = '🚨 系统性危机已确认'
    elif frag_score and frag_score >= 80:
        gate = 'RED'
        desc = '🔴 高风险'
    elif frag_score and frag_score >= 65:
        gate = 'ORANGE'
        desc = '🟠 中高风险'
    elif frag_score and frag_score >= 50:
        gate = 'YELLOW'
        desc = '🟡 中等：需监控'
    else:
        gate = 'GREEN'
        desc = '🟢 低风险'
    lines.append(f"│ {desc}")
    lines.append(f"│ Risk Gate: {gate}")
    lines.append("└" + "─" * 62)
    lines.append("")

    lines.append("═" * 72)
    lines.append("免责声明: 本报告仅为宏观状态监测，不构成投资建议。")
    lines.append("═" * 72)

    report = "\n".join(lines)

    # 保存到文件
    os.makedirs('reports\\daily', exist_ok=True)
    filename = f"reports\\daily\\gmre_daily_{asof}.txt"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(report)

    print(report)
    print(f"\n✅ 报告已保存至: {filename}")

    # 落盘
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS daily_intelligence (
        asof_date TEXT PRIMARY KEY, report TEXT)""")
    conn.execute("""INSERT OR REPLACE INTO daily_intelligence
        (asof_date, report) VALUES (?, ?)""", (asof, report))
    conn.commit()
    conn.close()

    return report


if __name__ == "__main__":
    generate_report()