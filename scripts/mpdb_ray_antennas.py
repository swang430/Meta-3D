"""用同源传播矩阵替换天线，而不在已合成的 H 上再次叠加方向图。"""
import json
import hashlib
import numpy as np


def apply_patterns(db, desc, column, doc, digest, carrier, link_ids, tx_ports, rx_ports, ids, original, angles):
    declared=desc.get("meta",{}).get("columnDescriptions",{})
    both=(declared.get("H")=="TX polar mode 1 -> RX polar mode 1"
          and all(k in desc["records"]["CHANNEL"] for k in ("JONES_T","JONES_R")))
    evidence=dict(source="source_H",antenna_response="both" if both else "unknown",
                  pattern_identity="unverified",formal_measurement=False)
    if doc is None:
        return original,evidence
    if (not isinstance(doc,dict) or doc.get("schema")!="ray-antenna-patterns/1"
            or doc.get("source_sha256")!=digest or doc.get("carrier_hz")!=carrier
            or doc.get("basis")!="global_theta_phi_rx_effective_length_transpose"):
        raise ValueError("方向图文件缺少同源、频率或极化约定依据")
    choices={}
    for end,ports in (("tx",tx_ports),("rx",rx_ports)):
        entries=doc.get(end,{})
        if not isinstance(entries,dict) or not set(entries)<={str(i) for i in ports}:
            raise ValueError("方向图引用了不存在的端口")
        choices[end]=entries
    if not any(choices.values()):
        raise ValueError("请至少提供一个端口的实测或设计方向图")
    from mimo_ota_simulator.conducted_ray_patterns import terminal_field, project_rays
    needed=["POLAR","FADE_L","PHASE","JONES_T","JONES_R"]
    missing=[k for k in needed if k not in desc["records"]["CHANNEL"]]
    if missing:
        return original,dict(evidence,unverified_reason="缺少 "+", ".join(missing)+"；沿用源 H，方向图未替换")
    def read(key,shape):
        value=column(db,desc,"CHANNEL",key)
        n=len(ids)
        expected = {(2,2): [(n,1,2,2),(n,2,2)], (2,): [(n,1,2,1),(n,2,1)], (): [(n,1),(n,)]}
        if value.shape not in expected[shape]:
            raise ValueError(f"射线 {key} 的极化分量与行数不符")
        return value.reshape((n,*shape))
    polar=read("POLAR",(2,2))
    path=read("PHASE",())*read("FADE_L",())
    tx,rx=read("JONES_T",(2,)).astype(complex),read("JONES_R",(2,)).astype(complex)
    prior=project_rays(tx,rx,polar,path)
    # 深零陷处的舍入误差随投影各乘积之和缩放，而不随相消后的 H 缩放。
    bound=np.einsum("ni,nij,nj->n",abs(rx),abs(polar),abs(tx))*abs(path)
    if not np.iscomplexobj(original) or not all(np.isfinite(v).all() for v in (original,prior,bound)):
        raise ValueError("源 H 或极化重建依据不是有限复系数")
    epsilon=np.finfo(original.real.dtype).eps
    if np.any(abs(prior-original)>16*epsilon*bound):
        raise ValueError("源 H 与导出的两端极化及传播矩阵不一致，无法核验相位约定")
    changed = np.zeros(len(ids), dtype=bool)
    aod,zod,aoa,zoa=angles
    for end,ports,values,az,zen in (("tx",tx_ports,tx,aod,zod),("rx",rx_ports,rx,aoa,zoa)):
        for port,pattern in choices[end].items():
            mask=np.isin(ids,link_ids[ports==int(port)])
            changed |= mask
            values[mask]=terminal_field(pattern,az[mask],zen[mask],carrier)
    result = original.astype(np.complex128, copy=True)
    result[changed] = project_rays(tx[changed], rx[changed], polar[changed], path[changed])
    record=dict(source="projected_from_propagation",antenna_response="both",formal_measurement=False,
                pattern_sha256=hashlib.sha256(json.dumps(doc,sort_keys=True,allow_nan=False).encode()).hexdigest(),
                replaced_ports={k:list(v) for k,v in choices.items()})
    return result,record
