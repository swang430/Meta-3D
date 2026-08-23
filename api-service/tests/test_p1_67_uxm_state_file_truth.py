"""P1-67: UXM 状态文件命令换手册真值。

故障（roadmap Discovered「驱动层事实」第 2 条，P1-65 #380 手册对账）：
`configure(state_file=…)` 一键配置路径发的是手册不存在的命令
`SYSTem:CONFiguration:LOAD`（六份手册 md + HTML 0 命中，真机必 -113）——
"一键配置"从未可能工作过；`list_state_files` 的 `MMEMory:CATalog?` 同。

手册真值（本地原件 `Instrument_API_Doc/Keysight UXM NR SCPI/`
`UXM5G_SCPI_06_General_Examples_Shared.md`「Utility > Export / Import SCPI」节）：
- `SYSTem:SCPI:IMPort "<file>"` —— "Import (i.e. load) a SCPI file, recovering
  a previously exported application state"
- `SYSTem:SCPI:EXPort "<file>"` —— "Export (i.e. save) the current application
  state into a SCPI file"
- `SYSTem:SCPI:IMPort:STATus?` —— Query only，"Queries the success or failure
  of an import"；Boolean（Range ON|1|OFF|0），**哪个值是成功手册未给** ——
  驱动按保守判法（解析出 ON/1 才算成功，解析不出按失败），fail-closed。
- 手册没有文件列表查询命令（`MMEMory:CATalog?` 查无；未探测 ≠ 不支持）。
- 命令标 Application Mode `NSA | SA`；IRAT 下可用性手册未说明 ——
  IRAT profile 三字段保持 None，`load_state_file` 如实拒绝。

假驱动照 `tests/test_p1_58_irat_compat_sequence.py` 的 `_ScriptedBs` 形态
（回复表驱动、记录全部命令），会话形态照 `tests/test_p02_uxm_truth_source.py`
的 `_FakeUxmSession`（真实生效端 = 发到会话上的命令，不钉内部状态）。

变异清单（内存快照还原实跑，见 PR/报告）：
- M1 IMPort 后不查 STATus? → 门 1/2 红；
- M2 换回编造命令 SYSTem:CONFiguration:LOAD → 门 1 红；
- M3 路径注入放行 → 门 3 红；
- M4 STATus? 解析不出当成功 → 门 2 红。
"""
from __future__ import annotations

from typing import Dict, List

import pytest

from app.hal.uxm_base_station import VISA_TIMEOUT_STATE_LOAD, RealUxmDriver
from app.hal.uxm_command_profiles import (
    Uxm5GNRTestAppProfile,
    UxmLteNrIratProfile,
)

# 编造命令 —— 任何路径都不许再发（写或查）。
_FABRICATED = ("SYSTem:CONFiguration:LOAD", "SYSTem:CONFiguration:SAVE",
               "MMEMory:CATalog?")


class _FakeUxmSession:
    """回复表驱动的假会话：按「查询串包含的子串 → 回复」匹配，
    先命中先用；未命中回 ""。记录全部写入与查询（真实生效端）。"""

    def __init__(self, replies: Dict[str, str]):
        self.replies = dict(replies)
        self.written: List[str] = []
        self.queried: List[str] = []
        self.ops: List[str] = []  # 写与查的**时序**统一记录
        self.timeout = 5000

    def write(self, cmd: str) -> None:
        c = cmd.strip()
        self.written.append(c)
        self.ops.append(c)

    def query(self, cmd: str) -> str:
        c = cmd.strip()
        self.queried.append(c)
        self.ops.append(c)
        for needle, reply in self.replies.items():
            if needle in c:
                return reply
        return ""

    @property
    def all_scpi(self) -> List[str]:
        return self.ops


_CLEAN_REPLIES = {
    "SYSTem:SCPI:IMPort:STATus?": "1",
    "SYSTem:ERRor?": '0,"No error"',
    "*OPC?": "1",
}


