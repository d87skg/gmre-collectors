# tools/audit_returns_quality.py
# 临时诊断脚本：检查 risk_budget_engine 所用 6 资产的收益率数据质量
import sqlite3
import numpy as np
import pandas as pd

DB_PATH = 'data/macro.db'

ASSETS = {
    'SP500': 'SP500',
    'GOLD': 'GOLD_PRICE',
    'BTC': 'BTC_SPOT_PRICE_1H',
    'SHY': 'SHY_PRICE',
    'TLT': 'TLT_PRICE',
    'WTI': 'WTI_OIL',
}

def get_pit_series(series_id, limit=252):
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    query = """
        SELECT obs_ts AS timestamp, value
        FROM observations
        WHERE series_id = ? AND value IS NOT NULL
        ORDER BY obs_ts ASC LIMIT ?
    """
    try:
        df = pd.read_sql_query(query, conn, params=(series_id, limit * 2))
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df = df.dropna(subset=['timestamp'])
        df['date'] = df['timestamp'].dt.date
        df = df.drop_duplicates(subset=['date'], keep='last')
        df = df.sort_values('date').set_index('date')['value'].astype(float)
        return df.ffill().tail(limit)
    except Exception as e:
        print(f"  [{series_id}] 读取失败: {e}")
        return pd.Series(dtype=float)
    finally:
        conn.close()

print("=" * 80)
print("  收益率数据质量审计")
print("=" * 80)

prices = {}
for name, sid in ASSETS.items():
    s = get_pit_series(sid, limit=252)
    if not s.empty:
        prices[name] = s

print(f"\n有效资产数: {len(prices)}/6\n")

# 1. 每个资产原始序列诊断
print("-" * 80)
print("【1】原始价格序列诊断")
print("-" * 80)
print(f"{'资产':<8} | {'样本数':<6} | {'首日':<12} | {'末日':<12} | {'min':<12} | {'max':<12} | {'唯一值数':<8} | {'std':<12}")
for name, s in prices.items():
    uniq = s.nunique()
    print(f"{name:<8} | {len(s):<6} | {str(s.index[0]):<12} | {str(s.index[-1]):<12} | "
          f"{s.min():<12.6f} | {s.max():<12.6f} | {uniq:<8} | {s.std():<12.6f}")

# 2. 对齐后收益率诊断
df_prices = pd.DataFrame(prices).ffill().dropna()
returns = df_prices.pct_change().dropna()

print("\n" + "-" * 80)
print("【2】对齐后收益率诊断（dropna 之后）")
print("-" * 80)
print(f"共同交易日数: {len(returns)}")
print(f"{'资产':<8} | {'均值':<14} | {'标准差':<14} | {'零收益率占比':<12} | {'最小':<14} | {'最大':<14}")
for col in returns.columns:
    r = returns[col]
    zero_ratio = (r == 0).mean() * 100
    print(f"{col:<8} | {r.mean():<14.8f} | {r.std():<14.8f} | "
          f"{zero_ratio:<11.1f}% | {r.min():<14.8f} | {r.max():<14.8f}")

# 3. 协方差矩阵对角线 vs 样本方差
print("\n" + "-" * 80)
print("【3】协方差矩阵对角线 vs 收益率样本方差")
print("-" * 80)
try:
    from sklearn.covariance import LedoitWolf
    lw = LedoitWolf()
    lw.fit(returns)
    cov = lw.covariance_
    sample_var = returns.var().values
    diag = np.diag(cov)
    print(f"{'资产':<8} | {'样本方差':<16} | {'LW协方差对角线':<16} | {'比值':<10}")
    for i, col in enumerate(returns.columns):
        ratio = diag[i] / sample_var[i] if sample_var[i] > 0 else float('inf')
        print(f"{col:<8} | {sample_var[i]:<16.10f} | {diag[i]:<16.10f} | {ratio:<10.4f}")
    print(f"\n样本方差矩阵最小特征值: {np.min(np.real(np.linalg.eigvals(cov))):.10f}")
    print(f"样本方差矩阵最大特征值: {np.max(np.real(np.linalg.eigvals(cov))):.10f}")
except Exception as e:
    print(f"LedoitWolf 失败: {e}")

# 4. 检查 observations 表里这些 series 最近 10 条原始记录
print("\n" + "-" * 80)
print("【4】observations 表最近 10 条原始记录")
print("-" * 80)
conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
for name, sid in ASSETS.items():
    print(f"\n-- {name} ({sid}) --")
    try:
        df = pd.read_sql_query(
            "SELECT obs_ts, value, source FROM observations "
            "WHERE series_id=? ORDER BY obs_ts DESC LIMIT 10",
            conn, params=(sid,)
        )
        if df.empty:
            print("  (无记录)")
        else:
            for _, row in df.iterrows():
                print(f"  {row['obs_ts']} | {row['value']:.6f} | {row['source']}")
    except Exception as e:
        print(f"  查询失败: {e}")
conn.close()

print("\n" + "=" * 80)
print("  审计完成")
print("=" * 80)