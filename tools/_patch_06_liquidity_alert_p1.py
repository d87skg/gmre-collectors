# -*- coding: utf-8 -*-
"""
补丁 06: liquidity_alert.py 预警 1 接入 rrp_guard
  - 原: rrp_now 直接读 df['RRP_B'] (FRED 旧数据)
  - 新: 优先用 guard 主源 (NYFed), 降级时回退
  - 只改预警 1, 不动 NET_LIQ 计算
"""
import shutil
from pathlib import Path

TARGET = Path(r"D:\HGZC\engines_v2\liquidity_alert.py")
BACKUP = TARGET.with_suffix(".py.bak5")

shutil.copy2(TARGET, BACKUP)
print("[OK] backup ->", BACKUP)

raw = TARGET.read_text(encoding="utf-8")

old_block = '''    # ============ 预警1：RRP 耗尽 ============
    rrp_now = float(df['RRP_B'].iloc[-1])
    rrp_20 = float(df['RRP_B'].iloc[-min(20, len(df))])
    rrp_20d_chg = rrp_now - rrp_20

    if rrp_now < RRP_DEPLETION_THRESHOLD:
        alerts.append({
            'level': 'CRITICAL',
            'type': 'RRP_DEPLETION',
            'msg': f"⚠️ RRP 余额仅 {rrp_now*10:.1f} 亿美元（{rrp_now:.2f} 十亿），接近耗尽",
            'metric': {'rrp_billion_usd': round(rrp_now, 3)}
        })
'''

new_block = '''    # ============ 预警1：RRP 耗尽 (由 rrp_guard 统一主源) ============
    try:
        _g1 = run_rrp_guard(verbose=False)
    except Exception:
        _g1 = None

    if (_g1 is not None
            and _g1.downstream_action == DownstreamAction.PROCEED
            and _g1.primary_value is not None):
        rrp_now = float(_g1.primary_value)
        _rrp_src = _g1.primary_source
    else:
        rrp_now = float(df['RRP_B'].iloc[-1])
        _rrp_src = "RRP_BALANCE_FALLBACK"

    rrp_20 = float(df['RRP_B'].iloc[-min(20, len(df))])
    rrp_20d_chg = rrp_now - rrp_20

    if rrp_now < RRP_DEPLETION_THRESHOLD:
        alerts.append({
            'level': 'CRITICAL',
            'type': 'RRP_DEPLETION',
            'msg': f"⚠️ RRP 余额仅 {rrp_now*10:.1f} 亿美元（{rrp_now:.2f} 十亿），接近耗尽 [{_rrp_src}]",
            'metric': {'rrp_billion_usd': round(rrp_now, 3), 'source': _rrp_src}
        })
'''

if old_block not in raw:
    raise RuntimeError("未找到 预警1 原代码块, 请核对文件")

raw = raw.replace(old_block, new_block, 1)
print("[OK] replaced 预警1 block")

TARGET.write_text(raw, encoding="utf-8")
print("[OK] written ->", TARGET)