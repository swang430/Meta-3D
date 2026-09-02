# -*- coding: utf-8 -*-
"""P2-56：LTE TDD 侧能力矩阵的门。

本片**只加声明，不加可达状态** —— profile 的 `duplex` 仍是 `Literal["fdd"]`，
三个 TDD 字段只接受 `None`。所以这里的门分两类：

- **内容门**：矩阵声明的取值域 / 选件 / 固件下限 / 前置约束 = 手册原文；
- **不变量门**：新维度不会脱离门的覆盖、不会脱离 profile 的字段集、
  不会把已冻结的 digest 弄漂。

⚠️ P2-55 的内容门硬编码在 `("transmission_mode", "mimo_layers")` 两个维度上，
   新维度**不在它们的覆盖里**。`test_every_declared_dimension_is_gated`
   就是为此存在的：加第七个维度而不给它门，会当场变红。
"""

import pathlib
import re

import pytest
from pydantic import ValidationError

from app.hal.base_station_manifest import (
    BaseStationMacDimensionCapability,
    BaseStationMacDimensionValueCapability,
)
from app.hal.base_station_mac_profile import (
    CMW500_LTE_PROFILE_SOURCE,
    FrozenMacTestProfile,
    LteRmcMacTestProfileV1,
    NrMacTestProfileV1,
)
from app.hal.cmw500_base_station import RealCmw500Driver


_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


CMW_MANUAL = CMW500_LTE_PROFILE_SOURCE

# P2-55 已经逐格盯住的维度 —— **从它自己的模块导入**，不手抄字面量：
# 覆盖不变量的这一端必须是「P2-55 实际盯了哪些」，不是「我记得它盯了哪些」
# （内审 F6：原来两边各写一份，靠手抄同步，没有门维持一致）。
from tests.test_p2_55_capability_matrix import GATED_DIMENSIONS

P2_55_GATED = set(GATED_DIMENSIONS)
# 本片盯住的四个。
P2_56_GATED = {"duplex", "uldl_configuration", "special_subframe", "rmc_version"}


def _dimensions():
    return {
        dimension.dimension: dimension
        for profile in RealCmw500Driver.adapter_manifest.mac_profiles
        for dimension in profile.dimensions
    }


def _values(name):
    """取值 → 声明。

    ⚠️ 键是**裸值**，方便下面按 `{None, 0, 1, ...}` 直接断言取值域。但裸值键
    会把 `False` 与 `0` 并成一格（Python 里两者相等且同哈希）—— 生产侧正是
    为此用 `(type(v), v)` 做键。所以这里显式验一次没有碰撞：否则往矩阵里插
    一格伪造的 `value=False` 声明能逃过本文件**全部**内容门（内审 F2）。
    """
    values = _dimensions()[name].values
    out = {item.value: item for item in values}
    assert len(out) == len(values), (
        f"{name} 的取值在裸值键下发生碰撞（bool 与 int 同键？）："
        f"{[item.value for item in values]}"
    )
    return out


# --------------------------------------------------------------------------
# 1. 不变量：门的覆盖面 / 维度名 / digest
# --------------------------------------------------------------------------


def test_every_declared_dimension_is_gated():
    """声明的维度集合 == 有门盯着的维度集合。

    这是**集合相等**不变量，不是"至少覆盖"：P2-55 的内容门把维度名写死在
    循环里，加一个新维度不会让任何门变红 —— 它会静悄悄地一格证据都不被检查。
    本片新增四个维度时就正是这个处境。
    """
    assert set(_dimensions()) == P2_55_GATED | P2_56_GATED


def test_every_dimension_name_is_a_real_profile_field():
    """维度名必须是 profile 上**真实存在的字段**。

    判定器按 `dimension in type(profile).model_fields` 取值
    （base_station_compatibility._mac_dimension_rejections），声明一个 profile
    没有的维度会走进「声明与 schema 脱节」那一格，把**每一条** LTE profile
    判成不兼容 —— 不是这个维度失效，是整个 adapter 失效。

    这条门把那个耦合变成构建期错误：本片正是因为先量到了它，才没有把
    `uldl_configuration` 直接写进矩阵了事。
    """
    fields = set(LteRmcMacTestProfileV1.model_fields)
    missing = set(_dimensions()) - fields
    assert not missing, f"矩阵声明了 profile 上不存在的维度：{sorted(missing)}"


