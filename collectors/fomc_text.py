# -*- coding: utf-8 -*-
"""collectors/fomc_text.py - FOMC 声明抓取（存原文，不做 NLP）"""
import requests
import sqlite3
from datetime import datetime

DB_PATH = 'data/macro.db'

# 美联储 FOMC 声明页面
FOMC_URLS = [
    "https://www.federalreserve.gov/newsevents/pressreleases/monetary20241031a.htm",
]


def init_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS fomc_statements (
        date TEXT PRIMARY KEY, url TEXT, content TEXT, fetched_at TEXT)""")
    conn.commit()


def fetch_fomc(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code == 200:
            # 简单提取正文（去除 HTML 标签）
            text = r.text
            import re
            # 提取正文段落
            paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', text, re.DOTALL)
            cleaned = []
            for p in paragraphs:
                t = re.sub(r'<[^>]+>', '', p).strip()
                if t and len(t) > 20:
                    cleaned.append(t)
            return '\n'.join(cleaned) if cleaned else text[:5000]
    except Exception as e:
        print(f"  ❌ FOMC 抓取失败: {str(e)[:60]}")
    return None


def main():
    print(f"\n{'='*60}")
    print(f"  FOMC 文本抓取 - {datetime.now().strftime('%Y-%m-%d')}")
    print(f"{'='*60}\n")

    conn = sqlite3.connect(DB_PATH)
    init_table(conn)

    for url in FOMC_URLS:
        date_str = url.split('/')[-1].replace('.htm', '')
        # 提取日期 20241031a -> 2024-10-31
        if len(date_str) >= 8 and date_str[:8].isdigit():
            y, m, d = date_str[:4], date_str[4:6], date_str[6:8]
            date_iso = f"{y}-{m}-{d}"
        else:
            date_iso = datetime.now().strftime('%Y-%m-%d')

        content = fetch_fomc(url)
        if content:
            conn.execute("""INSERT OR REPLACE INTO fomc_statements
                (date, url, content, fetched_at) VALUES (?, ?, ?, datetime('now'))""",
                (date_iso, url, content))
            print(f"  ✅ {date_iso}: {len(content)} 字符")
        else:
            print(f"  ⚠️ {date_iso}: 跳过")

    conn.commit()
    conn.close()
    print(f"\n  提示: 美联储 FOMC 通常在会议后发布声明，可手动补充 URL 列表")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()