"""
Farside BTC ETF Flows 每日资金流
输出: data/farside_btc_etf.csv
"""
import pandas as pd
from datetime import datetime
from pathlib import Path

URL = 'https://farside.co.uk/btc/'
OUT = Path('data/farside_btc_etf.csv')

def fetch():
    tables = pd.read_html(URL)
    # 表格 0 通常是 ETF 流量表
    df = tables[0]
    # 清理列名
    df.columns = [str(c).strip() for c in df.columns]
    return df

def main():
    try:
        df = fetch()
        df['retrieved_at'] = datetime.utcnow().isoformat()
        OUT.parent.mkdir(exist_ok=True)
        df.to_csv(OUT, index=False)
        print(f'已保存: {OUT} ({len(df)} 行)')
        print(df.head())
    except Exception as e:
        print(f'失败: {e}')

if __name__ == '__main__':
    main()