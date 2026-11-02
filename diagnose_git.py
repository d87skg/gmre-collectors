# -*- coding: utf-8 -*-
"""diagnose_git.py - Git 状态诊断（只读，不改任何东西）"""
import subprocess
from pathlib import Path

REPO = Path(r'D:\HGZC-collectors')


def run(cmd):
    r = subprocess.run(cmd, cwd=str(REPO), shell=True,
                      capture_output=True, text=True, encoding='utf-8', errors='ignore')
    return r.stdout.strip(), r.stderr.strip(), r.returncode


print(f"\n{'='*70}")
print(f"  Git 诊断 - {REPO}")
print(f"{'='*70}\n")

# 1. 当前分支
out, _, _ = run('git branch --show-current')
print(f"当前分支: {out}")

# 2. 本地 HEAD
out, _, _ = run('git log -1 --format="%h %s"')
print(f"本地 HEAD: {out}")

# 3. Fetch 远程（只读，不改本地任何东西）
print(f"\n📡 正在 fetch 远程（只读操作）...")
out, err, code = run('git fetch origin')
if code != 0:
    print(f"  ❌ fetch 失败: {err[:200]}")
    exit(1)
print(f"  ✅ fetch 成功")

# 4. 远程 HEAD
out, _, _ = run('git log -1 --format="%h %s" origin/main')
print(f"远程 HEAD: {out}")

# 5. 本地 vs 远程差异
print(f"\n{'='*70}")
print(f"  🔍 差异分析")
print(f"{'='*70}\n")

# 本地领先的 commit
out, _, _ = run('git log --oneline origin/main..HEAD')
local_ahead = [l for l in out.split('\n') if l]
print(f"🟢 本地领先远程 {len(local_ahead)} 个 commit（这些是您的修复）:")
for l in local_ahead[:20]:
    print(f"   {l}")
if len(local_ahead) > 20:
    print(f"   ... 还有 {len(local_ahead)-20} 个")

# 远程领先的 commit
out, _, _ = run('git log --oneline HEAD..origin/main')
remote_ahead = [l for l in out.split('\n') if l]
print(f"\n🔴 远程领先本地 {len(remote_ahead)} 个 commit（这些需要 pull）:")
for l in remote_ahead[:20]:
    print(f"   {l}")
if len(remote_ahead) > 20:
    print(f"   ... 还有 {len(remote_ahead)-20} 个")

# 6. 冲突风险文件
print(f"\n{'='*70}")
print(f"  ⚠️ 冲突风险分析（两边都改了同一个文件？）")
print(f"{'='*70}\n")

out, _, _ = run('git diff --name-only HEAD...origin/main')
local_changed = set(out.split('\n'))

out, _, _ = run('git diff --name-only origin/main...HEAD')
remote_changed = set(out.split('\n'))

both_changed = local_changed & remote_changed
if both_changed:
    print(f"  🔴 两边都改了 {len(both_changed)} 个文件（可能有冲突）:")
    for f in sorted(both_changed):
        if f:
            print(f"     {f}")
else:
    print(f"  ✅ 没有共同修改的文件，pull 不会冲突")

# 7. 建议
print(f"\n{'='*70}")
print(f"  📋 建议操作")
print(f"{'='*70}\n")
if len(local_ahead) > 0 and len(remote_ahead) > 0:
    if both_changed:
        print(f"  ⚠️ 双方都有修改，需要手动处理冲突")
        print(f"  推荐：git pull --rebase origin main")
    else:
        print(f"  ✅ 无冲突，可以安全 pull --rebase")
        print(f"  推荐：git pull --rebase origin main")
elif len(remote_ahead) > 0 and len(local_ahead) == 0:
    print(f"  ✅ 本地无新 commit，直接 pull 即可")
    print(f"  推荐：git pull origin main")
else:
    print(f"  ✅ 应该是快速前进，直接 push 即可")

print(f"\n{'='*70}\n")