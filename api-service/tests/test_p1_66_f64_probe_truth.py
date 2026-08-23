"""P1-66：F64 连接路径盲试探针换手册真值 —— 行为门。

故障（P1-65 手册对账查出，roadmap Discovered 2026-08-23 第 1 条）：
驱动每次 connect() 发两条**手册查无**的命令（`SYSTem:CALibration:USER:LIST?` /
`OUTPut:INTERFerence:LIST?`），各留一条 -100 在错误队列（08-07 实测一天 269 次连接）；
且 F64 会把 `-100,"ATE command not supported"` 当响应串回，探针把"有响应"当 ACK →
许可假阳性（08-07 实测驱动自称 ['INT-GEN','USER-ALIGN'] 全来自探针）。

手册依据（Propsim User Reference Rev 10.2，P1-65 设计稿 §2 已按原文核对）：
- §20.4.2.4 `SYSTem:INFO?` 尾部即 licenses（原文 "and licenses"）——干扰源真值源；
- §20.4.2.19 `SYSTem:CALIBration:USER:GET?` 未启用返回空串——用户对齐真值源；
- 两条 LIST? 探针命令手册全文 0 命中（措辞恒为"手册查无"，不说"仪器不支持"）。

门的形态：走**真实 connect() 代码路径**（patch pyvisa.ResourceManager，脚本化 VISA
resource，同 test_f64_local_control_lifecycle 的形态）——不是只查源码文本。
"""
from __future__ import annotations

from typing import Dict
from unittest.mock import patch

import pytest

from app.hal.capabilities import CE_INTERFERENCE_GENERATOR, CE_USER_ALIGNMENT
from app.hal.propsim_f64 import RealPropsimF64Driver

IDN = "Keysight Technologies,F8800A,FI1234567,8.0"
# 现场 2026-08 实测形态：SYST:INFO? 文本含 "AWGN interferences:32"
SYS_INFO_WITH_INT = (
    "PROPSIM F64,64,RF,v1.0,16,Band: 450MHz - 3000MHz,"
    "Main license,AWGN interferences:32,Shadowing"
)
SYS_INFO_NO_LICENSE = "PROPSIM F64,64,RF,v1.0,16,Band: 450MHz - 3000MHz"

_ERR_PAYLOAD = '-100,"ATE command not supported"'


def _forbidden_hits(commands) -> list:
    """两条手册查无命令的命中（大小写/缩写鲁棒：按 USER:LIST / INTERFERENCE…LIST 判）。"""
    hits = []
    for cmd in commands:
        u = cmd.upper()
        if "USER:LIST" in u or ("INTERF" in u and "LIST" in u):
            hits.append(cmd)
    return hits


class _ScriptedVisaResource:
    """脚本化 VISA resource：记录全部 write/query，按表回复。

    未脚本化的查询按 F64 真实行为回 `-100,"ATE command not supported"`
    （不是抛异常）——这正是探针假阳性形态的来源，门要在这个形态下仍然守住。
    """

    def __init__(self, replies: Dict[str, str]):
        self._replies = dict(replies)
        self.commands: list = []
        self.timeout = 5000
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def write(self, cmd: str) -> None:
        self.commands.append(cmd)

    def read(self) -> str:  # 排水路径兜底，不该被走到
        raise TimeoutError("no stale reply")

    def query(self, cmd: str) -> str:
        self.commands.append(cmd)
        if cmd == "SYST:ERR?":
            return '0,"No error"'
        if cmd in self._replies:
            return self._replies[cmd]
        return _ERR_PAYLOAD


class _ScriptedRM:
    def __init__(self, resource: _ScriptedVisaResource):
        self.resource = resource

    def open_resource(self, *_args, **_kwargs):
        return self.resource


async def _connect(replies: Dict[str, str], config: dict | None = None):
    """跑真实 connect() 全流程，返回 (driver, resource)。"""
    resource = _ScriptedVisaResource(replies)
    driver = RealPropsimF64Driver(
        "f64-p1-66", {"ip": "192.0.2.10", **(config or {})}
    )
    with patch("pyvisa.ResourceManager", return_value=_ScriptedRM(resource)):
        ok = await driver.connect()
    return driver, resource, ok


def _base_replies(**over) -> Dict[str, str]:
    base = {
        "*IDN?": IDN,
        "SYST:INFO?": SYS_INFO_WITH_INT,
        "SYSTem:CALIBration:USER:GET?": "",
    }
    base.update(over)
    return base


# ── 门 1：connect 全流程不发手册查无的两条命令 ──────────────────────────────

