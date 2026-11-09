"""
Data quality check definitions: what "clean" means for each MIMIC-III table.

Every check is one SQL query that returns a single row of aggregate counts:
    flagged, total [, extra named counts]
and never row values. Checks are built from the schema actually loaded, so a
table that is missing (e.g. LABEVENTS) is skipped, not an error.

Each check may carry a convention: a rule for how queries should treat the
issue (the query system passes these to the language model with the schema). Cleaning
here never edits the data: the evaluation SQL runs on the original schema.

Categories:
    keys         primary-key uniqueness and exact duplicate rows
    integrity    foreign keys and cross-table key consistency
    temporal     impossible or out-of-window times
    quirk        documented MIMIC-III conventions and coverage gaps
"""
from dataclasses import dataclass

Schema = dict[str, list[str]]  # table -> column names (lower case)


@dataclass(frozen=True)
class Check:
    id: str
    category: str
    description: str
    tables: tuple[str, ...]  # skipped unless all are loaded
    sql: str  # one row: flagged, total, [extra counts...]
    expect_zero: bool = True  # False: informational (a count to report, not an error)
    convention: str = ""  # emitted when flagged > 0 (or always, see below)
    always_convention: bool = False  # emit even when nothing is flagged (documented quirk)
    applies_to: tuple[str, ...] = ()  # "table.column" the convention is about
    group: str = ""  # Checks of the same kind share one rule (GROUP_RULES) listing every affected target
    target: str = ""  # How this check is named inside its group's rule, e.g. "prescriptions (enddate < startdate)"


# One rule per kind of finding; {targets} lists the affected tables/columns.
GROUP_RULES = {
    "pk_not_unique": "These identifiers are not unique: {targets}. Deduplicate before joining on them, "
                     "or the join multiplies rows.",
    "repeated_within_admission": "These combinations repeat within one admission: {targets}. Count DISTINCT "
                                 "admissions or codes, not rows.",
    "exact_duplicates": "These tables contain exact duplicate rows (all columns equal except row_id): {targets}. "
                        "Use COUNT(DISTINCT ...) or SELECT DISTINCT before counting or summing.",
    "orphan_keys": "Some keys have no matching parent row: {targets}. An INNER JOIN to the parent drops them.",
    "dictionary_gap": "Some codes have no entry in their dictionary table: {targets}. Use a LEFT JOIN to the "
                      "dictionary (an INNER JOIN drops those rows) and report unlabeled codes as such.",
    "icustay_hadm_mismatch": "For a few rows, the event's hadm_id differs from icustays.hadm_id of the same "
                             "icustay_id: {targets}. Never join these tables to icustays on both icustay_id and "
                             "hadm_id at once (those rows are dropped): join on icustay_id for ICU-stay "
                             "questions and on the event's own hadm_id for admission questions.",
    "linksto_mismatch": "Some event items are labeled for another table in d_items.linksto: {targets}. Look up "
                        "items by itemid, not by linksto.",
    "negative_duration": "Some end times precede their start times: {targets}. Exclude those rows when "
                         "computing durations or lengths of stay; keep them for counts.",
    "outside_admission": "Some events are timed slightly outside [admittime, dischtime] of their own admission, "
                         "mostly within 24 h (e.g. ED time before admission): {targets}. Link events to "
                         "admissions by hadm_id, not by time overlap (a time-window filter would drop them); "
                         "apply a time filter only when the question asks for one (e.g. 'first 24 hours').",
    "icd9_format": "ICD-9 codes are stored as text without the decimal point ('4019' is 401.9; E and V codes "
                   "keep their letter) in {targets}. Compare as strings; never cast to numbers.",
    "dbsource_crossover": "icustays.dbsource does not exactly partition the ICU event tables: {targets}. Find a "
                          "stay's events by querying the event table on icustay_id; never choose the table "
                          "from icustays.dbsource.",
    "padded_text": "Some text values have leading or trailing spaces, so an exact match fails (every APR row "
                   "has drg_type 'APR ', so drg_type = 'APR' finds nothing): {targets}. Compare with "
                   "trim(column) = 'value', or use LIKE / ILIKE patterns.",
    "all_null": "These columns are always null in this dataset: {targets}. Do not filter or group on them.",
}


@dataclass(frozen=True)
class Distribution:
    """Category counts for a low-cardinality coded column (value vocabulary, no free text)."""
    id: str
    table: str
    column: str
    description: str
    convention: str = ""


