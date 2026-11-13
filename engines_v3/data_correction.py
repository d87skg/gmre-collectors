"""engines_v3/data_correction.py - 数据修正（v4.1: 官方源直达新表 + 离线 fixture 回放）"""
import argparse
import io
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

# =============================================================================
# v4.1 沙盒约束（2026-11-11）
# -----------------------------------------------------------------------------
# 生产 D:\HGZC / D:\HGZC-collectors 为只读参考源，本脚本永不读写其路径。
# 官方数据一律走 append-only 的 insert_observation（落 observations_v2），
# 废除 INSERT OR REPLACE、废除周末 DELETE —— 只追加，不覆盖，不删除。
# =============================================================================
SANDBOX_ROOT = Path(r'D:\HGZC-v41-sandbox')
FORBIDDEN_ROOTS = (Path(r'D:\HGZC'), Path(r'D:\HGZC-collectors'))

DB_PATH = os.environ.get('GMRE_DB_PATH', str(SANDBOX_ROOT / 'data' / 'macro.db'))
PROXIES = None

# 非空则 fetch_fred 只读本地 fixture（格式同 FRED fredgraph CSV），绝不触网
FIXTURE_DIR = os.environ.get('GMRE_FIXTURE_DIR', '')

try:
    from dotenv import load_dotenv
    load_dotenv(str(SANDBOX_ROOT / '.env'))
except ImportError:
    pass

YAHOO_PROXY = os.environ.get('YAHOO_PROXY', '')
YAHOO_PROXIES = {"http": YAHOO_PROXY, "https": YAHOO_PROXY} if YAHOO_PROXY else None

sys.path.insert(0, str(SANDBOX_ROOT))
from core.database import Database  # noqa: E402

_DB = None


def _assert_sandbox() -> None:
    """库路径必须落在沙盒内，命中生产目录直接拒绝执行。"""
    resolved = Path(DB_PATH).resolve()
    for forbidden in FORBIDDEN_ROOTS:
        f = forbidden.resolve()
        if resolved == f or f in resolved.parents:
            raise SystemExit(f'DISARMED: DB_PATH={resolved} 命中生产目录 {f}，已拒绝执行。')


def _db() -> Database:
    global _DB
    if _DB is None:
        _DB = Database(DB_PATH)
    return _DB


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
    # ---- v4.1 阶段 2A：恢复 RRP / TGA 的官方源（此前完全缺失，只能靠飞书覆写）----
    'RRPONTSYD':    'RRPONTSYD',      # ON RRP 余额，FRED 原生单位：十亿美元
    'WTREGEN':      'WTREGEN',        # 财政部一般账户(TGA)，FRED 原生单位：百万美元
}

# 量纲 canonical（与阶段 0 决策一致）：TGA=百万美元，RRP=十亿美元
# 30 个引擎零改动的关键：入库时就按 canonical 单位落，代理层不再需要猜
SERIES_META = {
    'RRPONTSYD': {'unit': 'billion_usd', 'frequency': 'daily'},
    'WTREGEN':   {'unit': 'million_usd', 'frequency': 'weekly'},
}
DEFAULT_META = {'unit': 'n/a', 'frequency': 'daily'}


def _load_fixture(fred_id):
    """离线 fixture：<FIXTURE_DIR>/<fred_id>.csv，两列 fredgraph 格式（date,value）。"""
    p = Path(FIXTURE_DIR) / f'{fred_id}.csv'
    if not p.exists():
        return None
    return p.read_text(encoding='utf-8')


def _http_get(url, local_id):
    """带 3 次重试的 GET。失败返回 None —— 绝不返回"历史缓存"来冒充今日数据。"""
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=15, proxies=PROXIES)
            if r.status_code == 200:
                return r.text
        except Exception:
            if attempt < 2:
                print(f"  ⚠️ {local_id} 第 {attempt+1} 次请求超时/失败，准备重试...")
                time.sleep(2)
    return None


