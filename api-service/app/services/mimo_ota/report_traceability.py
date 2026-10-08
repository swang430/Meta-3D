"""P2-88：同次执行的只读报告审计；不查当前用例，不补历史默认。"""
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict
from typing import Any

from app.schemas.mimo_ota.config import MIMOOTAConfiguration
from app.services.base_station_adapter_profile import FREEZE_CONFIG_KEY
from app.services.execution_evidence_outcome import validate_frozen_compatibility_snapshot

SOURCE_KEY = "report_parameter_sources"
_FIELDS = (
    "azimuths_deg", "settling_time_s", "num_samples_per_azimuth", "target_tx_power_dbm",
    "uxm_dl_power_dbm_per_bw", "f64_crest_db", "f64_output_level_dbm", "f64_output_gain_db", "channel_asset_id",
    "f64_input_ref_dbm", "input_loop_initial_dl_power_dbm", "target_rsrp_dbm", "target_snr_db",
    "f64_bypass_mode", "f64_fade_after_attach", "base_station_config_mode", "mimo_port_preset",
    "attach_power_observation_s", "emulation_file", "asc_source_path", "scd_id", "switch_mode_id",
    "engine_mode", "cdl_model_name", "pass_criteria", "mac_profile",
    "component_carriers", "dut_profile_id", "measurement_duration_s",
    "sample_interval_ms", "theoretical_peak_throughput_mbps",
    "reference_antenna_model", "reference_antenna_gain_dbi", "mimo_layers", "modulation",
)
_CARRIER_FIELDS = {
    "radio_technology", "frequency_hz", "bandwidth_mhz", "subcarrier_spacing_khz",
    "band", "duplex", "lte_dl_earfcn", "nr_arfcn", "role", "carrier_id", "lte_transmission_mode",
}
_MAC_LEGACY = {
    "statistical_window.count": "stat_count",
    "scheduler_algorithm": "sched_algo", "mcs": "mcs",
    "enable_amc": "enable_amc", "tdd_pattern": "tdd_pattern",
    "tdd_period": "tdd_period", "harq_max_trans": "harq_max_trans",
    "harq_processes": "harq_processes", "csi_rs_ports": "csi_rs_ports",
    "mimo_layers": "mimo_layers", "subcarrier_spacing_khz": "subcarrier_spacing_khz",
    "transmission_mode": "lte_transmission_mode", "duplex": "duplex",
    "rmc_version": "lte_rmc_version",
}
_SOURCE_LABELS = {
    "saved_configuration": "本次启动读取的已保存配置（不倒推人工填写）",
    "launch_default": "本次启动补的默认值", "derived": "由本次输入派生",
    "untraceable": "来源不可追溯（历史未记录）",
    "not_configured": "未配置",
}


