from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.hal.base_station_mac_profile import (
    FrozenMacTestProfile,
    LteRmcMacTestProfileV1,
    MacMetricRequirement,
    MacStatisticalWindow,
    NrMacTestProfileV1,
)
from app.schemas.mimo_ota.config import (
    MIMOOTAConfiguration,
    canonicalize_mimo_ota_configuration_payload,
)
from app.hal.uxm_test_profiles import UxmTopologyProfile


def _nr_profile(**updates) -> NrMacTestProfileV1:
    payload = {
        "schema_version": 1,
        "kind": "nr_throughput",
        "profile_version": 1,
        "rat": "nr5g",
        "test_intent": "downlink_throughput",
        "mimo_layers": 2,
        "statistical_window": {"unit": "subframes", "count": 5000},
        "metric_requirements": [
            {"key": "dl_throughput_mbps", "scope": "pcell"}
        ],
        "rb_allocation": "all",
        "scheduler_algorithm": "full_throughput",
        "mcs": 28,
        "enable_amc": False,
        "tdd_pattern": "DDDDDDDSUU",
        "tdd_period": "5MS",
        "harq_max_trans": 4,
        "harq_processes": 16,
        "subcarrier_spacing_khz": 30,
        "csi_rs_ports": 4,
        "source_reference": (
            "Instrument_API_Doc/Keysight UXM NR SCPI/"
            "5G_NR_Test_Application_SCPI_Reference.zip"
        ),
    }
    payload.update(updates)
    return NrMacTestProfileV1.model_validate(payload)


def _lte_profile(**updates) -> LteRmcMacTestProfileV1:
    payload = {
        "schema_version": 1,
        "kind": "lte_rmc",
        "profile_version": 1,
        "rat": "lte",
        "test_intent": "downlink_throughput",
        "mimo_layers": 2,
        "statistical_window": {"unit": "subframes", "count": 5000},
        "metric_requirements": [
            {"key": "dl_throughput_mbps", "scope": "pcell"},
            {"key": "dl_bler_percent", "scope": "pcell"},
        ],
        "scheduling_mode": "rmc",
        "resource_allocation": "full",
        "enable_amc": False,
        "duplex": "fdd",
        "transmission_mode": "TM3",
        "source_reference": (
            "Instrument_API_Doc/R&S CMW500/"
            "CMW_LTE_UE_UserManual_V4-0-250_en_41 (2).pdf"
        ),
    }
    payload.update(updates)
    return LteRmcMacTestProfileV1.model_validate(payload)


def _lte_pcell() -> dict:
    return {
        "radio_technology": "lte",
        "frequency_hz": 1_815_000_000.0,
        "bandwidth_mhz": 20.0,
        "subcarrier_spacing_khz": None,
        "band": "B3",
        "duplex": "fdd",
        "lte_dl_earfcn": 1300,
        "lte_transmission_mode": "TM3",
        "role": "pcell",
    }


def test_profile_models_are_frozen_and_digest_covers_nested_truth():
    profile = _nr_profile()
    frozen = FrozenMacTestProfile.freeze(profile)

    assert frozen.profile.kind == "nr_throughput"
    assert frozen.profile_digest
    assert frozen == FrozenMacTestProfile.model_validate(frozen.model_dump(mode="json"))
    with pytest.raises(ValidationError):
        frozen.profile.mcs = 10

    changed = FrozenMacTestProfile.freeze(
        profile.model_copy(
            update={
                "statistical_window": MacStatisticalWindow(
                    unit="subframes", count=6000
                )
            }
        )
    )
    assert changed.profile_digest != frozen.profile_digest


def test_metric_requirements_are_nonempty_unique_stable_keys():
    with pytest.raises(ValidationError):
        _nr_profile(metric_requirements=[])
    with pytest.raises(ValidationError):
        _nr_profile(
            metric_requirements=[
                MacMetricRequirement(key="dl_throughput_mbps", scope="pcell"),
                MacMetricRequirement(key="dl_throughput_mbps", scope="pcell"),
            ]
        )
    with pytest.raises(ValidationError):
        _nr_profile(
            metric_requirements=[
                {"key": "fabricated_metric", "scope": "pcell"}
            ]
        )
    with pytest.raises(ValidationError):
        _lte_profile(
            metric_requirements=[
                {"key": "dl_throughput_mbps", "scope": "pcell"}
            ]
        )


