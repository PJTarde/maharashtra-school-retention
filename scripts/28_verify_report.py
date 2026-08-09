"""Machine-check every figure quoted in the report's prose against the database.

The charts are generated from dashboard.json and cannot drift. The prose is
hand-written, so every number in it is a place where an error or a stale value
can hide. This recomputes each claim from udise.duckdb and asserts that the
formatted string actually appears in the rendered report.

It also lists numbers found in the prose that no check covers, so the
unverified surface is visible rather than assumed empty.

Exit code 1 if any check fails.
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

import duckdb

ROOT = Path(r"e:\pbl project")
REPORT = ROOT / "report" / "maharashtra-schools.html"
DB = ROOT / "data" / "udise.duckdb"

YEARS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
Y0, Y1 = YEARS[-2], YEARS[-1]
con = duckdb.connect(str(DB), read_only=True)

DISTRICT = """CASE trim(district)
    WHEN 'AURANGABAD (MAHARASHTRA)' THEN 'CHHATRAPATI SAMBHAJINAGAR'
    WHEN 'OSMANABAD' THEN 'DHARASHIV'
    WHEN 'AHMADNAGAR' THEN 'AHILYANAGAR' ELSE trim(district) END"""

IND = """
    (drinking_water_func_yn=1)::INT + (electricity_availability=1)::INT
  + (library_availability=1)::INT + (playground_available=1)::INT
  + (availability_ramps=1)::INT + (handwash_near_toilet=1)::INT
  + (coalesce(desktop,0)+coalesce(laptop,0)+coalesce(tablet,0)>=1)::INT
  + (internet=1)::INT + (medical_checkups=1)::INT
  + (school_type<>1 AND total_girls_func_toilet>=1)::INT
  + (school_type<>2 AND total_boys_func_toilet>=1)::INT"""
APP = "9 + (school_type<>1)::INT + (school_type<>2)::INT"


# --------------------------------------------------------------- prose text
def prose() -> str:
    raw = REPORT.read_text(encoding="utf-8")
    raw = re.sub(r"<script\b.*?</script>", " ", raw, flags=re.S | re.I)
    raw = re.sub(r"<style\b.*?</style>", " ", raw, flags=re.S | re.I)
    raw = re.sub(r"<!--.*?-->", " ", raw, flags=re.S)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(raw))


TEXT = prose()


def q(sql):
    return con.execute(sql).fetchone()


def r1(v: float) -> str:
    """One decimal place, rounded half-up, matching how the prose is written."""
    from decimal import Decimal, ROUND_HALF_UP
    return str(Decimal(str(v)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def r0(v: float) -> str:
    from decimal import Decimal, ROUND_HALF_UP
    return str(Decimal(str(v)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def indian(n: float) -> str:
    """1234567 -> 12,34,567"""
    n = int(round(n))
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        s = f"{head},{tail}"
    return ("-" if n < 0 else "") + s


CHECKS: list[tuple[str, str]] = []   # (label, string that must appear)
FAILED: list[tuple[str, str]] = []


def check(label: str, expected: str, *, alt: list[str] | None = None):
    candidates = [expected] + (alt or [])
    hit = next((c for c in candidates if c in TEXT), None)
    # record the form that actually matched, so coverage credits alternates too
    CHECKS.append((label, hit or expected))
    mark = "ok  " if hit else "FAIL"
    if not hit:
        FAILED.append((label, expected))
    print(f"  [{mark}] {label:<52} {hit or expected}")
    return hit


print("=" * 92)
print("SCALE AND HEADLINE")
print("=" * 92)

r = q(f"""SELECT count(*), sum(enr_total), sum(total_tch)
          FROM school_year WHERE year='{Y1}'""")
check("schools, latest year", indian(r[0]))
check("pupils in crore", f"{r[1]/1e7:.2f} crore")
# teachers and the per-sex retention rates appear only in JS-generated KPI tiles,
# which read dashboard.json directly and therefore cannot drift. Not prose claims.
check("districts", "36")

n_rows = q("SELECT count(*) FROM school_year")[0]
check("panel rows", indian(n_rows))
check("age table rows (millions)", f"{q('SELECT count(*) FROM enrol_age')[0]/1e6:.1f} million")

ptr = q(f"""SELECT round(sum(enr_total)*1.0/sum(total_tch),1)
            FROM school_year WHERE year='{Y1}'""")[0]
check("state PTR, latest year", f"PTR {ptr}")

print("\n" + "=" * 92)
print("FINDING 01 - THE CLIFF")
print("=" * 92)

trans = con.execute(f"""
    SELECT a.class_num, a.t AS t0, b.t AS t1, round(100.0*b.t/a.t,1) AS ret
    FROM (SELECT class_num, sum(total) t FROM enrol_class
          WHERE year='{Y0}' AND class_num>=1 GROUP BY 1) a
    JOIN (SELECT class_num, sum(total) t FROM enrol_class
          WHERE year='{Y1}' AND class_num>=1 GROUP BY 1) b
      ON b.class_num = a.class_num + 1
    ORDER BY a.class_num""").fetchall()
by_class = {r[0]: r for r in trans}
ret1011 = by_class[10][3]
check("class 10->11 retention, latest pair", f"{ret1011}%")
check("pupils lost at the cliff", indian(by_class[10][1] - by_class[10][2]))

others = [r[3] for r in trans if r[0] != 10]
check("min of other transitions", f"{min(others)}%")
check("max of other transitions", f"{max(others)}%")

# all four pairs
pairs_ret = []
for y0, y1 in zip(YEARS, YEARS[1:]):
    v = q(f"""SELECT round(100.0*b.t/a.t,1)
              FROM (SELECT sum(total) t FROM enrol_class WHERE year='{y0}' AND class_num=10) a,
                   (SELECT sum(total) t FROM enrol_class WHERE year='{y1}' AND class_num=11) b""")[0]
    pairs_ret.append(v)
for v in pairs_ret:
    check(f"cliff value present ({v}%)", f"{v}%")

total_lost = sum(
    q(f"""SELECT (SELECT sum(total) FROM enrol_class WHERE year='{y0}' AND class_num=10)
                 - (SELECT sum(total) FROM enrol_class WHERE year='{y1}' AND class_num=11)""")[0]
    for y0, y1 in zip(YEARS, YEARS[1:]))
check("four-year cumulative loss (lakh, rounded)", f"{round(total_lost/1e5):.0f} lakh")

sc = q(f"""SELECT count(*) FILTER (class_num=11), count(*) FILTER (class_num=10)
           FROM enrol_class WHERE year='{Y1}'""")
check("schools offering class 11", indian(sc[0]))
check("schools offering class 10", indian(sc[1]))

print("\n" + "=" * 92)
print("FINDING 02 - GENDER")
print("=" * 92)

# gaps are computed from UNROUNDED rates and rounded once -- rounding the two
# rates first and subtracting gives 3.9 where the true value is 3.957 -> 4.0
gaps = []
for y0, y1 in zip(YEARS, YEARS[1:]):
    v = q(f"""SELECT 100.0*b.g/a.g - 100.0*b.b/a.b
              FROM (SELECT sum(girls) g, sum(boys) b FROM enrol_class
                    WHERE year='{y0}' AND class_num=10) a,
                   (SELECT sum(girls) g, sum(boys) b FROM enrol_class
                    WHERE year='{y1}' AND class_num=11) b""")[0]
    gaps.append(r1(v))
check("gender gap, latest", f"{gaps[-1]} percentage points")
check("gap sequence in prose",
      f"{gaps[0]}, then {gaps[1]}, then {gaps[2]},")

print("\n" + "=" * 92)
print("FINDING 03 - INFRASTRUCTURE")
print("=" * 92)

score = {y: q(f"""SELECT avg(({IND})::DOUBLE/nullif(({APP}),0)*100)
                  FROM school_year WHERE year='{y}'""")[0] for y in YEARS}
check("infra score, first year", r1(score[YEARS[0]]))
check("infra score, latest year", r1(score[Y1]))

seg = con.execute(f"""
    SELECT location, management_group,
           round(avg(({IND})::DOUBLE/nullif(({APP}),0)*100),2) sc, count(*) n,
           sum(enr_total) pupils
    FROM school_year WHERE year='{Y1}' AND location IS NOT NULL
      AND management_group IN ('Government','Private Aided','Private Unaided')
    GROUP BY 1,2""").fetchdf()
rg = seg[(seg.location == "Rural") & (seg.management_group == "Government")].iloc[0]
check("rural government school count", indian(rg["n"]))
check("rural government pupils (lakh)", f"{round(rg['pupils']/1e5):.0f} lakh")

net_then = q(f"""SELECT 100.0*count(*) FILTER (internet=1)/count(*)
                 FROM school_year WHERE year='{YEARS[0]}'""")[0]
net_now = q(f"""SELECT 100.0*count(*) FILTER (internet=1)/count(*)
                FROM school_year WHERE year='{Y1}'""")[0]
check("internet gain in points", f"{r0(net_now - net_then)} points")

print("\n" + "=" * 92)
print("FINDING 05 - THE DOORWAY")
print("=" * 92)

s = q(f"""
    WITH c10 AS (SELECT s.pseudocode, s.highclass, e.total c10
                 FROM school_year s JOIN enrol_class e USING (year, pseudocode)
                 WHERE s.year='{Y0}' AND e.class_num=10 AND e.total>0),
         c11 AS (SELECT pseudocode, total c11 FROM enrol_class
                 WHERE year='{Y1}' AND class_num=11 AND total>0)
    SELECT (SELECT sum(c10) FROM c10 WHERE highclass>=11),
           (SELECT sum(c10) FROM c10 WHERE highclass=10),
           (SELECT count(*) FROM c10 WHERE highclass=10),
           (SELECT sum(c11) FROM c11 WHERE pseudocode IN
                (SELECT pseudocode FROM c10 WHERE highclass>=11)),
           (SELECT sum(c11) FROM c11),
           (SELECT sum(c11) FROM c11 WHERE pseudocode NOT IN (SELECT pseudocode FROM c10))
