import requests
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

def fetch_ratio(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list) and len(data) > 0:
                return data[0]
    except Exception as e:
        print(f"获取多空比异常: {e}")
    return None

def main():
    rows = []
    now = datetime.now(timezone.utc).isoformat()
    
    # 1. 散户多空人数比
    retail_url = 'https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=BTCUSDT&period=1h&limit=1'
    retail = fetch_ratio(retail_url)
    if retail:
        rows.append({
            'datetime': now,
            'metric': 'RETAIL_LONG_SHORT_RATIO',
            'value': float(retail['longShortRatio']),
            'extra': f"多单 {float(retail['longAccount'])*100:.1f}% / 空单 {float(retail['shortAccount'])*100:.1f}%"
        })
        print(f"✅ 散户多空比: {retail['longShortRatio']}")

    # 2. 大户持仓多空比
    top_url = 'https://fapi.binance.com/futures/data/topLongShortPositionRatio?symbol=BTCUSDT&period=1h&limit=1'
    top = fetch_ratio(top_url)
    if top:
        rows.append({
            'datetime': now,
            'metric': 'TOP_LONG_SHORT_RATIO',
            'value': float(top['longShortRatio']),
            'extra': f"多头 {float(top['longAccount'])*100:.1f}% / 空头 {float(top['shortAccount'])*100:.1f}%"
        })
        print(f"✅ 大户多空比: {top['longShortRatio']}")

    if rows:
        df = pd.DataFrame(rows)
        Path('data').mkdir(exist_ok=True)
        df.to_csv('data/binance_sentiment.csv', index=False)
        print(f"已保存 {len(rows)} 条情绪数据")
    else:
        print("❌ 获取多空数据失败，可能被 Cloudflare 拦截")

if __name__ == '__main__':
    main()