"""
MIMIC-III schema profile on synthetic data (no MIMIC data).

    pytest tests/services/core/data_prep --noconftest -q
"""
import json

import duckdb
import pytest

from pneuma_seeker.services.core.data_prep.mimic3_docs import MIMIC_III_TABLE_DOCS
from pneuma_seeker.services.core.data_prep.mimic3_schema import TABLES
from pneuma_seeker.services.core.data_prep.profile import build_profile, format_profile_markdown, suppress_profile
from pneuma_seeker.services.core.data_prep.quality import run_quality
from pneuma_seeker.services.core.data_prep.snapshot import fingerprint, write_snapshot

from .synthetic_mimic3 import build_synthetic_db


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    db_path = build_synthetic_db(tmp_path_factory.mktemp("p") / "mimic_iii.db")
    con = duckdb.connect(str(db_path))
    for i in range(1, 15):  # 14 admissions of one type: a value common enough to be shared
        con.execute("INSERT INTO admissions (row_id, subject_id, hadm_id, admission_type, admittime, dischtime) "
                    "VALUES (?, 1, ?, 'URGENT', '2150-02-01', '2150-02-02')", [100 + i, 1000 + i])
    con.close()
    report = run_quality(db_path, progress=lambda _: None)
    return db_path, report, build_profile(db_path, report.to_dict())


def test_descriptions_cover_the_schema():
    for name, spec in TABLES.items():
        description, columns = MIMIC_III_TABLE_DOCS[spec.table_name]
        assert description
        assert set(columns) == {c.lower() for c in spec.column_names}


def test_roles_and_links(built):
    _, _, profile = built
    adm = profile["tables"]["admissions"]
    assert adm["kind"] == "core" and adm["key"] == ["hadm_id"]
    cols = adm["columns"]
    assert cols["row_id"]["role"] == "row_number"
    assert cols["hadm_id"]["role"] == "identifier"
    assert cols["subject_id"]["role"] == "reference" and cols["subject_id"]["references"] == "patients.subject_id"
    assert cols["admittime"]["role"] == "time"
    assert cols["admission_type"]["role"] == "category"
    assert cols["admission_type"]["values"]["URGENT"] == 14
    assert cols["hospital_expire_flag"]["role"] == "flag"
    assert cols["diagnosis"]["description"].startswith("Free-text")

    dx = profile["tables"]["diagnoses_icd"]["columns"]["icd9_code"]
    assert dx["role"] == "code" and dx["references"] == "d_icd_diagnoses.icd9_code"
    assert profile["tables"]["d_items"]["kind"] == "dictionary"
    assert profile["tables"]["patients"]["columns"]["dod"]["role"] == "always_null"  # dod empty in synthetic data

    link = next(l for l in profile["links"] if l["from"] == "diagnoses_icd.hadm_id")
    assert link["to"] == "admissions.hadm_id" and link["unmatched_rows"] == 1 and link["rows_checked"] == 4


def test_conventions_are_attached(built):
    _, _, profile = built
    drg = profile["tables"]["drgcodes"]["columns"]["drg_type"]
    assert "group.padded_text" in drg["conventions"]
    assert "group.exact_duplicates" in profile["tables"]["diagnoses_icd"]["table_conventions"]


def test_shared_profile_is_suppressed_and_stable(built, tmp_path):
    db_path, report, profile = built
    shared = suppress_profile(profile)
    values = shared["tables"]["admissions"]["columns"]["admission_type"]["values"]
    assert values == {"URGENT": 14}  # Values seen in fewer than 11 rows are dropped
    assert shared["tables"]["admissions"]["columns"]["admission_type"]["rare_values_omitted"] == 3
    assert shared["tables"]["patients"]["rows"] == "<11"
    assert "null_rows" not in shared["tables"]["patients"]["columns"]["dod"]  # Exact null counts not shared

    first = write_snapshot(report, fingerprint(db_path), tmp_path / "a", profile=profile)
    second = write_snapshot(report, fingerprint(db_path), tmp_path / "b",
                            profile=build_profile(db_path, report.to_dict()))
    assert set(first) == {"conventions", "quality_md", "profile_json", "profile_md"}
    assert all(first[k].read_bytes() == second[k].read_bytes() for k in first)  # Byte-identical
    payload = json.loads(first["profile_json"].read_text())
    assert payload["data_fingerprint"]["id"] and "/Users/" not in first["profile_json"].read_text()
    md = first["profile_md"].read_text()
    assert "## admissions" in md and "## Links between tables" in md and "`'URGENT'`" in md
    assert "`'NEWBORN'`" not in md  # Rare value not shown in the shared copy


def test_markdown_renders_local_profile(built):
    md = format_profile_markdown(built[2])
    assert "| hadm_id | INTEGER | identifier |" in md