@pytest.mark.parametrize(
    "model, payload, expected",
    [
        (
            LteRmcMacTestProfileV1,
            {
                "schema_version": 1, "kind": "lte_rmc", "profile_version": 1,
                "rat": "lte", "test_intent": "downlink_throughput",
                "mimo_layers": 2,
                "statistical_window": {"unit": "subframes", "count": 5000},
                "metric_requirements": [
                    {"key": "dl_throughput_mbps", "scope": "pcell"},
                    {"key": "dl_bler_percent", "scope": "pcell"},
                ],
                "scheduling_mode": "rmc", "resource_allocation": "full",
                "enable_amc": False, "duplex": "fdd",
                "transmission_mode": "TM3",
                "source_reference": CMW_MANUAL,
            },
            "6c0ebb0e0e31e5c41200024708cb8cdca54eb0a3a1ebdfba9ca038fbcf9e59b6",
        ),
    ],
)
def test_profile_digest_is_pinned_across_the_new_optional_fields(
    model, payload, expected
):
    """profile digest 钉到**加新字段之前** main 上的值。

    本片给 LTE profile 加了三个可选字段。若 digest 口径不是 omit-when-None，
    这三个 `None` 会进 payload，让**所有升级前冻结的 profile** 重算出不同的
    digest —— `FrozenMacTestProfile` 当场自我拒绝，历史 TestCase 配置整体
    加载不了。这条门同时锁住两件事：

    ① `_profile_payload_digest` 用的是 `exclude_none=True`；
    ② `freeze()` 与 `_digest_matches_profile()` 走的是**同一个**口径 ——
       两处各写一次 `model_dump` 时，只给一处加 exclude_none 会让每一条
       新冻结的 profile 自我拒绝。下面两个断言分别打在这两条路径上。

    ⚠️ 不要直接改这里的期望值：它变红意味着已冻结的历史 profile 会全部失配。
    """
    validated = model.model_validate(payload)
    frozen = FrozenMacTestProfile.freeze(validated)
    assert frozen.profile_digest == expected

    from app.hal.base_station_mac_profile import _canonical_digest

    assert frozen.profile_digest == _canonical_digest(
        validated.model_dump(mode="json", exclude_none=True)
    )

    # 历史 payload（不带本片新增的键）必须原样通过校验
    revalidated = FrozenMacTestProfile.model_validate(
        {"profile": payload, "profile_digest": expected}
    )
    assert revalidated.profile_digest == expected


def test_profile_digest_omits_none_not_defaults():
    """直接钉住 digest 的**口径**是 `exclude_none`，不是 `exclude_defaults`（内审 F4）。

    只钉 hex 值钉不住：把 `exclude_none=True` 换成 `exclude_defaults=True`
    时全部门仍绿 —— 今天两者在真实 profile 上完全等价（唯一带默认值的字段
    就是本片那三个 `None`）。但两者语义不同：只要将来任何字段拿到一个
    **非 None 的默认值**，`exclude_defaults` 就会在该字段取默认值时静默丢键，
    让两条本该不同的 profile 算出同一个 digest。

    所以用一个**带非 None 默认值**的合成模型去问 `_profile_payload_digest`
    ——这是今天唯一能把两种口径区分开的输入。
    """
    from pydantic import BaseModel

    from app.hal.base_station_mac_profile import (
        _canonical_digest,
        _profile_payload_digest,
    )

    class _Probe(BaseModel):
        kept_default: int = 5      # exclude_defaults 会丢掉它，exclude_none 不会
        kept_value: str = "x"
        dropped_none: None = None  # 两种口径都该丢掉

    assert _profile_payload_digest(_Probe()) == _canonical_digest(
        {"kept_default": 5, "kept_value": "x"}
    )
    # 反向：确认它确实**不**等于 exclude_defaults 的结果，否则上面那条恒真
    assert _profile_payload_digest(_Probe()) != _canonical_digest({})


def test_nr_profile_digest_is_untouched_by_the_lte_change():
    """NR 侧 digest 不因本片漂移（改的是共享的 digest 口径，必须两边都验）。"""
    payload = {
        "schema_version": 1, "kind": "nr_throughput", "profile_version": 1,
        "rat": "nr5g", "test_intent": "downlink_throughput", "mimo_layers": 2,
        "statistical_window": {"unit": "subframes", "count": 2000},
        "metric_requirements": [{"key": "dl_throughput_mbps", "scope": "pcell"}],
        "rb_allocation": "all", "scheduler_algorithm": "full_throughput",
        "mcs": 27, "enable_amc": False, "tdd_pattern": "DDDSU",
        "tdd_period": "2.5MS", "harq_max_trans": 4, "harq_processes": 16,
        "subcarrier_spacing_khz": 30, "csi_rs_ports": 4,
        "source_reference": (
            "Instrument_API_Doc/Keysight UXM NR SCPI/"
            "5G_NR_Test_Application_SCPI_Reference.zip"
        ),
    }
    frozen = FrozenMacTestProfile.freeze(
        NrMacTestProfileV1.model_validate(payload)
    )
    assert frozen.profile_digest == (
        "2aa1dc7992598591e9436fb152ed7d30aa5d9413f789be6e64f5be61a7df0f68"
    )


