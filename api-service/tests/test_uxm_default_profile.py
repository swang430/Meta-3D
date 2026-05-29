"""P1-17: UXM fresh-start 默认 topology profile 测试.

设计: UXM 走了"快速路"—— fresh-start 时 binding 没选 profile 就空配置 (driver
内部默认 2x2/3500M/-50dBm), 现场得手动 PUT 选。对称 F64 已有的默认 .smu 自动加载,
给 UXM 加"默认 profile fresh-start 自动应用":
  - 新建 caict_n78_3600_4x4 (3600M N78 4x4) 对齐 F64 默认 .smu (3600M N78 4-input)
  - UXM_DEFAULT_TOPOLOGY_PROFILE_ID 常量 + connection_params override
  - _initialize_from_db: binding 无 profile_id → fallback 到 driver._default_topology_profile_id

本测试钉死:
1. 3600M profile 存在 + 频率/MIMO 对齐 F64 默认 (防有人改频率破坏对齐)
2. 默认常量指向存在的 profile
3. driver 默认 attr + config override
4. fallback 语义 (binding 优先, 无则默认)
5. 现有 3500M profile 没被动 (没破坏既有引用)
"""
from __future__ import annotations

from app.hal.uxm_test_profiles import _PROFILE_REGISTRY, _register_builtin_profiles
from app.hal.uxm_base_station import (
    UXM_DEFAULT_TOPOLOGY_PROFILE_ID,
    RealUxmDriver,
)
from app.hal.propsim_f64 import F64_DEFAULT_EMULATION_FILE

# registry 是 module global, import 时填充一次
_register_builtin_profiles()


class TestDefault3600Profile:
    def test_3600_profile_in_registry(self):
        assert "caict_n78_3600_4x4" in _PROFILE_REGISTRY
        p = _PROFILE_REGISTRY["caict_n78_3600_4x4"]
        assert p.frequency_mhz == 3600.0
        assert p.mimo_layers == 4
        assert p.band == "N78"
        assert p.mimo_port_preset == "4x4"

    def test_default_profile_freq_aligns_f64_default(self):
        # 核心对齐: UXM 默认 profile 频率必须跟 F64 默认 .smu 同频 (3600M),
        # 否则 fresh-start 一键就位会配出 BS 3600 / CE 另一频的打架链路。
        # F64 默认 .smu 路径含 "3600M"; profile 频率 == 3600。
        p = _PROFILE_REGISTRY["caict_n78_3600_4x4"]
        assert p.frequency_mhz == 3600.0
        assert "3600M" in F64_DEFAULT_EMULATION_FILE


class TestDefaultConstant:
    def test_default_const_points_to_3600_profile(self):
        assert UXM_DEFAULT_TOPOLOGY_PROFILE_ID == "caict_n78_3600_4x4"

    def test_default_const_is_a_real_profile(self):
        # 常量必须指向 registry 里真实存在的 profile (防 typo / 删 profile 后常量悬空)
        assert UXM_DEFAULT_TOPOLOGY_PROFILE_ID in _PROFILE_REGISTRY


class TestDriverDefaultAttr:
    def test_driver_default_attr_is_const(self):
        # binding 没传 config override → driver 默认 = 系统常量
        drv = RealUxmDriver("uxm-test", {})
        assert drv._default_topology_profile_id == UXM_DEFAULT_TOPOLOGY_PROFILE_ID

    def test_driver_config_override(self):
        # operator 经 connection_params["default_topology_profile_id"] 覆盖
        # (对称 F64 default_emulation_file override)
        drv = RealUxmDriver(
            "uxm-test", {"default_topology_profile_id": "caict_n78_2x2"}
        )
        assert drv._default_topology_profile_id == "caict_n78_2x2"


class TestFallbackSemantics:
    """复现 _initialize_from_db 的 fallback 表达式:
    topology_id = binding_id or getattr(driver, "_default_topology_profile_id", None)
    钉死 "binding 显式选优先, 没选才用默认"。
    """

    def test_fallback_to_default_when_binding_empty(self):
        drv = RealUxmDriver("uxm-test", {})
        binding_id = None  # binding 没选 profile
        resolved = binding_id or getattr(drv, "_default_topology_profile_id", None)
        assert resolved == "caict_n78_3600_4x4"

    def test_binding_profile_takes_priority_over_default(self):
        drv = RealUxmDriver("uxm-test", {})
        binding_id = "caict_n78_2x2"  # binding 显式选
        resolved = binding_id or getattr(drv, "_default_topology_profile_id", None)
        assert resolved == "caict_n78_2x2"  # 不被默认覆盖


class TestExistingProfilesUnchanged:
    def test_existing_4x4_still_3500(self):
        # 没动现有 caict_n78_4x4 (3500M) — 其它引用/测试可能依赖
        p = _PROFILE_REGISTRY["caict_n78_4x4"]
        assert p.frequency_mhz == 3500.0

    def test_registry_has_8_profiles(self):
        # 7 原有 + 1 新 (caict_n78_3600_4x4)
        assert len(_PROFILE_REGISTRY) == 8
