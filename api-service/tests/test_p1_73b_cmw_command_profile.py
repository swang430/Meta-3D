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
        "route_nx2_query",
        "route_query",
        "ebler_absolute_query",
        "ebler_relative_query",
        "ebler_init",
        "ebler_stop",
        "ebler_abort",
        "ebler_state_query",
        "ebler_timeout",
        "ebler_repetition",
        "ebler_stop_condition",
        # P1-74：Extended BLER 统计基（每 measurement cycle 的子帧数）
        "ebler_subframes",
        "ebler_subframes_query",
        # P2-51: LTE MAC/调度配置（取证清单
        # docs/plans/2026-08-30-p2-51-cmw500-mac-scheduling-evidence.md）
        "mac_sched_type",
        "mac_sched_type_query",
        "mac_rmc_dl",
        "mac_rmc_dl_query",
        "mac_rmc_ul",
        "mac_rmc_ul_query",
        "mac_rmc_rbpos_dl",
        "mac_rmc_rbpos_dl_query",
        "mac_rmc_rbpos_ul",
        "mac_rmc_rbpos_ul_query",
        # P2-56 ②：LTE TDD 正式路径（ULDL / SSUBframe / 歧义 RMC 的版本）
        "mac_cell_uldl",
        "mac_cell_uldl_query",
        "mac_cell_ssubframe",
        "mac_cell_ssubframe_query",
        "mac_rmc_version_dl",
        "mac_rmc_version_dl_query",
        "mac_dl_stream_coupling",
        "mac_dl_stream_coupling_query",
        "mac_dl_padding",
        "mac_dl_padding_query",
        "mac_ul_multicluster_query",
        "mac_harq_dl_enable_query",
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
    assert Cmw500LteCommandProfile.route_nx2_query(1) == (
        "ROUTe:LTE:SIGN1:SCENario:TRO:FLEXible?"
    )


def test_nx2_route_query_parses_all_seven_instrument_returned_parameters():
    assert Cmw500LteCommandProfile.parse_route_nx2_readback(
        "SUA1,RF1C,RX1,RF1O,TX1,RF2C,TX2"
    ) == CmwNx2Route(
        pcc_bb_board="SUA1",
        rx_connector="RF1C",
        rx_converter="RX1",
        tx1_connector="RF1O",
        tx1_converter="TX1",
        tx2_connector="RF2C",
        tx2_converter="TX2",
    )


@pytest.mark.parametrize(
    "response",
    (
        "SUA1,RF1C,RX1,RF1O,TX1,RF2C",
        "NAV,RF1C,RX1,RF1O,TX1,RF2C,TX2",
        "SUA1,RF1C,RX1,,TX1,RF2C,TX2",
        "SUA1,RF1C,RX1,RF1O;*RST,TX1,RF2C,TX2",
    ),
)
def test_nx2_route_query_rejects_incomplete_or_untrusted_parameters(response):
    with pytest.raises(ValueError):
        Cmw500LteCommandProfile.parse_route_nx2_readback(response)


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
    assert Cmw500LteCommandProfile.ebler_timeout_disabled(2) == (
        "CONFigure:LTE:SIGN2:EBLer:TOUT 0"
    )
    assert Cmw500LteCommandProfile.ebler_repetition_continuous(2) == (
        "CONFigure:LTE:SIGN2:EBLer:REPetition CONTinuous"
    )
    assert Cmw500LteCommandProfile.ebler_stop_condition_none(2) == (
        "CONFigure:LTE:SIGN2:EBLer:SCONdition NONE"
    )
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
