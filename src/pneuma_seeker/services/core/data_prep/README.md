# Data preparation package (`data_prep`)

This package turns a dataset delivered as CSV files into a typed local database, measures its data
problems, and describes every table and column, so that the query system can answer questions over it
reliably. It is currently set up for **MIMIC-III v1.4**; this guide explains how it is built and how to set
it up for another dataset.

- **Using it for MIMIC-III** (setup, commands, what the results mean): see
  [`docs/mimic3/README.md`](../../../../../docs/mimic3/README.md).
- **This file**: how the package is structured, what "the schema" is made of, how the MIMIC-III version
  was created, how to set up a new dataset, and the output formats for developers.

## How it works

```
CSV files ──inventory──> checked file list ──load──> DuckDB database ──quality──> findings + query conventions
                                                            │                               │
                                                            └────────────profile────────────┘
                                                                          │
                                                    publish ──> shared copy (docs/<dataset>/)
```

| Stage | Module | Reads | Writes |
|---|---|---|---|
| inventory | `inventory.py` | file names and header lines | which tables are present and whether headers match |
| load | `loader.py` | the CSV files | the DuckDB database and `metadata.csv` |
| quality | `quality.py`, `quality_checks.py` | the database (read-only) | findings and query conventions |
| profile | `profile.py` | the database (read-only) and the quality results | the schema profile |
| publish | `snapshot.py` | the quality results and the profile | the shared, committed copy |

`scripts/prepare_mimic3.py` runs the stages; `paths.py` holds every input and output location.

## What "the schema" is made of

The pipeline needs four kinds of knowledge about a dataset. Only the first two must be written for a new
dataset; the third is configured; the fourth is measured.

| Layer | What it says | Where (MIMIC-III) | Written or measured |
|---|---|---|---|
| 1. Structure | Tables, columns in file order, column types, published row counts | `mimic3_schema.py` | Written, then verified by `inventory` and `load` |
| 2. Meaning | A one-line description of each table and of each column | `mimic3_docs.py` | Written |
| 3. Relationships and rules | Keys, links between tables, time columns, coded columns, dataset-specific checks | `quality_checks.py`, `profile.py` (constants at the top) | Written as configuration, then checked against the data |
| 4. Facts | Row counts, missing values, distinct values, category values, link match rates, rule evidence | produced by `quality` and `profile` | Measured |

### Layer 1: structure (`mimic3_schema.py`)

Each table is a `TableSpec`:

```python
@dataclass(frozen=True)
class TableSpec:
    name: str                               # upper case, as in the file name: ADMISSIONS -> ADMISSIONS.csv
    columns: tuple[tuple[str, str], ...]    # (header name, DuckDB type), in the file's column order
    official_rows: int | None               # published row count; None if the dataset publishes none
```

The file writes them compactly with `_spec(name, rows, "COLUMN:TYPE COLUMN:TYPE ...")`, for example:

```python
_spec("DIAGNOSES_ICD", 651_047,
      f"ROW_ID:{I} SUBJECT_ID:{I} HADM_ID:{I} SEQ_NUM:{I} ICD9_CODE:{V}"),
```

with `I, S, D, T, V` = `INTEGER, SMALLINT, DOUBLE, TIMESTAMP, VARCHAR`. It also defines:

- `TABLES`: all tables of the dataset (name -> spec).
- `TEAM_TABLES`: the tables expected in the team's copy. A missing team table is reported as **MISSING**; a
  missing table outside this list as **absent (known)**.

Rules for choosing types: identifiers and counts are `INTEGER`; measurements are `DOUBLE`; dates and times
are `TIMESTAMP`; **codes are always `VARCHAR`**, even when they look numeric, because leading zeros matter;
free text is `VARCHAR`.

### Layer 2: meaning (`mimic3_docs.py`)

One dictionary, `MIMIC_III_TABLE_DOCS`:

```python
MIMIC_III_TABLE_DOCS = {
    "diagnoses_icd": (
        "Hospital-assigned ICD-9 diagnosis codes for each admission, ...",   # table description
        {"row_id": "...", "subject_id": "Patient identifier (PATIENTS)",     # one entry per column
         "seq_num": "Priority of the diagnosis within the admission; 1 = primary diagnosis", ...},
    ),
    ...
}
```

Table and column names are lower case. Every column in layer 1 must have an entry (a test checks this).
The table descriptions also go into `metadata.csv` next to the database.

### Layer 3: relationships and rules (`quality_checks.py`, `profile.py`)

