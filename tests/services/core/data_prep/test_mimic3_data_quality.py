"""
MIMIC-III data quality checks on a synthetic DB with planted issues (no MIMIC data).

    pytest tests/services/core/data_prep --noconftest -q
"""
import pytest

from pneuma_seeker.services.core.data_prep.quality import format_markdown, run_quality

from .synthetic_mimic3 import build_synthetic_db


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    db_path = build_synthetic_db(tmp_path_factory.mktemp("q") / "mimic_iii.db")
    return run_quality(db_path, progress=lambda _: None)


def _check(report, check_id):
    return next(c for c in report.checks if c.id == check_id)


def test_all_checks_run(report):
    errors = [(c.id, c.error) for c in report.checks if c.status == "error"]
    assert not errors
    assert len(report.checks) > 80


def test_keys(report):
    assert _check(report, "keys.patients.subject_id").status == "pass"
    assert _check(report, "keys.diagnoses_icd.exact_duplicates").flagged == 1
    assert _check(report, "keys.diagnoses_icd.hadm_id,seq_num").flagged == 1


def test_integrity(report):
    fk = _check(report, "integrity.diagnoses_icd.hadm_id->admissions")
    assert (fk.status, fk.flagged, fk.total) == ("flag", 1, 4)
    code = _check(report, "integrity.diagnoses_icd.icd9_code->d_icd_diagnoses")
    assert code.status == "info" and code.flagged == 1 and code.extra["distinct_unmatched"] == 1
    assert _check(report, "integrity.diagnoses_icd.hadm_subject_consistent").flagged == 1
    assert _check(report, "integrity.inputevents_cv.icustay_hadm_consistent").flagged == 1


def test_temporal(report):
    reversed_stay = _check(report, "temporal.admissions.dischtime_before_admittime")
    assert reversed_stay.flagged == 1
    assert reversed_stay.extra == {"within_24h": 1, "died_in_hospital": 1}
    assert _check(report, "temporal.admissions.expire_flag_vs_deathtime").extra["flag_without_time"] == 1
    assert _check(report, "temporal.patients.expire_flag_vs_dod").flagged == 1
    assert _check(report, "temporal.icustays.los_matches_times").flagged == 1
    icu = _check(report, "temporal.icustays.intime_outside_admission")
    assert icu.flagged == 1 and icu.extra["beyond_24h"] == 0
    age = _check(report, "temporal.patients.age_over_89_shifted")
    assert age.flagged == 1 and age.extra["shifted_about_300"] == 1


def test_quirks_and_conventions(report):
    assert _check(report, "quirk.patients.gender_values").flagged == 1
    assert _check(report, "quirk.inputevents_cv.on_metavision_stays").flagged == 1
    ids = {c["id"] for c in report.conventions}
    assert "temporal.patients.age_over_89_shifted" in ids  # Always documented
    assert "group.icd9_format" in ids  # Always documented, even with 0 flagged
    assert "keys.patients.subject_id" not in ids  # Passed: no rule needed
    assert "dist.admissions.admission_type" in ids
    assert "group.icustay_hadm_mismatch" in ids  # Flagged checks carry a rule
    icd = next(c for c in report.conventions if c["id"] == "group.icd9_format")
    assert len(icd["sources"]) == 4 and "d_icd_diagnoses.icd9_code" in icd["rule"]  # One rule, 4 tables
    durations = next(c for c in report.conventions if c["id"] == "group.negative_duration")
    assert durations["targets"] == ["admissions (dischtime < admittime)"]  # Only flagged tables are listed
    assert durations["evidence"]["admissions (dischtime < admittime)"]["flagged"] == 1
    assert len({c["rule"] for c in report.conventions}) == len(report.conventions)


def test_padded_text(report):
    assert report.padded_text["drgcodes"]["drg_type"] == 1
    padded = next(c for c in report.conventions if c["id"] == "group.padded_text")
    assert "drgcodes.drg_type" in padded["targets"]
    assert report.distributions["dist.drgcodes.drg_type"]["values"]["APR "] == 1  # Raw value kept in JSON


def test_outputs_are_aggregate_only(report):
    md = format_markdown(report)
    assert "Amebic" not in md and "2150-01" not in md  # No row values or timestamps in the report
    assert report.missingness["patients"]["columns"]["dod"] == 100.0
    assert report.distributions["dist.admissions.admission_type"]["values"]["NEWBORN"] == 1
    assert report.to_dict()["conventions"] == report.conventions  # Local JSON carries the rules too
