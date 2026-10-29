"""
Shared, committed snapshot of the MIMIC-III data quality findings (docs/mimic3/).

What: the files that every user (and the query system) reads instead of their own
local reports:
    mimic3_query_conventions.json   the query conventions + the data fingerprint
    mimic3_data_quality_report.md   the readable data quality report
    mimic3_schema_profile.json      every table and column (see profile.py)
    mimic3_schema_profile.md        the readable schema profile

Why: one copy of the rules keeps the system's behaviour, and the numbers in
the paper, the same for everyone. Written by the dataset maintainer only
(`python scripts/prepare_mimic3.py publish`); others treat it as read-only.

How the content stays shareable and stable:
- Data fingerprint instead of a timestamp: the row count of every loaded table
  plus a short hash of them. The files change only when the data or the rules
  change, so `git diff` shows real changes only.
- Small-count suppression: any count from 1 to 10 is written as "<11" (and its
  percentage omitted), following the common "rule of 11" for health data.
  Zero is shown as 0. Complementary suppression is not applied.
- No file paths: nothing user-specific is written.

compare_with_snapshot() tells a teammate whether their local DB matches the
data the snapshot was made from; the pipeline prints a warning when it does
not, and the query system can call the same function.
"""
import copy
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from pneuma_seeker.services.core.data_prep import paths

SMALL_COUNT_LIMIT = 11  # counts 1 .. SMALL_COUNT_LIMIT-1 are suppressed
SUPPRESSED = f"<{SMALL_COUNT_LIMIT}"


