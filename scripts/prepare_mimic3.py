# scripts/prepare_mimic3.py
"""
MIMIC-III v1.4 data preparation.

Builds the "mimic_iii" dataset DB that the query system reads, at
src/pneuma_seeker/services/db/datasets/mimic_iii/mimic_iii.db, and documents
the data it contains. Replaces the earlier scripts/build_mimic3.py loader.

Stages (run one at a time, in this order, or the first four with `all`):
    inventory   Find each table's source file and check its header against the official schema.
    load        Load every table into DuckDB with its official column types; check row counts.
    quality     Check keys, links, time order, missing values and MIMIC-III quirks (read-only),
                and turn each finding into a query convention.
    profile     Describe every table and column (meaning, role, missing values, common values,
                links, applicable conventions); needs the `quality` results.
    publish     Dataset maintainer only: run `quality` and `profile` and write the shared,
                committed snapshot to docs/mimic3/ (no paths, no timestamps, counts 1-10 as <11).

Each stage prints what it does and why. Local reports (one JSON per stage) go to
data_src/mimic_iii/reports/ (git-ignored). `load` and `quality` also warn when your
local data differ from the shared snapshot. Full guide: docs/mimic3/README.md.

Source folder: --mimic-dir, else MIMIC_III_DIR (environment variable or the project
.env; copy .env.example to .env and set it). There is no default.

MIMIC-III is credentialed data (PhysioNet data use agreement): this script reads and writes local
files only, makes no network or LLM calls, and prints schema facts and counts,
never row contents.

Usage (from the project root, with the project environment active):
    python scripts/prepare_mimic3.py inventory
    python scripts/prepare_mimic3.py load
    python scripts/prepare_mimic3.py quality
    python scripts/prepare_mimic3.py profile
    python scripts/prepare_mimic3.py publish                             # dataset maintainer only
    python scripts/prepare_mimic3.py load --tables PATIENTS,ADMISSIONS   # reload a subset in place
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pneuma_seeker.services.core.data_prep import paths  # noqa: E402
from pneuma_seeker.services.core.data_prep.inventory import format_inventory, run_inventory  # noqa: E402
from pneuma_seeker.services.core.data_prep.loader import (  # noqa: E402
    format_load_report, load_all, results_to_dict, write_report,
)
from pneuma_seeker.services.core.data_prep.profile import DESCRIPTION as PROFILE_DESCRIPTION, build_profile  # noqa: E402
from pneuma_seeker.services.core.data_prep.quality import (  # noqa: E402
    DESCRIPTION as QUALITY_DESCRIPTION, format_console, run_quality,
)
from pneuma_seeker.services.core.data_prep.snapshot import (  # noqa: E402
    compare_with_snapshot, fingerprint, read_snapshot_fingerprint, write_snapshot,
)


def banner(title: str, what_why: str) -> None:
    print(f"\n=== {title} ===\n{what_why}\n")


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def save(key: str, payload: dict) -> None:
    name, about = paths.REPORT_FILES[key]
    write_report(paths.report_path(key), {"report": name, "about": about, "generated": now(), **payload})


def source_dir(args) -> Path:
    try:
        return paths.resolve_mimic_dir(args.mimic_dir)
    except paths.SourceDirNotSet as exc:
        sys.exit(str(exc))


def db_path(args) -> Path:
    return paths.dataset_db_path(Path(args.db_root) if args.db_root else paths.DATASET_DB_ROOT)


def run_inventory_stage(args):
    banner("MIMIC-III source file inventory",
           "What: finds each table's file (.csv or .csv.gz) and compares its header with the official v1.4 "
           "column list.\nWhy:  catches missing, misnamed or differently structured files before anything is "
           "loaded. Reads file names and header lines only.")
    inventory = run_inventory(source_dir(args))
    print(format_inventory(inventory))
    save("inventory", inventory.to_dict())
    print(f"\nReport -> {paths.report_path('inventory')}")
    return inventory


def run_load_stage(args, inventory=None):
    banner("MIMIC-III typed load",
           "What: loads each table into DuckDB with its official column types and counts rows that fail to "
           "parse.\nWhy:  guessed types corrupt codes (ICD-9 '0066' would become 66) and the generic loader "
           "drops bad rows silently; row counts are checked against the published v1.4 numbers.")
    inventory = inventory or run_inventory(source_dir(args))
    if inventory.problems and not args.tables:
        print("The source file inventory found problems; loading only the tables that passed.")
    target = db_path(args)
    tables = [t.strip() for t in args.tables.split(",")] if args.tables else None
    print(f"Loading into {target}")
    results = load_all(inventory, target, tables, args.memory_limit, args.threads)
    print("\n" + format_load_report(results))
    save("load", {"db_path": paths.repo_relative(target), "tables": results_to_dict(results)})
    print(f"\nDataset DB -> {target}\nReport     -> {paths.report_path('load')}")
    print("\n" + compare_with_snapshot(target).message())


def run_quality_stage(args):
    banner("MIMIC-III data quality checks", QUALITY_DESCRIPTION)
    target = db_path(args)
    if not target.exists():
        sys.exit(f"No dataset DB at {target}: run the `load` stage first.")
    print(compare_with_snapshot(target).message() + "\n")
    print(f"Checking {target} (read-only)")
    report = run_quality(target)
    print("\n" + format_console(report))
    save("quality", report.to_dict())
    print(f"\nReport -> {paths.report_path('quality')}")
    print("(Readable report and rules: docs/mimic3/, written by the `publish` stage.)")
    return report


def run_profile_stage(args, report=None) -> dict:
    banner("MIMIC-III schema profile", PROFILE_DESCRIPTION)
    target = db_path(args)
    if not target.exists():
        sys.exit(f"No dataset DB at {target}: run the `load` stage first.")
    if report is not None:
        quality = report.to_dict()
    elif paths.report_path("quality").exists():
        quality = json.loads(paths.report_path("quality").read_text())
    else:
        sys.exit("No data quality results yet: run the `quality` stage first.")
    if "conventions" not in quality:
        sys.exit("The data quality results are from an older version: re-run the `quality` stage first.")
    profile = build_profile(target, quality)
    columns = sum(len(t["columns"]) for t in profile["tables"].values())
    roles: dict[str, int] = {}
    for info in profile["tables"].values():
        for col in info["columns"].values():
            roles[col["role"]] = roles.get(col["role"], 0) + 1
    print(f"Profiled {len(profile['tables'])} tables, {columns} columns, {len(profile['links'])} links between tables.")
    print("Columns by role: " + ", ".join(f"{r} {n}" for r, n in sorted(roles.items(), key=lambda kv: -kv[1])))
    save("profile", profile)
    print(f"\nReport -> {paths.report_path('profile')}")
    return profile


def run_publish_stage(args):
    banner("MIMIC-III shared snapshot (dataset maintainer only)",
           "What: re-runs the data quality checks and writes the committed copy of the query conventions and\n"
           "      the report to docs/mimic3/, stamped with a data fingerprint (row count of every table).\n"
           "Why:  everyone (and the query system) uses the same rules; the files change only when the data or rules\n"
           "      change; counts from 1 to 10 are shown as <11 and no paths are written, so it is safe to commit.")
    report = run_quality_stage(args)
    profile = run_profile_stage(args, report)
    target = db_path(args)
    previous = read_snapshot_fingerprint()
    fp = fingerprint(target)
    written = write_snapshot(report, fp, profile=profile)
    if previous is None:
        change = "first snapshot"
    elif previous["id"] == fp["id"]:
        change = "same data as the previous snapshot (only rule or check changes, if any, will show in git diff)"
    else:
        change = f"data changed since the previous snapshot ({previous['id']} -> {fp['id']})"
    print(f"\nShared snapshot, fingerprint {fp['id']}: {change}")
    for path in written.values():
        print(f"  {paths.repo_relative(path)}")
    print("Review with `git diff docs/mimic3/`, then commit the folder.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=["inventory", "load", "quality", "profile", "publish", "all"])
    parser.add_argument("--mimic-dir", help="Folder with the MIMIC-III CSV / CSV.GZ files")
    parser.add_argument("--db-root", help="Dataset DB root (default: the one DatasetManager uses)")
    parser.add_argument("--tables", help="Comma-separated subset to (re)load, e.g. PATIENTS,ADMISSIONS")
    parser.add_argument("--memory-limit", help="DuckDB memory limit, e.g. 8GB")
    parser.add_argument("--threads", type=int, help="DuckDB threads")
    args = parser.parse_args()

    if args.stage == "inventory":
        run_inventory_stage(args)
    elif args.stage == "load":
        run_load_stage(args)
    elif args.stage == "quality":
        run_quality_stage(args)
    elif args.stage == "profile":
        run_profile_stage(args)
    elif args.stage == "publish":
        run_publish_stage(args)
    else:
        run_load_stage(args, run_inventory_stage(args))
        run_profile_stage(args, run_quality_stage(args))


if __name__ == "__main__":
    main()
