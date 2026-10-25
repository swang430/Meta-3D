"""真实 SQLite ORM 绑定 UUID；不以 MagicMock 查询掩盖冻结字符串边界。"""
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.models.instrument import InstrumentCategory, InstrumentConnection
from app.services.channel_emulator_certification import freeze_channel_emulator_execution_qualification
from app.hal.base_station_compatibility import canonical_payload_digest
from tests.test_p2_61_channel_emulator_certification import _qualification_fixture, _qualification_hal


def _execution(identity):
    _, execution, case, _ = _qualification_fixture()
    frozen_binding = execution.config['channel_emulator_binding_freeze']
    frozen_binding['instrument_connection_id'] = identity
    frozen_binding['resolved_binding']['instrument_connection_id'] = identity
    frozen_binding['digest'] = canonical_payload_digest({k: v for k, v in frozen_binding.items() if k != 'digest'})
    return execution, case


def test_configured_connection_string_freeze_uses_real_sqlite_uuid_binding(tmp_path):
    identity = str(uuid4())
    execution, case = _execution(identity)
    engine = create_engine(f'sqlite:///{tmp_path / "qualification.db"}')
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            category = InstrumentCategory(category_key='channelEmulator', category_name='隔离CE', driver_mode='mock')
            db.add(category); db.flush()
            connection = InstrumentConnection(id=UUID(identity), category_id=category.id,
                created_by='隔离测试')
            db.add(connection); db.commit()
            result = freeze_channel_emulator_execution_qualification(db, _qualification_hal(), execution, case)
            assert result.classification == 'diagnostic'
            assert 'site_certification_not_active' in result.reasons
            assert result.instrument_connection_id == identity
            assert execution.config['channel_emulator_binding_freeze']['instrument_connection_id'] == identity
            # 合法 UUID 但无真实连接，保持既有明确拒绝，不走默认/诊断兜底。
            db.delete(connection); db.commit()
            missing, missing_case = _execution(identity)
            with pytest.raises(ValueError, match='connection no longer exists'):
                freeze_channel_emulator_execution_qualification(db, _qualification_hal(), missing, missing_case)
            invalid, invalid_case = _execution('not-a-uuid')
            with pytest.raises(ValueError, match='UUID'):
                freeze_channel_emulator_execution_qualification(db, _qualification_hal(), invalid, invalid_case)
    finally:
        engine.dispose()
