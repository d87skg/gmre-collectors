"""engines_v3/data_correction.py - 数据修正（黄金用yfinance，最终版）"""
import requests
import sqlite3
import io
import pandas as pd

DB_PATH = 'data/macro.db'
PROXIES = None


FRED_SERIES = {
    'SP500':        'SP500',
    'DCOILWTICO':   'WTI_OIL',
    'DCOILBRENTEU': 'BRENT_OIL',
    'PPIACO':       'PPI',
    'PAYEMS':       'PAYROLLS',
    'UNRATE':       'UNEMPLOYMENT',
    'ICSA':         'JOBLESS_CLAIMS',
    'BAMLH0A0HYM2': 'HY_SPREAD',
}


def fetch_fred(fred_id, local_id):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fred_id}"
    r = requests.get(url, timeout=30, proxies=PROXIES)
    if r.status_code != 200:
        return 0, None
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = ['date', 'value']
    df = df[df['value'] != '.']
    if df.empty:
        return 0, None

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    count = 0
    for _, row in df.iterrows():
        try:
            c.execute(
                """INSERT OR REPLACE INTO observations
                (series_id, timestamp, value, source, retrieved_at)
                VALUES (?, ?, ?, ?, datetime('now'))""",
                (local_id, str(row['date']), float(row['value']), 'fred_csv')
            )
            count += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    latest = df.iloc[-1]
    return count, f"{latest['date']} = {latest['value']}"


def fetch_gold_yahoo():
    """从 Yahoo Finance 拉取黄金期货 (GC=F)"""
    try:
        import yfinance as yf
        ticker = yf.Ticker("GC=F")
        df = ticker.history(period="max", interval="1d")
        if df.empty:
            return 0, "yfinance返回空"

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        count = 0
        for date_idx, row in df.iterrows():
            try:
                date_str = date_idx.strftime('%Y-%m-%d')
                c.execute(
                    """INSERT OR REPLACE INTO observations
                    (series_id, timestamp, value, source, retrieved_at)
                    VALUES (?, ?, ?, ?, datetime('now'))""",
                    ('GOLD_PRICE', date_str, float(row['Close']), 'yahoo')
                )
                count += 1
            except Exception:
                pass
        conn.commit()
        conn.close()
        latest = df.tail(1).iloc[0]
        latest_date = df.tail(1).index[0].strftime('%Y-%m-%d')
        return count, f"{latest_date} = {latest['Close']:.2f}"
    except Exception as e:
        return 0, f"yahoo失败: {str(e)[:80]}"


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"  数据修正")
    print(f"{'='*60}\n")

    # 1. FRED 序列
    for fred_id, local_id in FRED_SERIES.items():
        try:
            count, latest = fetch_fred(fred_id, local_id)
            if count > 0:
                print(f"  ✅ {fred_id:15s} -> {local_id:15s} {count:5d}条 (最新: {latest})")
            else:
                print(f"  ⚠️ {fred_id:15s} -> {local_id:15s} 无数据")
        except Exception as e:
            print(f"  ❌ {fred_id:15s}: {str(e)[:60]}")

       # 2. 黄金（暂时跳过，防止被限流）
    # print()
    # try:
    #     count, latest = fetch_gold_yahoo()
    #     if count > 0:
    #         print(f"  ✅ {'GC=F(yahoo)':15s} -> {'GOLD_PRICE':15s} {count:5d}条 (最新: {latest})")
    #     else:
    #         print(f"  ❌ GOLD_PRICE: {latest}")
    # except Exception as e:
    #     print(f"  ❌ GOLD_PRICE: {str(e)[:80]}")

    print(f"\n{'='*60}")
    print(f"  ✅ 数据修正完成")
    print(f"{'='*60}\n")