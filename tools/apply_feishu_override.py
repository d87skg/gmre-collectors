# -*- coding: utf-8 -*-
"""tools/apply_feishu_override.py - v4.1 已退役写库能力，改为隔离到 quarantine

【历史行为（已废除）】
读 feishu_snapshot 的最新一行，把 15 个字段按硬编码乘数（TGA ×1000、
准备金 ×1e6 …）换算后 `INSERT OR REPLACE INTO observations`，source 统一
写成 'feishu_override'。后果就是审计里的四条致命问题：

  1. 真理源倒挂 —— 一条从"已发送文本"正则反解出来的数字，优先级高于
     FRED / NYFed / Treasury 的官方读数；
  2. 时间戳篡改 —— 写入日期取报文时间，不是真实观测日，周末也照打一针；
  3. 量纲错位 —— 飞书原文是"十亿美元"，乘数写成 1000 后变成"百万美元"，
     结果与 TGA_DAILY（treasury_fiscal_data, 真·百万美元）混在同一张表里；
  4. 无锁覆写 —— 无版本、无 revision、无冲突检测，直接 REPLACE。

【现在】
只做一件事：把飞书数值搬进 `quarantine` 隔离区（带原始值、乘数、来源、
捕获时刻），供人工审计比对。**永不写入 observations。**
官方数值一律由 FRED / NYFed / Treasury 经 append-only 管道入库。
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SANDBOX_ROOTS = (Path(r'D:\HGZC-v41-sandbox'), Path(r'D:\HGZC-v41-sandbox-collectors'))
DB_PATH = ROOT / 'data' / 'macro.db'

# 原映射保留下来仅作"审计对照表"，不再参与任何写库
OVERRIDE_MAP = {
    'gold':         ('GOLD_PRICE', 1.0, 'usd/oz'),
    'oil':          ('WTI_OIL', 1.0, 'usd/bbl'),
    'dxy':          ('DXY_PROXY', 1.0, 'index'),
    'usdjpy':       ('USD_JPY', 1.0, 'jpy'),
    'vix':          ('VIX', 1.0, 'index'),
    'us_10y':       ('YC10Y', 1.0, '%'),
    'us_2y':        ('YC2Y', 1.0, '%'),
    'us_30y':       ('YC30Y', 1.0, '%'),
    'hy_oas_bp':    ('HY_SPREAD', 0.01, '%'),
    'hy_ccc_bp':    ('HY_CCC_OAS', 0.01, '%'),
    'sofr':         ('SOFR', 1.0, '%'),
    'effr':         ('EFFR', 1.0, '%'),
    'rrp_b':        ('RRP_BALANCE', 1.0, 'billion_usd'),
    'tga_b':        ('TGA_BALANCE', 1000.0, 'billion_usd -> million_usd (*1000)'),
    'reserve_t':    ('RESERVE_BALANCE', 1000000.0, 'trillion_usd -> million_usd (*1e6)'),
}

QUARANTINE_DDL = """
CREATE TABLE IF NOT EXISTS quarantine (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id         TEXT NOT NULL,
    obs_date          TEXT,
    raw_value         REAL,
    normalized_value  REAL,
    multiplier        REAL,
    unit              TEXT,
    source            TEXT NOT NULL DEFAULT 'feishu_override',
    reason            TEXT,
    payload           TEXT,
    captured_at       TEXT NOT NULL,
    UNIQUE(series_id, obs_date, source)
)
"""


def _assert_sandbox(path: Path) -> None:
    resolved = path.resolve()
    ok = any(resolved == r.resolve() or r.resolve() in resolved.parents
             for r in SANDBOX_ROOTS)
    if not ok:
        raise SystemExit(f'DISARMED: {resolved} 不在沙盒内，已拒绝执行。')


def main() -> int:
    _assert_sandbox(DB_PATH)
    if not DB_PATH.exists():
        print(f'ℹ️ 沙盒内无数据库（采集仓副本正常如此）: {DB_PATH}，跳过。')
        return 0

    conn = sqlite3.connect(str(DB_PATH), timeout=15)
    try:
        try:
            cur = conn.execute('SELECT * FROM feishu_snapshot ORDER BY timestamp DESC LIMIT 1')
        except sqlite3.OperationalError:
            print('ℹ️ feishu_snapshot 表不存在，无隔离对象。')
            return 0

        row = cur.fetchone()
        if not row:
            print('❌ feishu_snapshot 表为空，无隔离对象')
            return 0

        cols = [d[0] for d in cur.description]
        latest = dict(zip(cols, row))
        feishu_date = str(latest.get('timestamp') or '')[:10]
        captured = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        conn.execute(QUARANTINE_DDL)
        conn.commit()

        moved = 0
        skipped = 0
        for field, (series_id, multiplier, unit) in OVERRIDE_MAP.items():
            val = latest.get(field)
            if val is None or val == '':
                continue
            try:
                raw = float(val)
                norm = raw * multiplier
                conn.execute(
                    """INSERT OR IGNORE INTO quarantine
                       (series_id, obs_date, raw_value, normalized_value, multiplier,
                        unit, source, reason, payload, captured_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (series_id, feishu_date, raw, norm, multiplier, unit,
                     'feishu_override',
                     'v4.1: 飞书文本回读值，禁止进入 observations',
                     json.dumps({field: val}, ensure_ascii=False),
                     captured))
                moved += 1
            except Exception as e:
                skipped += 1
                print(f'  ⚠️ {field} 隔离失败: {e}')

        conn.commit()
        q_total = conn.execute('SELECT COUNT(*) FROM quarantine').fetchone()[0]

        # 明确断言：本次运行没有向 observations / observations_v2 写入任何飞书数据
        obs_cnt = conn.execute(
            "SELECT COUNT(*) FROM observations WHERE source=? AND timestamp LIKE ?",
            ('feishu_override', feishu_date + '%')).fetchone()[0]

        print(f'🔒 飞书快照日期 {feishu_date}：隔离 {moved} 个指标（跳过 {skipped}）')
        print(f'    quarantine 累计 {q_total} 行')
        print(f'    observations 中该日 feishu_override 行数 = {obs_cnt}（本次未新增任何一行）')
        print('    ✅ 写库能力已退役：官方数值请取 FRED / NYFed / Treasury')
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    raise SystemExit(main())
