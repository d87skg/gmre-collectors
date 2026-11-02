# tools/inspect_parquet.py
import pandas as pd
import os

# 👇 修正：直接指向你解压出来的这两个文件夹
base_paths = {
    'v3版': r'D:\btc_carry_v3',
    'full版': r'D:\btc_carry_full'
}

files_to_check = [
    'spot_1h.parquet',
    'perp_1h.parquet',
    'funding_binance.parquet',
    'btc_merged.parquet',
    'metrics_2026.parquet'
]

for version, base_path in base_paths.items():
    print(f"\n{'='*60}")
    print(f"📦 正在检查: {version} (路径: {base_path})")
    
    if not os.path.exists(base_path):
        print(f"❌ 文件夹不存在，请检查！")
        continue

    for file in files_to_check:
        file_path = os.path.join(base_path, file)
        if os.path.exists(file_path):
            try:
                df = pd.read_parquet(file_path)
                print(f"  ✅ {file:<25} | 行数: {len(df):<8} | 列名: {df.columns.tolist()}")
            except Exception as e:
                print(f"  ⚠️ {file:<25} | 读取失败: {e}")
        else:
            print(f"  ❌ {file:<25} | 未找到")