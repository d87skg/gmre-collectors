# -*- coding: utf-8 -*-
"""push_to_github.py - 推送 GMRE 代码到 GitHub（gmre-collectors）"""
import sqlite3
import subprocess
import csv
from datetime import datetime
from pathlib import Path

# 🎯 仓库目录（推送目标）
REPO = Path(r'D:\HGZC-collectors')

# 🎯 数据源（从主库只读）
DB_PATH = Path(r'D:\HGZC\data\macro.db')

# 🎯 快照导出位置
SNAPSHOT_DIR = REPO / 'data' / 'github_snapshot'
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def export_snapshot():
    """导出关键表为 CSV（供 GitHub 云端审计）"""
    if not DB_PATH.exists():
        print(f"  ⚠️ 数据库不存在: {DB_PATH}")
        return []
    
    tables = [
        'daily_summary', 'probability_engine', 'defense_v4',
        'fragility_engine', 'stress_overlay_v2', 'gms_regimes',
        'caps_engine', 'lti_engine',
    ]
    
    conn = sqlite3.connect(str(DB_PATH))
    exported = []
    for table in tables:
        try:
            cursor = conn.execute(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT 100")
            rows = cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            
            with open(SNAPSHOT_DIR / f"{table}.csv", 'w',
                      newline='', encoding='utf-8-sig') as f:
                w = csv.writer(f)
                w.writerow(cols)
                w.writerows(rows)
            exported.append(table)
            print(f"  ✅ {table}.csv ({len(rows)} 行)")
        except Exception as e:
            print(f"  ⚠️ {table}: {e}")
    conn.close()
    return exported


def run_git(cmd, check=True):
    result = subprocess.run(
        cmd, cwd=str(REPO), shell=True,
        capture_output=True, text=True, encoding='utf-8', errors='ignore'
    )
    if check and result.returncode != 0:
        print(f"  ❌ {cmd[:60]}: {result.stderr[:150]}")
    else:
        print(f"  ✅ {cmd[:60]}")
    return result


def main():
    print(f"\n{'='*60}")
    print(f"  🚀 推送 GMRE 到 GitHub")
    print(f"  仓库: {REPO}")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")
    
    if not (REPO / '.git').exists():
        print(f"❌ {REPO} 不是 Git 仓库")
        return
    
    # 1. 导出快照
    print("📊 [1/4] 导出决策快照...")
    exported = export_snapshot()
    
    # 2. 状态检查
    print(f"\n🔍 [2/4] Git 状态...")
    result = run_git("git status --short", check=False)
    if not result.stdout.strip():
        print("  ℹ️ 工作区干净，无新变化")
        return
    print(f"  待推送:\n{result.stdout[:800]}")
    
    # 3. Commit
    print(f"\n📦 [3/4] 提交...")
    run_git("git add -A")
    commit_msg = f"P0/P1/P2 + 阶段A数据治理 - {datetime.now().strftime('%m-%d %H:%M')}"
    r = run_git(f'git commit -m "{commit_msg}"', check=False)
    if 'nothing to commit' in r.stdout:
        print("  ℹ️ 无新变化")
        return
    
    # 4. Push
    print(f"\n☁️ [4/4] 推送到 GitHub...")
    r = run_git("git push origin main", check=False)
    
    if r.returncode == 0:
        print(f"\n{'='*60}")
        print(f"  ✅ 推送成功！")
        print(f"  📦 快照: {len(exported)} 个表")
        print(f"  🔗 https://github.com/d87skg/gmre-collectors")
        print(f"{'='*60}\n")
    else:
        print(f"\n⚠️ 推送失败:\n{r.stderr[:400]}")


if __name__ == '__main__':
    main()