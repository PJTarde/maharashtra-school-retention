"""Cohort retention + infrastructure equity analysis on the harmonised UDISE panel.

Two questions:
  1. Where do Maharashtra's students disappear between grades, and is the loss
     gendered?  Because pupils change school at the stage boundaries, cohort
     tracking is done on district/state aggregates, never school-by-school.
  2. Does school infrastructure vary systematically by location, management and
     district -- and does it move with retention?

Writes JSON for the dashboard into data/analysis/.
"""
import json
from pathlib import Path

import duckdb

ROOT = Path(r"e:\pbl project")
DB = ROOT / "data" / "udise.duckdb"
OUT = ROOT / "data" / "analysis"
OUT.mkdir(parents=True, exist_ok=True)

con = duckdb.connect(str(DB), read_only=True)

YEARS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
YEAR_PAIRS = list(zip(YEARS, YEARS[1:]))
FIRST, LATEST = YEARS[0], YEARS[-1]
# the trustworthy transition pair for headline retention (see the 2021-22 caveat)
MAIN_PAIR = f"{YEARS[-2]} -> {YEARS[-1]}"

# Three districts were renamed mid-panel, so the raw strings do not join across
# it. School counts confirm each pairing (Aurangabad 4,490 -> Sambhajinagar
# 4,456; Osmanabad 1,805 -> Dharashiv 1,810; Ahmadnagar 5,270 -> Ahilyanagar in
# 2025-26). 36 districts once merged.
DISTRICT = """CASE trim(district)
    WHEN 'AURANGABAD (MAHARASHTRA)' THEN 'CHHATRAPATI SAMBHAJINAGAR'
    WHEN 'OSMANABAD' THEN 'DHARASHIV'
    WHEN 'AHMADNAGAR' THEN 'AHILYANAGAR'
    ELSE trim(district) END"""


def dump(name, df):
    path = OUT / f"{name}.json"
    df.to_json(path, orient="records", indent=1)
    print(f"  -> {path.name}  ({len(df)} rows)")
    return df


# ------------------------------------------------------------------ 1. index
# Indicators are equal-weighted and only counted when applicable to the school
# (a boys-only school is not marked down for having no girls' toilet).
# boundary_wall / building_status are type-codes whose UDISE labels are not in
# the supplied schema PDF, so they are deliberately left out of the index.
# furniture_availability is excluded too: 2021-22 reports it as a COUNT of
# furniture sets (0..18,777) while 2022-23 onward report a 1/2/3 code, so no
# single test is comparable across the panel.
INDICATOR_SQL = f"""
    CREATE OR REPLACE TEMP TABLE ind AS
    SELECT year, pseudocode, {DISTRICT} AS district,
           location, management_group, category_label,
           stage, enr_total, enr_girls, total_tch,
           -- (applicable, met)
           1                                        AS a_water,
           (drinking_water_func_yn = 1)::INT        AS m_water,
           (school_type <> 1)::INT                  AS a_gtoilet,
           (school_type <> 1 AND total_girls_func_toilet >= 1)::INT AS m_gtoilet,
           (school_type <> 2)::INT                  AS a_btoilet,
           (school_type <> 2 AND total_boys_func_toilet >= 1)::INT  AS m_btoilet,
           1 AS a_elec,     (electricity_availability = 1)::INT AS m_elec,
           1 AS a_lib,      (library_availability = 1)::INT     AS m_lib,
           1 AS a_play,     (playground_available = 1)::INT     AS m_play,
           1 AS a_ramp,     (availability_ramps = 1)::INT       AS m_ramp,
           1 AS a_hwash,    (handwash_near_toilet = 1)::INT     AS m_hwash,
           1 AS a_comp,     (coalesce(desktop,0)+coalesce(laptop,0)+coalesce(tablet,0) >= 1)::INT AS m_comp,
           1 AS a_net,      (internet = 1)::INT                 AS m_net,
           1 AS a_med,      (medical_checkups = 1)::INT         AS m_med
    FROM school_year
"""
con.execute(INDICATOR_SQL)

IND = ["water", "gtoilet", "btoilet", "elec", "lib", "play", "ramp",
       "hwash", "comp", "net", "med"]
MET = " + ".join(f"m_{i}" for i in IND)
APP = " + ".join(f"a_{i}" for i in IND)

con.execute(f"""
    CREATE OR REPLACE TEMP TABLE idx AS
    SELECT *, ({MET}) AS met, ({APP}) AS applicable,
           round(100.0 * ({MET}) / nullif(({APP}), 0), 2) AS infra_score
    FROM ind
""")

print(f"\n=== indicator coverage, % of schools meeting each ({LATEST}) ===")
cov = con.execute(f"""
    SELECT {', '.join(f"round(100.0*sum(m_{i})/sum(a_{i}),1) AS {i}" for i in IND)}
    FROM idx WHERE year='{LATEST}'""").fetchdf()
