"""P1-73B Task 6：CMW500 LTE 命令目录必须可审计且共用同一 builder。"""

from dataclasses import replace

import pytest

from app.hal.cmw500_command_profile import (
    CMW500_LTE_COMMANDS,
    Cmw500LteCommandProfile,
    CmwNx2Route,
)


def test_reachable_cmw_commands_carry_manual_source_and_purpose():
    required = {
        "route_nx2",
        "route_query",
        "ebler_absolute_query",
        "ebler_relative_query",
        "ebler_init",
        "ebler_stop",
        "ebler_abort",
        "ebler_state_query",
    }

    assert required == set(CMW500_LTE_COMMANDS)
    for spec in CMW500_LTE_COMMANDS.values():
        assert "1173.9628.02-41" in spec.source_reference
        assert "printed p." in spec.source_reference
        assert spec.purpose


def test_nx2_route_builder_preserves_all_seven_manual_parameters():
    route = CmwNx2Route(
        pcc_bb_board="BB1",
        rx_connector="RF1C",
        rx_converter="RX1",
        tx1_connector="RF1C",
        tx1_converter="TX1",
        tx2_connector="RF2C",
        tx2_converter="TX2",
    )

    assert Cmw500LteCommandProfile.build_route_nx2(1, route) == (
        "ROUTe:LTE:SIGN1:SCENario:TRO:FLEXible "
        "BB1,RF1C,RX1,RF1C,TX1,RF2C,TX2"
    )
    assert Cmw500LteCommandProfile.route_query(1) == "ROUTe:LTE:SIGN1?"


@pytest.mark.parametrize(
    "field_name",
    (
        "pcc_bb_board",
        "rx_connector",
        "rx_converter",
        "tx1_connector",
        "tx1_converter",
        "tx2_connector",
        "tx2_converter",
    ),
)
def test_nx2_route_builder_rejects_scpi_program_separator_in_every_token(field_name):
    route = CmwNx2Route(
        pcc_bb_board="BB1",
        rx_connector="RF1C",
        rx_converter="RX1",
        tx1_connector="RF1C",
        tx1_converter="TX1",
        tx2_connector="RF2C",
        tx2_converter="TX2",
    )

    with pytest.raises(ValueError, match="route token"):
        Cmw500LteCommandProfile.build_route_nx2(
            1,
            replace(route, **{field_name: "RF1C;*RST"}),
        )


def test_extended_bler_builders_share_the_catalog_templates():
    assert Cmw500LteCommandProfile.ebler_absolute_query(2) == (
        "FETCh:LTE:SIGN2:EBLer:PCC:ABSolute?"
    )
    assert Cmw500LteCommandProfile.ebler_relative_query(2) == (
        "FETCh:LTE:SIGN2:EBLer:PCC:RELative?"
    )
    assert Cmw500LteCommandProfile.ebler_init(2) == "INITiate:LTE:SIGN2:EBLer"
    assert Cmw500LteCommandProfile.ebler_stop(2) == "STOP:LTE:SIGN2:EBLer"
    assert Cmw500LteCommandProfile.ebler_abort(2) == "ABORt:LTE:SIGN2:EBLer"
    assert Cmw500LteCommandProfile.ebler_state_query(2) == (
        "FETCh:LTE:SIGN2:EBLer:STATe?"
    )
