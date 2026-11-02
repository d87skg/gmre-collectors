# -*- coding: utf-8 -*-
"""collect_cn_extended.py - 补中国 P0/P1 数据"""
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

# 1. 中国国债收益率
try:
    df = ak.bond_zh_us_rate(start_date="20260101")
    n = write(con, "CN_10Y_YIELD", df, "日期", "中国国债收益率10年")
    print(f"[ok] CN_10Y_YIELD ({n})")
    n = write(con, "CN_2Y_YIELD", df, "日期", "中国国债收益率2年")
    print(f"[ok] CN_2Y_YIELD ({n})")
    n = write(con, "US_10Y_YIELD_BOND", df, "日期", "美国国债收益率10年")
    print(f"[ok] US_10Y_YIELD_BOND ({n})")
except Exception as e:
    print(f"[fail] CN bond: {e}")

# 2. 汇率
try:
    df = ak.fx_pair_quote(symbol="USDCNH")
    print(f"[ok] USDCNH")
except Exception as e:
    print(f"[fail] USDCNH: {e}")

# 3. LPR
try:
    df = ak.macro_china_lpr()
    n = write(con, "CN_LPR_1Y", df, "TRADE_DATE", "LPR1Y")
    print(f"[ok] CN_LPR_1Y ({n})")
    n = write(con, "CN_LPR_5Y", df, "TRADE_DATE", "LPR5Y")
    print(f"[ok] CN_LPR_5Y ({n})")
except Exception as e:
    print(f"[fail] LPR: {e}")

# 4. 社融 / M2
try:
    df = ak.macro_china_shrzgm()
    print(f"[ok] 社融")
except Exception as e:
    print(f"[fail] 社融: {e}")

# 5. CPI / PPI
try:
    df = ak.macro_china_cpi_monthly()
    print(f"[ok] CN CPI")
except Exception as e:
    print(f"[fail] CN CPI: {e}")

con.commit()
con.close()
print("done")