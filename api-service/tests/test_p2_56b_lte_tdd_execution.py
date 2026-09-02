# -*- coding: utf-8 -*-
"""P2-56 ②：LTE TDD 正式路径的行为门。

① 声明半只加声明、零可达状态；② 把 TDD **变成可达的正式路径**，所以这里的门
必须打在**真实生效端**上：下发了什么、回读比对了什么、什么情况下一个字都不写。
"""

import pytest

from app.hal.base_station_mac_profile import (
    CMW500_LTE_PROFILE_SOURCE,
    LteRmcMacTestProfileV1,
)
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.cmw500_command_profile import (
    CMW500_LTE_FULL_RB_RMC_BY_BANDWIDTH,
)

from tests.test_p2_51_cmw_mac_config import _MacDriver


#: ⚠️ **刻意避开手册的 `*RST`**（ULDL `*RST 1` / SSUBframe `*RST 7`，pp.687-688）。
#: 内审 F6：初版全部用例都用 1 / 7，于是「把下发值与期望值都写死成 *RST」
#: 这个变异**全绿** —— 门恰好证明不了它最想证明的那件事（值来自 profile，
#: 不是从仪器默认补真）。换成非默认值后该变异转红。
_TDD_ULDL = 2
_TDD_SSUB = 4


def _tdd_kwargs(**over):
    payload = {
        "mimo_layers": 2,
        "duplex": "tdd",
        "uldl_configuration": _TDD_ULDL,
        "special_subframe": _TDD_SSUB,
    }
    payload.update(over)
    return payload


def _lte_profile(**over):
    payload = {
        "schema_version": 1, "kind": "lte_rmc", "profile_version": 1, "rat": "lte",
        "test_intent": "downlink_throughput", "mimo_layers": 2,
        "statistical_window": {"unit": "subframes", "count": 5000},
        "metric_requirements": [
            {"key": "dl_throughput_mbps", "scope": "pcell"},
            {"key": "dl_bler_percent", "scope": "pcell"},
        ],
        "scheduling_mode": "rmc", "resource_allocation": "full",
        "enable_amc": False, "duplex": "fdd", "transmission_mode": "TM3",
        "source_reference": CMW500_LTE_PROFILE_SOURCE,
    }
    payload.update(over)
    return LteRmcMacTestProfileV1.model_validate(payload)


# --------------------------------------------------------------------------
# 1. profile 层：TDD 维度与 duplex 的耦合，两个方向都拒
# --------------------------------------------------------------------------


def test_fdd_profile_must_not_carry_tdd_fields():
    """FDD 却设了 TDD 字段 → 拒。

    这些值在 FDD 分支**不会被下发**，留着等于给读 profile 的人一个假承诺。
    """
    for field in ("uldl_configuration", "special_subframe", "rmc_version"):
        with pytest.raises(Exception) as excinfo:
            _lte_profile(**{field: 0})
        assert field in str(excinfo.value)


def test_tdd_profile_must_declare_frame_structure():
    """TDD 却不给配比/特殊子帧 → 拒（不让驱动用仪器 *RST 补真）。"""
    with pytest.raises(Exception):
        _lte_profile(duplex="tdd")
    with pytest.raises(Exception):
        _lte_profile(duplex="tdd", uldl_configuration=1)
    with pytest.raises(Exception):
        _lte_profile(duplex="tdd", special_subframe=7)
    # 两个都给就通过；rmc_version 可选（是否必需取决于活体带宽）
    ok = _lte_profile(duplex="tdd", uldl_configuration=1, special_subframe=7)
    assert ok.rmc_version is None


@pytest.mark.parametrize("bad", [8, 9])
def test_special_subframe_8_and_9_stay_unreachable(bad):
    """值 8/9 手册要求 normal cyclic prefix，本驱动无 CP 维度 → 构造层即拒。

    它们在能力矩阵里**仍有声明**（带 `requires` token、标 diagnostic_only），
    属「声明了但不可达」—— 要放开须同片补 CP 维度。
    """
    with pytest.raises(Exception):
        _lte_profile(duplex="tdd", uldl_configuration=1, special_subframe=bad)


