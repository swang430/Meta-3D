"""P2-58 ②：信道仿真器分型号 preset 的后端地基门（模型 / 原子保存 / 剔除集合 / 迁移）。

镜像 BS 的门文件（``test_base_station_model_presets.py`` / ``…_atomic_model_save.py`` /
``…_model_preset_recovery.py``），但方向按设计稿 §2 外审 R2 的纠正：
``available_channel_models`` **必须原样进 preset**，``CHANNEL_EMULATOR_RUNTIME_CONNECTION_PARAM_KEYS``
是空集。每条门都配过让它变红的变异（见 PR 描述里的门↔变异表）。

迁移门**真的跑** ``upgrade()`` / ``downgrade()``（``MigrationContext`` + ``Operations.context``
手动驱动 alembic 的 ``op`` 代理），不是查源码里有没有某个 token —— BS 那条
``test_preset_backfill_never_promotes_runtime_detected_app_to_saved_truth`` 是存在性门，
这里升到行为门（⓪④：存在性门可被保留 token 的错写法绕过）。
"""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.instrument import (
    InstrumentCategory,
    InstrumentConnection,
    InstrumentModel,
)
from app.schemas.instrument import FEConnectionUpdate
from app.services.channel_emulator_model_preset import (
    CHANNEL_EMULATOR_RUNTIME_CONNECTION_PARAM_KEYS,
    ChannelEmulatorModelPreset,
    parse_channel_emulator_model_presets,
    persistent_channel_emulator_connection_params,
    save_channel_emulator_model_preset,
)


API_SERVICE_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    API_SERVICE_ROOT
    / "alembic"
    / "versions"
    / "a3c5e7f9b1d3_add_channel_emulator_model_presets.py"
)

F64_ENDPOINT = "192.168.100.21:3334"
FS16_ENDPOINT = "TCPIP0::192.168.100.22::inst0::INSTR"


def _f64_params() -> dict:
    """活动 F64 连接的参数：全部是操作员 / 同步维护的型号配置资产，一个都不能丢。"""

    return {
        "timeout_sec": 30,
        "alignment_name": "CAICT_2026-08_n78",
        "available_channel_models": [
            {"filename": "3GPP_5GNR_1x1_TDLA30-5.smu", "radio_technology": "nr5g"},
            "New GCM Model 5.smu",
        ],
        "default_emulation_file": "New GCM Model 5.smu",
    }


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


@pytest.fixture
def ce_db():
    """内存 SQLite：channelEmulator 品类 + F64 / FS16 两个型号 + 活动为 F64 的连接，
    ``channel_emulator_model_presets`` 尚为 NULL（从未存过任何型号）。"""

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    db = Session()
    category = InstrumentCategory(
        id=uuid4(),
        category_key="channelEmulator",
        category_name="信道仿真器",
        driver_mode="mock",
        is_active=True,
    )
    f64 = InstrumentModel(
        id=uuid4(),
        category_id=category.id,
        vendor="Keysight",
        model="PROPSIM F64",
        capabilities={},
        is_available=True,
    )
    fs16 = InstrumentModel(
        id=uuid4(),
        category_id=category.id,
        vendor="Keysight",
        model="PROPSIM FS16",
        capabilities={},
        is_available=True,
    )
    category.selected_model_id = f64.id
    connection = InstrumentConnection(
        id=uuid4(),
        category_id=category.id,
        endpoint=F64_ENDPOINT,
        controller_ip="192.168.100.21",
        port=3334,
        protocol="socket",
        notes="现场 F64",
        connection_params=_f64_params(),
        # 不显式传 channel_emulator_model_presets=None：SQLAlchemy JSON 会把显式 None
        # 存成 JSON 文本 'null' 而不是 SQL NULL，迁移回填的 IS NULL 认不到它。
        # 生产 API 建 InstrumentConnectionDB 时从不设该列（= SQL NULL），测试跟生产同形。
        created_by="test",
    )
    db.add_all([category, f64, fs16, connection])
    db.commit()
    ids = {
        "category": category.id,
        "connection": connection.id,
        "f64": f64.id,
        "fs16": fs16.id,
    }
    db.close()
    try:
        yield engine, Session, ids
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _load(db, ids):
    category = db.get(InstrumentCategory, ids["category"])
    connection = db.get(InstrumentConnection, ids["connection"])
    f64 = db.get(InstrumentModel, ids["f64"])
    fs16 = db.get(InstrumentModel, ids["fs16"])
    return category, connection, f64, fs16


