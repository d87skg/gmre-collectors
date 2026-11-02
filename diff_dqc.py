# -*- coding: utf-8 -*-
"""diff_dqc.py - 比对 data_quality_check.py 两份文件"""
from pathlib import Path
from datetime import datetime
import hashlib

FILES = {
    'A (D:\\HGZC)':            Path(r'D:\HGZC\engines_v2\data_quality_check.py'),
    'B (D:\\HGZC-collectors)': Path(r'D:\HGZC-collectors\engines_v2\data_quality_check.py'),
}

def file_info(p):
    if not p.exists():
        return None
    stat = p.stat()
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return {
        'size': stat.st_size,
        'mtime': datetime.fromtimestamp(stat.st_mtime),
        'md5': h.hexdigest()[:16],
    }

print(f"\n{'='*70}")
print(f"  data_quality_check.py 比对")
print(f"{'='*70}\n")

infos = {}
for name, p in FILES.items():
    info = file_info(p)
    infos[name] = info
    if info:
        print(f"  📄 {name}")
        print(f"     路径: {p}")
        print(f"     大小: {info['size']} bytes")
        print(f"     修改: {info['mtime'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"     MD5:  {info['md5']}\n")
    else:
        print(f"  ❌ {name}: 文件不存在\n")

# 判断哪个新
a, b = infos.get('A (D:\\HGZC)'), infos.get('B (D:\\HGZC-collectors)')
if a and b:
    print(f"{'='*70}")
    if a['md5'] == b['md5']:
        print(f"  ✅ 内容完全一致（但为何会报不一致？可能是比对脚本误判）")
    else:
        if a['mtime'] > b['mtime']:
            print(f"  🟢 A (D:\\HGZC) 更新")
            print(f"     A 比 B 新 {int((a['mtime'] - b['mtime']).total_seconds())} 秒")
            print(f"     → 建议：先把 A 复制到 B，再推 B")
        else:
            print(f"  🔵 B (D:\\HGZC-collectors) 更新")
            print(f"     B 比 A 新 {int((b['mtime'] - a['mtime']).total_seconds())} 秒")
            print(f"     → 建议：直接用 B 推送（B 的更新版本已在仓库）")
    print(f"{'='*70}\n")

    # 显示前 50 行的 diff
    print(f"🔍 内容 diff（前 50 行，-A +B）:\n")
    import difflib
    with open(FILES['A (D:\\HGZC)'], 'r', encoding='utf-8', errors='ignore') as f:
        a_lines = f.readlines()
    with open(FILES['B (D:\\HGZC-collectors)'], 'r', encoding='utf-8', errors='ignore') as f:
        b_lines = f.readlines()
    diff = list(difflib.unified_diff(a_lines, b_lines, fromfile='A', tofile='B', lineterm=''))
    if not diff:
        print("  (无差异)")
    else:
        for line in diff[:50]:
            print(f"  {line.rstrip()}")
        if len(diff) > 50:
            print(f"  ... 还有 {len(diff)-50} 行差异")