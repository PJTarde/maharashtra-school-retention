"""Unzip every UDISE zip into data/raw/<year>/<table>.csv with normalised names."""
import re
import zipfile
from pathlib import Path

ROOT = Path(r"e:\pbl project")
SRC = ROOT / "project data set pbl"
DEST = ROOT / "data" / "raw"

# 27_enr1.csv -> enr1 etc.
TABLES = {"enr1", "enr2", "fac", "prof1", "prof2", "tch", "safety"}


def year_of(folder: Path) -> str:
    m = re.search(r"(\d{4}-\d{2})", folder.name)
    if not m:
        raise ValueError(f"no year in {folder}")
    return m.group(1)


def main() -> None:
    for folder in sorted(SRC.glob("maharashtra state *")):
        year = year_of(folder)
        out = DEST / year
        out.mkdir(parents=True, exist_ok=True)
        for zpath in sorted(folder.glob("*.zip")):
            with zipfile.ZipFile(zpath) as z:
                for entry in z.namelist():
                    stem = Path(entry).stem.split("_", 1)[-1]  # 27_enr1 -> enr1
                    if stem not in TABLES:
                        print(f"  ?? unexpected entry {entry} in {zpath.name}")
                        continue
                    target = out / f"{stem}.csv"
                    if target.exists() and target.stat().st_size > 0:
                        print(f"  = {year}/{stem}.csv (exists, skipped)")
                        continue
                    with z.open(entry) as fsrc, open(target, "wb") as fdst:
                        while chunk := fsrc.read(1 << 20):
                            fdst.write(chunk)
                    mb = target.stat().st_size / 1024 / 1024
                    print(f"  + {year}/{stem}.csv  ({mb:.1f} MB)")


if __name__ == "__main__":
    main()