def _mk_5g(replies: Dict[str, str]) -> tuple[RealUxmDriver, _FakeUxmSession]:
    d = RealUxmDriver("uxm-5g", {"ip": "10.0.0.1"})  # 默认 5G_NR_Test
    assert d._cmds.PROFILE_NAME == Uxm5GNRTestAppProfile.PROFILE_NAME
    sess = _FakeUxmSession(replies)
    d._visa_session = sess
    return d, sess


def _mk_irat(replies: Dict[str, str]) -> tuple[RealUxmDriver, _FakeUxmSession]:
    d = RealUxmDriver("uxm-irat", {"ip": "10.0.0.2", "uxm_profile": "irat"})
    assert d._cmds.PROFILE_NAME == UxmLteNrIratProfile.PROFILE_NAME
    sess = _FakeUxmSession(replies)
    d._visa_session = sess
    return d, sess


def _assert_no_fabricated(sess: _FakeUxmSession) -> None:
    for cmd in sess.all_scpi:
        for bad in _FABRICATED:
            assert bad not in cmd, f"发出了编造命令: {cmd!r}"


# ── 门 1：configure(state_file=…) 走手册 IMPort + STATus? 复核 ─────────────

class TestConfigureStateFileManualTruth:
    @pytest.mark.asyncio
    async def test_configure_sends_import_and_status_check(self):
        d, sess = _mk_5g(dict(_CLEAN_REPLIES))
        ok = await d.configure({"state_file": "N78_100M.scpi"})
        assert ok is True
        assert 'SYSTem:SCPI:IMPort "N78_100M.scpi"' in sess.written
        assert "SYSTem:SCPI:IMPort:STATus?" in sess.queried
        # 写后读了错误队列
        assert "SYSTem:ERRor?" in sess.queried
        _assert_no_fabricated(sess)

    @pytest.mark.asyncio
    async def test_set_cell_config_shortcut_also_walks_manual_import(self):
        """第二入口：`apply_topology_profile → to_config_dict()` 只给 state_file 时
        走 `set_cell_config` 开头的捷径（uxm_base_station.py:1343），不经 configure()。
        内审变异 MUT-D（删该捷径）此前对本文件全绿 —— 此例补上该盲区：
        捷径必须同样走手册 IMPort + STATus? 复核，不得静默退化成空参数配置。"""
        d, sess = _mk_5g(dict(_CLEAN_REPLIES))
        ok = await d.set_cell_config({"state_file": "N78_100M.scpi"})
        assert ok is True
        assert 'SYSTem:SCPI:IMPort "N78_100M.scpi"' in sess.written
        assert "SYSTem:SCPI:IMPort:STATus?" in sess.queried
        _assert_no_fabricated(sess)

    @pytest.mark.asyncio
    async def test_timeout_restored_when_import_write_raises(self):
        """长超时（VISA_TIMEOUT_STATE_LOAD=60s）设置后 IMPort 写入抛异常，
        超时必须恢复原值 —— 否则本会话后续所有 SCPI 都继承 60s 超时（级联慢）。
        触发点选 IMPort 写入本身：它严格发生在超时设置之后，避免更早的
        stop_signaling 阶段抛异常造成「超时从未被设置」的假绿。"""
        d, sess = _mk_5g(dict(_CLEAN_REPLIES))
        sess.timeout = 4321  # 非默认值：区分「恢复原值」与「写死默认」(内审 F2)
        seen_at_import: List[int] = []
        orig_write = sess.write

        def _boom(cmd: str) -> None:
            if "SYSTem:SCPI:IMPort" in cmd:
                seen_at_import.append(sess.timeout)
                raise IOError("VISA write failed mid-import")
            orig_write(cmd)

        sess.write = _boom
        ok = await d.configure({"state_file": "a.scpi"})
        assert ok is False
        # 导入窗口内确实抬到长超时（内审 F3：删设置行 / *OPC? 挪出窗口在这红）
        assert seen_at_import == [VISA_TIMEOUT_STATE_LOAD]
        assert sess.timeout == 4321, "异常路径长超时未恢复原值"

    @pytest.mark.asyncio
    async def test_original_error_not_masked_when_session_lost_mid_import(self):
        """IMPort 写入断链、静默重连失败把 `_visa_session` 置 None 时，finally
        的超时恢复不得抛 `NoneType` AttributeError 吃掉原始异常 —— 失败归因
        (`_last_error`) 必须是断链原因，现场靠它区分「链路断」和「代码崩」。"""
        d, sess = _mk_5g(dict(_CLEAN_REPLIES))
        orig_write = sess.write

        def _boom(cmd: str) -> None:
            if "SYSTem:SCPI:IMPort" in cmd:
                d._visa_session = None  # 模拟重连失败后的会话丢失
                raise ConnectionError("link lost mid-import")
            orig_write(cmd)

        sess.write = _boom
        ok = await d.configure({"state_file": "a.scpi"})
        assert ok is False
        assert "link lost mid-import" in (d._last_error or "")
        assert "NoneType" not in (d._last_error or "")

    @pytest.mark.asyncio
    async def test_status_check_happens_after_import_write(self):
        """复核必须发生在 IMPort 之后（不查 STATus? 的变异 M1 在这红）。"""
        d, sess = _mk_5g(dict(_CLEAN_REPLIES))
        await d.configure({"state_file": "a.scpi"})
        idx_import = sess.ops.index('SYSTem:SCPI:IMPort "a.scpi"')
        idx_status = sess.ops.index("SYSTem:SCPI:IMPort:STATus?")
        idx_err = sess.ops.index("SYSTem:ERRor?")
        assert idx_import < idx_status, "STATus? 复核必须在 IMPort 之后"
        assert idx_import < idx_err, "错误队列读取必须在 IMPort 之后"


