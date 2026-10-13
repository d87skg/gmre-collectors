# -*- coding: utf-8 -*-
"""hourly_all.py - run hourly collectors (skip missing)"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent

collectors = [
    "okx_liquidation.py",
    "binance_funding.py",
    "binance_oi.py",
    "bybit_perp.py",
]

failed = []
for script in collectors:
    path = HERE / script
    if not path.exists():
        print(f"[skip] {script} not found")
        continue
    result = subprocess.run(
        [sys.executable, str(path)],
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        failed.append(script)
        print(f"[fail] {script} (exit {result.returncode})")
    else:
        print(f"[ok] {script}")

if failed:
    print(f"\nfailed: {failed}")
    sys.exit(1)
print("all done")