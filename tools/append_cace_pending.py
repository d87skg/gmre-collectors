# -*- coding: utf-8 -*-
import csv
from pathlib import Path

P = Path(r"D:\HGZC\reports\stagflation_watch_2026Q3\pending_issues.csv")

new_rows = [
    ("2026-10-08","P1","CACE引擎设计","Cross-Asset Correlation Engine三子维度","10-21后实施","10-21后"),
    ("2026-10-08","P1","NDX数据源接入","BTC-NDX相关性","Yahoo或AKShare","10-21后"),
    ("2026-10-08","P1","稳定币供应量接入","USDT/USDC净发行","DefiLlama API","10-21后"),
    ("2026-10-08","P1","ETF机构流向接入","Farside","已可获取","10-21后"),
    ("2026-10-08","P2","稳定币交易所净流","CryptoQuant/Glassnode","评估数据源","10-21后"),
    ("2026-10-08","P2","TLT数据接入","BTC-利率相关性","Yahoo","10-21后"),
    ("2026-10-08","P2","黄金实时价接入","BTC-GOLD相关性","FRED/Yahoo","10-21后"),
    ("2026-10-08","P2","Chain_G设计","Fed→NDX→BTC传导","新增传导链","10-21后"),
    ("2026-10-08","P2","CRSI扩展","新增Cross-Asset/Institutional/Stablecoin三维","CRSI设计输入","10-21后"),
]

with P.open("a", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    for row in new_rows:
        w.writerow(row)

print(f"追加 {len(new_rows)} 条")