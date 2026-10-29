"""
Synthetic MIMIC-III-shaped DuckDB with planted data quality issues, shared by the
data quality and shared snapshot tests. Contains no MIMIC data.
"""
from pathlib import Path

import duckdb

from pneuma_seeker.services.core.data_prep.mimic3_schema import TABLES, TEAM_TABLES


def _insert(con, table: str, rows: list[dict]) -> None:
    for i, row in enumerate(rows, 1):
        row = {"row_id": i, **row}
        cols = ", ".join(row)
        con.execute(f"INSERT INTO {table} ({cols}) VALUES ({', '.join('?' for _ in row)})", list(row.values()))


def build_synthetic_db(db_path: Path) -> Path:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    for name in TEAM_TABLES:  # All 21 team tables exist (mostly empty), so every check's SQL runs
        spec = TABLES[name]
        con.execute(f"CREATE TABLE {spec.table_name} ({', '.join(f'{c.lower()} {t}' for c, t in spec.columns)})")
    _insert(con, "patients", [
        dict(subject_id=1, gender="F", dob="2100-01-01", expire_flag=0),
        dict(subject_id=2, gender="M", dob="1800-01-01", expire_flag=0),  # Age about 300 (shifted)
        dict(subject_id=3, gender="X", dob="2120-01-01", expire_flag=1),  # Bad gender; flag without dod
    ])
    _insert(con, "admissions", [
        dict(subject_id=1, hadm_id=10, admittime="2150-01-01 00:00", dischtime="2150-01-05 00:00",
             hospital_expire_flag=0, discharge_location="HOME", admission_type="EMERGENCY"),
        dict(subject_id=2, hadm_id=11, admittime="2100-01-01 00:00", dischtime="2099-12-31 00:00",  # Reversed
             hospital_expire_flag=1, discharge_location="DEAD/EXPIRED", admission_type="ELECTIVE"),  # No deathtime
        dict(subject_id=3, hadm_id=12, admittime="2160-01-01 00:00", dischtime="2160-01-02 00:00",
             hospital_expire_flag=0, discharge_location="HOME", admission_type="NEWBORN"),
    ])
    _insert(con, "icustays", [
        dict(subject_id=1, hadm_id=10, icustay_id=100, dbsource="carevue",
             intime="2149-12-31 12:00", outtime="2150-01-02 12:00", los=2.0),  # Starts 12 h before admittime
        dict(subject_id=1, hadm_id=10, icustay_id=101, dbsource="metavision",
             intime="2150-01-03 00:00", outtime="2150-01-04 00:00", los=5.0),  # LOS inconsistent
    ])
    _insert(con, "d_icd_diagnoses", [dict(icd9_code="0066", short_title="Amebic brain abscess")])
    _insert(con, "diagnoses_icd", [
        dict(subject_id=1, hadm_id=10, seq_num=1, icd9_code="0066"),
        dict(subject_id=1, hadm_id=10, seq_num=1, icd9_code="0066"),  # Exact duplicate except row_id
        dict(subject_id=1, hadm_id=99, seq_num=1, icd9_code="9999"),  # Unknown admission and code
        dict(subject_id=2, hadm_id=10, seq_num=2, icd9_code="0066"),  # subject disagrees with admissions
    ])
    _insert(con, "inputevents_cv", [dict(subject_id=1, hadm_id=12, icustay_id=101, itemid=30001,  # hadm_id
                                         charttime="2150-01-03 01:00")])  # disagrees with icustays; MetaVision stay
    _insert(con, "drgcodes", [dict(subject_id=1, hadm_id=10, drg_type="APR ", drg_code="123"),  # Padded value
                              dict(subject_id=2, hadm_id=11, drg_type="HCFA", drg_code="45")])
    con.close()
    return db_path
