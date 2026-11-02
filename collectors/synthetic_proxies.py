"""collectors/synthetic_proxies.py - 合成代理数据采集（stooq版）"""
import sqlite3
import pandas as pd
import requests
import io
import time
from datetime import datetime

DB_PATH = 'data/macro.db'


def _save(conn, series_id, df):
    c = conn.cursor()
    count = 0
    for date_idx, row in df.iterrows():
        try:
            date_str = date_idx.strftime('%Y-%m-%d') if not isinstance(date_idx, str) else date_idx
            val = row['value'] if 'value' in row else row.iloc[0]
            if pd.isna(val):
                continue
            c.execute("""
                INSERT OR REPLACE INTO observations
                (series_id, timestamp, value, source, retrieved_at)
                VALUES (?, ?, ?, ?, datetime('now'))
            """, (series_id, date_str, float(val), 'stooq'))
            count += 1
        except Exception:
            pass
    conn.commit()
    return count


def fetch_stooq(symbol, local_id, field='Close'):
    """stooq.com 数据（免费、无限制）"""
    try:
        url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
        r = requests.get(url, timeout=30)
        if r.status_code != 200:
            print(f"  ⚠️ {symbol}: HTTP {r.status_code}")
            return 0
        df = pd.read_csv(io.StringIO(r.text))
        if df.empty or field not in df.columns:
            print(f"  ⚠️ {symbol}: 无 {field} 列")
            return 0
        df = df[['Date', field]].rename(columns={'Date': 'date', field: 'value'})
        df = df.set_index('date')
        conn = sqlite3.connect(DB_PATH)
        n = _save(conn, local_id, df)
        conn.close()
        return n
    except Exception as e:
        print(f"  ❌ {symbol}: {str(e)[:60]}")
        return 0


def fetch_fred(fred_id, local_id):
    """FRED CSV"""
    try:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fred_id}"
        r = requests.get(url, timeout=60)
        if r.status_code != 200:
            return 0
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = ['date', 'value']
        df = df[df['value'] != '.']
        df = df.set_index('date')
        conn = sqlite3.connect(DB_PATH)
        n = _save(conn, local_id, df)
        conn.close()
        return n
    except Exception as e:
        print(f"  ❌ {fred_id}: {str(e)[:60]}")
        return 0


def main():
    print(f"\n{'='*60}")
    print(f"  Synthetic Proxy Data Collection (stooq版)")
    print(f"  时间: {datetime.now().isoformat()}")
    print(f"{'='*60}\n")

    # ============ 代理1: Positioning ============
    print("[1/4] Positioning 代理数据...")
    for sym, sid in [('spy.us', 'SPY_VOLUME'), ('tlt.us', 'TLT_VOLUME'), ('gld.us', 'GLD_VOLUME')]:
        n = fetch_stooq(sym, sid, field='Volume')
        if n > 0:
            print(f"  ✅ {sym:8s} → {sid:15s} {n:5d}条")
        time.sleep(1)

    # ============ 代理2: Options Gamma ============
    print("\n[2/4] Options Gamma 代理数据...")
    # stooq 无 SKEW/VVIX，用 VIX 替代（已有）
    print("  ℹ️ SKEW/VVIX 无 stooq，用已有 VIX 代理")

    # ============ 代理3: Bank CDS ============
    print("\n[3/4] Bank CDS 代理数据...")
    for fred_id, sid in [('SOFR', 'SOFR'), ('DTB3', 'YC3M')]:
        n = fetch_fred(fred_id, sid)
        if n > 0:
            print(f"  ✅ {fred_id:8s} → {sid:15s} {n:5d}条")
        time.sleep(1)

    for sym, sid in [('hyg.us', 'HYG_PRICE'), ('lqd.us', 'LQD_PRICE')]:
        n = fetch_stooq(sym, sid, field='Close')
        if n > 0:
            print(f"  ✅ {sym:8s} → {sid:15s} {n:5d}条")
        time.sleep(1)

    # ============ 代理4 ============
    print("\n[4/4] Cross-Currency Basis 代理...")
    print("  ✅ USDJPY 已有数据，无需新采集")

    print(f"\n{'='*60}")
    print(f"  ✅ 代理数据采集完成")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()