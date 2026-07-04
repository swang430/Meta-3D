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
    """mock 驱动 (raw transport 路径): responses 是 readline 依次返回的 bytes。
    P2-9 现场收口后默认 transport=vxi11, raw 协议层用例显式钉 raw。"""
    drv = EtslSwitchDriver("emcenter-test", {"transport": "raw", **(config or {})})
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

    def test_default_port_is_scpi_standard_5025(self):
        # 端口默认 = SCPI 行业标准 raw-socket 端口 5025 (官方手册不写 LAN 端口, 5025 有标准依据)
        drv = EtslSwitchDriver("t", {})
        assert drv._port == 5025
        assert EtslSwitchDriver._DEFAULT_PORT == 5025


class _FakeVisaSession:
    """fake pyvisa session: 记录 write/query, query 响应带实录 \\n\\x00 尾。"""

    def __init__(self, query_responses=None):
        self.written: list[str] = []
        self.queried: list[str] = []
        self._responses = list(query_responses or [])
        self.write_termination = None
        self.timeout = None

    def write(self, body):
        self.written.append(body)

    def query(self, body):
        self.queried.append(body)
        return (self._responses.pop(0) if self._responses else "0") + "\n\x00"

    def close(self):
        pass


def _make_vxi11_driver(config=None, query_responses=None):
    drv = EtslSwitchDriver("emcenter-vxi", config or {})
    drv._visa_session = _FakeVisaSession(query_responses)
    return drv, drv._visa_session


class TestVxi11Transport:
    """P2-9 现场收口 (2026-07-03): 老固件 2.5.1 LAN 只有 VXI-11 —— 裸命令 + CR
    经 pyvisa TCPIP0::ip::inst0::INSTR 全通实证; 响应尾 \\n\\x00 清洗。"""

    def test_default_transport_is_vxi11(self):
        # 默认 = 现场唯一实证形态 (raw 5025 仅新固件; P0-8 哲学: 默认即可用)
        assert EtslSwitchDriver("t", {})._transport == "vxi11"
        assert EtslSwitchDriver("t", {"transport": "raw"})._transport == "raw"

    async def test_connect_opens_inst0_resource(self, monkeypatch):
        import pyvisa as _pv
        opened: list[str] = []
        session = _FakeVisaSession(query_responses=["0"])  # INTLK? -> 0

        rm = MagicMock()
        rm.open_resource = MagicMock(side_effect=lambda r, **kw: (opened.append(r), session)[1])
        monkeypatch.setattr(_pv, "ResourceManager", MagicMock(return_value=rm))

        drv = EtslSwitchDriver("emcenter-vxi", {"ip_address": "192.168.0.50"})
        assert await drv.connect() is True
        assert opened == ["TCPIP0::192.168.0.50::inst0::INSTR"]
        assert session.write_termination == CR  # 裸命令 + CR (终止符交 pyvisa)

    def test_hal_standard_ip_key_accepted(self):
        """Codex #202 R9 P2: HAL 标准路径注入 config['ip'] (=controller_ip,
        与 F64/UXM 同惯例) — 只认 ip_address 会让标准绑定落 127.0.0.1,
        VXI-11 永远连不上真开关。"""
        assert EtslSwitchDriver("t", {"ip": "10.0.1.60"})._ip == "10.0.1.60"

    def test_ip_beats_ip_address_when_both(self):
        """两键并存时 'ip' (binding 结构化列, 权威) 赢 ip_address (兼容遗留)。"""
        drv = EtslSwitchDriver(
            "t", {"ip": "10.0.1.60", "ip_address": "192.168.0.50"}
        )
        assert drv._ip == "10.0.1.60"

    def test_none_ip_falls_through_to_ip_address(self):
        """HAL 注入 ip=None (binding 无 controller_ip) 不遮蔽 ip_address。"""
        drv = EtslSwitchDriver(
            "t", {"ip": None, "ip_address": "192.168.0.50"}
        )
        assert drv._ip == "192.168.0.50"

    async def test_query_strips_trailing_nul(self):
        drv, sess = _make_vxi11_driver(query_responses=["NO"])
        assert await drv.get_path("4:INT_RELAY_A") == 1  # "NO\n\x00" -> "NO" -> 1
        assert sess.queried == ["4:INT_RELAY_A?"]  # 裸命令体, 无终止符 (pyvisa 加)

    async def test_switch_path_writes_without_terminator(self):
        drv, sess = _make_vxi11_driver()
        assert await drv.switch_path("5:INT_RELAY_A", 0, 3) is True
        assert sess.written == ["5:INT_RELAY_A_3"]
        assert sess.queried == []  # 写命令不 query

    async def test_interlock_error3_does_not_block_connect(self, monkeypatch):
        """现场实录 INTLK? 回 'ERROR 3' (interlock 未接线) — 不等于 '1', 放行。"""
        import pyvisa as _pv
        session = _FakeVisaSession(query_responses=["ERROR 3"])
        rm = MagicMock()
        rm.open_resource = MagicMock(return_value=session)
        monkeypatch.setattr(_pv, "ResourceManager", MagicMock(return_value=rm))
        drv = EtslSwitchDriver("emcenter-vxi", {"ip_address": "192.168.0.50"})
        assert await drv.connect() is True
