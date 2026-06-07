"""Seed the 'CAICT-FS' upper-hemisphere full-sky (满天星) 3D-MPAC chamber.

在现有 CAICT 16 位置双极化暗室基础上, 新增一个**上半球满天星**暗室配置:
仰角 0°→90° 铺一层近似均匀角密度的探头 (方位数按 cos(仰角) 递减), 双极化,
共 31 位置 × 2 极化 = 62 探头通道。支持全 3D 空间信道 (38.901 elevation/ZoD)。

设计详见 docs/design/CAICT-FS-fullsky-chamber.md。

幂等: 若已存在名为 'CAICT-FS' 的 ChamberConfiguration 则跳过 (不重复创建)。
不抢占当前激活暗室 (is_active=False); 激活/绑定见设计文档 §5。

用法:
    cd api-service
    .venv/bin/python scripts/dev-fixtures/seed_caict_fs_chamber.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# 让 `app` 可导入 (parents[2] = api-service), 不依赖 cwd
sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.db.database import SessionLocal
from app.models.chamber import ChamberConfiguration
from app.models.probe import Probe

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("seed_caict_fs")

CHAMBER_NAME = "CAICT-FS"

# 探头环 (自顶向下: ring 1 = 天顶, 跟现有 32-probe 布局 "ring 1 在最高仰角" 约定一致)。
# 方位数按 cos(仰角) 递减 → 球面角密度近似恒定 (满天星); az_offset 做环间交错。
_RING_LAYOUT_FS = [
    {"ring_id": 1, "elevation": 90, "count": 1,  "az_offset": 0.0},   # 天顶
    {"ring_id": 2, "elevation": 60, "count": 6,  "az_offset": 0.0},   # +60° (cos=0.5)
    {"ring_id": 3, "elevation": 30, "count": 12, "az_offset": 15.0},  # +30° (错开 15°)
    {"ring_id": 4, "elevation": 0,  "count": 12, "az_offset": 0.0},   # 地平基环
]

# 暗室 RF 参数 (对齐 Type-D 车载全功能 + 满天星 multi-ring 布局)
CAICT_FS_CHAMBER = dict(
    name=CHAMBER_NAME,
    description=(
        "CAICT 上半球满天星 3D-MPAC 暗室 — 62 探头通道 (31 位置×双极化) 覆盖上半球 "
        "(仰角 0–90°), 支持全 3D 空间信道 (38.901 elevation/ZoD)。"
    ),
    chamber_type="custom",
    is_active=False,  # 不抢占当前激活暗室; 需显式激活/绑定 (见设计文档 §5)
    chamber_radius_m=4.0,
    quiet_zone_diameter_m=1.0,
    # multi-ring 约定 (Codex P1 #154): num_probes = **物理位置数** (去重 (az,el) 后),
    # 而非极化通道数。channel_engine_client._build_probe_positions 去重 V/H 后要求
    # len(unique positions) == num_probes; num_ports = num_probes × 极化 = 62。
    num_probes=31,
    num_polarizations=2,
    num_rings=4,
    probe_distribution="multi-ring",
    has_lna=True,
    lna_gain_db=20.0,
    lna_noise_figure_db=1.5,
    has_pa=True,
    pa_gain_db=20.0,
    pa_p1db_dbm=30.0,
    has_duplexer=True,
    duplexer_isolation_db=25.0,
    duplexer_insertion_loss_db=0.5,
    has_turntable=True,
    turntable_max_load_kg=500.0,
    has_channel_emulator=True,
    ce_bidirectional=True,
    ce_num_ota_ports=62,
    ce_min_input_dbm=-30.0,
    freq_min_mhz=400.0,
    freq_max_mhz=7125.0,
    supports_trp=True,
    supports_tis=True,
    supports_mimo_ota=True,
    typical_cable_loss_db=5.0,
    probe_gain_dbi=8.0,
    is_system_preset=False,
    created_by="seed_caict_fs",
)


def build_fs_probe_specs(radius: float) -> list[dict]:
    """纯函数: 生成 62 个探头规格 (球坐标 + 双极化), 不碰 DB。便于单测几何。"""
    specs: list[dict] = []
    n = 1
    for ring in _RING_LAYOUT_FS:
        count = ring["count"]
        step = 360.0 / count if count else 0.0
        for i in range(count):
            azimuth = round((ring["az_offset"] + i * step) % 360.0, 1)
            for pol in ("V", "H"):
                specs.append(
                    {
                        "probe_number": n,
                        "name": f"Probe {n}-{pol}",
                        "ring": ring["ring_id"],
                        "polarization": pol,
                        "position": {
                            "azimuth": azimuth,
                            "elevation": float(ring["elevation"]),
                            "radius": radius,
                        },
                    }
                )
                n += 1
    return specs


def main() -> int:
    db = SessionLocal()
    try:
        existing = (
            db.query(ChamberConfiguration)
            .filter(ChamberConfiguration.name == CHAMBER_NAME)
            .first()
        )
        if existing is not None:
            n = db.query(Probe).filter(Probe.chamber_config_id == existing.id).count()
            logger.info(
                "[skip] %s 已存在 (id=%s, %d 探头) — 不重复创建", CHAMBER_NAME, existing.id, n
            )
            return 0

        chamber = ChamberConfiguration(**CAICT_FS_CHAMBER)
        db.add(chamber)
        db.flush()  # 拿到 chamber.id

        # probe_number 按 chamber **局部**编号 (1..62); 全局唯一靠 (chamber_config_id,
        # probe_number) 复合键 (uq_probes_chamber_probe_number) 保证, 无需偏移。
        # 人读标识 = 暗室名 + #probe_number, 见 name ("CAICT-FS Probe 1-V")。
        specs = build_fs_probe_specs(chamber.chamber_radius_m)
        for s in specs:
            db.add(
                Probe(
                    chamber_config_id=chamber.id,
                    probe_number=s["probe_number"],
                    name=f"CAICT-FS {s['name']}",
                    ring=s["ring"],
                    polarization=s["polarization"],
                    position=s["position"],
                    is_active=True,
                    is_connected=False,
                    status="idle",
                    calibration_status="unknown",
                )
            )
        db.commit()
        logger.info(
            "[ok] 创建 %s (id=%s) + %d 探头 (上半球满天星, 4 环)",
            CHAMBER_NAME, chamber.id, len(specs),
        )
        return 0
    except Exception as e:  # noqa: BLE001
        logger.exception("seed 失败: %s", e)
        db.rollback()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
