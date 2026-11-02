"""engines_v3/data_correction.py - 数据修正（v2.3: 周频兼容 + 三源GOLD + SP500兜底）"""
import requests
import sqlite3
import io
import pandas as pd
import time
from datetime import datetime

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
    'DGS10':        'YC10Y',
    'DGS2':         'YC2Y',
    'DGS30':        'YC30Y',
    'VIXCLS':       'VIX',
}


def fetch_fred(fred_id, local_id):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fred_id}"
    r = None
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=15, proxies=PROXIES)
            if r.status_code == 200:
                break
        except Exception:
            if attempt < 2:
                print(f"  ⚠️ {local_id} 第 {attempt+1} 次请求超时/失败，准备重试...")
                time.sleep(2)

    if r is None or r.status_code != 200:
        print(f"  🔴 [警告] {local_id} 连续3次拉取失败！将使用历史缓存数据，今日数据未更新！")
        return -1, "FAILED"

    try:
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = ['date', 'value']
        df = df[df['value'] != '.']
        if df.empty:
            print(f"  🔴 [警告] {local_id} 返回空数据！将使用历史缓存。")
            return -1, "EMPTY"

        df['date'] = pd.to_datetime(df['date'])
        df_weekday = df[df['date'].dt.dayofweek < 5].copy()
        if not df_weekday.empty:
            df = df_weekday
        else:
            print(f"  ℹ️ {local_id} 为周频数据（日期全为周末），跳过周末过滤")

        df['date'] = df['date'].dt.strftime('%Y-%m-%d')

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        if fred_id != 'ICSA':
            c.execute(f"""DELETE FROM observations WHERE series_id = ? 
                AND strftime('%w', timestamp) IN ('0', '6')""", (local_id,))

        count = 0
        for _, row in df.iterrows():
            try:
                c.execute("""INSERT OR REPLACE INTO observations
                    (series_id, timestamp, value, source, retrieved_at)
                    VALUES (?, ?, ?, ?, datetime('now'))""",
                    (local_id, str(row['date']), float(row['value']), 'fred_csv'))
                count += 1
            except Exception:
                pass
        conn.commit()
        conn.close()
        latest = df.iloc[-1]
        return count, f"{latest['date']} = {latest['value']}"
    except Exception as e:
        print(f"  🔴 [警告] {local_id} 解析异常: {str(e)[:50]}，将使用历史缓存。")
        return -1, "ERROR"


def fetch_sp500_yahoo():
    """SP500 Yahoo 兜底"""
    url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC"
    params = {"interval": "1d", "range": "5d"}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            result = data.get('chart', {}).get('result', [])
            if result:
                timestamps = result[0].get('timestamp', [])
                closes = result[0].get('indicators', {}).get('quote', [{}])[0].get('close', [])
                rows = []
                for ts, c in zip(timestamps, closes):
                    if c is not None:
                        d = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d')
                        rows.append((d, float(c)))
                return rows
    except Exception as e:
        print(f"    SP500 Yahoo 失败: {e}")
    return None


def check_sp500_stale():
    """检查 SP500 是否滞后 > 3 天，若是则用 Yahoo 兜底"""
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT MAX(timestamp) FROM observations WHERE series_id='SP500'"
        ).fetchone()
        conn.close()
        if not row or not row[0]:
            return True
        latest = pd.to_datetime(row[0]).date()
        lag = (datetime.now().date() - latest).days
        return lag > 3
    except Exception:
        return True


def fetch_gold_sina():
    url = "https://hq.sinajs.cn/list=hf_GC"
    headers = {"Referer": "https://finance.sina.com.cn/"}
    for attempt in range(3):
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if "=" not in r.text:
                time.sleep(1)
                continue
            data_str = r.text.split('="')[1].split('"')[0]
            if not data_str:
                continue
            return float(data_str.split(',')[0])
        except Exception:
            if attempt < 2:
                time.sleep(1)
    return None