# ── 门 2：STATus? 判法 fail-closed ─────────────────────────────────────────

class TestImportStatusVerdict:
    @pytest.mark.asyncio
    async def test_status_failure_returns_false(self):
        d, _ = _mk_5g({**_CLEAN_REPLIES, "SYSTem:SCPI:IMPort:STATus?": "0"})
        assert await d.load_state_file("f.scpi") is False

    @pytest.mark.asyncio
    async def test_status_off_token_returns_false(self):
        d, _ = _mk_5g({**_CLEAN_REPLIES, "SYSTem:SCPI:IMPort:STATus?": "OFF"})
        assert await d.load_state_file("f.scpi") is False

    @pytest.mark.asyncio
    async def test_status_unparseable_is_failure_not_success(self):
        """解析不出（枚举外 / 空串）按失败处理 —— 变异 M4 在这红。"""
        for raw in ("GARBAGE", "", "2"):
            d, _ = _mk_5g(
                {**_CLEAN_REPLIES, "SYSTem:SCPI:IMPort:STATus?": raw}
            )
            assert await d.load_state_file("f.scpi") is False, (
                f"STATus? 回 {raw!r} 不许判成功"
            )

    @pytest.mark.asyncio
    async def test_status_on_token_is_success(self):
        d, _ = _mk_5g({**_CLEAN_REPLIES, "SYSTem:SCPI:IMPort:STATus?": "ON"})
        assert await d.load_state_file("f.scpi") is True

    @pytest.mark.asyncio
    async def test_status_ok_but_error_queue_dirty_returns_false(self):
        """STATus? 成功但错误队列有错 → 半生效不报 applied（False）。"""
        d, _ = _mk_5g({
            **_CLEAN_REPLIES,
            "SYSTem:ERRor?": '-113,"Undefined header"',
        })
        assert await d.load_state_file("f.scpi") is False


# ── 门 3：路径注入 fail-loud，零 SCPI ─────────────────────────────────────