def _save(db, ids, *, target: str, endpoint: str, controller: str, notes: str,
          connection_params: dict, parsed_controller_ip: str, parsed_port: int | None):
    """在一个会话里调 save_* 并提交；current_model 恒取品类当前 selected_model_id。"""

    category, connection, f64, fs16 = _load(db, ids)
    models = {"f64": f64, "fs16": fs16}
    current = None
    if category.selected_model_id is not None:
        current = db.get(InstrumentModel, category.selected_model_id)
    save_channel_emulator_model_preset(
        category=category,
        current_model=current,
        target_model=models[target],
        connection=connection,
        endpoint=endpoint,
        controller=controller,
        notes=notes,
        connection_params=connection_params,
        parsed_controller_ip=parsed_controller_ip,
        parsed_port=parsed_port,
    )
    db.commit()


# ---------------------------------------------------------------------------
# 门 1：preset 模型 —— frozen / extra=forbid / 空 endpoint 拒 / 无 adapter_profile 槽
# ---------------------------------------------------------------------------


def test_preset_is_frozen_forbids_extra_fields_and_rejects_blank_endpoint():
    model_id = uuid4()
    preset = ChannelEmulatorModelPreset.model_validate(
        {
            "schema_version": 1,
            "model_id": str(model_id),
            "endpoint": "  192.168.100.21:3334  ",
            "controller": " socket ",
            "notes": " 现场 F64 ",
            "connection_params": _f64_params(),
        }
    )
    assert preset.model_id == model_id
    assert preset.endpoint == "192.168.100.21:3334"
    assert preset.controller == "socket" and preset.notes == "现场 F64"

    # frozen：赋值必须抛（变异：去掉 frozen=True → 这里不抛 → 红）
    with pytest.raises(ValidationError):
        preset.endpoint = "10.0.0.1:1"  # type: ignore[misc]
    assert preset.endpoint == "192.168.100.21:3334"

    # extra=forbid：多字段拒
    with pytest.raises(ValidationError):
        ChannelEmulatorModelPreset.model_validate(
            {**preset.model_dump(mode="json"), "unexpected": True}
        )

    # 空 endpoint 拒
    with pytest.raises(ValidationError):
        ChannelEmulatorModelPreset.model_validate(
            {**preset.model_dump(mode="json"), "endpoint": "   "}
        )

    # JSON-safe：model_id 序列化成 str，整份可 json.dumps
    dumped = preset.model_dump(mode="json")
    assert dumped["model_id"] == str(model_id)
    json.dumps(dumped)


def test_preset_has_no_adapter_profile_slot_and_exactly_the_designed_fields():
    """设计稿 §2：CE 无 profile 层 —— 字段集恰好是这六个，别悄悄长出 profile 槽。"""

    assert set(ChannelEmulatorModelPreset.model_fields) == {
        "schema_version",
        "model_id",
        "endpoint",
        "controller",
        "notes",
        "connection_params",
    }


def test_server_owned_preset_map_has_dedicated_storage_and_no_write_field():
    column = InstrumentConnection.__table__.c.channel_emulator_model_presets
    assert column.nullable is True
    # 服务端持有：前端连接更新 schema 不得长出直写该 map 的字段
    assert "channel_emulator_model_presets" not in FEConnectionUpdate.model_fields


# ---------------------------------------------------------------------------
# 门 2 / 3 / 4：原子保存
# ---------------------------------------------------------------------------


