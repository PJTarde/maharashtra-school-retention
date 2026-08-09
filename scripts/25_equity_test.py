"""Who is on the wrong side of the class 10 -> 11 doorway?

Splits the cliff by social category, then asks whether the doorway problem from
Finding 05 falls unevenly: are SC/ST pupils more likely to sit in a school that
ends at class 10, with nowhere to continue?
"""
import duckdb
import pandas as pd

DB = r"e:\pbl project\data\udise.duckdb"
YEARS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
PAIRS = list(zip(YEARS, YEARS[1:]))
Y0, Y1 = YEARS[-2], YEARS[-1]
CATS = ["General", "OBC", "SC", "ST"]
con = duckdb.connect(DB, read_only=True)

pd.set_option("display.width", 150)

# --------------------------------------------------------- 1. composition drift
print("=" * 78)
print("1  Who is in each grade?  Share of enrolment by category, 2025-26")
print("=" * 78)
comp = con.execute("""
    SELECT class_num,
           round(100.0*sum(total) FILTER (social_category='General')/sum(total),1) AS general,
           round(100.0*sum(total) FILTER (social_category='OBC')/sum(total),1) AS obc,
           round(100.0*sum(total) FILTER (social_category='SC')/sum(total),1) AS sc,
           round(100.0*sum(total) FILTER (social_category='ST')/sum(total),1) AS st,
           sum(total) AS pupils
    FROM enrol_social_class WHERE year='2025-26' AND class_num BETWEEN 1 AND 12
    GROUP BY 1 ORDER BY 1""").fetchdf()
print(comp.to_string(index=False))
print("\n  change from class 1 to class 12, in points:")
for c in ["general", "obc", "sc", "st"]:
    d = comp[comp.class_num == 12][c].iloc[0] - comp[comp.class_num == 1][c].iloc[0]
    print(f"    {c:<8} {d:+.1f}")

# ------------------------------------------------------------ 2. cliff by caste
print("\n" + "=" * 78)
print("2  Class 10 -> 11 retention by social category")
print("=" * 78)
parts = []
for y0, y1 in PAIRS:
    parts.append(f"""
        SELECT '{y0}\u2192{y1}' AS period, a.social_category,
               a.t0, b.t1, a.b0, b.b1, a.g0, b.g1
        FROM (SELECT social_category, sum(total) t0, sum(boys) b0, sum(girls) g0
              FROM enrol_social_class WHERE year='{y0}' AND class_num=10
              GROUP BY 1) a
        JOIN (SELECT social_category, sum(total) t1, sum(boys) b1, sum(girls) g1
              FROM enrol_social_class WHERE year='{y1}' AND class_num=11
              GROUP BY 1) b USING (social_category)""")
cliff = con.execute(f"""
    SELECT period, social_category,
           t0 AS class10, t1 AS class11,
           round(100.0*t1/t0,1) AS retention,
           round(100.0*b1/b0,1) AS boys,
           round(100.0*g1/g0,1) AS girls,
           t0 - t1 AS lost
    FROM ({" UNION ALL ".join(parts)})
    ORDER BY period, retention""").fetchdf()
latest = cliff[cliff.period == f"{Y0}\u2192{Y1}"]
print(latest.to_string(index=False))

print(f"\n  stability across all four pairs (retention %):")
piv = cliff.pivot(index="social_category", columns="period", values="retention")
print(piv.to_string())

# --------------------------------------------- 3. does the doorway fall unevenly?
print("\n" + "=" * 78)
print("3  Is the doorway problem itself unequal?")
print("   Share of each category's class-10 pupils in a school that ENDS at class 10")
print("=" * 78)
door = con.execute(f"""
    SELECT e.social_category,
           sum(e.total) AS c10_pupils,
           round(100.0*sum(e.total) FILTER (s.highclass = 10)/sum(e.total),1) AS pct_must_move,
           round(100.0*sum(e.total) FILTER (s.location='Rural')/sum(e.total),1) AS pct_rural,
           round(100.0*sum(e.total) FILTER (s.management_group='Government')/sum(e.total),1) AS pct_govt
    FROM enrol_social_class e JOIN school_year s USING (year, pseudocode)
    WHERE e.year='{Y0}' AND e.class_num=10
    GROUP BY 1 ORDER BY pct_must_move DESC""").fetchdf()
print(door.to_string(index=False))

# ---------------------------------------------------- 4. ST concentration by district
print("\n" + "=" * 78)
print("4  Districts where ST pupils are most concentrated, and how they fare")
print("=" * 78)
D = """CASE trim(district)
    WHEN 'AURANGABAD (MAHARASHTRA)' THEN 'CHHATRAPATI SAMBHAJINAGAR'
    WHEN 'OSMANABAD' THEN 'DHARASHIV'
    WHEN 'AHMADNAGAR' THEN 'AHILYANAGAR' ELSE trim(district) END"""
st = con.execute(f"""
    WITH c10 AS (
        SELECT {D} AS district, e.social_category, sum(e.total) t0,
               sum(e.total) FILTER (s.highclass=10) must_move
        FROM enrol_social_class e JOIN school_year s USING (year, pseudocode)
        WHERE e.year='{Y0}' AND e.class_num=10 GROUP BY 1,2
    ),
    c11 AS (
        SELECT {D} AS district, e.social_category, sum(e.total) t1
        FROM enrol_social_class e JOIN school_year s USING (year, pseudocode)
        WHERE e.year='{Y1}' AND e.class_num=11 GROUP BY 1,2
    ),
    tot AS (SELECT district, sum(t0) all10 FROM c10 GROUP BY 1)
    SELECT c10.district,
           round(100.0*c10.t0/tot.all10,1) AS pct_st_of_class10,
           c10.t0 AS st_class10,
           round(100.0*c10.must_move/c10.t0,1) AS st_pct_must_move,
           round(100.0*c11.t1/c10.t0,1) AS st_retention
    FROM c10 JOIN tot USING (district) LEFT JOIN c11 USING (district, social_category)
    WHERE c10.social_category='ST'
    ORDER BY pct_st_of_class10 DESC LIMIT 10""").fetchdf()
print(st.to_string(index=False))

# ------------------------------------------------------------- 5. gender x caste
print("\n" + "=" * 78)
print(f"5  Gender gap at the cliff within each category ({Y0} -> {Y1})")
print("=" * 78)
g = latest[["social_category", "boys", "girls"]].copy()
g["gap_girls_minus_boys"] = (g.girls - g.boys).round(1)
print(g.sort_values("gap_girls_minus_boys", ascending=False).to_string(index=False))

out = r"e:\pbl project\data\analysis"
cliff.to_csv(f"{out}/equity_cliff.csv", index=False)
comp.to_csv(f"{out}/equity_composition.csv", index=False)
door.to_csv(f"{out}/equity_doorway.csv", index=False)
print(f"\nwrote equity_*.csv to {out}")
con.close()
