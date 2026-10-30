# -*- coding: utf-8 -*-
"""tools/data_sanitizer.py - 全局数据清洗漏斗（P2.5 强化版）"""
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


def sanitize_us_cpi_yoy(conn):
    """🆕 P2.5：US_CPI_YOY 语义不明，全面废弃
    原因：数据源存的是某个 CPI 子项（14.32%），不是"美国 CPI 同比"
    与 MICH_1Y=4.6% / T5YIE=2.47% 严重矛盾，且不参与任何核心引擎
    """
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
    """🆕 P2.5：US_10Y_YIELD_BOND 与 YC10Y 双源冲突，废弃 AKShare 版本
    原因：AKShare 的 5.27% vs Treasury 官方 YC10Y 的 5.05%，差 22bp
    YC10Y 才是真理源（DGS10 数据），AKShare 版本是重复污染
    """
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
    """🆕 P2.5：REVERSE_REPO_FRED 单位归一化
    原因：FRED 的 WLRRAL 序列是"百万美元"单位，与 NYFed 的"十亿美元"差 1000 倍
    统一换算成"十亿美元"，与 NYFed 一致
    """
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
            print(f"  ⚠️ [清洗] 找不到同日期的 FRED RRP 数据，跳过对齐")
    else:
        print(f"  ⚠️ [清洗] 找不到 NYFed RRP 数据，跳过对齐")


def main():
    print(f"\n{'='*60}")
    print(f"  🧼 GMRE 全局数据清洗漏斗 - {datetime.now().strftime('%Y-%m-%d')}")
    print(f"  （P2.5：废弃 3 个脏数据源 + 保留原有 4 项检查）")
    print(f"{'='*60}\n")
    
    conn = sqlite3.connect(DB_PATH, timeout=15)
    try:
        sanitize_usdcny(conn)
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