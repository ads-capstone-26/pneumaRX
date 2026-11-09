"""
Where the MIMIC-III data preparation reads the raw files and writes its outputs.

Source directory (each user's own copy of MIMIC-III), first match wins:
    1. --mimic-dir on the command line
    2. MIMIC_III_DIR environment variable
    3. MIMIC_III_DIR=... in the project .env (git-ignored; see .env.example)
There is no built-in default: every user points the pipeline at their own copy.

Local outputs (git-ignored, see the .gitignore "MIMIC" block):
    data/mimic_iii/mimic_iii.db   dataset DB read by the query system
    data/mimic_iii/metadata.csv   table descriptions
    data/mimic_iii/reports/                                      stage reports (destinations defined in PreparationRequest)

Shared snapshot (committed, regenerated only by the dataset maintainer with the `publish` stage):
    docs/mimic3/                                                     SNAPSHOT_FILES
"""
import os
from pathlib import Path

from pneumarx.shared.paths import PROJECT_ROOT

SNAPSHOT_DIR = PROJECT_ROOT / "docs" / "mimic3"


class SourceDirNotSet(RuntimeError):
    pass


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
