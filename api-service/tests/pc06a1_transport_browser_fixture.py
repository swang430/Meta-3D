"""隔离真实HAL软件链：所有仪器transport脚本化；不是真机、不改生产资格门。"""
import asyncio
import json
import os
import socket
from contextlib import asynccontextmanager
from pathlib import Path

if os.environ.get('USE_MOCK_INSTRUMENTS') != 'true' or not os.environ.get('DATABASE_URL', '').startswith('sqlite:////tmp/pc06a1-transport-'):
    raise RuntimeError('真实HAL隔离fixture必须显式全局Mock启动，且只用专属/tmp SQLite')
# 启动前禁止所有非回环socket连接，即使遗漏transport替换也不能碰真设备。
_connect = socket.socket.connect
def local_only(self, address):
    if isinstance(address, tuple) and address[0] not in ('127.0.0.1', '::1', 'localhost'):
        raise RuntimeError(f'Task6隔离禁止外部连接：{address}')
    return _connect(self, address)
socket.socket.connect = local_only

from app.main import app
from app.db.database import SessionLocal
from tests.pc06a1_browser_fixture import seed
from tests.test_pc06a1_batch_plan import shared_switch
from tests.test_pc06a1_batch_jobs import runtime
from tests.test_pc06a1_batch_safety import safety_runtime
from app.models.lab_profile import LabProfile
from app.models.switch_topology import SwitchTopology
from app.models.instrument import InstrumentCategory, InstrumentConnection
from app.services import instrument_hal_service
from pytest import MonkeyPatch


@asynccontextmanager
async def isolated_lifespan(app):
    seed(include_switch=False)
    patch = MonkeyPatch()
    with SessionLocal() as db:
        lab = db.query(LabProfile).one()
        topo = db.query(SwitchTopology).one()
        category=db.query(InstrumentCategory).filter_by(category_key='rfSwitch').first()
        switch = (topo, db.query(InstrumentConnection).filter_by(category_id=category.id).one()) if category else shared_switch.__wrapped__(db, lab, topo)
        if os.environ.get('PC06A1_SERIAL') == 'true':
            from tests.test_pc06a1_batch_jobs import serial_graph
            switch = serial_graph(db, switch)
        for index, node in enumerate(topo.nodes):
            node.setdefault('label', node['id'])
            node['position'] = {'x':(index%4)*180, 'y':(index//4)*180}
        from sqlalchemy.orm.attributes import flag_modified
        for mode in topo.operating_modes:
            mode.setdefault('name', mode['id'])
        flag_modified(topo, 'nodes');flag_modified(topo, 'operating_modes');db.commit()
        state = runtime.__wrapped__(db, lab, patch)
        jobs, hal, calls = safety_runtime.__wrapped__(state, switch, db, patch)
        ce_transport=hal.drivers['channelEmulator']._visa_resource
        sa_transport=hal.drivers['signalAnalyzer']._visa_session
        # 解除生命周期fixture的人工替身，走真实生产准备/严格切换链。
        patch.setattr(jobs, '_prepare_item', hal.batch_prepare)
        hal.mode = instrument_hal_service.DriverMode.REAL
        hal._initialized = True
        patch.setattr(instrument_hal_service, '_hal_service', hal)
        driver = hal.drivers['rfSwitch']
        original = driver._send_command
        positions = {'1:INT_RELAY_A':'1', '1:INT_RELAY_B':'2'}
        async def transport(command):
            if command in ('1:INT_RELAY_A_1','1:INT_RELAY_A_2','1:INT_RELAY_B_2'):
                calls.append(command);positions[command[:-2]]=command[-1];return 'OK'
            if command in ('1:INT_RELAY_A?','1:INT_RELAY_B?'):
                calls.append(command)
                return 'ERROR 201 NC' if os.environ.get('PC06A1_SWITCH_REPLY')=='wrong' else positions[command[:-1]]
            return await original(command)
        patch.setattr(driver, '_send_command', transport)
        try:
            yield
        finally:
            await jobs.shutdown_route_batch_jobs()
            destination=Path(os.environ['PC06A1_TRANSPORT_RECORD'])
            destination.write_text(json.dumps({'switch':calls,
                'ce':ce_transport.commands,'sa':sa_transport.commands},ensure_ascii=False,indent=2))
            patch.undo()

app.router.lifespan_context = isolated_lifespan