# --------------------------------------------------------------------------
# 2. 内容 = 手册原文
# --------------------------------------------------------------------------


def test_duplex_matrix_matches_dmode_range():
    """DMODe Range `FDD | TDD`（p.366）两格都在，P2-56 ② 起两格都是正式路径。

    ① 声明半时 `tdd` 是 `diagnostic_only`，理由写的是「缺本驱动的实现」；
    ② 把实现补上了（活体/profile duplex 比对 + ULDL / SSUBframe /〔歧义带宽〕
    RMC:VERSion:DL 逐条下发回读），该理由不再成立，故上调。
    """
    values = _values("duplex")
    assert set(values) == {"fdd", "tdd"}
    assert values["fdd"].support == "authoritative"
    assert values["tdd"].support == "authoritative"
    # Options 原文「R&S CMW-KS500/-KS550 for FDD/TDD」——两侧各要一个，
    # 是 OR 语义（该侧装上那一个即可），不是 AND
    assert values["fdd"].satisfying_options == ("KS500",)
    assert values["tdd"].satisfying_options == ("KS550",)
    assert not values["fdd"].required_options
    assert not values["tdd"].required_options


#: 手册 Options 栏写「A **or** B」的维度 —— 只有它们该用 `satisfying_options`。
#: 其余维度要么是 AND（`required_options`），要么没有选件要求。
OR_SIDE_DIMENSIONS = {"duplex", "transmission_mode", "mimo_layers"}


def test_or_side_partition_is_not_a_free_label():
    """划分表本身要被验：只有**真的挂了 OR 选件**的维度才准列进去。

    两条纪律门都是「某个字段必须为空」，所以一个**今天没有任何选件**的维度
    （如 `rmc_version`）划到哪一侧都全绿 —— 划错了也看不出来，等哪天给它补上
    选件，它已经坐在错误的那一侧（内审 R3 F3 实测：把 `rmc_version` 塞进
    OR 侧 → 32 passed）。而分错侧正是本片立 `required_options` 要治的方向。
    """
    with_or = {
        name
        for name, dimension in _dimensions().items()
        if any(item.satisfying_options for item in dimension.values)
    }
    assert OR_SIDE_DIMENSIONS == with_or, (
        "OR 侧划分表与矩阵实况不符：只有真的声明了 satisfying_options 的"
        f"维度才准列进去，实况是 {sorted(with_or)}"
    )


@pytest.mark.parametrize(
    "name",
    sorted(set(_dimensions()) - OR_SIDE_DIMENSIONS),
)
def test_and_side_dimensions_keep_the_or_field_empty(name):
    """AND 语义的维度不得同时挂 OR 选件（内审 R1 F3 / R2 F1）。

    原来只有 ULDL 有这条断言，于是 `special_subframe` / `rmc_version` 可以
    凭空多一个 `satisfying_options` 而没有任何门变红 —— 而本片立
    `required_options` 的理由，正是「用 OR 存『与』会把只装 KS550 的整机
    判成支持」。判据两侧都要守，只守一侧等于没守。

    ⚠️ 作用域取**矩阵全集减去 OR 侧维度**，不是「本片新加的那几个」——
    与固件门同因（用「我做到的」当全集）。新增一个 AND 侧维度会自动被纳入。
    """
    for value, item in _values(name).items():
        assert not item.satisfying_options, (
            f"{name}={value!r} 的选件是 AND 语义，不该出现在 OR 字段里"
        )


@pytest.mark.parametrize("name", sorted(OR_SIDE_DIMENSIONS))
def test_or_side_dimensions_keep_the_and_field_empty(name):
    """反方向同理：手册写「or」的维度不得把选件塞进 AND 字段。

    没有这条时，给 `mimo_layers=4` 塞一个 `required_options=("KS999",)`
    全绿（内审 R2 F1 的 MU2）。
    """
    for value, item in _values(name).items():
        assert not item.required_options, (
            f"{name}={value!r} 的选件是 OR 语义，不该出现在 AND 字段里"
        )


