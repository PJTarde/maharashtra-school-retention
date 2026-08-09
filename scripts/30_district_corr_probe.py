"""Exact district-level correlation between 'must change school' and retention."""
import duckdb

con = duckdb.connect(r"e:\pbl project\data\udise.duckdb", read_only=True)
Y0, Y1 = "2024-25", "2025-26"
D = """CASE trim(district)
    WHEN 'AURANGABAD (MAHARASHTRA)' THEN 'CHHATRAPATI SAMBHAJINAGAR'
    WHEN 'OSMANABAD' THEN 'DHARASHIV'
    WHEN 'AHMADNAGAR' THEN 'AHILYANAGAR' ELSE trim(district) END"""

# (a) as written in 21_supply_test.py: one CTE, no total>0 filter, max() for c11
a = con.execute(f"""
    WITH sch AS (SELECT {D} AS district, pseudocode, highclass
                 FROM school_year WHERE year='{Y0}'),
    c10 AS (SELECT sch.district, sch.highclass, e.total c10 FROM sch
            JOIN enrol_class e ON e.pseudocode=sch.pseudocode
            WHERE e.year='{Y0}' AND e.class_num=10),
    c11 AS (SELECT sch.district, sum(e.total) c11 FROM sch
            JOIN enrol_class e ON e.pseudocode=sch.pseudocode
            WHERE e.year='{Y1}' AND e.class_num=11 GROUP BY 1)
    SELECT corr(mm, ret), count(*) FROM (
      SELECT c10.district,
             100.0*sum(c10.c10) FILTER (highclass=10)/sum(c10.c10) mm,
             100.0*max(c11.c11)/sum(c10.c10) ret
      FROM c10 LEFT JOIN c11 USING (district) GROUP BY 1)
    WHERE ret IS NOT NULL""").fetchone()

# (b) separate CTEs, inner joins (the version in the verifier)
b = con.execute(f"""
    WITH mm AS (SELECT {D} AS district,
                  100.0*sum(e.total) FILTER (sy.highclass=10)/sum(e.total) mm
                FROM enrol_class e JOIN school_year sy USING (year, pseudocode)
                WHERE e.year='{Y0}' AND e.class_num=10 GROUP BY 1),
    x AS (SELECT {D} AS district, sum(e.total) t FROM enrol_class e
          JOIN school_year sy USING (year, pseudocode)
          WHERE e.year='{Y0}' AND e.class_num=10 GROUP BY 1),
    y AS (SELECT {D} AS district, sum(e.total) t FROM enrol_class e
          JOIN school_year sy USING (year, pseudocode)
          WHERE e.year='{Y1}' AND e.class_num=11 GROUP BY 1)
    SELECT corr(mm.mm, 100.0*y.t/x.t), count(*)
    FROM x JOIN y USING (district) JOIN mm USING (district)""").fetchone()

print(f"(a) as originally computed : r = {a[0]:+.5f}  over {a[1]} districts")
print(f"(b) verifier construction  : r = {b[0]:+.5f}  over {b[1]} districts")
print(f"\n    rounded to 2dp: (a) {a[0]:+.2f}   (b) {b[0]:+.2f}")
con.close()
