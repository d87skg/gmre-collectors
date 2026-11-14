# -*- coding: utf-8 -*-
"""tools/data_sanitizer.py - 全局数据清洗漏斗（P2.5 强化版 + v4.1 适配）"""
import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = 'data/macro.db'


def sanitize_usdcny(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM observations WHERE series_id='USDCNY_MID' AND value > 10")
    count = cursor.fetchone()[0]
    if count > 0:
        cursor.execute("UPDATE observations SET value = value / 100.0 WHERE series_id='USDCNY_MID' AND value > 10")
        conn.commit()
        print(f"  🧼 [清洗] USDCNY_MID 量纲修复: 修正了 {count} 条记录")
    else:
        print(f"  ✅ [清洗] USDCNY_MID 量纲正常")


def sanitize_gold_history(conn):
    """🆕 清洗黄金数据的混合时间戳与多源重复（适配新表虚拟列）"""
    cursor = conn.cursor()
    try:
        # 1. 新表 obs_ts 是真实列，timestamp 是虚拟列不可写入。
        # 直接删除带 'T' 的脏记录，让 data_correction 重新拉取纯日期数据
        cursor.execute("DELETE FROM observations WHERE series_id='GOLD_PRICE' AND obs_ts LIKE '%T%'")
        t_deleted = cursor.rowcount
        
        # 2. 兜底去重：如果截断后同一天还有多条，只保留最新 rowid
        cursor.execute("""
            DELETE FROM observations 
            WHERE series_id='GOLD_PRICE' 
              AND rowid NOT IN (
                  SELECT MAX(rowid) FROM observations 
                  WHERE series_id='GOLD_PRICE' 
                  GROUP BY obs_date
              )
        """)
        dups_deleted = cursor.rowcount
        
        # 3. 剔除异常值
        cursor.execute("DELETE FROM observations WHERE series_id='GOLD_PRICE' AND (value < 1000 OR value > 10000)")
        outliers_deleted = cursor.rowcount
        
        conn.commit()
        print(f"  ✅ [清洗] GOLD_PRICE 修复: 删除带T记录 {t_deleted} 条 | 兜底去重 {dups_deleted} 条 | 剔除异常 {outliers_deleted} 条")
    except Exception as e:
        print(f"  ⚠️ 黄金清洗失败: {e}")
        conn.rollback()


def sanitize_us_cpi_yoy(conn):
    cursor = conn.cursor()
    cursor.execute("DELETE FROM observations WHERE series_id='US_CPI_YOY'")
    count = cursor.rowcount
    if count > 0:
        conn.commit()
        print(f"  🧼 [清洗] US_CPI_YOY 废弃清理: 删除了 {count} 条记录")
    else:
        print(f"  ✅ [清洗] US_CPI_YOY 已废弃（无残留）")


def sanitize_us_10y_yield_bond(conn):
    cursor = conn.cursor()
    cursor.execute("DELETE FROM observations WHERE series_id='US_10Y_YIELD_BOND'")
    count = cursor.rowcount
    if count > 0:
        conn.commit()
        print(f"  🧼 [清洗] US_10Y_YIELD_BOND 废弃清理: 删除了 {count} 条记录")
    else:
        print(f"  ✅ [清洗] US_10Y_YIELD_BOND 已废弃（无残留）")


def sanitize_reverse_repo_fred(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM observations WHERE series_id='REVERSE_REPO_FRED' AND value > 1000")
    count = cursor.fetchone()[0]
    if count > 0:
        cursor.execute("UPDATE observations SET value = value / 1000.0 WHERE series_id='REVERSE_REPO_FRED' AND value > 1000")
        conn.commit()
        print(f"  🧼 [清洗] REVERSE_REPO_FRED 单位修复: 修正了 {count} 条记录")
    else:
        print(f"  ✅ [清洗] REVERSE_REPO_FRED 单位正常")


def sanitize_hy_weekend(conn):
    cursor = conn.cursor()
    # 🆕 使用 obs_date 判断周末
    cursor.execute("""
        DELETE FROM observations 
        WHERE series_id IN ('HY_SPREAD', 'VIX', 'SP500', 'WTI_OIL', 'GOLD_PRICE') 
        AND (strftime('%w', obs_date) = '0' OR strftime('%w', obs_date) = '6')
    """)
    deleted = cursor.rowcount
    if deleted > 0:
        conn.commit()
        print(f"  🧼 [清洗] 周末脏数据清理: 移除了 {deleted} 条非交易日记录")
    else:
        print(f"  ✅ [清洗] 周末数据干净")


def align_rrp_source(conn):
    cursor = conn.cursor()
    # 统一使用 obs_ts 查询
    cursor.execute("SELECT obs_ts, value FROM observations WHERE series_id='RRP_NYFED' ORDER BY obs_ts DESC LIMIT 1")
    nyfed_row = cursor.fetchone()
    
    if nyfed_row:
        nyfed_date, nyfed_val = nyfed_row
        obs_date = nyfed_date[:10]
        cursor.execute("SELECT value FROM observations WHERE series_id='RRP_BALANCE' AND obs_ts=?", (nyfed_date,))
        fred_row = cursor.fetchone()
        
        if fred_row:
            fred_val = fred_row[0]
            if abs(fred_val - nyfed_val) / nyfed_val > 0.15:
                cursor.execute("UPDATE observations SET value=? WHERE series_id='RRP_BALANCE' AND obs_ts=?", (nyfed_val, nyfed_date))
                conn.commit()
                print(f"  🧼 [清洗] RRP 真理源对齐: 强制将 FRED ({fred_val:.2f}) 修正为 NYFed ({nyfed_val:.2f})")
            else:
                print(f"  ✅ [清洗] RRP 数据源偏差在合理范围内")
        else:
            cursor.execute("""
                INSERT OR REPLACE INTO observations (series_id, obs_ts, obs_date, value, source, ingest_at)
                VALUES ('RRP_BALANCE', ?, ?, ?, 'NYFED_SYNC', datetime('now'))
            """, (nyfed_date, obs_date, nyfed_val))
            conn.commit()
            print(f"  🧼 [清洗] RRP 真理源对齐: FRED 缺失，已强行缝合 NYFed ({nyfed_val:.2f}) 至 RRP_BALANCE")
    else:
        print(f"  ⚠️ [清洗] 找不到 NYFed RRP 数据，跳过对齐")


def main():
    print(f"\n{'='*60}")
    print(f"  🧼 GMRE 全局数据清洗漏斗 - {datetime.now().strftime('%Y-%m-%d')}")
    print(f"{'='*60}\n")
    
    conn = sqlite3.connect(DB_PATH, timeout=15)
    try:
        sanitize_usdcny(conn)
        sanitize_gold_history(conn)
        sanitize_us_cpi_yoy(conn)
        sanitize_us_10y_yield_bond(conn)
        sanitize_reverse_repo_fred(conn)
        sanitize_hy_weekend(conn)
        align_rrp_source(conn)
    except Exception as e:
        print(f"❌ 清洗过程发生严重异常: {e}")
    finally:
        conn.close()
        
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()