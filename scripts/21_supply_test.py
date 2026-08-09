"""Does the class 10 -> 11 cliff track the SUPPLY of higher-secondary places?

The report asserted this but never tested it. The sharp test available in this
data is institutional, not geographic: a pupil in a school that already runs
class 11 can continue in place; a pupil in a school that ends at class 10 must
find a different institution. `highclass` gives us that split directly.

Two tests:
  1. School level -- in-place continuation for schools that DO offer class 11.
     If supply is the constraint, these should retain far above the state's 80%.
  2. Block level -- does the share of class-10 pupils stuck in terminal-at-10
     schools predict how much a block loses? Run against infrastructure as a
     competing explanation, on n~400 blocks rather than 36 districts.
"""
import numpy as np
import pandas as pd
import duckdb

DB = r"e:\pbl project\data\udise.duckdb"
Y0, Y1 = "2024-25", "2025-26"

con = duckdb.connect(DB, read_only=True)

DISTRICT = """CASE trim(district)
    WHEN 'AURANGABAD (MAHARASHTRA)' THEN 'CHHATRAPATI SAMBHAJINAGAR'
    WHEN 'OSMANABAD' THEN 'DHARASHIV'
    WHEN 'AHMADNAGAR' THEN 'AHILYANAGAR'
    ELSE trim(district) END"""

IND = """
    (drinking_water_func_yn=1)::INT + (electricity_availability=1)::INT
  + (library_availability=1)::INT + (playground_available=1)::INT
  + (availability_ramps=1)::INT + (handwash_near_toilet=1)::INT
  + (coalesce(desktop,0)+coalesce(laptop,0)+coalesce(tablet,0)>=1)::INT
  + (internet=1)::INT + (medical_checkups=1)::INT
  + (school_type<>1 AND total_girls_func_toilet>=1)::INT
  + (school_type<>2 AND total_boys_func_toilet>=1)::INT"""
APP = """
    1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1
  + (school_type<>1)::INT + (school_type<>2)::INT"""

# ---------------------------------------------------------------- test 1
print("=" * 78)
print("TEST 1  In-place continuation, by whether the school offers class 11")
print("=" * 78)

t1 = con.execute(f"""
    WITH base AS (
        SELECT s.pseudocode, s.highclass, s.district, s.location,
               s.management_group, e.total AS c10
        FROM school_year s
        JOIN enrol_class e USING (year, pseudocode)
        WHERE s.year = '{Y0}' AND e.class_num = 10 AND e.total > 0
    ),
    nxt AS (
        SELECT pseudocode, total AS c11 FROM enrol_class
        WHERE year = '{Y1}' AND class_num = 11
    )
    SELECT CASE WHEN b.highclass >= 11 THEN 'Offers class 11 (can continue in place)'
                ELSE 'Ends at class 10 (must change institution)' END AS school_kind,
           count(*) AS schools,
           sum(b.c10) AS c10_pupils,
           sum(coalesce(n.c11, 0)) AS c11_next_year_same_school,
           round(100.0 * sum(coalesce(n.c11, 0)) / sum(b.c10), 1) AS in_place_rate
    FROM base b LEFT JOIN nxt n USING (pseudocode)
    GROUP BY 1 ORDER BY 1""").fetchdf()
print(t1.to_string(index=False))

tot = con.execute(f"""
    SELECT sum(CASE WHEN year='{Y0}' AND class_num=10 THEN total END) c10,
           sum(CASE WHEN year='{Y1}' AND class_num=11 THEN total END) c11
    FROM enrol_class""").fetchone()
print(f"\n  state total: {tot[0]:,.0f} class-10 -> {tot[1]:,.0f} class-11 "
      f"= {100*tot[1]/tot[0]:.1f}% (the headline cliff)")

share = con.execute(f"""
    SELECT round(100.0 * sum(e.total) FILTER (s.highclass = 10) / sum(e.total), 1)
    FROM school_year s JOIN enrol_class e USING (year, pseudocode)
    WHERE s.year='{Y0}' AND e.class_num = 10""").fetchone()[0]
print(f"  {share}% of all class-10 pupils sit in a school that ends at class 10")

# ---------------------------------------------------------------- test 2
print("\n" + "=" * 78)
print("TEST 2  Block-level: does 'must change institution' predict the loss?")
print("=" * 78)