# --------------------------------------------------------------------------
# 2. 驱动层：活体/profile 一致性（放开 duplex 新造出来的那一格）
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tdd_profile_against_tdd_instrument_sends_frame_structure():
    """TDD 正式路径：配比与特殊子帧确实下发并回读比对。"""
    driver = _MacDriver(duplex="TDD", bandwidth="B100")

    result = await driver._configure_mac_throughput_values(**_tdd_kwargs())

    assert result.ok, result.error
    joined = " | ".join(driver.writes)
    assert f"CONFigure:LTE:SIGN1:CELL:PCC:ULDL {_TDD_ULDL}" in joined
    assert f"CONFigure:LTE:SIGN1:CELL:PCC:SSUBframe {_TDD_SSUB}" in joined
    # 这两个值都不是 *RST（1 / 7）—— 证明它们确实来自 profile
    assert _TDD_ULDL != 1 and _TDD_SSUB != 7
    # 回读确认打在真实生效端上
    assert "CONFigure:LTE:SIGN1:CELL:PCC:ULDL?" in driver.queries
    assert "CONFigure:LTE:SIGN1:CELL:PCC:SSUBframe?" in driver.queries


@pytest.mark.asyncio
async def test_fdd_path_never_sends_tdd_commands():
    """FDD 不回归：TDD 那三条命令一条都不许出现。"""
    driver = _MacDriver(duplex="FDD", bandwidth="B200")

    result = await driver._configure_mac_throughput_values(mimo_layers=2)

    assert result.ok, result.error
    joined = " | ".join(driver.writes + driver.queries)
    for token in ("ULDL", "SSUBframe", "VERSion:DL"):
        assert token not in joined, f"FDD 路径发了 TDD 专属命令 {token}"


@pytest.mark.asyncio
async def test_frame_structure_readback_mismatch_fails_the_group():
    """回读不符 → 该组失败（验证打在生效端，不是「我发过了」）。"""
    driver = _MacDriver(
        duplex="TDD",
        bandwidth="B100",
        query_overrides={"CONFigure:LTE:SIGN1:CELL:PCC:ULDL?": "5"},
    )

    result = await driver._configure_mac_throughput_values(**_tdd_kwargs())

    assert not result.ok
    # ⚠️ 精确断言那一行的状态（内审 F10）：初版写的是 `status != "applied"`，
    #    而 `_confirm` 产出的 status 只有 "confirmed"（成功）与 "unknown"
    #    （各类失败）—— 从来不是 "applied"，所以那个条件对成功行也为真。
    rows = {row.field: row for row in result.receipt.fields}
    assert rows["tdd_uldl_configuration"].status == "unknown"
    # 组名落在 receipt.reason（本方法对单组被拒是记账不中断），不在 error
    assert "CELL_ULDL" in result.receipt.reason
    assert "回读" in result.receipt.reason


@pytest.mark.asyncio
async def test_driver_rejects_tdd_fields_under_fdd_even_via_kwargs():
    """驱动层也要挡「FDD 却带 TDD 字段」——不能只靠 profile 校验。

    ⚠️ 这条门是变异跑发现的缺口：把驱动里那句拒绝删掉，**全部门仍绿**，
    因为其余用例都经 profile 构造（那层确实挡住了）。而
    `_configure_mac_throughput_values` 是可以按 kwargs 直接调用的
    （mock 路径与本文件多数用例走的正是这条），那条路不过 profile 校验。
    """
    for field in ("uldl_configuration", "special_subframe", "rmc_version"):
        driver = _MacDriver(duplex="FDD", bandwidth="B100")
        result = await driver._configure_mac_throughput_values(
            mimo_layers=2, duplex="fdd", **{field: 0}
        )
        assert not result.ok, field
        assert field in (result.error or ""), field
        assert driver.writes == [], field


# --------------------------------------------------------------------------
# 3. RMC 版本：只在表 2-39 有歧义的带宽上必发，两向 fail-loud
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ambiguous_bandwidth_requires_an_explicit_version():
    """20 MHz 的 TDD 满配 DL 行有两个版本 → profile 不给就 fail-loud，不默认 *RST 0。"""
    driver = _MacDriver(duplex="TDD", bandwidth="B200")

    result = await driver._configure_mac_throughput_values(**_tdd_kwargs())

    assert not result.ok
    assert "rmc_version" in (result.error or "")
    assert driver.writes == []


@pytest.mark.asyncio
async def test_unambiguous_bandwidth_rejects_a_stray_version():
    """无歧义带宽却指定版本 → 拒，不下发一条手册限定「仅对某些 RMC 相关」的命令。"""
    driver = _MacDriver(duplex="TDD", bandwidth="B100")

    result = await driver._configure_mac_throughput_values(
        **_tdd_kwargs(rmc_version=1)
    )

    assert not result.ok
    assert "rmc_version" in (result.error or "")
    assert driver.writes == []


