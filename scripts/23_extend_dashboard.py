"""Add the supply-test and over-age results to dashboard.json.

Run after 09_dashboard_data.py, which writes the base file.
"""
import json
from pathlib import Path

import numpy as np
import duckdb

ROOT = Path(r"e:\pbl project")
OUT = ROOT / "data" / "analysis"
Y0, Y1 = "2024-25", "2025-26"
con = duckdb.connect(str(ROOT / "data" / "udise.duckdb"), read_only=True)

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

data = json.loads((OUT / "dashboard.json").read_text())

# The base file derives the gender gap by subtracting two ALREADY-ROUNDED rates,
# which double-rounds (82.5 - 78.6 = 3.9 where the true gap is 3.957 -> 4.0).
# Recompute every cliff period from unrounded rates and round exactly once.
YEARS_ALL = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
data["cliff_by_period"] = [
    {"period": f"{y0}→{y1}",
     "retention": round(r[0], 1), "boys": round(r[2], 1), "girls": round(r[1], 1),
     "gap": round(r[1] - r[2], 1), "lost": int(r[3])}
    for y0, y1 in zip(YEARS_ALL, YEARS_ALL[1:])
    for r in [con.execute(f"""
        SELECT 100.0*b.t/a.t, 100.0*b.g/a.g, 100.0*b.bo/a.bo, a.t - b.t
        FROM (SELECT sum(total) t, sum(girls) g, sum(boys) bo FROM enrol_class
              WHERE year='{y0}' AND class_num=10) a,
             (SELECT sum(total) t, sum(girls) g, sum(boys) bo FROM enrol_class
              WHERE year='{y1}' AND class_num=11) b""").fetchone()]
]
data["headline"]["gender_gap"] = data["cliff_by_period"][-1]["gap"]

# ------------------------------------------------------------- supply split
# NOTE: pseudocode identifies a school, not a pupil, so a school's class-11 roll
# mixes its own continuing pupils with arrivals from schools that end at class 10.
# Nothing here can decompose that. Only the accounting identity is reported:
#   class_11_total = stayers_placed + movers_placed, each capped by its own base.
row = con.execute(f"""
    WITH c10 AS (
        SELECT s.pseudocode, s.highclass, e.total AS c10
        FROM school_year s JOIN enrol_class e USING (year, pseudocode)
        WHERE s.year='{Y0}' AND e.class_num=10 AND e.total>0
    ),
    c11 AS (SELECT pseudocode, total AS c11 FROM enrol_class
            WHERE year='{Y1}' AND class_num=11 AND total>0)
    SELECT
      (SELECT sum(c10) FROM c10 WHERE highclass >= 11),
      (SELECT sum(c10) FROM c10 WHERE highclass = 10),
      (SELECT count(*) FROM c10 WHERE highclass >= 11),
      (SELECT count(*) FROM c10 WHERE highclass = 10),
      (SELECT sum(c11) FROM c11 WHERE pseudocode IN
          (SELECT pseudocode FROM c10 WHERE highclass >= 11)),
      (SELECT sum(c11) FROM c11),
      (SELECT sum(c11) FROM c11 WHERE pseudocode NOT IN (SELECT pseudocode FROM c10))
""").fetchone()
can_stay, must_move, sch11, sch10, c11_cont, c11_total, c11_standalone = [float(x) for x in row]

data["supply"] = {
    "can_stay": int(can_stay), "must_move": int(must_move),
    "schools_with_11": int(sch11), "schools_without_11": int(sch10),
    "pct_must_move": round(100 * must_move / (can_stay + must_move), 1),
    "c11_total": int(c11_total),
    "c11_in_continuing": int(c11_cont),
    "c11_standalone": int(c11_standalone),
    # an intake ratio, NOT a continuation rate -- above 100% only proves those
    # schools are net importers of pupils
    "intake_ratio": round(100 * c11_cont / can_stay, 1),
    # what the identity forces, with no pupil-level assumption
    "movers_placed_min_pct": round(100 * (c11_total - can_stay) / must_move, 1),
    "stayers_placed_min_pct": round(100 * (c11_total - must_move) / can_stay, 1),
    "standalone_pct_of_movers": round(100 * c11_standalone / must_move, 1),
}

