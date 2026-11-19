"""已评估的上下行文件组及其逐帧交换格式。"""
import hashlib
from pathlib import Path

from .cluster_csv import CLUSTER, QUALITY, cluster_path, decode_groups

REFERENCE_HASHES = {
    "original.zip": "6cada6a493b04bbf05725ffdeaac61956e382a18897fad5c3efce94113a0037d",
    "adapted-final.json": "bba63f0ca0b4450070c8e904bb14b04b88cb2ac932492690c80853403d61a919",
    "R0B0S0D_cluster_cdl.csv": "ed37fa3a1de7f160ac821f8fa697514012d9299f1381a0b19f222c7b707a8e0e",
    "R0B0S0D_cluster_quality.csv": "87c8e6762e2a492d1b5a8509919f6a4821719e81360e82b8b07cc91ef4b38e22",
    "R0B0S0U_cluster_cdl.csv": "cd63b2b5ddc6ecf9c338bb43842084c6f6f784c22e69299a8053320b875c62c4",
    "R0B0S0U_cluster_quality.csv": "a0c9e021be9b9ca11aa267c08a17b1714cb18f297e2bb1eba7b89400904bce7a"
}


def convert(document, direction, directory, manifest=None):
    name = direction["direction"]
    platform = direction["source_document"]["meta"]["lauraycsPlatform"]
    stem = Path(platform["name"]).stem
    if name != platform["direction"]:
        raise ValueError("上下行来源标记不一致")
    archive = document["source_files"][0]
    expected = REFERENCE_HASHES
    archive_hash = REFERENCE_HASHES["original.zip"]
    budget = None
    if manifest is not None:
        if not isinstance(manifest, dict) or manifest.get("schemaVersion") != "meta3d-cluster-delivery/1":
            raise ValueError("配套清单版本无效")
        if manifest.get("direction") != name:
            raise ValueError("清单与输入方向不同")
        expected = manifest["inputSha256"]
        if not isinstance(expected, dict):
            raise ValueError("清单缺少文件校验值")
        archive_hash = expected.get(archive["path"])
        budget = manifest["requestedClusterCount"]
        if budget is not None and (type(budget) is not int or not 1 <= budget <= 24):
            raise ValueError("清单中的请求簇数应为 1 至 24 或 null")
    if archive["sha256"] != archive_hash:
        raise ValueError("原始 MPDB 包与配套清单不匹配，新批次请提供自身清单")
    actual = {item["path"]: item["sha256"] for item in document["source_files"]}
    groups = []
    for suffix, columns in (("cdl", CLUSTER), ("quality", QUALITY)):
        file = directory / f"{stem}_cluster_{suffix}.csv"
        data = file.read_bytes()
        current = hashlib.sha256(data).hexdigest()
        if expected.get(file.name) != current:
            raise ValueError("CSV 当前内容与来源校验记录不匹配")
        actual[file.name] = current
        groups.append(decode_groups(file.name, data, columns))
    clusters, quality = groups
    same_files = archive["sha256"] == REFERENCE_HASHES["original.zip"] and all(
        actual[f"{stem}_cluster_{suffix}.csv"] == REFERENCE_HASHES.get(f"{stem}_cluster_{suffix}.csv")
        for suffix in ("cdl", "quality"))
    evaluated = (manifest is None and same_files and document["parameters"]["speed_m_s"] == 5
                 and document["parameters"]["coordinate_units"] == "metres")
    table = direction["raw_tables"]["LINK"]
    links = {f["link_id"] for f in direction["frames"]}
    if links != set(clusters) or links != set(quality) or len(links) != len(direction["frames"]):
        raise ValueError("输入帧与聚簇表或质量表不一一对应")
    frames = []
    for index, frame in enumerate(direction["frames"]):
        link = frame["link_id"]
        q, = quality[link]
        count = len(frame["sample_rows"])
        if (not 1 <= len(clusters[link]) <= min(count, budget or 24) or q["N_RAYS"] != count
                or q["N_CLUSTERS"] != len(clusters[link]) or (same_files and len(clusters[link]) != 24)):
            raise ValueError("质量表与路径或簇数不一致")
        if len({tuple(row[k] for k in CLUSTER) for row in clusters[link]}) != len(clusters[link]):
            raise ValueError("帧内存在重复的簇记录")
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
                txAnt=tx, rxAnt=rx, requestedClusterCount=budget, clusterIdentity="frame-local-only",
                angleCoordinateSystem=platform["angleCoordinateSystem"],
                units=dict(time="s", delay="ns", angles="deg", doppler="Hz", carrier="Hz", response="complex_scalar"),
                source=dict(taskId=None, linkKey=platform["linkKey"], mpdbPath=platform["name"], contentVersion=None,
                            softwareVersion=document["generator_version"], additionalLoss=None,
                            evaluation="reference_24_conditional" if evaluated else "unknown",
                            requestedClusterCountSource="delivery_manifest" if budget is not None else None,
                            inputSha256=actual, parameters=document["parameters"],
                            unitEvidence=direction["unit_evidence"]),
                timing=dict(source=direction["time"]["origin"], timesSeconds=[f["timeSeconds"] for f in frames]),
                frames=frames)


