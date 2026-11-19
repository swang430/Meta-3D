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
        convert(document, direction, tmp_path)
    document["source_files"][0]["sha256"] = "other"
    with pytest.raises(ValueError, match="原始 MPDB"):
        convert(document, direction, tmp_path)


def test_delivery_hashes_match_reviewed_evaluation():
    root = Path(__file__).resolve().parents[3]
    evaluated = json.loads((root / "docs/plans/s5c-24-frames.json").read_bytes())
    assert evaluated["input_sha256"] == REFERENCE_HASHES


@pytest.mark.parametrize("count,budget", [(8, None), (16, 24), (24, 24)])
def test_new_delivery_uses_own_manifest_and_counts(tmp_path, count, budget):
    import hashlib
    from scripts.s5_evaluation.export_trajectory import CLUSTER, QUALITY
    platform = {"name": "new.mpdb", "direction": "uplink", "angleCoordinateSystem": "LCS", "linkKey": "new-link"}
    direction = dict(direction="uplink", source_document={"meta": {"lauraycsPlatform": platform}},
                     raw_tables={"LINK": {"FREQUENCY": [[2400000000]], "TX_ANT": [0], "RX_ANT": [0]}},
                     frames=[dict(frame_id=3, link_id=9, time_s=0, sample_rows=list(range(count)))],
                     time={"origin": "distance_over_user_speed"}, unit_evidence={})
    archive = {"path": "sample.zip", "sha256": "b" * 64}
    document = dict(source_files=[archive], parameters=dict(speed_m_s=5, coordinate_units="metres"), generator_version=None)
    clusters = tmp_path / "new_cluster_cdl.csv"
    clusters.write_text(",".join(CLUSTER) + "\n" + "".join(
        f"9,0,{i*1e-9},50,90,0,90,0,90,0\n" for i in range(count)))
    quality = tmp_path / "new_cluster_quality.csv"
    quality.write_text(",".join(QUALITY) + f"\n9,{count},{count},1,1,1\n")
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [clusters, quality]}
    manifest = dict(schemaVersion="meta3d-cluster-delivery/1", direction="uplink",
                    inputSha256={**hashes, archive["path"]: archive["sha256"]}, requestedClusterCount=budget)
    data = convert(document, direction, tmp_path, manifest)
    assert data["requestedClusterCount"] == budget
    assert data["frames"][0]["clustering"]["nCluster"] == count
    assert data["source"]["evaluation"] == "unknown"
    assert data["source"]["inputSha256"] == manifest["inputSha256"]
    with pytest.raises(ValueError, match="质量表"):
        convert(document, direction, tmp_path, {**manifest, "requestedClusterCount": 1})
    clusters.write_text(clusters.read_text().replace(",50,", ",55,"))
    with pytest.raises(ValueError, match="CSV 当前内容"):
        convert(document, direction, tmp_path, manifest)


@pytest.mark.parametrize("fault", ["none", "direction", "mixed", "count"])
def test_original_budget_filenames_bound_to_manifest(fault):
    from app.trajectory.cluster_exchange import delivery_names
    stem = "R0B0S0D"
    pair = (stem+"_cluster_cdl_n8.csv", stem+"_cluster_quality_n8.csv")
    hashes = dict.fromkeys(pair, "digest")
    if fault == "mixed":
        hashes = {pair[0]: "digest", stem+"_cluster_quality_n16.csv": "digest"}
    manifest = dict(inputSha256=hashes, requestedClusterCount=16 if fault == "count" else 8)
    if fault == "none":
        assert delivery_names(stem, manifest) == pair
    else:
        with pytest.raises(ValueError):
            delivery_names("R0B0S0U" if fault == "direction" else stem, manifest)
