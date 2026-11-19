from pathlib import Path
import json

import pytest

from scripts.s5_evaluation.export_trajectory import REFERENCE_HASHES, convert


def test_changed_csv_with_same_name_cannot_reuse_reference_source(tmp_path):
    path = tmp_path / "R0B0S0D_cluster_cdl.csv"
    path.write_text("LINK_ID,DELAY\n0,1")
    direction = {"direction": "downlink", "source_document": {"meta": {"lauraycsPlatform": {
        "name": "R0B0S0D.mpdb", "direction": "downlink"}}}}
    document = {"source_files": [{"path": "original.zip", "sha256": REFERENCE_HASHES["original.zip"]}]}
    with pytest.raises(ValueError, match="CSV 当前内容"):
        convert(document, direction, tmp_path, REFERENCE_HASHES)
    document["source_files"][0]["sha256"] = "other"
    with pytest.raises(ValueError, match="原始 MPDB"):
        convert(document, direction, tmp_path, REFERENCE_HASHES)


def test_delivery_hashes_match_reviewed_evaluation():
    root = Path(__file__).resolve().parents[3]
    evaluated = json.loads((root / "docs/plans/s5c-24-frames.json").read_bytes())
    assert evaluated["input_sha256"] == REFERENCE_HASHES
