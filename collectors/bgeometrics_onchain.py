import os
import requests
import time
import pandas as pd
from datetime import datetime
from pathlib import Path

TOKEN = os.environ.get('BGEOMETRICS_TOKEN')
BASE_URL = 'https://api.bgeometrics.com/v1'

# 免费版限制每天15次，只请求 3 个核心指标
METRICS = ['mvrv', 'sopr', 'realized-price']

def fetch_metric(metric):
    url = f'{BASE_URL}/{metric}'
    params = {'token': TOKEN}
    try:
        res = requests.get(url, params=params, timeout=15)
        if res.status_code == 200:
            return res.json()
        else:
            print(f'  {metric} 失败: HTTP {res.status_code}')
    except Exception as e:
        print(f'  {metric} 异常: {e}')
    return None

def main():
    if not TOKEN:
        print('❌ 缺 BGEOMETRICS_TOKEN 环境变量')
        return

    all_rows = []
    for m in METRICS:
        print(f'抓取 {m} ...')
        data = fetch_metric(m)
        if not data:
            continue
        # 官方响应是 JSON 数组，每个元素包含 d (日期) 和指标值
        for item in data:
            date_str = item.get('d')
            # 根据返回的 key 提取值
            val = item.get(m) or item.get(m.replace('-', '_')) or item.get('price')
            if date_str and val is not None:
                all_rows.append({
                    'date': date_str,
                    'metric': m.upper(),
                    'value': float(val)
                })

    if all_rows:
        df = pd.DataFrame(all_rows)
        df['retrieved_at'] = datetime.now().isoformat()
        Path('data').mkdir(exist_ok=True)
        df.to_csv('data/bgeometrics_onchain.csv', index=False)
        print(f'✅ 已保存 {len(df)} 条链上估值数据')
    else:
        print('❌ 未获取到任何数据')

if __name__ == '__main__':
    main()