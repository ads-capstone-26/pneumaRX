"""
MIMIC-III v1.4 data preparation.

Builds, offline and locally, the dataset and the knowledge about it that the
query system (the part of Pneuma-Seeker that interprets questions and looks up
tables) uses at question time. Run with scripts/prepare_mimic3.py.

Stages, in order:
    inventory.py   source file inventory: which files exist, and do their headers match the official schema?
    loader.py      typed load into the "mimic_iii" dataset DB, with row-count and parse-error checks
    quality.py     data quality checks (rules in quality_checks.py) -> report + query conventions
    profile.py     schema profile: every table and column with its meaning, role, values, links and rules
    snapshot.py    shared, committed copy in docs/mimic3/ (fingerprint, small counts as <11, mismatch warning)

mimic3_schema.py holds the official table specifications (names, types, row
counts); mimic3_docs.py the written table and column descriptions; paths.py
input/output locations and report file names. README.md (next to this file)
explains the structure and how to set up another dataset.

Searching the code dictionaries and linking codes to medical vocabularies
(UMLS) happen at question time in the query system, not here.

MIMIC-III is credentialed data (PhysioNet DUA). Nothing in this package prints
or writes patient-level values: reports contain only schema facts and
aggregate counts.
"""
