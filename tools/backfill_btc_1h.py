# tools/backfill_btc_1h.py - 修复 NOT NULL 约束问题
import sqlite3, time, requests
from datetime import datetime, timezone

DB_PATH = 'data/macro.db'
SERIES_ID = 'BTC_SPOT_PRICE_1H'
BASE_URL = 'https://api.binance.com/api/v3/klines'

def ms(dt_str):
    return int(datetime.strptime(dt_str, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp() * 1000)

def fetch_klines(start_ms, end_ms, symbol='BTCUSDT', interval='1h'):
    rows = []
    cursor = start_ms
    while cursor < end_ms:
        r = requests.get(BASE_URL, params={
            'symbol': symbol, 'interval': interval,
            'startTime': cursor, 'endTime': end_ms, 'limit': 1000,
        }, timeout=15)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        rows.extend(batch)
        last_open = batch[-1][0]
        if last_open <= cursor:
            break
        cursor = last_open + 1
        time.sleep(0.3)
    return rows

def main():
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT MAX(obs_ts) FROM observations WHERE series_id=?", (SERIES_ID,)
    ).fetchone()
    last_ts = row[0]
    start_ms = ms('2026-09-01') if not last_ts else \
        int(datetime.fromisoformat(last_ts).replace(tzinfo=timezone.utc).timestamp() * 1000) + 3600_000
    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    print(f"BTC 1H 补数区间: {datetime.fromtimestamp(start_ms/1000, timezone.utc)} → now")
    klines = fetch_klines(start_ms, end_ms)
    print(f"拉到 {len(klines)} 根 1H K 线")

    inserted = 0
    now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    
    for k in klines:
        obs_ts = datetime.fromtimestamp(k[0] / 1000, timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        obs_date = obs_ts[:10]  # 提取 YYYY-MM-DD
        close = float(k[4])
        
        try:
            # 补充 obs_date 和 ingest_at
            conn.execute(
                "INSERT OR REPLACE INTO observations "
                "(series_id, obs_ts, obs_date, ingest_at, value, source) "
                "VALUES (?, ?, ?, ?, ?, 'binance_kline_backfill')",
                (SERIES_ID, obs_ts, obs_date, now_str, close)
            )
            inserted += 1
        except Exception as ex:
            print(f"❌ 插入失败: {ex}")
            break
    
    conn.commit()
    conn.close()
    print(f"幂等写入完成，新增 {inserted} 行")

if __name__ == '__main__':
    main()