def test_switch_save_leaves_other_models_preset_bytes_untouched(ce_db):
    """门 2：先存 F64，再切到 FS16 保存 → F64 那项逐字节不变。

    额外钉死「已存过就不重新快照」：存完 F64 后把活动连接 notes 直接改掉（模拟未保存的
    活动侧改动），切到 FS16 时 F64 preset 仍是保存时那份，不是活动侧现值。
    变异：保存时整张 map 重写（只留 target 键 / 重新快照全部）→ 红。
    """

    engine, Session, ids = ce_db
    with Session() as db:
        _save(
            db, ids, target="f64", endpoint=F64_ENDPOINT, controller="socket",
            notes="保存时的 F64", connection_params=_f64_params(),
            parsed_controller_ip="192.168.100.21", parsed_port=3334,
        )
    with Session() as db:
        _category, connection, _f64, _fs16 = _load(db, ids)
        f64_saved = _canonical(connection.channel_emulator_model_presets[str(ids["f64"])])
        connection.notes = "活动侧未保存的改动"
        db.commit()

    with Session() as db:
        _save(
            db, ids, target="fs16", endpoint=FS16_ENDPOINT, controller="visa",
            notes="FS16", connection_params={"timeout_sec": 10},
            parsed_controller_ip="192.168.100.22", parsed_port=None,
        )

    with Session() as db:
        category, connection, _f64, _fs16 = _load(db, ids)
        presets = connection.channel_emulator_model_presets
        assert set(presets) == {str(ids["f64"]), str(ids["fs16"])}
        assert _canonical(presets[str(ids["f64"])]) == f64_saved
        assert presets[str(ids["f64"])]["notes"] == "保存时的 F64"
        # 目标投影成活动连接字段
        assert category.selected_model_id == ids["fs16"]
        assert connection.endpoint == FS16_ENDPOINT
        assert connection.controller_ip == "192.168.100.22"
        assert connection.port is None
        assert connection.protocol == "visa"
        assert connection.notes == "FS16"
        assert connection.connection_params == {"timeout_sec": 10}
        assert presets[str(ids["fs16"])]["connection_params"] == {"timeout_sec": 10}


def test_switch_save_snapshots_unsaved_active_model_with_its_channel_models(ce_db):
    """门 3：从未存过 F64、活动连接是 F64、切到 FS16 保存 → map 里出现 F64 快照，
    且快照的 connection_params 与活动连接逐字节相等（含 available_channel_models）。
    变异：删快照分支 → 红。
    """

    engine, Session, ids = ce_db
    with Session() as db:
        _save(
            db, ids, target="fs16", endpoint=FS16_ENDPOINT, controller="visa",
            notes="FS16", connection_params={"timeout_sec": 10},
            parsed_controller_ip="192.168.100.22", parsed_port=None,
        )
    with Session() as db:
        _category, connection, _f64, _fs16 = _load(db, ids)
        presets = connection.channel_emulator_model_presets
        assert set(presets) == {str(ids["f64"]), str(ids["fs16"])}
        snapshot = presets[str(ids["f64"])]
        assert snapshot["endpoint"] == F64_ENDPOINT
        assert snapshot["controller"] == "socket"
        assert snapshot["notes"] == "现场 F64"
        assert _canonical(snapshot["connection_params"]) == _canonical(_f64_params())
        assert snapshot["connection_params"]["available_channel_models"] == (
            _f64_params()["available_channel_models"]
        )


