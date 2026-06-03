"""Pin: catalog 的 _convert_connection 暴露 InstrumentConnection.id (P2-12 slice 3 A 前置).

前端 SCD 管理 GUI 靠 category.connection.id 拿 instrument_connection_id 调 SCD API
(create/list/associate/delete)。若未来重构 _convert_connection 丢了 id 字段, SCD 管理
UI 会静默拿不到 connection → gate 不渲染, 用户无从建库 —— 这里先 break。
"""
from __future__ import annotations

from uuid import uuid4

from app.api.instrument import _convert_connection
from app.models.instrument import InstrumentConnection


def test_convert_connection_exposes_id():
    cid = uuid4()
    conn = InstrumentConnection(
        id=cid,
        endpoint="TCPIP0::192.168.0.132::inst0::INSTR",
        protocol="VISA/SCPI",
    )
    fe = _convert_connection(conn)
    assert fe.id == str(cid)


def test_convert_connection_none_when_absent():
    # 无 connection 的 category → id None; 前端据此 gate 不渲染 SCD 管理卡片。
    assert _convert_connection(None).id is None
