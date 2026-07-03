#!/usr/bin/env python3
"""现场修正: F64 Scenario Pack 18 条信道资产的频率/命名以工程实测为准。

背景 (2026-07-03 CAICT 现场, 用户定流程):
  .smu 文件名频率是场景族**标称**, 不等于工程内真实 CenterFrequency ——
  纯净加载实证 UMa_3600M 工程实为 3549.99 MHz (ARFCN 636666, 恰是 UXM
  Test App 自带默认), 文件名 fallback (parse_smu_center_freq_mhz) 对这类
  文件系统性报错值。SCD 登记必须填工程实测频率。

真值来源: SMB 只读挂载 //192.168.0.132/Scenario Packs, 逐个解析 .smu 的
[Channel Group 0] CenterFrequency (2026-07-03 实录, 解析器用 UMa_3600M
面板实证 3550 做金标准校验)。18 条中 3 条文件名≠真值:
  UMa_1800M → 1842.50 MHz / UMa_2450M → 2592.99 MHz / UMa_3600M → 3549.99 MHz
另 2 条命名格式不一致 (4700 的 arfcn 段写成 "4700MHZ") 一并统一。

做两处修正 (均幂等, 可重放):
  1. ChannelAsset vendor 目录 18 条 upsert (按 associated_file_path 匹配,
     含 inactive —— 软删的 b328d53a UMa3600 会被复活修正, onsite 吞吐脚本
     默认 ASSET_ID 得以延续);
  2. available_channel_models 18 条重建 (显式 center_frequency_mhz 真值,
     normalize 优先显式值不再走文件名 fallback)。

验收: vendor 资产恰 18 条 active 且频率=工程真值; channel-models 频率同步。
"""
import sys
import requests

API = "http://localhost:8000/api/v1"
PACK = r"D:\Scenario Packs\F9815064A TS 5G FR1 MIMO OTA\1.1"

# (原文件名主干, scenario, mimo, topo, 文件名标称MHz, 工程真值Hz, 真ARFCN, band)
# 真值 = SMB 实录 2026-07-03; band 按真值频率落位 (722/836.5/1575.42/2450→
# 无准确 NR DL band 的保留 FR1 泛化; 2592.99 落 n41 故 2450 文件标 N41)。
TRUTH = [
    ("3GPP_FR1_OTA_CDLC_UMa_617M",     "UMa", "4x4", "32x4",  617.0,   617000000, 123400, "N71"),
    ("3GPP_FR1_OTA_CDLC_UMa_722M",     "UMa", "4x4", "32x4",  722.0,   722000000, 144400, "FR1"),
    ("3GPP_FR1_OTA_CDLC_UMa_836.5M",   "UMa", "4x4", "32x4",  836.5,   836500000, 167300, "FR1"),
    ("3GPP_FR1_OTA_CDLC_UMa_1575.42M", "UMa", "4x4", "32x4", 1575.42, 1575420000, 315084, "FR1"),
    ("3GPP_FR1_OTA_CDLC_UMa_1800M",    "UMa", "4x4", "32x4", 1800.0,  1842500000, 368500, "N3"),
    ("3GPP_FR1_OTA_CDLC_UMa_2132.5M",  "UMa", "4x4", "32x4", 2132.5,  2132500000, 426500, "N1"),
    ("3GPP_FR1_OTA_CDLC_UMa_2450M",    "UMa", "4x4", "32x4", 2450.0,  2592990000, 518598, "N41"),
    ("3GPP_FR1_OTA_CDLC_UMa_3600M",    "UMa", "4x4", "32x4", 3600.0,  3549990000, 636666, "N78"),
    ("3GPP_FR1_OTA_CDLC_UMa_4700M",    "UMa", "4x4", "32x4", 4700.0,  4700000000, 713333, "N79"),
    ("3GPP_FR1_OTA_CDLC_UMi_617M",     "UMi", "2x2", "32x2",  617.0,   617000000, 123400, "N71"),
    ("3GPP_FR1_OTA_CDLC_UMi_722M",     "UMi", "2x2", "32x2",  722.0,   722000000, 144400, "FR1"),
    ("3GPP_FR1_OTA_CDLC_UMi_836.5M",   "UMi", "2x2", "32x2",  836.5,   836500000, 167300, "FR1"),
    ("3GPP_FR1_OTA_CDLC_UMi_1575.42M", "UMi", "2x2", "32x2", 1575.42, 1575420000, 315084, "FR1"),
    ("3GPP_FR1_OTA_CDLC_UMi_1800M",    "UMi", "2x2", "32x2", 1800.0,  1800000000, 360000, "N3"),
    ("3GPP_FR1_OTA_CDLC_UMi_2132.5M",  "UMi", "2x2", "32x2", 2132.5,  2132500000, 426500, "N1"),
    ("3GPP_FR1_OTA_CDLC_UMi_2450M",    "UMi", "2x2", "32x2", 2450.0,  2450000000, 490000, "FR1"),
    ("3GPP_FR1_OTA_CDLC_UMi_3600M",    "UMi", "2x2", "32x2", 3600.0,  3600000000, 640000, "N78"),
    ("3GPP_FR1_OTA_CDLC_UMi_4700M",    "UMi", "2x2", "32x2", 4700.0,  4700000000, 713333, "N79"),
]


