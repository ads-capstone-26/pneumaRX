"""
Data quality checks on the loaded "mimic_iii" dataset DB.

What: runs every check in quality_checks.py (keys, referential integrity,
temporal consistency, MIMIC-III quirks), then measures missing values, padded
text values and the value vocabulary of coded columns.

Why: the evaluation SQL runs on the original MIMIC-III schema, so the data are
not edited. Instead each problem found becomes a query convention: a rule
that tells the query system how to query around it, with the measured
counts as evidence.

Read-only: the DB is opened with read_only=True. Outputs contain aggregate
counts only (written by scripts/prepare_mimic3.py):
    data_src/mimic_iii/reports/mimic3_data_quality_report.json   full local results (exact counts)
    docs/mimic3/ (via snapshot.py)                                 shared readable report + rules
"""
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import duckdb

from pneuma_seeker.services.core.data_prep.quality_checks import (
    DISTRIBUTIONS, GROUP_RULES, Check, Schema, build_checks,
)

DESCRIPTION = (
    "What: checks keys, links between tables, time order, missing values and known MIMIC-III quirks "
    "in the loaded DB (read-only).\n"
    "Why:  the data are not edited (evaluation SQL runs on the original schema); each problem found "
    "becomes a query convention that the query system follows."
)


@dataclass
class CheckResult:
    id: str
    category: str
    description: str
    status: str  # pass | flag | info | error
    flagged: int = 0
    total: int = 0
    extra: dict[str, int] = field(default_factory=dict)
    convention: str = ""
    applies_to: list[str] = field(default_factory=list)
    error: str | None = None
    seconds: float = 0.0

    @property
    def pct(self) -> float:
        return round(100.0 * self.flagged / self.total, 3) if self.total else 0.0


@dataclass
class QualityReport:
    checks: list[CheckResult]
    missingness: dict[str, dict]  # table -> {"rows": n, "columns": {col: % null}}
    padded_text: dict[str, dict[str, int]]  # table -> {col: values with leading/trailing spaces}
    distributions: dict[str, dict]
    conventions: list[dict]

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for c in self.checks:
            counts[c.status] = counts.get(c.status, 0) + 1
        return counts

    def to_dict(self) -> dict:
        return {
            "summary": self.summary(),
            "checks": [asdict(c) | {"pct": c.pct} for c in self.checks],
            "missingness": self.missingness,
            "padded_text": self.padded_text,
            "distributions": self.distributions,
            "conventions": self.conventions,
        }


def read_schema(con: duckdb.DuckDBPyConnection) -> tuple[Schema, dict[str, dict[str, str]]]:
    """Returns (table -> column names, table -> {column: type})."""
    schema: Schema = {}
    types: dict[str, dict[str, str]] = {}
    for table, column, dtype in con.execute(
        "SELECT table_name, column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'main' ORDER BY table_name, ordinal_position"
    ).fetchall():
        schema.setdefault(table, []).append(column)
        types.setdefault(table, {})[column] = dtype
    return schema, types


def run_check(con: duckdb.DuckDBPyConnection, check: Check) -> CheckResult:
    result = CheckResult(check.id, check.category, check.description, "error",
                         convention=check.convention, applies_to=list(check.applies_to))
    start = time.time()
    try:
        cursor = con.execute(check.sql)
        names = [d[0] for d in cursor.description]
        row = dict(zip(names, cursor.fetchone()))
        result.flagged = int(row.pop("flagged") or 0)
        result.total = int(row.pop("total") or 0)
        result.extra = {k: int(v or 0) for k, v in row.items()}
        if check.expect_zero:
            result.status = "pass" if result.flagged == 0 else "flag"
        else:
            result.status = "info"
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {str(exc).splitlines()[0][:300]}"
    result.seconds = round(time.time() - start, 1)
    return result


