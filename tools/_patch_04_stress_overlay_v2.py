# -*- coding: utf-8 -*-
"""
补丁 04: stress_overlay_v2.py
  - 顶部 sys.path 兜底 + from tools.rrp_guard import ...
  - 替换 S4 判定段: 用 rrp_guard 主源 + 门控
"""
import re
import shutil
from pathlib import Path

TARGET = Path(r"D:\HGZC\engines_v3\stress_overlay_v2.py")
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

# --- 2) 替换 S4 判定段 ---
old_block = '''    # ============ S4 LIQUIDITY_BUFFER_DEPLETION（审计修正：不再是STRESS） ============
    s4_conditions = []
    if len(rrp) >= 5:
        rrp_now = float(rrp.iloc[-1])
        s4_conditions.append(('RRP<50B', rrp_now < 50, f'{rrp_now:.1f}B'))

    s4_triggered = sum(1 for c in s4_conditions if c[1]) >= 1
    layers.append({
        'layer': 'S4', 'name': 'LIQUIDITY_BUFFER_DEPLETION',
        'triggered': s4_triggered,
        'conditions': [{'name': c[0], 'met': c[1], 'value': c[2]} for c in s4_conditions],
        'description': '流动性缓冲垫耗尽（非危机，仅缓冲消失）'
    })
'''

new_block = '''    # ============ S4 LIQUIDITY_BUFFER_DEPLETION (由 rrp_guard 门控) ============
    s4_conditions = []
    try:
        _g4 = run_rrp_guard(verbose=False)
        if _g4.downstream_action == DownstreamAction.PROCEED and _g4.primary_value is not None:
            _rrp_used = float(_g4.primary_value)
            _rrp_src = _g4.primary_source
            s4_conditions.append((f'RRP<50B ({_rrp_src})', _rrp_used < 50, f'{_rrp_used:.2f}B'))
            s4_triggered = sum(1 for c in s4_conditions if c[1]) >= 1
        elif _g4.downstream_action == DownstreamAction.OBSERVE:
            s4_conditions.append(('RRP_OBSERVE', False, _g4.status.value))
            s4_triggered = False
        else:  # BLOCK
            s4_conditions.append(('RRP_DATA_UNAVAILABLE', False, _g4.status.value))
            s4_triggered = False
    except Exception as _e:
        s4_conditions.append(('RRP_GUARD_ERROR', False, str(_e)))
        s4_triggered = False
    layers.append({
        'layer': 'S4', 'name': 'LIQUIDITY_BUFFER_DEPLETION',
        'triggered': s4_triggered,
        'conditions': [{'name': c[0], 'met': c[1], 'value': c[2]} for c in s4_conditions],
        'description': '流动性缓冲垫耗尽（非危机，仅缓冲消失）'
    })
'''

if old_block not in raw:
    raise RuntimeError("未找到 S4 原代码块")

raw = raw.replace(old_block, new_block, 1)
print("[OK] replaced S4 block")

TARGET.write_text(raw, encoding="utf-8")
print("[OK] written ->", TARGET)