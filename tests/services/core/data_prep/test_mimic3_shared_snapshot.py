"""
Shared MIMIC-III snapshot (docs/mimic3/): fingerprint, small-count suppression,
stable content and the mismatch warning, on synthetic data (no MIMIC data).

    pytest tests/services/core/data_prep --noconftest -q
"""
import json
import re

import duckdb
import pytest

from pneuma_seeker.services.core.data_prep import paths
from pneuma_seeker.services.core.data_prep.quality import run_quality
from pneuma_seeker.services.core.data_prep.snapshot import (
    compare_with_snapshot, fingerprint, suppress_evidence, write_snapshot,
)

from .synthetic_mimic3 import build_synthetic_db


@pytest.fixture
def db(tmp_path):
    db_path = build_synthetic_db(tmp_path / "datasets" / "mimic_iii" / "mimic_iii.db")
    con = duckdb.connect(str(db_path))
    for i in range(1, 13):  # 12 items: a count large enough to be shown as is
        con.execute("INSERT INTO d_items (row_id, itemid, label, linksto) VALUES (?, ?, 'x', 'chartevents')",
                    [i, 1000 + i])
    con.close()
    return db_path


def _publish(db_path, out_dir):
    report = run_quality(db_path, progress=lambda _: None)
    return write_snapshot(report, fingerprint(db_path), out_dir)


def test_suppress_evidence():
    assert suppress_evidence({"flagged": 4, "total": 58_976, "pct": 0.007, "within_24h": 3}) == {
        "flagged": "<11", "total": 58_976, "within_24h": "<11", "pct": None}
    assert suppress_evidence({"flagged": 0, "total": 5, "pct": 0.0}) == {"flagged": 0, "total": "<11", "pct": 0.0}
    assert suppress_evidence({"flagged": 98, "total": 58_976, "pct": 0.166})["flagged"] == 98


def test_snapshot_content(db, tmp_path):
    written = _publish(db, tmp_path / "snapshot")
    payload = json.loads(written["conventions"].read_text())
    md = written["quality_md"].read_text()

    assert payload["data_fingerprint"]["row_counts"]["d_items"] == 12
    assert re.fullmatch(r"[0-9a-f]{12}", payload["data_fingerprint"]["id"])
    for text in (written["conventions"].read_text(), md):
        assert str(tmp_path) not in text and "/Users/" not in text  # No paths
        assert not re.search(r"20\d\d-\d\d-\d\dT\d\d:\d\d", text)  # No run timestamp
    assert "do not edit by hand" in md and payload["data_fingerprint"]["id"] in md

    # Every count 1-10 is suppressed in the evidence; zero stays visible
    for entry in payload["conventions"]:
        for ev in entry["evidence"].values():
            for key, value in ev.items():
                assert not (isinstance(value, int) and 0 < value < 11), (entry["id"], key, value)
    assert "<11" in md
    assert "`'chartevents'` (12)" in md  # Large enough counts are shown
    assert "| patients | dod | <11 rows |" in md or "all but" in md  # Missingness of tiny tables suppressed


def test_snapshot_is_stable(db, tmp_path):
    first = {k: p.read_bytes() for k, p in _publish(db, tmp_path / "a").items()}
    second = {k: p.read_bytes() for k, p in _publish(db, tmp_path / "b").items()}
    assert first == second  # Same data + same rules -> byte-identical files


def test_mismatch_warning(db, tmp_path):
    written = _publish(db, tmp_path / "snapshot")
    assert compare_with_snapshot(db, written["conventions"]).status == "match"

    con = duckdb.connect(str(db))
    con.execute("INSERT INTO caregivers (row_id, cgid) VALUES (1, 7)")
    con.execute("DROP TABLE callout")
    con.close()
    result = compare_with_snapshot(db, written["conventions"])
    assert result.status == "differs"
    assert any(d.startswith("caregivers:") for d in result.differences)
    assert "callout: in the snapshot, not in your DB" in result.differences
    assert "WARNING" in result.message()

    assert compare_with_snapshot(db, tmp_path / "missing.json").status == "no_snapshot"


def test_source_dir_must_be_set(tmp_path, monkeypatch):
    monkeypatch.delenv("MIMIC_III_DIR", raising=False)
    monkeypatch.setattr(paths, "PROJECT_ROOT", tmp_path)  # No .env here
    with pytest.raises(paths.SourceDirNotSet, match="MIMIC_III_DIR"):
        paths.resolve_mimic_dir()
    (tmp_path / ".env").write_text("OTHER=1\nMIMIC_III_DIR=/data/mimic3\n")
    assert str(paths.resolve_mimic_dir()) == "/data/mimic3"
    assert str(paths.resolve_mimic_dir("/cli/path")) == "/cli/path"  # Command line wins
