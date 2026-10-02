"""
CME FedWatch 利率预期
库: cme-fedwatch（数据来自 CME 官方结算价 + FRED）
输出: data/cme_fedwatch.csv
"""
import json
import sys
from datetime import datetime
from pathlib import Path
import pandas as pd

OUT = Path('data/cme_fedwatch.csv')


def fetch():
    from cme_fedwatch import get_probabilities
    # 获取未来所有 FOMC 会议的概率
    data = get_probabilities('all')
    return data


def main():
    try:
        data = fetch()
        print('===== 原始数据 =====')
        print(json.dumps(data, indent=2, ensure_ascii=False)[:3000])
        print('===================')
    except Exception as e:
        print(f'❌ 失败: {e}')
        sys.exit(1)

    # 写入 CSV（结构自适应）
    rows = []
    if isinstance(data, dict):
        for meeting, probs in data.items():
            if isinstance(probs, dict):
                row = {'meeting': meeting, 'retrieved_at': datetime.utcnow().isoformat()}
                for k, v in probs.items():
                    row[k] = v
                rows.append(row)
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                item['retrieved_at'] = datetime.utcnow().isoformat()
                rows.append(item)

    if not rows:
        print('⚠️ 无结构化数据，只保存原始 JSON')
        OUT.parent.mkdir(parents=True, exist_ok=True)
        Path('data/cme_fedwatch_raw.json').write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
        return

    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f'已保存: {OUT} ({len(df)} 行)')
    print(df.head().to_string())


if __name__ == '__main__':
    main()