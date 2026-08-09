# Where Maharashtra loses its students

A five-year panel analysis of every recognised school in Maharashtra, built from
the raw UDISE+ Data Sharing Portal returns (state code 27, 2021-22 to 2025-26).

**1,08,139 schools · 2.16 crore pupils · 5,42,682 school-year rows.**

The headline result: pupils progress from class 1 to class 10 almost without
loss — every grade-to-grade step holds between 99.6% and 102.6% — and then
**19.7% of them disappear in the single step from class 10 to class 11.** That
cliff is present in all four transition pairs in the panel and has cost roughly
15 lakh school places over four years.

**[→ Read the report](https://YOUR-USERNAME.github.io/maharashtra-school-retention/)**
&nbsp;·&nbsp; [PDF](report/maharashtra-schools.pdf) &nbsp;·&nbsp; [pipeline](scripts/)

<!-- After pushing: Settings > Pages > Source = "Deploy from a branch",
     branch = main, folder = /docs. Then replace the URL above. -->

- **Report (interactive):** `docs/index.html` — self-contained, no build step, no CDN
- **Report (print):** `report/maharashtra-schools.pdf` (14 pages)
- **Queryable database:** `data/udise.duckdb` (rebuild locally, see below)

---

## Getting the data

The raw returns are **not in this repo** — 122 MB of vendor zips, 885 MB unzipped,
and a 328 MB built database, all reproducible from the source. Download them
yourself:

1. Go to the **UDISE+ Data Sharing Portal** (`dashboard.udiseplus.gov.in`) and
   request the school-level files for **Maharashtra (state code 27)**.
2. For each academic year you want, download all available tables — profile 1 & 2,
   facility, teacher, enrolment 1 & 2, and safety where offered.
3. Drop each year into its own folder:

```
project data set pbl/
  maharashtra state 2021-22/*.zip
  maharashtra state 2022-23/*.zip
  ...
```

Folder names must contain the `YYYY-YY` year; the zip filenames themselves do not
matter, because `01_extract.py` reads the table name from the CSV *inside* each
zip. What is tracked here instead: the pipeline, the report, and the small
computed outputs in `data/analysis/`.

## Quick start

```bash
py -3.12 -m pip install -r requirements.txt
py -3.12 run_all.py
```

That rebuilds everything from the zips in `project data set pbl/` — roughly
10–15 minutes, most of it in the enrolment joins. Useful variants:

```bash
py -3.12 run_all.py --list            # show the stages
py -3.12 run_all.py --from analyse    # resume after the slow build stages
py -3.12 run_all.py --only verify     # just re-check the report's numbers
py -3.12 run_all.py --skip-optional   # skip PDF and screenshots
```

The PDF and screenshot stages drive **Microsoft Edge** headless. Everything else
is pure Python. `python` on PATH here is an MSYS2 build with no pip — use
`py -3.12`.

---

## Layout

```
project data set pbl/        raw vendor zips, one folder per year (never edited)
data/raw/<year>/*.csv        unzipped with normalised names
data/udise.duckdb            the built panel — query this directly
data/analysis/*.json         computed outputs; dashboard.json drives the report
report/                      the HTML and PDF deliverables
scripts/                     numbered pipeline + one-off forensics
run_all.py                   orchestrates the pipeline
```

### Pipeline stages

| Stage | Script | What it does |
|---|---|---|
| extract | `01_extract.py` | unzip to `data/raw/<year>/<table>.csv` |
| panel | `04_build_panel.py` | harmonise three schemas into `school_year` |
| age | `20_build_age.py` | age-by-grade enrolment → `enrol_age` (7.8M rows) |
| social | `24_build_social_class.py` | category-by-grade → `enrol_social_class` (7.4M rows) |
| analyse | `06_analyse.py` | cohort, infrastructure, safety, PTR analysis |
| data | `09_dashboard_data.py` | assemble `dashboard.json` |
| extend | `23_extend_dashboard.py` | add supply, over-age and equity results |
| report | `11_build_report.py` | render the HTML (the page template lives here) |
| **verify** | `28_verify_report.py` | **gate** — recheck every quoted figure |
| pdf / shots / preview | `17`, `12`, `18` | print PDF, theme screenshots, page previews |

Remaining numbered scripts (`02`, `03`, `05`, `07`, `08`, `10`, `13`–`16`, `19`,
`21`, `22`, `25`–`27`, `29`, `30`) are one-off data forensics, kept as the
evidence behind the decisions below. They are not part of the build.

### The verify gate

Charts are generated from `dashboard.json` and cannot drift. The prose is
hand-written, so every number in it is a place an error can hide. `28_verify_report.py`
recomputes **88 claims** straight from the database and fails the build if any
no longer matches, then lists any number in the prose that no check covers.

It has already caught two real errors — both the same bug, rounding a value that
was already rounded:

- the gender gap printed as `3.9` when the true figure is `3.957 → 4.0`
  (the chart had subtracted two pre-rounded rates)
- the 2021-22 infrastructure score printed as `82.9` when the exact value is
  `82.847 → 82.8`

---

## Adding a year

1. Drop the new folder into `project data set pbl/`.
2. Add the year to `YEARS` in `04_build_panel.py`, `06_analyse.py`,
   `09_dashboard_data.py`, `20_build_age.py` and `24_build_social_class.py`.
3. Run `py -3.12 run_all.py`.
4. **Re-check the codes.** Every new year so far has broken something.

---

## Data traps already found — do not re-derive, do not "fix"

Each is also written into the report's method section.

- **Three different release schemas.** 2021-22 misspells the key column as
  `psuedocode`, keys enrolment by a text label instead of numeric codes, stores
  enrolment *dense* (every school × every category) where later years are sparse,
  carries one drinking-water flag where later years carry six, and omits the
  teacher caste breakdown. 2022-23 to 2024-25 share one schema. 2025-26 adds
  columns and splits transgender pupils into `*_t`; earlier years folded them
  into `*_b`, so they are folded back to keep the series continuous.
- **Management code 7 is *not* Central Government.** It jumps from 79 schools to
  3,402 in 2025-26. Tracking those schools back one year shows 2,359 were Private
  Aided and 962 Private Unaided. It is a private-sector residual category and has
  its own group; the standard UDISE code list is wrong here.
- **`furniture_availability` is not comparable** — a count of furniture sets in
  2021-22 (0–18,777), a 1/2/3 code from 2022-23. Excluded from the index.
- **`boundary_wall` and `building_status`** are type codes with no labels in any
  supplied schema PDF. Excluded rather than guessed.
- **Three district renames** — Aurangabad → Chhatrapati Sambhajinagar, Osmanabad
  → Dharashiv, Ahmadnagar → Ahilyanagar (2025-26). Merged, each confirmed by
  matching school counts. 36 districts.
- **2021-22 totals are not comparable.** Enrolment falls 2.26 → 2.12 crore
  between the first two years, dragging every 2021-22 transition to roughly 94%.
  A reporting-basis change, not dropout. Headline retention uses the latest pair.
- **Two fake improvements.** The "not applicable" water code was retired in
  2024-25, so functional drinking water reaching 100% is a coding change; and
  zero-teacher schools fall 943 → 9, which is data validation, not hiring. Use
  single-teacher schools (5,906 → 9,269, rising) as the staffing measure.
- **Mumbai (Suburban) reports no class 11–12 at all** — its junior colleges sit
  under Mumbai II, which is why Mumbai II shows retention above 100%.
- **Maharashtra's grade structure is not the national one.** Most primary schools
  run 1–4 and upper primary ends at 7, so pupils change school at 4/5 and 7/8.
  Cohort retention must therefore be computed on state or district aggregates,
  never school-by-school, or ordinary transfers count as dropouts.
- **Schools can be followed; pupils cannot.** `pseudocode` is a school identifier
  and there is no pupil-level file, so every "retention" figure is a ratio of two
  headcounts a year apart, never a followed cohort. No school-level ratio can be
  read as a continuation rate.

## Conventions

- UDISE coding is `1 = Yes, 2 = No, 9 = Not applicable` throughout.
- Enrolment totals come from the four social categories (General/SC/ST/OBC),
  which partition every pupil exactly once. Never sum across item groups.
- Sanity check that the joins are right: rebuilt totals must reproduce published
  UDISE+ figures — 2.16 crore pupils, PTR 28.8 for 2025-26.
- The infrastructure index is 11 equal-weighted facilities, scored only where
  applicable (a boys-only school is not penalised for having no girls' toilet).
- Round once, at the end. Both errors the verifier caught were double-rounding.

---

## Findings

1. **The cliff.** Class 10 → 11 retention is ~80% where every other grade step is
   99.6–102.6%. Stable across all four pairs (76.1 / 80.4 / 79.6 / 80.3).
2. **Boys leave more, and the gap widens** — 1.7 → 4.0 → 4.2 → 4.5 points.
3. **Infrastructure rose 82.8 → 92.2 and did not move the cliff** (district
   r = 0.26).
4. **Geography does not line up.** Jalgaon is among the best-equipped districts
   and worst on retention (62.8%); Gadchiroli is worst-equipped and above average.
5. **The mechanism is a doorway.** 55% of class-10 pupils sit in a school with no
   class 11. Across 407 blocks that is by far the strongest predictor of loss
   (β = −0.46 against −0.19 for infrastructure). At district level it vanishes
   (r = −0.08) because pupils commute across blocks — district is the wrong unit.
6. **Over-age is rising** (5.4% → 7.8% of class 10) and is gendered in the same
   direction as the retention gap.
7. **Adivasi children lose the cliff by 18 points** — ST 64.9% against General
   82.9% — and the doorway does *not* explain it (ST 55.6% vs General 57.7% in
   terminal schools). Two separate mechanisms: geography sets *where*, caste sets
   *who*.
8. **The teacher shortage is urban.** Urban private-aided elementary schools run
   35.9:1; rural government runs 19.3:1 but holds 8,152 single-teacher schools.
9. **Safety, new in 2025-26.** CCTV reaches 92.6% of urban private unaided schools
   and 27.7% of rural government ones — a 65-point gap, the widest in the panel.

## Limits

School identifiers are pseudonymised and there are no coordinates, so no school
can be named or mapped below district level. There are no learning outcomes, no
attendance, and no finance beyond a grant-receipt flag — "retention" here means
appearing in the next grade's count, not passing anything.

## Source

UDISE+ Data Sharing Portal, Ministry of Education, Government of India.
Schema definitions in `project data set pbl/DSP_Schema (1).pdf` and
`maharashtra state 2025-26/DSP_Schema_V1.pdf`.
