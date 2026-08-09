"""Two discrepancies the verifier flagged: are they real, or rounding convention?"""
from decimal import Decimal, ROUND_HALF_UP

import duckdb

con = duckdb.connect(r"e:\pbl project\data\udise.duckdb", read_only=True)
YEARS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]

print("=== gender gap at the cliff: rounded-then-subtracted vs subtracted-then-rounded ===")
for y0, y1 in zip(YEARS, YEARS[1:]):
    r = con.execute(f"""
        SELECT 100.0*b.g/a.g AS girls, 100.0*b.b/a.b AS boys
        FROM (SELECT sum(girls) g, sum(boys) b FROM enrol_class
              WHERE year='{y0}' AND class_num=10) a,
             (SELECT sum(girls) g, sum(boys) b FROM enrol_class
              WHERE year='{y1}' AND class_num=11) b""").fetchone()
    girls, boys = r
    gap_raw = girls - boys
    gap_from_rounded = round(girls, 1) - round(boys, 1)
    print(f"  {y0}->{y1}  girls {girls:.4f}  boys {boys:.4f}  "
          f"| raw gap {gap_raw:.4f} -> {gap_raw:.1f}  "
          f"| from rounded {gap_from_rounded:.1f}")

print("\n=== infrastructure score, first year: exact value ===")
IND = """
    (drinking_water_func_yn=1)::INT + (electricity_availability=1)::INT
  + (library_availability=1)::INT + (playground_available=1)::INT
  + (availability_ramps=1)::INT + (handwash_near_toilet=1)::INT
  + (coalesce(desktop,0)+coalesce(laptop,0)+coalesce(tablet,0)>=1)::INT
  + (internet=1)::INT + (medical_checkups=1)::INT
  + (school_type<>1 AND total_girls_func_toilet>=1)::INT
  + (school_type<>2 AND total_boys_func_toilet>=1)::INT"""
APP = "9 + (school_type<>1)::INT + (school_type<>2)::INT"
for y in (YEARS[0], YEARS[-1]):
    v = con.execute(f"""SELECT avg(({IND})::DOUBLE/nullif(({APP}),0)*100)
                        FROM school_year WHERE year='{y}'""").fetchone()[0]
    half_up = Decimal(str(v)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    print(f"  {y}: exact {v:.6f}   python f'{{:.1f}}' -> {v:.1f}   half-up -> {half_up}")
con.close()
