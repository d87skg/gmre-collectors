# -*- coding: utf-8 -*-
"""tools/human_override.py - 人类否决权与治理记录"""
import sqlite3
from datetime import datetime

DB_PATH = 'data/macro.db'

def main():
    print(f"\n{'='*50}")
    print(f"  人类否决权 / 干预记录 - {datetime.now().strftime('%Y-%m-%d')}")
    print(f"{'='*50}")
    asof = datetime.now().strftime('%Y-%m-%d')
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""CREATE TABLE IF NOT EXISTS human_override (
            asof_date TEXT PRIMARY KEY, sys_gate TEXT, sys_action TEXT, 
            human_action TEXT, reason TEXT, logged_at TEXT)""")
        
        sys_gate = input("1. 系统建议的 Risk Gate (如 ORANGE): ").strip().upper()
        sys_action = input("2. 系统建议的操作 (如 减仓): ").strip()
        human_action = input("3. 你的实际操作 (如 未操作/加仓): ").strip()
        reason = input("4. 干预原因 (如 突发地缘/觉得跌透了): ").strip()
        
        conn.execute("""INSERT OR REPLACE INTO human_override
            (asof_date, sys_gate, sys_action, human_action, reason, logged_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            (asof, sys_gate, sys_action, human_action, reason))
        conn.commit()
        conn.close()
        print("\n✅ 记录已保存！这是未来系统进化的宝贵数据。")
    except Exception as e:
        print(f"❌ 记录失败: {e}")

if __name__ == '__main__':
    main()