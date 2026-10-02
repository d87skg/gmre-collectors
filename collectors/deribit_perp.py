"""
Deribit 永续合约资金费率 + 未平仓合约量
API: https://www.deribit.com/api/v2/public
无需 key
（Deribit 的 DVOL 已验证 Actions 可访问，Bybit/Binance 云 IP 被 403）
"""
import requests
import pandas as pd
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

OUT_FUNDING = Path('data/deribit_funding.csv')
OUT_OI = Path('data/deribit_oi.csv')
BASE = 'https://www.deribit.com/api/v2/public'

INSTRUMENTS = {
    'BTC-PERPETUAL': 'BTC',
    'ETH-PERPETUAL': 'ETH',
}


def fetch_funding(instrument, days=90):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    url = f'{BASE}/get_funding_rate_history'
    params = {
        'instrument_name': instrument,
        'start_timestamp': int(start.timestamp() * 1000),
        'end_timestamp': int(end.timestamp() * 1000),
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if 'result' not in data:
        raise RuntimeError(f'{instrument} 返回异常: {data}')
    rows = []
    for item in data['result']:
        ts = item['timestamp'] / 1000
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        # interest_8h 是 8 小时资金费率
        rows.append({
            'datetime': dt.strftime('%Y-%m-%d %H:%M'),
            'symbol': INSTRUMENTS[instrument],
            'funding_rate': float(item['interest_8h']),
        })
    return rows


def fetch_oi(instrument):
    """用 ticker 端点拿 open_interest 和 underlying_price"""
    url = f'{BASE}/ticker'
    params = {'instrument_name': instrument}
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if 'result' not in data:
        raise RuntimeError(f'{instrument} 返回异常: {data}')

    result = data['result']
    oi = float(result['open_interest'])

    # Deribit 永续合约每张面值 10 USD
    # （BTC-PERPETUAL 和 ETH-PERPETUAL 都是 inverse 合约）
    usd_per_contract = 10.0
    oi_usd = oi * usd_per_contract

    ts = result.get('timestamp', int(datetime.now(timezone.utc).timestamp() * 1000))
    dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)

    return [{
        'datetime': dt.strftime('%Y-%m-%d %H:%M'),
        'symbol': INSTRUMENTS[instrument],
        'oi': oi,
        'oi_usd': oi_usd,
    }]

def append_csv(rows, out):
    if not rows:
        return
    df_new = pd.DataFrame(rows)
    df_new['retrieved_at'] = datetime.utcnow().isoformat()
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        df_old = pd.read_csv(out)
        df = pd.concat([df_old, df_new]).drop_duplicates(
            subset=['datetime', 'symbol'], keep='last'
        )
    else:
        df = df_new
    df = df.sort_values(['datetime', 'symbol'])
    df.to_csv(out, index=False)
    print(f'已保存: {out} ({len(df)} 行)')


def main():
    funding_rows = []
    oi_rows = []
    for inst in INSTRUMENTS:
        try:
            rows = fetch_funding(inst)
            print(f'Funding {inst}: {len(rows)} 条')
            funding_rows.extend(rows)
        except Exception as e:
            print(f'Funding {inst} 失败: {e}')
        try:
            rows = fetch_oi(inst)
            print(f'OI {inst}: {len(rows)} 条')
            oi_rows.extend(rows)
        except Exception as e:
            print(f'OI {inst} 失败: {e}')

    if not funding_rows and not oi_rows:
        print('❌ 无数据')
        sys.exit(1)

    append_csv(funding_rows, OUT_FUNDING)
    append_csv(oi_rows, OUT_OI)


if __name__ == '__main__':
    main()