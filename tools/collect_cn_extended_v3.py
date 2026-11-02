# -*- coding: utf-8 -*-
"""collect_cn_extended_v3.py - 中国数据扩展（AKShare）"""
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB = Path(r"D:\HGZC\data\macro.db")

def write(con, series_id, df, date_col, val_col, source="akshare"):
    count = 0
    for _, row in df.iterrows():
        try:
            date = str(row[date_col])
            val = float(row[val_col])
        except (ValueError, KeyError, TypeError):
            continue
        con.execute("""
            INSERT OR REPLACE INTO observations
            (series_id, timestamp, value, source, retrieved_at, availability_type)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (series_id, date, val, source,
              datetime.now(timezone.utc).isoformat(), "OBSERVED"))
        count += 1
    return count

def main():
    import akshare as ak
    con = sqlite3.connect(str(DB))

    tasks = [
        # (series_id, 函数, date_col, val_col)
        ("CN_CPI_YOY",   lambda: ak.macro_china_cpi_yearly(),   "日期", "今值"),
                ("CN_PPI_YOY",   lambda: ak.macro_china_ppi(),          "月份", "当月同比增长"),
        ("CN_PMI_MFG",   lambda: ak.macro_china_pmi_yearly(),   "日期", "今值"),
        ("CN_FX_RESERVE",lambda: ak.macro_china_fx_gold(),      "月份", "黄金储备-数值"),
    ]

    for series_id, fetch_fn, date_col, val_col in tasks:
        try:
            df = fetch_fn()
            n = write(con, series_id, df, date_col, val_col)
            print(f"[ok] {series_id}: {n} rows")
        except Exception as e:
            print(f"[fail] {series_id}: {e}")

        # M1/M2 单独处理（正确列名）
    try:
        df = ak.macro_china_money_supply()
        m2_col = "货币和准货币(M2)-同比增长"
        m1_col = "货币(M1)-同比增长"
        if m2_col in df.columns:
            n = write(con, "CN_M2_YOY", df, "月份", m2_col)
            print(f"[ok] CN_M2_YOY: {n} rows")
        if m1_col in df.columns:
            n = write(con, "CN_M1_YOY", df, "月份", m1_col)
            print(f"[ok] CN_M1_YOY: {n} rows")
    except Exception as e:
        print(f"[fail] M1/M2: {e}")

    con.commit()
    con.close()
    print("done")

if __name__ == "__main__":
    main()