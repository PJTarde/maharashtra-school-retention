"""Build the harmonised UDISE panel database for Maharashtra (2021-22 .. 2023-24).

The panel spans five years and three different UDISE+ release schemas.

2021-22 differs from the 2022-23 .. 2024-25 middle block:
  * key column is misspelt `psuedocode`
  * enrolment is keyed by text `item_desc`, not (`item_group`, `item_id`)
  * enrolment is stored DENSE (every school x every category, mostly zeros);
    later years store only non-zero rows
  * facilities carry one `drinking_water_available` flag instead of six
    per-source flags, and lack the lab-condition / CWSN-toilet columns
  * teachers lack the caste breakdown

2024-25 is a drop-in match for the middle block.

2025-26 changes again, additively plus one breaking change:
  * enrolment splits transgender pupils into their own `*_t` column per class.
    Earlier years documented `*_b` as "Boys +Transgenders", so `*_t` is folded
    back into boys here to keep the series continuous (statewide this is 1-2
    pupils, so it changes nothing materially).
  * facilities gain 12 columns, profile gains 11 -- all additive, and ignored
    here because every SELECT names its columns explicitly
  * a new `safety` table appears (CCTV, fire safety, audits, counsellors),
    which exists for 2025-26 only

This script harmonises all five years onto a common core.

Coding convention throughout UDISE+: 1 = Yes, 2 = No, 9 = Not applicable.

Outputs data/udise.duckdb with:
  school_year   one row per school per year (profile + facility + teacher + totals)
  enrol_class   school x year x class x gender enrolment
  enrol_social  school x year x social category enrolment
"""
from pathlib import Path

import duckdb

ROOT = Path(r"e:\pbl project")
RAW = ROOT / "data" / "raw"
DB = ROOT / "data" / "udise.duckdb"

YEARS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
OLD = "2021-22"          # the odd-schema first year
TRANS_YEARS = {"2025-26"}  # years that split transgender into its own column
SAFETY_YEARS = ["2025-26"]

CLASSES = ["cpp"] + [f"c{i}" for i in range(1, 13)]
CLASS_NUM = {"cpp": 0, **{f"c{i}": i for i in range(1, 13)}}


def src(year: str, table: str) -> str:
    p = (RAW / year / f"{table}.csv").as_posix()
    return f"read_csv('{p}', header=true, all_varchar=true, ignore_errors=false)"


def key(year: str) -> str:
    """The school-id column, misspelt in 2021-22."""
    return "psuedocode" if year == OLD else "pseudocode"


# ---------------------------------------------------------------- enrolment
def enrol_filter(year: str) -> str:
    """Rows covering every student exactly once: the four social categories."""
    if year == OLD:
        return "item_desc IN ('General','SC','ST','OBC')"
    return "TRY_CAST(item_group AS INT) = 1 AND TRY_CAST(item_id AS INT) IN (1,2,3,4)"


def social_label(year: str) -> str:
    if year == OLD:
        return "item_desc"
    return """CASE TRY_CAST(item_id AS INT)
                WHEN 1 THEN 'General' WHEN 2 THEN 'SC'
                WHEN 3 THEN 'ST' WHEN 4 THEN 'OBC' END"""


def enrol_sums(year: str) -> str:
    """Per-class boy/girl sums. 2025-26 splits transgender out of `_b`; fold it back."""
    has_t = year in TRANS_YEARS
    parts = []
    for c in CLASSES:
        if has_t:
            parts.append(f"sum(TRY_CAST({c}_b AS INT) "
                         f"+ coalesce(TRY_CAST({c}_t AS INT), 0)) AS {c}_b")
        else:
            parts.append(f"sum(TRY_CAST({c}_b AS INT)) AS {c}_b")
        parts.append(f"sum(TRY_CAST({c}_g AS INT)) AS {c}_g")
    return ",\n               ".join(parts)


