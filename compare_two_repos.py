# -*- coding: utf-8 -*-
"""compare_two_repos.py - 比对两个文件夹的内容是否一致"""
import hashlib
from pathlib import Path

DIR_A = Path(r'D:\HGZC')
DIR_B = Path(r'D:\HGZC-collectors')

# 只比对核心业务文件
KEY_DIRS = ['engines_v2', 'engines_v3', 'tools', 'collectors']

# 排除项
EXCLUDE = ['__pycache__', '.pyc', '.venv', '.git', '.bak']


def should_skip(p: Path):
    return any(x in str(p) for x in EXCLUDE)


def file_hash(p: Path):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def compare():
    print(f"\n{'='*70}")
    print(f"  两个仓库的内容比对")
    print(f"{'='*70}")
    print(f"  A: {DIR_A}")
    print(f"  B: {DIR_B}\n")
    
    total_same = 0
    total_diff = 0
    total_only_a = 0
    total_only_b = 0
    
    for sub_dir in KEY_DIRS:
        a_dir = DIR_A / sub_dir
        b_dir = DIR_B / sub_dir
        
        if not a_dir.exists() or not b_dir.exists():
            print(f"⚠️ {sub_dir}: 一侧不存在")
            continue
        
        print(f"\n📁 {sub_dir}/")
        
        # 收集所有 py 文件
        a_files = {f.relative_to(a_dir): f for f in a_dir.rglob('*.py') if not should_skip(f)}
        b_files = {f.relative_to(b_dir): f for f in b_dir.rglob('*.py') if not should_skip(f)}
        
        all_names = sorted(set(a_files.keys()) | set(b_files.keys()))
        
        for name in all_names:
            a_f = a_files.get(name)
            b_f = b_files.get(name)
            
            if a_f and b_f:
                a_h = file_hash(a_f)
                b_h = file_hash(b_f)
                if a_h == b_h:
                    total_same += 1
                else:
                    print(f"  🔴 内容不一致: {name}")
                    total_diff += 1
            elif a_f:
                print(f"  🟡 仅 A 存在: {name}")
                total_only_a += 1
            elif b_f:
                print(f"  🟢 仅 B 存在: {name}")
                total_only_b += 1
    
    print(f"\n{'='*70}")
    print(f"  📊 总结:")
    print(f"    ✅ 内容一致:  {total_same} 个文件")
    print(f"    🔴 内容不一致: {total_diff} 个文件")
    print(f"    🟡 仅 A 存在: {total_only_a} 个文件")
    print(f"    🟢 仅 B 存在: {total_only_b} 个文件")
    print(f"{'='*70}")
    
    if total_diff == 0 and total_only_a == 0 and total_only_b == 0:
        print(f"\n  🎉 两边内容 100% 一致！可能是符号链接或同步工具")
        print(f"  → 推 D:\\HGZC-collectors 完全安全\n")
    elif total_diff > 0:
        print(f"\n  🚨 有 {total_diff} 个文件内容不一致！")
        print(f"  → 请先确认哪边的版本是最新的（比 mtime）")
        print(f"  → 建议推 D:\\HGZC-collectors（代码仓库）\n")
    else:
        print(f"\n  ℹ️ 存在一侧独有的文件，请确认是否有遗漏\n")


if __name__ == '__main__':
    compare()