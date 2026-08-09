"""Consolidate the analysis outputs into one JSON for the dashboard."""
import json
from pathlib import Path

import duckdb

ROOT = Path(r"e:\pbl project")
OUT = ROOT / "data" / "analysis"
con = duckdb.connect(str(ROOT / "data" / "udise.duckdb"), read_only=True)

YEARS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
FIRST, LATEST = YEARS[0], YEARS[-1]
MAIN_PAIR = f"{YEARS[-2]} -> {LATEST}"
PREV_PAIR = f"{YEARS[-3]} -> {YEARS[-2]}"

D = """CASE trim(district)
    WHEN 'AURANGABAD (MAHARASHTRA)' THEN 'CHHATRAPATI SAMBHAJINAGAR'
    WHEN 'OSMANABAD' THEN 'DHARASHIV'
    WHEN 'AHMADNAGAR' THEN 'AHILYANAGAR'
    ELSE trim(district) END"""

OVERRIDE = {
    "MUMBAI II": "Mumbai II",
    "MUMBAI (SUBURBAN)": "Mumbai (Suburban)",
    "RAIGARH (MAHARASHTRA)": "Raigarh",
    "AHILYANAGAR": "Ahilyanagar",
}


def load(name):
    return json.loads((OUT / f"{name}.json").read_text())


def title(s):
    """UDISE stores districts upper-case; render them readably."""
    s = s.strip()
    return OVERRIDE.get(s) or " ".join(w.capitalize() for w in s.split())


data = {"years": YEARS, "latest": LATEST, "first": FIRST}

# ---------------------------------------------------------------- headline
hd = con.execute(f"""
    SELECT count(*) schools, sum(enr_total) students, sum(total_tch) teachers
    FROM school_year WHERE year='{LATEST}'""").fetchone()
all_tr = load("transitions_state")
tr = [r for r in all_tr if r["period"] == MAIN_PAIR]
t1011 = next(r for r in tr if r["from_class"] == 10)

data["headline"] = {
    "schools": hd[0], "students": int(hd[1]), "teachers": int(hd[2]), "districts": 36,
    "retention_10_11": t1011["retention"],
    "lost_10_11": int(t1011["total0"] - t1011["total1"]),
    "retention_boys": t1011["retention_boys"],
    "retention_girls": t1011["retention_girls"],
    "gender_gap": round(t1011["retention_girls"] - t1011["retention_boys"], 1),
}

# the class 10 -> 11 cliff in every transition pair (the structural proof)
data["cliff_by_period"] = [
    {"period": r["period"].replace(" -> ", "\u2192"),
     "retention": r["retention"], "boys": r["retention_boys"],
     "girls": r["retention_girls"],
     "gap": round(r["retention_girls"] - r["retention_boys"], 1),
     "lost": int(r["total0"] - r["total1"])}
    for r in all_tr if r["from_class"] == 10
]

data["pyramid"] = [
    {"class_num": r["class_num"], "boys": int(r["boys"]), "girls": int(r["girls"]),
     "total": int(r["total"]), "schools": r["schools_offering"]}
    for r in load("grade_pyramid") if r["year"] == LATEST and r["class_num"] >= 1
]

data["transitions"] = [
    {"from_class": r["from_class"], "to_class": r["to_class"],
     "retention": r["retention"], "boys": r["retention_boys"],
     "girls": r["retention_girls"], "lost": int(r["total0"] - r["total1"])}
    for r in tr
]
data["transitions_prev"] = [
    {"from_class": r["from_class"], "retention": r["retention"]}
    for r in all_tr if r["period"] == PREV_PAIR
]

data["segments"] = [
    {"location": r["location"], "management": r["management_group"],
     "score": r["score"], "schools": r["schools"], "students": int(r["students"])}
    for r in load("score_by_segment")
    if r["year"] == LATEST and r["management_group"] in
    ("Government", "Private Aided", "Private Unaided")
]

# ---------------------------------------------------------------- districts
scatter = {r["district"]: r["retention"] for r in load("district_scatter")}
dist = []
for r in load("score_by_district"):
    if r["year"] != LATEST:
        continue
    dist.append({
        "district": title(r["district"]), "score": r["score"],
        "schools": r["schools"], "students": int(r["students"]),
        "internet": r["pct_internet"], "computer": r["pct_computer"],
        "girls_toilet": r["pct_girls_toilet"], "water": r["pct_water"],
        "electricity": r["pct_electricity"],
        "retention": scatter.get(r["district"]),
    })
