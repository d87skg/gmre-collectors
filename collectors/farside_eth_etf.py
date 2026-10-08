"""
Farside ETH ETF Flows
URL: https://farside.co.uk/eth/
用 curl_cffi 绕过 Cloudflare
"""
import io
import pandas as pd
import sys
from datetime import datetime
from pathlib import Path
from curl_cffi import requests

URL = 'https://farside.co.uk/eth/'
OUT = Path('data/farside_eth_etf.csv')


def fetch():
    r = requests.get(URL, impersonate="chrome", timeout=30)
    print(f'HTTP {r.status_code}, 长度 {len(r.text)}')
    if r.status_code != 200:
        raise RuntimeError(f'HTTP {r.status_code}')

    tables = pd.read_html(io.StringIO(r.text))
    print(f'找到 {len(tables)} 个表格')
    if not tables:
        raise RuntimeError('没找到表格')

    df = max(tables, key=len)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def main():
    try:
        df = fetch()
        df['retrieved_at'] = datetime.utcnow().isoformat()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(OUT, index=False)
        print(f'已保存: {OUT} ({len(df)} 行)')
        print(df.head().to_string())
    except Exception as e:
        print(f'❌ 失败: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()