"""
DefiLlama 稳定币数据
- 总市值（原）
- USDT / USDC 分开供应量（新增）
API: https://stablecoins.llama.fi
无需 key
"""
import requests
import pandas as pd
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path('data/defillama_stablecoin.csv')
OUT_DETAIL = Path('data/defillama_stablecoin_detail.csv')
BASE = 'https://stablecoins.llama.fi'


def fetch_total():
    """总市值历史（/stablecoincharts/all）"""
    url = f'{BASE}/stablecoincharts/all'
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    data = r.json()
    rows = []
    for item in data:
        ts = item.get('date')
        if not ts:
            continue
        try:
            ts_int = int(ts)
        except (ValueError, TypeError):
            continue
        dt = datetime.fromtimestamp(ts_int, tz=timezone.utc)
        total = item.get('totalCirculating', {})
        if not isinstance(total, dict):
            continue
        total_usd = total.get('peggedUSD')
        if total_usd is None:
            continue
        rows.append({
            'date': dt.strftime('%Y-%m-%d'),
            'total_usd': float(total_usd),
        })
    return rows


def fetch_detail():
    """USDT / USDC 分开供应量（/stablecoins）"""
    url = f'{BASE}/stablecoins'
    params = {'includePrices': 'false'}
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    data = r.json()
    pegged = data.get('peggedAssets', [])
    rows = []
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    for asset in pegged:
        symbol = asset.get('symbol', '').upper()
        if symbol not in ('USDT', 'USDC'):
            continue
        circ = asset.get('circulating', {})
        if isinstance(circ, dict):
            usd = circ.get('peggedUSD')
            if usd:
                rows.append({
                    'date': today,
                    'symbol': symbol,
                    'supply_usd': float(usd),
                })
    return rows


def main():
    # 总市值
    try:
        rows = fetch_total()
        print(f'总市值: {len(rows)} 条')
    except Exception as e:
        print(f'总市值失败: {e}')
        rows = []

    if rows:
        df_new = pd.DataFrame(rows)
        df_new['retrieved_at'] = datetime.utcnow().isoformat()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        if OUT.exists():
            df_old = pd.read_csv(OUT)
            df = pd.concat([df_old, df_new]).drop_duplicates(
                subset=['date'], keep='last'
            )
        else:
            df = df_new
        df = df.sort_values('date')
        df.to_csv(OUT, index=False)
        print(f'已保存: {OUT} ({len(df)} 行)')

    # USDT/USDC 分开
    try:
        rows = fetch_detail()
        print(f'USDT/USDC: {len(rows)} 条')
        for r in rows:
            print(f"  {r['symbol']}: ${r['supply_usd']/1e9:.1f}B")
    except Exception as e:
        print(f'USDT/USDC 失败: {e}')
        rows = []

    if rows:
        df_new = pd.DataFrame(rows)
        df_new['retrieved_at'] = datetime.utcnow().isoformat()
        OUT_DETAIL.parent.mkdir(parents=True, exist_ok=True)
        if OUT_DETAIL.exists():
            df_old = pd.read_csv(OUT_DETAIL)
            df = pd.concat([df_old, df_new]).drop_duplicates(
                subset=['date', 'symbol'], keep='last'
            )
        else:
            df = df_new
        df = df.sort_values(['date', 'symbol'])
        df.to_csv(OUT_DETAIL, index=False)
        print(f'已保存: {OUT_DETAIL} ({len(df)} 行)')


if __name__ == '__main__':
    main()