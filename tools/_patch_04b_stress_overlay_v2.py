# -*- coding: utf-8 -*-
"""
补丁 04b: stress_overlay_v2.py
  - 顶部 sys.path 兜底 + from tools.rrp_guard import ...
  - 替换 S4 判定段: 用 rrp_guard 主源 + 门控
  - 依据实际文件行 100-114 精确匹配
"""
import re
import shutil
from pathlib import Path

TARGET = Path(r"D:\HGZC\engines_v3\stress_overlay_v2.py")

# 幂等: 若已是打过补丁状态, 先回滚到 .bak2
bak2 = TARGET.with_suffix(".py.bak2")
if bak2.exists():
    # 只在检测到已插入 guard 时回滚, 避免覆盖人工改动
    cur = TARGET.read_text(encoding="utf-8")
    if "from tools.rrp_guard import" in cur:
        shutil.copy2(bak2, TARGET)
        print("[OK] restored from .bak2")

BACKUP = TARGET.with_suffix(".py.bak3")
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

# --- 2) 替换 S4 判定段 (严格按原文行 100-114) ---
old_block = (
    "    # ============ S4 LIQUIDITY_BUFFER_DEPLETION（审计修正：不再是STRESS）============\n"
    "    s4_conditions = []\n"
    "    if len(rrp) >= 5:\n"
    "        rrp_now = float(rrp.iloc[-1])\n"
    "        s4_conditions.append(('RRP<50B', rrp_now < 50, f'{rrp_now:.1f}B'))\n"
    "\n"
    "    s4_triggered = sum(1 for c in s4_conditions if c[1]) >= 1\n"
    "    layers.append({\n"
    "        'layer': 'S4', 'name': 'LIQUIDITY_BUFFER_DEPLETION',\n"
    "        'triggered': s4_triggered,\n"
    "        'conditions': [{'name': c[0], 'met': c[1], 'value': c[2]} for c in s4_conditions],\n"
    "        'description': '流动性缓冲垫耗尽（非危机，仅缓冲消失）'\n"
    "    })\n"
)

new_block = (
    "    # ============ S4 LIQUIDITY_BUFFER_DEPLETION (由 rrp_guard 门控) ============\n"
    "    s4_conditions = []\n"
    "    try:\n"
    "        _g4 = run_rrp_guard(verbose=False)\n"
    "        if _g4.downstream_action == DownstreamAction.PROCEED and _g4.primary_value is not None:\n"
    "            _rrp_used = float(_g4.primary_value)\n"
    "            _rrp_src = _g4.primary_source\n"
    "            s4_conditions.append((f'RRP<50B ({_rrp_src})', _rrp_used < 50, f'{_rrp_used:.2f}B'))\n"
    "            s4_triggered = sum(1 for c in s4_conditions if c[1]) >= 1\n"
    "        elif _g4.downstream_action == DownstreamAction.OBSERVE:\n"
    "            s4_conditions.append(('RRP_OBSERVE', False, _g4.status.value))\n"
    "            s4_triggered = False\n"
    "        else:  # BLOCK\n"
    "            s4_conditions.append(('RRP_DATA_UNAVAILABLE', False, _g4.status.value))\n"
    "            s4_triggered = False\n"
    "    except Exception as _e:\n"
    "        s4_conditions.append(('RRP_GUARD_ERROR', False, str(_e)))\n"
    "        s4_triggered = False\n"
    "    layers.append({\n"
    "        'layer': 'S4', 'name': 'LIQUIDITY_BUFFER_DEPLETION',\n"
    "        'triggered': s4_triggered,\n"
    "        'conditions': [{'name': c[0], 'met': c[1], 'value': c[2]} for c in s4_conditions],\n"
    "        'description': '流动性缓冲垫耗尽（非危机，仅缓冲消失）'\n"
    "    })\n"
)

if old_block not in raw:
    raise RuntimeError("S4 原代码块仍未匹配, 请再次 dump 输出给作者")

raw = raw.replace(old_block, new_block, 1)
print("[OK] replaced S4 block")

TARGET.write_text(raw, encoding="utf-8")
print("[OK] written ->", TARGET)