def missingness(con: duckdb.DuckDBPyConnection, schema: Schema) -> dict[str, dict]:
    out = {}
    for table, cols in schema.items():
        non_null = ", ".join('COUNT("' + c + '")' for c in cols)
        counts = con.execute(f'SELECT COUNT(*), {non_null} FROM "{table}"').fetchone()
        rows = counts[0]
        out[table] = {
            "rows": rows,
            "columns": {c: round(100.0 * (rows - n) / rows, 3) if rows else 0.0 for c, n in zip(cols, counts[1:])},
            "null_counts": {c: rows - n for c, n in zip(cols, counts[1:])},  # Exact, for small-count suppression
        }
    return out


def padded_text(con: duckdb.DuckDBPyConnection, types: dict[str, dict[str, str]]) -> dict[str, dict[str, int]]:
    """Counts text values with leading/trailing whitespace (e.g. drg_type 'APR '), which make
    exact matches such as WHERE drg_type = 'APR' silently return nothing."""
    out = {}
    for table, cols in types.items():
        text = [c for c, t in cols.items() if t == "VARCHAR"]
        if not text:
            continue
        exprs = ", ".join(f'COUNT(*) FILTER (WHERE "{c}" <> trim("{c}"))' for c in text)
        counts = con.execute(f'SELECT {exprs} FROM "{table}"').fetchone()
        padded = {c: int(n) for c, n in zip(text, counts) if n}
        if padded:
            out[table] = padded
    return out


def distributions(con: duckdb.DuckDBPyConnection, schema: Schema, top: int = 25) -> dict[str, dict]:
    out = {}
    for d in DISTRIBUTIONS:
        if d.table not in schema or d.column not in schema[d.table]:
            continue
        rows = con.execute(
            f'SELECT coalesce(CAST("{d.column}" AS VARCHAR), \'(null)\'), COUNT(*) '
            f'FROM "{d.table}" GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT {top + 1}').fetchall()  # Stable order on ties
        out[d.id] = {"table": d.table, "column": d.column, "description": d.description,
                     "convention": d.convention, "values": dict(rows[:top]), "truncated": len(rows) > top}
    return out


def derive_conventions(checks: list[CheckResult], built: list[Check], dists: dict[str, dict],
                       miss: dict[str, dict], padded: dict[str, dict[str, int]]) -> list[dict]:
    """
    One rule per kind of finding. Checks with a `group` (e.g. negative durations in four
    tables) share one rule from GROUP_RULES that lists every affected target, with the
    evidence kept per target. Other checks keep their own rule.

    Each entry: {id, rule, targets, applies_to, sources (check ids), evidence {target: counts}}
    """
    by_id = {c.id: c for c in built}
    entries: list[dict] = []
    groups: dict[str, dict] = {}

    def group_entry(group: str) -> dict:
        if group not in groups:
            groups[group] = {"id": f"group.{group}", "rule": "", "targets": [], "applies_to": [],
                             "sources": [], "evidence": {}}
            entries.append(groups[group])
        return groups[group]

    def extend(entry: dict, target: str, source: str, applies_to: list[str], evidence: dict) -> None:
        entry["targets"].append(target)
        entry["sources"].append(source)
        entry["applies_to"] += [a for a in applies_to if a not in entry["applies_to"]]
        if evidence:
            entry["evidence"][target] = evidence

    for r in checks:
        check = by_id[r.id]
        if r.status == "error" or not (r.flagged > 0 or check.always_convention):
            continue
        evidence = {"flagged": r.flagged, "total": r.total, "pct": r.pct, **r.extra}
        if check.group:
            extend(group_entry(check.group), check.target, r.id, r.applies_to, evidence)
        elif check.convention:
            entries.append({"id": r.id, "rule": check.convention, "targets": [], "applies_to": r.applies_to,
                            "sources": [r.id], "evidence": {r.id: evidence}})
    for d_id, d in dists.items():
        if d["convention"]:
            entries.append({"id": d_id, "rule": d["convention"], "targets": [],
                            "applies_to": [f"{d['table']}.{d['column']}"], "sources": [d_id], "evidence": {}})
    for table, cols in sorted(padded.items()):
        for col, n in cols.items():
            extend(group_entry("padded_text"), f"{table}.{col}", f"padded_text.{table}.{col}",
                   [f"{table}.{col}"], {"values_with_spaces": n})
    for table, info in sorted(miss.items()):
        for col, pct in info["columns"].items():
            if pct == 100.0 and info["rows"]:
                extend(group_entry("all_null"), f"{table}.{col}", f"missing.{table}.{col}",
                       [f"{table}.{col}"], {"rows": info["rows"]})
    for group, entry in groups.items():
        entry["rule"] = GROUP_RULES[group].format(targets=", ".join(entry["targets"]))
    return entries


