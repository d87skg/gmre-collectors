"""engines_v3/daily_intelligence.py - GMRE 4.0 每日情报报告（美元锚定+CALI+双阶段）"""
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
        regime = _load_col(conn, 'gms_regimes', 'regime_label', asof) or 'N/A'
        p_r4 = _load_col(conn, 'probability_engine', 'p_r4', asof)
        p_r5 = _load_col(conn, 'probability_engine', 'p_r5', asof)
        p_high = _load_col(conn, 'probability_engine', 'high_risk_prob', asof)
        frag_level = _load_col(conn, 'fragility_engine', 'level', asof)
        frag_score = _load_col(conn, 'fragility_engine', 'fragility_score', asof)
        stress_overall = _load_col(conn, 'stress_overlay_v2', 'overall', asof)
        stress_triggered = _load_col(conn, 'stress_overlay_v2', 'triggered_count', asof)
        stress_systemic = _load_col(conn, 'stress_overlay_v2', 'systemic_confirmed', asof)
        defense_count = _load_col(conn, 'defense_v4', 'triggered_count', asof)
        defense_systemic = _load_col(conn, 'defense_v4', 'systemic_confirmed', asof)

        # 🆕 GMRE 4.0 新引擎数据
        dxy_5y_pct = _load_col(conn, 'dollar_anchor', 'dxy_5y_pct', asof)
        dollar_scenario = _load_col(conn, 'dollar_anchor', 'scenario', asof)
        cali_score = _load_col(conn, 'cali_engine', 'cali_score', asof)
        cali_level = _load_col(conn, 'cali_engine', 'level', asof)
        crowding_score = _load_col(conn, 'crowding_engine', 'score', asof)
        crowding_level = _load_col(conn, 'crowding_engine', 'level', asof)
    finally:
        conn.close()

    lines = []
    lines.append("╔" + "═" * 70 + "╗")
    lines.append(f"║{'GMRE 4.0 DAILY INTELLIGENCE'.center(70)}║")
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
    lines.append("┌─ 【3】压力层 (S0-S10) " + "─" * 41)
    if stress_overall:
        lines.append(f"│ 当前状态: {stress_overall}")
    if stress_triggered is not None:
        lines.append(f"│ 已触发层数: {stress_triggered}/9")
    if stress_systemic:
        lines.append(f"│ 系统性危机: 🚨 已确认")
    else:
        lines.append(f"│ 系统性危机: 🟢 未确认")
    lines.append("└" + "─" * 62)
    lines.append("")

    # 4. 🆕 美元锚定区
    lines.append("┌─ 【4】美元锚定区 (Dollar Anchor) " + "─" * 33)
    if dxy_5y_pct is not None:
        lines.append(f"│ DXY 5y 分位: {dxy_5y_pct:.1f}%")
    scenario_map = {
        'RATE_CUT_FORCED': '🔴 降息倒逼路径',
        'HIGH_RATE_MAINTAINED': '🟢 高利率维持路径',
        'MIXED': '🟡 混合信号',
    }
    if dollar_scenario:
        lines.append(f"│ 情景: {scenario_map.get(dollar_scenario, dollar_scenario)}")
    lines.append("└" + "─" * 62)
    lines.append("")

    # 5. 🆕 CALI 流动性
    lines.append("┌─ 【5】CALI 流动性温度计 " + "─" * 39)
    if cali_score is not None:
        lines.append(f"│ CALI: {cali_score:.1f}/100 ({cali_level})")
    else:
        lines.append(f"│ CALI: N/A (未计算)")
    lines.append("└" + "─" * 62)
    lines.append("")

    # 6. 🆕 拥挤度
    lines.append("┌─ 【6】拥挤度 (Crowding) " + "─" * 38)
    if crowding_score is not None:
        lines.append(f"│ 拥挤度: {crowding_score:.1f}/100 ({crowding_level})")
    else:
        lines.append(f"│ 拥挤度: N/A (未计算)")
    lines.append("└" + "─" * 62)
    lines.append("")

    # 7. 防线
    lines.append("┌─ 【7】防线 (Defense) " + "─" * 42)
    if defense_count is not None:
        lines.append(f"│ 已突破: {defense_count}/7")
    if defense_systemic:
        lines.append(f"│ 系统性: 🚨 是")
    else:
        lines.append(f"│ 系统性: 🟢 否")
    lines.append("└" + "─" * 62)
    lines.append("")

    # 8. 🆕 双阶段判定
    lines.append("┌─ 【8】双阶段判定 (Dual Phase) " + "─" * 35)
    if cali_score is not None and cali_score >= 60:
        phase = '🔴 上半场（去杠杆中）'
        cash = '50-70%'
    elif dxy_5y_pct is not None and dxy_5y_pct < 10:
        phase = '🟠 上半场尾部（流动性枯竭末期）'
        cash = '50-70%'
    else:
        phase = '🟡 过渡期 / 🟢 下半场'
        cash = '40-60%'
    lines.append(f"│ 当前阶段: {phase}")
    lines.append(f"│ 建议现金: {cash}")
    lines.append("└" + "─" * 62)
    lines.append("")

    # 9. 最终 Risk Gate
    lines.append("┌─ 【9】最终风险等级 (Risk Gate) " + "─" * 32)
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

    os.makedirs('reports/daily', exist_ok=True)
    filename = f"reports/daily/gmre_daily_{asof}.txt"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(report)

    print(report)
    print(f"\n✅ 报告已保存至: {filename}")

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