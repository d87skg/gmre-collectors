# -*- coding: utf-8 -*-
"""diagnose_repos.py - 诊断两个文件夹的 Git 关系"""
import subprocess
from pathlib import Path
from datetime import datetime

FOLDERS = [r'D:\HGZC', r'D:\HGZC-collectors']


def diagnose(folder):
    folder = Path(folder)
    print(f"\n{'='*60}")
    print(f"  📁 {folder}")
    print(f"{'='*60}")
    
    if not folder.exists():
        print(f"  ❌ 文件夹不存在")
        return
    
    git_dir = folder / '.git'
    print(f"  .git 目录: {'✅ 存在' if git_dir.exists() else '❌ 不存在'}")
    
    if git_dir.exists():
        # remote
        r = subprocess.run(['git', 'remote', '-v'], cwd=str(folder),
                          capture_output=True, text=True, encoding='utf-8', errors='ignore')
        print(f"  remote:")
        for line in r.stdout.strip().split('\n'):
            if line:
                print(f"    {line}")
        
        # 当前分支
        r = subprocess.run(['git', 'branch', '--show-current'], cwd=str(folder),
                          capture_output=True, text=True, encoding='utf-8')
        print(f"  当前分支: {r.stdout.strip()}")
        
        # 状态
        r = subprocess.run(['git', 'status', '--short'], cwd=str(folder),
                          capture_output=True, text=True, encoding='utf-8', errors='ignore')
        lines = [l for l in r.stdout.strip().split('\n') if l]
        print(f"  未提交文件: {len(lines)} 个")
        if lines:
            for l in lines[:10]:
                print(f"    {l}")
            if len(lines) > 10:
                print(f"    ... 还有 {len(lines)-10} 个")
        
        # 最近 commit
        r = subprocess.run(['git', 'log', '-1', '--format=%h %ci %s'], cwd=str(folder),
                          capture_output=True, text=True, encoding='utf-8', errors='ignore')
        print(f"  最近 commit: {r.stdout.strip()}")
    
    # 关键文件检查
    print(f"\n  📄 关键修复文件:")
    key_files = [
        'engines_v3/data_correction.py',
        'engines_v3/stress_overlay_v2.py',
        'engines_v3/run_v4.py',
        'tools/apply_feishu_override.py',
        'tools/data_sanitizer.py',
        'tools/compute_percentile.py',
    ]
    for f in key_files:
        fp = folder / f
        if fp.exists():
            mtime = datetime.fromtimestamp(fp.stat().st_mtime)
            print(f"    ✅ {f:<40s} (改于 {mtime.strftime('%m-%d %H:%M')})")
        else:
            print(f"    ❌ {f:<40s} (不存在)")


for f in FOLDERS:
    diagnose(f)

print(f"\n{'='*60}")
print(f"  🎯 判断依据：")
print(f"    - 只有 .git 存在的文件夹才是 Git 仓库")
print(f"    - remote 指向 github.com/d87skg/gmre-collectors 的才是对的")
print(f"    - 关键文件修改时间最新的才是您真正改过的那份")
print(f"{'='*60}")