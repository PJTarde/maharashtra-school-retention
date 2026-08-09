"""How much can we actually say, given pupils cannot be tracked individually?

pseudocode identifies a SCHOOL, not a pupil. So a school's class-11 enrolment is
(its own continuing pupils) + (arrivals from schools that end at class 10), and
nothing in the data separates the two.

What IS pinned down is the accounting identity:
    class_11_total = stayers_placed + movers_placed          (ignoring repeaters)
    stayers_placed <= stayers        (a school cannot keep more than it taught)
    movers_placed  <= movers
which bounds each rate without needing pupil-level tracking.
"""
import duckdb

DB = r"e:\pbl project\data\udise.duckdb"
Y0, Y1 = "2024-25", "2025-26"
con = duckdb.connect(DB, read_only=True)

r = con.execute(f"""
    WITH c10 AS (
        SELECT s.pseudocode, s.highclass, e.total AS c10
        FROM school_year s JOIN enrol_class e USING (year, pseudocode)
        WHERE s.year='{Y0}' AND e.class_num=10 AND e.total>0
    ),
    c11 AS (
        SELECT pseudocode, total AS c11 FROM enrol_class
        WHERE year='{Y1}' AND class_num=11 AND total>0
    )
    SELECT
      (SELECT sum(c10) FROM c10 WHERE highclass >= 11) AS stayers,
      (SELECT sum(c10) FROM c10 WHERE highclass = 10)  AS movers,
      (SELECT sum(c11) FROM c11)                       AS c11_total,
      (SELECT sum(c11) FROM c11 WHERE pseudocode IN
          (SELECT pseudocode FROM c10 WHERE highclass >= 11)) AS c11_in_continuing,
      (SELECT sum(c11) FROM c11 WHERE pseudocode NOT IN (SELECT pseudocode FROM c10))
                                                       AS c11_in_no_class10
""").fetchone()
stayers, movers, c11_total, c11_cont, c11_nc10 = [float(x or 0) for x in r]

print("Class-10 pupils in the base year, split by whether their school goes on:")
print(f"  can stay (school offers class 11) : {stayers:>12,.0f}")
print(f"  must move (school ends at 10)     : {movers:>12,.0f}")
print(f"  total                             : {stayers+movers:>12,.0f}")
print(f"\nClass-11 places the next year       : {c11_total:>12,.0f}")
print(f"  of which in schools that also had class 10 and offer 11:"
      f" {c11_cont:>12,.0f}")
print(f"  of which in schools with NO class 10 at all (standalone junior"
      f" colleges): {c11_nc10:>12,.0f}")

print("\n--- what the accounting identity forces ---")
print("  class_11_total = stayers_placed + movers_placed")
mov_min = c11_total - stayers            # stayers cannot exceed their own number
mov_max = min(movers, c11_total)
stay_min = c11_total - movers
stay_max = min(stayers, c11_total)
print(f"\n  movers placed  : between {mov_min:>10,.0f} and {mov_max:>10,.0f}"
      f"   ->  {100*mov_min/movers:.1f}% to {100*mov_max/movers:.1f}% of movers")
print(f"  stayers placed : between {stay_min:>10,.0f} and {stay_max:>10,.0f}"
      f"   ->  {100*stay_min/stayers:.1f}% to {100*stay_max/stayers:.1f}% of stayers")

print("\n--- the one piece that needs no assumption ---")
print(f"  {c11_nc10:,.0f} class-11 places sit in schools with no class 10 of their own,")
print(f"  so those pupils must have arrived from elsewhere. That is at least")
print(f"  {100*c11_nc10/movers:.1f}% of the {movers:,.0f} pupils who had to move.")

print("\n--- what the 103.7% figure actually is ---")
print(f"  class-11 enrolment in continuing schools / their own prior class 10")
print(f"  = {c11_cont:,.0f} / {stayers:,.0f} = {100*c11_cont/stayers:.1f}%")
print("  It is an INTAKE ratio. Above 100% proves those schools are net importers")
print("  of pupils; it does not measure how many of their own pupils stayed.")
con.close()
