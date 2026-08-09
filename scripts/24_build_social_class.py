"""Build enrol_social_class: enrolment by school x year x social category x GRADE.

The existing enrol_social table sums across grades, so it cannot see the class
10 -> 11 cliff. This rebuilds the same source rows keeping class_num, which is
what the equity analysis needs.

Same three-schema harmonisation as 04_build_panel.py.
"""
from pathlib import Path

import duckdb

ROOT = Path(r"e:\pbl project")
RAW = ROOT / "data" / "raw"
DB = ROOT / "data" / "udise.duckdb"

YEARS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
OLD = "2021-22"
TRANS_YEARS = {"2025-26"}
CLASSES = ["cpp"] + [f"c{i}" for i in range(1, 13)]
CLASS_NUM = {"cpp": 0, **{f"c{i}": i for i in range(1, 13)}}


def src(y, t):
    return f"read_csv('{(RAW / y / (t + '.csv')).as_posix()}', header=true, all_varchar=true)"


def key(y):
    return "psuedocode" if y == OLD else "pseudocode"


def label(y):
    if y == OLD:
        return "item_desc"
    return """CASE TRY_CAST(item_id AS INT)
                WHEN 1 THEN 'General' WHEN 2 THEN 'SC'
                WHEN 3 THEN 'ST' WHEN 4 THEN 'OBC' END"""


def filt(y):
    if y == OLD:
        return "item_desc IN ('General','SC','ST','OBC')"
    return "TRY_CAST(item_group AS INT) = 1 AND TRY_CAST(item_id AS INT) IN (1,2,3,4)"


def sums(y):
    has_t = y in TRANS_YEARS
    out = []
    for c in CLASSES:
        b = (f"sum(TRY_CAST({c}_b AS INT) + coalesce(TRY_CAST({c}_t AS INT),0))"
             if has_t else f"sum(TRY_CAST({c}_b AS INT))")
        out.append(f"{b} AS {c}_b")
        out.append(f"sum(TRY_CAST({c}_g AS INT)) AS {c}_g")
    return ",\n               ".join(out)


def main():
    con = duckdb.connect(str(DB))

    wide = "\nUNION ALL".join(f"""
        SELECT '{y}' AS year, TRY_CAST({key(y)} AS BIGINT) AS pseudocode,
               {label(y)} AS social_category, {sums(y)}
        FROM {src(y, 'enr1')} WHERE {filt(y)}
        GROUP BY 1,2,3""" for y in YEARS)
    con.execute(f"CREATE OR REPLACE TEMP TABLE w AS {wide}")

    longs = "\nUNION ALL".join(f"""
        SELECT year, pseudocode, social_category, {CLASS_NUM[c]} AS class_num,
               coalesce({c}_b,0) AS boys, coalesce({c}_g,0) AS girls
        FROM w""" for c in CLASSES)
    con.execute(f"""
        CREATE OR REPLACE TABLE enrol_social_class AS
        SELECT year, pseudocode, social_category, class_num,
               sum(boys) AS boys, sum(girls) AS girls, sum(boys)+sum(girls) AS total
        FROM ({longs})
        GROUP BY 1,2,3,4
        HAVING sum(boys)+sum(girls) > 0""")

    n = con.execute("SELECT count(*) FROM enrol_social_class").fetchone()[0]
    print(f"enrol_social_class: {n:,} rows\n")

    print("=== reconciles with enrol_class? (2025-26) ===")
    print(con.execute("""
        SELECT s.class_num, s.total AS social_sum, c.total AS class_table,
               s.total - c.total AS diff
        FROM (SELECT class_num, sum(total) total FROM enrol_social_class
              WHERE year='2025-26' GROUP BY 1) s
        FULL JOIN (SELECT class_num, sum(total) total FROM enrol_class
                   WHERE year='2025-26' GROUP BY 1) c USING (class_num)
        ORDER BY class_num""").fetchdf().to_string(index=False))
    con.close()


if __name__ == "__main__":
    main()
