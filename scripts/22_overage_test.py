"""Is over-age enrolment an early-warning signal for the class 10 -> 11 cliff?

Nominal age for class N is N+5 (validated in 20_build_age.py: modal age climbs
exactly one year per grade). A pupil at N+6 or older is over-age -- the standard
leading indicator of dropout, because it means repetition or late entry.

Tests:
  1. How much over-age enrolment is there, and where does it concentrate?
  2. Does over-age share in class 10 predict whether those pupils continue --
     at school level (schools that offer class 11, so continuation is in-place
     and measurable) and at block level alongside the supply variable.
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
APP = "9 + (school_type<>1)::INT + (school_type<>2)::INT"

print("=" * 78)
print("1  Over-age enrolment by class, 2025-26  (nominal age for class N = N+5)")
print("=" * 78)
print(con.execute("""
    SELECT class_num,
           sum(total) AS pupils,
           round(100.0*sum(total) FILTER (age >= class_num + 6)/sum(total), 1) AS pct_overage,
           round(100.0*sum(total) FILTER (age >= class_num + 7)/sum(total), 1) AS pct_2plus,
           round(100.0*sum(girls) FILTER (age >= class_num + 6)/nullif(sum(girls),0), 1) AS pct_overage_girls,
           round(100.0*sum(boys)  FILTER (age >= class_num + 6)/nullif(sum(boys),0), 1) AS pct_overage_boys
    FROM enrol_age WHERE year='2025-26' AND class_num BETWEEN 1 AND 12
    GROUP BY 1 ORDER BY 1""").fetchdf().to_string(index=False))

print("\n=== over-age in class 10 by segment ===")
print(con.execute(f"""
    SELECT s.location, s.management_group,
           sum(a.total) AS c10_pupils,
           round(100.0*sum(a.total) FILTER (a.age >= 16)/sum(a.total), 1) AS pct_overage
    FROM enrol_age a JOIN school_year s USING (year, pseudocode)
    WHERE a.year='2025-26' AND a.class_num=10 AND s.location IS NOT NULL
      AND s.management_group IN ('Government','Private Aided','Private Unaided')
    GROUP BY 1,2 ORDER BY pct_overage DESC""").fetchdf().to_string(index=False))

print("\n=== over-age trend across the panel (class 10) ===")
print(con.execute("""
    SELECT year, sum(total) c10_pupils,
           round(100.0*sum(total) FILTER (age >= 16)/sum(total), 1) AS pct_overage
    FROM enrol_age WHERE class_num=10 GROUP BY 1 ORDER BY 1""").fetchdf().to_string(index=False))

# ------------------------------------------------------------------ test 2
print("\n" + "=" * 78)
print("2  Does over-age in class 10 predict continuation to class 11?")
print("=" * 78)

sch = con.execute(f"""
    WITH ov AS (
        SELECT pseudocode,
               sum(total) AS c10,
               100.0*sum(total) FILTER (age >= 16)/sum(total) AS pct_overage
        FROM enrol_age WHERE year='{Y0}' AND class_num=10 GROUP BY 1
    ),
    nxt AS (
        SELECT pseudocode, total AS c11 FROM enrol_class
        WHERE year='{Y1}' AND class_num=11
    )
    SELECT s.pseudocode, ov.c10, ov.pct_overage,
           coalesce(nxt.c11, 0) AS c11,
           100.0*coalesce(nxt.c11,0)/ov.c10 AS continuation,
           ({IND})::DOUBLE/nullif(({APP}),0)*100 AS infra,
           (s.location='Rural')::INT AS rural,
           s.management_group
    FROM school_year s
    JOIN ov USING (pseudocode)
    LEFT JOIN nxt USING (pseudocode)
    WHERE s.year='{Y0}' AND s.highclass >= 11 AND ov.c10 >= 20""").fetchdf()

print(f"\n  {len(sch):,} schools that offer class 11 and had >=20 class-10 pupils")
print(f"  mean in-place continuation {sch.continuation.mean():.1f}%  "
      f"| mean over-age {sch.pct_overage.mean():.1f}%")

print("\n  continuation by over-age quintile:")
sch["q"] = pd.qcut(sch.pct_overage, 5, labels=["Q1 lowest", "Q2", "Q3", "Q4", "Q5 highest"],
                   duplicates="drop")
print(sch.groupby("q", observed=True).agg(
    schools=("c10", "size"), mean_overage=("pct_overage", "mean"),
    c10=("c10", "sum"), c11=("c11", "sum")).assign(
    continuation=lambda d: 100*d.c11/d.c10).round(1).to_string())


def ols(y, X, names):
    """OLS, dropping any row with a non-finite value in y or the regressors."""
    yv = y.values.astype(float)
    cols = [X[c].values.astype(float) for c in names]
    ok = np.isfinite(yv)
    for c in cols:
        ok &= np.isfinite(c)
    yv = yv[ok]
    Xd = np.column_stack([np.ones(ok.sum())] + [c[ok] for c in cols])
    beta, *_ = np.linalg.lstsq(Xd, yv, rcond=None)
    resid = yv - Xd @ beta
    n, k = Xd.shape
    r2 = 1 - (resid**2).sum() / ((yv - yv.mean())**2).sum()
    se = np.sqrt(np.diag((resid**2).sum()/(n-k) * np.linalg.pinv(Xd.T @ Xd)))
    return beta, beta/se, r2, ["intercept"] + names, int(ok.sum())


print("\n  school-level model (continuation capped at 200% to limit outliers).")
print("  NOTE: in-place continuation counts pupils arriving from other schools,")
print("  so it measures retention AND intake. Read the sign with that in mind.")
s2 = sch[sch.continuation <= 200].copy()
b, t, r2, nm, n = ols(s2["continuation"], s2, ["pct_overage", "infra", "rural"])
print(f"    n = {n:,}   R2 = {r2:.3f}")
for name, coef, tt in zip(nm, b, t):
    print(f"      {name:<14} {coef:+9.3f}   t = {tt:+6.1f}")

print("\n  --- boys vs girls: is the gender gap in the cliff an over-age story? ---")
print(con.execute("""
    SELECT class_num,
           round(100.0*sum(boys) FILTER (age >= class_num+6)/nullif(sum(boys),0), 1) AS boys_overage,
           round(100.0*sum(girls) FILTER (age >= class_num+6)/nullif(sum(girls),0), 1) AS girls_overage,
           round(100.0*sum(boys) FILTER (age >= class_num+6)/nullif(sum(boys),0)
               - 100.0*sum(girls) FILTER (age >= class_num+6)/nullif(sum(girls),0), 1) AS gap
    FROM enrol_age WHERE year='2025-26' AND class_num BETWEEN 8 AND 12
    GROUP BY 1 ORDER BY 1""").fetchdf().to_string(index=False))

# ---------------------------------------------------- block-level joint model
print("\n" + "=" * 78)
print("3  Joint block model: supply vs over-age vs infrastructure")
print("=" * 78)

blk = con.execute(f"""
    WITH sch AS (
        SELECT {DISTRICT} || ' | ' || coalesce(block,'?') AS block_key,
               pseudocode, highclass, location,
               ({IND})::DOUBLE/nullif(({APP}),0)*100 AS infra
        FROM school_year WHERE year='{Y0}'
    ),
    c10 AS (
        SELECT sch.block_key, sch.highclass, sch.location, sch.infra,
               e.total AS c10, sch.pseudocode
        FROM sch JOIN enrol_class e ON e.pseudocode=sch.pseudocode
        WHERE e.year='{Y0}' AND e.class_num=10 AND e.total>0
    ),
    ov AS (
        SELECT sch.block_key,
               sum(a.total) AS c10a,
               sum(a.total) FILTER (a.age >= 16) AS c10_over
        FROM sch JOIN enrol_age a ON a.pseudocode=sch.pseudocode
        WHERE a.year='{Y0}' AND a.class_num=10 GROUP BY 1
    ),
    c11 AS (
        SELECT sch.block_key, sum(e.total) AS c11
        FROM sch JOIN enrol_class e ON e.pseudocode=sch.pseudocode
        WHERE e.year='{Y1}' AND e.class_num=11 GROUP BY 1
    ),
    agg AS (
        SELECT block_key, sum(c10) c10_pupils,
               100.0*sum(c10) FILTER (highclass=10)/sum(c10) AS pct_must_move,
               avg(infra) AS infra,
               100.0*count(*) FILTER (location='Rural')/count(*) AS rural_pct
        FROM c10 GROUP BY 1
    )
    SELECT a.*, 100.0*ov.c10_over/nullif(ov.c10a,0) AS pct_overage,
           100.0*coalesce(c11.c11,0)/a.c10_pupils AS retention
    FROM agg a LEFT JOIN ov USING (block_key) LEFT JOIN c11 USING (block_key)
    WHERE a.c10_pupils >= 200""").fetchdf().dropna()

print(f"\n  {len(blk)} blocks")
for c in ["pct_must_move", "pct_overage", "infra"]:
    print(f"    {c:<16} r with retention = {blk[c].corr(blk['retention']):+.3f}")

b, t, r2, nm, n = ols(blk["retention"], blk, ["pct_must_move", "pct_overage", "infra", "rural_pct"])
print(f"\n  joint model  n = {n}  R2 = {r2:.3f}")
for name, coef, tt in zip(nm, b, t):
    print(f"      {name:<16} {coef:+9.3f}   t = {tt:+6.1f}")

z = blk.copy()
for c in ["pct_must_move", "pct_overage", "infra", "rural_pct", "retention"]:
    z[c] = (z[c] - z[c].mean()) / z[c].std()
bz, _, _, nmz, _ = ols(z["retention"], z, ["pct_must_move", "pct_overage", "infra", "rural_pct"])
print("\n  standardised effect sizes:")
for name, coef in zip(nmz[1:], bz[1:]):
    print(f"      {name:<16} beta = {coef:+.3f}")

blk.to_csv(r"e:\pbl project\data\analysis\block_model.csv", index=False)
print("\n  wrote block_model.csv")
con.close()