# --------------------------------------------------------- block scatter/model
blk = con.execute(f"""
    WITH sch AS (
        SELECT {DISTRICT} || ' | ' || coalesce(block,'?') AS block_key,
               {DISTRICT} AS district, pseudocode, highclass, location,
               ({IND})::DOUBLE/nullif(({APP}),0)*100 AS infra
        FROM school_year WHERE year='{Y0}'
    ),
    c10 AS (SELECT sch.*, e.total AS c10 FROM sch
            JOIN enrol_class e ON e.pseudocode=sch.pseudocode
            WHERE e.year='{Y0}' AND e.class_num=10 AND e.total>0),
    ov AS (SELECT sch.block_key, sum(a.total) c10a,
                  sum(a.total) FILTER (a.age>=16) c10_over
           FROM sch JOIN enrol_age a ON a.pseudocode=sch.pseudocode
           WHERE a.year='{Y0}' AND a.class_num=10 GROUP BY 1),
    c11 AS (SELECT sch.block_key, sum(e.total) c11 FROM sch
            JOIN enrol_class e ON e.pseudocode=sch.pseudocode
            WHERE e.year='{Y1}' AND e.class_num=11 GROUP BY 1),
    agg AS (SELECT block_key, any_value(district) district, sum(c10) c10_pupils,
                   100.0*sum(c10) FILTER (highclass=10)/sum(c10) pct_must_move,
                   avg(infra) infra,
                   100.0*count(*) FILTER (location='Rural')/count(*) rural_pct
            FROM c10 GROUP BY 1)
    SELECT a.*, 100.0*ov.c10_over/nullif(ov.c10a,0) AS pct_overage,
           100.0*coalesce(c11.c11,0)/a.c10_pupils AS retention
    FROM agg a LEFT JOIN ov USING (block_key) LEFT JOIN c11 USING (block_key)
    WHERE a.c10_pupils >= 200""").fetchdf().dropna()

data["block_scatter"] = [
    {"x": round(r.pct_must_move, 1), "y": round(min(r.retention, 160), 1),
     "n": int(r.c10_pupils)}
    for r in blk.itertuples()
]

# standardised effect sizes
z = blk.copy()
cols = ["pct_must_move", "pct_overage", "infra", "rural_pct"]
for c in cols + ["retention"]:
    z[c] = (z[c] - z[c].mean()) / z[c].std()
X = np.column_stack([np.ones(len(z))] + [z[c].values for c in cols])
beta, *_ = np.linalg.lstsq(X, z["retention"].values, rcond=None)
pred = X @ beta
r2 = 1 - ((z["retention"].values - pred)**2).sum() / \
     ((z["retention"].values - z["retention"].values.mean())**2).sum()

LABEL = {"pct_must_move": "Must change institution",
         "pct_overage": "Over-age pupils",
         "infra": "Infrastructure score",
         "rural_pct": "Rural share"}
data["effect_sizes"] = {
    "r2": round(r2, 3), "n_blocks": len(blk),
    "terms": [{"label": LABEL[c], "beta": round(b, 3),
               "r": round(blk[c].corr(blk["retention"]), 3)}
              for c, b in zip(cols, beta[1:])],
}

# ------------------------------------------------------------------ over-age
data["overage_by_grade"] = [
    {"class_num": int(r[0]), "boys": r[1], "girls": r[2], "gap": r[3], "all": r[4]}
    for r in con.execute("""
        SELECT class_num,
               round(100.0*sum(boys) FILTER (age>=class_num+6)/nullif(sum(boys),0),1),
               round(100.0*sum(girls) FILTER (age>=class_num+6)/nullif(sum(girls),0),1),
               round(100.0*sum(boys) FILTER (age>=class_num+6)/nullif(sum(boys),0)
                   - 100.0*sum(girls) FILTER (age>=class_num+6)/nullif(sum(girls),0),1),
               round(100.0*sum(total) FILTER (age>=class_num+6)/sum(total),1)
        FROM enrol_age WHERE year='2025-26' AND class_num BETWEEN 1 AND 12
        GROUP BY 1 ORDER BY 1""").fetchall()
]

data["overage_trend"] = [
    {"year": r[0], "pct": r[1]}
    for r in con.execute("""
        SELECT year, round(100.0*sum(total) FILTER (age>=16)/sum(total),1)
        FROM enrol_age WHERE class_num=10 GROUP BY 1 ORDER BY 1""").fetchall()
]

data["overage_segment"] = [
    {"location": r[0], "management": r[1], "pupils": int(r[2]), "pct": r[3]}
    for r in con.execute("""
        SELECT s.location, s.management_group, sum(a.total),
               round(100.0*sum(a.total) FILTER (a.age>=16)/sum(a.total),1)
        FROM enrol_age a JOIN school_year s USING (year, pseudocode)
        WHERE a.year='2025-26' AND a.class_num=10 AND s.location IS NOT NULL
          AND s.management_group IN ('Government','Private Aided','Private Unaided')
        GROUP BY 1,2 ORDER BY 4 DESC""").fetchall()
]

# ------------------------------------------------------------------- equity
CATS = ["General", "OBC", "SC", "ST"]

data["equity_cliff"] = [
    {"cat": r[0], "class10": int(r[1]), "class11": int(r[2]), "retention": r[3],
     "boys": r[4], "girls": r[5], "lost": int(r[1] - r[2])}
    for r in con.execute(f"""
        SELECT a.social_category, a.t0, b.t1,
               round(100.0*b.t1/a.t0,1), round(100.0*b.b1/a.b0,1), round(100.0*b.g1/a.g0,1)
        FROM (SELECT social_category, sum(total) t0, sum(boys) b0, sum(girls) g0
              FROM enrol_social_class WHERE year='{Y0}' AND class_num=10 GROUP BY 1) a
        JOIN (SELECT social_category, sum(total) t1, sum(boys) b1, sum(girls) g1
              FROM enrol_social_class WHERE year='{Y1}' AND class_num=11 GROUP BY 1) b
          USING (social_category)
        ORDER BY 4""").fetchall()
]