for c in cov.columns:
    print(f"   {c:<9} {cov[c][0]:>6}%")

print("\n=== infrastructure score by year ===")
dump("score_by_year", con.execute("""
    SELECT year, round(avg(infra_score),2) AS score,
           round(median(infra_score),2) AS median_score, count(*) AS schools
    FROM idx GROUP BY 1 ORDER BY 1""").fetchdf()).to_string(index=False)

print(f"\n=== score by location x management ({LATEST}) ===")
d = dump("score_by_segment", con.execute(f"""
    SELECT year, location, management_group,
           round(avg(infra_score),2) AS score, count(*) AS schools,
           sum(enr_total) AS students
    FROM idx WHERE location IS NOT NULL AND management_group IS NOT NULL
    GROUP BY 1,2,3 ORDER BY 1,2,3""").fetchdf())
print(d[d.year == LATEST].to_string(index=False))

print(f"\n=== district scores ({LATEST}, worst 10 and best 5) ===")
dist = dump("score_by_district", con.execute(f"""
    SELECT year, district,
           round(avg(infra_score),2) AS score, count(*) AS schools,
           sum(enr_total) AS students,
           round(100.0*sum(m_net)/sum(a_net),1)         AS pct_internet,
           round(100.0*sum(m_comp)/sum(a_comp),1)       AS pct_computer,
           round(100.0*sum(m_gtoilet)/nullif(sum(a_gtoilet),0),1) AS pct_girls_toilet,
           round(100.0*sum(m_water)/sum(a_water),1)     AS pct_water,
           round(100.0*sum(m_elec)/sum(a_elec),1)       AS pct_electricity
    FROM idx GROUP BY 1,2 ORDER BY 1,3""").fetchdf())
cur = dist[dist.year == LATEST].sort_values("score")
print(cur.head(10).to_string(index=False))
print("   ...")
print(cur.tail(5).to_string(index=False))

# 3-year movement per district
print(f"\n=== biggest district movers, {FIRST} -> {LATEST} ===")
mv = dump("district_change", con.execute(f"""
    SELECT district,
           round(max(CASE WHEN year='{FIRST}' THEN score END),2) AS score_2021,
           round(max(CASE WHEN year='{LATEST}' THEN score END),2) AS score_2023,
           round(max(CASE WHEN year='{LATEST}' THEN score END)
               - max(CASE WHEN year='{FIRST}' THEN score END),2) AS change
    FROM (SELECT year, district, avg(infra_score) AS score FROM idx GROUP BY 1,2)
    GROUP BY 1 ORDER BY change DESC""").fetchdf())
print(mv.head(5).to_string(index=False))
print("   ...")
print(mv.tail(5).to_string(index=False))


# --------------------------------------------------------------- 2. cohorts
# Grade pyramid: total enrolment per class per year.
print("\n=== enrolment by class and year (state totals) ===")
pyr = dump("grade_pyramid", con.execute("""
    SELECT year, class_num,
           sum(boys) AS boys, sum(girls) AS girls, sum(total) AS total,
           count(*) AS schools_offering
    FROM enrol_class GROUP BY 1,2 ORDER BY 1,2""").fetchdf())
print(pyr[pyr.year == LATEST].to_string(index=False))

# State-level cohort transition: class c in year Y -> class c+1 in year Y+1.
trans_sql = "\nUNION ALL".join(f"""
    SELECT '{y0} -> {y1}' AS period, a.class_num AS from_class,
           a.boys AS boys0, a.girls AS girls0, a.total AS total0,
           b.boys AS boys1, b.girls AS girls1, b.total AS total1
    FROM (SELECT class_num, sum(boys) boys, sum(girls) girls, sum(total) total
          FROM enrol_class WHERE year='{y0}' AND class_num >= 1 GROUP BY 1) a
    JOIN (SELECT class_num, sum(boys) boys, sum(girls) girls, sum(total) total
          FROM enrol_class WHERE year='{y1}' AND class_num >= 1 GROUP BY 1) b
      ON b.class_num = a.class_num + 1""" for y0, y1 in YEAR_PAIRS)

print("\n=== state cohort transition rates (%) ===")
tr = dump("transitions_state", con.execute(f"""
    SELECT period, from_class, from_class + 1 AS to_class,
           total0, total1,
           round(100.0*total1/nullif(total0,0),1) AS retention,
           round(100.0*boys1 /nullif(boys0,0),1)  AS retention_boys,
           round(100.0*girls1/nullif(girls0,0),1) AS retention_girls,
           round(100.0*girls1/nullif(girls0,0) - 100.0*boys1/nullif(boys0,0),1) AS girl_gap
    FROM ({trans_sql}) ORDER BY period, from_class""").fetchdf())
