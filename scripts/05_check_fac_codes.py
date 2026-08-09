"""Check coding of the facility columns the equity index will rely on."""
import duckdb

con = duckdb.connect(r"e:\pbl project\data\udise.duckdb", read_only=True)

for col in ["building_status", "boundary_wall", "electricity_availability",
            "library_availability", "playground_available", "availability_ramps",
            "furniture_availability", "handwash_near_toilet", "medical_checkups",
            "drinking_water_yn", "drinking_water_func_yn", "internet",
            "handwash_facility_for_meal"]:
    print(f"\n{col}")
    for r in con.execute(f"""
        SELECT year, {col} AS v, count(*) n FROM school_year
        GROUP BY 1,2 ORDER BY 1, n DESC""").fetchall():
        print(f"   {r[0]}  {str(r[1]):>6} : {r[2]:>7,}")

print("\n\ntoilet / device counts (2023-24 quantiles)")
print(con.execute("""
    SELECT
      quantile_cont(total_girls_func_toilet, [0.25,0.5,0.75,0.95]) AS girls_func_toilet,
      quantile_cont(total_boys_func_toilet,  [0.25,0.5,0.75,0.95]) AS boys_func_toilet,
      quantile_cont(desktop + laptop + tablet, [0.5,0.75,0.9,0.99]) AS devices,
      quantile_cont(total_class_rooms, [0.25,0.5,0.75,0.95]) AS classrooms
    FROM school_year WHERE year='2023-24'""").fetchdf().to_string())

print("\n\nschool_category actual class ranges (2023-24, top range per category)")
for r in con.execute("""
    SELECT category_label, lowclass || '-' || highclass AS rng, count(*) n,
           row_number() OVER (PARTITION BY category_label ORDER BY count(*) DESC) rn
    FROM school_year WHERE year='2023-24'
    GROUP BY 1,2 QUALIFY rn <= 3 ORDER BY category_label, n DESC""").fetchall():
    print(f"   {r[0]:<38} {r[1]:<8} {r[2]:>7,}")
