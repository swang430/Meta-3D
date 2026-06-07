"""CAICT-FS 上半球满天星探头布局几何单测 (纯函数, 不碰 DB)。"""
import importlib.util
from pathlib import Path

# 按路径 import dev-fixture 模块 (它在 scripts/dev-fixtures/, 非常规包)
_FIX = (
    Path(__file__).resolve().parents[1]
    / "scripts" / "dev-fixtures" / "seed_caict_fs_chamber.py"
)
_spec = importlib.util.spec_from_file_location("seed_caict_fs_chamber", _FIX)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


class TestCaictFsLayout:
    def test_total_probe_count_62(self):
        assert len(mod.build_fs_probe_specs(4.0)) == 62

    def test_upper_hemisphere_only(self):
        # 满天星只铺上半球: 仰角 ∈ [0, 90]
        assert all(0 <= s["position"]["elevation"] <= 90 for s in mod.build_fs_probe_specs(4.0))

    def test_dual_polarization_split(self):
        specs = mod.build_fs_probe_specs(4.0)
        pols = [s["polarization"] for s in specs]
        assert pols.count("V") == 31
        assert pols.count("H") == 31

    def test_positions_per_elevation(self):
        # 每仰角的探头通道数 (×2 极化): 天顶90→1, 60→6, 30→12, 地平0→12 位置
        counts: dict[float, int] = {}
        for s in mod.build_fs_probe_specs(4.0):
            el = s["position"]["elevation"]
            counts[el] = counts.get(el, 0) + 1
        assert counts == {90.0: 2, 60.0: 12, 30.0: 24, 0.0: 24}

    def test_probe_numbers_unique_and_sequential(self):
        nums = [s["probe_number"] for s in mod.build_fs_probe_specs(4.0)]
        assert nums == list(range(1, 63))

    def test_radius_propagates(self):
        assert all(s["position"]["radius"] == 4.0 for s in mod.build_fs_probe_specs(4.0))

    def test_ring3_staggered_15deg(self):
        # R3 (+30°) 方位偏移 15° 与地平环错开
        r3_az = sorted({
            s["position"]["azimuth"]
            for s in mod.build_fs_probe_specs(4.0)
            if s["position"]["elevation"] == 30.0
        })
        assert r3_az[0] == 15.0  # 偏移 15° 起步

    def test_chamber_spec_consistency(self):
        c = mod.CAICT_FS_CHAMBER
        assert c["name"] == "CAICT-FS"
        assert c["num_probes"] == 62
        assert c["num_polarizations"] == 2
        assert c["num_rings"] == 4
        assert c["probe_distribution"] == "multi-ring"
        assert c["is_active"] is False  # 不抢占当前激活暗室
        assert c["supports_mimo_ota"] is True