# ----------------------------------------------------------------------
# Keys
# ----------------------------------------------------------------------
PRIMARY_KEYS: list[tuple[str, tuple[str, ...]]] = [
    ("patients", ("subject_id",)),
    ("admissions", ("hadm_id",)),
    ("icustays", ("icustay_id",)),
    ("caregivers", ("cgid",)),
    ("d_items", ("itemid",)),
    ("d_labitems", ("itemid",)),
    ("d_icd_diagnoses", ("icd9_code",)),
    ("d_icd_procedures", ("icd9_code",)),
]

# Not declared keys, but a duplicate here double-counts in COUNT(*) questions
NEAR_KEYS: list[tuple[str, tuple[str, ...], str]] = [
    ("diagnoses_icd", ("hadm_id", "seq_num"), "Two diagnoses share a priority within one admission"),
    ("diagnoses_icd", ("hadm_id", "icd9_code"), "Same ICD-9 diagnosis coded twice in one admission"),
    ("procedures_icd", ("hadm_id", "seq_num"), "Two procedures share a priority within one admission"),
    ("procedures_icd", ("hadm_id", "icd9_code"), "Same ICD-9 procedure coded twice in one admission"),
    ("drgcodes", ("hadm_id", "drg_type"), "More than one DRG of the same type per admission"),
]


def _cols(cols: tuple[str, ...]) -> str:
    return ", ".join(f'"{c}"' for c in cols)


def key_checks(schema: Schema) -> list[Check]:
    checks = []
    for table in sorted(schema):
        if "row_id" in schema[table]:
            checks.append(Check(
                f"keys.{table}.row_id", "keys", f"{table}.row_id is unique", (table,),
                f'SELECT COUNT(*) - COUNT(DISTINCT row_id) AS flagged, COUNT(*) AS total FROM "{table}"'))
    for table, cols in PRIMARY_KEYS:
        if table in schema:
            name = ",".join(cols)
            checks.append(Check(
                f"keys.{table}.{name}", "keys", f"{table}.{name} is unique (primary key)", (table,),
                f'SELECT COUNT(*) - (SELECT COUNT(*) FROM (SELECT DISTINCT {_cols(cols)} FROM "{table}")) AS flagged, '
                f'COUNT(*) AS total, COUNT(*) FILTER (WHERE {" OR ".join(f"{c} IS NULL" for c in cols)}) AS null_keys '
                f'FROM "{table}"',
                group="pk_not_unique", target=f"{table}.{name}",
                applies_to=tuple(f"{table}.{c}" for c in cols)))
    for table, cols, why in NEAR_KEYS:
        if table in schema:
            name = ",".join(cols)
            checks.append(Check(
                f"keys.{table}.{name}", "keys", f"{why} ({table}: {name})", (table,),
                f'SELECT COUNT(*) - (SELECT COUNT(*) FROM (SELECT DISTINCT {_cols(cols)} FROM "{table}")) AS flagged, '
                f'COUNT(*) AS total FROM "{table}"',
                expect_zero=False, group="repeated_within_admission", target=f"{table} ({', '.join(cols)})",
                applies_to=tuple(f"{table}.{c}" for c in cols)))
    for table in sorted(schema):
        if table.startswith("d_") or table == "caregivers":
            continue
        others = [c for c in schema[table] if c != "row_id"]
        checks.append(Check(
            f"keys.{table}.exact_duplicates", "keys",
            f"{table}: rows identical to another row except row_id", (table,),
            f'SELECT (SELECT COUNT(*) FROM "{table}") - (SELECT COUNT(*) FROM (SELECT DISTINCT {_cols(tuple(others))} '
            f'FROM "{table}")) AS flagged, (SELECT COUNT(*) FROM "{table}") AS total',
            expect_zero=False, group="exact_duplicates", target=table,
            applies_to=(f"{table}.*",)))
    return checks


