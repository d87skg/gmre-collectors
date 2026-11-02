# -*- coding: utf-8 -*-
"""
补丁 02: data_quality_check.py
  - 顶部 sys.path 兜底 + from tools.rrp_guard import ...
  - 替换 检查4 (RRP 双源交叉验证) 整段
  - 兼容 python xx.py 和 python -m engines_v2.xx
"""
import re
import shutil
from pathlib import Path

TARGET = Path(r"D:\HGZC\engines_v2\data_quality_check.py")
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
        "from tools.rrp_guard import run_rrp_guard, RRPStatus\n"
    )
    raw = raw[:m.start()] + block + raw[m.start():]
    print("[OK] inserted sys.path bootstrap + import")

# --- 2) 替换 检查4 ---
old_block = '''    # ============ 检查4：RRP 双源交叉验证 ============
    if 'RRP_BALANCE' in df.columns and 'RRP_NYFED' in df.columns:
        rrp_fred = float(df['RRP_BALANCE'].ffill().iloc[-1])
        rrp_nyfed = float(df['RRP_NYFED'].ffill().iloc[-1])
        if rrp_fred > 0:
            divergence = abs(rrp_fred - rrp_nyfed) / rrp_fred * 100
            if divergence < 15:
                checks.append({
                    'name': 'RRP 双源交叉',
                    'status': 'PASS',
                    'detail': f'FRED={rrp_fred:.2f}, NYFed={rrp_nyfed:.2f}, 偏差={divergence:.1f}%'
                })
            else:
                warnings.append(f'RRP 双源偏差 {divergence:.1f}%')
                checks.append({'name': 'RRP 双源交叉', 'status': 'WARN',
                               'detail': f'FRED={rrp_fred:.2f}, NYFed={rrp_nyfed:.2f}, 偏差={divergence:.1f}%'})
'''

new_block = '''    # ============ 检查4：RRP 双源对齐 (由 rrp_guard 统一判定) ============
    try:
        _g = run_rrp_guard(verbose=False)
        if _g.status in (RRPStatus.OK, RRPStatus.TIME_LAG):
            _detail = (
                f"FRED={_g.fred_value:.2f}@{_g.fred_date}, "
                f"NYFed={_g.nyfed_value:.2f}@{_g.nyfed_date}, "
                f"lag={_g.lag_days}d, 同日期偏差={_g.same_day_max_divergence_pct:.2f}%"
            )
            checks.append({
                'name': 'RRP 双源对齐',
                'status': 'PASS',
                'detail': _detail
            })
        elif _g.status == RRPStatus.DIVERGENCE:
            warnings.append(f'RRP 同日源分歧 {_g.same_day_max_divergence_pct:.1f}%')
            checks.append({
                'name': 'RRP 双源对齐',
                'status': 'WARN',
                'detail': _g.message
            })
        else:  # STALE / MISSING
            criticals.append(f'RRP 数据不可用: {_g.status.value}')
            checks.append({
                'name': 'RRP 双源对齐',
                'status': 'FAIL',
                'detail': _g.message
            })
    except Exception as _e:
        warnings.append(f'RRP guard 调用异常: {_e}')
        checks.append({
            'name': 'RRP 双源对齐',
            'status': 'WARN',
            'detail': f'guard error: {_e}'
        })
'''

if old_block not in raw:
    raise RuntimeError("未找到 检查4 原代码块")

raw = raw.replace(old_block, new_block, 1)
print("[OK] replaced 检查4 block")

TARGET.write_text(raw, encoding="utf-8")
print("[OK] written ->", TARGET)