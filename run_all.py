"""Rebuild the entire project from the raw UDISE zips.

    py -3.12 run_all.py                 # full build, stops at the first failure
    py -3.12 run_all.py --from analyse   # resume from a named stage
    py -3.12 run_all.py --only report    # run one stage
    py -3.12 run_all.py --list           # show the stages
    py -3.12 run_all.py --skip-optional  # data + report, no PDF/screenshots

Stages run in dependency order. The `verify` stage is a gate: it recomputes
every figure quoted in the report's prose from the database and fails the build
if any of them no longer matches.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"
PY = [sys.executable]

# (stage, script, description, optional)
STAGES: list[tuple[str, str, str, bool]] = [
    ("extract",  "01_extract.py",            "unzip raw vendor files to data/raw", False),
    ("panel",    "04_build_panel.py",        "harmonise 3 schemas -> school_year", False),
    ("age",      "20_build_age.py",          "age-by-grade enrolment -> enrol_age", False),
    ("social",   "24_build_social_class.py", "category-by-grade -> enrol_social_class", False),
    ("analyse",  "06_analyse.py",            "cohort, equity and infrastructure analysis", False),
    ("data",     "09_dashboard_data.py",     "assemble dashboard.json", False),
    ("extend",   "23_extend_dashboard.py",   "add supply, over-age and equity results", False),
    ("report",   "11_build_report.py",       "render the HTML report", False),
    ("verify",   "28_verify_report.py",      "GATE: check every figure against the DB", False),
    ("pdf",      "17_build_pdf.py",          "render the print PDF", True),
    ("shots",    "12_screenshot.py",         "screenshot both themes", True),
    ("preview",  "18_pdf_preview.py",        "PDF pages -> PNG contact sheet", True),
]
NAMES = [s[0] for s in STAGES]


def run(stage: str, script: str, desc: str) -> float:
    path = SCRIPTS / script
    if not path.exists():
        print(f"  !! missing {path}")
        sys.exit(1)
    print(f"\n{'=' * 78}\n[{stage}] {desc}\n  {script}\n{'=' * 78}")
    t0 = time.time()
    res = subprocess.run(PY + [str(path)], cwd=str(ROOT))
    dt = time.time() - t0
    if res.returncode != 0:
        print(f"\n  FAILED: {script} exited {res.returncode} after {dt:.1f}s")
        if stage == "verify":
            print("  The report quotes a figure the database no longer supports.")
            print("  Fix the prose in scripts/11_build_report.py, then re-run.")
        sys.exit(res.returncode)
    print(f"  done in {dt:.1f}s")
    return dt


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", choices=NAMES, help="resume from this stage")
    ap.add_argument("--only", choices=NAMES, help="run a single stage")
    ap.add_argument("--list", action="store_true", help="list stages and exit")
    ap.add_argument("--skip-optional", action="store_true", help="skip PDF and screenshots")
    args = ap.parse_args()

    if args.list:
        print("stages:")
        for name, script, desc, opt in STAGES:
            print(f"  {name:<9} {'(optional) ' if opt else '           '}{desc}")
        return

    todo = list(STAGES)
    if args.only:
        todo = [s for s in todo if s[0] == args.only]
    elif args.start:
        todo = todo[NAMES.index(args.start):]
    if args.skip_optional:
        todo = [s for s in todo if not s[3]]

    print(f"running {len(todo)} stage(s) with {sys.executable}")
    total = 0.0
    for name, script, desc, _ in todo:
        total += run(name, script, desc)

    print(f"\n{'=' * 78}")
    print(f"BUILD OK  ({total:.1f}s total)")
    print(f"  report : {ROOT / 'report' / 'maharashtra-schools.html'}")
    print(f"  pdf    : {ROOT / 'report' / 'maharashtra-schools.pdf'}")
    print(f"  data   : {ROOT / 'data' / 'udise.duckdb'}")
    print("=" * 78)


if __name__ == "__main__":
    main()
