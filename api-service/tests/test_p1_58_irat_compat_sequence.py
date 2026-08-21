"""P1-58: 兼容性普查的 critical 判定集从当前方言 profile 派生。

故障（roadmap Discovered，2026-08-06）：判定拿跨方言全局清单对单方言 profile，
「profile 未定义」被算成失败因子 → IRAT（现场方言）恒 4 条、5G_NR_Test 恒 20 条
→ `success` 在两个方言上都恒 False，现场健康检查永远点不亮绿灯。

修法（设计稿 docs/plans/2026-08-21-p1-58-irat-compat-sequence-design.md）：
判定集 = 全局 critical 能力清单 ∩ 当前 profile 实际定义（str）；未定义的一半
**不再被报成 BLOCKER / "仪器拒绝"**，而是如实披露（extra["critical_not_in_profile"]
+ summary）。但它也不能让 success 变 True（Codex #358 R1 P1：profile 口径 None =
未经查证；GUI 拿 success 画绿牌；生产驱动对同一批 None 会拒绝配置）—— 判决四态：
BLOCKER（实测 UNSUPPORTED / INFERRED_ONLY / 早退）> UNDETERMINED（无实测失败但有
未定义 critical，不能判健康）> SUCCESS（全定义且全支持）；ABORTED 另列。
⚠ 在 P1-46 拍板（CONFIG_APPLY / QCONFIG_APPLY_ALL 只读普查验证不了）下，SUCCESS
在生产 profile 上结构性不可达：定义它们 → BLOCKER，不定义 → UNDETERMINED。

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


def _fully_defined_profile():
    """把 5G_NR_Test profile 里 critical 清单中为 None 的能力全部补成**假的**可探测命令。

    只用于证明判决逻辑本身可达 SUCCESS / 隔离单一失败因子；这些命令形式不是手册
    查证过的，**绝不能**流入生产 profile（禁盲试）。
    """
    # critical 本身 + 动作命令做邻居推断要用的只读邻居（否则 ACTION 会因
    # "neighbor not probed" 记成 UNKNOWN → 假的 unsupported）
    needed = set(seq._CRITICAL_NAMES) | {
        q for q in seq._ACTION_NEIGHBOR_QUERY.values() if q
    }
    attrs = {
        n: f"CONFig:P158TEST:{n}"
        for n in needed
        if not isinstance(getattr(Uxm5GNRTestAppProfile, n, None), str)
    }
    attrs["PROFILE_NAME"] = "P158_FULLY_DEFINED"
    return type("_FullyDefinedProfile", (Uxm5GNRTestAppProfile,), attrs)


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
    """门①a：IRAT 下「方言 profile 没有的 critical 命令」不再被报成 BLOCKER 的失败项。

    2026-08-21 现状该清单是 4 条：APP_SELECT / MIMO_RX_ANT_PORT /
    MIMO_TX_ANT_PORT / PDSCH_AMC_ENABLE（断言按 profile 派生，不抄名单）。
    变异 M1（判据回退全局清单 → not_in_profile 恒空）/ M3（披露归零）→ 红。
    """
    expected = _not_in_profile(UxmLteNrIratProfile)
    assert expected, "本用例前提：IRAT 上确实有 critical 命令未在 profile 定义"

    result = _run(_ScriptedBs(UxmLteNrIratProfile))

    # 如实披露：extra 携带派生清单
    assert result.extra["critical_not_in_profile"] == expected
    # 未定义的不进任何**实测**失败因子
    assert result.extra["critical_unsupported"] == []
    assert not (set(expected) & set(result.extra["critical_unverified_actions"]))
    # 实测失败因子只剩 P1-46 拍板的 INFERRED_ONLY fail-closed（本片不动它）：
    # IRAT 定义了 CONFIG_APPLY / QCONFIG_APPLY_ALL 两条 mandatory ACTION，
    # 只读普查验证不了动作本身 → BLOCKER，success False，但原因收窄且如实。
    assert result.extra["critical_unverified_actions"] == [
        "CONFIG_APPLY", "QCONFIG_APPLY_ALL",
    ]
    assert result.success is False
    assert result.extra["verdict"] == "BLOCKER"
    blocker_part, _, disclosure = result.summary.partition("；另有")
    assert blocker_part.startswith("BLOCKER")
    # BLOCKER 段不点名未定义命令（它们不是"仪器拒绝"）；披露段必须在且点名
    for name in expected:
        assert name not in blocker_part
        assert name in disclosure
    assert "未探测、无结论" in disclosure


def test_5gnr_clean_firmware_is_undetermined_not_green():
    """门①b：5G_NR_Test 全 clean → **UNDETERMINED**，不是 BLOCKER、也不是绿。

    该方言无 mandatory ACTION、已定义命令全 clean → 零实测失败因子；但 20 条
    critical 能力在 profile 里是 None（= 未经查证，从未探测）—— 健康检查不能
    因此报绿（Codex #358 R1 P1）。修前（P1-58 之前）这里是 BLOCKER 且把 20 条
    当"不支持"列进失败段落；本片初版又把它判成了 success=True（假绿）。
    变异：success 放行 not_in_profile → 红；verdict 把 UNDETERMINED 写成 SUCCESS → 红。
    """
    expected = _not_in_profile(Uxm5GNRTestAppProfile)
    assert expected, "本用例前提：5G 方言里确实有 critical 命令未在 profile 定义"

    result = _run(_ScriptedBs(Uxm5GNRTestAppProfile))

    assert result.success is False
    assert result.extra["verdict"] == "UNDETERMINED"
    assert result.extra["critical_unsupported"] == []
    assert result.extra["critical_unverified_actions"] == []
    assert result.extra["critical_not_in_profile"] == expected
    assert result.summary.startswith("UNDETERMINED")
    assert "BLOCKER" not in result.summary
    assert "不能判健康" in result.summary and str(len(expected)) in result.summary
    # 措辞边界：不对仪器下"不支持"断言
    assert "实测不支持" not in result.summary


def test_success_is_reachable_when_everything_defined_and_clean(monkeypatch):
    """门①c：判决逻辑本身可达 SUCCESS —— 防"恒 False"的退化写法。

    用补满的 profile（critical 全部定义）+ 全 clean 固件；并临时清空 P1-46 的
    mandatory-direct-evidence 集（否则 CONFIG_APPLY / QCONFIG_APPLY_ALL 一被定义
    就 BLOCKER）。⚠ 这正说明：**P1-46 拍板不变时，生产 profile 上 SUCCESS 不可达**
    —— 不是本片引入，是如实状态，需用户拍板（改策略 / 另建能直接验证 apply 的剧本）。
    变异：verdict 分支把 SUCCESS 写成 UNDETERMINED → 红。
    """
    monkeypatch.setattr(
        seq, "_MANDATORY_ACTIONS_REQUIRING_DIRECT_EVIDENCE", frozenset())
    profile = _fully_defined_profile()
    assert _not_in_profile(profile) == []

    result = _run(_ScriptedBs(profile))

    assert result.success is True
    assert result.extra["verdict"] == "SUCCESS"
    assert result.extra["critical_not_in_profile"] == []
    assert result.summary.startswith(f"All {len(seq._CRITICAL_NAMES)} critical")
    assert "UNDETERMINED" not in result.summary and "BLOCKER" not in result.summary


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
    assert result.extra["verdict"] == "BLOCKER"
    blocker_part, _, disclosure = result.summary.partition("；另有")
    assert blocker_part.startswith("BLOCKER") and "CELL_BAND" in blocker_part
    assert result.extra["critical_unsupported"] == ["CELL_BAND"]
    # 真缺失照报；「方言没有的」不得混进失败清单（只许出现在披露段）
    for name in _not_in_profile(UxmLteNrIratProfile):
        assert name not in blocker_part


def test_real_unsupported_critical_fails_without_other_factors(monkeypatch):
    """门②b：真缺失是 success 的**独立**失败因子 —— 变异 M2 的专属探针。

    IRAT 上门②的 False 有 unverified_actions 兜底、5G 上有 not_in_profile 兜底，
    M2（success 放行 critical_unsupported）在那两处都会逃逸。这里用补满 profile +
    清空 mandatory 动作集，把其它因子全部拿掉：本场景的 False 只由 unsupported 撑起。
    """
    monkeypatch.setattr(
        seq, "_MANDATORY_ACTIONS_REQUIRING_DIRECT_EVIDENCE", frozenset())
    profile = _fully_defined_profile()
    broken = seq._to_probe_command(profile.CELL_BAND, profile)
    assert broken == "CONFig:NR5G:CELL0:BAND?"

    def err_for(probe_cmd):
        if probe_cmd == broken:
            return '-113,"Undefined header"'
        return '0,"No error"'

    result = _run(_ScriptedBs(profile, err_for))

    assert result.extra["critical_unverified_actions"] == []
    assert result.extra["critical_not_in_profile"] == []
    assert result.extra["critical_unsupported"] == ["CELL_BAND"]
    assert result.success is False
    assert result.extra["verdict"] == "BLOCKER"
    assert "BLOCKER" in result.summary


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