@pytest.mark.asyncio
async def test_ambiguous_bandwidth_sends_version_after_the_rmc_rows():
    """版本下发的**位置**取自手册 §2.5.20 示例（p.342）：排在 RMC/RBPosition 之后。

    顺序不是我们排的 —— 手册示例把 `RMC:VERSion:DL` 放在
    `RMC:DL / RBPosition:DL / RMC:UL / RBPosition:UL` 后面。
    """
    driver = _MacDriver(duplex="TDD", bandwidth="B200")

    result = await driver._configure_mac_throughput_values(
        **_tdd_kwargs(rmc_version=1)
    )

    assert result.ok, result.error
    headers = [w.partition(" ")[0] for w in driver.writes]
    version_at = headers.index("CONFigure:LTE:SIGN1:CONNection:PCC:RMC:VERSion:DL1")
    for earlier in (
        "CONFigure:LTE:SIGN1:CONNection:PCC:RMC:DL1",
        "CONFigure:LTE:SIGN1:CONNection:PCC:RMC:RBPosition:DL1",
        "CONFigure:LTE:SIGN1:CONNection:PCC:RMC:UL",
        "CONFigure:LTE:SIGN1:CONNection:PCC:RMC:RBPosition:UL",
    ):
        assert headers.index(earlier) < version_at, f"{earlier} 应在版本之前"
    # DLEQual 耦合的生效端证据：流 2 也要回读到同一版本
    assert (
        "CONFigure:LTE:SIGN1:CONNection:PCC:RMC:VERSion:DL2?" in driver.queries
    )


def test_version_requirement_is_derived_from_the_manual_table_not_hardcoded():
    """「哪些带宽要版本」是数据派生的不变量，不是逐带宽 if。"""
    assert {
        token
        for token, plan in CMW500_LTE_FULL_RB_RMC_BY_BANDWIDTH.items()
        if plan.tdd_dl_version_required
    } == {"B200"}


# --------------------------------------------------------------------------
# 4. 三处 duplex→选件 的硬编码必须与矩阵一致
# --------------------------------------------------------------------------


def test_formal_option_set_has_exactly_one_source():
    """一次 LTE 正式执行所需的选件集**只有一个真值源**。

    内审 F3/F7 的合并结论。此前这套映射在三处各写一份，其中**两处漏了
    KS510**（ULDL 的 Options 原文是「KS550 **and** KS510」，pp.687-688）；
    而 ① 声明半时那些 `required_options` 挂在不可达的格上，所以漏项无害 ——
    ② 让 TDD 可达之后它才会咬人。

    ⚠️ 初版这道门用 `inspect.getsource(...) 里有没有 "KS500" 字样` 来判，
    **对驱动那一侧是恒真断言**：矩阵的 `satisfying_options=("KS500",)`
    就在同一个类里，所以第一段 assert 一旦成立，字符串必然找得到。
    换成 AST：断言两处消费方**确实调用**了共享函数。
    """
    import ast as _ast
    import inspect

    from app.hal import cmw500_base_station as drv
    from app.hal.cmw500_command_profile import cmw500_lte_formal_options
    from app.services.mimo_ota import base_station_execution_evidence as bse

    # ① 真值源的内容 = 手册原文
    assert cmw500_lte_formal_options("fdd") == frozenset({"KS520", "KS500"})
    assert cmw500_lte_formal_options("tdd") == frozenset(
        {"KS520", "KS550", "KS510"}
    )
    with pytest.raises(ValueError):
        cmw500_lte_formal_options("nr5g")

    # ② 两处消费方确实调它，且**定位到具体那个函数**（复审 F5：只断言
    #    「模块里存在该调用」太宽 —— 调用挪到别处、原判定点自己写一份也不红）
    for module, func_name, label in (
        (drv, "evaluate_lte_2x2_formal_capability", "驱动"),
        (bse, "_formal_envelope", "正式 KPI 准入门"),
    ):
        tree = _ast.parse(inspect.getsource(module))
        target = next(
            (
                node
                for node in _ast.walk(tree)
                if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef))
                and node.name == func_name
            ),
            None,
        )
        assert target is not None, f"{label} 找不到 {func_name}"
        called = {
            node.func.id
            for node in _ast.walk(target)
            if isinstance(node, _ast.Call) and isinstance(node.func, _ast.Name)
        }
        assert "cmw500_lte_formal_options" in called, (
            f"{label} 的 {func_name} 没有调用共享的选件真值源 —— 又自己写了一份？"
        )

    # ③ 矩阵是**声明**，必须与真值源相容：声明的选件 ⊆ 该 duplex 的必需集
    matrix = {
        item.value: set(item.satisfying_options)
        for profile in RealCmw500Driver.adapter_manifest.mac_profiles
        for dimension in profile.dimensions
        if dimension.dimension == "duplex"
        for item in dimension.values
    }
    for duplex, declared in matrix.items():
        # ⚠️ 先要求非空（复审 F5）：`空集 <= 任何集合` 恒真，
        #    矩阵把声明删空也不会红。
        assert declared, f"矩阵没给 duplex={duplex} 声明任何选件"
        assert declared <= cmw500_lte_formal_options(duplex), (
            f"矩阵给 duplex={duplex} 声明的选件 {declared} 不在真值源里"
        )