def test_uldl_uses_and_options_not_or():
    """ULDL 的选件是「A **and** B」，必须存进 `required_options`。

    手册原文 `R&S CMW-KS550 and R&S CMW-KS510`。存进 `satisfying_options`
    会把只装了 KS550 的整机声明成支持 ULDL —— 反方向的假信息。
    这条门是本片三个新字段里**最容易被写回旧字段**的一格。
    """
    values = _values("uldl_configuration")
    assert set(values) == {None, 0, 1, 2, 3, 4, 5, 6}, "Range `0 to 6` + 未设"
    for value, item in values.items():
        if value is None:
            continue
        assert sorted(item.required_options) == ["KS510", "KS550"], value
        assert not item.satisfying_options, (
            f"ULDL={value} 的 AND 选件被存进了 OR 字段"
        )


def test_per_value_firmware_floors_match_the_manual_firmware_lines():
    """逐值固件下限 = 手册 Firmware 行，按**取值分组**断言集合相等。

    ULDL：`V3.0.10, V3.0.50 value 0, 2, 3, 4, 6`
    SSUB：`V2.1.20, V3.5.10 value 9`

    用集合相等而不是逐条 `in`：漏标一个取值、或多标一个，两个方向都要红。
    """
    def by_floor(name):
        grouped = {}
        for value, item in _values(name).items():
            if value is None:
                assert item.minimum_firmware is None, f"{name} 未设格不该有固件下限"
                continue
            grouped.setdefault(item.minimum_firmware, set()).add(value)
        return grouped

    # ⚠️ 作用域是 **`_dimensions()` 的全集**，不是「本片新加的那四个」。
    #    这道门被同一个错误连着咬了两次：
    #    ① 初版只写 ULDL / SSUBframe → `DMODe`（`V2.1.20, SCC command V3.5.10`）
    #       与 `RMC:VERSion:DL`（`V3.2.70`）两条 Firmware 行整条没进矩阵，
    #       而 `rmc_version` 那道门还反过来断言「必须没有固件下限」，
    #       把漏录钉死成了规范（内审 R1 F1）。
    #    ② 第一次修完，注释写着「按维度全集写，少一个就红」，作用域却仍是
    #       `P2_56_GATED` —— 用「我做到的」当「全集」，正是同一个错（内审 R2 F1）。
    #       P2-55 的 `transmission_mode` / `mimo_layers` 因此 11 格全无固件下限，
    #       而 `TRANsmission`（p.752）的 `V3.5.10: TM9 added` 恰恰是取值级加码，
    #       是本片引入 `minimum_firmware` 的立论依据本身。
    #
    #    `minimum_firmware=None` 分不出「本命令没门槛」与「我没录」——
    #    所以全集必须来自矩阵，不能来自作者的记忆。
    #
    #    各行 Firmware 原文里限定 `SCC<c>` 变体的那半句一律不计（本 profile
    #    走 `[:PCC]`）：`V3.5.20 SCC command`（ULDL / SSUBframe）、
    #    `SCC command V3.5.10`（DMODe）、`SCC command V3.2.50`（NENBantennas）。
    assert {name: by_floor(name) for name in sorted(_dimensions())} == {
        "duplex": {"V2.1.20": {"fdd", "tdd"}},
        "mimo_layers": {"V3.0.50": {1, 2, 4}},
        "rmc_version": {"V3.2.70": {0, 1}},
        "special_subframe": {
            "V2.1.20": {0, 1, 2, 3, 4, 5, 6, 7, 8},
            "V3.5.10": {9},
        },
        "transmission_mode": {
            "V3.2.70": {"TM1", "TM2", "TM3", "TM4", "TM6", "TM7", "TM8"},
            "V3.5.10": {"TM9"},
        },
        "uldl_configuration": {
            "V3.0.10": {1, 5},
            "V3.0.50": {0, 2, 3, 4, 6},
        },
    }


def test_special_subframe_prerequisites_are_exactly_values_8_and_9():
    """手册原文 `Value 8 and 9 can only be used with the normal cyclic prefix.`

    集合相等：给 7 也加前置要红，从 9 拿掉也要红。这是结构化 token 的意义 ——
    同一条事实写在散文里时，门只能靠措辞匹配，而措辞会漂。
    """
    carriers = {
        value
        for value, item in _values("special_subframe").items()
        if item.requires
    }
    assert carriers == {8, 9}
    for value in carriers:
        assert _values("special_subframe")[value].requires == (
            "normal_cyclic_prefix",
        )

    # 全矩阵其它取值一律不带前置 —— 防止「顺手给别处也加一个」
    others = [
        (name, item.value)
        for name, dimension in _dimensions().items()
        for item in dimension.values
        if item.requires and not (name == "special_subframe" and item.value in carriers)
    ]
    assert not others, others


