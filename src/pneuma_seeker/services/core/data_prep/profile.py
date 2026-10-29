"""
Schema profile of the loaded "mimic_iii" dataset: what is in each table and column.

What: for every table, its description, size, key and kind (core, event,
dictionary); for every column, its type, role (identifier, reference, code,
time, flag, category, number, text, ...), description, share of missing
values, approximate number of distinct values, the common values of category
columns, which other table it links to, and which query conventions apply to
it. Plus the links between tables, with how many rows actually match.

Why: this is the knowledge the query system searches when it maps a question
to tables and columns ("which column holds in-hospital death?", "how do I get
from a diagnosis to a patient?"). Combining the written descriptions with
measured facts tells it not only what a column means but how it behaves in
this copy of the data (e.g. 'drg_type' values include 'APR ' with a space).

Inputs: the dataset DB (read-only), the data quality results (for link match
rates and conventions) and mimic3_docs.py (descriptions). Outputs contain
aggregate counts and category vocabularies only, never values about individual
patients; the shared copy (see snapshot.py) also drops category values seen in
fewer than 11 rows and hides counts from 1 to 10.
"""
from pathlib import Path

import duckdb

from pneuma_seeker.services.core.data_prep.mimic3_docs import MIMIC_III_TABLE_DOCS
from pneuma_seeker.services.core.data_prep.quality import read_schema
from pneuma_seeker.services.core.data_prep.quality_checks import GENERIC_FKS, PRIMARY_KEYS, SPECIFIC_FKS

DESCRIPTION = (
    "What: describes every table and column (meaning, type, role, missing values, common values, links to\n"
    "      other tables, applicable query conventions), combining the written documentation with measured facts.\n"
    "Why:  this is what the query system searches to map a question to the right tables, columns and joins."
)

CORE_TABLES = ("patients", "admissions", "icustays")
CODE_COLUMNS = {"icd9_code", "cpt_cd", "cpt_number", "drg_code", "ndc", "gsn", "loinc_code", "formulary_drug_cd"}
CATEGORY_MAX_DISTINCT = 60  # Text columns with at most this many distinct values are categories
CODED_NUMBER_MAX_DISTINCT = 10  # Integer columns with at most this many distinct values are categories
TOP_VALUES = 40

ROLE_MEANING = {
    "row_number": "Row number within the table; not an identifier, never join on it",
    "identifier": "Identifies one record of this table (its key)",
    "reference": "Points to a record in another table (see 'references')",
    "code": "A code from a coding system (ICD-9, CPT, DRG, NDC, ...), stored as text",
    "local_identifier": "An identifier with no table of its own in this dataset (e.g. ward, order)",
    "time": "Date or date-time (shifted into the future per patient; intervals are real)",
    "flag": "Yes/no indicator (usually 0/1)",
    "category": "One of a small set of values (listed under 'values')",
    "number": "A measured or counted quantity",
    "text": "Free or semi-free text; match with patterns (ILIKE), not exact values",
    "always_null": "Always empty in this dataset; do not filter or group on it",
}


def references(schema: dict[str, list[str]]) -> dict[tuple[str, str], dict]:
    """(table, column) -> {"table", "column", "kind"} for every documented key link present in the DB."""
    out = {}
    for table, cols in schema.items():
        for col, (parent, pcol) in GENERIC_FKS.items():
            if col in cols and table != parent and parent in schema:
                out[(table, col)] = {"table": parent, "column": pcol, "kind": "key"}
    for child, col, parent, pcol in SPECIFIC_FKS:
        if child in schema and parent in schema and col in schema[child]:
            out[(child, col)] = {"table": parent, "column": pcol, "kind": "dictionary"}
    return out


def _role(table: str, col: str, dtype: str, distinct: int, keys: dict, refs: dict,
          rows: int = 0, null_rows: int | None = None) -> str:
    if col == "row_id":
        return "row_number"
    if col in keys.get(table, ()):
        return "identifier"
    if col in CODE_COLUMNS:
        return "code"
    if (table, col) in refs:
        return "reference"
    if rows and null_rows == rows:
        return "always_null"
    if dtype == "TIMESTAMP":
        return "time"
    if dtype in ("INTEGER", "SMALLINT", "BIGINT"):
        if col.endswith("id"):
            return "local_identifier"
        if distinct <= 2:
            return "flag"
        return "category" if distinct <= CODED_NUMBER_MAX_DISTINCT else "number"
    if dtype == "VARCHAR":
        return "category" if distinct <= CATEGORY_MAX_DISTINCT else "text"
    return "number"