df = con.execute(f"""
    WITH blk AS (
        SELECT {DISTRICT} || ' | ' || coalesce(block, '?') AS block_key,
               {DISTRICT} AS district
        FROM school_year WHERE year='{Y0}' GROUP BY 1, 2
    ),
    sch AS (
        SELECT {DISTRICT} || ' | ' || coalesce(s.block, '?') AS block_key,
               s.pseudocode, s.highclass, s.location,
               ({IND})::DOUBLE / nullif(({APP}), 0) * 100 AS infra
        FROM school_year s WHERE s.year='{Y0}'
    ),
    c10 AS (
        SELECT sch.block_key, sch.pseudocode, sch.highclass, sch.location,
               sch.infra, e.total AS c10
        FROM sch JOIN enrol_class e ON e.pseudocode = sch.pseudocode
        WHERE e.year='{Y0}' AND e.class_num=10 AND e.total > 0
    ),
    c11 AS (
        SELECT sch.block_key, sum(e.total) AS c11
        FROM sch JOIN enrol_class e ON e.pseudocode = sch.pseudocode
        WHERE e.year='{Y1}' AND e.class_num=11
        GROUP BY 1
    ),
    agg AS (
        SELECT block_key,
               sum(c10) AS c10_pupils,
               sum(c10) FILTER (highclass = 10) AS c10_terminal,
               avg(infra) AS infra,
               100.0 * count(*) FILTER (location='Rural') / count(*) AS rural_pct
        FROM c10 GROUP BY 1
    )
    SELECT a.block_key, a.c10_pupils,
           100.0 * a.c10_terminal / a.c10_pupils AS pct_must_move,
           a.infra, a.rural_pct,
           100.0 * coalesce(c11.c11, 0) / a.c10_pupils AS retention
    FROM agg a LEFT JOIN c11 USING (block_key)
    WHERE a.c10_pupils >= 200""").fetchdf()

print(f"\n  {len(df)} blocks with >=200 class-10 pupils")
print(df[["pct_must_move", "infra", "rural_pct", "retention"]].describe()
      .loc[["mean", "std", "min", "max"]].round(1).to_string())


def ols(y, X, names):
    """Weighted-free OLS with R^2 and t-stats."""
    Xd = np.column_stack([np.ones(len(y))] + [X[c].values for c in names])
    beta, *_ = np.linalg.lstsq(Xd, y.values, rcond=None)
    resid = y.values - Xd @ beta
    n, k = Xd.shape
    ss_res, ss_tot = (resid ** 2).sum(), ((y.values - y.values.mean()) ** 2).sum()
    r2 = 1 - ss_res / ss_tot
    sigma2 = ss_res / (n - k)
    se = np.sqrt(np.diag(sigma2 * np.linalg.pinv(Xd.T @ Xd)))
    t = beta / se
    return beta, t, r2, ["intercept"] + names


print("\n  --- simple correlations with block retention ---")
for c in ["pct_must_move", "infra", "rural_pct"]:
    r = df[c].corr(df["retention"])
    print(f"    {c:<16} r = {r:+.3f}")

print("\n  --- univariate models ---")
for c in ["pct_must_move", "infra"]:
    b, t, r2, nm = ols(df["retention"], df, [c])
    print(f"    retention ~ {c:<16} R2 = {r2:.3f}   slope = {b[1]:+.3f} (t = {t[1]:+.1f})")

print("\n  --- multiple model: does supply survive controlling for infrastructure? ---")
b, t, r2, nm = ols(df["retention"], df, ["pct_must_move", "infra", "rural_pct"])
print(f"    R2 = {r2:.3f}")
for name, coef, tt in zip(nm, b, t):
    print(f"      {name:<16} {coef:+9.3f}   t = {tt:+6.1f}")

# standardised betas, to compare effect sizes on one scale
print("\n  --- standardised coefficients (comparable effect sizes) ---")
z = df.copy()
for c in ["pct_must_move", "infra", "rural_pct", "retention"]:
    z[c] = (z[c] - z[c].mean()) / z[c].std()
bz, tz, r2z, nmz = ols(z["retention"], z, ["pct_must_move", "infra", "rural_pct"])
for name, coef in zip(nmz[1:], bz[1:]):
    print(f"      {name:<16} beta = {coef:+.3f}")

print("\n  --- district level, for comparison with the report's r = 0.26 ---")
dd = con.execute(f"""
    WITH sch AS (
        SELECT {DISTRICT} AS district, s.pseudocode, s.highclass,
               ({IND})::DOUBLE / nullif(({APP}),0) * 100 AS infra
        FROM school_year s WHERE s.year='{Y0}'
    ),
    c10 AS (SELECT sch.district, sch.highclass, sch.infra, e.total c10
            FROM sch JOIN enrol_class e ON e.pseudocode=sch.pseudocode
            WHERE e.year='{Y0}' AND e.class_num=10),
    c11 AS (SELECT sch.district, sum(e.total) c11
            FROM sch JOIN enrol_class e ON e.pseudocode=sch.pseudocode
            WHERE e.year='{Y1}' AND e.class_num=11 GROUP BY 1)
    SELECT c10.district, sum(c10.c10) c10_pupils,
           100.0*sum(c10.c10) FILTER (highclass=10)/sum(c10.c10) AS pct_must_move,
           avg(c10.infra) AS infra,
           100.0*max(c11.c11)/sum(c10.c10) AS retention
    FROM c10 LEFT JOIN c11 USING (district) GROUP BY 1""").fetchdf()
dd = dd.dropna()
print(f"    {len(dd)} districts")
for c in ["pct_must_move", "infra"]:
    print(f"      {c:<16} r = {dd[c].corr(dd['retention']):+.3f}")

dd.sort_values("pct_must_move", ascending=False).to_csv(
    r"e:\pbl project\data\analysis\supply_by_district.csv", index=False)
df.sort_values("retention").to_csv(
    r"e:\pbl project\data\analysis\supply_by_block.csv", index=False)
print("\n  wrote supply_by_district.csv and supply_by_block.csv")
con.close()
