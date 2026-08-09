import duckdb

con = duckdb.connect(r"e:\pbl project\data\udise.duckdb", read_only=True)
print("furniture_availability: distinct value count and range per year")
for r in con.execute("""
    SELECT year, count(DISTINCT furniture_availability) n_distinct,
           min(furniture_availability) lo, max(furniture_availability) hi,
           count(*) FILTER (furniture_availability = 0) zeros,
           count(*) FILTER (furniture_availability > 2) gt2
    FROM school_year GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"  {r[0]}  distinct={r[1]:>5}  min={r[2]}  max={r[3]}  zeros={r[4]:,}  >2={r[5]:,}")

print("\ntop values in 2023-24")
for r in con.execute("""
    SELECT furniture_availability v, count(*) n FROM school_year
    WHERE year='2023-24' GROUP BY 1 ORDER BY n DESC LIMIT 8""").fetchall():
    print(f"  {r[0]}: {r[1]:,}")

print("\nmedical_checkups by year (is the jump a coding change?)")
for r in con.execute("""
    SELECT year, medical_checkups v, count(*) n FROM school_year
    GROUP BY 1,2 ORDER BY 1, n DESC""").fetchall():
    print(f"  {r[0]}  {r[1]}: {r[2]:,}")