class TestPathInjectionRejected:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", [
        'a".scpi',          # 双引号 — 会截断 SCPI 字符串参数
        "a\nb.scpi",        # 换行 — 会被当第二条命令
        "a\rb.scpi",        # 回车
        "   ",              # 全空白 — 无意义路径 (P1-65 同判法)
    ])
    async def test_load_rejects_locally_zero_scpi(self, bad):
        d, sess = _mk_5g(dict(_CLEAN_REPLIES))
        assert await d.load_state_file(bad) is False
        assert sess.all_scpi == [], f"注入路径 {bad!r} 竟发出了 SCPI"

    @pytest.mark.asyncio
    async def test_configure_path_also_rejected(self):
        d, sess = _mk_5g(dict(_CLEAN_REPLIES))
        assert await d.configure({"state_file": 'x"\ny.scpi'}) is False
        assert sess.all_scpi == []

    @pytest.mark.asyncio
    async def test_save_rejects_injection_zero_scpi(self):
        d, sess = _mk_5g(dict(_CLEAN_REPLIES))
        assert await d.save_state_file('a".scpi') is False
        assert sess.all_scpi == []


# ── 门 4：IRAT profile 三字段 None → 如实拒绝，零 SCPI ────────────────────

class TestIratHonestRefusal:
    @pytest.mark.asyncio
    async def test_irat_load_refused_zero_scpi(self):
        d, sess = _mk_irat(dict(_CLEAN_REPLIES))
        assert await d.load_state_file("f.scpi") is False
        assert sess.all_scpi == []

    @pytest.mark.asyncio
    async def test_irat_configure_state_file_refused_zero_scpi(self):
        d, sess = _mk_irat(dict(_CLEAN_REPLIES))
        assert await d.configure({"state_file": "f.scpi"}) is False
        assert sess.all_scpi == []

    @pytest.mark.asyncio
    async def test_irat_save_refused_zero_scpi(self):
        d, sess = _mk_irat(dict(_CLEAN_REPLIES))
        assert await d.save_state_file("f.scpi") is False
        assert sess.all_scpi == []

    def test_irat_profile_state_fields_stay_none(self):
        """禁令（uxm_command_profiles.py:497）：其他 profile 保持 None，
        不按相似方言猜命令。"""
        assert UxmLteNrIratProfile.STATE_LOAD is None
        assert UxmLteNrIratProfile.STATE_SAVE is None
        assert UxmLteNrIratProfile.STATE_LIST is None


# ── 门 5：list_state_files 零 SCPI、返回 [] ───────────────────────────────

class TestListStateFilesNoFabricatedCatalog:
    @pytest.mark.asyncio
    async def test_5g_list_zero_scpi_empty(self):
        d, sess = _mk_5g(dict(_CLEAN_REPLIES))
        assert await d.list_state_files() == []
        assert sess.all_scpi == []

    @pytest.mark.asyncio
    async def test_irat_list_zero_scpi_empty(self):
        d, sess = _mk_irat(dict(_CLEAN_REPLIES))
        assert await d.list_state_files() == []
        assert sess.all_scpi == []

    def test_5g_profile_state_list_is_none(self):
        """手册无文件列表命令（MMEMory:CATalog? 查无）—— 字段保持 None。"""
        assert Uxm5GNRTestAppProfile.STATE_LIST is None


# ── 门 6：save_state_file 走手册 EXPort ───────────────────────────────────

class TestSaveStateFileManualTruth:
    @pytest.mark.asyncio
    async def test_save_sends_export_not_fabricated(self):
        d, sess = _mk_5g(dict(_CLEAN_REPLIES))
        ok = await d.save_state_file("cfg.scpi")
        assert ok is True
        assert 'SYSTem:SCPI:EXPort "cfg.scpi"' in sess.written
        # 写后读了错误队列
        assert "SYSTem:ERRor?" in sess.queried
        _assert_no_fabricated(sess)

    @pytest.mark.asyncio
    async def test_save_error_queue_dirty_returns_false(self):
        d, _ = _mk_5g({
            **_CLEAN_REPLIES,
            "SYSTem:ERRor?": '-113,"Undefined header"',
        })
        assert await d.save_state_file("cfg.scpi") is False


# ── profile 字段本身（存在性粗筛，行为门在上面） ──────────────────────────

def test_5g_profile_state_commands_are_manual_verbatim():
    assert Uxm5GNRTestAppProfile.STATE_LOAD == 'SYSTem:SCPI:IMPort "{filepath}"'
    assert Uxm5GNRTestAppProfile.STATE_SAVE == 'SYSTem:SCPI:EXPort "{filepath}"'