def test_special_subframe_option_set_matches_the_manual_options_lines():
    """SSUBframe 选件：基线 KS550；`KS512 for value 9` 那一格额外必装。"""
    values = _values("special_subframe")
    assert set(values) == {None, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9}
    for value, item in values.items():
        if value is None:
            continue
        expected = ["KS512", "KS550"] if value == 9 else ["KS550"]
        assert sorted(item.required_options) == expected, value


def test_rmc_version_matrix_matches_its_range():
    """RMC:VERSion:DL<s> Range `0 to 1`（p.803），该条目无 Options 行。"""
    values = _values("rmc_version")
    assert set(values) == {None, 0, 1}
    for value, item in values.items():
        if value is None:
            continue
        assert item.support == "authoritative"
        assert not item.satisfying_options
        assert not item.required_options, "p.803 该条目没有 Options 行"
        # 固件下限由 test_per_value_firmware_floors_... 按维度全集统一断言。
        # 这里**刻意不再写 `is None`** —— 原来那句把「我漏录了 Firmware 行」
        # 钉死成了「本命令没有固件下限」，而 p.803 明写 `V3.2.70`（内审 F1）。


def test_support_grading_is_pinned_per_dimension():
    """逐维度钉死「哪些取值是正式路径」——集合相等，上调或降级都红。

    这条门是从 ② 实现时的一次真事故长出来的：给 `rmc_version` 上调时用了
    一个**无计数的整体替换**（`support="diagnostic_only"` + `V3.2.70`），
    而 `transmission_mode` 的 TM7/TM8 在 ① 里刚好被填上同一个固件值 ——
    两格被连带误上调成 `authoritative`。P2-55 的门抓到了（5 条红），
    但那是**下一次跑测试**才发现的；这条门把「定档全景」变成一处显式清单，
    读 diff 的人一眼能看出哪几格动了。
    """
    graded = {
        name: {
            support: {item.value for item in dimension.values if item.support == support}
            for support in ("authoritative", "diagnostic_only")
        }
        for name, dimension in _dimensions().items()
    }
    graded = {
        name: {k: v for k, v in buckets.items() if v}
        for name, buckets in graded.items()
    }
    assert graded == {
        "transmission_mode": {
            "authoritative": {"TM1", "TM2", "TM3", "TM4", "TM6"},
            "diagnostic_only": {"TM7", "TM8", "TM9"},
        },
        "mimo_layers": {
            "authoritative": {1, 2},
            "diagnostic_only": {4},
        },
        "duplex": {"authoritative": {"fdd", "tdd"}},
        "uldl_configuration": {
            "authoritative": {None, 0, 1, 2, 3, 4, 5, 6},
        },
        "special_subframe": {
            # 8/9 要求 normal cyclic prefix，而本驱动没有 CP 维度
            "authoritative": {None, 0, 1, 2, 3, 4, 5, 6, 7},
            "diagnostic_only": {8, 9},
        },
        "rmc_version": {"authoritative": {None, 0, 1}},
    }


def test_firmware_floors_parse_with_the_drivers_own_comparator():
    """固件字符串必须能被**本驱动自己**的比较器解析。

    版本串格式是厂商方言，所以格式门放在驱动侧而不是 vendor-neutral 的
    manifest 模块里。判据用自反 + 单调两条，`_firmware_at_least` 解析失败时
    恒返回 False，所以自反那条就能抓住写坏的串。
    """
    at_least = RealCmw500Driver._firmware_at_least
    floors = {
        item.minimum_firmware
        for dimension in _dimensions().values()
        for item in dimension.values
        if item.minimum_firmware is not None
    }
    assert floors, "本片应当声明了逐值固件下限"
    for floor in floors:
        assert at_least(floor, floor), f"{floor!r} 解析不了"
        assert not at_least("V0.0.1", floor), f"{floor!r} 的单调性不对"


# --------------------------------------------------------------------------
# 3. 新维度的理由质量（沿用 P2-55 的三条规则，作用在本片四个维度上）
# --------------------------------------------------------------------------