# ----------------------------------------------------------------------
# Fingerprint
# ----------------------------------------------------------------------
def fingerprint(db_path: Path) -> dict:
    """{"id": short hash, "row_counts": {table: rows}} for the dataset DB."""
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        tables = sorted(name for (name,) in con.execute("SHOW TABLES").fetchall())
        counts = {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
    finally:
        con.close()
    return {"id": fingerprint_id(counts), "row_counts": counts}


def fingerprint_id(counts: dict[str, int]) -> str:
    return hashlib.sha256(json.dumps(counts, sort_keys=True).encode()).hexdigest()[:12]


@dataclass
class SnapshotComparison:
    status: str  # "match" | "differs" | "no_snapshot"
    snapshot_id: str | None = None
    local_id: str | None = None
    differences: list[str] = field(default_factory=list)

    def message(self) -> str:
        if self.status == "match":
            return f"Local data match the shared snapshot (fingerprint {self.local_id})."
        if self.status == "no_snapshot":
            return f"No shared snapshot found at {paths.repo_relative(paths.snapshot_path('conventions'))}."
        lines = [f"WARNING: your local MIMIC-III data differ from the shared snapshot "
                 f"(snapshot {self.snapshot_id}, local {self.local_id}).",
                 "The shared query conventions in docs/mimic3/ were derived from different data, so they may "
                 "not describe yours:"]
        lines += [f"  - {d}" for d in self.differences[:15]]
        if len(self.differences) > 15:
            lines.append(f"  - ... {len(self.differences) - 15} more")
        lines.append("Re-run `load` from the shared source, or ask the dataset maintainer which copy is current.")
        return "\n".join(lines)


def read_snapshot_fingerprint(snapshot_file: Path | None = None) -> dict | None:
    snapshot_file = snapshot_file or paths.snapshot_path("conventions")
    if not snapshot_file.exists():
        return None
    return json.loads(snapshot_file.read_text()).get("data_fingerprint")


def compare_with_snapshot(db_path: Path, snapshot_file: Path | None = None) -> SnapshotComparison:
    shared = read_snapshot_fingerprint(snapshot_file)
    if shared is None:
        return SnapshotComparison("no_snapshot")
    local = fingerprint(db_path)
    result = SnapshotComparison("match", shared["id"], local["id"])
    if shared["id"] == local["id"]:
        return result
    result.status = "differs"
    s, lc = shared["row_counts"], local["row_counts"]
    for table in sorted(set(s) | set(lc)):
        if table not in lc:
            result.differences.append(f"{table}: in the snapshot, not in your DB")
        elif table not in s:
            result.differences.append(f"{table}: in your DB, not in the snapshot")
        elif s[table] != lc[table]:
            result.differences.append(f"{table}: {_show(s[table])} rows in the snapshot, "
                                      f"{_show(lc[table])} in your DB")
    return result


# ----------------------------------------------------------------------
# Small-count suppression
# ----------------------------------------------------------------------
def is_small(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 < value < SMALL_COUNT_LIMIT


def _show(value) -> str:
    return SUPPRESSED if is_small(value) else f"{value:,}"


def suppress_evidence(evidence: dict) -> dict:
    """Counts 1-10 -> '<11'; the percentage is dropped when its count is suppressed."""
    out = {}
    for key, value in evidence.items():
        if key == "pct":
            continue
        out[key] = SUPPRESSED if is_small(value) else value
    if "pct" in evidence:
        out["pct"] = None if is_small(evidence.get("flagged")) else evidence["pct"]
    return out


def suppress_conventions(conventions: list[dict]) -> list[dict]:
    out = copy.deepcopy(conventions)
    for entry in out:
        entry["evidence"] = {target: suppress_evidence(ev) for target, ev in entry["evidence"].items()}
    return out


# ----------------------------------------------------------------------
# Writing
# ----------------------------------------------------------------------
def snapshot_header(fp: dict) -> list[str]:
    rows = ", ".join(f"{t} {_show(n)}" for t, n in fp["row_counts"].items())
    return [
        "> **Shared snapshot - do not edit by hand.** Regenerated only by the dataset maintainer with "
        "`python scripts/prepare_mimic3.py publish`; everyone else treats this file as read-only. "
        f"Counts from 1 to {SMALL_COUNT_LIMIT - 1} are shown as `{SUPPRESSED}`.",
        "",
        f"Data fingerprint `{fp['id']}` (rows per table: {rows}).",
    ]


def _payload(key: str, fp: dict, body: dict) -> dict:
    return {
        "report": paths.SNAPSHOT_FILES[key][0],
        "about": paths.SNAPSHOT_FILES[key][1],
        "maintenance": "Shared snapshot: regenerate only with `python scripts/prepare_mimic3.py publish` "
                       "(dataset maintainer); do not edit by hand.",
        "small_count_rule": f"Counts from 1 to {SMALL_COUNT_LIMIT - 1} are written as \"{SUPPRESSED}\" and "
                            f"their percentage as null; category values seen in fewer than {SMALL_COUNT_LIMIT} "
                            f"rows are omitted.",
        "data_fingerprint": fp,
        **body,
    }


def write_snapshot(report, fp: dict, out_dir: Path | None = None, profile: dict | None = None) -> dict[str, Path]:
    """Writes the shared files (conventions + quality report, and the schema profile if given)."""
    from pneuma_seeker.services.core.data_prep.profile import format_profile_markdown, suppress_profile
    from pneuma_seeker.services.core.data_prep.quality import format_markdown  # Avoid an import cycle

    out_dir = out_dir or paths.SNAPSHOT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {key: out_dir / name for key, (name, _) in paths.SNAPSHOT_FILES.items()}
    written["conventions"].write_text(json.dumps(
        _payload("conventions", fp, {"conventions": suppress_conventions(report.conventions)}), indent=2) + "\n")
    written["quality_md"].write_text(format_markdown(report, header=snapshot_header(fp), suppress_small=True))
    if profile is None:
        return {k: written[k] for k in ("conventions", "quality_md")}
    shared = suppress_profile(profile)
    written["profile_json"].write_text(json.dumps(_payload("profile_json", fp, shared), indent=2) + "\n")
    written["profile_md"].write_text(format_profile_markdown(shared, header=snapshot_header(fp)))
    return written