def _convention_index(conventions: list[dict]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for entry in conventions:
        for target in entry.get("applies_to", []):
            index.setdefault(target, [])
            if entry["id"] not in index[target]:
                index[target].append(entry["id"])
    return index


def _link_results(quality: dict) -> dict[str, dict]:
    """'child.col->parent' -> integrity check result, from the quality results."""
    out = {}
    for check in quality.get("checks", []):
        if check["category"] == "integrity" and "->" in check["id"]:
            out[check["id"].removeprefix("integrity.")] = check
    return out


def build_profile(db_path: Path, quality: dict) -> dict:
    """quality: QualityReport.to_dict() of the same DB (for link match rates and conventions)."""
    keys = {t: cols for t, cols in PRIMARY_KEYS}
    conv_index = _convention_index(quality.get("conventions", []))
    missing = quality.get("missingness", {})
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        schema, types = read_schema(con)
        refs = references(schema)
        tables = {}
        for table in sorted(schema):
            cols = schema[table]
            approx = ", ".join(f'approx_count_distinct("{c}")' for c in cols)
            counts = con.execute(f'SELECT COUNT(*), {approx} FROM "{table}"').fetchone()
            rows, distinct = counts[0], dict(zip(cols, counts[1:]))
            doc_table, doc_cols = MIMIC_III_TABLE_DOCS.get(table, ("", {}))
            miss = missing.get(table, {})
            columns = {}
            for col in cols:
                role = _role(table, col, types[table][col], distinct[col], keys, refs,
                             rows, miss.get("null_counts", {}).get(col))
                entry = {
                    "type": types[table][col],
                    "role": role,
                    "description": doc_cols.get(col, ""),
                    "missing_pct": miss.get("columns", {}).get(col),
                    "null_rows": miss.get("null_counts", {}).get(col),
                    "distinct_values_approx": distinct[col],
                }
                if (table, col) in refs:
                    entry["references"] = f"{refs[(table, col)]['table']}.{refs[(table, col)]['column']}"
                if role in ("category", "flag") and rows:
                    values = con.execute(
                        f'SELECT CAST("{col}" AS VARCHAR), COUNT(*) FROM "{table}" WHERE "{col}" IS NOT NULL '
                        f"GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT {TOP_VALUES + 1}").fetchall()
                    entry["values"] = dict(values[:TOP_VALUES])
                    entry["values_truncated"] = len(values) > TOP_VALUES
                rules = conv_index.get(f"{table}.{col}", [])
                if rules:
                    entry["conventions"] = rules
                columns[col] = entry
            tables[table] = {
                "description": doc_table,
                "kind": "dictionary" if table.startswith("d_") or table == "caregivers"
                        else "core" if table in CORE_TABLES else "event",
                "rows": rows,
                "key": list(keys.get(table, ())),
                "table_conventions": conv_index.get(f"{table}.*", []),
                "columns": columns,
            }
    finally:
        con.close()

    link_results = _link_results(quality)
    links = []
    for (child, col), ref in sorted(refs.items()):
        check = link_results.get(f"{child}.{col}->{ref['table']}", {})
        links.append({
            "from": f"{child}.{col}", "to": f"{ref['table']}.{ref['column']}", "kind": ref["kind"],
            "evidence": "documented MIMIC-III link" + (", checked against the data" if check else ""),
            "rows_checked": check.get("total"), "unmatched_rows": check.get("flagged"),
            "unmatched_pct": check.get("pct"), "rows_without_key": check.get("extra", {}).get("null_keys"),
        })
    return {
        "role_meanings": ROLE_MEANING,
        "key_hierarchy": "subject_id (patient) > hadm_id (hospital admission) > icustay_id (ICU stay): each ICU stay "
                         "belongs to one admission and each admission to one patient. Join on the most specific "
                         "identifier both tables share.",
        "tables": tables,
        "links": links,
    }


# ----------------------------------------------------------------------
# Small-count suppression for the shared copy
# ----------------------------------------------------------------------
def suppress_profile(profile: dict) -> dict:
    """Shared copy: counts 1-10 -> '<11'; category values seen in fewer than 11 rows are dropped."""
    import copy

    from pneuma_seeker.services.core.data_prep.snapshot import SUPPRESSED, is_small

    out = copy.deepcopy(profile)
    for info in out["tables"].values():
        if is_small(info["rows"]):
            info["rows"] = SUPPRESSED
        for col in info["columns"].values():
            nulls = col.pop("null_rows", None)
            if isinstance(nulls, int):
                total = info["rows"] if isinstance(info["rows"], int) else None
                if is_small(nulls) or (total is not None and is_small(total - nulls)):
                    col["missing_pct"] = None
                    col["missing_note"] = (f"{SUPPRESSED} rows missing" if is_small(nulls)
                                           else f"all but {SUPPRESSED} rows missing")
            if "values" in col:
                kept = {v: n for v, n in col["values"].items() if not is_small(n)}
                omitted = len(col["values"]) - len(kept)
                col["values"] = kept
                if omitted:
                    col["rare_values_omitted"] = omitted
    for link in out["links"]:
        for key in ("unmatched_rows", "rows_without_key", "rows_checked"):
            if is_small(link.get(key)):
                link[key] = SUPPRESSED
        if link.get("unmatched_rows") == SUPPRESSED:
            link["unmatched_pct"] = None
    return out


# ----------------------------------------------------------------------
# Readable version
# ----------------------------------------------------------------------
def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value).replace("|", "\\|")