def test_available_channel_models_round_trips_into_preset_and_runtime_keys_empty(ce_db):
    """门 4（设计稿 §4 门 3 反向版）：保存后 preset 里 available_channel_models 与传入
    逐字节相等；剔除集合为空 frozenset；persistent_* 是恒等。
    变异：把 available_channel_models 加进剔除集合 → 三处一起红。
    """

    assert isinstance(CHANNEL_EMULATOR_RUNTIME_CONNECTION_PARAM_KEYS, frozenset)
    assert CHANNEL_EMULATOR_RUNTIME_CONNECTION_PARAM_KEYS == frozenset()
    params = _f64_params()
    assert persistent_channel_emulator_connection_params(params) == params
    assert persistent_channel_emulator_connection_params(None) == {}

    engine, Session, ids = ce_db
    with Session() as db:
        _save(
            db, ids, target="f64", endpoint=F64_ENDPOINT, controller="socket",
            notes="F64", connection_params=params,
            parsed_controller_ip="192.168.100.21", parsed_port=3334,
        )
    with Session() as db:
        _category, connection, _f64, _fs16 = _load(db, ids)
        saved = connection.channel_emulator_model_presets[str(ids["f64"])]
        assert _canonical(saved["connection_params"]["available_channel_models"]) == (
            _canonical(params["available_channel_models"])
        )
        assert _canonical(saved["connection_params"]) == _canonical(params)
        assert _canonical(connection.connection_params) == _canonical(params)


# ---------------------------------------------------------------------------
# 门 5：剔除集合里的每个键都必须在 app/hal/ 的 connect() 路径上有写入点（判定器 + 自测）
# ---------------------------------------------------------------------------


def _hal_connect_path_written_keys(source: str) -> set[str]:
    """从一份源码派生「在名字含 connect 的函数体内被写入的字符串键」集合。

    算写入的三种形态：``x["k"] = …`` 下标赋值、``{"k": …}`` 字典字面量、``x.setdefault("k", …)``。
    只读（``config.get("k")``）与不在 connect 函数里的写都**不算**。
    有意偏宽（函数名含 connect 即算路径）：门的职责是拒掉**没有**连接期写入点的键，
    偏宽只会少误伤，不会放过错分类的键。
    """

    tree = ast.parse(source)
    written: set[str] = set()

    def _collect(body_node: ast.AST) -> None:
        for node in ast.walk(body_node):
            if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if (
                        isinstance(target, ast.Subscript)
                        and isinstance(target.slice, ast.Constant)
                        and isinstance(target.slice.value, str)
                    ):
                        written.add(target.slice.value)
            elif isinstance(node, ast.Dict):
                for key in node.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        written.add(key.value)
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "setdefault"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                written.add(node.args[0].value)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
            "connect" in node.name
        ):
            _collect(node)
    return written


def _hal_connect_path_written_keys_repo_wide() -> set[str]:
    keys: set[str] = set()
    for path in sorted((API_SERVICE_ROOT / "app" / "hal").rglob("*.py")):
        keys |= _hal_connect_path_written_keys(path.read_text(encoding="utf-8"))
    return keys


def test_runtime_key_judge_detects_connect_writes_and_ignores_reads_and_other_writes():
    """判定器自测（正反两向）：能抓 connect 路径的三种写法；不把只读 / 非 connect 写 /
    模块级写 / 文档字符串里的键误判成写入点。"""

    positive = (
        "class Drv:\n"
        "    async def connect(self):\n"
        "        params['detected_sub'] = 1\n"
        "        self.cfg.setdefault('detected_default', 2)\n"
        "        return {'detected_literal': 3}\n"
        "    def _silent_reconnect_visa(self):\n"
        "        self._params['detected_reconnect'] = True\n"
    )
    found = _hal_connect_path_written_keys(positive)
    assert {
        "detected_sub",
        "detected_default",
        "detected_literal",
        "detected_reconnect",
    } <= found

    negative = (
        "'''docstring mentions connection_params[\"available_channel_models\"]'''\n"
        "params['module_level'] = 1\n"
        "def add_entry(params):\n"
        "    params['available_channel_models'] = []\n"
        "class Drv:\n"
        "    async def connect(self):\n"
        "        '''connect docstring: available_channel_models'''\n"
        "        models = config.get('available_channel_models') or []\n"
        "        return bool(models)\n"
    )
    assert _hal_connect_path_written_keys(negative) == set()