print(tr.to_string(index=False))

# District-level transition for the two critical exits.
dtrans_sql = "\nUNION ALL".join(f"""
    SELECT '{y0} -> {y1}' AS period, a.district, a.class_num AS from_class,
           a.boys boys0, a.girls girls0, a.total total0,
           b.boys boys1, b.girls girls1, b.total total1
    FROM (SELECT {DISTRICT} AS district, e.class_num,
                 sum(e.boys) boys, sum(e.girls) girls, sum(e.total) total
          FROM enrol_class e JOIN school_year s USING (year, pseudocode)
          WHERE e.year='{y0}' AND e.class_num >= 1 GROUP BY 1,2) a
    JOIN (SELECT {DISTRICT} AS district, e.class_num,
                 sum(e.boys) boys, sum(e.girls) girls, sum(e.total) total
          FROM enrol_class e JOIN school_year s USING (year, pseudocode)
          WHERE e.year='{y1}' AND e.class_num >= 1 GROUP BY 1,2) b
      ON b.district = a.district AND b.class_num = a.class_num + 1"""
    for y0, y1 in YEAR_PAIRS)

dtr = dump("transitions_district", con.execute(f"""
    SELECT period, district, from_class, from_class+1 AS to_class, total0, total1,
           round(100.0*total1/nullif(total0,0),1) AS retention,
           round(100.0*boys1 /nullif(boys0,0),1)  AS retention_boys,
           round(100.0*girls1/nullif(girls0,0),1) AS retention_girls
    FROM ({dtrans_sql}) ORDER BY period, from_class, retention""").fetchdf())

print(f"\n=== worst districts on the class 10 -> 11 exit ({MAIN_PAIR}) ===")
w = dtr[(dtr.period == MAIN_PAIR) & (dtr.from_class == 10)].sort_values("retention")
print(w.head(8).to_string(index=False))

# --------------------------------------------- 3. do the two stories connect?
print("\n=== district infra score vs class 10->11 retention ===")
link = con.execute(f"""
    WITH s AS (SELECT district, avg(infra_score) AS score FROM idx WHERE year='{LATEST}' GROUP BY 1),
         r AS (
           SELECT a.district, 100.0*sum(b.total)/nullif(sum(a.total),0) AS retention
           FROM (SELECT {DISTRICT} AS district, e.class_num, sum(e.total) total
                 FROM enrol_class e JOIN school_year s USING (year, pseudocode)
                 WHERE e.year='{YEARS[-2]}' AND e.class_num=10 GROUP BY 1,2) a
           JOIN (SELECT {DISTRICT} AS district, e.class_num, sum(e.total) total
                 FROM enrol_class e JOIN school_year s USING (year, pseudocode)
                 WHERE e.year='{LATEST}' AND e.class_num=11 GROUP BY 1,2) b
             ON b.district=a.district
           GROUP BY 1)
    SELECT round(corr(s.score, r.retention),3) AS pearson_r, count(*) AS districts
    FROM s JOIN r USING (district)""").fetchdf()
print(link.to_string(index=False))

dump("district_scatter", con.execute(f"""
    WITH s AS (SELECT district, avg(infra_score) AS score, sum(enr_total) students
               FROM idx WHERE year='{LATEST}' GROUP BY 1),
         r AS (
           SELECT a.district, 100.0*sum(b.total)/nullif(sum(a.total),0) AS retention
           FROM (SELECT {DISTRICT} AS district, sum(e.total) total FROM enrol_class e
                 JOIN school_year s USING (year, pseudocode)
                 WHERE e.year='{YEARS[-2]}' AND e.class_num=10 GROUP BY 1) a
           JOIN (SELECT {DISTRICT} AS district, sum(e.total) total FROM enrol_class e
                 JOIN school_year s USING (year, pseudocode)
                 WHERE e.year='{LATEST}' AND e.class_num=11 GROUP BY 1) b
             ON b.district=a.district GROUP BY 1)
    SELECT s.district, round(s.score,2) AS score, round(r.retention,1) AS retention,
           s.students
    FROM s JOIN r USING (district) ORDER BY score""").fetchdf())

