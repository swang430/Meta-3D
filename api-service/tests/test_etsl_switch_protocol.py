"""P2-9: EtslSwitchDriver EMCenter SCPI 协议层测试.

对照权威文档 (EMCenter SCPI Commands and Error Codes, Part #1801188 Rev A, 2025-08):
命令是裸 <slot>:<cmd> + CR 终止, **无** Write/Query 前缀 (旧实现误读文档表格的 Write/Query
动作标签, 极可能是 2026-05-27 现场 raw socket 无响应真因)。command_style / line_terminator
是现场逃生开关 (raw/CR 无响应时不改代码切回旧行为, 同 P0-8 哲学)。
设计见 docs/site-debug/2026-06-04-emcenter-switch-protocol.md。mock asyncio streams, 不需硬件。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.hal.rf_switch import EtslSwitchDriver

CR = chr(13)   # 0x0D 权威文档终止符
LF = chr(10)   # 0x0A 旧实现误用的终止符


def _cmd(text, term=CR):
    """期望写出的命令字节 (默认 CR 终止)。"""
    return (text + term).encode("ascii")


def _resp(text):
    """模拟设备回包 (带 CRLF, readline 读到)。"""
    return (text + CR + LF).encode("ascii")


def _make_driver(config=None, responses=None):
    """mock 驱动: responses 是 readline 依次返回的 bytes (查询响应)。"""
    drv = EtslSwitchDriver("emcenter-test", config or {})
    writer = MagicMock()
    writer.write = MagicMock()
    writer.drain = AsyncMock()
    resp_q = list(responses or [])

    async def _readline():
        return resp_q.pop(0) if resp_q else _resp("")

    reader = MagicMock()
    reader.readline = _readline
    drv._reader = reader
    drv._writer = writer
    return drv, writer


def _written(writer):
    return [c.args[0] for c in writer.write.call_args_list]


class TestRawCommandFraming:
    """权威文档: 裸 <slot>:<cmd> + CR, 无 Write 前缀 (旧 bug 是无响应真因)。"""

    async def test_sp6t_switch_path_bare_cr(self):
        drv, writer = _make_driver()
        assert await drv.switch_path("1:INT_RELAY_A", 0, 4) is True
        assert _written(writer) == [_cmd("1:INT_RELAY_A_4")]

    async def test_spdt_switch_path_no(self):
        drv, writer = _make_driver()
        await drv.switch_path("4:INT_RELAY_B", 0, "NO")
        assert _written(writer) == [_cmd("4:INT_RELAY_B_NO")]

    async def test_no_legacy_write_prefix_or_lf(self):
        # 回归旧 bug: "Write 1:INT_RELAY_A_4" + LF -> EMCenter 不解析 (无响应)
        drv, writer = _make_driver()
        await drv.switch_path("1:INT_RELAY_A", 0, 4)
        sent = _written(writer)[0]
        assert not sent.startswith(b"Write ")
        assert sent.endswith(CR.encode())
        assert not sent.endswith(LF.encode())


class TestResponseParsing:
    async def test_get_path_sp6t_numeric(self):
        drv, _ = _make_driver(responses=[_resp("3")])
        assert await drv.get_path("1:INT_RELAY_A") == 3

    async def test_get_path_spdt_nc_is_zero(self):
        drv, _ = _make_driver(responses=[_resp("NC")])
        assert await drv.get_path("4:INT_RELAY_B") == 0

    async def test_get_path_spdt_no_is_one(self):
        drv, _ = _make_driver(responses=[_resp("NO")])
        assert await drv.get_path("4:INT_RELAY_B") == 1

    async def test_get_path_query_is_bare(self):
        drv, writer = _make_driver(responses=[_resp("3")])
        await drv.get_path("1:INT_RELAY_A")
        assert _written(writer) == [_cmd("1:INT_RELAY_A?")]

    async def test_parse_tolerates_legacy_read_prefix(self):
        # verbose / 旧固件可能回 "Read 3" -> 容错剥掉
        drv, _ = _make_driver(responses=[_resp("Read 3")])
        assert await drv.get_path("1:INT_RELAY_A") == 3


class TestFieldEscapeHatches:
    """现场逃生: raw/CR 无响应时可经 config 切回旧行为, 不改代码 (P0-8 哲学)。"""

    async def test_verbose_wraps_write(self):
        drv, writer = _make_driver(config={"command_style": "verbose"})
        await drv.switch_path("1:INT_RELAY_A", 0, 4)
        assert _written(writer) == [_cmd("Write 1:INT_RELAY_A_4")]

    async def test_verbose_wraps_query(self):
        drv, writer = _make_driver(
            config={"command_style": "verbose"}, responses=[_resp("3")]
        )
        await drv.get_path("1:INT_RELAY_A")
        assert _written(writer) == [_cmd("Query 1:INT_RELAY_A?")]

    async def test_verbose_mid_string_query_wrapped_as_query(self):
        # Codex P2 #130: "?" 在中间的查询 (INTLK? SAFETYRELAY) verbose 下也应包 Query
        # (跟 _send_command 读响应判定一致), 否则包成 Write 却又等响应 -> 挂死
        drv, writer = _make_driver(
            config={"command_style": "verbose"}, responses=[_resp("0")]
        )
        assert await drv._send_command("INTLK? SAFETYRELAY") == "0"
        assert _written(writer) == [_cmd("Query INTLK? SAFETYRELAY")]

    async def test_terminator_lf(self):
        drv, writer = _make_driver(config={"line_terminator": "lf"})
        await drv.switch_path("1:INT_RELAY_A", 0, 4)
        assert _written(writer) == [_cmd("1:INT_RELAY_A_4", LF)]

    async def test_terminator_crlf(self):
        drv, writer = _make_driver(config={"line_terminator": "crlf"})
        await drv.switch_path("1:INT_RELAY_A", 0, 4)
        assert _written(writer) == [_cmd("1:INT_RELAY_A_4", CR + LF)]

    def test_defaults_are_raw_and_cr(self):
        drv = EtslSwitchDriver("t", {})
        assert drv._command_style == "raw"
        assert drv._line_terminator == CR


class TestResetPaths:
    async def test_spdt_reset_to_nc(self):
        drv, writer = _make_driver()
        drv._mappings = {"path1": {"switch_id": "4:INT_RELAY_B"}}
        assert await drv.reset_paths() is True
        assert _written(writer) == [_cmd("4:INT_RELAY_B_NC")]

    async def test_ext_relay_reset_to_zero(self):
        drv, writer = _make_driver()
        drv._mappings = {"p": {"switch_id": "EXT_RELAY_A"}}
        await drv.reset_paths()
        assert _written(writer) == [_cmd("EXT_RELAY_A_0")]

    async def test_sp6t_reset_skipped_no_illegal_nc(self):
        # SP6T 复位语义未确认 -> 跳过, 不发非法 _NC (现场确认后再实现)
        drv, writer = _make_driver()
        drv._mappings = {"p": {"switch_id": "5:INT_RELAY_A", "relay_type": "sp6t"}}
        assert await drv.reset_paths() is True
        assert _written(writer) == []


class TestPortConfig:
    def test_port_from_config(self):
        assert EtslSwitchDriver("t", {"port": 9221})._port == 9221

    def test_default_port_is_unverified_placeholder(self):
        assert (
            EtslSwitchDriver("t", {})._port
            == EtslSwitchDriver._DEFAULT_PORT_UNVERIFIED
        )
