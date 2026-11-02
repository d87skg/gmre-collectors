# -*- coding: utf-8 -*-
"""
补丁 03: defense_v4.py
  - 顶部 sys.path 兜底 + from tools.rrp_guard import ...
  - 替换 防线3 判定段: 用 rrp_guard 的主源 + 门控
"""
import re
import shutil
from pathlib import Path

TARGET = Path(r"D:\HGZC\engines_v3\defense_v4.py")
BACKUP = TARGET.with_suffix(".py.bak2")

shutil.copy2(TARGET, BACKUP)
print("[OK] backup ->", BACKUP)

raw = TARGET.read_text(encoding="utf-8")

# --- 1) 顶部 sys.path + import ---
if "from tools.rrp_guard import" in raw:
    print("[SKIP] import already present")
else:
    m = re.search(r"^(\s*(?:import|from)\s+\S+)", raw, flags=re.MULTILINE)
    if not m:
        raise RuntimeError("找不到 import 段")
    block = (
        "import sys as _sys\n"
        "from pathlib import Path as _Path\n"
        "_PROJECT_ROOT = _Path(__file__).resolve().parents[1]\n"
        "if str(_PROJECT_ROOT) not in _sys.path:\n"
        "    _sys.path.insert(0, str(_PROJECT_ROOT))\n"
        "from tools.rrp_guard import run_rrp_guard, DownstreamAction, RRPStatus\n"
    )
    raw = raw[:m.start()] + block + raw[m.start():]
    print("[OK] inserted sys.path bootstrap + import")

# --- 2) 替换 防线3 判定段 ---
old_block = '''    # ============ 防线3：LIQUIDITY_BUFFER_DEPLETION ============
    d3_conds = []
    if len(rrp) >= 1:
        d3_conds.append(('RRP<50B', float(rrp.iloc[-1]) < 50, f'{float(rrp.iloc[-1]):.1f}B'))
    d3 = sum(1 for c in d3_conds if c[1]) >= 1
    lines.append({
        'line': '防线3', 'name': 'LIQUIDITY_BUFFER',
        'triggered': d3, 'conditions': d3_conds,
        'action': '流动性缓冲耗尽，保留现金'
    })
'''

new_block = '''    # ============ 防线3：LIQUIDITY_BUFFER_DEPLETION (由 rrp_guard 门控) ============
    d3_conds = []
    try:
        _g3 = run_rrp_guard(verbose=False)
        if _g3.downstream_action == DownstreamAction.PROCEED and _g3.primary_value is not None:
            _rrp_used = float(_g3.primary_value)
            _rrp_src = _g3.primary_source
            d3_conds.append((f'RRP<50B ({_rrp_src})', _rrp_used < 50, f'{_rrp_used:.2f}B'))
            d3 = sum(1 for c in d3_conds if c[1]) >= 1
        elif _g3.downstream_action == DownstreamAction.OBSERVE:
            d3_conds.append(('RRP_OBSERVE', False, _g3.status.value))
            d3 = False
        else:  # BLOCK
            d3_conds.append(('RRP_DATA_UNAVAILABLE', False, _g3.status.value))
            d3 = False
    except Exception as _e:
        d3_conds.append(('RRP_GUARD_ERROR', False, str(_e)))
        d3 = False
    lines.append({
        'line': '防线3', 'name': 'LIQUIDITY_BUFFER',
        'triggered': d3, 'conditions': d3_conds,
        'action': '流动性缓冲耗尽，保留现金'
    })
'''

if old_block not in raw:
    raise RuntimeError("未找到 防线3 原代码块")

raw = raw.replace(old_block, new_block, 1)
print("[OK] replaced 防线3 block")

TARGET.write_text(raw, encoding="utf-8")
print("[OK] written ->", TARGET)