def test_new_dimension_reasons_cite_the_manual_and_state_our_own_gap():
    """降级理由：禁厂商否定断言 + 必须自述缺什么 + 必须有可定位坐标。

    与 P2-55 的同名门同源（那道门写死在两个旧维度上，够不到这里），
    成因也相同：**把「我没找到」写成「手册没有」**。
    """
    vendor_negations = (
        "手册未给", "手册没有", "手册未覆盖", "无依据", "没有依据",
        "无 RMC 依据", "无 RMC 表依据",
    )
    self_scoped = (
        "本驱动", "本矩阵", "本模块", "本地", "未实现", "未接", "未支持", "未验证",
    )
    for name in sorted(P2_56_GATED):
        for item in _dimensions()[name].values:
            reason = item.reason
            assert item.source_reference == CMW_MANUAL, (name, item.value)
            for phrase in vendor_negations:
                assert phrase not in reason, (
                    f"{name}={item.value!r} 写了关于厂商的否定断言 {phrase!r}："
                    f"{reason!r}"
                )
            if item.support != "authoritative":
                assert any(k in reason for k in self_scoped), (
                    f"{name}={item.value!r} 降级了却没说清是我们这边缺什么："
                    f"{reason!r}"
                )
            assert (
                re.search(r"p{1,2}\.\d+", reason)
                or re.search(r"表\s*2-\d+", reason)
                or re.search(r"§2\.\d+(\.\d+)*", reason)
            ), f"{name}={item.value!r} 的理由里没有可定位坐标：{reason!r}"


# --------------------------------------------------------------------------
# 4. 行为门：None 那一格是承重的，不是装饰
# --------------------------------------------------------------------------


def _lte_requirements():
    from app.hal.base_station_compatibility import (
        BaseStationExecutionRequirements,
    )
    from app.schemas.mimo_ota.config import MIMOOTAConfiguration

    configuration = {
        "component_carriers": [
            {
                "radio_technology": "lte",
                "frequency_hz": 1_842_500_000.0,
                "bandwidth_mhz": 20.0,
                "band": "B3",
                "duplex": "fdd",
                "lte_dl_earfcn": 1575,
                "lte_transmission_mode": "TM3",
                "role": "pcell",
            }
        ],
        "mimo_layers": 2,
    }
    frozen = MIMOOTAConfiguration.model_validate(configuration).mac_profile
    return BaseStationExecutionRequirements.model_construct(
        schema_version=1,
        requested_rat="lte",
        required_operations=(),
        mac_profile=frozen,
    )


@pytest.mark.parametrize(
    "dropped", sorted(P2_56_GATED - {"duplex"})
)
def test_the_none_cell_is_load_bearing_for_every_fdd_profile(dropped):
    """删掉任一 TDD 维度的 `None` 格 → **完好的 FDD profile 当场被拒**。

    这就是为什么 `None` 必须是一条写出理由的正式声明，而不是在判定器里静默
    跳过：判定器按 `(类型, 值)` 取声明，FDD profile 这三个字段恒为 `None`，
    缺那一格就落进「未声明的取值」。变异（去掉 None 格）在这里会红。
    """
    from app.hal.base_station_compatibility import (
        evaluate_base_station_compatibility,
    )

    manifest = RealCmw500Driver.adapter_manifest
    ok = evaluate_base_station_compatibility(_lte_requirements(), manifest)
    assert ok.compatible, ok.reasons

    mutated = manifest.model_copy(
        update={
            "mac_profiles": tuple(
                profile.model_copy(
                    update={
                        "dimensions": tuple(
                            dimension.model_copy(
                                update={
                                    "values": tuple(
                                        item
                                        for item in dimension.values
                                        if item.value is not None
                                    )
                                }
                            )
                            if dimension.dimension == dropped
                            else dimension
                            for dimension in profile.dimensions
                        )
                    }
                )
                for profile in manifest.mac_profiles
            )
        }
    )
    verdict = evaluate_base_station_compatibility(_lte_requirements(), mutated)
    assert not verdict.compatible
    assert any(dropped in reason for reason in verdict.reasons), verdict.reasons


def test_tdd_side_is_declared_but_unreachable():
    """声明 ≠ 可达：profile 仍拒绝 TDD 与三个字段的任何非 None 取值。

    本片有意**不新增任何可达状态**。放开取值域会立刻造出「profile 说 TDD、
    仪器活体是 FDD」这一格，而驱动今天只拿活体 duplex 跟字面量 "FDD" 比、
    从不跟 profile 比 —— 那会把 TDD 用例静默按 FDD 配掉。
    """
    from tests.test_p2_54_mac_profile_schema import _lte_profile

    with pytest.raises(ValidationError):
        _lte_profile(duplex="tdd")
    for field in ("uldl_configuration", "special_subframe", "rmc_version"):
        # 枚举形态空间：整数 / 零 / 字符串 / 布尔 / 负数，全都不许进
        for bad in (0, 1, "0", True, -1):
            with pytest.raises(ValidationError):
                _lte_profile(**{field: bad})