# ------------------------------------------------------- 4. deprivation flags
print(f"\n=== schools failing basic norms ({LATEST}) ===")
gaps = dump("deprivation", con.execute(f"""
    SELECT 'No functional girls'' toilet' AS gap,
           count(*) FILTER (a_gtoilet=1 AND m_gtoilet=0) AS schools,
           sum(enr_girls) FILTER (a_gtoilet=1 AND m_gtoilet=0) AS girls_affected
    FROM idx WHERE year='{LATEST}'
    UNION ALL SELECT 'No functional drinking water',
           count(*) FILTER (m_water=0), sum(enr_total) FILTER (m_water=0)
    FROM idx WHERE year='{LATEST}'
    UNION ALL SELECT 'No electricity',
           count(*) FILTER (m_elec=0), sum(enr_total) FILTER (m_elec=0)
    FROM idx WHERE year='{LATEST}'
    UNION ALL SELECT 'No computing device',
           count(*) FILTER (m_comp=0), sum(enr_total) FILTER (m_comp=0)
    FROM idx WHERE year='{LATEST}'
    UNION ALL SELECT 'No internet',
           count(*) FILTER (m_net=0), sum(enr_total) FILTER (m_net=0)
    FROM idx WHERE year='{LATEST}'
    UNION ALL SELECT 'No library',
           count(*) FILTER (m_lib=0), sum(enr_total) FILTER (m_lib=0)
    FROM idx WHERE year='{LATEST}'
    UNION ALL SELECT 'No playground',
           count(*) FILTER (m_play=0), sum(enr_total) FILTER (m_play=0)
    FROM idx WHERE year='{LATEST}'
    ORDER BY schools DESC""").fetchdf())
print(gaps.to_string(index=False))

# PTR against the RTE 30:1 elementary norm
print(f"\n=== pupil-teacher ratio vs RTE norm (elementary schools, {LATEST}) ===")
ptr = dump("ptr", con.execute(f"""
    SELECT location, management_group,
           count(*) AS schools,
           round(sum(enr_total)*1.0/nullif(sum(total_tch),0),1) AS ptr,
           count(*) FILTER (total_tch > 0 AND enr_total*1.0/total_tch > 30) AS over_30,
           count(*) FILTER (total_tch = 1) AS single_teacher,
           count(*) FILTER (total_tch = 0 AND enr_total > 0) AS zero_teacher
    FROM idx WHERE year='{LATEST}' AND stage IN ('Primary','Elementary','Upper Primary')
      AND location IS NOT NULL AND management_group IS NOT NULL
    GROUP BY 1,2 ORDER BY ptr DESC""").fetchdf())
print(ptr.to_string(index=False))

# ------------------------------------------------- 5. school safety (2025-26)
# The safety table exists only in the final year, so this is a snapshot, not a
# trend. Coded 1 = Yes, 2 = No, 9 = Not applicable; the denominator below is
# schools answering yes or no, so "not applicable" never counts as a failure.
SAFETY = [
    ("cctv_cam_yn", "CCTV cameras installed"),
    ("fire_ext_yn", "Fire extinguishers"),
    ("sdmp_plan_yn", "Disaster management plan"),
    ("struct_safaud_yn", "Structural safety audit done"),
    ("nonstr_safaud_yn", "Non-structural safety audit done"),
    ("nodal_tch_yn", "Nodal teacher for safety"),
    ("safty_trng_yn", "Regular safety training"),
    ("tch_first_level_counsellor", "Teacher trained as first-level counsellor"),
    ("slfdef_grt_yn", "Self-defence training for girls"),
    ("guide_display_yn", "Helpline / guidance displayed"),
    ("tch_icard_yn", "Teacher ID cards issued"),
    ("sch_eco_club_yn", "Eco club"),
]
print(f"\n=== school safety, {LATEST} (new table this year) ===")
parts = []
for col, label in SAFETY:
    parts.append(f"""
        SELECT '{label}' AS measure,
               count(*) FILTER ({col} = 1) AS yes,
               count(*) FILTER ({col} = 2) AS no,
               count(*) FILTER ({col} NOT IN (1,2)) AS na,
               round(100.0*count(*) FILTER ({col} = 1)
                     / nullif(count(*) FILTER ({col} IN (1,2)), 0), 1) AS pct
        FROM safety WHERE year = '{LATEST}'""")
saf = dump("safety", con.execute("\nUNION ALL".join(parts) + " ORDER BY pct DESC").fetchdf())
print(saf.to_string(index=False))

print("\n=== safety by location and management ===")
safseg = dump("safety_segment", con.execute(f"""
    SELECT s.location, s.management_group,
           count(*) AS schools,
           round(100.0*count(*) FILTER (f.cctv_cam_yn = 1)/count(*), 1) AS pct_cctv,
           round(100.0*count(*) FILTER (f.fire_ext_yn = 1)/count(*), 1) AS pct_fire,
           round(100.0*count(*) FILTER (f.tch_first_level_counsellor = 1)/count(*), 1) AS pct_counsellor,
           round(100.0*count(*) FILTER (f.slfdef_grt_yn = 1)/count(*), 1) AS pct_selfdef
    FROM safety f JOIN school_year s USING (year, pseudocode)
    WHERE f.year = '{LATEST}' AND s.location IS NOT NULL
      AND s.management_group IN ('Government','Private Aided','Private Unaided')
    GROUP BY 1,2 ORDER BY pct_cctv""").fetchdf())
print(safseg.to_string(index=False))

con.close()
print("\ndone.")
