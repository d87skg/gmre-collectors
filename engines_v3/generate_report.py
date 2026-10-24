# -*- coding: utf-8 -*-
"""engines_v3/generate_report.py - 每日 GMRE 综合风控晨报生成器（防崩溃版）"""
import os
import sqlite3
from datetime import datetime

DB_PATH = 'data/macro.db'

def generate_report(asof: str):
    conn = sqlite3.connect(DB_PATH)
    
    # 1. 初始化默认值，防止 UnboundLocalError
    frag_score, frag_level = 0, "N/A"
    gate = "UNKNOWN"
    caps_cu, caps_al = 0, 0
    
    try:
        # 拉取 Fragility
        row = conn.execute("SELECT fragility_score, level FROM fragility_engine WHERE asof_date=?", (asof,)).fetchone()
        if row:
            frag_score, frag_level = row[0], row[1]
            
        # 拉取 Risk Gate
        row = conn.execute("SELECT risk_gate FROM daily_summary WHERE asof_date=?", (asof,)).fetchone()
        if row:
            gate = row[0]

        # 拉取 CAPS
        row = conn.execute("SELECT caps_score FROM caps_engine WHERE asof_date=? AND symbol='SHFE_COPPER'", (asof,)).fetchone()
        if row: caps_cu = row[0]
        row = conn.execute("SELECT caps_score FROM caps_engine WHERE asof_date=? AND symbol='SHFE_ALUMINUM'", (asof,)).fetchone()
        if row: caps_al = row[0]
        
    except Exception as e:
        print(f"  ⚠️ 读取数据库失败: {e}")
    finally:
        conn.close()

    report_dir = 'reports/daily'
    os.makedirs(report_dir, exist_ok=True)
    filepath = f"{report_dir}/gmre_daily_{asof}.md"
    
    content = f"""# GMRE 3.3 每日综合风控晨报 - {asof}

## 🚦 核心风险仪表盘
- **Risk Gate**: `{gate}`
- **Fragility**: `{frag_level} ({frag_score})`

## 📦 微观与商品结构监控 (CAPS)
- **沪铜逼仓评分**: {caps_cu}
- **沪铝逼仓评分**: {caps_al}

---
*本报告由 GMRE 3.3 自动生成，仅供投研参考，非交易建议。*
"""
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"  [Daily Report]       ✅ 已生成 {filepath}")