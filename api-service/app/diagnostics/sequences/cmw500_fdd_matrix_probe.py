"""CMW FDD closed-cell matrix samples; diagnostic evidence, never qualification.

Manual: R&S 1173.9628.02-41, Table 2-32 pp.65-66 (TM/TX/DCI),
Tables 2-37/2-38 pp.77-78 (DL), Table 2-33 pp.70-71 (UL).
No claim of throughput, attach, or validated hardware capability is made here.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict
from functools import partial

from app.diagnostics.protocol import SequenceMetadata, SequenceRunResult, SequenceStepResult
from app.hal.cmw500_base_station import CmwScpiCommands, RealCmw500Driver
from app.hal.cmw500_command_profile import (
    CMW500_LTE_FULL_RB_RMC_BY_BANDWIDTH, Cmw500LteCommandProfile as Commands,
    CmwRmcSelection, cmw500_lte_formal_options,
)
from app.hal.scpi_evidence import capture_scpi_exchanges
from app.services.base_station_binding import ResolvedBaseStationBinding
from app.services.instrument_hal_service import is_mock_driver
from app.services.instrument_test_lease import await_completion_despite_cancellation


metadata = SequenceMetadata(
    name="CMW500 FDD 矩阵抽样（关闭小区）",
    description=("仅 FDD/20MHz/1CC-nx2：tm1_one 或 tm3_two。会关闭小区并保留目标配置；"
                 "不启射频、不 Attach、不测吞吐、不授予正式资格。"),
    required_categories=["baseStation"],
    params_schema=[{"name": "sample", "label": "样本（tm1_one / tm3_two）",
                    "type": "string", "default": "tm1_one"}],
    safe_during_test=False,
)


class ProbeCancelled(asyncio.CancelledError):
    """Carry partial audit through the API's existing cancellation persistence."""
    def __init__(self, result: SequenceRunResult):
        super().__init__(result.summary)
        self.result = result


class ProbePreflightRejected(Exception):
    """Read-only preflight result; no control lease was acquired or released."""
    def __init__(self, result: SequenceRunResult):
        super().__init__(result.summary)
        self.result = result


def validate_params(params: dict) -> str:
    if set(params) != {"sample"} or params["sample"] not in ("tm1_one", "tm3_two"):
        raise ValueError("仅接受 sample=tm1_one 或 tm3_two；不接受自由组合或额外参数")
    return params["sample"]


def _token(raw: str, allowed: tuple[str, ...]) -> str:
    value = raw.strip().upper()
    if value not in allowed:
        raise ValueError(f"未知回读 {raw!r}，允许 {allowed}")
    return value