class TestConnectSendsNoFabricatedCommands:
    @pytest.mark.asyncio
    async def test_connect_command_set_excludes_manual_absent_probes(self):
        driver, resource, ok = await _connect(_base_replies())
        assert ok is True, f"connect 应成功, last_error={driver._last_error}"
        hits = _forbidden_hits(resource.commands)
        assert hits == [], (
            f"connect 发了手册查无的探针命令: {hits}\n"
            f"全部命令: {resource.commands}"
        )

    @pytest.mark.asyncio
    async def test_connect_no_probes_even_when_syst_info_lacks_keywords(self):
        """无许可关键字时也不许退回盲试探针（探针机制应整体不存在）。"""
        driver, resource, ok = await _connect(
            _base_replies(**{"SYST:INFO?": SYS_INFO_NO_LICENSE})
        )
        assert ok is True
        assert _forbidden_hits(resource.commands) == []


# ── 门 2：干扰源真值 = SYST:INFO? 关键字，fail-closed ───────────────────────

class TestInterferenceGeneratorFromSystInfo:
    @pytest.mark.asyncio
    async def test_awgn_interferences_in_syst_info_sets_flag_true(self):
        driver, _, ok = await _connect(_base_replies())
        assert ok is True
        assert driver.has_interference_generator is True
        assert CE_INTERFERENCE_GENERATOR in driver.capabilities
        assert "INT-GEN" in driver._installed_options

    @pytest.mark.asyncio
    async def test_no_keyword_and_no_explicit_config_is_false(self):
        """fail-closed：SYST:INFO? 无关键字且 config 未显式声明 → False。"""
        driver, _, ok = await _connect(
            _base_replies(**{"SYST:INFO?": SYS_INFO_NO_LICENSE})
        )
        assert ok is True
        assert driver.has_interference_generator is False
        assert CE_INTERFERENCE_GENERATOR not in driver.capabilities
        assert driver._installed_options == []

    @pytest.mark.asyncio
    async def test_explicit_config_still_wins(self):
        """config 显式声明通道不受本片影响（爆炸半径兜底）。"""
        driver, _, ok = await _connect(
            _base_replies(**{"SYST:INFO?": SYS_INFO_NO_LICENSE}),
            config={"has_interference_generator": True},
        )
        assert ok is True
        assert driver.has_interference_generator is True


# ── 门 3：用户对齐真值 = USER:GET?，错误 payload 不是值 ─────────────────────

class TestUserAlignmentFromGetQuery:
    @pytest.mark.asyncio
    async def test_empty_reply_means_no_user_alignment(self):
        """§20.4.2.19：未启用返回空串 → 能力不报有。"""
        driver, _, ok = await _connect(_base_replies())
        assert ok is True
        assert driver._active_alignment is None
        assert CE_USER_ALIGNMENT not in driver.capabilities

    @pytest.mark.asyncio
    async def test_name_reply_reports_capability(self):
        """有真值就报真值：GET? 回名字 → 能力报有。"""
        driver, _, ok = await _connect(_base_replies(**{
            "SYSTem:CALIBration:USER:GET?": "CAICT_5G_3500MHz",
            "SYSTem:CALIBration:USER:INFO?": "FI1234567, 29.01.2024",
        }))
        assert ok is True
        assert driver._active_alignment is not None
        assert driver._active_alignment["alignment_name"] == "CAICT_5G_3500MHz"
        assert CE_USER_ALIGNMENT in driver.capabilities

    @pytest.mark.asyncio
    async def test_error_payload_reply_is_not_an_alignment_name(self):
        """F64 会把 -100 payload 当响应串回（驱动内 `_is_unsupported_error_payload`
        即为此存在）——它不能变成 alignment 名 / 能力假阳性。"""
        driver, _, ok = await _connect(_base_replies(**{
            "SYSTem:CALIBration:USER:GET?": _ERR_PAYLOAD,
        }))
        assert ok is True
        assert driver._active_alignment is None, (
            f"错误 payload 被当成了 alignment: {driver._active_alignment}"
        )
        assert CE_USER_ALIGNMENT not in driver.capabilities


# ── 门 4：health 序列探针清单不含 INT_LIST（第三站点） ──────────────────────

class TestHealthSequenceHasNoFabricatedProbe:
    def test_probe_table_excludes_interference_list(self):
        from app.diagnostics.sequences.propsim_f64_health import PROPSIM_SCPI

        cmds = [row[1] for row in PROPSIM_SCPI]
        assert _forbidden_hits(cmds) == [], (
            f"health 探针表仍含手册查无命令: {_forbidden_hits(cmds)}"
        )
        assert all(row[0] != "INT_LIST" for row in PROPSIM_SCPI)
