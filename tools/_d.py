import sqlite3
import pandas as pd

conn = sqlite3.connect(r"D:\HGZC\data\macro.db")

print("=== RRP candidates in observations ===")
rows = [r[0] for r in conn.execute(
    "SELECT DISTINCT series_id FROM observations WHERE upper(series_id) LIKE '%RRP%' OR upper(series_id) LIKE '%REPO%' ORDER BY series_id"
)]
for r in rows:
    print("  ", r)

print("=== RRP candidates in macro_series ===")
rows2 = [r[0] for r in conn.execute(
    "SELECT DISTINCT series_id FROM macro_series WHERE upper(series_id) LIKE '%RRP%' OR upper(series_id) LIKE '%REPO%' ORDER BY series_id"
)]
for r in rows2:
    print("  ", r)

print("=== series table ===")
try:
    df = pd.read_sql_query(
        "SELECT series_id, source_id, symbol, name, category FROM series WHERE upper(series_id) LIKE '%RRP%' OR upper(name) LIKE '%RRP%'",
        conn
    )
    print(df.to_string(index=False))
except Exception as e:
    print("  error:", e)

print("=== latest rows per candidate ===")
for s in sorted(set(rows + rows2)):
    df = pd.read_sql_query(
        "SELECT timestamp, value, source FROM observations WHERE series_id=? ORDER BY timestamp DESC LIMIT 5",
        conn, params=(s,)
    )
    print("--- " + s + " ---")
    print(df.to_string(index=False) if not df.empty else "  EMPTY")

conn.close()