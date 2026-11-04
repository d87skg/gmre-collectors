# -*- coding: utf-8 -*-
"""tools/data_sanitizer.py - 全局数据清洗漏斗（P2.5 强化版 + 黄金数据清洗）"""
import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = 'data/macro.db'


def sanitize_usdcny(conn):
    """修复 USDCNY 量纲放大问题 (例如 669.33 -> 6.6933)"""
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
    """🆕 清洗黄金数据的混合时间戳与多源重复
    原因：历史数据混入了 2026-10-22T00:13:00 等带时间戳的数据，
    且截断时容易触发 (series_id, timestamp) 唯一约束冲突。
    """
    cursor = conn.cursor()
    try:
        # 1. 删除冲突项：带 T 的记录如果对应的纯日期已存在，直接删掉带 T 的
        cursor.execute("""
            DELETE FROM observations 
            WHERE series_id='GOLD_PRICE' 
              AND timestamp LIKE '%T%'
              AND substr(timestamp, 1, 10) IN (
                  SELECT timestamp FROM observations 
                  WHERE series_id='GOLD_PRICE' AND timestamp NOT LIKE '%T%'
              )
        """)
        conflict_deleted = cursor.rowcount

        # 2. 现在剩下的带 T 的记录，可以安全截断了
        cursor.execute("""
            UPDATE observations 
            SET timestamp = substr(timestamp, 1, 10) 
            WHERE series_id='GOLD_PRICE' AND timestamp LIKE '%T%'
        """)
        t_fixed = cursor.rowcount
        
        # 3. 兜底去重：如果截断后同一天还有多条（比如两条都带 T），只保留最新 rowid
        cursor.execute("""
            DELETE FROM observations 
            WHERE series_id='GOLD_PRICE' 
              AND rowid NOT IN (
                  SELECT MAX(rowid) FROM observations 
                  WHERE series_id='GOLD_PRICE' 
                  GROUP BY substr(timestamp, 1, 10)
              )
        """)
        dups_deleted = cursor.rowcount
        
        # 4. 剔除异常值（比如小于 1000 或大于 10000 的脏数据）
        cursor.execute("""
            DELETE FROM observations 
            WHERE series_id='GOLD_PRICE' AND (value < 1000 OR value > 10000)
        """)
        outliers_deleted = cursor.rowcount
        
        conn.commit()
        print(f"  ✅ [清洗] GOLD_PRICE 修复: 解决冲突 {conflict_deleted} 条 | 时间戳截断 {t_fixed} 条 | 兜底去重 {dups_deleted} 条 | 剔除异常 {outliers_deleted} 条")
    except Exception as e:
        print(f"  ⚠️ 黄金清洗失败: {e}")
        conn.rollback()


def sanitize_us_cpi_yoy(conn):
    """🆕 P2.5：US_CPI_YOY 语义不明，全面废弃"""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM observations WHERE series_id='US_CPI_YOY'")
    count = cursor.fetchone()[0]
    if count > 0:
        cursor.execute("DELETE FROM observations WHERE series_id='US_CPI_YOY'")
        conn.commit()
        print(f"  🧼 [清洗] US_CPI_YOY 废弃清理: 删除了 {count} 条语义不明的记录")
    else:
        print(f"  ✅ [清洗] US_CPI_YOY 已废弃（无残留）")


def sanitize_us_10y_yield_bond(conn):
    """🆕 P2.5：US_10Y_YIELD_BOND 与 YC10Y 双源冲突，废弃 AKShare 版本"""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM observations WHERE series_id='US_10Y_YIELD_BOND'")
    count = cursor.fetchone()[0]
    if count > 0:
        cursor.execute("DELETE FROM observations WHERE series_id='US_10Y_YIELD_BOND'")
        conn.commit()
        print(f"  🧼 [清洗] US_10Y_YIELD_BOND 废弃清理: 删除了 {count} 条与 YC10Y 冲突的记录")
    else:
        print(f"  ✅ [清洗] US_10Y_YIELD_BOND 已废弃（无残留）")


