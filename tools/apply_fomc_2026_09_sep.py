# -*- coding: utf-8 -*-
"""
apply_fomc_2026_09_sep.py
用途：将 2026-09 FOMC SEP/点阵图官方核验数据写入 GMRE 报告目录。
纪律：只写数据/文档/Pending，不改引擎代码。
"""
from pathlib import Path
import csv
from datetime import datetime
import shutil

BASE = Path(r"D:\HGZC")
REPORT_DIR = BASE / "reports" / "stagflation_watch_2026Q3"
DOCS_DIR = BASE / "docs"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DIR.mkdir(parents=True, exist_ok=True)

TS = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP_DIR = REPORT_DIR / f"backup_{TS}"
BACKUP_DIR.mkdir(exist_ok=True)

def backup_if_exists(path: Path):
    if path.exists():
        shutil.copy2(path, BACKUP_DIR / path.name)
        print(f"[backup] {path} -> {BACKUP_DIR / path.name}")

def write_csv(path: Path, fieldnames, rows, encoding="utf-8-sig"):
    backup_if_exists(path)
    with path.open("w", newline="", encoding=encoding) as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow(row)
    print(f"[write] {path} ({len(rows)} rows)")

def append_csv(path: Path, fieldnames, rows, encoding="utf-8-sig"):
    backup_if_exists(path)
    exists = path.exists()
    with path.open("a", newline="", encoding=encoding) as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            w.writeheader()
        for row in rows:
            w.writerow(row)
    print(f"[append] {path} ({len(rows)} rows)")

# 1) SEP 校准表
sep_path = REPORT_DIR / "sep_2026Q3.csv"
sep_fields = ["meeting_date","variable","year","median","unit","source","notes"]
sep_rows = [
    {"meeting_date":"2026-09-16","variable":"core_pce","year":"2026","median":"3.4","unit":"%","source":"FOMC SEP 2026-09-16","notes":"官方PDF核验；此前误写2.7%，已修正"},
    {"meeting_date":"2026-09-16","variable":"core_pce","year":"2027","median":"2.4","unit":"%","source":"FOMC SEP 2026-09-16","notes":"待与原始PDF确认2.4/2.5"},
    {"meeting_date":"2026-09-16","variable":"core_pce","year":"2028","median":"2.2","unit":"%","source":"FOMC SEP 2026-09-16","notes":""},
    {"meeting_date":"2026-09-16","variable":"core_pce","year":"longer_run","median":"2.0","unit":"%","source":"FOMC SEP 2026-09-16","notes":"PCE通胀目标"},
    {"meeting_date":"2026-09-16","variable":"unemployment_u3","year":"2026","median":"4.1","unit":"%","source":"FOMC SEP 2026-09-16","notes":"此前误写4.2%，已修正"},
    {"meeting_date":"2026-09-16","variable":"unemployment_u3","year":"2027","median":"4.1","unit":"%","source":"FOMC SEP 2026-09-16","notes":"此前误写4.3%，已修正"},
    {"meeting_date":"2026-09-16","variable":"unemployment_u3","year":"2028","median":"4.1","unit":"%","source":"FOMC SEP 2026-09-16","notes":"此前误写4.3%，已修正"},
    {"meeting_date":"2026-09-16","variable":"unemployment_u3","year":"longer_run","median":"4.2","unit":"%","source":"FOMC SEP 2026-09-16","notes":"长期NAIRU；此前误写4.1%，已修正"},
    {"meeting_date":"2026-09-16","variable":"fed_funds_rate","year":"2026","median":"4.125","unit":"%","source":"FOMC SEP 2026-09-16","notes":"区间4.00-4.25%中点"},
    {"meeting_date":"2026-09-16","variable":"fed_funds_rate","year":"2027","median":"4.125","unit":"%","source":"FOMC SEP 2026-09-16","notes":"维持不变，Higher-for-Longer"},
    {"meeting_date":"2026-09-16","variable":"fed_funds_rate","year":"2028","median":"3.875","unit":"%","source":"FOMC SEP 2026-09-16","notes":"区间3.75-4.00%中点；显示层可四舍五入3.9%"},
    {"meeting_date":"2026-09-16","variable":"fed_funds_rate","year":"longer_run","median":"3.20","unit":"%","source":"FOMC SEP 2026-09-16","notes":"中性利率r*，较6月上调0.10%"},
    {"meeting_date":"2026-09-16","variable":"real_gdp","year":"2026","median":"2.3","unit":"%","source":"FOMC SEP 2026-09-16","notes":""},
    {"meeting_date":"2026-09-16","variable":"real_gdp","year":"2027","median":"2.4","unit":"%","source":"FOMC SEP 2026-09-16","notes":""},
    {"meeting_date":"2026-09-16","variable":"real_gdp","year":"2028","median":"2.2","unit":"%","source":"FOMC SEP 2026-09-16","notes":"上一版误写2.1%，已修正"},
    {"meeting_date":"2026-09-16","variable":"real_gdp","year":"longer_run","median":"2.0","unit":"%","source":"FOMC SEP 2026-09-16","notes":""},
]
write_csv(sep_path, sep_fields, sep_rows)