def test_every_runtime_connection_param_key_has_a_hal_connect_path_writer():
    """真门：CHANNEL_EMULATOR_RUNTIME_CONNECTION_PARAM_KEYS 里每个键都必须在 app/hal/
    的 connect() 路径上有写入点，否则它不是「运行期观测」而是操作员配置资产被错分类
    （available_channel_models 的写方在 API / 服务层 —— 外审 #451 R2 抓过一次）。
    今天集合为空 = 恒过；变异：加 "available_channel_models" → 红。
    """

    hal_written = _hal_connect_path_written_keys_repo_wide()
    for key in sorted(CHANNEL_EMULATOR_RUNTIME_CONNECTION_PARAM_KEYS):
        assert key in hal_written, (
            f"{key!r} 被列为 CE 运行期连接参数，但 app/hal/ 里没有任何 connect() 路径写入它 —— "
            "它是操作员配置资产，不该从 preset 里剔除"
        )


# ---------------------------------------------------------------------------
# 门 6：parse_* 对坏输入大声失败（中文 ValueError），不静默丢项
# ---------------------------------------------------------------------------


def test_parse_rejects_malformed_input_loudly_in_chinese_and_never_drops_items():
    good_id = uuid4()
    good = {
        "schema_version": 1,
        "model_id": str(good_id),
        "endpoint": F64_ENDPOINT,
        "controller": "socket",
        "notes": "",
        "connection_params": _f64_params(),
    }
    assert parse_channel_emulator_model_presets(None) == {}
    parsed = parse_channel_emulator_model_presets({str(good_id): good})
    assert set(parsed) == {str(good_id)}
    assert parsed[str(good_id)].connection_params == _f64_params()

    # 非 dict
    with pytest.raises(ValueError, match="信道仿真器"):
        parse_channel_emulator_model_presets([good])

    # 坏项（空 endpoint）混在好项里：整张 map 必须失败，不能悄悄只返回好项
    bad_id = uuid4()
    with pytest.raises(ValueError, match="信道仿真器") as excinfo:
        parse_channel_emulator_model_presets(
            {
                str(good_id): good,
                str(bad_id): {**good, "model_id": str(bad_id), "endpoint": ""},
            }
        )
    assert str(bad_id) in str(excinfo.value)

    # 键与 model_id 不一致
    with pytest.raises(ValueError, match="信道仿真器"):
        parse_channel_emulator_model_presets({"not-the-id": good})

    # 32 位 hex（SQLite 裸存储形态）当键也不行 —— 键必须是 str(UUID) 规范形
    with pytest.raises(ValueError, match="信道仿真器"):
        parse_channel_emulator_model_presets({good_id.hex: good})


# ---------------------------------------------------------------------------
# 门 7：迁移 —— 真跑 upgrade / downgrade（幂等、回填保留 available_channel_models、双向）
# ---------------------------------------------------------------------------


def _migration_module():
    spec = importlib.util.spec_from_file_location("mig_p2_58_2", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _run_migration(engine, fn) -> None:
    """用 MigrationContext + Operations.context 让迁移模块里的 ``alembic.op`` 代理生效。"""

    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            fn()
        conn.commit()


def _column_names(engine) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns("instrument_connections")}


def _stored_presets(engine, connection_id: UUID):
    with engine.connect() as conn:
        raw = conn.execute(
            text(
                "SELECT channel_emulator_model_presets FROM instrument_connections "
                "WHERE id = :id"
            ),
            {"id": connection_id.hex},
        ).scalar_one()
    return json.loads(raw) if isinstance(raw, str) else raw


def _add_base_station_row(engine, Session):
    """一行 baseStation 连接：有选型、有 endpoint，但品类不对 → 回填必须不碰它。"""

    with Session() as db:
        category = InstrumentCategory(
            id=uuid4(),
            category_key="baseStation",
            category_name="基站模拟器",
            driver_mode="mock",
            is_active=True,
        )
        model = InstrumentModel(
            id=uuid4(),
            category_id=category.id,
            vendor="Keysight",
            model="UXM 5G E7515B",
            capabilities={},
            is_available=True,
        )
        category.selected_model_id = model.id
        connection = InstrumentConnection(
            id=uuid4(),
            category_id=category.id,
            endpoint="192.168.1.112",
            protocol="socket",
            connection_params={"timeout_ms": 30000},
                created_by="test",
        )
        db.add_all([category, model, connection])
        db.commit()
        return connection.id


