import sqlite3
import pandas as pd

conn = sqlite3.connect(r"D:\HGZC\data\macro.db")

for t in ["observations", "macro_series", "pit_observations", "series", "sources"]:
    print("=== " + t + " ===")
    try:
        df = pd.read_sql_query("PRAGMA table_info(" + t + ")", conn)
        print(df[["cid","name","type"]].to_string(index=False))
    except Exception as e:
        print("  error:", e)
    print()

print("=== observations 3 rows ===")
try:
    print(pd.read_sql_query("SELECT * FROM observations LIMIT 3", conn).to_string(index=False))
except Exception as e:
    print("  error:", e)
print()

print("=== macro_series 3 rows ===")
try:
    print(pd.read_sql_query("SELECT * FROM macro_series LIMIT 3", conn).to_string(index=False))
except Exception as e:
    print("  error:", e)
print()

conn.close()