# ----------------------------------------------------------------------
# Referential integrity
# ----------------------------------------------------------------------
# column -> (parent table, parent column); applied to every other table that has the column
GENERIC_FKS = {
    "subject_id": ("patients", "subject_id"),
    "hadm_id": ("admissions", "hadm_id"),
    "icustay_id": ("icustays", "icustay_id"),
    "cgid": ("caregivers", "cgid"),
}
# (child, column, parent, parent column)
SPECIFIC_FKS = [
    ("datetimeevents", "itemid", "d_items", "itemid"),
    ("inputevents_cv", "itemid", "d_items", "itemid"),
    ("procedureevents_mv", "itemid", "d_items", "itemid"),
    ("chartevents", "itemid", "d_items", "itemid"),
    ("outputevents", "itemid", "d_items", "itemid"),
    ("inputevents_mv", "itemid", "d_items", "itemid"),
    ("labevents", "itemid", "d_labitems", "itemid"),
    ("microbiologyevents", "spec_itemid", "d_items", "itemid"),
    ("microbiologyevents", "org_itemid", "d_items", "itemid"),
    ("microbiologyevents", "ab_itemid", "d_items", "itemid"),
    ("diagnoses_icd", "icd9_code", "d_icd_diagnoses", "icd9_code"),
    ("procedures_icd", "icd9_code", "d_icd_procedures", "icd9_code"),
]
# event table -> d_items.linksto value its items should have
LINKSTO = {
    "datetimeevents": "datetimeevents", "inputevents_cv": "inputevents_cv",
    "procedureevents_mv": "procedureevents_mv", "chartevents": "chartevents",
    "outputevents": "outputevents", "inputevents_mv": "inputevents_mv",
}


def _fk_check(child: str, col: str, parent: str, pcol: str) -> Check:
    dictionary = parent.startswith("d_")
    return Check(
        f"integrity.{child}.{col}->{parent}", "integrity",
        f"{child}.{col} values found in {parent}.{pcol}", (child, parent),
        f'SELECT COUNT(*) FILTER (WHERE c."{col}" IS NOT NULL AND p.k IS NULL) AS flagged, '
        f'COUNT(c."{col}") AS total, '
        f'COUNT(*) FILTER (WHERE c."{col}" IS NULL) AS null_keys, '
        f'COUNT(DISTINCT c."{col}") FILTER (WHERE c."{col}" IS NOT NULL AND p.k IS NULL) AS distinct_unmatched '
        f'FROM "{child}" c LEFT JOIN (SELECT DISTINCT "{pcol}" AS k FROM "{parent}") p ON c."{col}" = p.k',
        expect_zero=not dictionary,  # Codes missing from a dictionary are a known MIMIC gap, not a load error
        group="dictionary_gap" if dictionary else "orphan_keys", target=f"{child}.{col} -> {parent}",
        applies_to=(f"{child}.{col}",))


def integrity_checks(schema: Schema) -> list[Check]:
    checks = []
    for table in sorted(schema):
        for col, (parent, pcol) in GENERIC_FKS.items():
            if col in schema[table] and table != parent and parent in schema:
                checks.append(_fk_check(table, col, parent, pcol))
    for child, col, parent, pcol in SPECIFIC_FKS:
        if child in schema and parent in schema and col in schema[child]:
            checks.append(_fk_check(child, col, parent, pcol))

    for table in sorted(schema):
        cols = schema[table]
        if table != "admissions" and {"hadm_id", "subject_id"} <= set(cols) and "admissions" in schema:
            checks.append(Check(
                f"integrity.{table}.hadm_subject_consistent", "integrity",
                f"{table}: subject_id agrees with admissions for the same hadm_id", (table, "admissions"),
                f'SELECT COUNT(*) FILTER (WHERE a.subject_id <> c.subject_id) AS flagged, COUNT(*) AS total '
                f'FROM "{table}" c JOIN admissions a ON c.hadm_id = a.hadm_id'))
        if table != "icustays" and {"icustay_id", "hadm_id"} <= set(cols) and "icustays" in schema:
            checks.append(Check(
                f"integrity.{table}.icustay_hadm_consistent", "integrity",
                f"{table}: hadm_id agrees with icustays for the same icustay_id", (table, "icustays"),
                f'SELECT COUNT(*) FILTER (WHERE i.hadm_id <> c.hadm_id) AS flagged, COUNT(*) AS total, '
                f'COUNT(*) FILTER (WHERE c.hadm_id IS NULL) AS event_hadm_null '
                f'FROM "{table}" c JOIN icustays i ON c.icustay_id = i.icustay_id',
                group="icustay_hadm_mismatch", target=table,
                applies_to=(f"{table}.icustay_id", f"{table}.hadm_id")))

    for table, linksto in LINKSTO.items():
        if table in schema and "d_items" in schema:
            checks.append(Check(
                f"integrity.{table}.itemid_linksto", "integrity",
                f"{table} items are labeled LINKSTO='{linksto}' in d_items", (table, "d_items"),
                f"SELECT COUNT(*) FILTER (WHERE lower(d.linksto) IS DISTINCT FROM '{linksto}') AS flagged, "
                f'COUNT(*) AS total FROM "{table}" c JOIN d_items d ON c.itemid = d.itemid',
                group="linksto_mismatch", target=table,
                applies_to=("d_items.linksto",)))
    return checks


