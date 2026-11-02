# -*- coding: utf-8 -*-
"""sync_to_collectors.py - 从 D:\HGZC 同步到 D:\HGZC-collectors（单向 A→B）"""
import shutil
import fnmatch
from pathlib import Path
from datetime import datetime

SOURCE = Path(r'D:\HGZC')
TARGET = Path(r'D:\HGZC-collectors')

# 需要同步的目录（只覆盖 + 新增，不删除 B 独有的文件）
INCLUDE_DIRS = [
    'engines_v2', 'engines_v3', 'tools', 'collectors',
    'docs', 'core', 'config',
]

# 需要同步的根目录文件
INCLUDE_ROOT = [
    'auto_daily.bat',
    'push_to_github.py',
    'diagnose_git.py',
    'compare_two_repos.py',
    'diagnose_repos.py',
    'diff_dqc.py',
    'sync_to_collectors.py',
]

# 排除规则（目录名或文件名匹配）
EXCLUDE_PATTERNS = [
    '__pycache__', '*.pyc', '*.pyo',
    '*.bak', '*.bak2', '*.bak3', '*.bak_p*', '*.bak_hy*',
    '*.log', '*.tmp', '*.temp',
    '*.db', '*.db-journal', '*.db-wal', '*.db-shm',
    '.env', '.venv', 'venv',
]


def should_exclude(p: Path) -> bool:
    # 检查路径中任何一段是否匹配排除规则
    for part in p.parts:
        for pat in EXCLUDE_PATTERNS:
            if fnmatch.fnmatch(part, pat):
                return True
    return False


def sync_dir(rel_dir: str) -> tuple:
    src_dir = SOURCE / rel_dir
    dst_dir = TARGET / rel_dir
    if not src_dir.exists():
        return 0, 0, 0

    copied, skipped, failed = 0, 0, 0
    failed_files = []

    for src_file in src_dir.rglob('*'):
        if not src_file.is_file():
            continue
        if should_exclude(src_file):
            skipped += 1
            continue

        rel_path = src_file.relative_to(SOURCE)
        dst_file = TARGET / rel_path
        try:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)  # copy2 保留 mtime
            copied += 1
        except Exception as e:
            failed += 1
            failed_files.append(f"{rel_path}: {str(e)[:60]}")

    return copied, skipped, failed


def sync_root_files() -> int:
    copied = 0
    for fname in INCLUDE_ROOT:
        src = SOURCE / fname
        if not src.exists():
            continue
        dst = TARGET / fname
        try:
            shutil.copy2(src, dst)
            copied += 1
            print(f"  ✅ {fname}")
        except Exception as e:
            print(f"  ❌ {fname}: {e}")
    return copied


def main():
    print(f"\n{'='*60}")
    print(f"  GMRE 4.0 同步工具 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  源:   {SOURCE}")
    print(f"  目标: {TARGET}")
    print(f"{'='*60}\n")

    if not TARGET.exists():
        print(f"❌ 目标目录不存在: {TARGET}")
        return

    total_copied = 0
    total_skipped = 0
    total_failed = 0

    for rel_dir in INCLUDE_DIRS:
        src_dir = SOURCE / rel_dir
        if not src_dir.exists():
            print(f"📁 {rel_dir}/  (源不存在，跳过)")
            continue

        print(f"\n📁 {rel_dir}/")
        c, s, f = sync_dir(rel_dir)
        print(f"  复制: {c} | 排除: {s} | 失败: {f}")
        total_copied += c
        total_skipped += s
        total_failed += f

    print(f"\n📄 根目录文件:")
    rc = sync_root_files()
    total_copied += rc

    print(f"\n{'='*60}")
    print(f"  ✅ 同步完成")
    print(f"  复制: {total_copied} 个文件")
    print(f"  排除: {total_skipped} 个文件（缓存/数据库/备份）")
    print(f"  失败: {total_failed} 个文件")
    print(f"{'='*60}")

    if total_failed > 0:
        print(f"\n⚠️ 有 {total_failed} 个文件失败，请检查权限或路径")
    else:
        print(f"\n✅ 下一步: 在 D:\\HGZC-collectors 中执行 git 推送")
        print(f"   具体命令见下方")


if __name__ == '__main__':
    main()