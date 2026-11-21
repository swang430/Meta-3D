import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import mpdb_playback as clocks


def test_pair_and_rate_follow_physical_axis_not_speed():
    platform = dict(name="R0B0S0D.mpdb", direction="downlink", linkIndex=0, routeIndex=0,
                    sectorIndex=0, baseStationIndex=0, transmitterIndex=0, linkKey="link",
                    transmitter={"nodeId":"tx","index":0}, receiver={"nodeId":"rx","terminalIndex":0,"routeIndex":0})
    meta = {k:platform[k] for k in ("direction","linkIndex","routeIndex","sectorIndex",
                                      "baseStationIndex","transmitterIndex","linkKey")}
    meta.update(txNodeId="tx", rxNodeId="rx", terminalIndex=0, rtFrameClock={"version":1,"mode":"physical"},
                rtSampleTimesSeconds=[7,7.25,9])
    plan = dict(planIndex=0, dataFile="R0B0S0D.arrow", frameCount=3, metadata=meta,
                rowOffset=0, rowsPerFrame=8)
    shard = dict(planIndex=0,sequence=0,path="s3://project/runs/source/R0B0S0D.arrow",rowCount=24,rowOffset=0)
    doc = dict(protocol="lauraycs-compute-link-plan",protocolVersion=1,kind="compute-link-plan",
               frameCount=3,plans=[plan],datasets=[dict(datasetId="links",rowCount=24, shards=[shard])])
    timing = dict(source_times_s=None, frame_ids=[0,1,2], distances_m=[None,None],
                  max_abs_doppler_hz=0, time_source=None, frame_row_counts=[8,8,8])
    raw = json.dumps(doc).encode()
    assert callable(getattr(clocks,"match_plan",None))
    matched = clocks.match_plan(raw, platform, timing)
    assert matched["plan_sha256"] == hashlib.sha256(raw).hexdigest()
    standard = clocks.resolve_playback(matched,None,None,"standard")
    assert standard["rate_hz"] >= 4
    assert standard["source_times_s"] == [0,.25,2]
    regular = json.dumps({**doc,"plans":[{**plan,"metadata":{**meta,"rtSampleTimesSeconds":[7,8,9]}}]}).encode()
    interval_only = {**timing,"source_times_s":[0,1,2],"time_source":"meta.rtSampleIntervalSeconds"}
    assert clocks.match_plan(regular,platform,interval_only)["source_times_s"] == [7,8,9]
    approx = {**timing,"source_times_s":[7.0000001,7.25,9],"time_source":"FRAME.TIME_S"}
    assert clocks.match_plan(raw,platform,approx)["source_times_s"] == [7,7.25,9]
    for bad in ({**interval_only,"source_times_s":[0,.5,2]}, {**approx,"source_times_s":[7.001,7.25,9]}):
        with pytest.raises(ValueError):
            clocks.match_plan(raw,platform,bad)
    assert clocks.resolve_playback(matched,None,None,"dense")["rate_hz"] == 2*standard["rate_hz"]
    assert clocks.resolve_playback({**matched,"max_abs_doppler_hz":27},None,None,"standard")["rate_hz"] > 54
    for changes in (dict(frame_ids=[0,1,4]),dict(source_times_s=[0,1,2]),
                    dict(frame_only=True),dict(frame_row_counts=[8,7,9]),dict(embedded_axis_lengths=[4])):
        with pytest.raises(ValueError):
            clocks.match_plan(raw,platform,{**timing,**changes})
    for change in (dict(terminalIndex=99),dict(terminalIndex=False),dict(txNodeId="rx"),dict(routeIndex=1),dict(rtFrameClock={"version":1,"mode":"frame-only"}),
                   dict(rtSampleTimesSeconds=[7,8,8]),dict(rtSampleTimesSeconds=[7,8,10**400])):
        with pytest.raises(ValueError):
            clocks.match_plan(json.dumps({**doc,"plans":[{**plan,"metadata":{**meta,**change}}]}).encode(),platform,timing)
    for change in (dict(path="unrelated-run/R0B0S0D.arrow"),dict(path="https://bucket/R0B0S0D.arrow"),
                   dict(path="s3:///R0B0S0D.arrow"),dict(sequence=1),
                   dict(planIndex=1),dict(path="s3://project/R0B0S0U.arrow"),dict(rowCount=23)):
        with pytest.raises(ValueError):
            clocks.match_plan(json.dumps({**doc,"datasets":[dict(datasetId="links",rowCount=24,shards=[{**shard,**change}])]}).encode(),platform,timing)
    shard["path"] = "R0B0S0D.arrow"
    assert clocks.match_plan(json.dumps(doc).encode(),platform,timing)["source_times_s"] == [7,7.25,9]
