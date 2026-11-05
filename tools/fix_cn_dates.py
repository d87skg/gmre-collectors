# -*- coding: utf-8 -*-
"""tools/fix_cn_dates.py - 清洗数据库中含中文的时间戳（解决唯一约束冲突）"""
import sqlite3
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
DB_PATH = 'data/macro.db'

def fix_dates():
    print("🔄 开始扫描并清洗包含中文的时间戳...")
    try:
        conn = sqlite3.connect(DB_PATH, timeout=15)
        cursor = conn.cursor()

        # 查找所有带有“年”字的时间戳
        cursor.execute("SELECT rowid, series_id, timestamp FROM observations WHERE timestamp LIKE '%年%'")
        rows = cursor.fetchall()
        
        if not rows:
            print("✅ 没有发现任何包含中文的时间戳，数据库很干净。")
            return

        print(f"找到 {len(rows)} 条包含中文的脏数据。开始转换...")
        
        to_delete = []
        to_update = []
        
        for rowid, series_id, ts in rows:
            # 提取 "2008年01月份" 中的 年和月
            match = re.search(r'(\d{4})年(\d{1,2})月', ts)
            if match:
                year = match.group(1)
                month = match.group(2).zfill(2)
                new_ts = f"{year}-{month}-01"
                
                # 检查库里是否已经存在同系列、同日期的新格式数据
                cursor.execute("SELECT 1 FROM observations WHERE series_id=? AND timestamp=?", (series_id, new_ts))
                if cursor.fetchone():
                    # 如果已经存在，说明这条中文格式的数据是多余的，直接删掉
                    to_delete.append((rowid,))
                else:
                    # 如果不存在，安全地更新
                    to_update.append((new_ts, rowid))
        
        # 执行删除
        if to_delete:
            cursor.executemany("DELETE FROM observations WHERE rowid = ?", to_delete)
            print(f"🧹 发现冲突，已清理 {len(to_delete)} 条重复的旧格式数据。")
            
        # 执行更新
        if to_update:
            cursor.executemany("UPDATE observations SET timestamp = ? WHERE rowid = ?", to_update)
            print(f"✅ 成功修复了 {len(to_update)} 条时间戳格式。")
            
        conn.commit()
        print("🎉 全部清洗完成！")
            
    except Exception as e:
        print(f"❌ 清洗失败: {e}")
        conn.rollback()
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    fix_dates()