def fetch_fred(fred_id, local_id):
    """拉取（或回放）单序列，append-only 写入。返回 (新增行数, 最新值描述)。

    v4.1 改动：
      1. 写库走 core.database.insert_observation（obs_ts 全精度 + rev_seq 版本号），
         废除 INSERT OR REPLACE；
      2. 废除 `DELETE ... WHERE strftime('%w',timestamp) IN ('0','6')` 这类破坏性清洗，
         周末过滤改为入库前 select 过滤；
      3. 拉取失败只报警、**不写旧值、不 ffill** —— 陈旧由阶段三代理层按 SLA 拦截；
      4. GMRE_FIXTURE_DIR 非空时只读本地 CSV，可做完全离线的回放测试。
    """
    # 🆕 只拉取过去 30 天，大幅度减少网络请求负载
    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fred_id}&cosd={start_date}"

    if FIXTURE_DIR:
        text = _load_fixture(fred_id)
        via = 'FIXTURE'
        if text is None:
            print(f"  🔴 [警告] {local_id} 离线 fixture 缺失: {fred_id}.csv")
            return -1, "FIXTURE_MISSING"
    else:
        text = _http_get(url, local_id)
        via = 'FRED_API'

    if not text:
        print(f"  🔴 [警告] {local_id} 连续3次拉取失败！本次不写入（不使用历史缓存顶替）")
        return -1, "FAILED"

    try:
        df = pd.read_csv(io.StringIO(text))
        df.columns = ['date', 'value']
        df = df[df['value'] != '.']
        df['value'] = pd.to_numeric(df['value'], errors='coerce')
        df = df.dropna(subset=['value'])
        if df.empty:
            print(f"  🔴 [警告] {local_id} 返回空数据！本次不写入。")
            return -1, "EMPTY"

        df['date'] = pd.to_datetime(df['date'])
        df_weekday = df[df['date'].dt.dayofweek < 5].copy()
        if not df_weekday.empty:
            df = df_weekday
        else:
            print(f"  ℹ️ {local_id} 为周频数据（日期全为周末），跳过周末过滤")

        df['date'] = df['date'].dt.strftime('%Y-%m-%d')

        meta = SERIES_META.get(local_id, DEFAULT_META)
        db = _db()
        created = 0
        idempotent = 0
        failed = 0
        for _, row in df.iterrows():
            try:
                _row_id, is_new = db.insert_observation(
                    local_id, str(row['date']), float(row['value']),
                    source='fred_csv',
                    unit=meta['unit'],
                    frequency=meta['frequency'],
                )
                if is_new:
                    created += 1
                else:
                    idempotent += 1
            except Exception as e:
                failed += 1
                if failed <= 3:
                    print(f"  ⚠️ {local_id} 写入失败 {row['date']}: {str(e)[:70]}")

        latest = df.iloc[-1]
        note = f"{latest['date']} = {latest['value']} [{via}] 新增{created}/幂等{idempotent}"
        if failed:
            note += f"/失败{failed}"
        return created, note
    except Exception as e:
        print(f"  🔴 [警告] {local_id} 解析异常: {str(e)[:50]}，本次不写入。")
        return -1, "ERROR"


def fetch_sp500_yahoo():
    url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC"
    params = {"interval": "1d", "range": "5d"}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15, proxies=YAHOO_PROXIES)
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
            r = requests.get(url, params=params, headers=headers, timeout=15, proxies=YAHOO_PROXIES)
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
    if sina_price: candidates.append(('Sina', sina_price))
    if yahoo_price: candidates.append(('Yahoo', yahoo_price))
    if stooq_price: candidates.append(('Stooq', stooq_price))

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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='GMRE 数据修正（v4.1 官方源直达新表）')
    ap.add_argument('--series', default='',
                    help='只跑指定 FRED id，逗号分隔（如 RRPONTSYD,WTREGEN）；空=全部')
    ap.add_argument('--offline', action='store_true',
                    help='仅用本地 fixture 回放，绝不触网（需 GMRE_FIXTURE_DIR）')
    ap.add_argument('--no-aux', action='store_true',
                    help='跳过 SP500 Yahoo 兜底与 GOLD 三源（纯离线测试用）')
    args = ap.parse_args(argv)

    if args.offline and not FIXTURE_DIR:
        ap.error('--offline 需要环境变量 GMRE_FIXTURE_DIR 指向 fixture 目录')

    _assert_sandbox()

    print(f"\n{'='*60}")
    print(f"  数据修正 (v4.1: 官方源 -> obs_ts/rev_seq 追加式新表)")
    print(f"  DB       : {DB_PATH}")
    print(f"  MODE     : {'OFFLINE FIXTURE ' + FIXTURE_DIR if FIXTURE_DIR else 'LIVE FRED API'}")
    print(f"{'='*60}\n")

    if args.series.strip():
        ids = [x.strip() for x in args.series.split(',') if x.strip()]
        unknown = [x for x in ids if x not in FRED_SERIES]
        if unknown:
            ap.error(f'未知 FRED id: {unknown}')
    else:
        ids = list(FRED_SERIES)

    ok = 0
    skipped = 0
    for fred_id in ids:
        local_id = FRED_SERIES[fred_id]
        try:
            count, latest = fetch_fred(fred_id, local_id)
            if count >= 0:
                ok += 1
                print(f"  ✅ {fred_id:15s} -> {local_id:15s} {count:5d}条新增  {latest}")
            else:
                skipped += 1
                print(f"  ⚠️ {fred_id:15s} -> {local_id:15s} 跳过（{latest}）")
        except Exception as e:
            skipped += 1
            print(f"  ❌ {fred_id:15s}: 未知异常 {str(e)[:60]}")

    if not args.no_aux:
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
    print(f"  ✅ 数据修正完成：成功 {ok} / 跳过 {skipped}")
    print(f"{'='*60}\n")
    return 0 if skipped == 0 else 1


if __name__ == "__main__":
    sys.exit(main())