def build_enrolment(con: duckdb.DuckDBPyConnection) -> None:
    parts = []
    for y in YEARS:
        parts.append(f"""
        SELECT '{y}' AS year,
               TRY_CAST({key(y)} AS BIGINT) AS pseudocode,
               {social_label(y)} AS social_category,
               {enrol_sums(y)}
        FROM {src(y, 'enr1')}
        WHERE {enrol_filter(y)}
        GROUP BY 1, 2, 3""")
    con.execute("CREATE OR REPLACE TABLE enrol_social_wide AS " + "\nUNION ALL".join(parts))

    # long: one row per school-year-class-social category
    longs = []
    for c in CLASSES:
        longs.append(f"""
        SELECT year, pseudocode, social_category,
               {CLASS_NUM[c]} AS class_num, '{c}' AS class_code,
               coalesce({c}_b, 0) AS boys, coalesce({c}_g, 0) AS girls
        FROM enrol_social_wide""")
    con.execute("CREATE OR REPLACE TABLE enrol_detail AS " + "\nUNION ALL".join(longs))

    con.execute("""
        CREATE OR REPLACE TABLE enrol_class AS
        SELECT year, pseudocode, class_num, any_value(class_code) AS class_code,
               sum(boys) AS boys, sum(girls) AS girls, sum(boys) + sum(girls) AS total
        FROM enrol_detail
        GROUP BY 1, 2, 3
        HAVING sum(boys) + sum(girls) > 0
    """)

    con.execute("""
        CREATE OR REPLACE TABLE enrol_social AS
        SELECT year, pseudocode, social_category,
               sum(boys) AS boys, sum(girls) AS girls, sum(boys) + sum(girls) AS total
        FROM enrol_detail
        GROUP BY 1, 2, 3
        HAVING sum(boys) + sum(girls) > 0
    """)
    con.execute("DROP TABLE enrol_detail")


# ------------------------------------------------------------------ profile
def profile_select(y: str) -> str:
    k = key(y)
    if y == OLD:
        block = "NULL::VARCHAR AS block"
        # 2021-22 splits these by stage; collapse to one school-level value
        instr = "greatest(TRY_CAST(instr_days_pr AS INT), TRY_CAST(instr_days_up AS INT), " \
                "TRY_CAST(instr_days_sec AS INT), TRY_CAST(instr_days_hsec AS INT)) AS avg_instr_days"
        cce = "CASE WHEN 1 IN (TRY_CAST(cce_pr AS INT), TRY_CAST(cce_up AS INT), " \
              "TRY_CAST(cce_sec AS INT), TRY_CAST(cce_hsec AS INT)) THEN 1 ELSE 2 END AS cce_yn"
        angan = "TRY_CAST(anganwadi_premises AS INT) AS anganwadi_yn"
        estab = "TRY_CAST(year_of_establishment AS INT) AS year_of_establishment"
    else:
        block = "block"
        instr = "TRY_CAST(avg_instr_days AS INT) AS avg_instr_days"
        cce = "TRY_CAST(cce_yn AS INT) AS cce_yn"
        angan = "TRY_CAST(anganwadi_yn AS INT) AS anganwadi_yn"
        # only 2025-26 brings the founding year back, as `estd_year`
        estab = ("TRY_CAST(estd_year AS INT) AS year_of_establishment"
                 if y == "2025-26" else "NULL::INT AS year_of_establishment")
    return f"""
        SELECT '{y}' AS year,
               TRY_CAST({k} AS BIGINT) AS pseudocode,
               trim(district) AS district, {block},
               TRY_CAST(rural_urban AS INT) AS rural_urban,
               TRY_CAST(school_category AS INT) AS school_category,
               TRY_CAST(school_type AS INT) AS school_type,
               TRY_CAST(lowclass AS INT) AS lowclass,
               TRY_CAST(highclass AS INT) AS highclass,
               TRY_CAST(managment AS INT) AS management,
               TRY_CAST(medium_instr1 AS INT) AS medium1,
               TRY_CAST(minority_school AS INT) AS minority_school,
               TRY_CAST(shift_school AS INT) AS shift_school,
               TRY_CAST(resi_school AS INT) AS resi_school,
               TRY_CAST(approachable_road AS INT) AS approachable_road,
               TRY_CAST(pre_primary AS INT) AS pre_primary,
               {angan}, {instr}, {cce}, {estab}
        FROM {src(y, 'prof1')}"""


# ----------------------------------------------------------------- facility
FAC_COMMON = [
    "building_status", "no_building_blocks", "pucca_building_blocks", "boundary_wall",
    "total_class_rooms", "other_rooms", "classrooms_in_good_condition",
    "classrooms_needs_minor_repair", "classrooms_needs_major_repair", "separate_room_for_hm",
    "total_boys_toilet", "total_boys_func_toilet", "total_girls_toilet", "total_girls_func_toilet",
    "func_boys_cwsn_friendly", "func_girls_cwsn_friendly", "urinal_boys",
    "handwash_near_toilet", "rain_water_harvesting", "handwash_facility_for_meal",
    "electricity_availability", "solar_panel", "library_availability", "playground_available",
    "medical_checkups", "availability_ramps", "availability_of_handrails",
    "furniture_availability", "laptop", "tablet", "desktop", "digiboard",
    "projector", "printer", "internet", "dth",
]

