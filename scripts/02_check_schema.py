"""Compare column sets across years for each table, and report row counts."""
import csv
from pathlib import Path

RAW = Path(r"e:\pbl project\data\raw")
TABLES = ["prof1", "prof2", "fac", "tch", "enr1", "enr2"]
YEARS = sorted(p.name for p in RAW.iterdir() if p.is_dir())


def header(path: Path) -> list[str]:
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        return next(csv.reader(f))


def rowcount(path: Path) -> int:
    n = 0
    with open(path, "rb") as f:
        while chunk := f.read(1 << 22):
            n += chunk.count(b"\n")
    return n - 1


for t in TABLES:
    print("=" * 90)
    print(f"TABLE {t}")
    heads = {}
    for y in YEARS:
        p = RAW / y / f"{t}.csv"
        if not p.exists():
            print(f"  {y}: MISSING")
            continue
        h = header(p)
        heads[y] = h
        print(f"  {y}: {len(h):3d} cols, {rowcount(p):>9,} rows")

    base_year = YEARS[-1]
    base = heads.get(base_year, [])
    for y, h in heads.items():
        if y == base_year:
            continue
        missing = [c for c in base if c not in h]
        extra = [c for c in h if c not in base]
        if missing or extra:
            print(f"  ! {y} vs {base_year}:")
            if missing:
                print(f"      absent in {y}: {missing}")
            if extra:
                print(f"      only in {y}: {extra}")
        elif h != base:
            print(f"  ! {y}: same columns, DIFFERENT ORDER")
        else:
            print(f"  ok {y}: identical to {base_year}")
