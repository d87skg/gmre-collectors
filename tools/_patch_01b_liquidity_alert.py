# -*- coding: utf-8 -*-
"""
补丁 01b: liquidity_alert.py
  - 顶部加 sys.path 兜底 + from tools.rrp_guard import ...
  - 替换 预警1.5 整段 (RRP 双源交叉验证)
  - 兼容: python xx.py 和 python -m engines_v2.xx 两种运行方式
"""
import re
import shutil
from pathlib import Path

TARGET = Path(r"D:\HGZC\engines_v2\liquidity_alert.py")
BACKUP = TARGET.with_suffix(".py.bak3")

# 幂等: 若已经打过 01b 补丁, 先恢复
bak2 = TARGET.with_suffix(".py.bak2")
if bak2.exists():
    shutil.copy2(bak2, TARGET)
    print("[OK] restored from .bak2")

shutil.copy2(TARGET, BACKUP)
print("[OK] backup ->", BACKUP)

raw = TARGET.read_text(encoding="utf-8")

# --- 1) 顶部插入 sys.path 兜底 + rrp_guard import ---
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

# --- 2) 替换 预警1.5 整段 ---
old_block = '''    # ============ 预警1.5：RRP 双源交叉验证 ============
    try:
        conn = sqlite3.connect(DB_PATH)
        rrp_fred = _load_series(conn, 'RRP_BALANCE', 5)
        rrp_nyfed = _load_series(conn, 'RRP_NYFED', 5)
        conn.close()

        if len(rrp_fred) >= 1 and len(rrp_nyfed) >= 1:
            fred_val = float(rrp_fred.iloc[-1])       # 十亿美元
            nyfed_val = float(rrp_nyfed.iloc[-1])     # 十亿美元

            # 两者理论上应该一致（差异<5%为正常）
            if fred_val > 0:
                divergence_pct = abs(fred_val - nyfed_val) / fred_val * 100
                if divergence_pct > 15:
                    alerts.append({
                        'level': 'WARNING',
                        'type': 'RRP_SOURCE_DIVERGENCE',
                        'msg': f"⚠️ RRP数据源偏差 {divergence_pct:.1f}%：FRED={fred_val:.2f}, 纽约联储={nyfed_val:.2f}，建议人工复核",
                        'metric': {
                            'fred_billion': round(fred_val, 3),
                            'nyfed_billion': round(nyfed_val, 3),
                            'divergence_pct': round(divergence_pct, 2)
                        }
                    })
    except Exception:
        pass
'''

new_block = '''    # ============ 预警1.5：RRP 双源对齐 (由 rrp_guard 统一门控) ============
    try:
        _guard = run_rrp_guard(verbose=False)

        if _guard.status == RRPStatus.DIVERGENCE:
            alerts.append({
                'level': 'WARNING',
                'type': 'RRP_SOURCE_DIVERGENCE',
                'msg': _guard.message,
                'metric': {
                    'fred_billion': _guard.fred_value,
                    'nyfed_billion': _guard.nyfed_value,
                    'divergence_pct': _guard.same_day_max_divergence_pct
                }
            })
        elif _guard.status == RRPStatus.TIME_LAG:
            alerts.append({
                'level': 'INFO',
                'type': 'RRP_TIME_LAG',
                'msg': _guard.message,
                'metric': {
                    'fred_date': _guard.fred_date.isoformat() if _guard.fred_date else None,
                    'nyfed_date': _guard.nyfed_date.isoformat() if _guard.nyfed_date else None,
                    'lag_days': _guard.lag_days,
                    'primary_source': _guard.primary_source,
                    'primary_value': _guard.primary_value
                }
            })
        elif _guard.status in (RRPStatus.STALE, RRPStatus.MISSING):
            alerts.append({
                'level': 'WARNING',
                'type': 'RRP_DATA_UNAVAILABLE',
                'msg': _guard.message,
                'metric': {'status': _guard.status.value}
            })
    except Exception as _e:
        alerts.append({
            'level': 'WARNING',
            'type': 'RRP_GUARD_ERROR',
            'msg': f'RRP guard 调用失败: {_e}',
            'metric': {}
        })
'''

if old_block not in raw:
    raise RuntimeError("未找到 预警1.5 原代码块, 请人工核对")

raw = raw.replace(old_block, new_block, 1)
print("[OK] replaced 预警1.5 block")

TARGET.write_text(raw, encoding="utf-8")
print("[OK] written ->", TARGET)