def format_profile_markdown(profile: dict, header: list[str] | None = None) -> str:
    lines = ["# MIMIC-III v1.4 schema profile", ""]
    if header:
        lines += header + [""]
    lines += [
        "What each table and column of the loaded MIMIC-III data contains: written descriptions from the "
        "MIMIC-III documentation combined with facts measured on this copy of the data. The query system "
        "uses this to find the right tables, columns and links for a question. Rule names (e.g. "
        "`group.padded_text`) are the `id`s of the rules in `mimic3_query_conventions.json`.", "",
        f"**Identifiers.** {profile['key_hierarchy']}", "",
        "**Column roles.** " + "; ".join(f"*{r}*: {m}" for r, m in profile["role_meanings"].items()) + ".", "",
    ]
    for table, info in profile["tables"].items():
        key = ", ".join(info["key"]) or "none (row_id is only a row number)"
        lines += [f"## {table}", "", f"{info['description']}", "",
                  f"Kind: {info['kind']}. Rows: {_cell(info['rows'])}. Key: {key}."
                  + (f" Rules for the whole table: {', '.join(info['table_conventions'])}."
                     if info["table_conventions"] else ""), "",
                  "| Column | Type | Role | Missing % | Distinct (approx.) | Links to | Description |",
                  "|---|---|---|---:|---:|---|---|"]
        for col, c in info["columns"].items():
            missing = c.get("missing_note") or _cell(c.get("missing_pct"))
            lines.append(f"| {col} | {c['type']} | {c['role']} | {missing} | {_cell(c['distinct_values_approx'])} | "
                         f"{c.get('references', '')} | {_cell(c['description'])} |")
        notes = []
        for col, c in info["columns"].items():
            if c.get("values"):
                shown = ", ".join(f"`'{v}'`" for v in list(c["values"])[:15])
                more = len(c["values"]) > 15 or c.get("values_truncated") or c.get("rare_values_omitted")
                notes.append(f"- **{col}** values: {shown}{' ...' if more else ''}")
            if c.get("conventions"):
                notes.append(f"- **{col}** rules: {', '.join(c['conventions'])}")
        if notes:
            lines += [""] + notes
        lines.append("")
    lines += ["## Links between tables", "",
              "Documented links (joins), with how many rows were checked and how many found no match.", "",
              "| From | To | Kind | Rows checked | Unmatched | Unmatched % | Rows without the key |",
              "|---|---|---|---:|---:|---:|---:|"]
    for link in profile["links"]:
        lines.append(f"| {link['from']} | {link['to']} | {link['kind']} | {_cell(link['rows_checked'])} | "
                     f"{_cell(link['unmatched_rows'])} | {_cell(link['unmatched_pct'])} | "
                     f"{_cell(link['rows_without_key'])} |")
    return "\n".join(lines) + "\n"
