# tools/backup_db.py
import sqlite3
import os

source_db = 'data/macro.db'
backup_db = r'D:\macro_SAFE_BACKUP_20261025.db'

print("⏳ 正在使用 SQLite 原生 API 备份数据库，请稍候...")
try:
    # 使用 sqlite3 原生 backup API，比 VACUUM INTO 更稳定，且能处理活动连接
    with sqlite3.connect(source_db) as src:
        with sqlite3.connect(backup_db) as dst:
            src.backup(dst)
    print(f"✅ 备份成功！文件已保存至: {backup_db}")
    print(f"文件大小: {os.path.getsize(backup_db) / 1024 / 1024:.2f} MB")
except Exception as e:
    print(f"❌ 备份失败: {e}")