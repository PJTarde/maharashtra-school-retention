"""What's already in the panel vs what's sitting unused on disk."""
from pathlib import Path

import duckdb

RAW = Path(r"e:\pbl project\data\raw")
con = duckdb.connect(r"e:\pbl project\data\udise.duckdb", read_only=True)

print("=== tables currently in udise.duckdb ===")
for r in con.execute("SHOW TABLES").fetchall():
    n = con.execute(f'SELECT count(*) FROM "{r[0]}"').fetchone()[0]
    print(f"  {r[0]:<22} {n:>10,} rows")

print("\n=== block granularity (unused: all analysis is at district level) ===")
for r in con.execute("""
    SELECT year, count(DISTINCT district) districts,
           count(DISTINCT block) blocks
    FROM school_year GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"  {r[0]}  {r[1]:>3} districts  {r[2]:>5} blocks")

print("\n=== enrol_social (built, never analysed) ===")
print(con.execute("""
    SELECT social_category, sum(total) pupils
    FROM enrol_social WHERE year='2025-26' GROUP BY 1 ORDER BY 2 DESC""").fetchdf()
    .to_string(index=False))

print("\n=== enr2 age file: extracted to CSV but NOT loaded into the panel ===")
p = (RAW / "2025-26" / "enr2.csv").as_posix()
print(con.execute(f"""
    SELECT item_group, count(DISTINCT item_id) distinct_ages,
           min(TRY_CAST(item_id AS INT)) min_id, max(TRY_CAST(item_id AS INT)) max_id,
           count(*) n_rows
    FROM read_csv('{p}', header=true, all_varchar=true)
    GROUP BY 1""").fetchdf().to_string(index=False))

print("\n  age distribution in class 9 (age id ~= years; over-age = the dropout signal)")
print(con.execute(f"""
    SELECT TRY_CAST(item_id AS INT) AS age_id,
           sum(TRY_CAST(c9_b AS INT) + TRY_CAST(c9_g AS INT)) AS class9_pupils
    FROM read_csv('{p}', header=true, all_varchar=true)
    GROUP BY 1 HAVING class9_pupils > 0 ORDER BY 1""").fetchdf().to_string(index=False))