def test_migration_upgrade_backfills_first_preset_keeping_channel_models_and_is_idempotent(ce_db):
    """create_all 之后列已在（greenfield 路径）：upgrade 只回填。回填出的 F64 preset 里
    connection_params（含 available_channel_models）与活动连接逐字节相等，键是 str(UUID)
    规范形（SQLite 裸存储是 32-hex，PG 带连字符 —— 迁移必须两边都对），且能被
    parse_channel_emulator_model_presets 消费；二次 upgrade 不炸也不改字节；非 CE 行不回填。
    变异：回填 ``params.pop("available_channel_models", None)`` → 红。
    """

    engine, Session, ids = ce_db
    bs_connection_id = _add_base_station_row(engine, Session)
    module = _migration_module()
    assert module.down_revision == "f2a4c6e8b0d1"

    _run_migration(engine, module.upgrade)
    stored = _stored_presets(engine, ids["connection"])
    assert set(stored) == {str(ids["f64"])}
    preset = stored[str(ids["f64"])]
    assert preset["schema_version"] == 1
    assert preset["model_id"] == str(ids["f64"])
    assert preset["endpoint"] == F64_ENDPOINT
    assert preset["controller"] == "socket"
    assert preset["notes"] == "现场 F64"
    assert _canonical(preset["connection_params"]) == _canonical(_f64_params())
    assert preset["connection_params"]["available_channel_models"] == (
        _f64_params()["available_channel_models"]
    )
    parsed = parse_channel_emulator_model_presets(stored)
    assert parsed[str(ids["f64"])].connection_params == _f64_params()
    assert _stored_presets(engine, bs_connection_id) is None

    first_bytes = _canonical(stored)
    _run_migration(engine, module.upgrade)
    assert _canonical(_stored_presets(engine, ids["connection"])) == first_bytes
    assert _stored_presets(engine, bs_connection_id) is None


def test_migration_downgrade_drops_column_and_upgrade_readds_with_backfill(ce_db):
    """brownfield 路径：downgrade 掉列（两次不炸）→ upgrade 真走 add_column + 回填 →
    列回来、preset 回来且仍带 available_channel_models。"""

    engine, Session, ids = ce_db
    module = _migration_module()
    assert "channel_emulator_model_presets" in _column_names(engine)

    _run_migration(engine, module.downgrade)
    assert "channel_emulator_model_presets" not in _column_names(engine)
    _run_migration(engine, module.downgrade)  # 双守门：列已不在也不炸
    assert "channel_emulator_model_presets" not in _column_names(engine)

    _run_migration(engine, module.upgrade)
    assert "channel_emulator_model_presets" in _column_names(engine)
    stored = _stored_presets(engine, ids["connection"])
    assert set(stored) == {str(ids["f64"])}
    assert _canonical(stored[str(ids["f64"])]["connection_params"]) == _canonical(
        _f64_params()
    )
    parse_channel_emulator_model_presets(stored)

    _run_migration(engine, module.upgrade)  # 列已在 + 行非 NULL：纯 no-op
    assert _canonical(_stored_presets(engine, ids["connection"])) == _canonical(stored)


def test_migration_skips_connections_without_endpoint_or_selected_model(ce_db):
    """回填的三个前置条件缺一个都不回填（留 NULL，让首次切型号的快照分支补）。"""

    engine, Session, ids = ce_db
    module = _migration_module()
    with Session() as db:
        category, connection, _f64, _fs16 = _load(db, ids)
        connection.endpoint = "   "
        db.commit()
    _run_migration(engine, module.upgrade)
    assert _stored_presets(engine, ids["connection"]) is None

    with Session() as db:
        category, connection, _f64, _fs16 = _load(db, ids)
        connection.endpoint = F64_ENDPOINT
        category.selected_model_id = None
        db.commit()
    _run_migration(engine, module.upgrade)
    assert _stored_presets(engine, ids["connection"]) is None