# --------------------------------------------------------------------------
# 5. 正式证据的记录端（判定端换源了，记录端也必须换）
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_success_summary_records_the_real_duplex_and_tdd_values():
    """成功摘要必须记真实 duplex 与三组 TDD 值。

    ⚠️ 这条门来自内审 F1（P1）：判定端已经换源成「跟 frozen profile 比」，
    而记录端还写着字面量 `FDD` —— 一次 TDD 执行的**正式证据**（经
    `execution_scpi_evidence` 落库）会永久记成 FDD，且摘要里完全没有
    ULDL / SSUBframe / VERSion 这三组本片新增的核心配置。
    """
    driver = _MacDriver(duplex="TDD", bandwidth="B200")
    result = await driver._configure_mac_throughput_values(
        **_tdd_kwargs(rmc_version=1)
    )
    assert result.ok, result.error

    summary = result.receipt.reason
    assert "TDD" in summary and "FDD" not in summary, summary
    assert f"ULDL={_TDD_ULDL}" in summary, summary
    assert f"SSUBframe={_TDD_SSUB}" in summary, summary
    assert "VERSion:DL=1" in summary, summary

    # 非歧义带宽（B100）：摘要有 ULDL/SSUBframe，但**不该**有版本
    # （复审 F4：把 `if tdd_dl_version_required` 换成 `if True` 时全绿 ——
    #  那样 B100 的正式证据会写一条从未下发的 `VERSion:DL=None`）
    driver = _MacDriver(duplex="TDD", bandwidth="B100")
    result = await driver._configure_mac_throughput_values(**_tdd_kwargs())
    assert result.ok, result.error
    summary = result.receipt.reason
    assert f"ULDL={_TDD_ULDL}" in summary and "TDD" in summary, summary
    assert "VERSion:DL" not in summary, summary

    # FDD 侧对照：摘要记 FDD，且不出现 TDD 三组
    driver = _MacDriver(duplex="FDD", bandwidth="B200")
    result = await driver._configure_mac_throughput_values(mimo_layers=2)
    assert result.ok, result.error
    summary = result.receipt.reason
    assert "FDD" in summary and "TDD" not in summary, summary
    for token in ("ULDL=", "SSUBframe=", "VERSion:DL="):
        assert token not in summary, summary


@pytest.mark.parametrize(
    "field, bad",
    [
        ("uldl_configuration", 7),      # Range 是 0..6
        ("special_subframe", 8),        # 本驱动只放开 0..7
        ("special_subframe", 9),
        ("rmc_version", 2),             # Range 是 0..1
    ],
)
@pytest.mark.asyncio
async def test_driver_rejects_out_of_domain_tdd_values_via_kwargs(field, bad):
    """驱动层也要挡越域取值 —— 与「FDD 带 TDD 字段」同一条 kwargs 直调路径。

    ⚠️ 内审 F8：`build_mac_cell_ssubframe` 按**手册全域** 0..9 校验，而本驱动
    只放开 0..7（值 8/9 要求 normal cyclic prefix，无 CP 维度）。这个收窄
    只写在 profile 的 Literal 里，而内层方法可被 kwargs 直调、不过 profile。
    """
    driver = _MacDriver(duplex="TDD", bandwidth="B100")
    result = await driver._configure_mac_throughput_values(
        **_tdd_kwargs(**{field: bad})
    )
    assert not result.ok
    assert field in (result.error or "")
    assert driver.writes == []