# ----------------------------------------------------------------------
# Temporal consistency
# ----------------------------------------------------------------------
# (table, time column, granularity) for "event recorded during its admission"
EVENT_TIMES = [
    ("callout", "createtime", "ts"),
    ("cptevents", "chartdate", "date"),
    ("datetimeevents", "charttime", "ts"),
    ("inputevents_cv", "charttime", "ts"),
    ("microbiologyevents", "chartdate", "date"),
    ("prescriptions", "startdate", "date"),
    ("procedureevents_mv", "starttime", "ts"),
    ("services", "transfertime", "ts"),
    ("transfers", "intime", "ts"),
    ("labevents", "charttime", "ts"),
    ("chartevents", "charttime", "ts"),
]
# (table, start, end): end must not precede start
ORDERED_TIMES = [
    ("admissions", "admittime", "dischtime"),
    ("admissions", "edregtime", "edouttime"),
    ("icustays", "intime", "outtime"),
    ("transfers", "intime", "outtime"),
    ("prescriptions", "startdate", "enddate"),
    ("procedureevents_mv", "starttime", "endtime"),
    ("callout", "createtime", "outcometime"),
    ("patients", "dob", "dod"),
]


# Extra counts that help explain an ordering violation (what kind of rows are affected)
_ORDER_CONTEXT = {
    "admissions": ", COUNT(*) FILTER (WHERE \"{end}\" < \"{start}\" AND hospital_expire_flag = 1) AS died_in_hospital",
}


def _ordered(table: str, start: str, end: str) -> Check:
    context = _ORDER_CONTEXT.get(table, "").format(start=start, end=end)
    return Check(
        f"temporal.{table}.{end}_before_{start}", "temporal", f"{table}: {end} earlier than {start}", (table,),
        f'SELECT COUNT(*) FILTER (WHERE "{end}" < "{start}") AS flagged, '
        f'COUNT(*) FILTER (WHERE "{end}" IS NOT NULL AND "{start}" IS NOT NULL) AS total, '
        f'COUNT(*) FILTER (WHERE "{end}" < "{start}" AND "{start}" - "{end}" <= INTERVAL 1 DAY) AS within_24h'
        f'{context} FROM "{table}"',
        group="negative_duration", target=f"{table} ({end} < {start})",
        applies_to=(f"{table}.{start}", f"{table}.{end}"))


def _in_admission(table: str, col: str, granularity: str) -> Check:
    if granularity == "date":
        t, lo, hi = f'CAST(e."{col}" AS DATE)', "CAST(a.admittime AS DATE)", "CAST(a.dischtime AS DATE)"
        lo24, hi24 = f"{lo} - INTERVAL 1 DAY", f"{hi} + INTERVAL 1 DAY"
    else:
        t, lo, hi = f'e."{col}"', "a.admittime", "a.dischtime"
        lo24, hi24 = f"{lo} - INTERVAL 1 DAY", f"{hi} + INTERVAL 1 DAY"
    return Check(
        f"temporal.{table}.{col}_outside_admission", "temporal",
        f"{table}.{col} outside its admission [admittime, dischtime]" + (" (by date)" if granularity == "date" else ""),
        (table, "admissions"),
        f"SELECT COUNT(*) FILTER (WHERE {t} < {lo} OR {t} > {hi}) AS flagged, COUNT(*) AS total, "
        f"COUNT(*) FILTER (WHERE {t} < {lo24} OR {t} > {hi24}) AS beyond_24h "
        f'FROM "{table}" e JOIN admissions a ON e.hadm_id = a.hadm_id WHERE e."{col}" IS NOT NULL',
        expect_zero=False, group="outside_admission", target=f"{table}.{col}",
        applies_to=(f"{table}.{col}",))