def test_nr_and_lte_profiles_reject_each_others_fields():
    with pytest.raises(ValidationError):
        _nr_profile(transmission_mode="TM3")
    with pytest.raises(ValidationError):
        _lte_profile(mcs=28)
    with pytest.raises(ValidationError):
        _lte_profile(tdd_pattern="DDDDDDDSUU")
    with pytest.raises(ValidationError):
        _lte_profile(harq_processes=16)
    with pytest.raises(ValidationError):
        _lte_profile(subcarrier_spacing_khz=30)
    with pytest.raises(ValidationError):
        _lte_profile(csi_rs_ports=4)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("mcs", 31),
        ("enable_amc", True),
        ("mimo_layers", 3),
        ("mimo_layers", 5),
        ("tdd_pattern", ""),
        ("tdd_pattern", "DUS"),
        ("tdd_period", "BANANA"),
        ("harq_max_trans", 9),
        ("harq_processes", 3),
        ("subcarrier_spacing_khz", 20),
        ("csi_rs_ports", 3),
    ),
)
def test_nr_profile_rejects_values_outside_the_audited_uxm_domain(field, value):
    with pytest.raises(ValidationError):
        _nr_profile(**{field: value})


def test_nr_profile_rejects_tdd_pattern_that_does_not_fill_its_period():
    with pytest.raises(ValidationError, match="TDD pattern duration"):
        _nr_profile(
            tdd_pattern="DDDSU",
            tdd_period="5MS",
            subcarrier_spacing_khz=30,
        )

    assert _nr_profile(
        tdd_pattern="DDDSU",
        tdd_period="2.5MS",
        subcarrier_spacing_khz=30,
    ).tdd_pattern == "DDDSU"


@pytest.mark.parametrize("layers", (1, 2, 4))
def test_nr_profile_accepts_only_audited_uxm_mimo_layers(layers):
    assert _nr_profile(mimo_layers=layers).mimo_layers == layers


def test_topology_profile_cannot_recreate_the_removed_kwargs_mac_spi():
    assert not hasattr(UxmTopologyProfile, "to_mac_throughput_kwargs")


def test_lte_v1_is_the_existing_narrow_fdd_fixed_rmc_shape():
    assert _lte_profile().model_dump(mode="json") == {
        "schema_version": 1,
        "kind": "lte_rmc",
        "profile_version": 1,
        "rat": "lte",
        "test_intent": "downlink_throughput",
        "mimo_layers": 2,
        "statistical_window": {"unit": "subframes", "count": 5000},
        "metric_requirements": [
            {"key": "dl_throughput_mbps", "scope": "pcell"},
            {"key": "dl_bler_percent", "scope": "pcell"},
        ],
        "scheduling_mode": "rmc",
        "resource_allocation": "full",
        "enable_amc": False,
        "duplex": "fdd",
        "transmission_mode": "TM3",
        # P2-56：TDD 专属维度存在于 schema（能力矩阵的维度名必须是真实字段），
        # 但只接受 None —— 取值域声明在 CMW500 矩阵里，下发路径未实现。
        "uldl_configuration": None,
        "special_subframe": None,
        "rmc_version": None,
        "source_reference": (
            "Instrument_API_Doc/R&S CMW500/"
            "CMW_LTE_UE_UserManual_V4-0-250_en_41 (2).pdf"
        ),
    }
    with pytest.raises(ValidationError):
        _lte_profile(enable_amc=True)
    with pytest.raises(ValidationError):
        _lte_profile(duplex="tdd")
    with pytest.raises(ValidationError):
        _lte_profile(mimo_layers=4)


