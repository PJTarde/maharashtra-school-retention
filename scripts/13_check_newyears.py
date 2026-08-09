"""Check that the 2024-25 / 2025-26 files extend the panel: id stability, districts, codes."""
from pathlib import Path

import duckdb

RAW = Path(r"e:\pbl project\data\raw")
YEARS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
con = duckdb.connect()


def csv(y, t):
    return f"read_csv('{(RAW / y / (t + '.csv')).as_posix()}', header=true, all_varchar=true)"


def key(y):
    return "psuedocode" if y == "2021-22" else "pseudocode"


print("=== schools per year and carry-over from the previous year ===")
prev = None
for y in YEARS:
    con.execute(f"CREATE OR REPLACE TEMP TABLE cur AS "
                f"SELECT DISTINCT TRY_CAST({key(y)} AS BIGINT) AS pc FROM {csv(y,'prof1')}")
    n = con.execute("SELECT count(*) FROM cur").fetchone()[0]
    if prev is None:
        print(f"  {y}: {n:,} schools")
    else:
        ov = con.execute("SELECT count(*) FROM cur JOIN prv USING (pc)").fetchone()[0]
        print(f"  {y}: {n:,} schools · {ov:,} also present in {prev} ({100*ov/n:.1f}%)")
    con.execute("CREATE OR REPLACE TEMP TABLE prv AS SELECT * FROM cur")
    prev = y

print("\n=== districts present per year (looking for further renames) ===")
sets = {}
for y in YEARS:
    sets[y] = {r[0] for r in con.execute(
        f"SELECT DISTINCT trim(district) FROM {csv(y,'prof1')}").fetchall()}
    print(f"  {y}: {len(sets[y])} districts")
base = sets["2023-24"]
for y in ["2024-25", "2025-26"]:
    print(f"  only in {y}: {sorted(sets[y] - base)}")
    print(f"  missing from {y}: {sorted(base - sets[y])}")

print("\n=== 2025-26 transgender columns: are they populated? ===")
print(con.execute(f"""
    SELECT sum(TRY_CAST(c1_t AS INT)) c1_t, sum(TRY_CAST(c5_t AS INT)) c5_t,
           sum(TRY_CAST(c10_t AS INT)) c10_t,
           sum(TRY_CAST(c1_b AS INT)) c1_b, sum(TRY_CAST(c1_g AS INT)) c1_g
    FROM {csv('2025-26','enr1')}
    WHERE TRY_CAST(item_group AS INT)=1 AND TRY_CAST(item_id AS INT) IN (1,2,3,4)
""").fetchdf().to_string(index=False))

print("\n=== enrolment item groups, new years ===")
for y in ["2024-25", "2025-26"]:
    rows = con.execute(f"""SELECT item_group, count(*) FROM {csv(y,'enr1')}
                           GROUP BY 1 ORDER BY 1""").fetchall()
    print(f"  {y} enr1 groups: {rows}")

print("\n=== 2025-26 safety table: value distributions ===")
for c in ["cctv_cam_yn", "fire_ext_yn", "slfdef_grt_yn", "nodal_tch_yn",
          "tch_first_level_counsellor", "struct_safaud_yn", "sdmp_plan_yn"]:
    rows = con.execute(f"""SELECT {c}, count(*) n FROM {csv('2025-26','safety')}
                           GROUP BY 1 ORDER BY n DESC LIMIT 5""").fetchall()
    print(f"  {c}: {rows}")

print("\n=== do safety rows match prof1 schools? ===")
print(con.execute(f"""
    SELECT (SELECT count(*) FROM {csv('2025-26','safety')}) AS safety_rows,
           (SELECT count(*) FROM {csv('2025-26','prof1')}) AS prof_rows""").fetchdf().to_string(index=False))
