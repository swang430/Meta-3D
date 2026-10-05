"""P2-79：仪器文件归属只取显式 connection/model，不由当前选择补真。"""
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel


def validate_channel_asset_owner(
    db: Session, connection_id, model_id, *, require_selected: bool = True,
) -> InstrumentConnection:
    try:
        connection_id = UUID(str(connection_id))
        model_id = UUID(str(model_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("信道资产归属必须明确提供连接与仪器型号") from exc
    connection = db.get(InstrumentConnection, connection_id)
    model = db.get(InstrumentModel, model_id)
    category = db.get(InstrumentCategory, connection.category_id) if connection else None
    if (category is None or category.category_key != "channelEmulator"
            or model is None or model.category_id != category.id):
        raise ValueError("信道资产归属连接/型号不属于同一信道仿真器类别")
    if require_selected and category.selected_model_id != model.id:
        raise ValueError("信道资产请求型号与已保存型号不一致，请刷新后重新确认")
    return connection


def owned_channel_model_params(db: Session, connection_id, model_id, raw) -> dict:
    """派生条目读源资产归属，不能信任客户端标记；无派生 ID 的手工配置保留。"""
    from app.models.channel_asset import ChannelAsset
    from app.models.standard_channel import StandardChannelDefinition
    params = dict(raw or {})
    if "available_channel_models" not in params:
        return params
    owned = []
    for entry in params["available_channel_models"] or []:
        if not isinstance(entry, dict) or not (entry.get("channel_asset_id") or entry.get("scd_id")):
            owned.append(entry)
            continue
        try:
            source_id = UUID(str(entry.get("channel_asset_id") or entry.get("scd_id")))
        except (ValueError, TypeError):
            continue
        # 现代 ChannelAsset 同 ID 优先，不能退回旧 SCD twin 补另一份归属。
        source = db.get(ChannelAsset, source_id) or db.get(StandardChannelDefinition, source_id)
        if (source is None or model_id is None or source.instrument_model_id is None
                or not getattr(source, "is_active", True)
                or str(source.instrument_connection_id) != str(connection_id)
                or str(source.instrument_model_id) != str(model_id)
                or source.associated_file_path != entry.get("filename")):
            continue
        owned.append({**entry, "instrument_model_id": str(model_id)})
    params["available_channel_models"] = owned
    return params
