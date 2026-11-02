@echo off
chcp 65001 >nul
cd /d D:\HGZC

echo ========================================================
echo   GMRE 3.3 Daily Pipeline
echo ========================================================

echo [1/16] Data correction (FRED/WTI/GOLD)...
.venv\Scripts\python.exe -X utf8 engines_v3\data_correction.py
if %errorlevel% neq 0 (
    echo FATAL: data correction failed, pipeline aborted!
    exit /b 1
)

echo [2/16] Enhanced liquidity data...
if exist collectors\enhanced_data.py (.venv\Scripts\python.exe -X utf8 collectors\enhanced_data.py)

echo [2.5/16] Global data sanitizer...
.venv\Scripts\python.exe -X utf8 tools\data_sanitizer.py
if %errorlevel% neq 0 (
    echo FATAL: data sanitizer failed, pipeline aborted!
    exit /b 1
)

rem ====================================================================
rem Smart gap check gateway
rem   - Rate limit: skip if last run was less than 4 hours ago
rem   - Gap check: 0 request if latest data is up to today
rem   - Weekday skip: skip full backfill Mon-Thu if gap is small
rem   - Weekend: full backfill Sat/Sun
rem ====================================================================
echo [3/16] Smart gap check for market history...
.venv\Scripts\python.exe -X utf8 tools\check_and_backfill.py

echo [4/16] Sync feishu snapshot...
.venv\Scripts\python.exe -X utf8 tools\sync_feishu_snapshot.py
.venv\Scripts\python.exe -X utf8 tools\apply_feishu_override.py

echo [5/16] Compute percentiles...
.venv\Scripts\python.exe -X utf8 tools\compute_percentile.py
if %errorlevel% neq 0 (
    echo FATAL: percentile computation failed, pipeline aborted!
    exit /b 1
)

echo [6/16] Contagion engine...
.venv\Scripts\python.exe -X utf8 engines_v3\contagion_engine.py

echo [7/16] CAPS commodity collection...
if exist collectors\caps_collector.py (.venv\Scripts\python.exe -X utf8 collectors\caps_collector.py)
if exist tools\sync_commodity_github.py (.venv\Scripts\python.exe -X utf8 tools\sync_commodity_github.py)

echo [8/16] LTI engine...
if exist engines_v3\lti_engine.py (.venv\Scripts\python.exe -X utf8 engines_v3\lti_engine.py)

echo [8.5/16] Copper spread engine...
.venv\Scripts\python.exe -X utf8 engines_v3\spread_engine.py

echo [9/16] GMRE V4 main engine...
.venv\Scripts\python.exe -X utf8 engines_v3\run_v4.py
if %errorlevel% neq 0 (
    echo FATAL: main engine failed!
    exit /b 1
)

echo [10/16] Daily report...
if exist engines_v3\generate_report.py (.venv\Scripts\python.exe -X utf8 engines_v3\generate_report.py)

echo [11/16] Brier calibration...
if exist engines_v3\calibration_tracker.py (.venv\Scripts\python.exe -X utf8 engines_v3\calibration_tracker.py)

echo [12/16] Data freshness check...
.venv\Scripts\python.exe -X utf8 tools\check_freshness.py

echo [13/16] Push to Feishu...
.venv\Scripts\python.exe -X utf8 tools\send_local_feishu.py

echo ========================================================
echo   Pipeline completed successfully
echo ========================================================
pause