Constants at the top of the two modules; every check built from them is skipped automatically when a
table or column is not loaded.

| Constant | Module | What to list |
|---|---|---|
| `PRIMARY_KEYS` | quality_checks | each table's identifying column(s), checked for uniqueness |
| `NEAR_KEYS` | quality_checks | column combinations that should rarely repeat (repeats double-count) |
| `GENERIC_FKS` | quality_checks | key columns shared across tables -> the table that defines them (e.g. `hadm_id -> admissions.hadm_id`) |
| `SPECIFIC_FKS` | quality_checks | other links, e.g. code columns -> their dictionary table |
| `ORDERED_TIMES` | quality_checks | (table, start, end) pairs where end must not precede start |
| `EVENT_TIMES` | quality_checks | event time columns that should fall inside their admission |
| `LINKSTO` | quality_checks | MIMIC-specific: item tables and the `d_items.linksto` value they should have |
| `DISTRIBUTIONS` | quality_checks | coded columns whose value counts go into the report |
| `temporal_checks()`, `quirk_checks()` | quality_checks | hand-written checks for documented behaviours of the dataset |
| `GROUP_RULES` | quality_checks | the wording of rules shared by several checks of the same kind |
| `CORE_TABLES`, `CODE_COLUMNS` | profile | the main entity tables; columns that hold codes |
| `key_hierarchy` text | profile (`build_profile`) | how the identifiers nest (patient > admission > ICU stay) |

Conventions the code assumes: tables whose names start with `d_` (and `caregivers`) are dictionaries; a
column named `row_id` is a row number, not an identifier.

**Writing a check.** A `Check` is one SQL query that returns a single row of counts, never row values:

```python
Check(
    id="temporal.admissions.dischtime_before_admittime",   # unique, "<category>.<table>.<what>"
    category="temporal",                                   # keys | integrity | temporal | quirk
    description="admissions: dischtime earlier than admittime",
    tables=("admissions",),                                # skipped unless all are loaded
    sql="SELECT COUNT(*) FILTER (WHERE dischtime < admittime) AS flagged, "
        "COUNT(*) AS total, ... AS within_24h FROM admissions",   # flagged, total, then any extra counts
    expect_zero=True,          # True: any flagged row is a finding; False: a count to report
    convention="...",          # the rule to follow when flagged > 0 (or set group= to share a GROUP_RULES rule)
    applies_to=("admissions.admittime", "admissions.dischtime"),
)
```

Privacy rule for every new check: return counts only (`COUNT`, `SUM` of conditions); never select,
group by or print identifiers, dates or free text from patient tables.

## How the MIMIC-III version was created

- **Structure (`mimic3_schema.py`)**: written from the official MIMIC-III v1.4 table definitions (MIT-LCP
  `mimic-code`, `mimic-iii/buildmimic/postgres/postgres_create_tables.sql`), from knowledge of that file
  rather than a fresh download, translated to DuckDB types; row counts from the MIMIC-III v1.4
  documentation. **Verified** on the team's copy: for all 21 team tables, every header matched (inventory)
  and every row count matched exactly with no unreadable rows (load). The specs of the 5 tables not in the
  team's copy (CHARTEVENTS, INPUTEVENTS_MV, LABEVENTS, NOTEEVENTS, OUTPUTEVENTS) are not verified yet; the
  inventory will report any mismatch when those files are added.