WATER_SRC = ["hand_pump", "well_prot", "tap", "othsrc", "well_unprot", "pack_water"]


def facility_select(y: str) -> str:
    k = key(y)
    cols = ",\n               ".join(f"TRY_CAST({c} AS INT) AS {c}" for c in FAC_COMMON)
    if y == OLD:
        girls_urinal = "TRY_CAST(urinla_girls AS INT) AS urinal_girls"  # source typo
        water = "TRY_CAST(drinking_water_available AS INT) AS drinking_water_yn"
        water_fn = "TRY_CAST(drinking_water_functional AS INT) AS drinking_water_func_yn"
        # 2021-22 only reports these as NULL-equivalents
        extra = """NULL::INT AS total_boys_cwsn_toilet, NULL::INT AS total_girls_cwsn_toilet,
               NULL::INT AS book_bank, NULL::INT AS reading_corner,
               NULL::INT AS spl_educator_yn, NULL::INT AS smart_class_tv_tot,
               NULL::INT AS comp_ict_lab_yn"""
    else:
        girls_urinal = "TRY_CAST(urinal_girls AS INT) AS urinal_girls"
        any_yes = " OR ".join(f"TRY_CAST({s}_yn AS INT) = 1" for s in WATER_SRC)
        any_fn = " OR ".join(f"TRY_CAST({s}_fun_yn AS INT) = 1" for s in WATER_SRC)
        water = f"CASE WHEN {any_yes} THEN 1 ELSE 2 END AS drinking_water_yn"
        water_fn = f"CASE WHEN {any_fn} THEN 1 ELSE 2 END AS drinking_water_func_yn"
        extra = """TRY_CAST(total_boys_cwsn_toilet AS INT) AS total_boys_cwsn_toilet,
               TRY_CAST(total_girls_cwsn_toilet AS INT) AS total_girls_cwsn_toilet,
               TRY_CAST(book_bank AS INT) AS book_bank,
               TRY_CAST(reading_corner AS INT) AS reading_corner,
               TRY_CAST(spl_educator_yn AS INT) AS spl_educator_yn,
               TRY_CAST(smart_class_tv_tot AS INT) AS smart_class_tv_tot,
               TRY_CAST(comp_ict_lab_yn AS INT) AS comp_ict_lab_yn"""
    return f"""
        SELECT '{y}' AS year, TRY_CAST({k} AS BIGINT) AS pseudocode,
               {cols},
               {girls_urinal}, {water}, {water_fn},
               {extra}
        FROM {src(y, 'fac')}"""


# ------------------------------------------------------------------ teacher
TCH_COMMON = [
    "male", "female", "transgender", "regular", "contract", "part_time",
    "below_graduate", "graduate", "post_graduate_and_above",
    "class_taught_pr", "class_taught_upr", "class_taught_pr_upr",
    "class_taught_sec_only", "class_taught_hsec_only", "class_taught_upr_sec",
    "class_taught_sec_hsec", "class_taugt_pre_primary_only", "class_taught_pr_and_pre_pri",
    "diploma_certificate", "bachelor_of_ee", "bed_equivalent", "med_equivalent",
    "none", "diploma_special_edu",
]


def teacher_select(y: str) -> str:
    k = key(y)
    cols = ",\n               ".join(f"TRY_CAST({c} AS INT) AS {c}" for c in TCH_COMMON)
    if y == OLD:
        total = "TRY_CAST(total_teacher AS INT) AS total_tch"
        trained = "TRY_CAST(total_teacher_trained_computer AS INT) AS trained_comp"
        caste = ("NULL::INT AS gen_tch, NULL::INT AS sc_tch, "
                 "NULL::INT AS st_tch, NULL::INT AS obc_tch")
        extra = "NULL::INT AS trained_cwsn"
    else:
        total = "TRY_CAST(total_tch AS INT) AS total_tch"
        trained = "TRY_CAST(trained_comp AS INT) AS trained_comp"
        caste = ("TRY_CAST(gen_tch AS INT) AS gen_tch, TRY_CAST(sc_tch AS INT) AS sc_tch, "
                 "TRY_CAST(st_tch AS INT) AS st_tch, TRY_CAST(obc_tch AS INT) AS obc_tch")
        extra = "TRY_CAST(trained_cwsn AS INT) AS trained_cwsn"
    return f"""
        SELECT '{y}' AS year, TRY_CAST({k} AS BIGINT) AS pseudocode,
               {total}, {cols}, {trained}, {caste}, {extra}
        FROM {src(y, 'tch')}"""