data["equity_doorway"] = [
    {"cat": r[0], "pct_must_move": r[1], "pct_rural": r[2], "pct_govt": r[3]}
    for r in con.execute(f"""
        SELECT e.social_category,
               round(100.0*sum(e.total) FILTER (s.highclass=10)/sum(e.total),1),
               round(100.0*sum(e.total) FILTER (s.location='Rural')/sum(e.total),1),
               round(100.0*sum(e.total) FILTER (s.management_group='Government')/sum(e.total),1)
        FROM enrol_social_class e JOIN school_year s USING (year, pseudocode)
        WHERE e.year='{Y0}' AND e.class_num=10 GROUP BY 1 ORDER BY 2 DESC""").fetchall()
]

data["equity_composition"] = [
    {"class_num": int(r[0]), "General": r[1], "OBC": r[2], "SC": r[3], "ST": r[4]}
    for r in con.execute("""
        SELECT class_num,
               round(100.0*sum(total) FILTER (social_category='General')/sum(total),1),
               round(100.0*sum(total) FILTER (social_category='OBC')/sum(total),1),
               round(100.0*sum(total) FILTER (social_category='SC')/sum(total),1),
               round(100.0*sum(total) FILTER (social_category='ST')/sum(total),1)
        FROM enrol_social_class WHERE year='2025-26' AND class_num BETWEEN 1 AND 12
        GROUP BY 1 ORDER BY 1""").fetchall()
]

YEARS_ALL = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
stab = []
for y0, y1 in zip(YEARS_ALL, YEARS_ALL[1:]):
    for r in con.execute(f"""
        SELECT a.social_category, round(100.0*b.t1/a.t0,1)
        FROM (SELECT social_category, sum(total) t0 FROM enrol_social_class
              WHERE year='{y0}' AND class_num=10 GROUP BY 1) a
        JOIN (SELECT social_category, sum(total) t1 FROM enrol_social_class
              WHERE year='{y1}' AND class_num=11 GROUP BY 1) b USING (social_category)
        """).fetchall():
        stab.append({"period": f"{y0}→{y1}", "cat": r[0], "retention": r[1]})
data["equity_stability"] = stab

data["st_districts"] = [
    {"district": " ".join(w.capitalize() for w in r[0].split()),
     "pct_st": r[1], "st_pupils": int(r[2]), "retention": r[3]}
    for r in con.execute(f"""
        WITH c10 AS (
            SELECT {DISTRICT} AS district, e.social_category, sum(e.total) t0
            FROM enrol_social_class e JOIN school_year s USING (year, pseudocode)
            WHERE e.year='{Y0}' AND e.class_num=10 GROUP BY 1,2),
        c11 AS (
            SELECT {DISTRICT} AS district, e.social_category, sum(e.total) t1
            FROM enrol_social_class e JOIN school_year s USING (year, pseudocode)
            WHERE e.year='{Y1}' AND e.class_num=11 GROUP BY 1,2),
        tot AS (SELECT district, sum(t0) all10 FROM c10 GROUP BY 1)
        SELECT c10.district, round(100.0*c10.t0/tot.all10,1), c10.t0,
               round(100.0*c11.t1/c10.t0,1)
        FROM c10 JOIN tot USING (district)
        LEFT JOIN c11 USING (district, social_category)
        WHERE c10.social_category='ST'
        ORDER BY 2 DESC LIMIT 8""").fetchall()
]

path = OUT / "dashboard.json"
path.write_text(json.dumps(data, indent=1))
print(f"extended {path} ({path.stat().st_size/1024:.0f} KB)")
print(json.dumps(data["supply"], indent=1))
print("\neffect sizes (standardised, block level):")
print(f"  R2 = {data['effect_sizes']['r2']}  n = {data['effect_sizes']['n_blocks']}")
for t in data["effect_sizes"]["terms"]:
    print(f"    {t['label']:<24} beta {t['beta']:+.3f}   r {t['r']:+.3f}")
print("\nover-age gender gap by grade:")
for g in data["overage_by_grade"]:
    if g["class_num"] >= 8:
        print(f"  class {g['class_num']:>2}: boys {g['boys']:>4}%  girls {g['girls']:>4}%  gap {g['gap']:+.1f}")
print("\nequity at the cliff:")
for e in data["equity_cliff"]:
    print(f"  {e['cat']:<8} {e['retention']:>5}%  lost {e['lost']:>7,}")
print("\ndoorway burden (should be similar if it does NOT explain the caste gap):")
for e in data["equity_doorway"]:
    print(f"  {e['cat']:<8} must-move {e['pct_must_move']:>5}%  rural {e['pct_rural']:>5}%")
con.close()