def test_legacy_nr_flat_fields_migrate_to_one_canonical_profile():
    raw = {
        "mimo_layers": 4,
        "mcs": 19,
        "enable_amc": False,
        "tdd_pattern": "DDDDDDDSUU",
        "tdd_period": "5MS",
        "harq_max_trans": 3,
        "harq_processes": 8,
        "stat_count": 6000,
        "sched_algo": "FULLBUFFER",
        "csi_rs_ports": 8,
    }

    config = MIMOOTAConfiguration.model_validate(raw)

    assert config.mac_profile.profile.kind == "nr_throughput"
    assert config.mac_profile.profile.mimo_layers == 4
    assert config.mac_profile.profile.mcs == 19
    assert config.mac_profile.profile.harq_processes == 8
    assert config.mac_profile.profile.statistical_window.count == 6000
    assert config.mac_profile.profile.scheduler_algorithm == "full_throughput"
    assert config.mac_profile.profile.csi_rs_ports == 8

    canonical = canonicalize_mimo_ota_configuration_payload(raw)
    assert "mac_profile" in canonical
    for legacy in (
        "mcs",
        "enable_amc",
        "tdd_pattern",
        "tdd_period",
        "harq_max_trans",
        "harq_processes",
        "stat_count",
        "sched_algo",
        "csi_rs_ports",
    ):
        assert legacy not in canonical


@pytest.mark.parametrize(("layers", "expected_ports"), [(1, 2), (4, 8)])
def test_legacy_nr_missing_csi_ports_preserves_layer_derived_default(
    layers,
    expected_ports,
):
    config = MIMOOTAConfiguration.model_validate({"mimo_layers": layers})

    assert config.mac_profile.profile.csi_rs_ports == expected_ports


def test_explicit_profile_rejects_conflicting_legacy_mac_value():
    canonical = canonicalize_mimo_ota_configuration_payload({"mcs": 28})
    canonical["mcs"] = 21

    with pytest.raises(ValidationError, match="mac_profile.*mcs"):
        MIMOOTAConfiguration.model_validate(canonical)


def test_explicit_lte_profile_rejects_nr_only_legacy_mac_value():
    canonical = canonicalize_mimo_ota_configuration_payload(
        {
            "component_carriers": [_lte_pcell()],
            "mimo_layers": 2,
        }
    )
    canonical["mcs"] = 28

    with pytest.raises(ValidationError, match="mac_profile.*mcs"):
        MIMOOTAConfiguration.model_validate(canonical)


def test_legacy_lte_migrates_without_nr_only_fields():
    raw = {
        "component_carriers": [_lte_pcell()],
        "mimo_layers": 2,
        "enable_amc": False,
        "stat_count": 10_000,
        # Historical universal fields may exist but are not LTE semantics.
        "mcs": 28,
        "tdd_pattern": "DDDDDDDSUU",
        "harq_processes": 16,
        "csi_rs_ports": 4,
    }

    profile = MIMOOTAConfiguration.model_validate(raw).mac_profile.profile

    assert profile.kind == "lte_rmc"
    assert profile.statistical_window.count == 10_000
    dumped = profile.model_dump(mode="json")
    for nr_only in (
        "mcs",
        "tdd_pattern",
        "harq_processes",
        "subcarrier_spacing_khz",
        "csi_rs_ports",
    ):
        assert nr_only not in dumped


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update({"rat": "lte"}),
        lambda p: p.update({"mimo_layers": 4}),
        lambda p: p.update({"subcarrier_spacing_khz": 15}),
    ],
)
def test_explicit_nr_profile_must_match_pcell_and_common_intent(mutate):
    profile = _nr_profile().model_dump(mode="json")
    mutate(profile)
    with pytest.raises(ValidationError):
        MIMOOTAConfiguration.model_validate(
            {
                "mimo_layers": 2,
                "subcarrier_spacing_khz": 30,
                "mac_profile": FrozenMacTestProfile.freeze(
                    NrMacTestProfileV1.model_validate(profile)
                ).model_dump(mode="json"),
            }
        )


def test_explicit_lte_profile_must_match_pcell_tm_and_duplex():
    base = {
        "component_carriers": [_lte_pcell()],
        "mimo_layers": 2,
    }
    for update in (
        {"transmission_mode": "TM4"},
        {"duplex": "tdd"},
        {"mimo_layers": 1},
    ):
        with pytest.raises(ValidationError):
            profile = _lte_profile().model_copy(update=update)
            raw = deepcopy(base)
            raw["mac_profile"] = FrozenMacTestProfile.freeze(profile).model_dump(
                mode="json"
            )
            MIMOOTAConfiguration.model_validate(raw)


