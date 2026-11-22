"""分析只接受能对回原始源帧和成员表的外部汇总。"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mpdb_port_evidence import expected_rows


def test_source_summary_rejects_nonfinite_and_fractional_identity(tmp_path):
    source = {"mpdb": "m", "members": "g"}
    path = tmp_path / "result.json"
    base = dict(frame=0, tx=0, rx=0, cluster=0, real=1e-5, imag=0)
    for changes in ({"imag": float("nan")}, {"frame": True}, {"cluster": 0.5}):
        path.write_text(
            json.dumps(
                dict(schema="joint-results/1", source=source, rows=[base | changes])
            )
        )
        with pytest.raises(ValueError):
            expected_rows(path.read_bytes(), source)


def test_partial_material_preserves_independent_results(tmp_path, monkeypatch):
    import hashlib
    import zipfile
    from argparse import Namespace
    from types import ModuleType

    import numpy as np

    from scripts.tests.test_mpdb_conducted_project import sample
    from scripts.mpdb_port_evidence import analyze

    db = tmp_path / "test.mpdb"
    sample(db, 16)
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.write(db, "R0B0S0D.mpdb")
    digest = hashlib.sha256(db.read_bytes()).hexdigest()
    members = tmp_path / "members.npz"
    np.savez(
        members,
        source_sha256=digest,
        **{f"L{i}": np.array([0, 1]) for i in range(1, 16)},
    )
    expected = tmp_path / "expected.json"
    expected.write_text('{"source":{}}')
    engine = ModuleType("mimo_ota_simulator.port_evidence")
    engine.analyze_frame = lambda frame, links, offsets, floor: len(links)
    monkeypatch.setitem(sys.modules, engine.__name__, engine)
    result = analyze(
        Namespace(
            archive=archive,
            members=members,
            expected=expected,
            bandwidth_mhz=100,
            points=3,
            amplitude_floor=None,
        )
    )
    assert result["frames"] == [7, 8]
    assert any("汇总" in note and "未核验" in note for note in result["notes"])
    assert any("发射 0 接收 0" in note for note in result["notes"])


def test_output_cannot_replace_analysis_input(tmp_path, monkeypatch):
    from mpdb_port_evidence import main

    original = tmp_path / "source.zip"
    original.write_bytes(b"existing input")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "analyze",
            "--archive",
            str(original),
            "--output",
            str(original),
            "--points",
            "3",
            "--bandwidth-mhz",
            "1",
        ],
    )
    with pytest.raises(FileExistsError):
        main()
    assert original.read_bytes() == b"existing input"