def test_option_and_firmware_fields_are_declarative_today():
    """显式钉住：这三个新字段今天**没有判定消费方**。

    兼容层没有「已装选件 / 固件版本」这个输入（`satisfying_options` 自 P2-55
    起同样是纯声明）。把不可能满足的选件塞进去，verdict 必须**不变** ——
    这条门记录的是现状，不是理想状态。

    将来真给它们接上消费方时，本门会红：那时要一并更新本片文档里
    「验收 = 结构能区分 + 门能机械校验」那句话。
    """
    from app.hal.base_station_compatibility import (
        evaluate_base_station_compatibility,
    )

    manifest = RealCmw500Driver.adapter_manifest
    baseline = evaluate_base_station_compatibility(_lte_requirements(), manifest)
    assert baseline.compatible

    mutated = manifest.model_copy(
        update={
            "mac_profiles": tuple(
                profile.model_copy(
                    update={
                        "dimensions": tuple(
                            dimension.model_copy(
                                update={
                                    "values": tuple(
                                        item.model_copy(
                                            update={
                                                "required_options": (
                                                    "NO-SUCH-OPTION",
                                                ),
                                                "minimum_firmware": "V99.9.9",
                                            }
                                        )
                                        for item in dimension.values
                                    )
                                }
                            )
                            for dimension in profile.dimensions
                        )
                    }
                )
                for profile in manifest.mac_profiles
            )
        }
    )
    assert evaluate_base_station_compatibility(
        _lte_requirements(), mutated
    ).compatible


# --------------------------------------------------------------------------
# 5. 判定器自测：新结构的构造层校验能抓坏输入、不误伤好输入
# --------------------------------------------------------------------------


def _value(**updates):
    payload = {
        "value": "TM3",
        "support": "authoritative",
        "reason": "r",
        "source_reference": CMW_MANUAL,
    }
    payload.update(updates)
    return payload


def test_option_cannot_be_both_satisfying_and_required():
    """同一个选件既「二选一」又「必装」= 自相矛盾的声明，构造层即拒。"""
    with pytest.raises(ValidationError):
        BaseStationMacDimensionValueCapability(
            **_value(
                satisfying_options=("KS520", "KS540"),
                required_options=("KS540",),
            )
        )
    # 不重叠的组合是合法的，不许误伤
    BaseStationMacDimensionValueCapability(
        **_value(
            satisfying_options=("KS520",), required_options=("KS550", "KS510")
        )
    )


@pytest.mark.parametrize("bad", [("KS550", "  "), ("KS550", "KS550")])
def test_required_options_reject_blank_and_duplicate(bad):
    with pytest.raises(ValidationError):
        BaseStationMacDimensionValueCapability(**_value(required_options=bad))


def test_requires_is_a_closed_enum_not_free_text():
    """`requires` 是封闭枚举 —— 写错的 token 在构造层就红，不等到有人读散文。"""
    with pytest.raises(ValidationError):
        BaseStationMacDimensionValueCapability(
            **_value(requires=("normal cyclic prefix",))
        )
    with pytest.raises(ValidationError):
        BaseStationMacDimensionValueCapability(
            **_value(requires=("extended_cyclic_prefix",))
        )
    with pytest.raises(ValidationError):
        BaseStationMacDimensionValueCapability(
            **_value(requires=("normal_cyclic_prefix", "normal_cyclic_prefix"))
        )
    BaseStationMacDimensionValueCapability(
        **_value(requires=("normal_cyclic_prefix",))
    )


@pytest.mark.parametrize("blank", ["", "   "])
def test_minimum_firmware_rejects_blank_but_allows_absent(blank):
    with pytest.raises(ValidationError):
        BaseStationMacDimensionValueCapability(**_value(minimum_firmware=blank))
    assert (
        BaseStationMacDimensionValueCapability(
            **_value(minimum_firmware=None)
        ).minimum_firmware
        is None
    )


def test_none_and_zero_and_false_stay_three_distinct_declarations():
    """`None` / `0` / `False` 是三条不同的声明，判重不能把它们并成一条。

    Python 里 `False == 0` 且哈希相同；`None` 又是新引入的一格。判重按
    `(类型, 值)`，三者必须共存。
    """
    dimension = BaseStationMacDimensionCapability(
        dimension="uldl_configuration",
        values=(
            BaseStationMacDimensionValueCapability(**_value(value=None)),
            BaseStationMacDimensionValueCapability(**_value(value=0)),
            BaseStationMacDimensionValueCapability(**_value(value=False)),
        ),
    )
    assert len(dimension.values) == 3
    with pytest.raises(ValidationError):
        BaseStationMacDimensionCapability(
            dimension="uldl_configuration",
            values=(
                BaseStationMacDimensionValueCapability(**_value(value=None)),
                BaseStationMacDimensionValueCapability(**_value(value=None)),
            ),
        )