def temporal_checks(schema: Schema) -> list[Check]:
    checks = [_ordered(t, s, e) for t, s, e in ORDERED_TIMES
              if t in schema and {s, e} <= set(schema[t])]
    checks += [_in_admission(t, c, g) for t, c, g in EVENT_TIMES
               if t in schema and "admissions" in schema and c in schema[t] and "hadm_id" in schema[t]]
    if "admissions" in schema:
        checks += [
            Check("temporal.admissions.deathtime_outside_stay", "temporal",
                  "admissions.deathtime outside [admittime, dischtime]", ("admissions",),
                  "SELECT COUNT(*) FILTER (WHERE deathtime < admittime OR deathtime > dischtime) AS flagged, "
                  "COUNT(deathtime) AS total, COUNT(*) FILTER (WHERE deathtime < admittime - INTERVAL 1 DAY "
                  "OR deathtime > dischtime + INTERVAL 1 DAY) AS beyond_24h FROM admissions",
                  expect_zero=False,
                  convention="Identify in-hospital death with admissions.hospital_expire_flag = 1, not by "
                             "testing deathtime against the admission window.",
                  applies_to=("admissions.deathtime", "admissions.hospital_expire_flag")),
            Check("temporal.admissions.expire_flag_vs_deathtime", "temporal",
                  "hospital_expire_flag disagrees with deathtime being recorded", ("admissions",),
                  "SELECT COUNT(*) FILTER (WHERE (hospital_expire_flag = 1) <> (deathtime IS NOT NULL)) AS flagged, "
                  "COUNT(*) AS total, "
                  "COUNT(*) FILTER (WHERE hospital_expire_flag = 1 AND deathtime IS NULL) AS flag_without_time, "
                  "COUNT(*) FILTER (WHERE hospital_expire_flag = 0 AND deathtime IS NOT NULL) AS time_without_flag "
                  "FROM admissions",
                  convention="hospital_expire_flag and deathtime disagree for some admissions: use "
                             "hospital_expire_flag as the definition of in-hospital death.",
                  applies_to=("admissions.hospital_expire_flag",)),
            Check("temporal.admissions.dead_location_vs_flag", "temporal",
                  "discharge_location 'DEAD/EXPIRED' disagrees with hospital_expire_flag", ("admissions",),
                  "SELECT COUNT(*) FILTER (WHERE (coalesce(discharge_location, '') = 'DEAD/EXPIRED') "
                  "<> (hospital_expire_flag = 1)) AS flagged, COUNT(*) AS total FROM admissions",
                  convention="discharge_location = 'DEAD/EXPIRED' and hospital_expire_flag disagree for some "
                             "admissions: use hospital_expire_flag.",
                  applies_to=("admissions.discharge_location",)),
        ]
    if "patients" in schema:
        checks.append(Check(
            "temporal.patients.expire_flag_vs_dod", "temporal",
            "patients.expire_flag disagrees with dod being recorded", ("patients",),
            "SELECT COUNT(*) FILTER (WHERE (expire_flag = 1) <> (dod IS NOT NULL)) AS flagged, COUNT(*) AS total "
            "FROM patients"))
    if "icustays" in schema:
        checks.append(Check(
            "temporal.icustays.los_matches_times", "temporal",
            "icustays.los differs from (outtime - intime) by more than 0.01 day", ("icustays",),
            "SELECT COUNT(*) FILTER (WHERE abs(los - date_diff('second', intime, outtime) / 86400.0) > 0.01) "
            "AS flagged, COUNT(*) FILTER (WHERE los IS NOT NULL AND intime IS NOT NULL AND outtime IS NOT NULL) "
            "AS total, COUNT(*) FILTER (WHERE outtime IS NULL) AS null_outtime FROM icustays",
            convention="icustays.los is inconsistent with intime/outtime for some stays: compute length of "
                       "stay from the timestamps when precision matters.",
            applies_to=("icustays.los",)))
        if "admissions" in schema:
            checks.append(Check(
                "temporal.icustays.intime_outside_admission", "temporal",
                "ICU intime outside its hospital admission [admittime, dischtime]", ("icustays", "admissions"),
                "SELECT COUNT(*) FILTER (WHERE i.intime < a.admittime OR i.intime > a.dischtime) AS flagged, "
                "COUNT(*) AS total, COUNT(*) FILTER (WHERE i.intime < a.admittime - INTERVAL 1 DAY "
                "OR i.intime > a.dischtime + INTERVAL 1 DAY) AS beyond_24h "
                "FROM icustays i JOIN admissions a ON i.hadm_id = a.hadm_id",
                expect_zero=False, group="outside_admission", target="icustays.intime",
                applies_to=("icustays.intime",)))
    if {"patients", "admissions"} <= set(schema):
        checks.append(Check(
            "temporal.patients.age_over_89_shifted", "temporal",
            "Patients aged >= 89 at first admission (DOB shifted: computed age about 300)", ("patients", "admissions"),
            "WITH f AS (SELECT subject_id, MIN(admittime) AS t FROM admissions GROUP BY 1), "
            "g AS (SELECT date_diff('day', p.dob, f.t) / 365.25 AS age FROM patients p JOIN f USING (subject_id)) "
            "SELECT COUNT(*) FILTER (WHERE age >= 89) AS flagged, COUNT(*) AS total, "
            "COUNT(*) FILTER (WHERE age >= 250) AS shifted_about_300, "
            "COUNT(*) FILTER (WHERE age < 1) AS under_1_year FROM g",
            expect_zero=False, always_convention=True,
            convention="Patients older than 89 at their first admission have DOB shifted so that computed age "
                       "is about 300 years. For age questions treat computed age > 89 as '>89' (cap, or exclude); "
                       "never average raw computed ages. MIMIC documents the median true age of this group as 91.4.",
            applies_to=("patients.dob",)))
    return checks