data["districts"] = sorted(dist, key=lambda d: d["score"])

data["district_change"] = sorted(
    ({"district": title(r["district"]), "y_first": r["score_2021"],
      "y_last": r["score_2023"], "change": r["change"]}
     for r in load("district_change")
     if r["score_2021"] is not None and r["score_2023"] is not None),
    key=lambda d: -d["change"])

data["deprivation"] = [
    {"gap": r["gap"], "schools": r["schools"], "students": int(r["girls_affected"] or 0)}
    for r in load("deprivation") if r["schools"] > 0
]

data["ptr"] = [
    {"location": r["location"], "management": r["management_group"],
     "schools": r["schools"], "ptr": r["ptr"], "over_30": r["over_30"],
     "single_teacher": r["single_teacher"]}
    for r in load("ptr")
    if r["management_group"] in ("Government", "Private Aided", "Private Unaided")
]

data["score_by_year"] = load("score_by_year")
data["safety"] = load("safety")
data["safety_segment"] = load("safety_segment")

# --------------------------------------------------------------- coverage
LABELS = {
    "water": "Functional drinking water", "gtoilet": "Functional girls' toilet",
    "btoilet": "Functional boys' toilet", "elec": "Electricity",
    "lib": "Library", "play": "Playground", "ramp": "Ramps",
    "hwash": "Handwash near toilet",
    "comp": "Computing device", "net": "Internet", "med": "Medical check-ups",
}
con.execute("""
    CREATE OR REPLACE TEMP TABLE ind AS
    SELECT year,
           1 a_water, (drinking_water_func_yn=1)::INT m_water,
           (school_type<>1)::INT a_gtoilet,
           (school_type<>1 AND total_girls_func_toilet>=1)::INT m_gtoilet,
           (school_type<>2)::INT a_btoilet,
           (school_type<>2 AND total_boys_func_toilet>=1)::INT m_btoilet,
           1 a_elec, (electricity_availability=1)::INT m_elec,
           1 a_lib,  (library_availability=1)::INT m_lib,
           1 a_play, (playground_available=1)::INT m_play,
           1 a_ramp, (availability_ramps=1)::INT m_ramp,
           1 a_hwash,(handwash_near_toilet=1)::INT m_hwash,
           1 a_comp, (coalesce(desktop,0)+coalesce(laptop,0)+coalesce(tablet,0)>=1)::INT m_comp,
           1 a_net,  (internet=1)::INT m_net,
           1 a_med,  (medical_checkups=1)::INT m_med
    FROM school_year""")
cov = []
for k, lab in LABELS.items():
    rows = con.execute(f"""
        SELECT year, round(100.0*sum(m_{k})/sum(a_{k}),1) FROM ind
        GROUP BY 1 ORDER BY 1""").fetchall()
    cov.append({"key": k, "label": lab, **{y: v for y, v in rows}})
data["coverage"] = sorted(cov, key=lambda c: c[LATEST])

# ------------------------------------------------------------ enrolment trend
data["enrolment_trend"] = [
    {"year": r[0], "students": int(r[1]), "schools": r[2], "teachers": int(r[3])}
    for r in con.execute("""
        SELECT year, sum(enr_total), count(*), sum(total_tch)
        FROM school_year GROUP BY 1 ORDER BY 1""").fetchall()
]

path = OUT / "dashboard.json"
path.write_text(json.dumps(data, indent=1))
print(f"wrote {path}  ({path.stat().st_size/1024:.0f} KB)")
print(json.dumps(data["headline"], indent=1))
print("\ncliff by period:")
for c in data["cliff_by_period"]:
    print(f"  {c['period']}  {c['retention']:>5}%  gap +{c['gap']}  lost {c['lost']:,}")
print("\ncoverage first -> last:")
for c in data["coverage"]:
    print(f"  {c['label']:<26} {c[FIRST]:>5} -> {c[LATEST]:>5}")
print("\nsafety:")
for s in data["safety"]:
    print(f"  {s['measure']:<42} {s['pct']:>5}%")