def run_quality(db_path: Path, progress=print) -> QualityReport:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        schema, types = read_schema(con)
        built = build_checks(schema)
        progress(f"Running {len(built)} checks on {len(schema)} tables ...")
        results = []
        for i, check in enumerate(built, 1):
            r = run_check(con, check)
            results.append(r)
            if r.status in ("flag", "error") or r.seconds > 30:  # Keep the console short
                progress(f"[{i:3d}/{len(built)}] {r.status.upper():5s} {r.id}: {r.flagged:,}/{r.total:,} "
                         f"({r.seconds}s)" + (f" - {r.error}" if r.error else ""))
            elif i % 25 == 0:
                progress(f"[{i:3d}/{len(built)}] ...")
        progress("Measuring missing values, padded text values and value distributions ...")
        miss = missingness(con, schema)
        padded = padded_text(con, types)
        dists = distributions(con, schema)
    finally:
        con.close()
    return QualityReport(results, miss, padded, dists, derive_conventions(results, built, dists, miss, padded))


# ----------------------------------------------------------------------
# Markdown report
# ----------------------------------------------------------------------
_TITLES = {
    "keys": ("Keys and duplicates", "Is each identifier unique where it should be, and are there repeated rows?"),
    "integrity": ("Referential integrity", "Does every key in an event table exist in its parent or dictionary table?"),
    "temporal": ("Temporal consistency", "Do end times follow start times, and do events fall inside their admission?"),
    "quirk": ("MIMIC-III conventions and coverage", "Documented MIMIC-III behaviours and gaps in this copy of the data."),
}
_STATUS = ("**pass**: expected zero and found zero. **flag**: expected zero, found some. "
           "**info**: a measured count with no single correct value.")


def _fmt(value, suppress: bool) -> str:
    """Count for display; with suppress, 1-10 become '<11' (see snapshot.py)."""
    from pneuma_seeker.services.core.data_prep.snapshot import SUPPRESSED, is_small
    if suppress and is_small(value):
        return SUPPRESSED
    return f"{value:,}" if isinstance(value, int) else str(value)


def _pct(flagged, pct, suppress: bool) -> str:
    from pneuma_seeker.services.core.data_prep.snapshot import is_small
    return "" if suppress and is_small(flagged) else f"{pct:g}"


def _evidence(entry: dict, suppress: bool = False) -> str:
    """Per-target counts for the markdown list, e.g. 'prescriptions (enddate < startdate) 15,922 of 4,150,832 (0.384%)'."""
    parts = []
    for target, ev in entry["evidence"].items():
        label = f"{target} " if entry["targets"] else ""
        if "flagged" in ev and ev.get("total"):
            pct = _pct(ev["flagged"], ev["pct"], suppress)
            parts.append(f"{label}{_fmt(ev['flagged'], suppress)} of {_fmt(ev['total'], suppress)}"
                         + (f" ({pct}%)" if pct else ""))
        elif "values_with_spaces" in ev:
            parts.append(f"{label}{_fmt(ev['values_with_spaces'], suppress)} values")
    if not parts:
        return ""
    return "\n   *Evidence: " + "; ".join(parts) + ".*"


