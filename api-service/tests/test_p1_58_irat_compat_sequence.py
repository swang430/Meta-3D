"""P1-58: 兼容性普查的 critical 判定集从当前方言 profile 派生。

故障（roadmap Discovered，2026-08-06）：判定拿跨方言全局清单对单方言 profile，
「profile 未定义」被算成失败因子 → IRAT（现场方言）恒 4 条、5G_NR_Test 恒 20 条
→ `success` 在两个方言上都恒 False，现场健康检查永远点不亮绿灯。

修法（设计稿 docs/plans/2026-08-21-p1-58-irat-compat-sequence-design.md）：
判定集 = 全局 critical 能力清单 ∩ 当前 profile 实际定义（str）；未定义的一半
降为如实披露（extra["critical_not_in_profile"] + summary），不再参与 success。
fail-closed 三因子（实测 UNSUPPORTED / INFERRED_ONLY / aborted_early）原样保留。

措辞边界（uxm_command_profiles.py:627-648 权威口径 + NotebookLM 2026-08-21 查证）：
「未定义」≠「已验证不支持」—— 两个方向都无手册原文，序列与本文件都不下仪器断言。
"""
import asyncio
from unittest.mock import MagicMock

from app.diagnostics.sequences import uxm_scpi_compatibility as seq
from app.hal.uxm_command_profiles import (
    Uxm5GNRTestAppProfile,
    UxmLteNrIratProfile,
    UxmTestApp,
)


def _not_in_profile(profile) -> list:
    """与生产同判据地派生「critical 里 profile 未定义」清单（测试侧独立实现）。"""
    return sorted(
        n for n in seq._CRITICAL_NAMES
        if not isinstance(getattr(profile, n, None), str)
    )


class _ScriptedBs:
    """回放式假驱动：对 SYSTem:ERRor? 按「上一条探测命令」回错误队列。"""

    def __init__(self, profile, err_for_cmd=None):
        self._cmds = profile
        self.queries = []
        self._err_for_cmd = err_for_cmd or (lambda cmd: '0,"No error"')
        self._last_probe = None

    def _query(self, cmd):
        self.queries.append(cmd)
        if cmd == "SYSTem:ERRor?":
            last = self._last_probe
            return self._err_for_cmd(last) if last else '0,"No error"'
        self._last_probe = cmd
        return ""

    def _write(self, _cmd):
        return None


def _run(bs, params=None):
    hal = MagicMock()
    hal.drivers = {"baseStation": bs}
    return asyncio.run(seq.run(
        MagicMock(), hal, params or {}, log=lambda *_: None,
    ))


def test_irat_missing_profile_commands_are_disclosed_not_failed():
    """门①a：IRAT 下「方言 profile 没有的 critical 命令」不再判失败。

    2026-08-21 现状该清单是 4 条：APP_SELECT / MIMO_RX_ANT_PORT /
    MIMO_TX_ANT_PORT / PDSCH_AMC_ENABLE（断言按 profile 派生，不抄名单）。
    变异 M1（判据回退全局清单 → not_in_profile 恒空）/ M3（披露归零）→ 红。
    """
    expected = _not_in_profile(UxmLteNrIratProfile)
    assert expected, "本用例前提：IRAT 上确实有 critical 命令未在 profile 定义"

    result = _run(_ScriptedBs(UxmLteNrIratProfile))

    # 如实披露（不是失败）：extra 携带派生清单
    assert result.extra["critical_not_in_profile"] == expected
    # 未定义的不进任何失败因子
    assert result.extra["critical_unsupported"] == []
    assert not (set(expected) & set(result.extra["critical_unverified_actions"]))
    # 失败因子只剩 P1-46 拍板的 INFERRED_ONLY fail-closed（本片不动它）：
    # IRAT 定义了 CONFIG_APPLY / QCONFIG_APPLY_ALL 两条 mandatory ACTION，
    # 只读普查验证不了动作本身 → success 仍 False，但原因收窄且如实。
    assert result.extra["critical_unverified_actions"] == [
        "CONFIG_APPLY", "QCONFIG_APPLY_ALL",
    ]
    assert result.success is False
    # BLOCKER 总结不再点名未定义命令、不再带「未在方言 X 中定义」失败段落
    for name in expected:
        assert name not in result.summary
    assert "未在方言" not in result.summary


