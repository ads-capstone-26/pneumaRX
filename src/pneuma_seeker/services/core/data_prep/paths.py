"""
Where the MIMIC-III data preparation reads the raw files and writes its outputs.

Source directory (each user's own copy of MIMIC-III), first match wins:
    1. --mimic-dir on the command line
    2. MIMIC_III_DIR environment variable
    3. MIMIC_III_DIR=... in the project .env (git-ignored; see .env.example)
There is no built-in default: every user points the pipeline at their own copy.

Local outputs (git-ignored, see the .gitignore "MIMIC" block):
    src/pneuma_seeker/services/db/datasets/mimic_iii/mimic_iii.db   dataset DB read by the query system
    src/pneuma_seeker/services/db/datasets/mimic_iii/metadata.csv   table descriptions
    data_src/mimic_iii/reports/                                      one JSON report per stage (REPORT_FILES)

Shared snapshot (committed, regenerated only by the dataset maintainer with the `publish` stage):
    docs/mimic3/                                                     SNAPSHOT_FILES
"""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[5]

DATASET_NAME = "mimic_iii"  # The query system gives datasets named mimic_iii* its MIMIC-III settings
DATASET_DB_ROOT = PROJECT_ROOT / "src" / "pneuma_seeker" / "services" / "db" / "datasets"
REPORT_DIR = PROJECT_ROOT / "data_src" / DATASET_NAME / "reports"
SNAPSHOT_DIR = PROJECT_ROOT / "docs" / "mimic3"


class SourceDirNotSet(RuntimeError):
    pass


# Local output files in REPORT_DIR (one per stage), and what each one is
REPORT_FILES: dict[str, tuple[str, str]] = {
    "inventory": ("mimic3_source_file_inventory.json",
                  "Which MIMIC-III source files were found, their size, and whether each CSV header matches "
                  "the official v1.4 column list."),
    "load": ("mimic3_load_row_counts.json",
             "Rows loaded per table into the mimic_iii DuckDB dataset, compared with the published v1.4 row "
             "counts, plus any CSV lines that could not be parsed."),
    "quality": ("mimic3_data_quality_report.json",
                "Full data quality findings (keys, links between tables, time order, missing values, MIMIC-III "
                "quirks) and the query conventions derived from them, with exact counts. Local only; the "
                "shared, readable version is in docs/mimic3/."),
    "profile": ("mimic3_schema_profile.json",
                "Every table and column: meaning, type, role, missing values, distinct values, all category values, "
                "links to other tables and applicable query conventions, with exact counts. Local only."),
}

# Committed shared snapshot in SNAPSHOT_DIR (small counts suppressed, no paths, no timestamps)
SNAPSHOT_FILES: dict[str, tuple[str, str]] = {
    "conventions": ("mimic3_query_conventions.json",
                    "Shared query conventions for MIMIC-III, with the data fingerprint they were derived from. "
                    "Read by the query system."),
    "quality_md": ("mimic3_data_quality_report.md",
                   "Shared data quality report for MIMIC-III (counts from 1 to 10 shown as <11)."),
    "profile_json": ("mimic3_schema_profile.json",
                     "Shared schema profile: every table and column with its meaning, role, missing values, common "
                     "values, links and applicable query conventions. Read by the query system."),
    "profile_md": ("mimic3_schema_profile.md",
                   "Readable version of the shared schema profile."),
}


def report_path(key: str) -> Path:
    return REPORT_DIR / REPORT_FILES[key][0]


def snapshot_path(key: str) -> Path:
    return SNAPSHOT_DIR / SNAPSHOT_FILES[key][0]


def repo_relative(path: Path) -> str:
    """Path relative to the project root when inside it (keeps user-specific prefixes out of output)."""
    try:
        return Path(path).resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return Path(path).name


def _from_dotenv(key: str) -> str | None:
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return None
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip("'\"") or None
    return None


def resolve_mimic_dir(cli_value: str | None = None) -> Path:
    value = cli_value or os.environ.get("MIMIC_III_DIR") or _from_dotenv("MIMIC_III_DIR")
    if not value:
        raise SourceDirNotSet(
            "The MIMIC-III source folder is not set. Add a line like\n"
            "    MIMIC_III_DIR=/path/to/your/MIMIC_III\n"
            f"to {PROJECT_ROOT / '.env'} (copy .env.example if the file does not exist), "
            "or pass --mimic-dir /path/to/your/MIMIC_III.")
    return Path(value).expanduser()


def dataset_db_path(db_root: Path = DATASET_DB_ROOT) -> Path:
    """Same location DatasetManager uses: <root>/<name>/<name>.db"""
    return db_root / DATASET_NAME / f"{DATASET_NAME}.db"