# ----------------------------------------------------------------------
# MIMIC-III quirks and coverage
# ----------------------------------------------------------------------
def quirk_checks(schema: Schema) -> list[Check]:
    has = set(schema)
    checks = []
    for table in ("diagnoses_icd", "procedures_icd", "d_icd_diagnoses", "d_icd_procedures"):
        if table in has:
            checks.append(Check(
                f"quirk.{table}.icd9_without_dot", "quirk", f"{table}.icd9_code stored without a decimal point",
                (table,),
                f"SELECT COUNT(*) FILTER (WHERE icd9_code LIKE '%.%') AS flagged, COUNT(icd9_code) AS total FROM \"{table}\"",
                always_convention=True, group="icd9_format", target=f"{table}.icd9_code",
                applies_to=(f"{table}.icd9_code",)))
    if "patients" in has:
        checks.append(Check(
            "quirk.patients.gender_values", "quirk", "patients.gender is 'M' or 'F'", ("patients",),
            "SELECT COUNT(*) FILTER (WHERE gender IS NULL OR gender NOT IN ('M', 'F')) AS flagged, "
            "COUNT(*) AS total FROM patients"))
    if {"icustays", "inputevents_cv"} <= has:
        checks.append(Check(
            "quirk.icustays.without_inputevents", "quirk",
            "ICU stays with no INPUTEVENTS_CV rows (MetaVision stays need INPUTEVENTS_MV, not loaded)",
            ("icustays", "inputevents_cv"),
            "WITH s AS (SELECT DISTINCT icustay_id FROM inputevents_cv WHERE icustay_id IS NOT NULL) "
            "SELECT COUNT(*) FILTER (WHERE s.icustay_id IS NULL) AS flagged, COUNT(*) AS total, "
            "COUNT(*) FILTER (WHERE s.icustay_id IS NULL AND i.dbsource = 'metavision') AS metavision_without, "
            "COUNT(*) FILTER (WHERE s.icustay_id IS NULL AND i.dbsource = 'carevue') AS carevue_without "
            "FROM icustays i LEFT JOIN s ON i.icustay_id = s.icustay_id",
            expect_zero=False, always_convention="inputevents_mv" not in has,
            convention="ICU input (fluid/drug administration) data cover CareVue stays only (INPUTEVENTS_CV, "
                       "2001-2008); INPUTEVENTS_MV is not loaded, so input questions about MetaVision stays "
                       "(2008-2012) cannot be answered and population-level input statistics are partial.",
            applies_to=("inputevents_cv.*",)))
        checks.append(Check(
            "quirk.inputevents_cv.on_metavision_stays", "quirk",
            "INPUTEVENTS_CV rows on MetaVision-only ICU stays", ("icustays", "inputevents_cv"),
            "SELECT COUNT(*) FILTER (WHERE i.dbsource = 'metavision') AS flagged, COUNT(*) AS total, "
            "COUNT(DISTINCT e.icustay_id) FILTER (WHERE i.dbsource = 'metavision') AS stays_affected "
            "FROM inputevents_cv e JOIN icustays i ON e.icustay_id = i.icustay_id",
            group="dbsource_crossover", target="inputevents_cv rows on 'metavision' stays",
            applies_to=("icustays.dbsource", "inputevents_cv.icustay_id")))
    if {"icustays", "procedureevents_mv"} <= has:
        checks.append(Check(
            "quirk.procedureevents_mv.on_carevue_stays", "quirk",
            "PROCEDUREEVENTS_MV rows on CareVue-only ICU stays", ("icustays", "procedureevents_mv"),
            "SELECT COUNT(*) FILTER (WHERE i.dbsource = 'carevue') AS flagged, COUNT(*) AS total, "
            "COUNT(DISTINCT e.icustay_id) FILTER (WHERE i.dbsource = 'carevue') AS stays_affected "
            "FROM procedureevents_mv e JOIN icustays i ON e.icustay_id = i.icustay_id",
            group="dbsource_crossover", target="procedureevents_mv rows on 'carevue' stays",
            applies_to=("icustays.dbsource", "procedureevents_mv.icustay_id")))
        checks.append(Check(
            "quirk.icustays.without_procedureevents", "quirk",
            "ICU stays with no PROCEDUREEVENTS_MV rows (table covers MetaVision stays only)",
            ("icustays", "procedureevents_mv"),
            "WITH s AS (SELECT DISTINCT icustay_id FROM procedureevents_mv WHERE icustay_id IS NOT NULL) "
            "SELECT COUNT(*) FILTER (WHERE s.icustay_id IS NULL) AS flagged, COUNT(*) AS total, "
            "COUNT(*) FILTER (WHERE s.icustay_id IS NULL AND i.dbsource = 'carevue') AS carevue_without "
            "FROM icustays i LEFT JOIN s ON i.icustay_id = s.icustay_id",
            expect_zero=False, always_convention=True,
            convention="PROCEDUREEVENTS_MV covers MetaVision ICU stays only (2008-2012); CareVue stays have no "
                       "ICU procedure events. Use PROCEDURES_ICD for hospital procedures across all years.",
            applies_to=("procedureevents_mv.*",)))
    if {"cptevents", "icustays"} <= has:
        checks.append(Check(
            "quirk.cptevents.without_icu_stay", "quirk", "CPTEVENTS rows whose admission has no ICU stay",
            ("cptevents", "icustays"),
            "WITH s AS (SELECT DISTINCT hadm_id FROM icustays) "
            "SELECT COUNT(*) FILTER (WHERE s.hadm_id IS NULL) AS flagged, COUNT(*) AS total "
            "FROM cptevents c LEFT JOIN s ON c.hadm_id = s.hadm_id",
            expect_zero=False, always_convention=True,
            convention="CPTEVENTS records billed professional services (mostly ICU); it is not a complete record "
                       "of procedures. Use PROCEDURES_ICD for 'which procedures did the patient have'.",
            applies_to=("cptevents.*",)))
    if "prescriptions" in has:
        checks.append(Check(
            "quirk.prescriptions.ndc_unusable", "quirk", "PRESCRIPTIONS rows with no usable NDC (null, '' or '0')",
            ("prescriptions",),
            "SELECT COUNT(*) FILTER (WHERE ndc IS NULL OR trim(ndc) IN ('', '0')) AS flagged, COUNT(*) AS total "
            "FROM prescriptions",
            expect_zero=False,
            convention="Many prescriptions have no usable NDC: find drugs by name (drug, drug_name_generic; "
                       "case-insensitive, e.g. lower(drug) LIKE '%heparin%') rather than by NDC.",
            applies_to=("prescriptions.ndc", "prescriptions.drug")))
    if "datetimeevents" in has:
        checks.append(Check(
            "quirk.datetimeevents.error_rows", "quirk", "DATETIMEEVENTS rows marked error = 1", ("datetimeevents",),
            "SELECT COUNT(*) FILTER (WHERE error = 1) AS flagged, COUNT(*) AS total FROM datetimeevents",
            expect_zero=False,
            convention="Exclude datetimeevents rows with error = 1 (charted in error).",
            applies_to=("datetimeevents.error",)))
    if "procedureevents_mv" in has:
        checks.append(Check(
            "quirk.procedureevents_mv.rewritten", "quirk",
            "PROCEDUREEVENTS_MV rows with statusdescription 'Rewritten' (superseded entries)",
            ("procedureevents_mv",),
            "SELECT COUNT(*) FILTER (WHERE statusdescription = 'Rewritten') AS flagged, COUNT(*) AS total "
            "FROM procedureevents_mv",
            expect_zero=False,
            convention="Exclude procedureevents_mv rows with statusdescription = 'Rewritten' (replaced by a "
                       "later entry) when counting procedures.",
            applies_to=("procedureevents_mv.statusdescription",)))
    if "microbiologyevents" in has:
        checks.append(Check(
            "quirk.microbiologyevents.date_only", "quirk", "MICROBIOLOGYEVENTS rows with chartdate but no charttime",
            ("microbiologyevents",),
            "SELECT COUNT(*) FILTER (WHERE charttime IS NULL) AS flagged, COUNT(*) AS total FROM microbiologyevents",
            expect_zero=False,
            convention="Microbiology charttime is often missing: use chartdate for microbiology timing.",
            applies_to=("microbiologyevents.charttime", "microbiologyevents.chartdate")))
        checks.append(Check(
            "quirk.microbiologyevents.no_organism", "quirk",
            "MICROBIOLOGYEVENTS rows with no organism (org_name null: no growth / specimen only)",
            ("microbiologyevents",),
            "SELECT COUNT(*) FILTER (WHERE org_name IS NULL) AS flagged, COUNT(*) AS total FROM microbiologyevents",
            expect_zero=False,
            convention="Microbiology rows with org_name IS NULL record specimens without a grown organism; "
                       "count positive cultures with org_name IS NOT NULL.",
            applies_to=("microbiologyevents.org_name",)))
    if {"admissions", "diagnoses_icd"} <= has:
        checks.append(Check(
            "quirk.admissions.without_diagnoses", "quirk", "Admissions with no DIAGNOSES_ICD rows",
            ("admissions", "diagnoses_icd"),
            "WITH s AS (SELECT DISTINCT hadm_id FROM diagnoses_icd) "
            "SELECT COUNT(*) FILTER (WHERE s.hadm_id IS NULL) AS flagged, COUNT(*) AS total "
            "FROM admissions a LEFT JOIN s ON a.hadm_id = s.hadm_id",
            expect_zero=False))
    if "d_items" in has:
        checks.append(Check(
            "quirk.d_items.linksto_missing", "quirk", "D_ITEMS rows with no LINKSTO table", ("d_items",),
            "SELECT COUNT(*) FILTER (WHERE linksto IS NULL) AS flagged, COUNT(*) AS total FROM d_items",
            expect_zero=False))
    return checks


