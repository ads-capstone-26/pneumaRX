"""
Typed load of the MIMIC-III CSVs into the "mimic_iii" dataset DB.

Why not DatasetManager.ingest_dataset (the project's generic CSV ingest)?
- It lets DuckDB guess types from a 100k-row sample, so code columns such as
  ICD-9 '0066' can become the integer 66.
- It uses IGNORE_ERRORS=TRUE, which silently drops rows that fail to parse.

Here every column gets its official type, parsing is strict about the CSV
dialect, and any row DuckDB cannot parse is counted (not dropped silently):
the report lists, per table, rows loaded vs the published v1.4 count and the
number of rejected lines by column and error type. Reject details stay in
temporary tables that are discarded; no data values are printed or written.

The result is written to the same path DatasetManager uses, so the query system and
the rest of Pneuma-Seeker open it unchanged: table and column names in lower
case, plus metadata.csv with table descriptions.
"""
import csv
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import duckdb

from pneuma_seeker.services.core.data_prep.inventory import Inventory, read_header
from pneuma_seeker.services.core.data_prep.mimic3_docs import MIMIC_III_TABLE_DOCS
from pneuma_seeker.services.core.data_prep.mimic3_schema import TABLES, TableSpec


@dataclass
class TableLoad:
    table: str
    source_file: str
    rows_loaded: int = 0
    official_rows: int | None = None  # None: no published count to compare with
    rows_rejected: int = 0  # CSV lines DuckDB could not parse (not in the table)
    rejects_by_column: dict[str, int] = field(default_factory=dict)  # "column / error type" -> lines
    seconds: float = 0.0
    error: str | None = None

    @property
    def row_diff(self) -> int | None:
        return None if self.official_rows is None else self.rows_loaded - self.official_rows

    @property
    def status(self) -> str:
        if self.error:
            return "FAILED"
        if self.rows_rejected:
            return "REJECTED ROWS"
        if self.row_diff is None:
            return "ok (no official count)"
        return "ok" if self.row_diff == 0 else "COUNT DIFFERS"


def _sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def column_types_for(spec: TableSpec, header: list[str]) -> dict[str, str]:
    """Lower-case column name -> type, in the file's own column order.
    Columns not in the official spec are kept as VARCHAR (and flagged by the source file inventory)."""
    types = {name.upper(): dtype for name, dtype in spec.columns}
    return {col.strip().lower(): types.get(col.strip().upper(), "VARCHAR") for col in header}


def load_table(con: duckdb.DuckDBPyConnection, spec: TableSpec, path: Path) -> TableLoad:
    result = TableLoad(table=spec.table_name, source_file=path.name, official_rows=spec.official_rows)
    start = time.time()
    rejects, scans = f"rejects_{spec.table_name}", f"rejects_scan_{spec.table_name}"
    try:
        columns = column_types_for(spec, read_header(path))
        columns_sql = "{" + ", ".join(f"{_sql_str(c)}: {_sql_str(t)}" for c, t in columns.items()) + "}"
        con.execute(f'DROP TABLE IF EXISTS "{spec.table_name}"')
        con.execute(f"""
            CREATE TABLE "{spec.table_name}" AS
            SELECT * FROM read_csv(
                {_sql_str(path.as_posix())},
                header = true,
                auto_detect = false,
                delim = ',', quote = '"', escape = '"',
                columns = {columns_sql},
                store_rejects = true,
                rejects_table = {_sql_str(rejects)},
                rejects_scan = {_sql_str(scans)}
            )
        """)
        result.rows_loaded = con.execute(f'SELECT COUNT(*) FROM "{spec.table_name}"').fetchone()[0]
        summary = con.execute(f"""
            SELECT coalesce(column_name, '(row)') || ' / ' || error_type, COUNT(DISTINCT line)
            FROM "{rejects}" GROUP BY ALL ORDER BY 2 DESC
        """).fetchall()
        result.rejects_by_column = {key: n for key, n in summary}
        result.rows_rejected = con.execute(f'SELECT COUNT(DISTINCT line) FROM "{rejects}"').fetchone()[0]
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {str(exc).splitlines()[0][:300]}"
    finally:
        for temp in (rejects, scans):  # Reject tables hold raw CSV lines: drop them
            con.execute(f'DROP TABLE IF EXISTS "{temp}"')
        result.seconds = round(time.time() - start, 1)
    return result