def test_openapi_contract_matches_the_lte_profile_schema_both_ways():
    """`api/openapi.yaml` 的 LTE profile 字段集 == 活 schema 的字段集（双向）。

    这道门是从本片自己造的一次契约破坏里长出来的（内审 R2 F2）：给
    `LteRmcMacTestProfileV1` 加了三个字段，没走契约同步四步，而契约那边写着
    `additionalProperties: false` 且改动前是**逐字对齐**的。于是活接口返回的
    profile（经 `app/api/instrument.py` 的 base_station_testcase_compatibility
    出网，并写进存库配置）不再满足自己的契约，照契约生成的 TS 类型里也没有
    这三个字段。

    ⚠️ **既有的 G11 抓不到这个方向** —— 它查的是「文档 ⊆ 活 schema」，
    往活 schema 加字段恒绿。所以这里要的是**集合相等**，两个方向都红。

    `required` 也一起断言：这三个字段序列化时恒出现（dump 不带 exclude_none），
    漏进 required 会让契约允许一个真实响应里不存在的形态。
    """
    import yaml

    contract = yaml.safe_load(
        (_REPO_ROOT / "api" / "openapi.yaml").read_text(encoding="utf-8")
    )
    declared = contract["components"]["schemas"]["LteRmcMacTestProfileV1"]
    live = set(LteRmcMacTestProfileV1.model_fields)

    assert set(declared["properties"]) == live, (
        "openapi.yaml 的 LteRmcMacTestProfileV1 与活 schema 字段集不一致；"
        "走契约同步四步（改 openapi.yaml → npm run openapi:generate）"
    )
    # `required` 取 `model_fields` 全集是**有意比 Pydantic 生成的更严**（内审 R3 F6）：
    # Pydantic 把这三个有默认值的字段判成 optional，那是**请求**视角；而本 schema
    # 描述的是**响应/落库**形态，序列化不带 exclude_none，三个键恒出现。
    assert set(declared["required"]) == live
    # 契约禁止额外属性 —— 上面那条集合相等才有意义
    assert declared.get("additionalProperties") is False

    # ⚠️ 只比键集拦不住类型写错（内审 R3 F2 实测：把 special_subframe 改成
    #    `{type: string}`，键集不变 → 全绿）。契约是 TS 类型的生成源，
    #    类型写错会直接生成错的前端类型，所以本片三个字段逐字段钉死。
    # P2-56 ②：取值域已放开，逐字段钉死枚举（含 null = 该维度不适用）。
    # `special_subframe` 只到 7 而非手册的 9 —— 值 8/9 要求 normal cyclic
    # prefix，本驱动无 CP 维度，收窄理由写在 profile 与矩阵里。
    expected_domains = {
        "uldl_configuration": [None, 0, 1, 2, 3, 4, 5, 6],
        "special_subframe": [None, 0, 1, 2, 3, 4, 5, 6, 7],
        "rmc_version": [None, 0, 1],
    }
    for field, domain in expected_domains.items():
        assert declared["properties"][field] == {
            "type": "integer",
            "nullable": True,
            "enum": domain,
        }, f"{field} 的契约取值域与活 schema 不符"
    assert declared["properties"]["duplex"] == {
        "type": "string",
        "enum": ["fdd", "tdd"],
    }

    # ⚠️ 契约同步的**第 4 步**（重生 TS 类型）此前没有任何机械保证
    #    （内审 R3 F4 实测：从 api.generated.ts 删掉两行 → 全绿）。
    #    这里按字段名核生成文件里的同名 block —— 忘跑 openapi:generate 会红。
    generated = (
        _REPO_ROOT / "gui" / "src" / "types" / "api.generated.ts"
    ).read_text(encoding="utf-8")
    block = generated.split("LteRmcMacTestProfileV1: {", 1)[1].split("\n        };", 1)[0]
    emitted = set(re.findall(r"^\s{12}(\w+)[?]?:", block, re.MULTILINE))
    assert emitted == live, (
        "gui/src/types/api.generated.ts 与契约不同步 —— 跑 "
        "`cd gui && npm run openapi:generate`"
    )