def test_explicit_profile_digest_tampering_is_rejected():
    frozen = FrozenMacTestProfile.freeze(_nr_profile()).model_dump(mode="json")
    frozen["profile_digest"] = "0" * 64

    with pytest.raises(ValidationError):
        MIMOOTAConfiguration.model_validate({"mac_profile": frozen})


@pytest.mark.parametrize(
    "field",
    [
        "mimo_layers",
        "stat_count",
        "tdd_pattern",
        "tdd_period",
        "mcs",
        "enable_amc",
        "harq_max_trans",
        "harq_processes",
    ],
)
def test_legacy_nr_explicit_null_is_rejected_not_crashed(field):
    """显式 null 必须走受控的字段级拒绝，不能崩在校验之前。

    `data.get(k, default)` 只对「键缺失」回退默认值；键存在但值为 null 时拿到的
    是 None。曾经 mimo_layers / tdd_pattern 的 None 会先参与派生计算，分别以
    TypeError 和 AttributeError 崩掉——那既不是受控拒绝，报错也指不到字段。

    这里不把 null 当作「没写」去补默认值：那是从非法形态补真。这八个字段一律拒绝。
    唯一的例外是 csi_rs_ports——它本来就有「不给就从层数派生」的语义，见下一个用例。

    ⚠️ 故意**不给** csi_rs_ports：给了它就走显式分支，`max(2, layers * 2)` 这条
    派生路径永远不执行，mimo_layers=None 便碰不到那处乘法，守卫失效也抓不出来。
    """
    raw = {
        "mimo_layers": 4,
        "mcs": 19,
        "enable_amc": False,
        "tdd_pattern": "DDDDDDDSUU",
        "tdd_period": "5MS",
        "harq_max_trans": 3,
        "harq_processes": 8,
        "stat_count": 6000,
    }
    MIMOOTAConfiguration.model_validate(deepcopy(raw))  # 对照：不含 null 时通过

    raw[field] = None
    with pytest.raises(ValidationError):
        MIMOOTAConfiguration.model_validate(raw)


def test_legacy_nr_pattern_whitespace_matches_model_normalization():
    """周期推导必须与模型的 strip().upper() 规范化同源。

    推导发生在 mode="before" 的 validator 之前。不 strip 的话，
    `" DDDDDDDSUU "` 会按 12 个时隙算出 6 ms 而被拒；可同一个值配上显式
    tdd_period 却能通过、并被规范化成 10 个时隙——同一输入两种结论。
    """
    spaced = {
        "component_carriers": [
            {
                "radio_technology": "nr5g",
                "subcarrier_spacing_khz": 30,
                "frequency_hz": 3.5e9,
                "bandwidth_mhz": 100.0,
            }
        ],
        "tdd_pattern": " DDDDDDDSUU ",
    }

    derived = MIMOOTAConfiguration.model_validate(deepcopy(spaced))
    assert derived.mac_profile.profile.tdd_pattern == "DDDDDDDSUU"
    assert derived.mac_profile.profile.tdd_period == "5MS"

    explicit = dict(spaced, tdd_period="5MS")
    assert (
        MIMOOTAConfiguration.model_validate(explicit).mac_profile.profile.tdd_period
        == derived.mac_profile.profile.tdd_period
    )


def test_legacy_nr_null_csi_rs_ports_means_derive_from_layers():
    """csi_rs_ports 是唯一把 null 当「未指定」的字段，这是既有设计不是漏网。

    端口数可以**故意**大于层数，所以显式值优先；不给（缺失或 null）时按
    max(2, layers * 2) 派生。与上一个用例里那八个字段的语义不同，不要合并。
    """
    raw = {
        "mimo_layers": 4,
        "mcs": 19,
        "enable_amc": False,
        "tdd_pattern": "DDDDDDDSUU",
        "tdd_period": "5MS",
        "harq_max_trans": 3,
        "harq_processes": 8,
        "stat_count": 6000,
    }

    omitted = MIMOOTAConfiguration.model_validate(deepcopy(raw))
    explicit_null = MIMOOTAConfiguration.model_validate(dict(raw, csi_rs_ports=None))
    explicit_value = MIMOOTAConfiguration.model_validate(dict(raw, csi_rs_ports=16))

    assert omitted.mac_profile.profile.csi_rs_ports == 8  # max(2, 4 * 2)
    assert explicit_null.mac_profile.profile.csi_rs_ports == 8
    assert explicit_value.mac_profile.profile.csi_rs_ports == 16


