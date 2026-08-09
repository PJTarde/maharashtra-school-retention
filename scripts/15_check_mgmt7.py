"""What are the 2025-26 management-code-7 schools? Track them back a year."""
import duckdb

con = duckdb.connect(r"e:\pbl project\data\udise.duckdb", read_only=True)

print("=== 2025-26 code-7 schools: what were they in 2024-25? ===")
for r in con.execute("""
    SELECT prev.management AS was, any_value(prev.management_label) AS was_label,
           count(*) AS n
    FROM school_year cur
    JOIN school_year prev
      ON prev.pseudocode = cur.pseudocode AND prev.year = '2024-25'
    WHERE cur.year = '2025-26' AND cur.management = 7
    GROUP BY 1 ORDER BY n DESC""").fetchall():
    print(f"  was code {str(r[0]):>4} ({r[1]}): {r[2]:,}")

print("\n=== and the reverse: 2024-25 code-4/5 schools, where did they go? ===")
for r in con.execute("""
    SELECT prev.management AS was, cur.management AS now,
           any_value(cur.management_label) AS now_label, count(*) n
    FROM school_year prev
    JOIN school_year cur
      ON cur.pseudocode = prev.pseudocode AND cur.year = '2025-26'
    WHERE prev.year = '2024-25' AND prev.management IN (4,5)
      AND cur.management <> prev.management
    GROUP BY 1,2 ORDER BY n DESC LIMIT 8""").fetchall():
    print(f"  {r[0]} -> {r[1]} ({r[2]}): {r[3]:,}")

print("\n=== profile of 2025-26 code-7 schools vs code-3 (govt) and code-5 (pvt unaided) ===")
print(con.execute("""
    SELECT management,
           count(*) schools,
           round(100.0*count(*) FILTER (location='Rural')/count(*),1) pct_rural,
           round(avg(enr_total),0) avg_enr,
           round(avg(total_tch),1) avg_tch,
           round(100.0*count(*) FILTER (minority_school=1)/count(*),1) pct_minority,
           round(100.0*count(*) FILTER (medium_label='Urdu')/count(*),1) pct_urdu,
           round(100.0*count(*) FILTER (medium_label='English')/count(*),1) pct_english,
           round(100.0*count(*) FILTER (internet=1)/count(*),1) pct_internet
    FROM school_year WHERE year='2025-26' AND management IN (3,4,5,7)
    GROUP BY 1 ORDER BY 1""").fetchdf().to_string(index=False))

print("\n=== code 7 across all years ===")
for r in con.execute("""
    SELECT year, count(*) FILTER (management=7) code7, count(*) FILTER (management=4) code4,
           count(*) FILTER (management=5) code5, count(*) FILTER (management=6) code6
    FROM school_year GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"  {r[0]}  code7={r[1]:>6,}  code4={r[2]:>7,}  code5={r[3]:>7,}  code6={r[4]:>5,}")
