# -*- coding: utf-8 -*-
"""
补丁 09: HY 利差显示措辞修复
  - defense_v4.py: 动态显示"走阔/收窄", 符号用 +/-
  - invalidation_conditions.py: 措辞改为"波动(绝对值)"
"""
import shutil
from pathlib import Path

# ============ 文件 1: defense_v4.py ============
T1 = Path(r"D:\HGZC\engines_v3\defense_v4.py")
B1 = T1.with_suffix(".py.bak_hy2")
shutil.copy2(T1, B1)
print("[OK] backup ->", B1)

raw1 = T1.read_text(encoding="utf-8")

old1 = "        d5_conds.append(('HY 20D走阔>10%', hyg_20d_chg > 0.10, f'{hyg_20d_chg*100:.2f}%'))"
new1 = (
    "        _hy_dir = '走阔' if hyg_20d_chg > 0 else '收窄'\n"
    "        d5_conds.append((f'HY 20D{_hy_dir}>10%', hyg_20d_chg > 0.10, f'{hyg_20d_chg*100:+.2f}%'))"
)

if old1 not in raw1:
    raise RuntimeError("defense_v4.py 未找到目标行")
raw1 = raw1.replace(old1, new1, 1)
T1.write_text(raw1, encoding="utf-8")
print("[OK] defense_v4.py 更新")

# ============ 文件 2: invalidation_conditions.py ============
T2 = Path(r"D:\HGZC\engines_v3\invalidation_conditions.py")
B2 = T2.with_suffix(".py.bak_hy2")
shutil.copy2(T2, B2)
print("[OK] backup ->", B2)

raw2 = T2.read_text(encoding="utf-8")

old2a = "    # 5. HY利差稳定（20日变化 < 10%）"
new2a = "    # 5. HY利差波动（|20日变化| < 10%）"

old2b = "            'name': 'HY利差稳定（20D<10%）',"
new2b = "            'name': 'HY利差波动（|20D|<10%）',"

if old2a not in raw2:
    raise RuntimeError("invalidation_conditions.py 未找到注释行")
if old2b not in raw2:
    raise RuntimeError("invalidation_conditions.py 未找到 name 行")

raw2 = raw2.replace(old2a, new2a, 1)
raw2 = raw2.replace(old2b, new2b, 1)
T2.write_text(raw2, encoding="utf-8")
print("[OK] invalidation_conditions.py 更新")

print("\n[DONE] 请运行:")
print("  python -m py_compile D:\\HGZC\\engines_v3\\defense_v4.py")
print("  python -m py_compile D:\\HGZC\\engines_v3\\invalidation_conditions.py")