"""engines_v3/data_correction.py - 数据修正（双源黄金 + HY周末防火墙 + 重试降级版）"""
import requests
import sqlite3
import io
import pandas as pd
import time
from datetime import datetime

DB_PATH = 'data/macro.db'
PROXIES = None

# 核心 FRED 序列
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
    """拉取 FRED 数据，内置重试机制与周末过滤防火墙"""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fred_id}"
    
    r = None
    # 连续请求 3 次，每次超时 15 秒
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=15, proxies=PROXIES)
            if r.status_code == 200:
                break
        except Exception as e:
            if attempt < 2:
                print(f"  ⚠️ {local_id} 第 {attempt+1} 次请求超时/失败，准备重试...")
                time.sleep(2)
                
    # 如果彻底失败
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

        # 将 date 列转为 datetime 格式
        df['date'] = pd.to_datetime(df['date'])
        # 过滤掉周六(5)和周日(6)
        df = df[df['date'].dt.dayofweek < 5]
        # 转换回字符串格式 'YYYY-MM-DD'
        df['date'] = df['date'].dt.strftime('%Y-%m-%d')

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # 清理该序列可能存在的历史周末脏数据
        c.execute(f"""
            DELETE FROM observations 
            WHERE series_id = ? 
            AND strftime('%w', timestamp) IN ('0', '6')
        """, (local_id,))

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
    except Exception as e:
        print(f"  🔴 [警告] {local_id} 解析异常: {str(e)[:50]}，将使用历史缓存。")
        return -1, "ERROR"


def fetch_gold_sina():
    """主源：新浪财经（国内极速，带重试）"""
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
            fields = data_str.split(',')
            return float(fields[0]) # 最新价
        except Exception:
            if attempt < 2:
                time.sleep(1)
    return None

def fetch_gold_yahoo():
    """备源：Yahoo Finance（容易限流，带重试）"""
    try:
        import yfinance as yf
        ticker = yf.Ticker("GC=F")
        for attempt in range(3):
            try:
                df = ticker.history(period="1d", interval="1d")
                if not df.empty:
                    return float(df['Close'].iloc[-1])
            except Exception:
                time.sleep(1)
    except Exception:
        pass
    return None

def process_gold():
    """处理黄金双源交叉验证与入库"""
    print("\n  [GOLD] 启动双源交叉验证...")
    sina_price = fetch_gold_sina()
    yahoo_price = fetch_gold_yahoo()
    final_price = None
    source = ""

    # 1. 价格交叉验证逻辑
    if sina_price and yahoo_price:
        diff_pct = abs(sina_price - yahoo_price) / sina_price * 100
        print(f"    Sina: {sina_price:.2f} | Yahoo: {yahoo_price:.2f} | 偏差: {diff_pct:.2f}%")
        if diff_pct > 1.0:
            print(f"    ⚠️ 警告: GOLD 双源偏差超过 1% (Sina 与 Yahoo 异常)！")
        final_price = sina_price  # 优先用新浪实时价
        source = "sina_hf_GC"
    elif sina_price:
        final_price = sina_price
        source = "sina_hf_GC"
        print(f"    Sina: {sina_price:.2f} (Yahoo 失败或限流，使用单源)")
    elif yahoo_price:
        final_price = yahoo_price
        source = "yahoo_GC"
        print(f"    Yahoo: {yahoo_price:.2f} (Sina 失败，降级使用备用源)")
    else:
        print("    🔴 [警告] GOLD 双源连续重试均失败！今日金价将使用历史缓存。")
        return

    # 2. 写入数据库
    if final_price:
        date_str = datetime.now().strftime('%Y-%m-%d')
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            """INSERT OR REPLACE INTO observations
            (series_id, timestamp, value, source, retrieved_at)
            VALUES (?, ?, ?, ?, datetime('now'))""",
            ('GOLD_PRICE', date_str, final_price, source)
        )
        conn.commit()
        conn.close()
        print(f"    ✅ GOLD_PRICE -> {date_str} = {final_price:.2f} (源: {source})")


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"  数据修正 (解冻版 v2.1 - 重试降级)")
    print(f"{'='*60}\n")

    # 1. 跑 FRED 序列
    for fred_id, local_id in FRED_SERIES.items():
        try:
            count, latest = fetch_fred(fred_id, local_id)
            if count > 0:
                print(f"  ✅ {fred_id:15s} -> {local_id:15s} {count:5d}条 (最新: {latest})")
            # 失败时的红字提示已经在 fetch_fred 内部打印过了
        except Exception as e:
            print(f"  ❌ {fred_id:15s}: 未知异常 {str(e)[:60]}")

    # 2. 跑 GOLD 双源融合
    process_gold()

    print(f"\n{'='*60}")
    print(f"  ✅ 数据修正完成")
    print(f"{'='*60}\n")