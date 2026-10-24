"""路损补偿的应用事实快照。

应用、证书来源与正式可信门是三个独立事实。历史记录缺失或畸形时只能降级为
``unknown``，不得从旧补偿数值或证书 ID 反推。
"""
from __future__ import annotations

from typing import Any, Mapping, Optional
from copy import deepcopy
from types import SimpleNamespace


SCHEMA_VERSION = 1
_GATE_MODES = {"strict", "operator_bypass", "mock_not_applicable"}
_MISSING_REASONS = {
    "missing",
    "expired",
    "frequency_mismatch",
    "operating_mode_mismatch",
}
_FIELDS = {
    "schema_version",
    "status",
    "provenance",
    "reason",
    "gate_mode",
    "certificate_id",
    "value_disclosure",
}


def _legacy_unknown() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "unknown",
        "provenance": "unknown",
        "reason": "legacy_unclassified",
        "gate_mode": "strict",
        "certificate_id": None,
        "value_disclosure": "none",
    }


def _certificate_provenance(certificate: Any) -> str:
    use_mock = getattr(certificate, "use_mock", None)
    if use_mock is False:
        return "real"
    if use_mock is True:
        return "simulated"
    return "unknown"


def build_path_loss_application(
    *,
    selected_certificate: Optional[Any],
    applied_certificate: Optional[Any],
    selection_reason: str,
    gate_mode: str,
) -> dict[str, Any]:
    """从当次选择与实际应用对象构造不可变语义快照。"""
    if gate_mode not in _GATE_MODES:
        raise ValueError(f"Unknown path-loss gate mode: {gate_mode}")

    if applied_certificate is not None:
        if selected_certificate is None or selection_reason != "selected":
            raise ValueError("An applied certificate must be the selected certificate")
        if getattr(applied_certificate, "id", None) != getattr(
            selected_certificate, "id", None
        ):
            raise ValueError("Applied and selected path-loss certificates differ")
        provenance = _certificate_provenance(applied_certificate)
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "applied",
            "provenance": provenance,
            "reason": "selected",
            "gate_mode": gate_mode,
            "certificate_id": str(applied_certificate.id),
            "value_disclosure": (
                "verified" if provenance == "real" else "hidden_unverified"
            ),
        }

    if selected_certificate is not None:
        if selection_reason != "selected":
            raise ValueError("A selected certificate requires selection reason 'selected'")
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "not_applied",
            "provenance": _certificate_provenance(selected_certificate),
            "reason": "rejected_untrusted",
            "gate_mode": gate_mode,
            "certificate_id": str(selected_certificate.id),
            "value_disclosure": "none",
        }

    if selection_reason not in _MISSING_REASONS:
        raise ValueError(f"Unknown path-loss selection reason: {selection_reason}")
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "not_applied",
        "provenance": "missing",
        "reason": selection_reason,
        "gate_mode": gate_mode,
        "certificate_id": None,
        "value_disclosure": "none",
    }


def parse_path_loss_application(value: Any) -> dict[str, Any]:
    """验证持久化快照；任何未知/非法组合都保守降级。"""
    if isinstance(value,Mapping) and value.get('schema_version')==2:
        return _parse_v2(value)
    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        return _legacy_unknown()
    parsed = dict(value)
    if (
        type(parsed.get("schema_version")) is not int
        or parsed["schema_version"] != SCHEMA_VERSION
    ):
        return _legacy_unknown()
    if parsed.get("gate_mode") not in _GATE_MODES:
        return _legacy_unknown()

    status = parsed.get("status")
    provenance = parsed.get("provenance")
    reason = parsed.get("reason")
    certificate_id = parsed.get("certificate_id")
    disclosure = parsed.get("value_disclosure")

    if status == "applied":
        if (
            provenance not in {"real", "simulated", "unknown"}
            or reason != "selected"
            or not isinstance(certificate_id, str)
            or not certificate_id
        ):
            return _legacy_unknown()
        if (
            provenance in {"simulated", "unknown"}
            and parsed["gate_mode"] != "mock_not_applicable"
        ):
            return _legacy_unknown()
        expected_disclosure = "verified" if provenance == "real" else "hidden_unverified"
        return parsed if disclosure == expected_disclosure else _legacy_unknown()

    if status == "not_applied" and reason == "rejected_untrusted":
        if (
            provenance not in {"simulated", "unknown"}
            or not isinstance(certificate_id, str)
            or not certificate_id
            or disclosure != "none"
            or parsed["gate_mode"] == "mock_not_applicable"
        ):
            return _legacy_unknown()
        return parsed

    if status == "not_applied" and reason in _MISSING_REASONS:
        if provenance == "missing" and certificate_id is None and disclosure == "none":
            return parsed

    if parsed == _legacy_unknown():
        return parsed
    return _legacy_unknown()