def _leaves(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {p: v for key, item in value.items()
                for p, v in _leaves(item, f"{prefix}.{key}".strip(".")).items()}
    if isinstance(value, list) and prefix == "component_carriers":
        return {p: v for i, item in enumerate(value)
                for p, v in _leaves(item, f"{prefix}.{i}").items()}
    return {prefix: value}


def capture_report_sources(name: str, configuration: dict) -> dict:
    """只保存字段路径：既不复制密钥，也不把保存输入叫成人工显式输入。"""
    return {"schema_version": 1, "case_name": name,
            "saved_paths": sorted(p for p, v in _leaves(configuration).items() if v is not None)}


def report_instrument_configuration(execution: Any, audit: dict) -> dict:
    """同次冻结请求的白名单展示，不查询当前目录/HAL，不推断实测身份。"""
    from app.services.channel_emulator_binding import (
        CE_FREEZE_CONFIG_KEY, validate_frozen_channel_emulator_binding,
    )
    config = execution.config if isinstance(getattr(execution, 'config', None), dict) else {}
    def scalar(mapping, key):
        value = mapping.get(key)
        return value if isinstance(value, str) else None
    def endpoint(transport):
        if not isinstance(transport, dict):
            return None
        resource = scalar(transport, 'resource')
        host, port = scalar(transport, 'host'), transport.get('port')
        if resource:
            return resource
        if host and type(port) is int and 0 < port <= 65535:
            return f'[{host}]:{port}' if ':' in host and not (host.startswith('[') and host.endswith(']')) else f'{host}:{port}'
        return host
    rows = []
    for category, key in (('baseStation', FREEZE_CONFIG_KEY), ('channelEmulator', CE_FREEZE_CONFIG_KEY)):
        row = {'category': category, 'model': None, 'endpoint': None, 'adapter': None,
               'execution_mode': 'unknown', 'provenance': 'unavailable',
               'reason': '历史未记录或冻结配置无效；不查询当前配置补真', 'route': None}
        frozen = config.get(key)
        valid = isinstance(frozen, dict)
        if valid and category == 'baseStation':
            valid = validate_frozen_compatibility_snapshot(frozen) is None
        elif valid:
            try:
                validate_frozen_channel_emulator_binding(frozen)
            except ValueError:
                valid = False
        if valid:
            binding = frozen.get('resolved_binding') or {}
            if not isinstance(binding, dict):
                rows.append(row)
                continue
            manifest = binding.get('manifest') or {}
            transport = binding.get('expected_transport') or {}
            resolution = frozen.get('resolution') or {}
            if isinstance(resolution, dict) and isinstance(manifest, dict) and isinstance(transport, dict):
                mode = resolution.get('execution_mode', frozen.get('execution_mode', 'unknown'))
                row.update(model=scalar(manifest, 'model_name'), adapter=scalar(manifest, 'adapter_id'),
                           endpoint=endpoint(transport),
                           execution_mode=mode if mode in ('real', 'simulated') else 'unknown',
                           provenance='frozen_request', reason='冻结配置请求，不代表实测确认')
                profile = resolution.get('profile')
                if isinstance(profile, dict):
                    profile = profile.get('lte_2x2_internal_route') or {}
                    route_keys = ('pcc_bb_board', 'rx_connector', 'rx_converter',
                                  'tx1_connector', 'tx1_converter', 'tx2_connector', 'tx2_converter')
                    if isinstance(profile, dict):
                        row['route'] = {k: profile[k] for k in route_keys if isinstance(profile.get(k), str)} or None
        rows.append(row)
    # 目前该冻结件只含坐标 profile 与构造身份，不含型号名；不从类名猜硬件。
    from app.services.positioner_coordinate_profile import FREEZE_CONFIG_KEY as POSITIONER_KEY, _canonical_digest
    positioner = config.get(POSITIONER_KEY)
    positioner_row = {'category': 'positioner', 'model': None, 'endpoint': None, 'adapter': None,
                      'execution_mode': 'unknown', 'provenance': 'unavailable',
                      'reason': '历史未记录可展示仪器配置；不根据驱动类名猜型号', 'route': None}
    if isinstance(positioner, dict) and positioner.get('digest') == _canonical_digest({k: v for k, v in positioner.items() if k != 'digest'}):
        from app.services.positioner_coordinate_profile import PositionerCoordinateProfile
        resolution = positioner.get('resolution')
        valid = isinstance(resolution, dict) and resolution.get('execution_mode') in ('real', 'simulated')
        profile = positioner.get('profile')
        if profile is not None:
            try:
                PositionerCoordinateProfile.model_validate(profile)
            except ValueError:
                valid = False
        elif valid and resolution.get('status') == 'verified':
            valid = False
        if valid:
            mode = resolution['execution_mode']
            positioner_row.update(adapter=scalar(resolution, 'adapter'), execution_mode=mode,
                                  endpoint=endpoint(positioner.get('expected_driver_connection')) if mode == 'real' else None,
                                  provenance='frozen_request',
                                  reason='冻结配置请求，不代表实测确认；型号名未记录，不补当前值')
    rows.append(positioner_row)
    rows.append({'category': 'rfSwitch', 'model': None, 'endpoint': None, 'adapter': None,
                 'execution_mode': 'unknown', 'provenance': 'unavailable',
                 'reason': '同次执行未记录统一射频开关配置；不能补当前值', 'route': None})
    return {'schema_version': 1, 'instruments': rows,
            'channel_asset': deepcopy(audit.get('channel_asset')),
            'notice': '冻结配置请求不代表实测确认；模拟执行不证明真实仪器已连接或已生效'}


def _source(path: str, paths: set[str]) -> str:
    if path in paths:
        return "saved_configuration"
    if path == "base_station_config_mode" and "uxm_config_mode" in paths:
        return "saved_configuration"
    if path.startswith("component_carriers.0."):
        alias = path.removeprefix("component_carriers.0.")
        if alias in paths:
            return "saved_configuration"
        if alias in {"nr_arfcn", "carrier_id", "role"}:
            return "derived"
    if path.startswith("mac_profile.profile."):
        alias = path.removeprefix("mac_profile.profile.")
        if _MAC_LEGACY.get(alias) in paths:
            return "saved_configuration"
        carrier_alias = _MAC_LEGACY.get(alias, alias)
        if alias in {"duplex", "transmission_mode", "subcarrier_spacing_khz"} and f"component_carriers.0.{carrier_alias}" in paths:
            return "saved_configuration"
        if alias in {"uldl_configuration", "special_subframe", "rmc_version"} and f"lte_tdd_frame_structure.{alias}" in paths:
            return "saved_configuration"
        if alias == "tdd_period":
            return "derived"
        if alias in {"kind", "profile_version", "schema_version", "rat", "test_intent", "source_reference", "csi_rs_ports", "metric_requirements"}:
            return "derived"
    if path == "mac_profile.profile_digest":
        return "derived"
    return "launch_default"


def report_traceability(execution: Any, duration_s: float | None) -> dict:
    config = execution.config if isinstance(getattr(execution, "config", None), dict) else {}
    frozen = config.get(FREEZE_CONFIG_KEY)
    result = {"schema_version": 1, "status": "unavailable", "parameters": {},
              "case_name": None, "execution_mode": "unknown", "duration_s": duration_s,
              "recorded_window_count": None, "reason": "缺少有效的同次执行冻结配置"}
    if not isinstance(frozen, dict) or validate_frozen_compatibility_snapshot(frozen):
        return result
    raw = frozen.get("mimo_ota_configuration")
    # 不调用 canonicalizer 补旧默认：缺字段的历史行不能变成本次请求。
    if not isinstance(raw, dict) or not isinstance(raw.get("mac_profile"), dict):
        return result
    try:
        model = MIMOOTAConfiguration.model_validate(raw)
    except ValueError:
        return result
    # 仅展示原冻结确实存在的字段；模型用于结构校验和白名单，不制造缺失值。
    safe = {key: deepcopy(raw[key]) for key in _FIELDS if key in raw}
    if isinstance(safe.get("component_carriers"), list):
        safe["component_carriers"] = [
            {key: value for key, value in cc.items() if key in _CARRIER_FIELDS}
            for cc in safe["component_carriers"]
        ]
    origin = frozen.get(SOURCE_KEY)
    traced = (isinstance(origin, dict) and origin.get("schema_version") == 1
              and isinstance(origin.get("case_name"), str)
              and isinstance(origin.get("saved_paths"), list)
              and all(isinstance(p, str) for p in origin["saved_paths"]))
    paths = set(origin["saved_paths"]) if traced else set()
    result.update(
        status="frozen_request", reason="冻结请求不代表仪器已生效",
        case_name=origin["case_name"] if traced else None,
        execution_mode=(frozen.get("resolution") or {}).get("execution_mode", "unknown"),
        parameters={path: {"requested": value, "source": ("not_configured" if value is None else _source(path, paths)) if traced else "untraceable"}
                    for path, value in _leaves(safe).items()},
        binding={key: frozen.get(key) for key in (
            "lab_profile_id", "instrument_model_id", "instrument_connection_id", "binding_digest")},
        adapter=(frozen.get("resolution") or {}).get("adapter"),
        requested_windows_per_azimuth=raw.get("num_samples_per_azimuth"),
    )
    _window_summary(result, execution, config, frozen, model)
    _channel_summary(result, config, frozen, model)
    return result


def _channel_summary(result: dict, config: dict, frozen: dict, model: MIMOOTAConfiguration) -> None:
    from app.services.channel_emulator_execution_plan import (
        CHANNEL_ASSET_RESOLUTION_FREEZE_KEY, CE_PLAN_FREEZE_CONFIG_KEY,
        LEGACY_CHANNEL_FILE_RESOLUTION_FREEZE_KEY,
        validate_frozen_channel_asset_resolution, validate_frozen_channel_emulator_load_context,
    )

    asset = frozen.get(CHANNEL_ASSET_RESOLUTION_FREEZE_KEY)
    reference_id = model.channel_asset_id
    if asset is None and reference_id is None and model.engine_mode == "keysight_gcm":
        asset = frozen.get(LEGACY_CHANNEL_FILE_RESOLUTION_FREEZE_KEY)
        reference_id = model.scd_id
    if asset is not None:
        try:
            identity = validate_frozen_channel_asset_resolution(asset)
            if identity["channel_asset_id"] == str(reference_id):
                result["channel_asset"] = {k: identity.get(k) for k in (
                    "channel_asset_id", "source_type", "name", "canonical_name", "associated_file_path",
                    "instrument_connection_id", "instrument_model_id", "executable_content_digest",
                )}
        except ValueError:
            pass  # 无效审计块不补当前资产，不改变正式判据。
    result["channel_load_request"] = None
    try:
        request, _ = validate_frozen_channel_emulator_load_context(config, config.get(CE_PLAN_FREEZE_CONFIG_KEY))
        result["channel_load_request"] = {k: request[k] for k in (
            "source", "channel_asset_id", "effective_engine_mode", "requested_load_mode",
        )}
    except ValueError:
        pass  # 历史缺件/损坏不猜有效引擎；已有正式 outcome 独立保守裁决。


def _window_summary(result: dict, execution: Any, config: dict, frozen: dict, model: MIMOOTAConfiguration) -> None:
    from app.services.mimo_ota.base_station_execution_evidence import (
        BaseStationExecutionEvidence, parse_base_station_execution_evidence,
        _attempt_window_shape_envelope,
    )
    from app.services.mimo_ota.executors.measure import _build_pcell_requested_config

    normalized = parse_base_station_execution_evidence(config.get("base_station_execution_evidence"))
    if normalized is None:
        return
    evidence = BaseStationExecutionEvidence.model_validate(normalized)
    if (evidence.execution_id != str(getattr(execution, "id", ""))
            or evidence.adapter != result["adapter"]
            or evidence.execution_mode != result["execution_mode"]
            or evidence.identity.instrument_connection_id != frozen.get("instrument_connection_id")
            or evidence.current_measurement_attempt_id is None
            or evidence.requested_config.payload != asdict(_build_pcell_requested_config(model))):
        return
    valid, _, windows, releases = _attempt_window_shape_envelope(evidence, evidence.current_measurement_attempt_id)
    if not valid or any(
        w.config_digest != evidence.requested_config.digest
        or releases[w.lease_id].session_token != w.session_token
        for w in windows
    ):
        return
    positions = {p.azimuth_deg for p in evidence.requested_positions}
    if positions != set(model.azimuths_deg):
        return
    plans = []
    for azimuth in model.azimuths_deg:
        group = [w for w in windows if w.position.azimuth_deg == azimuth]
        request = group[0].trust.request if group[0].trust else None
        plans.append({"azimuth_deg": azimuth, "requested": request.requested_window_count if request else None,
                      "planned": request.expected_window_count if request else None, "recorded": len(group)})
    provenances = {w.trust.simulated if w.trust else None for w in windows}
    provenance = ("simulated" if evidence.execution_mode == "simulated" or provenances == {True}
                  else "recorded_real" if provenances == {False}
                  else "mixed" if provenances == {False, True} else "unknown")
    result.update(recorded_window_count=len(windows), window_plan=plans,
                  window_elapsed_s=sum((w.completed_at - w.started_at).total_seconds() for w in windows),
                  window_provenance=provenance,
                  application_confirmation="本段只读请求及窗口记录，逐字段生效以同次 SCPI/receipt 证据为准")
    _application_summary(result, evidence, windows, model, frozen)


def _application_summary(result: dict, evidence: Any, windows: list, model: MIMOOTAConfiguration, frozen: dict) -> None:
    from app.hal.base_station_mac_profile import build_mac_throughput_command_inputs
    from app.hal.base_station_manifest import BaseStationAdapterManifest
    from app.services.execution_scpi_evidence import base_station_config_receipts_confirmed
    from app.services.mimo_ota.executors.measure import _build_pcell_requested_config

    config_fields = _build_pcell_requested_config(model).receipt_payload()
    mac_fields = build_mac_throughput_command_inputs(model.mac_profile)
    mac_fields["mac_profile"] = model.mac_profile.profile.model_dump(mode="json")
    try:
        manifest = BaseStationAdapterManifest.model_validate(frozen["resolved_binding"]["manifest"])
    except (KeyError, TypeError, ValueError):
        manifest = None
    scoped_rows = {}
    required_scopes = {(w.lease_id, w.session_token) for w in windows}
    receipts = [("config", row, config_fields) for row in evidence.adapter_operations if row.operation == "config"]
    receipts += [("mac", row, mac_fields) for row in (evidence.mac_profile_receipts or [])
                 if row.profile_digest == model.mac_profile.profile_digest]
    for prefix, receipt, expected in receipts:
        if receipt.measurement_attempt_id != evidence.current_measurement_attempt_id:
            continue
        if not any(w.lease_id == receipt.lease_id and w.session_token == receipt.session_token for w in windows):
            continue
        if prefix == "config" and receipt.frozen_request_digest != evidence.requested_config.digest:
            continue
        attaches = [a for a in (evidence.attach_operations or [])
                    if (a.measurement_attempt_id, a.lease_id, a.session_token, a.adapter)
                    == (receipt.measurement_attempt_id, receipt.lease_id, receipt.session_token, receipt.adapter)]
        if prefix == "config":
            operations = [o for o in evidence.adapter_operations if o.operation == "config"
                          and (o.measurement_attempt_id, o.lease_id, o.session_token, o.adapter)
                          == (receipt.measurement_attempt_id, receipt.lease_id, receipt.session_token, receipt.adapter)]
            activation_confirmed = bool(manifest and len(operations) == 1 and len(attaches) == 1
                                        and base_station_config_receipts_confirmed(evidence, manifest, receipt, attaches[0]))
        else:
            activation_confirmed = bool(manifest and len(attaches) == 1 and attaches[0].formally_confirmed
                                        and not attaches[0].simulated
                                        and set(attaches[0].exchange_ids).issubset(set(evidence.exchange_ids))
                                        and any(p.kind == model.mac_profile.profile.kind
                                                and p.profile_version == model.mac_profile.profile.profile_version
                                                and p.application_evidence == "authoritative_readback"
                                                for p in manifest.mac_profiles))
        for field in receipt.fields:
            if field.field not in expected or field.requested != expected[field.field]:
                continue
            confirmed = (activation_confirmed and evidence.execution_mode == "real" and not receipt.simulated
                         and field.status == "confirmed" and bool(field.exchange_ids)
                         and set(field.exchange_ids).issubset(set(receipt.exchange_ids))
                         and set(field.exchange_ids).issubset(set(evidence.exchange_ids)))
            key = f"{prefix}.{field.field}"
            row = {"requested": field.requested, "applied": field.applied if confirmed else None,
                   "status": "confirmed" if confirmed else "unknown", "simulated": receipt.simulated,
                   "reason": field.reason}
            # 同一 attempt 同字段出现冲突时不任选一次充当应用真值。
            scope = (receipt.lease_id, receipt.session_token)
            scopes = scoped_rows.setdefault(key, {})
            if scope in scopes and scopes[scope] != row:
                row = {"requested": expected[field.field], "applied": None, "status": "unknown",
                       "simulated": receipt.simulated, "reason": "同次应用回执冲突"}
            scopes[scope] = row
    rows = {}
    for key, scopes in scoped_rows.items():
        reference = next(iter(scopes.values()))
        globally_confirmed = (set(scopes) == required_scopes
                              and all(row["status"] == "confirmed" and row["applied"] == reference["applied"]
                                      for row in scopes.values()))
        rows[key] = {**reference, "status": "confirmed" if globally_confirmed else "unknown",
                     "applied": reference["applied"] if globally_confirmed else None,
                     "simulated": any(row["simulated"] for row in scopes.values()),
                     "reason": reference["reason"] if globally_confirmed else "未确认全部窗口租约下的一致生效值"}
    result["application_fields"] = rows


def report_traceability_parameters(audit: dict) -> dict:
    """复用 PDF parameters 与 GUI step_configs，避免第二份客户端参数真值。"""
    rows = {
        "审计说明": audit["reason"], "执行模式": audit["execution_mode"],
        "原始用例名称": audit["case_name"] or "未冻结（名称来源不可追溯）",
        "实际总耗时 (s)": audit["duration_s"] if audit["duration_s"] is not None else "未知",
        "记录窗口数": audit["recorded_window_count"] if audit["recorded_window_count"] is not None else "未知（未借计划数补真）",
    }
    for path, value in audit["parameters"].items():
        requested = value["requested"]
        if isinstance(requested, list) and len(requested) > 16:
            # 361 个允许方位不能塞进 PDF 单个不可分页的表格行。
            for start in range(0, len(requested), 16):
                rows[f"{path}[{start}:{min(start + 16, len(requested))}]"] = {
                    "冻结请求": requested[start:start + 16], "来源": _SOURCE_LABELS[value["source"]]}
        else:
            rows[path] = {"冻结请求": requested, "来源": _SOURCE_LABELS[value["source"]]}
            if path in {"measurement_duration_s", "sample_interval_ms"}:
                rows[path]["生效说明"] = "历史兼容字段，不控制本次测量"
            elif path in {"pass_criteria.min_throughput_ratio", "theoretical_peak_throughput_mbps"}:
                rows[path]["生效说明"] = "当前判据已弃用此字段；历史判据以原落库判决为准，不重写历史结论"
            elif path == "pass_criteria.min_throughput_mbps":
                rows[path]["生效说明"] = "当前规则：操作员绝对 Mbps 阈值；可信实测均值不低于此值才通过，未配置则 UNKNOWN；历史判据以原落库判决为准"
    if audit["status"] == "frozen_request":
        rows["预计总耗时"] = "未知：统计计数无墙钟换算承诺，另含初始化、attach、移动与清理开销"
    if "binding" in audit:
        rows["冻结仪器绑定"] = {**audit["binding"], "adapter": audit["adapter"]}
    if "window_plan" in audit:
        for plan in audit["window_plan"]:
            rows[f"方位 {plan['azimuth_deg']}° 窗口请求/计划/记录"] = plan
        rows["窗口累计实际耗时 (s)"] = audit["window_elapsed_s"]
        rows["窗口来源"] = audit["window_provenance"]
    if "application_fields" in audit:
        for field, value in audit["application_fields"].items():
            rows[f"仪器请求/确认生效（不是 KPI） {field}"] = value
    if "channel_asset" in audit:
        for field, value in audit["channel_asset"].items():
            rows[f"冻结信道资产（名称不裁决频段/RAT） {field}"] = value
    if "channel_load_request" in audit:
        rows["有效信道引擎请求（不代表已加载）"] = audit["channel_load_request"] or "未冻结或不可核验"
    return rows