DISTRIBUTIONS = [
    Distribution("dist.icustays.dbsource", "icustays", "dbsource", "ICU stays by documentation system",
                 "ICU data come from two systems: CareVue (2001-2008) and MetaVision (2008-2012); item IDs and "
                 "event tables differ between them (dbsource)."),
    Distribution("dist.icustays.first_careunit", "icustays", "first_careunit", "ICU stays by first care unit"),
    Distribution("dist.admissions.admission_type", "admissions", "admission_type", "Admissions by type",
                 "admission_type = 'NEWBORN' marks neonatal admissions (age about 0); exclude them for adult "
                 "cohort questions unless newborns are asked about."),
    Distribution("dist.admissions.insurance", "admissions", "insurance", "Admissions by insurance"),
    Distribution("dist.drgcodes.drg_type", "drgcodes", "drg_type", "DRG rows by DRG system",
                 "DRGCODES mixes DRG systems (drg_type HCFA, MS, APR): filter by drg_type before comparing codes."),
    Distribution("dist.prescriptions.drug_type", "prescriptions", "drug_type", "Prescriptions by drug type"),
    Distribution("dist.d_items.linksto", "d_items", "linksto", "ICU items by event table"),
    Distribution("dist.d_items.dbsource", "d_items", "dbsource", "ICU items by documentation system"),
    Distribution("dist.services.curr_service", "services", "curr_service", "Service assignments by service"),
    Distribution("dist.transfers.eventtype", "transfers", "eventtype", "Transfers by event type"),
    Distribution("dist.procedureevents_mv.statusdescription", "procedureevents_mv", "statusdescription",
                 "ICU procedures by status"),
    Distribution("dist.microbiologyevents.interpretation", "microbiologyevents", "interpretation",
                 "Susceptibility results by interpretation"),
]


def build_checks(schema: Schema) -> list[Check]:
    return key_checks(schema) + integrity_checks(schema) + temporal_checks(schema) + quirk_checks(schema)
