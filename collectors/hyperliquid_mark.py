"""
Hyperliquid 链上数据（标记价 + 资金费率 + OI）
API: https://api.hyperliquid.xyz/info (POST)
无 IP 封锁，Actions 可直连
"""
import requests
import pandas as pd
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path('data/hyperliquid.csv')
API = 'https://api.hyperliquid.xyz/info'

TARGETS = ['BTC', 'ETH', 'SOL']


def call(payload):
    r = requests.post(API, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch():
    # 全市场中间价
    mids = call({'type': 'allMids'})
    # 元数据 + 上下文
    meta_ctxs = call({'type': 'metaAndAssetCtxs'})
    return mids, meta_ctxs


def main():
    try:
        mids, meta_ctxs = fetch()
        print(f'allMids: {len(mids)} 币种')
        print(f'metaAndAssetCtxs: {len(meta_ctxs)} 组')
    except Exception as e:
        print(f'❌ 失败: {e}')
        sys.exit(1)

    today = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')
    rows = []

    # 解析 metaAndAssetCtxs
    # 返回格式: [{"universe": [...]}, [{"funding":"...", "openInterest":"...", "markPx":"...", "oraclePx":"...", ...}, ...]]
    try:
        universe = meta_ctxs[0].get('universe', [])
        ctxs = meta_ctxs[1]
    except (IndexError, KeyError, TypeError):
        universe = []
        ctxs = []

    for i, ctx in enumerate(ctxs):
        if i >= len(universe):
            break
        name = universe[i].get('name', '')
        if name not in TARGETS:
            continue
        rows.append({
            'datetime': today,
            'symbol': name,
            'mid_px': float(mids.get(name, 0)),
            'mark_px': float(ctx.get('markPx', 0)) if ctx.get('markPx') else None,
            'oracle_px': float(ctx.get('oraclePx', 0)) if ctx.get('oraclePx') else None,
            'funding_rate': float(ctx.get('funding', 0)) if ctx.get('funding') else None,
            'open_interest': float(ctx.get('openInterest', 0)) if ctx.get('openInterest') else None,
            'premium': float(ctx.get('premium', 0)) if ctx.get('premium') else None,
        })

    if not rows:
        print('❌ 无数据（universe 里没有 BTC/ETH/SOL）')
        sys.exit(1)

    print(f'拿到 {len(rows)} 条:')
    for r in rows:
        oi_str = f"{r['open_interest']:.0f}" if r['open_interest'] else "N/A"
        fr_str = f"{r['funding_rate']*100*365*24:.2f}%" if r['funding_rate'] is not None else "N/A"
        print(f"  {r['symbol']}: mid={r['mid_px']:.2f}, mark={r['mark_px']}, OI={oi_str}, FR年化={fr_str}")

    df_new = pd.DataFrame(rows)
    df_new['retrieved_at'] = datetime.utcnow().isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)

    if OUT.exists():
        df_old = pd.read_csv(OUT)
        df = pd.concat([df_old, df_new]).drop_duplicates(
            subset=['datetime', 'symbol'], keep='last'
        )
    else:
        df = df_new

    df = df.sort_values(['datetime', 'symbol'])
    df.to_csv(OUT, index=False)
    print(f'已保存: {OUT} ({len(df)} 行)')


if __name__ == '__main__':
    main()