# -*- coding: utf-8 -*-
import shutil
from pathlib import Path

TARGET = Path(r"D:\HGZC\engines_v3\run_v4.py")
BACKUP = TARGET.with_suffix(".py.bak_p0b")

shutil.copy2(TARGET, BACKUP)
print("[OK] backup ->", BACKUP)

raw = TARGET.read_text(encoding="utf-8")

old_line = '    print(f"  Base Regime: R4 (43.9%) | Fragility: F3 | Risk Gate: {gate}")'

new_block = '''    # v1.1 修复: 动态读取 regime 和 frag_level
    try:
        _regime_display = f"{regime['regime_label']} ({regime['confidence']*100:.1f}%)"
    except Exception:
        _regime_display = "N/A"
    try:
        _frag_display = frag_level
    except Exception:
        _frag_display = "N/A"
    print(f"  Base Regime: {_regime_display} | Fragility: {_frag_display} | Risk Gate: {gate}")'''

if old_line not in raw:
    raise RuntimeError("未找到硬编码行")

raw = raw.replace(old_line, new_block, 1)
print("[OK] replaced")

TARGET.write_text(raw, encoding="utf-8")
print("[OK] written ->", TARGET)