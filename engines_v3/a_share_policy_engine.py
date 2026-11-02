# -*- coding: utf-8 -*-
"""engines_v3/a_share_policy_engine.py - A股政策底引擎"""
import sqlite3
import json
from datetime import datetime, timedelta

DB_PATH = 'data/macro.db'


def _check_recent_event(conn, keyword, days=30):
    try:
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        row = conn.execute(
            "SELECT event_date, event_name FROM event_calendar "
            "WHERE event_name LIKE ? AND event_date >= ? ORDER BY event_date DESC LIMIT 1",
            (f'%{keyword}%', cutoff)
        ).fetchone()
        if row:
            return {'date': row[0], 'name': row[1]}
    except Exception:
        pass
    return None


def compute_policy_bottom(asof: str) -> dict:
    signals = []
    score = 0
    checks = {}

    try:
        conn = sqlite3.connect(DB_PATH)

        # 1. 汇金增持
        huijin = _check_recent_event(conn, '汇金', days=30)
        if huijin:
            signals.append(f"汇金增持 {huijin['date']}")
            score += 30
            checks['huijin'] = f'✅ {huijin["date"]}'
        else:
            checks['huijin'] = '⚪ 30日内无'

        # 2. SFISF
        sfisf = _check_recent_event(conn, 'SFISF', days=30)
        if sfisf:
            signals.append(f"SFISF {sfisf['date']}")
            score += 25
            checks['sfisf'] = f'✅ {sfisf["date"]}'
        else:
            checks['sfisf'] = '⚪ 30日内无'

        # 3. IPO 收紧
        ipo = _check_recent_event(conn, 'IPO', days=30)
        if ipo:
            signals.append("IPO/减持收紧")
            score += 20
            checks['ipo'] = '✅'
        else:
            checks['ipo'] = '⚪'

        # 4. 一行两会喊话
        speak = _check_recent_event(conn, '一行两会', days=14)
        if not speak:
            speak = _check_recent_event(conn, '金融委', days=14)
        if speak:
            signals.append("一行两会喊话")
            score += 15
            checks['speak'] = '✅'
        else:
            checks['speak'] = '⚪ 14日内无'

        conn.close()
    except Exception as e:
        print(f"  ⚠️ A股政策底引擎异常: {e}")

    if score >= 50:
        level = 'POLICY_BOTTOM_CONFIRMED'
        action = '🟢 政策底确认，反弹可期'
    elif score >= 30:
        level = 'POLICY_BOTTOM_FORMING'
        action = '🟡 政策底形成中'
    else:
        level = 'NO_SIGNAL'
        action = '⚪ 无政策底信号'

    result = {
        'asof': asof,
        'score': score,
        'level': level,
        'signals': signals,
        'checks': checks,
        'action': action,
        'note': '政策底 ≠ 市场底，市场底需等信用/地产拐点'
    }

    try:
        conn2 = sqlite3.connect(DB_PATH)
        conn2.execute("""CREATE TABLE IF NOT EXISTS a_share_policy (
            asof_date TEXT PRIMARY KEY, score REAL, level TEXT, detail TEXT)""")
        conn2.execute("""INSERT OR REPLACE INTO a_share_policy
            (asof_date, score, level, detail) VALUES (?, ?, ?, ?)""",
            (asof, score, level, json.dumps(result)))
        conn2.commit()
        conn2.close()
    except Exception:
        pass

    return result


if __name__ == '__main__':
    asof = datetime.now().strftime('%Y-%m-%d')
    r = compute_policy_bottom(asof)
    print(f"\n{'='*60}")
    print(f"  A股政策底引擎 - {asof}")
    print(f"{'='*60}")
    print(f"  评分: {r['score']}/100 ({r['level']})")
    print(f"  信号: {r['signals']}")
    print(f"  动作: {r['action']}")
    print(f"  {r['note']}")
    print(f"{'='*60}\n")