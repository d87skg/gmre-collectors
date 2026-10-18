import requests
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

BASE = 'https://stablecoins.llama.fi'

def fetch_current_flows():
    # 当前快照 + 24h 净流量
    url = f'{BASE}/stablecoin_flows'
    res = requests.get(url, timeout=30)
    res.raise_for_status()
    return res.json()

def fetch_history(token, days=30):
    # 日频历史净流量
    url = f'{BASE}/stablecoin_history/{token}'
    params = {'days': days}
    res = requests.get(url, params=params, timeout=30)
    res.raise_for_status()
    return res.json()

def main():
    rows = []
    try:
        current = fetch_current_flows()
        # current 通常是 list，每项包含 name, symbol, totalCirculating, netFlow24h 等
        for item in current if isinstance(current, list) else current.get('data', []):
            sym = str(item.get('symbol', '')).upper()
            if sym not in ('USDT', 'USDC', 'DAI', 'USDS', 'USDE', 'FDUSD', 'USDG', 'PYUSD', 'RLUSD'):
                continue
            rows.append({
                'date': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                'symbol': sym,
                'supply': float(item.get('totalCirculating', 0) or 0),
                'net_flow_24h': float(item.get('netFlow24h', 0) or 0),
                'source': 'flow_snapshot',
            })
    except Exception as e:
        print(f'当前流量失败: {e}')

    # 尝试拉取主要币种的历史流量
    for token in ['usdt', 'usdc', 'dai']:
        try:
            hist = fetch_history(token, days=30)
            hist_list = hist if isinstance(hist, list) else hist.get('data', [])
            for h in hist_list:
                rows.append({
                    'date': str(h.get('date', '')),
                    'symbol': token.upper(),
                    'supply': float(h.get('totalCirculating', 0) or 0),
                    'net_flow_24h': float(h.get('netFlow', 0) or 0),
                    'source': 'history',
                })
        except Exception as e:
            print(f'{token} 历史失败: {e}')

    if rows:
        df = pd.DataFrame(rows)
        Path('data').mkdir(exist_ok=True)
        df.to_csv('data/defillama_flows.csv', index=False)
        print(f'✅ 已保存 {len(df)} 条稳定币流量')
    else:
        print('❌ 未获取到流量数据')

if __name__ == '__main__':
    main()