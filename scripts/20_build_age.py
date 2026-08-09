"""Load the age-wise enrolment file (enr2) into the panel as `enrol_age`.

enr2 has sat unused on disk: ~800k rows per year giving enrolment by class AND
age. Over-age enrolment (a pupil older than the nominal age for their grade) is
the standard leading indicator of dropout, so this is the input for the
early-warning analysis.

Schema quirks, same shape as enr1:
  * 2021-22 keys rows by a text `item_desc` ("Age<5", "Age5" .. "Age22", "None")
    and misspells the id column `psuedocode`
  * 2022-23 onward use item_group = 8 with item_id carrying the age
  * 2025-26 splits transgender into `*_t`, folded back into boys for continuity
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


def src(year, table):
    return f"read_csv('{(RAW / year / (table + '.csv')).as_posix()}', header=true, all_varchar=true)"


def key(year):
    return "psuedocode" if year == OLD else "pseudocode"


def age_expr(year):
    """Normalise the age key to an integer year of age."""
    if year == OLD:
        # 'Age<5' -> 4, 'Age12' -> 12, 'None' -> NULL
        return ("CASE WHEN item_desc = 'Age<5' THEN 4 "
                "WHEN item_desc LIKE 'Age%' "
                "THEN TRY_CAST(replace(item_desc, 'Age', '') AS INT) END")
    return "TRY_CAST(item_id AS INT)"


def age_filter(year):
    if year == OLD:
        return "item_desc <> 'None'"
    return "TRY_CAST(item_group AS INT) = 8"


def sums(year):
    has_t = year in TRANS_YEARS
    parts = []
    for c in CLASSES:
        b = (f"sum(TRY_CAST({c}_b AS INT) + coalesce(TRY_CAST({c}_t AS INT), 0))"
             if has_t else f"sum(TRY_CAST({c}_b AS INT))")
        parts.append(f"{b} AS {c}_b")
        parts.append(f"sum(TRY_CAST({c}_g AS INT)) AS {c}_g")
    return ",\n               ".join(parts)


def main():
    con = duckdb.connect(str(DB))

    wide = "\nUNION ALL".join(f"""
        SELECT '{y}' AS year, TRY_CAST({key(y)} AS BIGINT) AS pseudocode,
               {age_expr(y)} AS age,
               {sums(y)}
        FROM {src(y, 'enr2')}
        WHERE {age_filter(y)}
        GROUP BY 1, 2, 3""" for y in YEARS)
    con.execute(f"CREATE OR REPLACE TEMP TABLE age_wide AS {wide}")

    longs = "\nUNION ALL".join(f"""
        SELECT year, pseudocode, age, {CLASS_NUM[c]} AS class_num,
               coalesce({c}_b, 0) AS boys, coalesce({c}_g, 0) AS girls
        FROM age_wide""" for c in CLASSES)
    con.execute(f"""
        CREATE OR REPLACE TABLE enrol_age AS
        SELECT year, pseudocode, class_num, age,
               sum(boys) AS boys, sum(girls) AS girls, sum(boys) + sum(girls) AS total
        FROM ({longs})
        WHERE age IS NOT NULL
        GROUP BY 1, 2, 3, 4
        HAVING sum(boys) + sum(girls) > 0""")

    n = con.execute("SELECT count(*) FROM enrol_age").fetchone()[0]
    print(f"enrol_age: {n:,} rows\n")

    # --- validate the age coding against enrol_class totals
    print("=== does enrol_age reconcile with enrol_class? (2025-26) ===")
    print(con.execute("""
        SELECT a.class_num,
               a.total AS age_table, c.total AS class_table,
               a.total - c.total AS diff
        FROM (SELECT class_num, sum(total) total FROM enrol_age
              WHERE year='2025-26' GROUP BY 1) a
        FULL JOIN (SELECT class_num, sum(total) total FROM enrol_class
                   WHERE year='2025-26' GROUP BY 1) c USING (class_num)
        ORDER BY class_num""").fetchdf().to_string(index=False))

    # --- is age id actually age? modal age per class should climb by 1
    print("\n=== modal age by class (2025-26) - should rise one year per grade ===")
    print(con.execute("""
        SELECT class_num,
               arg_max(age, total) AS modal_age,
               round(sum(age * total) / nullif(sum(total), 0), 1) AS mean_age
        FROM enrol_age WHERE year='2025-26' AND class_num BETWEEN 1 AND 12
        GROUP BY 1 ORDER BY 1""").fetchdf().to_string(index=False))

    con.close()


if __name__ == "__main__":
    main()
