"""engines_v3/run_v4.py - GMRE 3.3 完整集成版（终极防弹 + 宏观事件）"""
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
from tools.check_events import check_upcoming_events

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
    # 核心防御：如果 frag_level 解析失败、为 N/A、或者引擎崩溃，强制阻断 GREEN
    if frag_level == 'N/A' or frag_level is None:
        return 'UNKNOWN', '🚨 数据缺失：Fragility 状态无法计算'
        
    try:
        # 如果是旧格式字符串（例如 "F3_FRAGILE (60.5)"），进行解析
        frag_score = float(frag_level.split('(')[1].split(')')[0])
        if not math.isfinite(frag_score):
            return 'UNKNOWN', '🚨 数值异常：Fragility 得分为 NaN 或 Inf'
    except Exception:
        # 解析失败，直接进入 SAFE_MODE
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
    
    print("-" * 50)
    print("  📅 宏观事件倒计时检查")
    check_upcoming_events(config_path="config/events_calendar.yaml")
    print("-" * 50 + "\n")

    audit_status, regime_label, p_r4_r5_val, frag_score_val = 'UNKNOWN', 'UNKNOWN', 0.0, 0.0

    # 1. 轨道 1-3 引擎（略，保留你原本庞大的逻辑。此处不展开以省篇幅，你本地有完整版）
    # 请务必保留你本地原有的:
    # [轨道1] Base Regime 的循环
    # [轨道2] Stress Overlay V2
    # [轨道3] 多维度增强引擎
    
    # ... (保留你的原始代码逻辑) ...
    
    # 提取 Fragility 结果用于风控
    frag_level = 'N/A' 
    try:
        from engines_v3 import fragility_engine
        with contextlib.redirect_stdout(io.StringIO()):
            frag = fragility_engine.compute_fragility(asof)
        frag_level = f"{frag['level']} ({frag['fragility_score']})"
        frag_score_val = frag['fragility_score']
    except Exception as e:
        print(f"  ❌ [Fragility 崩溃] {str(e)[:50]}")
        # 注意：frag_level 保持 'N/A'，接下来风控会拦截
        frag_level = 'N/A'

    # ... (保留你本地的 CAPS, LTI, Transmission 代码) ...

    # 2. 最终风控
    contagion_status = 'NORMAL'
    # 这里调用了全新的 Fail-Closed 版本
    gate, gate_msg = compute_risk_gate(
        frag_level, 
        stress.get('overall', ''), 
        contagion_status, 
        stress.get('systemic_confirmed', False)
    )
    
    print(f"\n┌{'─'*58}┐\n│  【最终】Risk Gate 风险等级                        │\n└{'─'*58}┘\n")
    print(f"  {gate_msg}")
    print(f"  Risk Gate: {gate}")

    # 3. P0-B 日志落表
    # ... (保留你原有的逻辑) ...

if __name__ == "__main__":
    main()