# ------------------------------------------------------------------- safety
# New in 2025-26. Coded 1 = Yes, 2 = No, 9 = Not applicable, as elsewhere.
SAFETY_COLS = [
    "sdmp_plan_yn", "struct_safaud_yn", "nonstr_safaud_yn", "cctv_cam_yn",
    "fire_ext_yn", "nodal_tch_yn", "safty_trng_yn", "dismgmt_taug_yn",
    "slfdef_grt_yn", "slfdef_trained", "guide_display_yn",
    "tch_first_level_counsellor", "safe_sec_audit", "teacher_displaying_photo",
    "vidya_pravesh", "stu_atndnc_yn", "tch_atndnc_yn", "sch_youth_club_yn",
    "sch_eco_club_yn", "tch_icard_yn", "self_cert_obtained_yn",
]


def safety_select(y: str) -> str:
    cols = ",\n               ".join(f"TRY_CAST({c} AS INT) AS {c}" for c in SAFETY_COLS)
    return f"""
        SELECT '{y}' AS year, TRY_CAST(pseudocode AS BIGINT) AS pseudocode,
               {cols}
        FROM {src(y, 'safety')}"""


# ---------------------------------------------------------------- lookups
LOOKUPS = {
    "lk_management": [
        (1, "Dept. of Education", "Government"),
        (2, "Tribal / Social Welfare Dept.", "Government"),
        (3, "Local body (Zilla Parishad / Municipal)", "Government"),
        (4, "Private Aided", "Private Aided"),
        (5, "Private Unaided (Recognised)", "Private Unaided"),
        (6, "Other", "Other"),
        # NOT Central Government. Empirically: of the 3,402 schools carrying code 7
        # in 2025-26, 2,359 were Private Aided and 962 Private Unaided in 2024-25,
        # and only 77 already held code 7. It is a private-sector residual category
        # that absorbed a reclassification in 2025-26, so it gets its own group and
        # never contaminates the Government bucket.
        (7, "Private / other management", "Private Other"),
        (8, "Other / Unrecognised", "Other"),
        (90, "Central Govt. school", "Government"),
        (92, "Jawahar Navodaya Vidyalaya", "Government"),
        (93, "Sainik School", "Government"),
        (94, "Railway School", "Government"),
        (95, "Central Govt. (other)", "Government"),
        (97, "Central Govt. (other)", "Government"),
        (98, "Other", "Other"),
        (101, "Other", "Other"),
    ],
    "lk_school_category": [
        (1, "Primary (1-5)", "Primary"),
        (2, "Primary + Upper Primary (1-8)", "Elementary"),
        (3, "Primary to Higher Sec. (1-12)", "Composite"),
        (4, "Upper Primary only (6-8)", "Upper Primary"),
        (5, "Upper Primary to Higher Sec. (6-12)", "Composite"),
        (6, "Primary to Secondary (1-10)", "Composite"),
        (7, "Upper Primary + Secondary (6-10)", "Upper Primary"),
        (8, "Secondary only (9-10)", "Secondary"),
        (10, "Secondary + Higher Sec. (9-12)", "Secondary"),
        (11, "Higher Secondary only (11-12)", "Higher Secondary"),
        (12, "Pre-primary only", "Pre-primary"),  # new in 2025-26, 5 schools
    ],
    "lk_medium": [
        (2, "Bengali"), (3, "Gujarati"), (4, "Hindi"), (5, "Kannada"),
        (10, "Marathi"), (15, "Sindhi"), (16, "Tamil"), (17, "Telugu"),
        (18, "Urdu"), (19, "English"),
    ],
}


