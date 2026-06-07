"""一次性维护: 清理重复暗室 + 恢复被"加载默认布局"误清的探头。

背景:
- GUI「加载默认布局」按钮做的是**全局** PUT /probes/bulk —— 删光所有暗室的探头, 再写
  32 个无暗室归属 (chamber_config_id=NULL) 的默认探头。结果 CAICT-FS(62) / 3GPP(32) /
  Type-C 预设(32) 的探头全被清掉。
- DB 里同时堆了 124 个暗室, 其中 ~118 个是自动化测试/手动试验反复建出来的重复脏数据
  (大型单向暗室 ×28、大型双向暗室 ×28 等), 真正要留的只有 4 个系统预设 + CAICT-FS + 3GPP。

本脚本 (默认 **dry-run**, 仅打印计划; 加 `--apply` 才真正改库):
  1. 保留: 全部 is_system_preset=True 的暗室 (4 个) + 名为 CAICT-FS / 3GPP 16 Probe Dual 的暗室。
  2. 删除: 其余所有暗室 + 所有不属于保留暗室的探头 (含 chamber_config_id=NULL 的孤儿默认探头)。
  3. 恢复探头 (幂等, 仅当目标暗室当前 0 探头时): CAICT-FS 62 / Type-C 预设 32 / 3GPP 32,
     按各自原始几何精确重建; probe_number 按 chamber 局部 1..N (复合唯一键)。

安全:
- 整个改库过程在单事务内, 出错回滚, 不留半截状态。
- dry-run 不写库, 可放心先跑看计划。

用法:
    cd api-service
    .venv/bin/python scripts/dev-fixtures/cleanup_and_restore_chambers.py            # 预览计划
    .venv/bin/python scripts/dev-fixtures/cleanup_and_restore_chambers.py --apply     # 执行
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))  # 让 `app` 可导入

from sqlalchemy import or_

from app.db.database import SessionLocal
from app.models.chamber import ChamberConfiguration
from app.models.probe import Probe

KEEP_NAMES = {"CAICT-FS", "3GPP 16 Probe Dual"}

# 各保留暗室的探头几何 (用于恢复; 仅当该暗室当前 0 探头才插入)。
# 每个环: ring_id / elevation / count(方位数) / az_offset(环间交错)。极化 V+H。
_LAYOUT_CAICT_FS = [
    {"ring": 1, "el": 90, "count": 1,  "az_offset": 0.0},
    {"ring": 2, "el": 60, "count": 6,  "az_offset": 0.0},
    {"ring": 3, "el": 30, "count": 12, "az_offset": 15.0},
    {"ring": 4, "el": 0,  "count": 12, "az_offset": 0.0},
]  # 31 位置 × 2 = 62
_LAYOUT_TYPE_C_PRESET = [
    {"ring": 1, "el": 45,  "count": 4, "az_offset": 0.0},
    {"ring": 2, "el": 0,   "count": 8, "az_offset": 0.0},
    {"ring": 3, "el": -45, "count": 4, "az_offset": 0.0},
]  # 16 × 2 = 32
_LAYOUT_3GPP = [
    {"ring": 3, "el": 0, "count": 16, "az_offset": 0.0},
]  # 16 × 2 = 32


def _build_specs(layout: list[dict], radius: float) -> list[dict]:
    specs: list[dict] = []
    n = 1
    for ring in layout:
        count = ring["count"]
        step = 360.0 / count if count else 0.0
        for i in range(count):
            az = round((ring["az_offset"] + i * step) % 360.0, 1)
            for pol in ("V", "H"):
                specs.append({
                    "probe_number": n,
                    "name": f"Probe {n}-{pol}",
                    "ring": ring["ring"],
                    "polarization": pol,
                    "position": {"azimuth": az, "elevation": float(ring["el"]), "radius": radius},
                })
                n += 1
    return specs


def _restore_layout_for(chamber: ChamberConfiguration) -> list[dict] | None:
    """返回该暗室应恢复的探头几何; 不需恢复则 None。"""
    if chamber.name == "CAICT-FS":
        return _LAYOUT_CAICT_FS
    if chamber.name == "3GPP 16 Probe Dual":
        return _LAYOUT_3GPP
    if chamber.is_system_preset and chamber.chamber_type == "type_c":
        return _LAYOUT_TYPE_C_PRESET
    return None


def main(apply: bool) -> int:
    db = SessionLocal()
    try:
        all_chambers = db.query(ChamberConfiguration).all()
        keep = [c for c in all_chambers if c.is_system_preset or c.name in KEEP_NAMES]
        keep_ids = [c.id for c in keep]
        drop = [c for c in all_chambers if c.id not in set(keep_ids)]

        print(f"暗室总数: {len(all_chambers)} | 保留: {len(keep)} | 删除: {len(drop)}")
        print("\n保留的暗室:")
        for c in sorted(keep, key=lambda x: (not x.is_system_preset, x.name)):
            tag = "[预设]" if c.is_system_preset else "[非预设]"
            print(f"  {tag} {c.name} ({c.chamber_type}) {c.id}")

        # 待删探头 = chamber 不在保留集 (含 NULL 孤儿)
        probes_to_delete = (
            db.query(Probe)
            .filter(or_(Probe.chamber_config_id.is_(None), Probe.chamber_config_id.notin_(keep_ids)))
            .count()
        )
        print(f"\n待删探头 (孤儿 NULL + 属于待删暗室): {probes_to_delete}")

        print("\n待恢复探头 (仅当该暗室当前 0 探头):")
        restore_plan: list[tuple[ChamberConfiguration, list[dict]]] = []
        for c in keep:
            layout = _restore_layout_for(c)
            if layout is None:
                continue
            cur = db.query(Probe).filter(Probe.chamber_config_id == c.id).count()
            specs = _build_specs(layout, c.chamber_radius_m or 4.0)
            if cur == 0:
                restore_plan.append((c, specs))
                print(f"  + {c.name}: 恢复 {len(specs)} 探头")
            else:
                print(f"  = {c.name}: 已有 {cur} 探头, 跳过")

        if not apply:
            print("\n[dry-run] 未改库。确认无误后加 --apply 执行。")
            return 0

        # ---- 真正执行 (单事务) ----
        # 1. 先删探头 (避免删暗室时 FK SET NULL 把它们变孤儿后又漏删)
        db.query(Probe).filter(
            or_(Probe.chamber_config_id.is_(None), Probe.chamber_config_id.notin_(keep_ids))
        ).delete(synchronize_session=False)
        # 2. 删暗室
        if drop:
            db.query(ChamberConfiguration).filter(
                ChamberConfiguration.id.in_([c.id for c in drop])
            ).delete(synchronize_session=False)
        # 3. 恢复探头
        for c, specs in restore_plan:
            for s in specs:
                db.add(Probe(
                    chamber_config_id=c.id,
                    probe_number=s["probe_number"],
                    name=f"{c.name} {s['name']}",
                    ring=s["ring"],
                    polarization=s["polarization"],
                    position=s["position"],
                    is_active=True,
                    is_connected=False,
                    status="idle",
                    calibration_status="unknown",
                ))
        db.commit()
        print("\n[apply] 完成。")
        # 复核
        print(f"剩余暗室: {db.query(ChamberConfiguration).count()} | 剩余探头: {db.query(Probe).count()}")
        return 0
    except Exception as e:  # noqa: BLE001
        db.rollback()
        print(f"\n[error] 已回滚: {e}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main(apply="--apply" in sys.argv[1:]))