def write_metadata_csv(db_path: Path, tables: list[str]) -> Path:
    path = db_path.parent / "metadata.csv"
    with open(path, "w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["table_name", "description"])
        for name in tables:
            writer.writerow([TABLES[name].table_name, MIMIC_III_TABLE_DOCS[TABLES[name].table_name][0]])
    return path


def load_all(
    inventory: Inventory,
    db_path: Path,
    tables: list[str] | None = None,
    memory_limit: str | None = None,
    threads: int | None = None,
    progress=print,
) -> list[TableLoad]:
    """
    tables=None rebuilds the whole DB in a temporary file and swaps it in at the
    end, so a failed run never leaves the query system a half-built database.
    tables=[...] reloads only those tables inside the existing DB.
    """
    checks = {c.table: c for c in inventory.checks}
    selected = [t.upper() for t in tables] if tables else inventory.loadable
    unknown = [t for t in selected if t not in TABLES]
    if unknown:
        raise ValueError(f"Unknown table(s): {', '.join(unknown)}")
    not_ready = [t for t in selected if t not in inventory.loadable]
    if not_ready:
        raise ValueError(f"Not loadable (see the source file inventory): {', '.join(not_ready)}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    full_rebuild = tables is None
    target = db_path.with_suffix(".db.building") if full_rebuild else db_path
    if full_rebuild:
        for leftover in (target, Path(f"{target}.wal")):
            leftover.unlink(missing_ok=True)

    con = duckdb.connect(str(target))
    if memory_limit:
        con.execute(f"SET memory_limit = {_sql_str(memory_limit)}")
    if threads:
        con.execute(f"SET threads = {int(threads)}")
    results = []
    try:
        for i, name in enumerate(selected, 1):
            progress(f"[{i}/{len(selected)}] {name} ...")
            result = load_table(con, TABLES[name], Path(checks[name].path))
            results.append(result)
            official = "none" if result.official_rows is None else f"{result.official_rows:,}"
            progress(f"    {result.status}: {result.rows_loaded:,} rows "
                     f"(official {official}), {result.seconds}s"
                     + (f" - {result.error}" if result.error else ""))
        con.execute("CHECKPOINT")
    finally:
        con.close()

    if full_rebuild:
        if any(r.error for r in results):
            raise RuntimeError(f"Load failed; existing DB left unchanged. Partial build: {target}")
        Path(f"{db_path}.wal").unlink(missing_ok=True)
        os.replace(target, db_path)

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        present = {name.upper() for (name,) in con.execute("SHOW TABLES").fetchall()}
    finally:
        con.close()
    write_metadata_csv(db_path, [t for t in TABLES if t in present])
    return results


def format_load_report(results: list[TableLoad]) -> str:
    lines = [f"{'table':20s} {'status':14s} {'rows loaded':>13s} {'official':>13s} {'diff':>9s} {'rejected':>9s} {'sec':>7s}"]
    for r in results:
        official = "-" if r.official_rows is None else f"{r.official_rows:,}"
        diff = "-" if r.row_diff is None else f"{r.row_diff:+,}"
        lines.append(f"{r.table:20s} {r.status:14s} {r.rows_loaded:>13,} {official:>13s} "
                     f"{diff:>9s} {r.rows_rejected:>9,} {r.seconds:>7}")
        for key, n in r.rejects_by_column.items():
            lines.append(f"{'':20s}   rejected: {key}: {n:,} lines")
        if r.error:
            lines.append(f"{'':20s}   {r.error}")
    total = sum(r.rows_loaded for r in results)
    bad = [r.table for r in results if not r.status.startswith("ok")]
    lines.append(f"Total rows loaded: {total:,}; tables needing attention: {', '.join(bad) or 'none'}")
    return "\n".join(lines)


def write_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))


def results_to_dict(results: list[TableLoad]) -> list[dict]:
    return [asdict(r) | {"status": r.status, "row_diff": r.row_diff} for r in results]