def fetch_gold_yahoo():
    url = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F"
    params = {"interval": "1d", "range": "5d"}
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json()
                result = data.get('chart', {}).get('result', [])
                if result:
                    closes = result[0].get('indicators', {}).get('quote', [{}])[0].get('close', [])
                    if closes:
                        for c in reversed(closes):
                            if c is not None:
                                return float(c)
            elif r.status_code in (429, 403):
                time.sleep(2)
        except Exception:
            if attempt < 2:
                time.sleep(1)
    return None


def fetch_gold_stooq():
    url = "https://stooq.com/q/d/l/?s=xauusd&i=d"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            df = pd.read_csv(io.StringIO(r.text))
            if not df.empty and 'Close' in df.columns:
                return float(df['Close'].iloc[-1])
    except Exception:
        pass
    return None


def process_gold():
    print("\n  [GOLD] 启动三源交叉验证...")
    sina_price = fetch_gold_sina()
    yahoo_price = fetch_gold_yahoo()
    stooq_price = fetch_gold_stooq()

    candidates = []
    if sina_price:
        candidates.append(('Sina', sina_price))
    if yahoo_price:
        candidates.append(('Yahoo', yahoo_price))
    if stooq_price:
        candidates.append(('Stooq', stooq_price))

    if not candidates:
        print("    🔴 [警告] GOLD 三源全部失败！今日金价将使用历史缓存。")
        return

    for name, price in candidates:
        print(f"    {name}: {price:.2f}")

    final_price = sina_price or yahoo_price or stooq_price
    source = "sina_hf_GC" if sina_price else ("yahoo_chart_api" if yahoo_price else "stooq_xauusd")

    if len(candidates) >= 2:
        prices = [p for _, p in candidates]
        max_diff_pct = (max(prices) - min(prices)) / min(prices) * 100
        if max_diff_pct > 1.0:
            print(f"    ⚠️ 警告: GOLD 多源偏差 {max_diff_pct:.2f}% > 1%！")
        else:
            print(f"    ✅ 多源一致性验证通过 (最大偏差 {max_diff_pct:.2f}%)")
    else:
        print(f"    ⚠️ 仅单源可用 ({source})，无交叉验证")

    if final_price:
        date_str = datetime.now().strftime('%Y-%m-%d')
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""INSERT OR REPLACE INTO observations
            (series_id, timestamp, value, source, retrieved_at)
            VALUES (?, ?, ?, ?, datetime('now'))""",
            ('GOLD_PRICE', date_str, final_price, source))
        conn.commit()
        conn.close()
        print(f"    ✅ GOLD_PRICE -> {date_str} = {final_price:.2f} (源: {source})")


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"  数据修正 (v2.3: 周频兼容 + 三源GOLD + SP500兜底)")
    print(f"{'='*60}\n")

    for fred_id, local_id in FRED_SERIES.items():
        try:
            count, latest = fetch_fred(fred_id, local_id)
            if count > 0:
                print(f"  ✅ {fred_id:15s} -> {local_id:15s} {count:5d}条 (最新: {latest})")
        except Exception as e:
            print(f"  ❌ {fred_id:15s}: 未知异常 {str(e)[:60]}")

    # 🆕 SP500 兜底检查
    if check_sp500_stale():
        print("\n  [SP500] FRED 滞后 > 3 天，启动 Yahoo 兜底...")
        rows = fetch_sp500_yahoo()
        if rows:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            count = 0
            for d, v in rows:
                try:
                    c.execute("""INSERT OR REPLACE INTO observations
                        (series_id, timestamp, value, source, retrieved_at)
                        VALUES ('SP500', ?, ?, 'yahoo_sp500', datetime('now'))""", (d, v))
                    count += 1
                except Exception:
                    pass
            conn.commit()
            conn.close()
            print(f"    ✅ SP500 Yahoo 兜底: 写入 {count} 条，最新 {rows[-1][0]} = {rows[-1][1]:.2f}")
        else:
            print("    ❌ SP500 Yahoo 也失败，继续用历史缓存")

    process_gold()

    print(f"\n{'='*60}")
    print(f"  ✅ 数据修正完成")
    print(f"{'='*60}\n")