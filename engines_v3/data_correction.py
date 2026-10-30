"""engines_v3/data_correction.py - 数据修正（双源黄金 + 周末防火墙 + 周频兼容 + 重试降级版）"""
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
    # 🆕 P0 修复：补 4 个关键序列，让本地有实时数据源，摆脱对飞书快照的依赖
    'DGS10':        'YC10Y',       # 10Y 美债（防线2 核心）
    'DGS2':         'YC2Y',        # 2Y 美债
    'DGS30':        'YC30Y',       # 30Y 美债
    'VIXCLS':       'VIX',         # VIX 恐慌指数
}


def fetch_fred(fred_id, local_id):
    """拉取 FRED 数据，内置重试机制 + 周末防火墙 + 周频兼容"""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fred_id}"

    r = None
    # 连续请求 3 次，每次超时 15 秒
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=15, proxies=PROXIES)
            if r.status_code == 200:
                break
        except Exception:
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

        # ✅ 修复 1：周末防火墙 - 智能识别周频数据
        # 周末防火墙：过滤周六(5)/周日(6)的"日频"脏数据
        # 但如果过滤后变空，说明该序列本身就是周频（如 ICSA 初请失业金），保留原数据
        df_weekday = df[df['date'].dt.dayofweek < 5].copy()
        if not df_weekday.empty:
            df = df_weekday
        else:
            # 全部是周六/日：说明是周频数据（ICSA），保留原始数据
            print(f"  ℹ️ {local_id} 为周频数据（日期全为周末），跳过周末过滤")

        # 转换回字符串格式 'YYYY-MM-DD'
        df['date'] = df['date'].dt.strftime('%Y-%m-%d')

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # 清理该序列可能存在的历史周末脏数据
        # （只对日频序列生效，避免误删周频数据）
        if fred_id != 'ICSA':
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
            return float(fields[0])  # 最新价
        except Exception:
            if attempt < 2:
                time.sleep(1)
    return None


def fetch_gold_yahoo():
    """✅ 修复 2：备源改为直接 requests 访问 Yahoo chart API
    避开 yfinance 库的限流封装，成功率大幅提升。
    """
    url = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F"
    params = {"interval": "1d", "range": "5d"}  # 取最近5天，取最后一个非空收盘价
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json()
                result = data.get('chart', {}).get('result', [])
                if result:
                    closes = result[0].get('indicators', {}).get('quote', [{}])[0].get('close', [])
                    if closes:
                        # 从后往前取第一个非 None 的收盘价
                        for c in reversed(closes):
                            if c is not None:
                                return float(c)
            elif r.status_code in (429, 403):
                # 明确限流，短睡眠后重试
                time.sleep(2)
        except Exception:
            if attempt < 2:
                time.sleep(1)
    return None


def fetch_gold_stooq():
    """✅ 修复 2 补充：第三备源用 stooq（完全免费，无 IP 限制）"""
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
    """处理黄金双源交叉验证（升级为三源验证）+ 入库"""
    print("\n  [GOLD] 启动三源交叉验证...")
    sina_price = fetch_gold_sina()
    yahoo_price = fetch_gold_yahoo()
    stooq_price = fetch_gold_stooq()

    # 收集所有成功的价格
    candidates = []
    if sina_price:
        candidates.append(('Sina', sina_price))
    if yahoo_price:
        candidates.append(('Yahoo', yahoo_price))
    if stooq_price:
        candidates.append(('Stooq', stooq_price))

    final_price = None
    source = ""

    if not candidates:
        print("    🔴 [警告] GOLD 三源全部失败！今日金价将使用历史缓存。")
        return

    # 打印所有源的值
    for name, price in candidates:
        print(f"    {name}: {price:.2f}")

    # 主源优先用 Sina，其次 Yahoo，最后 Stooq
    if sina_price:
        final_price = sina_price
        source = "sina_hf_GC"
    elif yahoo_price:
        final_price = yahoo_price
        source = "yahoo_chart_api"
    elif stooq_price:
        final_price = stooq_price
        source = "stooq_xauusd"

    # 双源一致性检查（如果有 ≥2 个源）
    if len(candidates) >= 2:
        prices = [p for _, p in candidates]
        max_diff_pct = (max(prices) - min(prices)) / min(prices) * 100
        if max_diff_pct > 1.0:
            print(f"    ⚠️ 警告: GOLD 多源偏差 {max_diff_pct:.2f}% > 1%！可能存在报价异常")
        else:
            print(f"    ✅ 多源一致性验证通过 (最大偏差 {max_diff_pct:.2f}%)")
    else:
        print(f"    ⚠️ 仅单源可用 ({source})，无交叉验证")

    # 写入数据库
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
    print(f"  数据修正 (解冻版 v2.2 - 周频兼容 + 三源 GOLD)")
    print(f"{'='*60}\n")

    # 1. 跑 FRED 序列
    for fred_id, local_id in FRED_SERIES.items():
        try:
            count, latest = fetch_fred(fred_id, local_id)
            if count > 0:
                print(f"  ✅ {fred_id:15s} -> {local_id:15s} {count:5d}条 (最新: {latest})")
        except Exception as e:
            print(f"  ❌ {fred_id:15s}: 未知异常 {str(e)[:60]}")

    # 2. 跑 GOLD 三源融合
    process_gold()

    print(f"\n{'='*60}")
    print(f"  ✅ 数据修正完成")
    print(f"{'='*60}\n")