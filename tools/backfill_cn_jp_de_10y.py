# tools/backfill_cn_jp_de_10y.py - 跨国 10Y 补数
import sqlite3
import akshare as ak

DB_PATH = 'data/macro.db'

def upsert(conn, series_id, df, date_col, value_col, source):
    inserted = 0
    for _, row in df.iterrows():
        obs_ts = str(row[date_col])[:10]
        val = row[value_col]
        if val is None or (isinstance(val, float) and val != val):
            continue
        try:
            cur = conn.execute(
                "INSERT OR IGNORE INTO observations (series_id, obs_ts, value, source) "
                "VALUES (?, ?, ?, ?)",
                (series_id, obs_ts, float(val), source)
            )
            inserted += cur.rowcount
        except sqlite3.OperationalError:
            conn.execute(
                "INSERT OR IGNORE INTO observations (series_id, timestamp, value, source) "
                "VALUES (?, ?, ?, ?)",
                (series_id, obs_ts, float(val), source)
            )
            inserted += 1
    conn.commit()
    return inserted

def main():
    conn = sqlite3.connect(DB_PATH)

    # 中国 10Y：bond_zh_us_rate 同时含中美两国 10Y
    df = ak.bond_zh_us_rate(start_date="20260101")
    n_cn = upsert(conn, 'CN_10Y_YIELD', df, '日期', '中国国债收益率10年', 'akshare_bond_zh_us_rate')
    print(f"CN_10Y_YIELD 新增 {n_cn} 行")

    # 日本 / 德国 10Y：用 bond_investing_global，先查国家名称再拉
    for gmre_id, country, index_name in [
        ('JP_10Y', '日本', '日本10年期国债'),
        ('DE_10Y', '德国', '德国10年期国债'),
    ]:
        try:
            df_global = ak.bond_investing_global(
                country=country, index_name=index_name,
                period='每日', start_date='2026-01-01'
            )
            n = upsert(conn, gmre_id, df_global, '日期', '收益率', 'akshare_bond_investing_global')
            print(f"{gmre_id} 新增 {n} 行")
        except Exception as e:
            print(f"  ⚠️ {gmre_id} 拉取失败: {e}")

    conn.close()

if __name__ == '__main__':
    main()