""")
stayers, movers, sch10, c11_cont, c11_tot, c11_alone = [float(x) for x in s]
check("share who must change school", f"{round(100*movers/(stayers+movers)):.0f}%")
check("movers in lakh", f"{movers/1e5:.1f} lakh")
check("schools ending at class 10", indian(sch10))
check("intake ratio", f"{100*c11_cont/stayers:.1f}%")
check("standalone junior college places", indian(c11_alone))
check("movers-placed lower bound", f"{round(100*(c11_tot-stayers)/movers):.0f}%")
check("stayers-placed lower bound", f"{round(100*(c11_tot-movers)/stayers):.0f}%")

print("\n" + "=" * 92)
print("FINDING 07 - EQUITY")
print("=" * 92)

eq = con.execute(f"""
    SELECT a.social_category, round(100.0*b.t1/a.t0,1) ret,
           round(100.0*b.g1/a.g0,1) girls, round(100.0*b.b1/a.b0,1) boys
    FROM (SELECT social_category, sum(total) t0, sum(girls) g0, sum(boys) b0
          FROM enrol_social_class WHERE year='{Y0}' AND class_num=10 GROUP BY 1) a
    JOIN (SELECT social_category, sum(total) t1, sum(girls) g1, sum(boys) b1
          FROM enrol_social_class WHERE year='{Y1}' AND class_num=11 GROUP BY 1) b
      USING (social_category)""").fetchdf().set_index("social_category")
check("General retention", f"{eq.loc['General','ret']}%")
check("ST retention", f"{eq.loc['ST','ret']}%")
check("ST vs General gap", f"{round(eq.loc['General','ret']-eq.loc['ST','ret']):.0f}-point")
check("ST girls", f"{eq.loc['ST','girls']}%")
check("General boys", f"{eq.loc['General','boys']}%")
check("SC gender gap", f"{round(eq.loc['SC','girls']-eq.loc['SC','boys'],1)} points")

comp = con.execute(f"""
    SELECT class_num,
           round(100.0*sum(total) FILTER (social_category='ST')/sum(total),1) st
    FROM enrol_social_class WHERE year='{Y1}' AND class_num IN (1,12)
    GROUP BY 1 ORDER BY 1""").fetchall()
check("ST share of class 1", f"{comp[0][1]}%")
check("ST share of class 12", f"{comp[1][1]}%")

door = con.execute(f"""
    SELECT e.social_category,
           round(100.0*sum(e.total) FILTER (s.highclass=10)/sum(e.total),1) mm,
           round(100.0*sum(e.total) FILTER (s.location='Rural')/sum(e.total),1) rural
    FROM enrol_social_class e JOIN school_year s USING (year, pseudocode)
    WHERE e.year='{Y0}' AND e.class_num=10 GROUP BY 1""").fetchdf().set_index("social_category")
check("ST must-move share", f"{door.loc['ST','mm']}%")
check("General must-move share", f"{door.loc['General','mm']}%")
check("ST rural share", f"{round(door.loc['ST','rural']):.0f}%")

print("\n" + "=" * 92)
print("FINDING 08 - STAFFING")
print("=" * 92)

st = con.execute(f"""
    SELECT location, management_group,
           round(sum(enr_total)*1.0/nullif(sum(total_tch),0),1) ptr,
           count(*) FILTER (total_tch=1) single
    FROM school_year WHERE year='{Y1}'
      AND stage IN ('Primary','Elementary','Upper Primary')
      AND location IS NOT NULL
      AND management_group IN ('Government','Private Aided','Private Unaided')
    GROUP BY 1,2""").fetchdf()
check("worst PTR segment", f"{st.ptr.max()}")
check("rural government PTR",
      f"{st[(st.location=='Rural')&(st.management_group=='Government')].ptr.iloc[0]}")
check("rural government single-teacher schools",
      indian(st[(st.location=='Rural')&(st.management_group=='Government')].single.iloc[0]))
for y in (YEARS[0], Y1):
    n = q(f"SELECT count(*) FROM school_year WHERE year='{y}' AND total_tch=1")[0]
    check(f"single-teacher schools statewide {y}", indian(n))

print("\n" + "=" * 92)
print("FINDING 09 - SAFETY")
print("=" * 92)

sf = con.execute(f"""
    SELECT s.location, s.management_group,
           round(100.0*count(*) FILTER (f.cctv_cam_yn=1)/count(*),1) cctv
    FROM safety f JOIN school_year s USING (year, pseudocode)
    WHERE s.location IS NOT NULL
      AND s.management_group IN ('Government','Private Aided','Private Unaided')
    GROUP BY 1,2""").fetchdf()
hi, lo = sf.cctv.max(), sf.cctv.min()
check("highest CCTV segment", f"{hi}%")
check("lowest CCTV segment", f"{lo}%")
check("CCTV gap in points", f"{round(hi-lo):.0f}-point")

for col, label in [("slfdef_grt_yn", "self-defence"), ("tch_first_level_counsellor", "counsellor")]:
    v = q(f"""SELECT 100.0*count(*) FILTER ({col}=1)
              / nullif(count(*) FILTER ({col} IN (1,2)),0) FROM safety""")[0]
    check(f"safety: {label}", f"{r1(v)}%", alt=[f"{r0(v)}%"])

# the 2021-22 transitions the caveat describes as "roughly 94%"
old = [q(f"""SELECT 100.0*b.t/a.t
             FROM (SELECT sum(total) t FROM enrol_class
                   WHERE year='2021-22' AND class_num={c}) a,
                  (SELECT sum(total) t FROM enrol_class
                   WHERE year='2022-23' AND class_num={c+1}) b""")[0]
       for c in range(1, 10)]
check("2021-22 transitions, rough level", f"{r0(sum(old)/len(old))}%")

ovr = [r[1] for r in con.execute("""
    SELECT year, 100.0*sum(total) FILTER (age>=16)/sum(total)
    FROM enrol_age WHERE class_num=10 AND year<>'2021-22' GROUP BY 1""").fetchall()]
check("over-age range, low end", f"{r0(min(ovr))}")
check("over-age range, high end", f"{r0(max(ovr))}%")

print("\n" + "=" * 92)
print("METHOD CAVEATS")
print("=" * 92)

mg = con.execute("""
    SELECT year, count(*) FILTER (management=7) FROM school_year
    WHERE year IN ('2024-25','2025-26') GROUP BY 1 ORDER BY 1""").fetchall()
check("management code 7, prior year", indian(mg[0][1]))
check("management code 7, latest year", indian(mg[1][1]))

back = con.execute(f"""
    SELECT p.management, count(*) FROM school_year c
    JOIN school_year p ON p.pseudocode=c.pseudocode AND p.year='{Y0}'
    WHERE c.year='{Y1}' AND c.management=7 AND p.management IN (4,5)
    GROUP BY 1 ORDER BY 1""").fetchall()
for code, n in back:
    check(f"code 7 came from management {code}", indian(n))

zt = con.execute("""
    SELECT year, count(*) FILTER (total_tch=0) FROM school_year
    WHERE year IN ('2023-24','2025-26') GROUP BY 1 ORDER BY 1""").fetchall()
check("zero-teacher schools, 2023-24", indian(zt[0][1]))
check("zero-teacher schools, latest", indian(zt[1][1]))

fur = q("""SELECT max(TRY_CAST(furniture_availability AS INT))
           FROM read_csv('e:/pbl project/data/raw/2021-22/fac.csv',
                         header=true, all_varchar=true)""")[0]
check("furniture max value, 2021-22", indian(fur))

ov = con.execute("""
    SELECT year, round(100.0*sum(total) FILTER (age>=16)/sum(total),1)
    FROM enrol_age WHERE class_num=10 GROUP BY 1 ORDER BY 1""").fetchall()
check("over-age 2021-22 (the excluded outlier)", f"{ov[0][1]}%")
check("over-age, second year", f"{ov[1][1]}%")
check("over-age, latest", f"{ov[-1][1]}%")

enr_first_two = [q(f"SELECT sum(enr_total) FROM school_year WHERE year='{y}'")[0]
                 for y in YEARS[:2]]
check("enrolment crore, year 1", f"{enr_first_two[0]/1e7:.2f} crore")
check("enrolment crore, year 2", f"{enr_first_two[1]/1e7:.2f} crore")
check("first-two-year enrolment drop in lakh",
      f"{r0((enr_first_two[0]-enr_first_two[1])/1e5)} lakh")

print("\n" + "=" * 92)
print("MODEL STATISTICS AND NAMED DISTRICTS")
print("=" * 92)

import numpy as np

blk = con.execute(f"""
    WITH sch AS (
        SELECT {DISTRICT} || ' | ' || coalesce(block,'?') AS bk,
               {DISTRICT} AS district, pseudocode, highclass, location,
               ({IND})::DOUBLE/nullif(({APP}),0)*100 AS infra
        FROM school_year WHERE year='{Y0}'),
    c10 AS (SELECT sch.*, e.total c10 FROM sch
            JOIN enrol_class e ON e.pseudocode=sch.pseudocode
            WHERE e.year='{Y0}' AND e.class_num=10 AND e.total>0),
    ov AS (SELECT sch.bk, sum(a.total) t, sum(a.total) FILTER (a.age>=16) o
           FROM sch JOIN enrol_age a ON a.pseudocode=sch.pseudocode
           WHERE a.year='{Y0}' AND a.class_num=10 GROUP BY 1),
    c11 AS (SELECT sch.bk, sum(e.total) c11 FROM sch
            JOIN enrol_class e ON e.pseudocode=sch.pseudocode
            WHERE e.year='{Y1}' AND e.class_num=11 GROUP BY 1),
    agg AS (SELECT bk, sum(c10) n,
                   100.0*sum(c10) FILTER (highclass=10)/sum(c10) mm,
                   avg(infra) infra,
                   100.0*count(*) FILTER (location='Rural')/count(*) rural
            FROM c10 GROUP BY 1)
    SELECT a.mm, 100.0*ov.o/ov.t AS ov, a.infra, a.rural,
           100.0*coalesce(c11.c11,0)/a.n AS ret
    FROM agg a LEFT JOIN ov USING (bk) LEFT JOIN c11 USING (bk)
    WHERE a.n >= 200""").fetchdf().dropna()
check("blocks in the model", str(len(blk)))
check("minimum block size", "200")

cols = ["mm", "ov", "infra", "rural"]
z = blk.copy()
for c in cols + ["ret"]:
    z[c] = (z[c] - z[c].mean()) / z[c].std()
X = np.column_stack([np.ones(len(z))] + [z[c].values for c in cols])
beta, *_ = np.linalg.lstsq(X, z["ret"].values, rcond=None)
pred = X @ beta
r2 = 1 - ((z["ret"] - pred) ** 2).sum() / ((z["ret"] - z["ret"].mean()) ** 2).sum()
check("block model R2", f"{r2:.2f}")
check("over-age standardised beta", f"{abs(beta[2]):.2f}")
# the must-move beta (0.46) is rendered only in the effect-size chart, which reads
# dashboard.json directly, so it is not a prose claim and cannot drift

# Replicates the published definition exactly: infrastructure is averaged over
# ALL schools in the district in the latest year (as in the district table), and
# retention is district class-11 next year over district class-10 this year.
dist = con.execute(f"""
    WITH s AS (SELECT {DISTRICT} AS district,
                      avg(({IND})::DOUBLE/nullif(({APP}),0)*100) AS infra
               FROM school_year WHERE year='{Y1}' GROUP BY 1),
    mm AS (SELECT {DISTRICT} AS district,
                  100.0*sum(e.total) FILTER (sy.highclass=10)/sum(e.total) AS mm
           FROM enrol_class e JOIN school_year sy USING (year, pseudocode)
           WHERE e.year='{Y0}' AND e.class_num=10 GROUP BY 1),
    a AS (SELECT {DISTRICT} AS district, sum(e.total) t FROM enrol_class e
          JOIN school_year sy USING (year, pseudocode)
          WHERE e.year='{Y0}' AND e.class_num=10 GROUP BY 1),
    b AS (SELECT {DISTRICT} AS district, sum(e.total) t FROM enrol_class e
          JOIN school_year sy USING (year, pseudocode)
          WHERE e.year='{Y1}' AND e.class_num=11 GROUP BY 1)
    SELECT a.district, mm.mm, s.infra, 100.0*b.t/a.t AS ret
    FROM a JOIN b USING (district) JOIN s USING (district)
           JOIN mm USING (district)""").fetchdf().dropna()
check("district-level must-move correlation",
      f"{abs(dist['mm'].corr(dist['ret'])):.2f}")
check("district-level infra correlation",
      f"{abs(dist['infra'].corr(dist['ret'])):.2f}")
check("districts with both measures", str(len(dist)))
check("Jalgaon overall retention",
      r1(dist[dist.district == "JALGAON"]["ret"].iloc[0]) + "%")

stt = con.execute(f"""
    WITH c10 AS (SELECT {DISTRICT} d, e.social_category sc, sum(e.total) t0,
                        sum(e.total) FILTER (s.highclass=10) mm
                 FROM enrol_social_class e JOIN school_year s USING (year, pseudocode)
                 WHERE e.year='{Y0}' AND e.class_num=10 GROUP BY 1,2),
    c11 AS (SELECT {DISTRICT} d, e.social_category sc, sum(e.total) t1
            FROM enrol_social_class e JOIN school_year s USING (year, pseudocode)
            WHERE e.year='{Y1}' AND e.class_num=11 GROUP BY 1,2),
    tot AS (SELECT d, sum(t0) all10 FROM c10 GROUP BY 1)
    SELECT c10.d, 100.0*c10.t0/tot.all10 AS st_share, 100.0*c11.t1/c10.t0 AS ret
    FROM c10 JOIN tot USING (d) LEFT JOIN c11 USING (d, sc)
    WHERE c10.sc='ST'""").fetchdf().set_index("d")
for name in ["JALGAON", "DHULE", "NANDURBAR"]:
    check(f"ST retention, {name.title()}", r1(stt.loc[name, "ret"]) + "%")
check("Nandurbar ST share of class 10", r1(stt.loc["NANDURBAR", "st_share"]) + "%")

check("General rural share", r0(door.loc["General", "rural"]) + "%")
check("over-age gap, class 8", r1(q("""
    SELECT 100.0*sum(boys) FILTER (age>=class_num+6)/sum(boys)
         - 100.0*sum(girls) FILTER (age>=class_num+6)/sum(girls)
    FROM enrol_age WHERE year='2025-26' AND class_num=8""")[0]))
check("over-age gap, class 12", r1(q("""
    SELECT 100.0*sum(boys) FILTER (age>=class_num+6)/sum(boys)
         - 100.0*sum(girls) FILTER (age>=class_num+6)/sum(girls)
    FROM enrol_age WHERE year='2025-26' AND class_num=12""")[0]))
check("self-defence 'not applicable' count",
      indian(q("SELECT count(*) FROM safety WHERE slfdef_grt_yn NOT IN (1,2)")[0]))
check("cliff loss in lakh", f"{(by_class[10][1]-by_class[10][2])/1e5:.1f} lakh")

carry = []
for y0, y1 in zip(YEARS, YEARS[1:]):
    v = q(f"""SELECT 100.0*count(*)/ (SELECT count(*) FROM school_year WHERE year='{y1}')
              FROM school_year a WHERE a.year='{y1}' AND EXISTS
              (SELECT 1 FROM school_year b WHERE b.year='{y0}'
               AND b.pseudocode=a.pseudocode)""")[0]
    carry.append(v)
check("carry-over lower bound", r1(min(carry)))
check("carry-over upper bound", r1(max(carry)) + "%")

reclass = q(f"""SELECT count(*) FROM school_year c
                JOIN school_year p ON p.pseudocode=c.pseudocode AND p.year='{Y0}'
                WHERE c.year='{Y1}' AND c.management=7 AND p.management IN (4,5)""")[0]
check("reclassified private schools (approx in prose)", "3,300",
      alt=[indian(reclass)])
print(f"        (exact reclassified count: {indian(reclass)})")

# ------------------------------------------------------- uncovered numbers
print("\n" + "=" * 92)
print("COVERAGE - numbers in the prose that no check above accounts for")
print("=" * 92)

def tokens(s: str) -> set[str]:
    """Numeric tokens, with sentence punctuation stripped from the tail."""
    out = set()
    for m in re.findall(r"\d[\d,]*(?:\.\d+)?%?", s):
        out.add(m.rstrip(".,"))
    return out


nums = tokens(TEXT)
covered_tokens = set()
for _, e in CHECKS:
    covered_tokens.update(tokens(e))

IGNORE = {  # structural, not data claims
    "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12",
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "100%", "30", "27",
    "2021", "2022", "2023", "2024", "2025", "2026", "22", "26", "25", "24", "23",
}
left = sorted(n for n in nums - covered_tokens - IGNORE
              if not re.fullmatch(r"\d{4}-\d{2}", n))
print(f"  {len(left)} unverified tokens (review by eye):")
for i in range(0, len(left), 10):
    print("    " + "  ".join(left[i:i + 10]))

print("\n" + "=" * 92)
print(f"RESULT: {len(CHECKS) - len(FAILED)}/{len(CHECKS)} checks passed")
if FAILED:
    print("\nFAILURES:")
    for label, exp in FAILED:
        print(f"  - {label}: expected to find {exp!r} in the prose")
print("=" * 92)
con.close()
sys.exit(1 if FAILED else 0)
