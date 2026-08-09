import duckdb

con = duckdb.connect(r"e:\pbl project\data\udise.duckdb", read_only=True)

print("=== school_category codes by year ===")
for r in con.execute("""
    SELECT school_category,
           count(*) FILTER (year='2021-22') y21, count(*) FILTER (year='2022-23') y22,
           count(*) FILTER (year='2023-24') y23, count(*) FILTER (year='2024-25') y24,
           count(*) FILTER (year='2025-26') y25,
           any_value(category_label) lab
    FROM school_year GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"  code {str(r[0]):>4}: {r[1]:>7,} {r[2]:>7,} {r[3]:>7,} {r[4]:>7,} {r[5]:>7,}  "
          f"{r[6] or '<< UNMAPPED >>'}")

print("\n=== class range for any unmapped category (2025-26) ===")
for r in con.execute("""
    SELECT school_category, lowclass, highclass, count(*) n
    FROM school_year WHERE category_label IS NULL AND year='2025-26'
    GROUP BY 1,2,3 ORDER BY n DESC LIMIT 10""").fetchall():
    print(f"  code {r[0]}: classes {r[1]}-{r[2]}  n={r[3]:,}")

print("\n=== management codes by year ===")
for r in con.execute("""
    SELECT management,
           count(*) FILTER (year='2024-25') y24, count(*) FILTER (year='2025-26') y25,
           any_value(management_label) lab
    FROM school_year GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"  code {str(r[0]):>4}: {r[1]:>7,} {r[2]:>7,}  {r[3] or '<< UNMAPPED >>'}")

print("\n=== medium codes not mapped ===")
print(con.execute("""
    SELECT medium1, count(*) n FROM school_year
    WHERE medium_label IS NULL AND medium1 IS NOT NULL
    GROUP BY 1 ORDER BY n DESC LIMIT 10""").fetchall())