def row_fields(row):
    stem, scenario, mimo, topo, nominal, freq_hz, arfcn, band = row
    path = f"{PACK}\\{stem}.wiz\\{stem}.smu"
    name = f"MF_{band}_{arfcn}_BW100_CDLC_{scenario}_{mimo}_DP_v1"
    mhz = freq_hz / 1e6
    desc = (f"F64 Scenario Pack v1.1 {stem}.smu | 工程实测 {mhz:g}MHz / "
            f"ARFCN {arfcn} (SMB 实录 2026-07-03) | {topo} OTA DL")
    if abs(nominal - mhz) > 0.5:
        desc += f" | ⚠ 文件名标称 {nominal:g}M ≠ 工程真值"
    return {
        "name": name,
        "path": path,
        "freq_hz": float(freq_hz),
        "mhz": mhz,
        "desc": desc,
        "scd_config": {
            "band": band, "mimo": mimo, "arfcn": arfcn, "model": "CDLC",
            "version": 1, "scenario": scenario, "polarization": "DP",
            "bandwidth_mhz": 100,
        },
    }


def upsert_assets():
    r = requests.get(f"{API}/channel-assets",
                     params={"source_type": "vendor_file",
                             "include_inactive": "true", "page_size": 100})
    r.raise_for_status()
    data = r.json()
    existing = {a["associated_file_path"]: a
                for a in (data if isinstance(data, list) else data.get("items", []))
                if a.get("associated_file_path")}
    created = updated = 0
    for row in TRUTH:
        f = row_fields(row)
        body = {
            "name": f["name"],
            "canonical_name": f["name"] + ".smu",
            "description": f["desc"],
            "center_frequency_hz": f["freq_hz"],
            "bandwidth_mhz": 100.0,
            "associated_file_path": f["path"],
            "payload": {"scd_config": f["scd_config"]},
        }
        hit = existing.get(f["path"])
        if hit:
            body["is_active"] = True  # 软删条目一并复活修正
            resp = requests.put(f"{API}/channel-assets/{hit['id']}", json=body)
            if resp.status_code >= 400:
                print(f"  ✗ PUT {f['name']}: {resp.status_code} {resp.text[:200]}")
                resp.raise_for_status()
            updated += 1
        else:
            body["source_type"] = "vendor_file"
            body["created_by"] = "onsite-fix-20260703"
            resp = requests.post(f"{API}/channel-assets", json=body)
            if resp.status_code >= 400:
                print(f"  ✗ POST {f['name']}: {resp.status_code} {resp.text[:200]}")
                resp.raise_for_status()
            created += 1
    print(f"  ChannelAsset: {updated} 更新(含复活) + {created} 新建")


def rebuild_channel_models():
    # 单类别无 GET 端点 (405) —— connection_params 从 catalog 列表取; PUT 是整体
    # 覆盖 connection_params, 必须先全量取回再改单键, 否则冲掉其他配置。
    r = requests.get(f"{API}/instruments/catalog")
    r.raise_for_status()
    cats = r.json()
    cats = cats if isinstance(cats, list) else cats.get("items") or cats.get("categories") or []
    conn = next((c.get("connection") or {} for c in cats
                 if (c.get("key") or c.get("category_key")) == "channelEmulator"), {})
    params = dict(conn.get("connection_params") or conn.get("connectionParams") or {})
    entries = []
    for row in TRUTH:
        f = row_fields(row)
        entries.append({
            "filename": f["path"],
            "label": f["name"],
            "description": f["desc"],
            "center_frequency_mhz": f["mhz"],  # 显式真值, 压制文件名 fallback
        })
    params["available_channel_models"] = entries
    body = {"connection": {"connection_params": params}}
    resp = requests.put(f"{API}/instruments/channelEmulator", json=body)
    resp.raise_for_status()
    print(f"  available_channel_models: 重建 {len(entries)} 条 (显式真值频率)")


def acceptance():
    r = requests.get(f"{API}/channel-assets",
                     params={"source_type": "vendor_file", "page_size": 100})
    r.raise_for_status()
    data = r.json()
    items = data if isinstance(data, list) else data.get("items", [])
    active = [a for a in items if a.get("is_active", True)]
    truth = {row_fields(row)["path"]: row_fields(row) for row in TRUTH}
    print(f"\n== 验收: vendor 资产 {len(active)} 条 (期望 18) ==")
    ok = True
    for a in sorted(active, key=lambda x: x["name"]):
        t = truth.get(a.get("associated_file_path"))
        if not t:
            print(f"  ✗ 多余条目: {a['name']}"); ok = False; continue
        good = (a["name"] == t["name"]
                and abs((a.get("center_frequency_hz") or 0) - t["freq_hz"]) < 1
                and (a.get("payload", {}).get("scd_config", {}).get("arfcn")
                     == t["scd_config"]["arfcn"]))
        mark = "✓" if good else "✗"
        if not good: ok = False
        print(f"  {mark} {a['name']:<44} {t['mhz']:>9.2f}MHz arfcn={t['scd_config']['arfcn']}")
    missing = set(truth) - {a.get("associated_file_path") for a in active}
    for p in missing:
        print(f"  ✗ 缺: {p}"); ok = False
    rm = requests.get(f"{API}/instruments/channelEmulator/channel-models").json()
    freqs = {it["filename"]: it.get("center_frequency_mhz")
             for it in rm.get("items", [])}
    bad = [p for p, t in truth.items()
           if freqs.get(p) is None or abs(freqs[p] - t["mhz"]) > 0.01]
    print(f"== channel-models 频率同步: {len(truth) - len(bad)}/18 一致 ==")
    if bad:
        ok = False
        for p in bad:
            print(f"  ✗ {p.split(chr(92))[-1]}: {freqs.get(p)}")
    if not (len(active) == 18 and ok):
        print("验收未通过"); sys.exit(2)
    print("验收通过 ✓")


if __name__ == "__main__":
    print("== Step 1: ChannelAsset vendor 18 条 upsert ==")
    upsert_assets()
    print("== Step 2: available_channel_models 重建 ==")
    rebuild_channel_models()
    acceptance()
