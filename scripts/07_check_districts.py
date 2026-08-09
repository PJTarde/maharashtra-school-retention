import duckdb

con = duckdb.connect(r"e:\pbl project\data\udise.duckdb", read_only=True)
rows = con.execute("""
  SELECT district,
         count(*) FILTER (year='2021-22') y21,
         count(*) FILTER (year='2022-23') y22,
         count(*) FILTER (year='2023-24') y23
  FROM school_year GROUP BY 1 ORDER BY 1""").fetchall()
print(f"{len(rows)} distinct district strings")
for r in rows:
    flag = "   <-- MISSING in some year" if 0 in r[1:] else ""
    print(f"  {r[0]:<30} {r[1]:>7,} {r[2]:>7,} {r[3]:>7,}{flag}")