async def run(ctx, hal, params, *, log, resolved_binding=None, preflight_only=False):
    steps = []
    extra = {"formal_eligible": False, "classification": "diagnostic_only",
             "cleanup": {"safe_idle": None, "required": False}}
    success = False
    summary = "未执行"
    driver = hal.drivers.get("baseStation")
    touched = False
    cancelled = None

    def record(label, ok, detail, raw=None):
        steps.append(SequenceStepResult(label, ok, detail=detail, raw=raw))
        log(f"{label}: {detail}")

    def read(label, query, parser=lambda raw: raw.strip()):
        raw = driver._query(query)
        try:
            # Consume the device's failure channel before parsing can abort.
            # ERR reads are the terminal case, not recursively drained.
            if query != CmwScpiCommands.ERR:
                clean(f"{label} query errors")
            value = parser(raw)
        except Exception as exc:
            record(label, False, f"{query}: {exc}", raw)
            raise
        record(label, True, query, raw)
        return value

    def clean(label):
        raw = read(label, CmwScpiCommands.ERR)
        if not driver._error_queue_is_empty(raw):
            raise ValueError(f"{label}: 错误队列非空或无法解析: {raw!r}")

    # Capture includes failed requests and SAFE_IDLE, not only successful reads.
    with capture_scpi_exchanges() as exchanges:
        try:
            sample = validate_params(params)
            extra["sample"] = sample
            extra["simulated"] = is_mock_driver(driver)
            if extra["simulated"] or type(driver) is not RealCmw500Driver:
                raise ValueError("此现场抽样只接受已绑定的真实 CMW500；Mock 不生成现场证据")
            if not isinstance(resolved_binding, ResolvedBaseStationBinding):
                raise ValueError("缺少租约内服务器 binding 快照")
            binding = resolved_binding
            if (binding.execution_mode != "real" or binding.status != "configured"
                    or binding.manifest.adapter_id != "cmw500"
                    or binding.runtime_driver.instrument_id != driver.instrument_id):
                raise ValueError("冻结 binding 与当前租约 CMW 不一致")
            extra["binding"] = binding.model_dump(mode="json")
            identity = driver.get_base_station_identity()
            extra["identity"] = asdict(identity)
            if not driver.identity_snapshot_verified or identity.model != "CMW":
                raise ValueError("CMW 身份/固件/选件未完成权威查询")
            # route_nx2_query pp.630-631 is the newest command used (V3.5.40).
            if not driver._firmware_at_least(identity.firmware_version, "V3.5.40"):
                raise ValueError("矩阵抽样要求固件至少 V3.5.40")
            options = {x.upper().removeprefix("CMW-") for x in identity.options}
            if not cmw500_lte_formal_options("fdd").issubset(options):
                raise ValueError("FDD nx2 抽样需要 KS500 与 KS520（包括 TM1 SIMO）")
            i = driver._sign_channel

            def preconditions():
                if read("duplex", driver._fmt(CmwScpiCommands.CELL_DUPLEX) + "?") != "FDD":
                    raise ValueError("仅接受已配置 FDD")
                if read("bandwidth", driver._fmt(CmwScpiCommands.CELL_DL_BW) + "?") != "B200":
                    raise ValueError("仅接受已配置 B200/20MHz")
                route = read("scenario", Commands.route_query(i), Commands.parse_route_readback)
                exact = read("route", Commands.route_nx2_query(i), Commands.parse_route_nx2_readback)
                expected = binding.profile.lte_2x2_internal_route.model_dump()
                if asdict(exact) != expected or any(
                    getattr(route, field) != value for field, value in expected.items()
                    if field != "pcc_bb_board"
                ):
                    raise ValueError("仪器 nx2 route 与冻结七字段配置不一致")
                if read("UL allocation", Commands.mac_ul_multicluster_query(i),
                        Commands.parse_mac_on_off) != "OFF":
                    raise ValueError("UL 必须已配置连续分配（MCLuster OFF）")
                clean("precondition errors")

            clean("existing errors")
            # Existing queries/parsers: Base Software §5.1.2 p.119 (*IDN?),
            # §6.3.10.3 p.242 (usable software/hardware options). Capture on
            # warm sessions too; cache alone is not this run's raw evidence.
            live_model, live_version = read("identity", CmwScpiCommands.IDN,
                                            driver._parse_identity_response)
            live_options = read("software options", CmwScpiCommands.OPTION_LIST_VALID_SOFTWARE,
                                driver._parse_options_response)
            live_options += read("hardware options", CmwScpiCommands.OPTION_LIST_FUNCTIONAL_HARDWARE,
                                 driver._parse_options_response)
            if (live_model != identity.model or live_version != identity.firmware_version
                    or set(live_options) != set(identity.options)):
                raise ValueError("当次身份/选件回读与连接身份快照漂移，请重新连接后诊断")
            preconditions()
            if preflight_only:
                return SequenceRunResult(True, "只读前置核验通过；尚未取得控制租约", steps, extra)
            # Policy, not a vendor claim: configure only after confirmed OFF,ADJ.
            touched = True  # ensure_safe_idle itself may write OFF.
            extra["cleanup"]["required"] = True
            if await driver.ensure_safe_idle() is not True:
                raise ValueError("配置前 SAFE_IDLE 未确认")
            clean("SAFE_IDLE errors")
            dual = sample == "tm3_two"
            dl = (CMW500_LTE_FULL_RB_RMC_BY_BANDWIDTH["B200"].downlink if dual
                  else CmwRmcSelection("N100", "QPSK", "T5"))  # Table 2-37 p.77
            ul = CMW500_LTE_FULL_RB_RMC_BY_BANDWIDTH["B200"].uplink
            tm = "TM3" if dual else "TM1"
            antennas = "TWO" if dual else "ONE"
            dci = "D2A" if dual else "D1A"
            tm_header = driver._fmt(CmwScpiCommands.TRANSMISSION_MODE)
            ant_header = driver._fmt(CmwScpiCommands.MIMO_MODE)
            # pp.752-753 enum readback whitelist; no assumed auto-coupling.
            settings = [
                ("TM", tm_header + "?", f"{tm_header} {tm}", tm,
                 partial(_token, allowed=("TM1", "TM2", "TM3", "TM4", "TM6", "TM7", "TM8", "TM9"))),
                ("TX", ant_header + "?", f"{ant_header} {antennas}", antennas,
                 partial(_token, allowed=("ONE", "TWO", "FOUR"))),
                ("DCI", Commands.mac_dci_query(i), Commands.build_mac_dci(i, dci), dci,
                 partial(_token, allowed=("D1", "D1A", "D1B", "D2", "D2A", "D2B", "D2C", "D61"))),
                ("scheduling", Commands.mac_scheduling_type_query(i),
                 Commands.mac_scheduling_type_rmc(i), "RMC", Commands.parse_mac_scheduling_type),
            ]
            if dual:
                settings.append(("DLEQual", Commands.mac_dl_stream_coupling_query(i),
                                 Commands.mac_dl_stream_coupling_on(i), "ON", Commands.parse_mac_on_off))
            for stream in ((1, 2) if dual else (1,)):
                settings.extend([
                    (f"DL{stream}", Commands.mac_rmc_dl_query(i, stream),
                     Commands.build_mac_rmc_dl(i, stream, dl), dl,
                     partial(Commands.parse_mac_rmc_readback, direction="dl")),
                    (f"DL{stream} RB", Commands.mac_rbposition_dl_query(i, stream),
                     Commands.mac_rbposition_dl_low(i, stream), "LOW",
                     partial(Commands.parse_mac_rb_position, direction="dl")),
                ])
            settings.extend([
                ("UL", Commands.mac_rmc_ul_query(i), Commands.build_mac_rmc_ul(i, ul), ul,
                 partial(Commands.parse_mac_rmc_readback, direction="ul")),
                ("UL RB", Commands.mac_rbposition_ul_query(i), Commands.mac_rbposition_ul_low(i), "LOW",
                 partial(Commands.parse_mac_rb_position, direction="ul")),
            ])
            for label, query, command, target, parser in settings:
                await asyncio.sleep(0)  # cancellation boundary between synchronous exchanges
                current = read(f"{label} before", query, parser)
                clean(f"{label} read errors")
                if current != target:
                    driver._write(command)
                    if read(f"{label} OPC", CmwScpiCommands.OPC) != "1":
                        raise ValueError(f"{label}: OPC 未完成")
                    clean(f"{label} write errors")
                if read(f"{label} after", query, parser) != target:
                    raise ValueError(f"{label}: 写后回读不匹配")
                clean(f"{label} verification errors")
            for label, query, _, target, parser in settings:
                if read(f"{label} final", query, parser) != target:
                    raise ValueError(f"{label}: 最终组合回读漂移")
            preconditions()
            success = True
            summary = f"{sample} 配置抽样通过（仅诊断；未测吞吐、未授予正式资格）"
        except asyncio.CancelledError as exc:
            cancelled = exc
            summary = "矩阵抽样已取消；保留已发生的部分证据"
        except Exception as exc:
            summary = f"矩阵抽样失败: {exc}"
            record("failure", False, str(exc))
        finally:
            if touched:
                cleanup = await await_completion_despite_cancellation(driver.ensure_safe_idle())
                safe = cleanup.value is True and cleanup.error is None
                extra["cleanup"]["safe_idle"] = safe
                record("SAFE_IDLE cleanup", safe, str(cleanup.error or safe))
                if not safe:
                    success = False
                    summary += "；SAFE_IDLE 收尾未确认"
                cancelled = cancelled or cleanup.delayed_cancellation
            extra["exchanges"] = [item.model_dump(mode="json") for item in exchanges]
    if cancelled is not None:
        extra.update(cancelled=True, partial_result_available=True)
        raise ProbeCancelled(SequenceRunResult(False, summary, steps, extra)) from cancelled
    return SequenceRunResult(success, summary, steps, extra)
