# -*- coding: utf-8 -*-
"""collect_cn_extended_v2.py - 中国数据全覆盖（修 USDCNH + CPI）"""
import sqlite3
from pathlib import Path
from datetime import datetime
import akshare as ak

DB = Path(r"D:\HGZC\data\macro.db")

def write(con, series_id, df, date_col, val_col):
    count = 0
    for _, row in df.iterrows():
        try:
            date = str(row[date_col])
            val = float(row[val_col])
        except (ValueError, KeyError):
            continue
        con.execute("""
            INSERT OR REPLACE INTO observations
            (series_id, timestamp, value, source, retrieved_at, availability_type)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (series_id, date, val, "akshare", datetime.now().isoformat(), "OBSERVED"))
        count += 1
    return count

con = sqlite3.connect(str(DB))

# ========== 1. 国债收益率 ==========
try:
    df = ak.bond_zh_us_rate(start_date="20260101")
    write(con, "CN_10Y_YIELD", df, "日期", "中国国债收益率10年")
    write(con, "CN_2Y_YIELD", df, "日期", "中国国债收益率2年")
    write(con, "US_10Y_YIELD_BOND", df, "日期", "美国国债收益率10年")
    print("[ok] 国债收益率")
except Exception as e:
    print(f"[fail] 国债: {e}")

# ========== 2. 汇率 ==========
try:
    # USD/CNY 中间价（新浪源）
    df = ak.currency_boc_sina(symbol="美元", start_date="20260101", end_date="20261231")
    write(con, "USDCNY_MID", df, "日期", "中行汇买价")
    print("[ok] USDCNY")
except Exception as e:
    print(f"[fail] USDCNY: {e}")

# ========== 3. LPR ==========
try:
    df = ak.macro_china_lpr()
    write(con, "CN_LPR_1Y", df, "TRADE_DATE", "LPR1Y")
    write(con, "CN_LPR_5Y", df, "TRADE_DATE", "LPR5Y")
    print("[ok] LPR")
except Exception as e:
    print(f"[fail] LPR: {e}")

# ========== 4. 社融 ==========
try:
    df = ak.macro_china_shrzgm()
    print("[ok] 社融")
except Exception as e:
    print(f"[fail] 社融: {e}")

# ========== 5. CPI ==========
try:
    df = ak.macro_china_cpi_yearly()
    write(con, "CN_CPI_YOY", df, "日期", "今值")
    print("[ok] CN CPI YoY")
except Exception as e:
    print(f"[fail] CN CPI: {e}")

# ========== 6. PPI ==========
try:
    df = ak.macro_china_ppi_yearly()
    write(con, "CN_PPI_YOY", df, "日期", "今值")
    print("[ok] CN PPI YoY")
except Exception as e:
    print(f"[fail] CN PPI: {e}")

# ========== 7. M1/M2 ==========
try:
    df = ak.macro_china_money_supply()
    write(con, "CN_M2_YOY", df, "月份", "M2同比")
    write(con, "CN_M1_YOY", df, "月份", "M1同比")
    print("[ok] M1/M2")
except Exception as e:
    print(f"[fail] M1/M2: {e}")

# ========== 8. 外储 ==========
try:
    df = ak.macro_china_fx_gold()
    write(con, "CN_FX_RESERVE", df, "月份", "外汇储备")
    print("[ok] 外储")
except Exception as e:
    print(f"[fail] 外储: {e}")

# ========== 9. PMI ==========
try:
    df = ak.macro_china_pmi()
    write(con, "CN_PMI_MFG", df, "月份", "制造业-指数")
    write(con, "CN_PMI_NONMFG", df, "月份", "非制造业-指数")
    print("[ok] PMI")
except Exception as e:
    print(f"[fail] PMI: {e}")

con.commit()
con.close()
print("done")