def build_lookups(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE OR REPLACE TABLE lk_management(code INT, label VARCHAR, grp VARCHAR)")
    con.executemany("INSERT INTO lk_management VALUES (?,?,?)", LOOKUPS["lk_management"])
    con.execute("CREATE OR REPLACE TABLE lk_school_category(code INT, label VARCHAR, stage VARCHAR)")
    con.executemany("INSERT INTO lk_school_category VALUES (?,?,?)", LOOKUPS["lk_school_category"])
    con.execute("CREATE OR REPLACE TABLE lk_medium(code INT, label VARCHAR)")
    con.executemany("INSERT INTO lk_medium VALUES (?,?)", LOOKUPS["lk_medium"])


# --------------------------------------------------------------------- main
def main() -> None:
    DB.parent.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()
    con = duckdb.connect(str(DB))

    print("building lookups ...")
    build_lookups(con)

    print("building enrolment tables ...")
    build_enrolment(con)

    print("building safety (2025-26 only) ...")
    con.execute("CREATE OR REPLACE TABLE safety AS "
                + "\nUNION ALL".join(safety_select(y) for y in SAFETY_YEARS))

    print("building profile / facility / teacher ...")
    con.execute("CREATE OR REPLACE TABLE prof AS "
                + "\nUNION ALL".join(profile_select(y) for y in YEARS))
    con.execute("CREATE OR REPLACE TABLE fac AS "
                + "\nUNION ALL".join(facility_select(y) for y in YEARS))
    con.execute("CREATE OR REPLACE TABLE tch AS "
                + "\nUNION ALL".join(teacher_select(y) for y in YEARS))

    print("assembling school_year ...")
    con.execute("""
        CREATE OR REPLACE TABLE school_year AS
        SELECT p.*,
               m.label AS management_label, m.grp AS management_group,
               sc.label AS category_label, sc.stage AS stage,
               md.label AS medium_label,
               CASE p.rural_urban WHEN 1 THEN 'Rural' WHEN 2 THEN 'Urban' END AS location,
               f.* EXCLUDE (year, pseudocode),
               t.* EXCLUDE (year, pseudocode),
               coalesce(e.enr_total, 0)   AS enr_total,
               coalesce(e.enr_boys, 0)    AS enr_boys,
               coalesce(e.enr_girls, 0)   AS enr_girls,
               coalesce(e.enr_elem, 0)    AS enr_elementary,
               coalesce(e.enr_sec, 0)     AS enr_secondary
        FROM prof p
        LEFT JOIN fac f  USING (year, pseudocode)
        LEFT JOIN tch t  USING (year, pseudocode)
        LEFT JOIN (
            SELECT year, pseudocode,
                   sum(total) AS enr_total, sum(boys) AS enr_boys, sum(girls) AS enr_girls,
                   sum(total) FILTER (class_num BETWEEN 1 AND 8)  AS enr_elem,
                   sum(total) FILTER (class_num BETWEEN 9 AND 12) AS enr_sec
            FROM enrol_class GROUP BY 1, 2
        ) e USING (year, pseudocode)
        LEFT JOIN lk_management     m  ON m.code  = p.management
        LEFT JOIN lk_school_category sc ON sc.code = p.school_category
        LEFT JOIN lk_medium         md ON md.code = p.medium1
    """)

    con.execute("DROP TABLE enrol_social_wide")

    # ---- validation
    print("\n--- validation ---")
    for t in ["school_year", "enrol_class", "enrol_social", "safety"]:
        n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {n:,} rows")

    print("\n  schools & enrolment per year:")
    for r in con.execute("""
        SELECT year, count(*) schools, sum(enr_total) students,
               sum(total_tch) teachers,
               round(sum(enr_total)*1.0/nullif(sum(total_tch),0), 1) ptr,
               count(*) FILTER (enr_total = 0) zero_enr
        FROM school_year GROUP BY 1 ORDER BY 1""").fetchall():
        print(f"    {r[0]}  schools={r[1]:,}  students={r[2]:,}  teachers={r[3]:,}  "
              f"PTR={r[4]}  zero-enrolment schools={r[5]:,}")

    print(f"\n  school_category vs lowclass/highclass consistency ({YEARS[-1]}):")
    for r in con.execute(f"""
        SELECT category_label, mode(lowclass) lo, mode(highclass) hi, count(*) n
        FROM school_year WHERE year='{YEARS[-1]}'
        GROUP BY 1 ORDER BY n DESC""").fetchall():
        label = r[0] if r[0] is not None else "<UNMAPPED>"
        print(f"    {label:<38} low={str(r[1]):<4} high={str(r[2]):<4} n={r[3]:,}")

    print("\n  unmapped codes:")
    for col, lk in [("management", "management_label"), ("school_category", "category_label")]:
        rows = con.execute(f"""
            SELECT {col}, count(*) FROM school_year
            WHERE {lk} IS NULL AND {col} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC""").fetchall()
        print(f"    {col}: {rows if rows else 'none'}")

    con.close()
    print(f"\nwrote {DB}  ({DB.stat().st_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()
