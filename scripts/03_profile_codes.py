"""Profile coded/categorical columns so harmonisation assumptions are grounded in the data."""
import duckdb
from pathlib import Path

RAW = Path(r"e:\pbl project\data\raw")
con = duckdb.connect()


def q(sql):
    return con.execute(sql).fetchall()


def csv(year, table):
    return f"read_csv('{(RAW / year / (table + '.csv')).as_posix()}', header=true, all_varchar=true)"


def dist(year, table, col, limit=15):
    try:
        rows = q(
            f"SELECT {col} AS v, count(*) c FROM {csv(year, table)} "
            f"GROUP BY 1 ORDER BY c DESC LIMIT {limit}"
        )
    except Exception as e:
        return f"      {col}: ERROR {str(e)[:80]}"
    total = sum(r[1] for r in rows)
    body = ", ".join(f"{r[0]}={r[1]:,}" for r in rows)
    return f"      {col} (top {len(rows)}, {total:,}): {body}"


print("### drinking water columns, 2023-24 (to derive a canonical flag)")
for c in ["hand_pump_yn", "well_prot_yn", "tap_yn", "othsrc_yn", "well_unprot_yn",
          "pack_water_yn", "tap_fun_yn", "hand_pump_fun_yn"]:
    print(dist("2023-24", "fac", c))

print("\n### drinking water columns, 2021-22")
for c in ["drinking_water_available", "drinking_water_functional"]:
    print(dist("2021-22", "fac", c))

print("\n### ict lab naming")
print(dist("2021-22", "fac", "ict_lab"))
print(dist("2023-24", "fac", "ict_lab_yn"))
print(dist("2023-24", "fac", "comp_ict_lab_yn"))

print("\n### school management / category / type across years")
for y in ["2021-22", "2022-23", "2023-24"]:
    print(f"  -- {y}")
    print(dist(y, "prof1", "managment", 25))
    print(dist(y, "prof1", "school_category", 20))
    print(dist(y, "prof1", "school_type", 6))
    print(dist(y, "prof1", "rural_urban", 6))

print("\n### medium of instruction 1 (2023-24)")
print(dist("2023-24", "prof1", "medium_instr1", 20))

print("\n### enrolment item groups")
print(dist("2023-24", "enr1", "item_group", 15))
print(dist("2023-24", "enr2", "item_group", 15))
print(dist("2021-22", "enr1", "item_desc", 20))
print(dist("2021-22", "enr2", "item_desc", 30))

print("\n### district count sanity")
for y in ["2021-22", "2022-23", "2023-24"]:
    n = q(f"SELECT count(DISTINCT district) FROM {csv(y, 'prof1')}")[0][0]
    print(f"      {y}: {n} distinct districts")
