"""
Inventory of the raw MIMIC-III files.

For every official table, finds its file (TABLE.csv or TABLE.csv.gz, any case)
and compares the CSV header line with the official column list. Only file
names, sizes and header lines are read, never data rows.
"""
import csv
import gzip
import io
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pneuma_seeker.services.core.data_prep.mimic3_schema import TABLES, TEAM_TABLES, TableSpec


@dataclass
class FileCheck:
    table: str
    expected_in_team_copy: bool
    found: bool = False
    path: str | None = None
    compressed: bool = False
    size_mb: float | None = None
    header_ok: bool | None = None
    missing_columns: list[str] = field(default_factory=list)
    extra_columns: list[str] = field(default_factory=list)
    order_differs: bool = False
    error: str | None = None

    @property
    def status(self) -> str:
        if not self.found:
            return "MISSING" if self.expected_in_team_copy else "absent (known)"
        if self.error:
            return "UNREADABLE"
        if not self.header_ok:
            return "HEADER MISMATCH"
        return "ok (column order differs)" if self.order_differs else "ok"


@dataclass
class Inventory:
    source_dir: str
    source_dir_exists: bool
    checks: list[FileCheck]
    unrecognized_files: list[str]

    @property
    def loadable(self) -> list[str]:
        return [c.table for c in self.checks if c.found and c.header_ok and not c.error]

    @property
    def problems(self) -> list[FileCheck]:
        return [c for c in self.checks if c.status in ("MISSING", "UNREADABLE", "HEADER MISMATCH")]

    def to_dict(self) -> dict:
        return {
            "source_dir": self.source_dir,
            "source_dir_exists": self.source_dir_exists,
            "loadable_tables": self.loadable,
            "checks": [asdict(c) | {"status": c.status} for c in self.checks],
            "unrecognized_files": self.unrecognized_files,
        }


def open_text(path: Path):
    """Opens a .csv or .csv.gz file as UTF-8 text (BOM stripped)."""
    if path.suffix.lower() == ".gz":
        return io.TextIOWrapper(gzip.open(path, "rb"), encoding="utf-8-sig", newline="")
    return open(path, encoding="utf-8-sig", newline="")


def read_header(path: Path) -> list[str]:
    with open_text(path) as file:
        return next(csv.reader(file))


def find_file(source_dir: Path, table: str) -> Path | None:
    """TABLE.csv preferred over TABLE.csv.gz; file-name case is ignored."""
    by_lower = {p.name.lower(): p for p in source_dir.iterdir() if p.is_file()}
    for suffix in (".csv", ".csv.gz"):
        match = by_lower.get(f"{table.lower()}{suffix}")
        if match is not None:
            return match
    return None


def compare_header(spec: TableSpec, header: list[str]) -> tuple[list[str], list[str], bool]:
    """Returns (missing, extra, order_differs), case-insensitively."""
    expected = [c.upper() for c in spec.column_names]
    actual = [c.strip().upper() for c in header]
    missing = [c for c in expected if c not in actual]
    extra = [c for c in actual if c not in expected]
    common_actual = [c for c in actual if c in expected]
    common_expected = [c for c in expected if c in actual]
    return missing, extra, common_actual != common_expected


def run_inventory(source_dir: Path) -> Inventory:
    exists = source_dir.is_dir()
    checks: list[FileCheck] = []
    matched: set[str] = set()
    for name, spec in TABLES.items():
        check = FileCheck(table=name, expected_in_team_copy=name in TEAM_TABLES)
        checks.append(check)
        if not exists:
            continue
        path = find_file(source_dir, name)
        if path is None:
            continue
        matched.add(path.name)
        check.found = True
        check.path = str(path)
        check.compressed = path.suffix.lower() == ".gz"
        check.size_mb = round(path.stat().st_size / 1e6, 1)
        try:
            header = read_header(path)
        except Exception as exc:  # e.g. Box placeholder not yet downloaded, bad gzip
            check.error = f"{type(exc).__name__}: {exc}"
            continue
        check.missing_columns, check.extra_columns, check.order_differs = compare_header(spec, header)
        check.header_ok = not check.missing_columns and not check.extra_columns

    unrecognized = []
    if exists:
        unrecognized = sorted(
            p.name for p in source_dir.iterdir()
            if p.is_file() and p.name not in matched and not p.name.startswith(".")
        )
    return Inventory(str(source_dir), exists, checks, unrecognized)


def format_inventory(inv: Inventory) -> str:
    lines = [f"Source: {inv.source_dir}" + ("" if inv.source_dir_exists else "  <-- NOT FOUND")]
    lines.append(f"{'table':20s} {'status':28s} {'size MB':>9s}  file")
    for c in inv.checks:
        size = f"{c.size_mb:,.1f}" if c.size_mb is not None else ""
        lines.append(f"{c.table:20s} {c.status:28s} {size:>9s}  {Path(c.path).name if c.path else ''}")
        if c.missing_columns:
            lines.append(f"{'':20s}   missing columns: {', '.join(c.missing_columns)}")
        if c.extra_columns:
            lines.append(f"{'':20s}   unexpected columns: {', '.join(c.extra_columns)}")
        if c.error:
            lines.append(f"{'':20s}   {c.error}")
    if inv.unrecognized_files:
        lines.append(f"Other files in the folder (not loaded): {', '.join(inv.unrecognized_files)}")
    team_found = sum(c.found for c in inv.checks if c.expected_in_team_copy)
    lines.append(f"Loadable: {len(inv.loadable)} tables; team tables found: {team_found}/{len(TEAM_TABLES)}; "
                 f"problems: {len(inv.problems)}")
    return "\n".join(lines)
