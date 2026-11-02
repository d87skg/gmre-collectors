import sqlite3
import pandas as pd

conn = sqlite3.connect(r"D:\HGZC\data\macro.db")
cur = conn.cursor()

print("=== TABLES ===")
for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
    print("  ", r[0])

print()
print("=== SERIES CONTAINING RRP OR REPO (observations) ===")
try:
    for r in cur.execute("SELECT DISTINCT series FROM observations WHERE series LIKE '%RRP%' OR series LIKE '%REPO%' ORDER BY series"):
        print("  ", r[0])
except Exception as e:
    print("  observations not usable:", e)

print()
print("=== TABLES LIKE rrp ===")
for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND lower(name) LIKE '%rrp%'"):
    print("  ", r[0])

print()
print("=== LATEST VALUES: candidate series in observations ===")
for s in ["RRP_BALANCE", "REVERSE_REPO_FRED", "RRP_NYFED", "RRPONTSYD"]:
    try:
        df = pd.read_sql_query(
            "SELECT date, value FROM observations WHERE series=? ORDER BY date DESC LIMIT 5",
            conn, params=(s,)
        )
        if not df.empty:
            print("--- " + s + " ---")
            print(df.to_string(index=False))
        else:
            print("--- " + s + ": EMPTY ---")
    except Exception as e:
        print("--- " + s + ": ERROR " + str(e))











print()
print("=== standalone table rrp_nyfed ===")
try:
    df = pd.read_sql_query("SELECT * FROM rrp_nyfed ORDER BY rowid DESC LIMIT 5", conn)
    print(df.to_string(index=False))
except Exception as e:
    print("  not found:", e)

conn.close()










