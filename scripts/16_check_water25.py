"""Is 'functional drinking water = 100%' in 2025-26 real, or a coding change?"""
from pathlib import Path

import duckdb

RAW = Path(r"e:\pbl project\data\raw")
con = duckdb.connect(r"e:\pbl project\data\udise.duckdb", read_only=True)

SRC = ["hand_pump", "well_prot", "tap", "othsrc", "well_unprot", "pack_water"]
YEARS = ["2022-23", "2023-24", "2024-25", "2025-26"]


def csv(y):
    return f"read_csv('{(RAW / y / 'fac.csv').as_posix()}', header=true, all_varchar=true)"


print("=== raw *_fun_yn value counts, tap and hand_pump ===")
for s in ["tap", "hand_pump"]:
    print(f"\n  {s}_fun_yn")
    for y in YEARS:
        rows = con.execute(f"""SELECT {s}_fun_yn v, count(*) n FROM {csv(y)}
                               GROUP BY 1 ORDER BY n DESC""").fetchall()
        print(f"    {y}: " + ", ".join(f"{r[0]}={r[1]:,}" for r in rows))

print("\n=== schools reporting ANY functional source (the flag's definition) ===")
anyfn = " OR ".join(f"TRY_CAST({s}_fun_yn AS INT) = 1" for s in SRC)
for y in YEARS:
    r = con.execute(f"""SELECT count(*) tot, count(*) FILTER ({anyfn}) anyf FROM {csv(y)}""").fetchone()
    print(f"  {y}: {r[1]:,} of {r[0]:,} ({100*r[1]/r[0]:.1f}%) have a functional source")

print("\n=== and ANY source at all (availability, not functionality) ===")
anyav = " OR ".join(f"TRY_CAST({s}_yn AS INT) = 1" for s in SRC)
for y in YEARS:
    r = con.execute(f"""SELECT count(*) tot, count(*) FILTER ({anyav}) anya FROM {csv(y)}""").fetchone()
    print(f"  {y}: {r[1]:,} of {r[0]:,} ({100*r[1]/r[0]:.1f}%)")

print("\n=== teacher counts: zero-teacher schools by year ===")
for r in con.execute("""
    SELECT year, count(*) FILTER (total_tch = 0) zero_tch,
           count(*) FILTER (total_tch = 0 AND enr_total > 0) zero_with_pupils,
           count(*) FILTER (total_tch = 1) single_tch, sum(total_tch) total
    FROM school_year GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"  {r[0]}  zero={r[1]:>6,}  (with pupils={r[2]:>4,})  single={r[3]:>7,}  "
          f"teachers={r[4]:,}")
