# -*- coding: utf-8 -*-
"""tools/clean_btc_cg_stale.py - 清理 BTC_SPOT_PRICE_1H_CG 旧脏数据

原因：v2 采集器的日期错位（timestamp 是 UTC 0:00），导致库里存的数据日期比
正确日期晚一天。v3 修复后，必须清空旧数据重新抓，否则新旧混杂。
"""
import sqlite3

DB_PATH = 'data/macro.db'

TARGETS = ['BTC_SPOT_PRICE_1H_CG', 'ETH_PRICE_CG']

conn = sqlite3.connect(DB_PATH)
for sid in TARGETS:
    cur = conn.execute("DELETE FROM observations WHERE series_id=?", (sid,))
    print(f"  🧹 删除 {sid}: {cur.rowcount} 行")
conn.commit()
conn.close()
print("✅ 清理完成")