"""按登记时的场景原文核对可复用范围。未知字段也参与比较。"""
import hashlib
import json


def scenario_digest(snapshot):
    raw = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _operating_fields(snapshot):
    fields = {k: v for k, v in snapshot.items() if k not in {"description", "name", "version", "kpi_definitions"}}
    steps = fields.get("step_configuration")
    if isinstance(steps, dict):
        # 场景第一次增加门限时，模型也会序列化其余未配置的步骤为 null。
        steps = {k: v for k, v in steps.items() if v is not None}
        validation = steps.get("kpi_validation")
        if isinstance(validation, dict):
            remaining = {k: v for k, v in validation.items() if k != "kpi_thresholds" and v is not None}
            if remaining:
                steps["kpi_validation"] = remaining
            else:
                del steps["kpi_validation"]
        fields["step_configuration"] = steps or None
    return fields


def same_operating_conditions(reference, reference_digest, current):
    if not isinstance(reference, dict) or not reference.get("id") or not isinstance(current, dict):
        return False
    try:
        return (scenario_digest(reference) == reference_digest
                and scenario_digest(_operating_fields(reference)) == scenario_digest(_operating_fields(current)))
    except (ValueError, TypeError, OverflowError):
        return False


def registration_matches(entry, current, current_digest):
    if "reference_scenario" in entry:
        reference = entry["reference_scenario"]
        return (isinstance(reference, dict) and isinstance(reference.get("version"), str)
                and entry.get("scenario_version") == reference["version"]
                and same_operating_conditions(reference, entry.get("scenario_sha256"), current))
    return entry.get("scenario_version") == current.get("version") and entry.get("scenario_sha256") == current_digest

def matching_registrations(candidates, current, current_digest):
    matching = [entry for entry in candidates if registration_matches(entry, current, current_digest)]
    exact = [entry for entry in matching if entry.get("scenario_sha256") == current_digest
             and entry.get("scenario_version") == current.get("version")]
    return exact or matching