def test_5gnr_clean_firmware_reaches_green_end_to_end():
    """门①b：5G_NR_Test 全 clean 时序列终于能成功。

    该方言未定义任何 mandatory ACTION（CONFIG_APPLY / QCONFIG_APPLY_ALL 均
    None）→ 修后无任何失败因子。修前 20 条「未定义」恒致 False —— 本门红。
    """
    expected = _not_in_profile(Uxm5GNRTestAppProfile)
    assert expected, "本用例前提：5G 方言里确实有 critical 命令未在 profile 定义"

    result = _run(_ScriptedBs(Uxm5GNRTestAppProfile))

    assert result.success is True
    assert result.extra["critical_unsupported"] == []
    assert result.extra["critical_unverified_actions"] == []
    assert result.extra["critical_not_in_profile"] == expected
    # 成功总结如实：报 applicable 口径 + 披露未定义能力，不冒充全局全绿
    assert "BLOCKER" not in result.summary
    assert "未在本方言 profile 定义" in result.summary
    assert str(len(expected)) in result.summary


def test_irat_real_unsupported_critical_still_fails_closed():
    """门②：真缺失（profile 有、仪器答 -113）仍必须失败 —— fail-closed 不放水。

    变异 M2（success 去掉 critical_unsupported 因子）→ 红。
    「BLOCKER 不夹带未定义名字」半边在修前也红（旧 summary 会把 4 条
    未定义一并列进失败段落）。
    """
    broken = seq._to_probe_command(
        UxmLteNrIratProfile.CELL_BAND, UxmLteNrIratProfile)
    assert broken == "BSE:CONFig:NR5G:CELL1:BAND?"

    def err_for(probe_cmd):
        if probe_cmd == broken:
            return '-113,"Undefined header"'
        return '0,"No error"'

    result = _run(_ScriptedBs(UxmLteNrIratProfile, err_for))

    assert result.success is False
    assert "BLOCKER" in result.summary
    assert "CELL_BAND" in result.summary
    assert result.extra["critical_unsupported"] == ["CELL_BAND"]
    # 真缺失照报；「方言没有的」不得混进同一份失败清单
    for name in _not_in_profile(UxmLteNrIratProfile):
        assert name not in result.summary


def test_critical_partition_invariants_per_profile():
    """门③（不变量）：判定集 ⊆ 当前方言实际会被普查遍历的命令集。

    partition 完整性同时成立：applicable ∪ not_in_profile == 全局清单、两半不交
    —— 防「第三种静默漏斗」（某能力既不进判定也不进披露，即 #275 P2 假绿的根）。
    """
    for profile in (Uxm5GNRTestAppProfile, UxmLteNrIratProfile):
        applicable, not_in_profile = seq._critical_partition(profile)
        walked = {name for name, _ in seq._all_commands(profile)}
        assert applicable <= walked, (
            f"{profile.PROFILE_NAME}: 判定集含普查根本不会遍历的名字 "
            f"{sorted(applicable - walked)}"
        )
        assert applicable | set(not_in_profile) == seq._CRITICAL_NAMES
        assert applicable.isdisjoint(not_in_profile)

    # 实例形态（live 驱动的 _cmds 是实例）与类形态判定一致
    inst_applicable, inst_rest = seq._critical_partition(UxmLteNrIratProfile())
    cls_applicable, cls_rest = seq._critical_partition(UxmLteNrIratProfile)
    assert inst_applicable == cls_applicable
    assert inst_rest == cls_rest


def test_partition_base_profile_self_check():
    """门③自测（判定器自测形态）：对基类 profile（几乎全 None），partition
    必须把绝大多数 critical 划入 not_in_profile —— 防判据退化成恒全 applicable。"""
    applicable, not_in_profile = seq._critical_partition(UxmTestApp)
    # 基类只有 IEEE 488.2 五条 + ERR；critical 里 str 的只剩 IDN / ERR
    assert applicable == frozenset({"IDN", "ERR"})
    assert set(not_in_profile) == set(seq._CRITICAL_NAMES) - {"IDN", "ERR"}
