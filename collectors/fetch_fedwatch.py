"""
CME FedWatch 利率预期
库: cme-fedwatch（数据来自 CME 官方结算价 + FRED）
输出: data/cme_fedwatch.csv

实际返回结构:
{
  "effr": 3.88,
  "current_target": "3.75%-4.00%",
  "target_source": "fred",
  "trade_date": "2026-10-01",
  "meetings": [...]
}
"""
import json
import sys
from datetime import datetime
from pathlib import Path
import pandas as pd

OUT = Path('data/cme_fedwatch.csv')


def fetch(mode='all'):
    from cme_fedwatch import get_probabilities
    return get_probabilities(mode)


def main():
    data = None
    # 先试 all，失败试 next
    for mode in ['all', 'next']:
        try:
            data = fetch(mode)
            if data:
                print(f'mode={mode} 成功')
                break
        except Exception as e:
            print(f'mode={mode} 失败: {e}')

    if not data:
        print('❌ 无数据')
        sys.exit(1)

    print('===== 原始数据 =====')
    print(json.dumps(data, indent=2, ensure_ascii=False)[:3000])
    print('===================')

    # 基础字段
    rows = []
    base = {
        'date': data.get('trade_date', datetime.utcnow().strftime('%Y-%m-%d')),
        'effr': data.get('effr'),
        'current_target': data.get('current_target'),
        'target_source': data.get('target_source'),
        'retrieved_at': datetime.utcnow().isoformat(),
    }

    # 会议概率
    meetings = data.get('meetings', [])
    if meetings:
        for m in meetings:
            row = dict(base)
            if isinstance(m, dict):
                row.update(m)
            rows.append(row)
    else:
        # 没有会议数据，只存基础行
        rows.append(base)

    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f'已保存: {OUT} ({len(df)} 行)')
    print(df.to_string())


if __name__ == '__main__':
    main()