"""Migrate pre-confirmation API fixtures without changing their resolver assertions."""
from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel
from app.services.instrument_saved_configuration import saved_configuration_digest


def saved_confirmation(db, key):
    category = db.query(InstrumentCategory).filter_by(category_key=key).populate_existing().one()
    model = db.get(InstrumentModel, category.selected_model_id)
    connection = db.query(InstrumentConnection).filter_by(category_id=category.id).populate_existing().one_or_none()
    # Invalid snapshots cannot be confirmed. These existing tests intentionally
    # exercise earlier semantic rejection (missing preset/etc), not confirmation.
    token = saved_configuration_digest(category, model, connection)
    return {"expected_saved_configuration_digest": token or "0" * 64}
