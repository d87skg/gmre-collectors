"""
Farside BTC ETF Flows
输出: data/farside_btc_etf.csv
"""
import io
import requests
import pandas as pd
import sys
from datetime import datetime
from pathlib import Path

URL = 'https://farside.co.uk/btc/'
OUT = Path('data/farside_btc_etf.csv')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}


def fetch():
    r = requests.get(URL, headers=HEADERS, timeout=30)
    print(f'HTTP {r.status_code}, 长度 {len(r.text)}')
    r.raise_for_status()

    # 关键修复：用 io.StringIO 包住，避免 pandas 把 HTML 当路径
    tables = pd.read_html(io.StringIO(r.text))
    print(f'找到 {len(tables)} 个表格')
    if not tables:
        raise RuntimeError('没找到表格')

    # 找最大的表格（ETF flow 表行数最多）
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
        print(df.head())
    except Exception as e:
        print(f'❌ 失败: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()