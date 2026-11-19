"""把已评估的上下行 CSV 与原始非均匀时间轴组织为计算服务可消费的轨迹。"""
import argparse
import json
from pathlib import Path

from scripts.s5_evaluation.csv_export import CLUSTER, QUALITY, cluster_path, read_groups
from scripts.s5_evaluation.run import sha


def convert(document, direction, directory, hashes):
    name = direction["direction"]
    platform = direction["source_document"]["meta"]["lauraycsPlatform"]
    stem = Path(platform["name"]).stem
    if name != platform["direction"]:
        raise ValueError("上下行来源标记不一致")
    clusters = read_groups(directory / f"{stem}_cluster_cdl.csv", CLUSTER)
    quality = read_groups(directory / f"{stem}_cluster_quality.csv", QUALITY)
    table = direction["raw_tables"]["LINK"]
    links = {f["link_id"] for f in direction["frames"]}
    if links != set(clusters) or links != set(quality) or len(links) != len(direction["frames"]):
        raise ValueError("输入帧与聚簇表或质量表不一一对应")
    frames = []
    for index, frame in enumerate(direction["frames"]):
        link = frame["link_id"]
        q, = quality[link]
        count = len(frame["sample_rows"])
        if q["N_RAYS"] != count or q["N_CLUSTERS"] != len(clusters[link]):
            raise ValueError("质量表与路径或簇数不一致")
        paths = []
        for cid, row in enumerate(clusters[link]):
            p = cluster_path(row)
            paths.append(dict(clusterId=cid, delayNs=p["delay_s"] * 1e9, hReal=p["h_real"],
                              hImag=p["h_imag"], aoaPhi=row["AOA"], aoaTheta=row["ZOA"],
                              aodPhi=row["AOD"], aodTheta=row["ZOD"], channelType=row["CHANNEL_TYPE"],
                              dopplerHz=row["DOPPLER"]))
        frames.append(dict(sampleIndex=index, frameId=frame["frame_id"], internalLinkId=link,
                           timeSeconds=frame["time_s"], inputPathCount=count, status="clustered",
                           clustering=dict(rawPaths=count, filteredPaths=None, nCluster=len(paths), paths=paths)))
    carrier, = {v for row in table["FREQUENCY"] for v in row}
    tx, = set(table["TX_ANT"])
    rx, = set(table["RX_ANT"])
    return dict(schemaVersion="meta3d-cluster-trajectory/1", direction=name, carrierHz=carrier,
                txAnt=tx, rxAnt=rx, requestedClusterCount=24, clusterIdentity="frame-local-only",
                angleCoordinateSystem=platform["angleCoordinateSystem"],
                units=dict(time="s", delay="ns", angles="deg", doppler="Hz", carrier="Hz", response="complex_scalar"),
                source=dict(taskId=platform["linkKey"], mpdbPath=platform["name"], contentVersion=None,
                            softwareVersion=document["generator_version"], additionalLoss=None,
                            inputSha256=hashes, parameters=document["parameters"],
                            unitEvidence=direction["unit_evidence"]),
                timing=dict(source=direction["time"]["origin"], timesSeconds=[f["timeSeconds"] for f in frames]),
                frames=frames)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("adapted", "directory", "evaluation", "output"):
        parser.add_argument(argument, type=Path)
    args = parser.parse_args()
    evaluation = json.loads(args.evaluation.read_bytes())
    if sha(args.adapted) != evaluation["input_sha256"][args.adapted.name]:
        raise ValueError("时间轴输入与评估时的文件不一致")
    document = json.loads(args.adapted.read_bytes())
    args.output.mkdir(exist_ok=True, parents=True)
    for direction in document["directions"]:
        trajectory = convert(document, direction, args.directory, evaluation["input_sha256"])
        path = args.output / (direction["direction"] + ".json")
        path.write_text(json.dumps(trajectory, ensure_ascii=False, allow_nan=False), encoding="utf-8")
