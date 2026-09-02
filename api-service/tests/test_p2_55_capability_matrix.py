"""P2-55 — CMW500 LTE FDD MAC 能力矩阵。

守两件事：
1. **矩阵内容**逐值等于 2026-09-02 手册取证的结论（谁 authoritative、要什么选件、出处是谁）。
2. **矩阵结构**的自洽约束真的会拒绝坏声明（判定器自测，正反两向）。

⚠️ 本文件的期望值不是"当前实现的快照"，而是**手册取证结论**。改动实现让它变红时，
先回去核对 `docs/plans/2026-09-02-p2-55-cmw500-lte-fdd-capability-matrix-design.md` §3，
而不是直接改期望值 —— 那等于把矩阵改成了"代码说什么就是什么"。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.hal.base_station_manifest import (
    BaseStationMacDimensionCapability,
    BaseStationMacDimensionValueCapability,
)
from app.hal.cmw500_base_station import RealCmw500Driver


CMW_MANUAL = (
    "Instrument_API_Doc/R&S CMW500/CMW_LTE_UE_UserManual_V4-0-250_en_41 (2).pdf"
)


def _dimension(name: str) -> BaseStationMacDimensionCapability:
    for profile in RealCmw500Driver.adapter_manifest.mac_profiles:
        for dimension in profile.dimensions:
            if dimension.dimension == name:
                return dimension
    raise AssertionError(f"CMW500 manifest 未声明维度 {name}")


# --------------------------------------------------------------------------
# 1. 矩阵内容 = 手册取证结论
# --------------------------------------------------------------------------


def test_transmission_mode_matrix_matches_manual_evidence():
    """TM 取值域与 support 判定。

    命令 Range（p.752）含 8 个 TM。TM1 与 TM2..TM6 标 authoritative，
    TM7/TM8/TM9 标 diagnostic_only —— **逐格理由见矩阵各自的 reason**，
    此处不复述判据（那份概括数错过三次）。

    TM7/TM8/TM9 的手册侧证据**齐全**（RMC 表 §2.2.19.5/.6/.7 = 表 2-40..2-45，
    天线配置见表 2-32），仍是 diagnostic_only 的原因是**本驱动未实现**它们的
    下发路径 —— 现行结论的完整表述只在矩阵的 reason 里，此处不复述，避免两处漂移。

    ⚠️ 这句话改过三版，前两版都是关于手册的**假断言**（"没有 RMC 表"、
    "天线配置路径手册未给"）。成因同源：用一句概括替代一张表 —— 表 2-32 是
    「场景 × TM × 天线」三维表，压成 "TM7=1x2" 必然丢掉场景维（p.65 的
    1x1 carrier 场景下 TM7 是 1x1）。引表格类依据前先数这个键在表里占几行，
    多于一行就不许用"固定 / 即 / 就是"。
    """
    actual = {item.value: item.support for item in _dimension("transmission_mode").values}

    assert actual == {
        "TM1": "authoritative",
        "TM2": "authoritative",
        "TM3": "authoritative",
        "TM4": "authoritative",
        "TM6": "authoritative",
        "TM7": "diagnostic_only",
        "TM8": "diagnostic_only",
        "TM9": "diagnostic_only",
    }


def test_transmission_mode_range_skips_tm5():
    """手册 Range 原文是 TM1|TM2|TM3|TM4|TM6|TM7|TM8|TM9 —— 中间跳过 5。

    任何"TM1..TM9 连续"的实现都会把 TM5 带进来，而它根本不在命令的取值域里。
    """
    declared = {item.value for item in _dimension("transmission_mode").values}

    assert "TM5" not in declared
    assert declared == {"TM1", "TM2", "TM3", "TM4", "TM6", "TM7", "TM8", "TM9"}


def test_transmission_mode_option_dependencies_match_manual():
    """选件原文：`KS520 or -KS540 for TM 2, 3, 4, 6, 7, 9`；`KS520 for TM 8`。

    TM1 是 *RST 默认值且属性块未对它列选件 —— 它必须是唯一不要选件的那个。
    """
    actual = {
        item.value: item.satisfying_options
        for item in _dimension("transmission_mode").values
    }

    assert actual["TM1"] == ()
    # 手册原文是「KS520 **or** -KS540 for TM 2, 3, 4, 6, 7, 9」——「或」不是「且」，
    # 只装 KS540 的整机也支持这些 TM。TM8 手册单列 KS520，没有替代。
    assert all(
        actual[tm] == ("KS520", "KS540")
        for tm in ("TM2", "TM3", "TM4", "TM6", "TM7", "TM9")
    )
    assert actual["TM8"] == ("KS520",)


def test_mimo_layers_matrix_matches_manual_evidence():
    """天线数取值域。

    NENBantennas Range 是 ONE|TWO|FOUR（p.753）。ONE/TWO 分别有表 2-37 / 2-38
    支撑；FOUR 命令层有据但本地无真机证据，保守不放行正式路径。
    """
    values = _dimension("mimo_layers").values
    actual = {item.value: (item.support, item.satisfying_options) for item in values}

    # Options 原文四行：TWO 有 2x2→KS520 / 2x4→KS540 两种，FOUR 有
    # 4x2→KS521 / 4x4→KS540 两种。都是「装任一即可」。
    assert actual == {
        1: ("authoritative", ()),
        2: ("authoritative", ("KS520", "KS540")),
        4: ("diagnostic_only", ("KS521", "KS540")),
    }


def test_mimo_layers_values_are_integers_not_strings():
    """维度取值要带 profile 字段自己的 JSON 形态。

    mimo_layers 在 profile 里是 int；若这里声明成 "2"，判定时与 int 2 比对不上，
    会让一个本该放行的值被静默拒绝（或反过来，靠 str() 归一化蒙混过关）。
    """
    for item in _dimension("mimo_layers").values:
        assert type(item.value) is int


def test_every_declared_value_cites_the_registered_manual():
    """每格都要有出处，且出处必须是已登记的那本手册。

    出处不在 manual_sources 里等于无法审计 —— 它会让一格错误的能力声明
    看起来有据可查。manifest 层已有该校验，这里断言实际数据满足它。
    """
    for name in ("transmission_mode", "mimo_layers"):
        for item in _dimension(name).values:
            assert item.source_reference == CMW_MANUAL
            assert item.reason.strip()


def test_authoritative_values_cite_an_rmc_table():
    """authoritative 的取值必须引用一张 DL RMC 表。

    ⚠️ 判据的完整条数**不在这里复述** —— 它在驱动内矩阵声明上方那段注释里，
    而且改过三次（两样 → 三样 → 三样仍不全，见 mimo_layers=4 靠"本地无真机
    证据"这第四条降级）。这里只锁一件可机械检查的事：**声明 authoritative 就得
    指出是哪张 RMC 表**。

    表号范围覆盖 §2.2.19.3-.7 全部七张（2-37..2-45）：初版只认 2-37/2-38，
    而 TM7 的表是 2-40 —— 那会让门用一个已知为假的理由拦住未来真正实现 TM7 的人。
    """
    for name in ("transmission_mode", "mimo_layers"):
        for item in _dimension(name).values:
            if item.support == "authoritative":
                import re as _re2

                # 只认 **FDD** 侧的表：2-37（单天线）/ 2-38（多天线）/
                # 2-40（TM7）/ 2-42（TM8）/ 2-44（TM9）。
                # 2-39 / 2-41 / 2-43 / 2-45 是 TDD 专表，而本 profile 的
                # duplex 锁死 fdd —— 拿 TDD 表当 FDD 取值的依据是净放宽。
                # 用 (?!\d) 而不是 \b：Python 3 的 \b 是 Unicode 感知的，中文属 \w，
                # 「表 2-37中的满配行」这种紧跟中文的写法 \b 匹配不到，会误判成
                # "没引表号"。(?!\d) 同样挡得住 表 2-371。
                assert _re2.search(r"表\s*2-(37|38|40|42|44)(?!\d)", item.reason), (
                    f"{name}={item.value!r} 声明为 authoritative 却未引用任何一张 "
                    f"**FDD** DL RMC 表（2-37/2-38/2-40/2-42/2-44）：{item.reason!r}"
                )


def test_diagnostic_only_reasons_state_what_is_missing_and_where():
    """降级的取值必须说清**缺的是哪一样、在哪能查到**。

    这道门是从连续两次同型错误里长出来的：
    1. 初版说 TM7/8/9「无 RMC 表依据」—— 假的，手册有 §2.2.19.5/.6/.7 三节专表；
    2. 第一次修正说「天线配置路径手册未给」—— **还是假的**，表 2-32（pp.65-67）
       给了天线配置，§2.6.15.4（pp.761-764）是 TM7/8 的专属命令集。
    两次成因相同：**把"我没找到"写成了"手册没有"**。

    所以门锁两件事：

    - **禁止"手册没有"这类关于厂商的否定断言**（白名单式：列出已知的同义写法
      并全部禁掉）。要降级，就说清楚是**我们**缺什么 —— 那是可核验的自述，
      而"手册没有"要穷尽全书才能证伪，写的人几乎不会真去穷尽。
    - **整条理由里要有可定位的坐标**（页码 / 表号 / 章节 / 命令），证明作者确实
      翻过手册。坐标**不**要求落在"缺什么"那半句里 —— 缺真机证据是完全正当的
      降级理由（`mimo_layers=4` 即是），而真机证据没有页码可引。

    两条分工：禁否定断言 + 必须自述，管的是**理由具体不具体**；坐标管的是
    **查没查手册**。单独任何一条都不够。
    """
    import re as _re

    # 关于「厂商没有提供」的否定断言：一律禁止（无法在一格 reason 里被证伪）
    # ⚠️ 只列**关于厂商/手册**的否定断言。「未取证」「证据不足」描述的是
    #    **我们自己**缺验证（`mimo_layers=4` 的正当理由就是"本地无真机证据"），
    #    放进来会误伤合法的自述式降级理由 —— 那是把这道门用反了方向。
    vendor_negations = (
        "手册未给", "手册没有", "手册未覆盖", "无依据", "没有依据",
        "无 RMC 依据", "无 RMC 表依据",
    )
    # 关于「本驱动/本矩阵缺什么」的自述：这才是可核验的降级理由
    # ⚠️ 刻意**不含**「没有」：加进来会让「RMC 表没有覆盖 TM7」
    #    「3GPP 没有定义该组合」「手册里没有对应命令」全部放行 —— 那正是本片
    #    要治的那句假话的变体，而它们都不在 vendor_negations 的字面词表里。
    #    放宽要靠加"自述主语"（本地/本模块）和"自述动词"（未支持/未验证），
    #    不能靠加一个厂商否定也会用的通用否定词。
    self_scoped = (
        "本驱动", "本矩阵", "本模块", "本地",
        "未实现", "未接", "未支持", "未验证",
    )

    for name in ("transmission_mode", "mimo_layers"):
        for item in _dimension(name).values:
            if item.support != "diagnostic_only":
                continue
            reason = item.reason

            for phrase in vendor_negations:
                assert phrase not in reason, (
                    f"{name}={item.value!r} 用「{phrase}」断言厂商侧没有该能力。"
                    f"这类否定要穷尽全书才能证伪，已连错两次 —— "
                    f"改成说明**我们**缺什么：{reason!r}"
                )

            assert any(k in reason for k in self_scoped), (
                f"{name}={item.value!r} 降级为 diagnostic_only，"
                f"但没说清是我们这边缺什么（期望出现 {self_scoped} 之一）：{reason!r}"
            )

            # 整条 reason 里必须有可定位的坐标，证明作者确实去手册里查过 ——
            # 缺的具体是什么由上面两条（禁否定断言 + 必须自述）保证。
            # ⚠️ 坐标不要求落在"缺什么"那半句里：缺**真机证据**是完全正当的降级
            # 理由（mimo_layers=4 就是），而真机证据没有页码可引。
            located = (
                _re.search(r"p\.\d+", reason)
                or _re.search(r"表\s*2-\d+", reason)
                or _re.search(r"§2\.\d+(\.\d+)*", reason)
                # 命令名含数字或占位符也要认：本片 reason 里就有
                # `TM<no>:NTXantennas`。冒号两侧都要求 ≥2 个连续大写字母
                # （SCPI 的助记符约定），否则 `Note:we` / `Missing:mimo_layers`
                # 这类普通英文会被当成坐标，把整条门静默绕过。
                or _re.search(
                    r"\b[A-Z]{2,}[A-Za-z0-9<>_]*:[A-Z]{2,}[A-Za-z0-9<>_]*", reason
                )
            )
            assert located, (
                f"{name}={item.value!r} 降级为 diagnostic_only，"
                f"但整条理由里没有任何可定位的坐标（页码 / 表号 / 章节 / 命令）"
                f"—— 无从判断作者查过手册没有：{reason!r}"
            )


# --------------------------------------------------------------------------
# 2. 判定器自测：坏声明必须被拒，好声明不能被误伤
# --------------------------------------------------------------------------


def _value(**overrides) -> dict:
    payload = {
        "value": "TM1",
        "support": "authoritative",
        "satisfying_options": (),
        "reason": "手册 p.752 Range 含 TM1",
        "source_reference": CMW_MANUAL,
    }
    payload.update(overrides)
    return payload


def test_dimension_rejects_duplicate_values():
    """同一取值两条声明 = 「它支持吗」有两个答案，取哪条都是猜。"""
    with pytest.raises(ValidationError):
        BaseStationMacDimensionCapability(
            dimension="transmission_mode",
            values=(
                BaseStationMacDimensionValueCapability(**_value()),
                BaseStationMacDimensionValueCapability(
                    **_value(support="diagnostic_only")
                ),
            ),
        )


def test_dimension_rejects_empty_value_domain():
    """声明了维度却不给取值 = 一个什么都答不出的空矩阵。"""
    with pytest.raises(ValidationError):
        BaseStationMacDimensionCapability(dimension="transmission_mode", values=())


@pytest.mark.parametrize(
    "bad_name",
    [
        "Transmission Mode",          # 大写 + 空格
        "statistical_window.count",   # 点号路径：判定器 hasattr 取不到
        "mac.transmission_mode",      # 同上
    ],
)
def test_dimension_rejects_names_the_matcher_cannot_resolve(bad_name):
    """维度名必须是单段 token。

    点号路径尤其要挡：判定器按 `dimension in type(profile).model_fields`
    取字段，`"a.b"` 恒不命中 —— 声明会落进"脱节"分支被拒。方向虽是
    fail-closed，但拒绝理由指不到点子上，所以这一格要在构造层就红。
    NR profile 恰好有嵌套的 statistical_window，是最自然的下一步扩展。
    """
    with pytest.raises(ValidationError):
        BaseStationMacDimensionCapability(
            dimension=bad_name,
            values=(BaseStationMacDimensionValueCapability(**_value()),),
        )


@pytest.mark.parametrize("blank", ["", "   "])
def test_value_rejects_blank_reason_and_source(blank):
    with pytest.raises(ValidationError):
        BaseStationMacDimensionValueCapability(**_value(reason=blank))
    with pytest.raises(ValidationError):
        BaseStationMacDimensionValueCapability(**_value(source_reference=blank))


def test_value_rejects_blank_or_duplicate_options():
    with pytest.raises(ValidationError):
        BaseStationMacDimensionValueCapability(
            **_value(satisfying_options=("KS520", "  "))
        )
    with pytest.raises(ValidationError):
        BaseStationMacDimensionValueCapability(
            **_value(satisfying_options=("KS520", "KS520"))
        )


def test_value_rejects_unknown_support_token():
    with pytest.raises(ValidationError):
        BaseStationMacDimensionValueCapability(**_value(support="supported"))


def test_value_keeps_bool_and_int_distinct():
    """bool 是 int 的子类：True 与 1 必须是两条不同的声明，不能互相顶替。

    P1-74 踩过这个坑 —— 普通 int 字段会把 True 静默归一成 1。
    """
    true_value = BaseStationMacDimensionValueCapability(**_value(value=True))
    one_value = BaseStationMacDimensionValueCapability(**_value(value=1))

    assert type(true_value.value) is bool
    assert type(one_value.value) is int

    # 同一维度里两者并存是合法的（它们是不同取值），不该被判重规则误伤
    dimension = BaseStationMacDimensionCapability(
        dimension="enable_amc",
        values=(true_value, one_value),
    )
    assert len(dimension.values) == 2


def test_good_declaration_is_accepted():
    """反向：合法声明不能被上面那些约束误伤。"""
    dimension = BaseStationMacDimensionCapability(
        dimension="transmission_mode",
        values=(
            BaseStationMacDimensionValueCapability(**_value()),
            BaseStationMacDimensionValueCapability(
                **_value(value="TM3", satisfying_options=("KS520",))
            ),
        ),
    )

    assert dimension.dimension == "transmission_mode"
    assert len(dimension.values) == 2


# --------------------------------------------------------------------------
# 3. 矩阵真的生效：判定器逐维度对账（不是一份没人读的声明）
# --------------------------------------------------------------------------


def _lte_requirements(**profile_overrides):
    """造一份冻结的 LTE 需求投影，可覆盖 profile 的单个维度取值。"""
    from app.hal.base_station_compatibility import (
        BaseStationExecutionRequirements,
    )
    from app.hal.base_station_mac_profile import FrozenMacTestProfile
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
    if profile_overrides:
        # 绕过 profile schema 自己的 Literal，直接构造一个"矩阵该拦住"的取值：
        # 本片要证明的正是**矩阵**在拦，不是 schema 在拦。
        payload = frozen.profile.model_dump(mode="json")
        payload.update(profile_overrides)
        frozen = FrozenMacTestProfile.model_construct(
            profile=frozen.profile.model_construct(**payload),
            profile_digest=frozen.profile_digest,
        )
    return BaseStationExecutionRequirements.model_construct(
        schema_version=1,
        requested_rat="lte",
        required_operations=frozen and (),
        mac_profile=frozen,
    )


def test_matrix_is_actually_consumed_by_the_compatibility_decision():
    """基线：TM3 + 2 层（矩阵里都是 authoritative）不因维度被拒。

    这条是下面两条拒绝用例的对照 —— 没有它，"矩阵拦住了"可能只是
    因为判定器把所有 LTE 都拒了。
    """
    from app.hal.base_station_compatibility import _mac_dimension_rejections

    requirements = _lte_requirements()
    rejections = _mac_dimension_rejections(
        profile=requirements.mac_profile.profile,
        manifest=RealCmw500Driver.adapter_manifest,
    )

    assert rejections == []


@pytest.mark.parametrize(
    "overrides, expected_fragment",
    [
        ({"transmission_mode": "TM7"}, "diagnostic_only"),
        ({"mimo_layers": 4}, "diagnostic_only"),
        ({"transmission_mode": "TM5"}, "does not declare"),
        ({"mimo_layers": 8}, "does not declare"),
    ],
)
def test_non_authoritative_and_undeclared_values_are_rejected(
    overrides, expected_fragment
):
    """矩阵的两层 fail-closed 判据都要真的拦得住。

    - TM7 / 4 层：声明里**有**这个取值，但标的是 diagnostic_only
      → 能下发不等于可正式配置，必须拒。
    - TM5 / 8 层：声明里根本**没有**（TM5 不在命令 Range 里，8 不在天线取值域里）
      → 未声明即拒，不猜。
    """
    from app.hal.base_station_compatibility import _mac_dimension_rejections

    requirements = _lte_requirements(**overrides)
    rejections = _mac_dimension_rejections(
        profile=requirements.mac_profile.profile,
        manifest=RealCmw500Driver.adapter_manifest,
    )

    assert rejections, f"{overrides} 应当被矩阵拒绝，实际放行"
    assert any(expected_fragment in item for item in rejections), rejections


def test_dimensions_absent_from_the_manifest_are_not_judged():
    """manifest **没声明**的维度不在这里判 —— 那属于 profile schema 的取值域。

    否则"尚未取证的维度"会被误判成"不兼容"，把 fail-closed 变成 fail-everything。
    注意与下一条区分：这条测的是"矩阵里没有这个维度"，
    下一条测的是"矩阵里有、但 profile 上没有那个字段"。
    """
    from app.hal.base_station_compatibility import _mac_dimension_rejections

    # duplex / resource_allocation 本片未声明进矩阵
    declared = {
        dimension.dimension
        for profile in RealCmw500Driver.adapter_manifest.mac_profiles
        for dimension in profile.dimensions
    }
    assert "duplex" not in declared
    assert "resource_allocation" not in declared

    requirements = _lte_requirements()
    assert (
        _mac_dimension_rejections(
            profile=requirements.mac_profile.profile,
            manifest=RealCmw500Driver.adapter_manifest,
        )
        == []
    )


def test_declared_dimension_missing_from_profile_is_rejected():
    """矩阵声明了一个 profile 上不存在的字段 → 显式拒绝，不能静默放行。

    这是声明与 schema 脱节。早期实现在这里 `continue`，于是一条 fail-closed
    的声明反而变成放行 —— 方向与本机制其余部分相反。维度名写错一个字母
    也落在这一格。
    """
    from app.hal.base_station_compatibility import _mac_dimension_rejections

    manifest = RealCmw500Driver.adapter_manifest
    profile = _lte_requirements().mac_profile.profile
    bogus = manifest.mac_profiles[0].model_copy(
        update={
            "dimensions": (
                BaseStationMacDimensionCapability(
                    dimension="nonexistent_knob",
                    values=(BaseStationMacDimensionValueCapability(**_value()),),
                ),
            )
        }
    )
    patched = manifest.model_copy(update={"mac_profiles": (bogus,)})

    rejections = _mac_dimension_rejections(profile=profile, manifest=patched)

    assert rejections, "声明与 profile 脱节的维度必须被拒绝，不能静默跳过"
    assert any("does not have" in item for item in rejections), rejections


# --------------------------------------------------------------------------
# 4. 接线门：矩阵必须真的参与**公开**的兼容性判定
# --------------------------------------------------------------------------


def test_matrix_reaches_the_public_compatibility_verdict():
    """经 `evaluate_base_station_compatibility` 而非私有 helper 断言。

    上面那些用例都直接调 `_mac_dimension_rejections`，所以把 evaluate 里那句
    接线整段删掉时它们**全都还是绿的** —— 矩阵会退化成一份没人读的声明，
    而 verdict 照常放行。这条门专门锁住"接线还在"。
    """
    from app.hal.base_station_compatibility import (
        evaluate_base_station_compatibility,
    )

    manifest = RealCmw500Driver.adapter_manifest
    ok = evaluate_base_station_compatibility(
        _lte_requirements(), manifest
    )
    assert ok.compatible, ok.reasons

    # TM7 在矩阵里是 diagnostic_only —— verdict 必须因此不兼容
    blocked = evaluate_base_station_compatibility(
        _lte_requirements(transmission_mode="TM7"), manifest
    )
    assert not blocked.compatible
    assert any("diagnostic_only" in reason for reason in blocked.reasons), (
        blocked.reasons
    )


def test_manifest_digest_ignores_the_dimension_matrix():
    """矩阵不进 manifest digest。

    它默认值是 `()` 而非 `None`，`exclude_none` 拦不住 —— 不显式排除的话，
    仅仅给某个取值改一句 reason 文案（判定毫无变化）就会让所有历史 frozen 的
    digest 失配，把完好的执行判成 manifest drifted、把完好的历史证据标成
    invalid。连一个维度都没声明的 adapter 也会因多出 `"dimensions": []` 而漂。

    判定性变化不靠 digest 兜：`verify_frozen_base_station_compatibility`
    会重算整个 verdict 并逐字段比对。
    """
    from app.hal.base_station_compatibility import manifest_compatibility_digest

    manifest = RealCmw500Driver.adapter_manifest
    baseline = manifest_compatibility_digest(manifest)

    # 只改 reason 文案，判定毫无变化
    profile = manifest.mac_profiles[0]
    dimension = profile.dimensions[0]
    reworded = dimension.model_copy(
        update={
            "values": (
                dimension.values[0].model_copy(
                    update={"reason": dimension.values[0].reason + "（措辞改动）"}
                ),
            )
            + dimension.values[1:]
        }
    )
    patched = manifest.model_copy(
        update={
            "mac_profiles": (
                profile.model_copy(
                    update={"dimensions": (reworded,) + profile.dimensions[1:]}
                ),
            )
        }
    )

    assert manifest_compatibility_digest(patched) == baseline

    # 反向：没有维度的 adapter 与有维度的 adapter，digest 都不受矩阵影响
    stripped = manifest.model_copy(
        update={
            "mac_profiles": (profile.model_copy(update={"dimensions": ()}),)
        }
    )
    assert manifest_compatibility_digest(stripped) == baseline


def test_matching_is_type_sensitive_so_bool_cannot_borrow_int():
    """判定器的匹配必须带类型判别。

    Python 里 ``True == 1`` **且哈希相同**，所以裸值做匹配键时
    ``{1: 授权声明}.get(True)`` 会命中 —— 一个布尔请求会借用 int 1 的
    authoritative 声明混进正式路径。这正是 P1-74 踩过的 bool/int 同一坑。

    ⚠️ 反方向（声明写成字符串 "2"、请求是 int 2）**测不出差异**：两种实现
    都会判未声明。只有 bool↔int 这一格能区分，因为它们在字典里是同一个键。
    """
    from app.hal.base_station_compatibility import _mac_dimension_rejections

    manifest = RealCmw500Driver.adapter_manifest
    declared = {
        item.value: item.support
        for item in _dimension("mimo_layers").values
    }
    assert declared[1] == "authoritative"  # True 会去借的就是这一条

    profile = _lte_requirements(mimo_layers=True).mac_profile.profile
    assert profile.mimo_layers is True

    rejections = _mac_dimension_rejections(profile=profile, manifest=manifest)

    assert rejections, "布尔 True 不得借用 int 1 的 authoritative 声明"
    assert any("does not declare" in item for item in rejections), rejections


def test_manifest_rejects_dimension_value_with_unregistered_source():
    """维度取值的出处必须登记在 manual_sources 里 —— 判定器自测。

    只断言"现有数据的出处是对的"管不住这条校验：把校验删掉，那种断言照样绿。
    出处不在 manual_sources 里等于无法审计，会让一格错误的能力声明看起来有据可查。
    """
    manifest = RealCmw500Driver.adapter_manifest
    profile = manifest.mac_profiles[0]
    tampered = profile.model_copy(
        update={
            "dimensions": (
                BaseStationMacDimensionCapability(
                    dimension="transmission_mode",
                    values=(
                        BaseStationMacDimensionValueCapability(
                            **_value(source_reference="某本没登记的手册.pdf")
                        ),
                    ),
                ),
            )
        }
    )

    with pytest.raises(ValidationError):
        manifest.model_copy(update={"mac_profiles": (tampered,)}).model_validate(
            manifest.model_copy(
                update={"mac_profiles": (tampered,)}
            ).model_dump(mode="json")
        )


@pytest.mark.parametrize(
    "adapter, expected",
    [
        ("cmw500", "7034550e172e"),
        ("uxm", "890c453c73c2"),
    ],
)
def test_manifest_compatibility_digest_is_pinned_to_its_baseline(
    adapter, expected
):
    """把两个 adapter 的 compatibility digest 钉到具体值。

    只断言「矩阵变了 digest 不变」是相对不变量，防不住反方向的错误：
    将来有人往排除集里"顺手多排一个字段"（例如 application_evidence），
    历史 digest 的语义会被静默改写而没有任何门变红。

    ⚠️ 这两个值 = 引入维度矩阵**之前** main 上的值。它们变红意味着
    digest 的覆盖面变了 —— 那要么是有意的契约变更（须同时处理历史冻结
    数据），要么就是一次意外的排除集改动。不要直接改这里的期望值。
    """
    from app.hal.base_station_compatibility import manifest_compatibility_digest
    from app.hal.uxm_base_station import RealUxmDriver

    driver = {"cmw500": RealCmw500Driver, "uxm": RealUxmDriver}[adapter]

    assert manifest_compatibility_digest(driver.adapter_manifest).startswith(
        expected
    )


@pytest.mark.parametrize(
    "adapter, expected",
    [
        ("cmw500", "c417c961"),
        ("uxm", "0c35808a"),
    ],
)
def test_binding_manifest_projection_is_pinned_to_its_baseline(
    adapter, expected
):
    """binding_digest 侧的 manifest 投影同样钉基线。

    这条是上一条的对称面，也是本片修过的一个真实漏网：初版只让
    `manifest_compatibility_digest` 排除了矩阵，而 `base_station_binding`
    仍在整份 dump —— 结果 binding_digest 照样漂，会让
    execution_qualification 的站点认证作用域失配、把已认证连接的正式执行
    静默降级成 diagnostic。

    ⚠️ 两处的 `exclude_none` 语义**不同**（compat 侧 True、binding 侧 False），
    统一成任何一个都会让另一边整体漂移 —— 所以投影函数把它交给调用方传。
    """
    from app.hal.base_station_compatibility import (
        canonical_payload_digest,
        digest_safe_manifest_payload,
    )
    from app.hal.uxm_base_station import RealUxmDriver

    driver = {"cmw500": RealCmw500Driver, "uxm": RealUxmDriver}[adapter]
    payload = digest_safe_manifest_payload(
        driver.adapter_manifest, exclude_none=False
    )

    assert canonical_payload_digest(payload).startswith(expected)


def test_binding_digest_payload_goes_through_the_shared_projection():
    """`binding_digest` 的 manifest 必须经共享投影，不能是裸 dump。

    上一条门只调 `digest_safe_manifest_payload` 本身，所以把
    `base_station_binding` 里的调用**撤回成裸 dump** 时它照样绿 ——
    测的是 helper，不是接线。这条从源码派生不变量补上那一格。

    为什么值得单独钉：binding_digest 的下游（`execution_qualification`）
    是**纯比对、无重算**的，一旦漂移就是站点认证作用域失配 →
    已认证连接的正式执行被静默降级成 diagnostic，且不能拿部署前的
    历史执行重新认证。
    """
    import ast
    import pathlib as _pathlib

    # 用 __file__ 定位，不依赖 pytest 的当前工作目录：从仓库根跑时
    # 相对路径会 FileNotFoundError，让这道门变成"换个目录就失效"。
    binding_file = (
        _pathlib.Path(__file__).resolve().parent.parent
        / "app"
        / "services"
        / "base_station_binding.py"
    )
    source = binding_file.read_text(encoding="utf-8")
    tree = ast.parse(source)

    manifest_values = [
        value
        for node in ast.walk(tree)
        if isinstance(node, ast.Dict)
        for key, value in zip(node.keys, node.values)
        if isinstance(key, ast.Constant) and key.value == "manifest"
    ]
    assert manifest_values, "未找到任何 manifest 键的字典字面量"

    projected = [
        value
        for value in manifest_values
        if isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id == "digest_safe_manifest_payload"
    ]
    assert projected, (
        "binding 的 digest payload 没有经过 digest_safe_manifest_payload —— "
        "裸 model_dump 会把 dimensions 矩阵算进 binding_digest"
    )
    # 投影必须显式传 exclude_none：两侧语义不同，默认值会让一边整体漂移
    for call in projected:
        assert any(
            kw.arg == "exclude_none" for kw in call.keywords
        ), "digest_safe_manifest_payload 必须显式传 exclude_none"


@pytest.mark.parametrize(
    "builtin_name",
    # 取 pydantic v2/v3 都保留的 model_* 成员：`copy` / `json` / `dict` 是 v1
    # 兼容方法，v3 移除后这门的前提断言会无谓变红。实测这类"hasattr 命中但
    # 不是字段"的成员共 27 个，这里取代表性的几个。
    ["model_dump", "model_config", "model_fields_set", "model_copy"],
)
def test_pydantic_builtin_names_are_not_mistaken_for_fields(builtin_name):
    """维度取名撞上 pydantic 内建成员时，要走「脱节」分支而不是拿 bound method 比对。

    `hasattr(profile, "model_dump")` 恒为真，用它判断字段是否存在，会让判定器
    拿一个方法对象去跟声明的取值比对 —— 方向仍是拒绝，但理由会指错地方
    （报成「该取值未声明」而不是「这个维度 profile 上根本没有」）。
    """
    from app.hal.base_station_compatibility import _mac_dimension_rejections

    manifest = RealCmw500Driver.adapter_manifest
    profile = _lte_requirements().mac_profile.profile
    assert hasattr(profile, builtin_name)               # 前提：确实是实例成员
    assert builtin_name not in type(profile).model_fields  # 但不是字段

    bogus = manifest.mac_profiles[0].model_copy(
        update={
            "dimensions": (
                BaseStationMacDimensionCapability(
                    dimension=builtin_name,
                    values=(BaseStationMacDimensionValueCapability(**_value()),),
                ),
            )
        }
    )
    rejections = _mac_dimension_rejections(
        profile=profile,
        manifest=manifest.model_copy(update={"mac_profiles": (bogus,)}),
    )

    assert any("does not have" in item for item in rejections), rejections


def test_table_2_32_citations_acknowledge_its_scenario_dimension():
    """引表 2-32 时必须承认它有「场景」维，不能压成单值。

    这条门是从**同一句话写错三次**里长出来的，第三次就死在这里：
    reason 曾写「表 2-32（pp.65-67）—— TM7 固定 1x2」，而 TM7 在该表里出现两次
    （`1x1 carrier` 场景是 `1x1`，`nx2 carrier` 场景才是 `1x2`）。
    表 2-32 是「场景 × TM × 天线」三维表，任何把某个 TM 压成单一天线值的引用
    都必然丢掉场景维。

    机械判据：提到"表 2-32"就必须同时提到"场景"，且不得出现"固定 / 即 / 就是"
    这类把多行压成一行的绝对化措辞。
    """
    import re as _re3

    # 只在绝对化措辞**后面紧跟一个单值**时才算违规（「固定 1x2」「即1x2」
    # 「就是单天线」），而不是见到「固定 / 就是 / 即」就拦 —— 否则
    # 「这就是本驱动未实现的原因」「该场景下带宽是固定的」这类正当叙述会被误伤。
    #
    # 「即」额外排除「使 / 便 / 时 / 刻」（即使、即便、即时、即刻）；
    # 但**不排除「为」** —— 「固定为 1x2」正是要抓的写法。
    absolute_patterns = (
        r"(?:(?:固定|就是)|(?<![立随])即(?![使便时刻]))"
        # 末尾**只认本矩阵真实用得到的取值**，不用泛化的 \d{1,2}：
        #   mimo_layers / NENBantennas = 1|2|4；CSI-RS 端口 = 1,2,4,8,12,16,24,32。
        # 泛化数字会把「即 79 页」「即 2026-09-02」这类页码/日期当成"压成单值"。
        # 长值在前，否则 "1" 会先吃掉 "16"；再排除后接「页」的写法（16 既是
        # 合法端口数也可能是页码）。
        r"\s*(?:是|为)?\s*"
        r"(?:\d+x\d+|单天线|双天线|(?:32|24|16|12|8|4|2|1)(?!\d)(?!\s*页))",
    )

    for name in ("transmission_mode", "mimo_layers"):
        for item in _dimension(name).values:
            # 用正则而不是子串：写成「表2-32」时子串判断会让这条门**静默跳过**，
            # 门失效却不报错 —— 那比没有门更糟。
            if not _re3.search(r"表\s*2-32", item.reason):
                continue
            assert "场景" in item.reason, (
                f"{name}={item.value!r} 引用了表 2-32 却未提及「场景」维 —— "
                f"该表按场景 × TM 列出，同一个 TM 可能占多行：{item.reason!r}"
            )
            for pattern in absolute_patterns:
                assert not _re3.search(pattern, item.reason), (
                    f"{name}={item.value!r} 用绝对化措辞把表 2-32 的多行压成了"
                    f"单值（命中 {pattern!r}）：{item.reason!r}"
                )