def path_loss_application_is_formally_verified(value: Any) -> bool:
    """正式消费者统一白名单：必须是可解析的 applied explicit-real 快照。"""
    application = parse_path_loss_application(value)
    return (
        application["status"] == "applied"
        and application["provenance"] == "real"
        and application["reason"] == "selected"
        and application["value_disclosure"] == "verified"
    )


def path_loss_application_message(value: Any) -> str:
    """生成人读叙事；故意不接收或格式化任何补偿数值。"""
    application = parse_path_loss_application(value)
    status = application["status"]
    provenance = application["provenance"]
    reason = application["reason"]

    if application.get('schema_version')==2 and status!='applied':
        if reason=='route_identity_mismatch':
            return '当前通路与执行冻结身份不一致；请新建执行复核接线，未应用旧通路补偿。'
        if reason=='pending_compensation_wiring':
            return '已冻结逐链采用来源；新参考面数值消费尚未接通，本次未应用补偿。'
        return '逐链冻结来源尚未全部应用；缺失链或诊断来源不形成正式补偿。'

    if status == "applied" and provenance == "real":
        return "已应用经验证的路损补偿。"
    if status == "applied" and provenance == "simulated":
        return "已应用模拟路损证书用于流程演练；数值不进入正式结果。"
    if status == "applied" and provenance == "unknown":
        return "已应用路损补偿；证书来源未知，补偿数值不展示，结果不参与正式判定。"
    if reason == "rejected_untrusted":
        return "检测到路损证书，但因来源未验证未应用；本次结果未补偿，补偿数值不展示。"
    if reason == "expired":
        return "匹配的路损证书已过期；本次结果未补偿。"
    if reason == "frequency_mismatch":
        return "现有证书与本次频率不匹配；本次结果未补偿。"
    if reason == "operating_mode_mismatch":
        return "现有证书与本次 RF operating mode 不匹配；本次结果未补偿。"
    if reason == "missing":
        return "未找到匹配的路损证书；本次结果未补偿。"
    return "历史记录无法证明是否应用路损补偿；补偿数值不展示。"


def build_frozen_path_loss_application(frozen,*,gate_mode,applied=False,reason='incomplete_coverage'):
    """v2区分冻结选择与真实应用；Task4只有legacy-only适配可标已应用。"""
    if frozen.get('version')!=1:
        return _legacy_unknown()
    routes=frozen['route_entries']
    complete=bool(routes) and all(row['source_kind']!='unavailable' for row in routes)
    real=complete and all(row['measurement_provenance']=='real' for row in routes)
    if applied and not real:
        raise ValueError('未完整覆盖的冻结来源不能标已应用')
    return dict(schema_version=2,status='applied' if applied else 'not_applied',
        provenance='real' if real else 'missing',reason='selected' if applied else reason,
        gate_mode=gate_mode,certificate_id=None,value_disclosure='verified' if applied else 'none',
        route_compensation=deepcopy(frozen),applied_chain_ids=[row['chain_id'] for row in routes] if applied else [])


def _parse_v2(value):
    if set(value)!=_FIELDS|{'route_compensation','applied_chain_ids'} or value.get('gate_mode') not in _GATE_MODES:
        return _legacy_unknown()
    from app.services.mimo_ota.route_calibration_freeze import read_execution_route_compensation,FREEZE_KEY
    try:
        frozen=value['route_compensation']
        read_execution_route_compensation(SimpleNamespace(id=frozen['execution_id'],config={FREEZE_KEY:frozen}))
        routes=frozen['route_entries']
        complete=bool(routes) and all(row['source_kind']!='unavailable' and row['measurement_provenance']=='real' for row in routes)
        applied=value['status']=='applied'
        if value['certificate_id'] is not None or value['status'] not in ('applied','not_applied'):
            return _legacy_unknown()
        if applied:
            if (not complete or value['reason']!='selected' or value['provenance']!='real' or
                value['value_disclosure']!='verified' or
                sorted(value['applied_chain_ids'])!=sorted(row['chain_id'] for row in routes)):
                return _legacy_unknown()
        elif (value['applied_chain_ids']!=[] or value['value_disclosure']!='none' or
              value['provenance']!=('real' if complete else 'missing') or
              value['reason'] not in ('pending_compensation_wiring','incomplete_coverage','diagnostic','rejected_untrusted','route_identity_mismatch')):
            return _legacy_unknown()
        return deepcopy(dict(value))
    except (ValueError,KeyError,TypeError,AttributeError):
        return _legacy_unknown()
