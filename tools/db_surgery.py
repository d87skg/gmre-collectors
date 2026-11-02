# tools/db_surgery.py
import sqlite3
import time

db_path = 'data/macro.db'
print(f"🏥 开始对 {db_path} 进行手术...")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 1. 统计
cursor.execute("SELECT COUNT(*) FROM observation_vintages")
before_count = cursor.fetchone()[0]
print(f"📊 去重前行数: {before_count:,} 行")

# 2. 执行去重
print("⏳ 正在清理重复数据（保留最新），预计耗时 1-3 分钟，请勿强制关闭...")
start_time = time.time()

cursor.execute("""
    DELETE FROM observation_vintages
    WHERE rowid NOT IN (
        SELECT MAX(rowid) FROM observation_vintages
        GROUP BY series_id, observed_at, vintage_date
    )
""")
conn.commit()
print(f"✅ 去重完成！耗时: {time.time() - start_time:.2f} 秒")

# 3. 添加唯一约束，防止未来再次膨胀
print("⏳ 正在添加唯一索引防膨胀锁...")
cursor.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS ux_vintages
    ON observation_vintages(series_id, observed_at, vintage_date)
""")
conn.commit()
print("✅ 索引建立成功！")

# 4. 统计
cursor.execute("SELECT COUNT(*) FROM observation_vintages")
after_count = cursor.fetchone()[0]
print(f"📊 去重后行数: {after_count:,} 行 (清理了 {before_count - after_count:,} 条冗余)")

# 5. 压缩物理文件（VACUUM）
print("⏳ 正在执行 VACUUM 压缩物理文件，请稍候...")
cursor.execute("VACUUM")
conn.commit()

conn.close()
print("🎉 手术完成！主库已彻底瘦身并加上防膨胀锁！")