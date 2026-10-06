"""Read-only digest of saved configuration for operator-confirmed Lab sync.

This is not execution qualification or a stored revision ledger. Runtime
observations and certification are deliberately outside this confirmation.
"""
import hashlib
import json

from app.services.base_station_model_preset import BaseStationModelPreset, persistent_base_station_connection_params
from app.services.channel_emulator_model_preset import ChannelEmulatorModelPreset


def saved_configuration_digest(category, model, connection) -> str | None:
    if model is None or connection is None:
        return None
    params = connection.connection_params
    if params is not None and not isinstance(params, dict):
        return None
    if category.category_key == "baseStation":
        params = persistent_base_station_connection_params(params)
    preset = None
    if category.category_key in {"baseStation", "channelEmulator"}:
        presets = (connection.base_station_model_presets if category.category_key == "baseStation"
                   else connection.channel_emulator_model_presets)
        if not isinstance(presets, dict):
            return None
        preset = presets.get(str(model.id))
        try:
            schema = BaseStationModelPreset if category.category_key == "baseStation" else ChannelEmulatorModelPreset
            parsed = schema.model_validate(preset)
            if str(parsed.model_id) != str(model.id):
                return None
        except (TypeError, ValueError):
            return None
    payload = {
        "category_id": str(category.id), "category_key": category.category_key,
        "selected_model_id": str(category.selected_model_id),
        "model": {"id": str(model.id), "vendor": model.vendor, "model": model.model, "capabilities": model.capabilities},
        "driver_mode": category.driver_mode or "auto", "is_active": category.is_active,
        "connection": {"id": str(connection.id), "endpoint": connection.endpoint,
                       "controller_ip": connection.controller_ip, "protocol": connection.protocol,
                       "port": connection.port, "username": connection.username,
                       "password_encrypted": connection.password_encrypted,
                       "notes": connection.notes, "params": params},
        "selected_preset": preset,
    }
    try:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        return None
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