def format_markdown(report: QualityReport, header: list[str] | None = None, suppress_small: bool = False) -> str:
    """
    Readable report. snapshot.py calls it for the shared, committed copy with a
    fingerprint header and suppress_small=True (counts 1-10 shown as '<11').
    """
    sup = suppress_small
    s = report.summary()
    lines = ["# MIMIC-III v1.4 data quality report", ""]
    if header:
        lines += header + [""]
    lines += ["MIMIC-III v1.4 is a de-identified database of patients admitted to intensive care units at Beth "
              "Israel Deaconess Medical Center, Boston (2001-2012). This report checks the copy loaded for this "
              "project for data problems that can make a database query give a wrong answer.", "",
              "The data were **not modified**. Instead, each problem found is turned into a **query convention**: "
              "a plain-language rule for writing queries (SQL) that avoid the problem, listed in the last "
              "section and in `mimic3_query_conventions.json`. The report contains aggregate counts only, never "
              "information about individual patients. Produced by `python scripts/prepare_mimic3.py publish`.", "",
              f"Checks: {len(report.checks)} (pass {s.get('pass', 0)}, flagged {s.get('flag', 0)}, "
              f"informational {s.get('info', 0)}, errors {s.get('error', 0)}). {_STATUS}", ""]
    for category, (title, question) in _TITLES.items():
        rows = [c for c in report.checks if c.category == category]
        if not rows:
            continue
        lines += [f"## {title}", "", question, "",
                  "| Check | Status | Flagged | Total | % | Details |", "|---|---|---:|---:|---:|---|"]
        for c in rows:
            details = ", ".join(f"{k}={_fmt(v, sup)}" for k, v in c.extra.items()) or (c.error or "")
            lines.append(f"| {c.description} | {c.status} | {_fmt(c.flagged, sup)} | {_fmt(c.total, sup)} | "
                         f"{_pct(c.flagged, c.pct, sup)} | {details} |")
        lines.append("")
    lines += ["## Missing values", "", "Share of null values, for columns with any.", "",
              "| Table | Column | % null |", "|---|---|---:|"]
    for table, info in sorted(report.missingness.items()):
        nulls = info.get("null_counts", {})
        for col, pct in sorted(info["columns"].items(), key=lambda kv: -kv[1]):
            if pct <= 0:
                continue
            n = nulls.get(col)
            if sup and n is not None and _fmt(n, True) != _fmt(n, False):
                shown = f"{_fmt(n, True)} rows"
            elif sup and n is not None and _fmt(info["rows"] - n, True) != _fmt(info["rows"] - n, False):
                shown = f"all but {_fmt(info['rows'] - n, True)} rows"
            else:
                shown = f"{pct:g}"
            lines.append(f"| {table} | {col} | {shown} |")
    lines += ["", "## Padded text values", "",
              "Text values with leading or trailing spaces (an exact match on them fails).", "",
              "| Table | Column | Values with spaces |", "|---|---|---:|"]
    for table, cols in sorted(report.padded_text.items()):
        for col, n in cols.items():
            lines.append(f"| {table} | {col} | {_fmt(n, sup)} |")
    lines += ["", "## Value distributions of coded columns", "",
              "Values are quoted so that padding is visible.", ""]
    for d in report.distributions.values():
        values = ", ".join((f"`{k}`" if k == "(null)" else f"`'{k}'`") + f" ({_fmt(v, sup)})"
                           for k, v in d["values"].items())
        lines.append(f"- **{d['table']}.{d['column']}**: {values}{' ...' if d['truncated'] else ''}")
    lines += ["", "## Derived query conventions", "",
              "Rules the system follows when writing SQL over this dataset.", ""]
    for i, c in enumerate(report.conventions, 1):
        lines.append(f"{i}. {c['rule']}{_evidence(c, sup)}")
    return "\n".join(lines) + "\n"


def format_console(report: QualityReport) -> str:
    s = report.summary()
    lines = [f"Checks: {len(report.checks)} | pass {s.get('pass', 0)} | flagged {s.get('flag', 0)} | "
             f"info {s.get('info', 0)} | errors {s.get('error', 0)}"]
    for c in report.checks:
        if c.status in ("flag", "error"):
            lines.append(f"  {c.status.upper():5s} {c.description}: {c.flagged:,} of {c.total:,} ({c.pct:g}%)"
                         + (f" - {c.error}" if c.error else ""))
    if report.padded_text:
        cols = sum(len(v) for v in report.padded_text.values())
        lines.append(f"Padded text values: {cols} column(s) in {len(report.padded_text)} table(s)")
    lines.append(f"Query conventions derived: {len(report.conventions)}")
    return "\n".join(lines)
