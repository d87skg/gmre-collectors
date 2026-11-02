import sqlite3
import pandas as pd

conn = sqlite3.connect(r"D:\HGZC\data\macro.db")

def schema(tbl):
    print("=== " + tbl + " schema ===")
    try:
        df = pd.read_sql_query("PRAGMA table_info(" + tbl + ")", conn)
        print(df.to_string(index=False))
    except Exception as e:
        print("  error:", e)
    print()

for t in ["observations", "macro_series", "pit_observations", "observation_vintages", "series", "sources"]:
    schema(t)

print("=== observations sample 3 rows ===")
try:
    print(pd.read_sql_query("SELECT * FROM observations LIMIT 3", conn).to_string(index=False))
except Exception as e:
    print("  error:", e)

print()
print("=== macro_series sample 3 rows ===")
try:
    print(pd.read_sql_query("SELECT * FROM macro_series LIMIT 3", conn).to_string(index=False))
except Exception as e:
    print("  error:", e)

print()
print("=== macro_series distinct series_name / symbol containing RRP ===")
for col in ["series", "series_name", "name", "symbol", "ticker", "code"]:
    try:
        q = "SELECT DISTINCT " + col + " FROM macro_series WHERE lower(" + col + ") LIKE '%rrp%' OR lower(" + col + ") LIKE '%repo%' LIMIT 20"
        rows = [r[0] for r in conn.execute(q)]
        if rows:
 








           print("  via column", col, "->", rows)
    except Exception:
        pass

print()
print("=== observations distinct series-like columns containing RRP ===")
for col in ["series", "series_name", "name", "symbol", "ticker", "code"]:
    try:
        q = "SE







LECT DISTINCT " + col + " FROM observations WHERE lower(" + col + ") LIKE '%rrp%' OR lower(" + col + ") LIKE '%repo%' LIMIT 20"
        rows = [r[0] for r in conn.execute(q)]
        if rows:
            print("  via column", col, "->", rows)
 



   except Exception:
        pass

conn.close()