def _sparse_nr_legacy_row() -> dict:
    """稀疏 legacy NR 行：**故意不带 tdd_period**。

    推导分支只在 tdd_period 缺席时才执行，而真实旧行正是这个形态（推导存在的
    理由就是 period 通常没写）。基线里放了 tdd_period 的用例走不进推导，
    那一段守卫便无人看守。
    """
    return {
        "mimo_layers": 4,
        "mcs": 19,
        "enable_amc": False,
        "tdd_pattern": "DDDDDDDSUU",
        "harq_max_trans": 3,
        "harq_processes": 8,
        "stat_count": 6000,
    }


@pytest.mark.parametrize("field", ["tdd_pattern", "subcarrier_spacing_khz"])
def test_legacy_nr_null_derivation_input_is_rejected_not_crashed(field):
    """周期推导的两个输入为 null 时，同样要受控拒绝而不是崩在校验之前。

    这两格与上面那批的区别是它们**先被读去推导**：null 会以
    AttributeError（`None.strip()`）或 TypeError（`None in dict`）
    崩掉，报错既不受控也指不到字段。
    """
    MIMOOTAConfiguration.model_validate(_sparse_nr_legacy_row())  # 对照：推导分支可通过

    raw = _sparse_nr_legacy_row()
    raw[field] = None
    with pytest.raises(ValidationError):
        MIMOOTAConfiguration.model_validate(raw)


@pytest.mark.parametrize(
    "field, value, expected",
    [
        ("mimo_layers", 4.0, 4),
        ("subcarrier_spacing_khz", 30.0, 30),
    ],
)
def test_legacy_nr_float_shaped_numbers_stay_accepted(field, value, expected):
    """派生守卫的受理域必须与下游 schema 同源，不能更窄。

    pydantic 的 lax 模式把 4.0 / 30.0 归一成 int，所以它们本来就能进
    `Literal[1, 2, 4]` 与 `Literal[15, 30, 60, 120]`。守卫若只认 `int`，
    这些值就会「好到能进 schema，却不够格参与派生」——那是回归不是收紧。
    现场脚本 scripts/onsite-run-channel-throughput.sh 把 LAYERS 裸插值进
    JSON，`LAYERS=4.0` 正是这个形态。
    """
    raw = _sparse_nr_legacy_row()
    raw[field] = value

    profile = MIMOOTAConfiguration.model_validate(raw).mac_profile.profile

    assert getattr(profile, field) == expected
    assert profile.tdd_period == "5MS"  # 推导仍然跑通


@pytest.mark.parametrize("value", [[], {}, "30"])
def test_legacy_nr_unhashable_scs_is_rejected_not_crashed(value):
    """SCS 为不可哈希的值时也要受控拒绝。

    推导里有 `scs_khz in UXM_NR_SLOT_DURATION_MS` 这一步，list / dict 会在那儿
    炸 `TypeError: unhashable type`——这正是守卫要挡的那一格。None 与字符串
    走到推导函数自己的域检查，本来就受控；不可哈希的这两种不行。
    """
    raw = _sparse_nr_legacy_row()
    raw["subcarrier_spacing_khz"] = value

    with pytest.raises(ValidationError):
        MIMOOTAConfiguration.model_validate(raw)


@pytest.mark.parametrize("field", ["mimo_layers", "subcarrier_spacing_khz"])
def test_legacy_nr_bool_is_rejected_not_silently_coerced(field):
    """bool 是 int 的子类，必须显式排除。

    否则 `mimo_layers: true` 会被静默当成 1 层、csi_rs_ports 派生成 2，
    而 `profile.mimo_layers != self.mimo_layers` 那道跨检也不会红——
    两边都被归一成 1，看起来一致。静默改测试条件比报错更糟。
    """
    raw = _sparse_nr_legacy_row()
    raw[field] = True

    with pytest.raises(ValidationError):
        MIMOOTAConfiguration.model_validate(raw)