def sanitize_reverse_repo_fred(conn):
    """🆕 P2.5：REVERSE_REPO_FRED 单位归一化 (百万美元->十亿美元)"""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM observations WHERE series_id='REVERSE_REPO_FRED' AND value > 1000")
    count = cursor.fetchone()[0]
    if count > 0:
        cursor.execute("UPDATE observations SET value = value / 1000.0 WHERE series_id='REVERSE_REPO_FRED' AND value > 1000")
        conn.commit()
        print(f"  🧼 [清洗] REVERSE_REPO_FRED 单位修复: 修正了 {count} 条记录（百万美元→十亿美元）")
    else:
        print(f"  ✅ [清洗] REVERSE_REPO_FRED 单位正常")


def sanitize_hy_weekend(conn):
    """清理 HY_SPREAD 和 VIX 等周末的非交易时段数据（保留空值）"""
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM observations 
        WHERE series_id IN ('HY_SPREAD', 'VIX', 'SP500', 'WTI_OIL', 'GOLD_PRICE') 
        AND (strftime('%w', timestamp) = '0' OR strftime('%w', timestamp) = '6')
    """)
    deleted = cursor.rowcount
    if deleted > 0:
        conn.commit()
        print(f"  🧼 [清洗] 周末脏数据清理: 移除了 {deleted} 条非交易日记录")
    else:
        print(f"  ✅ [清洗] 周末数据干净")


def align_rrp_source(conn):
    """解决 RRP 双源打架：强制以 NYFed 为唯一真源，修正 FRED 数据"""
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, value FROM observations WHERE series_id='RRP_NYFED' ORDER BY timestamp DESC LIMIT 1")
    nyfed_row = cursor.fetchone()
    
    if nyfed_row:
        nyfed_date, nyfed_val = nyfed_row
        cursor.execute("SELECT value FROM observations WHERE series_id='RRP_BALANCE' AND timestamp=?", (nyfed_date,))
        fred_row = cursor.fetchone()
        
        if fred_row:
            fred_val = fred_row[0]
            if abs(fred_val - nyfed_val) / nyfed_val > 0.15:
                cursor.execute("UPDATE observations SET value=? WHERE series_id='RRP_BALANCE' AND timestamp=?", (nyfed_val, nyfed_date))
                conn.commit()
                print(f"  🧼 [清洗] RRP 真理源对齐: 强制将 FRED ({fred_val:.2f}) 修正为 NYFed ({nyfed_val:.2f})")
            else:
                print(f"  ✅ [清洗] RRP 数据源偏差在合理范围内")
        else:
            # 如果飞书数据没过来，直接把 NYFed 的数据同步给 RRP_BALANCE，防止其他引擎瞎眼
            cursor.execute("""
                INSERT OR REPLACE INTO observations (series_id, timestamp, value, source, retrieved_at)
                VALUES ('RRP_BALANCE', ?, ?, 'NYFED_SYNC', datetime('now'))
            """, (nyfed_date, nyfed_val))
            conn.commit()
            print(f"  🧼 [清洗] RRP 真理源对齐: FRED 缺失，已强行缝合 NYFed ({nyfed_val:.2f}) 至 RRP_BALANCE")
    else:
        print(f"  ⚠️ [清洗] 找不到 NYFed RRP 数据，跳过对齐")


def main():
    print(f"\n{'='*60}")
    print(f"  🧼 GMRE 全局数据清洗漏斗 - {datetime.now().strftime('%Y-%m-%d')}")
    print(f"  （P2.5：废弃 3 个脏数据源 + 黄金时间戳去重 + 原有 4 项检查）")
    print(f"{'='*60}\n")
    
    conn = sqlite3.connect(DB_PATH, timeout=15)
    try:
        sanitize_usdcny(conn)
        sanitize_gold_history(conn)        # 🆕 新增：黄金时间戳统一与去重
        sanitize_us_cpi_yoy(conn)          # 🆕 P2.5
        sanitize_us_10y_yield_bond(conn)   # 🆕 P2.5
        sanitize_reverse_repo_fred(conn)   # 🆕 P2.5
        sanitize_hy_weekend(conn)
        align_rrp_source(conn)
    except Exception as e:
        print(f"❌ 清洗过程发生严重异常: {e}")
    finally:
        conn.close()
        
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()