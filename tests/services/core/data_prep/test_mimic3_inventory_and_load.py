"""
MIMIC-III source file inventory and typed load, on small synthetic CSVs (no MIMIC data).

Run without the repo-wide Postgres fixture:
    pytest tests/services/core/data_prep --noconftest -q
"""
import csv
import gzip
from pathlib import Path

import duckdb
import pytest

from pneuma_seeker.services.core.data_prep.inventory import run_inventory
from pneuma_seeker.services.core.data_prep.loader import load_all
from pneuma_seeker.services.core.data_prep.mimic3_schema import TABLES, TEAM_TABLES


def _write(path: Path, header: list[str], rows: list[list[str]], gz: bool = False) -> None:
    opener = (lambda p: gzip.open(p, "wt", newline="")) if gz else (lambda p: open(p, "w", newline=""))
    with opener(path) as file:
        writer = csv.writer(file, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(header)
        writer.writerows(rows)


@pytest.fixture
def source(tmp_path: Path) -> Path:
    src = tmp_path / "MIMIC_III"
    src.mkdir()
    _write(src / "PATIENTS.csv", TABLES["PATIENTS"].column_names, [
        ["1", "10", "F", "2100-01-01 00:00:00", "", "", "", "0"],
        ["2", "11", "M", "2090-05-02 00:00:00", "2150-01-01 00:00:00", "", "2150-01-01 00:00:00", "1"],
    ])
    _write(src / "D_ICD_DIAGNOSES.csv.gz", TABLES["D_ICD_DIAGNOSES"].column_names, [
        ["1", "0066", "Amebic brain abscess", "Amebic brain abscess"],
        ["2", "V3000", "Single lb in-hosp w/o cs", "Single liveborn, born in hospital"],
    ], gz=True)
    _write(src / "DIAGNOSES_ICD.csv", TABLES["DIAGNOSES_ICD"].column_names, [
        ["1", "10", "100", "1", "0066"],
        ["2", "11", "101", "not-a-number", "V3000"],  # Bad SEQ_NUM -> rejected, not silently kept
        ["3", "11", "101", "2", "4019"],
    ])
    _write(src / "ADMISSIONS.csv", ["ROW_ID", "SUBJECT_ID"], [["1", "10"]])  # Truncated header
    (src / "PROCEDURESEVENTS_MV.csv").write_text("ROW_ID\n")  # Misspelled file name
    return src


def test_inventory(source: Path):
    inv = run_inventory(source)
    status = {c.table: c.status for c in inv.checks}
    assert status["PATIENTS"] == "ok"
    assert status["D_ICD_DIAGNOSES"] == "ok"  # .csv.gz is found and read
    assert status["ADMISSIONS"] == "HEADER MISMATCH"
    assert status["PROCEDUREEVENTS_MV"] == "MISSING"  # Team table, wrong file name
    assert status["LABEVENTS"] == "absent (known)"  # Not in the team copy
    assert "PROCEDURESEVENTS_MV.csv" in inv.unrecognized_files
    assert set(inv.loadable) == {"PATIENTS", "D_ICD_DIAGNOSES", "DIAGNOSES_ICD"}


def test_load(source: Path, tmp_path: Path):
    db_path = tmp_path / "datasets" / "mimic_iii" / "mimic_iii.db"
    results = {r.table: r for r in load_all(run_inventory(source), db_path, progress=lambda _: None)}

    assert results["patients"].rows_loaded == 2
    assert results["diagnoses_icd"].rows_loaded == 2
    assert results["diagnoses_icd"].rows_rejected == 1
    assert results["diagnoses_icd"].status == "REJECTED ROWS"
    assert any(k.startswith("seq_num") for k in results["diagnoses_icd"].rejects_by_column)
    assert results["patients"].status == "COUNT DIFFERS"  # Synthetic data != 46,520 rows

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        assert sorted(n for (n,) in con.execute("SHOW TABLES").fetchall()) == [
            "d_icd_diagnoses", "diagnoses_icd", "patients"]  # No reject tables left behind
        types = dict(con.execute(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'patients'"
        ).fetchall())
        assert types["dob"] == "TIMESTAMP" and types["subject_id"] == "INTEGER"
        codes = [c for (c,) in con.execute("SELECT icd9_code FROM d_icd_diagnoses ORDER BY row_id").fetchall()]
        assert codes == ["0066", "V3000"]  # Leading zeros kept
        assert con.execute("SELECT COUNT(*) FROM patients WHERE dod IS NULL").fetchone()[0] == 1
    finally:
        con.close()

    metadata = (db_path.parent / "metadata.csv").read_text()
    assert metadata.startswith("table_name,description") and "patients," in metadata
    assert not (db_path.parent / "mimic_iii.db.building").exists()


def test_subset_reload_keeps_other_tables(source: Path, tmp_path: Path):
    db_path = tmp_path / "mimic_iii.db"
    inv = run_inventory(source)
    load_all(inv, db_path, progress=lambda _: None)
    load_all(inv, db_path, tables=["patients"], progress=lambda _: None)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        assert len(con.execute("SHOW TABLES").fetchall()) == 3
    finally:
        con.close()


def test_specs_cover_team_tables():
    assert set(TEAM_TABLES) <= set(TABLES)
    assert len(TEAM_TABLES) == 21
    for spec in TABLES.values():
        assert spec.column_names[0] == "ROW_ID"
        assert len(set(spec.column_names)) == len(spec.column_names)
        assert all(t in {"INTEGER", "SMALLINT", "DOUBLE", "TIMESTAMP", "VARCHAR"} for _, t in spec.columns)


def test_table_without_published_row_count(tmp_path: Path):
    """Datasets that publish no row counts: official_rows=None loads as 'ok (no official count)'."""
    from pneuma_seeker.services.core.data_prep.loader import format_load_report, load_table
    from pneuma_seeker.services.core.data_prep.mimic3_schema import TableSpec

    spec = TableSpec("VISITS", (("ROW_ID", "INTEGER"), ("CODE", "VARCHAR")), None)
    _write(tmp_path / "VISITS.csv", ["ROW_ID", "CODE"], [["1", "007"], ["2", "042"]])
    con = duckdb.connect()
    result = load_table(con, spec, tmp_path / "VISITS.csv")
    con.close()
    assert (result.rows_loaded, result.row_diff, result.status) == (2, None, "ok (no official count)")
    assert "tables needing attention: none" in format_load_report([result])