- **Meaning (`mimic3_docs.py`)**: written by a team member for the query system by paraphrasing the public
  MIMIC-III documentation (https://mimic.mit.edu/docs/iii/tables/), and copied here unchanged so that
  there is one copy; it covers every column of every table.
- **Relationships and rules**: the documented MIMIC-III identifiers and links, then refined with what the
  checks found on the data (e.g. the padded `'APR '` value, CareVue/MetaVision crossovers). Three rules
  rest on the MIMIC-III documentation rather than on measurements and should be confirmed against it before
  being cited: rows with `statusdescription = 'Rewritten'` are superseded; the median true age of patients
  shown as over 89 is 91.4; a null `org_name` means no organism grew.

## Setting up a new dataset

The package is not yet dataset-independent: MIMIC-III names (`mimic3_*` files, `MIMIC_III_DIR`,
`mimic_iii`) are wired into a few places. Setting up another dataset means adding its own versions of the
dataset-specific pieces, as below. A natural next improvement is to gather all of them into one dataset
definition object.

1. **Prepare the files.** One CSV file per table, named `TABLE.csv` or `TABLE.csv.gz`, with a header row,
   comma separators and double-quoted text.
2. **Write layer 1** (`<dataset>_schema.py`, same format as `mimic3_schema.py`). Take columns, order and
   types from the dataset's official definitions (SQL `CREATE TABLE` scripts or data dictionary). If there
   are none, list each file's columns and DuckDB's guessed types, then review every guess by hand (codes and
   identifiers with leading zeros must become `VARCHAR`). This prints names and types only, no values:
   ```
   python -c "import duckdb, sys; print(duckdb.sql(f\"DESCRIBE SELECT * FROM read_csv_auto('{sys.argv[1]}')\"))" /path/to/TABLE.csv
   ```
   Use published row counts if they exist; otherwise `None`.
3. **Write layer 2** (`<dataset>_docs.py`): a description for every table and column, from the dataset's
   documentation.
4. **Configure layer 3**: fill the constants listed above for the new tables (keys, links, time pairs,
   event times, coded columns, distributions) and write `Check`s for behaviours documented for the dataset.
   Remove or skip the MIMIC-III-specific ones (`LINKSTO`, `quirk_checks()`, the admissions/patients/ICU
   parts of `temporal_checks()`).
5. **Set paths** (`paths.py`): dataset name (the database becomes `datasets/<name>/<name>.db`), the
   environment variable holding the source folder, report and snapshot file names and folder.
6. **Add a run script** (a copy of `scripts/prepare_mimic3.py` pointing at the new modules).
7. **Add tests** with a small synthetic database (see `tests/services/core/data_prep/synthetic_mimic3.py`),
   including the check that every column has a description.
8. **Run** `inventory`, fix every header mismatch, then `load` (every table should be `ok`), `quality`,
   `profile`, and `publish`. Review the derived rules before sharing them.

## Output formats (for developers of the query system)

All shared files carry `report`, `about`, `maintenance`, `small_count_rule` and `data_fingerprint`
(`{"id": "<12-character hash>", "row_counts": {table: rows}}`).

**`mimic3_query_conventions.json`** -> `conventions`: a list of rules.

```json
{"id": "group.negative_duration",
 "rule": "Some end times precede their start times: admissions (dischtime < admittime), ... Exclude those rows when computing durations ...",
 "targets": ["admissions (dischtime < admittime)", "prescriptions (enddate < startdate)"],
 "applies_to": ["admissions.admittime", "admissions.dischtime", "prescriptions.startdate", "..."],
 "sources": ["temporal.admissions.dischtime_before_admittime", "..."],
 "evidence": {"admissions (dischtime < admittime)": {"flagged": 98, "total": 58976, "pct": 0.166, "within_24h": 98}}}
```

Use `applies_to` (`table.column` or `table.*`) to select the rules relevant to the tables a question uses,
and pass `rule` to the language model.

**`mimic3_schema_profile.json`** -> `tables`, `links`, `role_meanings`, `key_hierarchy`.

```json
"tables": {"admissions": {
    "description": "One row per hospital admission: ...", "kind": "core", "rows": 58976, "key": ["hadm_id"],
    "table_conventions": [],
    "columns": {"admission_type": {
        "type": "VARCHAR", "role": "category", "description": "One of 'ELECTIVE', 'URGENT', ...",
        "missing_pct": 0.0, "distinct_values_approx": 4, "values": {"EMERGENCY": 42071, "NEWBORN": 7863, "ELECTIVE": 7706, "URGENT": 1336},
        "conventions": ["dist.admissions.admission_type"]}}}},
"links": [{"from": "diagnoses_icd.hadm_id", "to": "admissions.hadm_id", "kind": "key",
           "evidence": "documented MIMIC-III link, checked against the data",
           "rows_checked": 651047, "unmatched_rows": 0, "unmatched_pct": 0.0, "rows_without_key": 0}]
```

Roles: `row_number`, `identifier`, `reference` (see `references`), `code`, `local_identifier`, `time`,
`flag`, `category` (see `values`), `number`, `text`, `always_null`. In the shared copy, counts from 1 to 10
are the string `"<11"`, their percentages `null`, and category values seen in fewer than 11 rows are
omitted (`rare_values_omitted` gives how many).

**Checking that a user's data match the shared files:**

```python
from pneuma_seeker.services.core.data_prep.snapshot import compare_with_snapshot
result = compare_with_snapshot(db_path)     # status: "match" | "differs" | "no_snapshot"
if result.status != "match":
    logger.warning(result.message())        # lists the tables whose row counts differ
```

The database itself is opened as the `mimic_iii` dataset by the existing dataset manager (same location
and naming as any other dataset).
