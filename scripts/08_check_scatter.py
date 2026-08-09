import json
from pathlib import Path

import duckdb

OUT = Path(r"e:\pbl project\data\analysis")
con = duckdb.connect(r"e:\pbl project\data\udise.duckdb", read_only=True)

D = """CASE trim(district)
    WHEN 'AURANGABAD (MAHARASHTRA)' THEN 'CHHATRAPATI SAMBHAJINAGAR'
    WHEN 'OSMANABAD' THEN 'DHARASHIV' ELSE trim(district) END"""

scatter = {r["district"] for r in json.loads((OUT / "district_scatter.json").read_text())}
alld = {r[0] for r in con.execute(
    f"SELECT DISTINCT {D} FROM school_year WHERE year='2023-24'").fetchall()}
print("districts in panel:", len(alld), " in scatter:", len(scatter))
print("missing:", alld - scatter)

for d in sorted(alld - scatter):
    print(f"\n{d}: class-10/11 enrolment by year")
    for r in con.execute(f"""
        SELECT e.year, e.class_num, sum(e.total) students, count(*) schools
        FROM enrol_class e JOIN school_year s USING (year, pseudocode)
        WHERE {D} = ? AND e.class_num IN (9,10,11,12)
        GROUP BY 1,2 ORDER BY 1,2""", [d]).fetchall():
        print(f"   {r[0]}  class {r[1]:>2}: {r[2]:>8,} students in {r[3]:>4} schools")