# 2) 点阵图分布
dot_path = REPORT_DIR / "dot_plot_2026Q3.csv"
dot_fields = ["meeting_date","year","median_rate","range_low","range_high","distribution","notes"]
dot_rows = [
    {"meeting_date":"2026-09-16","year":"2026","median_rate":"4.125","range_low":"4.00","range_high":"4.25","distribution":"12: +1 hike; 4: +2 hikes; 2: unchanged","notes":"绝大多数认为年内至少再加一次"},
    {"meeting_date":"2026-09-16","year":"2027","median_rate":"4.125","range_low":"4.00","range_high":"4.25","distribution":"8: +1 hike; 6: unchanged; 4: -1 cut","notes":"鹰派众数，2027无降息多数"},
    {"meeting_date":"2026-09-16","year":"2028","median_rate":"3.875","range_low":"3.75","range_high":"4.00","distribution":"converged; one 25bp cut","notes":"仅一次降息，不快速回中性"},
    {"meeting_date":"2026-09-16","year":"longer_run","median_rate":"3.20","range_low":"","range_high":"","distribution":"neutral r*","notes":"较6月3.10%上调0.10%"},
]
write_csv(dot_path, dot_fields, dot_rows)

# 3) r* 历史
rstar_path = REPORT_DIR / "r_star_history.csv"
rstar_fields = ["meeting_date","longer_run_median","change","notes"]
rstar_rows = [
    {"meeting_date":"2026-06","longer_run_median":"3.10","change":"","notes":"6月SEP"},
    {"meeting_date":"2026-09-16","longer_run_median":"3.20","change":"+0.10","notes":"9月SEP上调"},
]
write_csv(rstar_path, rstar_fields, rstar_rows)

# 4) Pending 追加
pending_path = REPORT_DIR / "pending_issues.csv"
pending_fields = ["date","priority","issue","detail","action","status"]
pending_rows = [
    {"date":"2026-10-01","priority":"P0","issue":"INF_EXPECT阈值与SEP核心PCE一致性审查","detail":"2026核心PCE=3.4%，但09-26 INF_EXPECT=0；需审查阈值是否过松","action":"10-21后执行","status":"pending"},
    {"date":"2026-10-01","priority":"P1","issue":"MON_V2就业维度校准","detail":"SEP失业率2026-2028均为4.1%，削弱衰退预期","action":"10-21后执行","status":"pending"},
    {"date":"2026-10-01","priority":"P1","issue":"长期NAIRU与r*参数更新","detail":"长期NAIRU=4.2%，r*=3.2%，均衡利率中枢上移","action":"10-21后执行","status":"pending"},
    {"date":"2026-10-01","priority":"P1","issue":"R3/R4概率下调审查","detail":"SEP支持软着陆，需审查R3/R4概率是否滞后","action":"10-21后执行","status":"pending"},
    {"date":"2026-10-01","priority":"P2","issue":"2027核心PCE确认","detail":"当前写2.4%，外部有2.5%口径，需原始PDF确认","action":"用原始PDF确认","status":"pending"},
    {"date":"2026-10-01","priority":"P2","issue":"2028利率显示统一","detail":"内部浮点3.875%，显示层3.9%；需统一规则","action":"已定义规则，待文档化","status":"pending"},
]
append_csv(pending_path, pending_fields, pending_rows)

# 5) Markdown 补充文档
md_path = DOCS_DIR / "FOMC_2026_09_SEP_DOT_PLOT.md"
md = f"""# FOMC 2026-09 SEP / 点阵图核验与 GMRE 校准

**生成时间**：{datetime.now().isoformat(timespec='seconds')}
**数据源**：美联储官网 fomcprojtabl20260916.pdf，FRED/ALFRED 交叉校验
**性质**：宏观状态识别框架 · 学术研究 · 非交易建议

## 1. 核心结论

- 2027 点阵中位数维持 4.125%，**无降息空间**；降息仅定价在 2028。
- 基准情景切换为 **Higher-for-Longer**。
- 2026 核心 PCE 中位数 = **3.4%**，此前 2.7% 为误写。
- 失业率 2026/2027/2028 均为 **4.1%**，软着陆预期强化。
- 长期 NAIRU = **4.2%**，长期中性利率 r* = **3.20%**。

## 2. SEP 校准表

| 指标 | 2026 | 2027 | 2028 | Longer Run |
|---|---:|---:|---:|---:|
| 核心PCE（Q4同比，中位数） | 3.4% | 2.4% | 2.2% | 2.0% |
| 失业率U3（Q4，中位数） | 4.1% | 4.1% | 4.1% | 4.2% |
| 联邦基金利率（年末中位数，区间中点） | 4.125% | 4.125% | 3.875% | 3.20% |
| 实际GDP增速（Q4同比） | 2.3% | 2.4% | 2.2% | 2.0% |

## 3. 点阵图分布

- 2026：12 位 +1 次加息；4 位 +2 次；2 位不变。
- 2027：8 位 +1 次加息；6 位不变；4 位 -1 次降息。
- 2028：中位数 3.875%，仅一次 25bp 降息。

## 4. GMRE 修正清单

1. 降息预期交易模块：2027 降息降为低概率乐观情景，基准改为 Higher-for-Longer。
2. INF_EXPECT：核心 PCE 路径上修，通胀粘性权重上调。
3. MON_V2：中性利率 r* 上调至 3.2%，利率通道整体上移。
4. S 状态机：S6 基准；S5 推迟至 2028；S7 为尾部风险。
5. 预期差因子：市场期货定价 vs FOMC 点阵，作为独立价差因子。

## 5. 待确认

- 2027 核心 PCE：2.4% vs 2.5%，需原始 PDF 确认。
- 长期 NAIRU 4.2%：需原始 PDF 确认。

## 6. 数据文件

- `reports/stagflation_watch_2026Q3/sep_2026Q3.csv`
- `reports/stagflation_watch_2026Q3/dot_plot_2026Q3.csv`
- `reports/stagflation_watch_2026Q3/r_star_history.csv`
- `reports/stagflation_watch_2026Q3/pending_issues.csv`
"""
md_path.write_text(md, encoding="utf-8")
print(f"[write] {md_path}")

print("\n完成。已写入数据/文档/Pending，未修改任何引擎代码。")
print(f"备份目录：{BACKUP_DIR}")