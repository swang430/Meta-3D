"""P2-41 清理片的行为门（Schema Review R1/R2/R3/R5）。

守什么：迁移 a3e5c7d9f1b2 的 DELETE 判据必须**只**清演示期数据，绝不误删：
- 现场 2026-07-03 的 brownfield NULL 行（use_mock 列 2026-08-11 才加，
  现场 real 数据在任何库里都是 NULL —— 裸 `use_mock IS NULL` 会误删它们）；
- 显式 use_mock=False 的 real 行；
- 显式 use_mock=True 的行（provenance 正常工作的记录，R5 只清 NULL 演示行）。

真实生效端：测试执行的 SQL 由迁移模块的同一构造函数产出（单源），
不是测试自己抄一份判据。SQLite 内存库上建 models 表后逐条执行。

R3 复活门：ProbeConfiguration model 与 4 个 schema 类已删，防止悄悄回来。
"""
import importlib.util
import uuid
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

_MIG_PATH = (Path(__file__).parent.parent / "alembic" / "versions"
             / "a3e5c7d9f1b2_p2_41_schema_cleanup.py")


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_p2_41", _MIG_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def db():
    """SQLite 内存库，仅建本片涉及的表（models metadata 单源）。"""
    from app.db.database import Base
    import app.models  # noqa: F401  确保全部模型注册

    engine = create_engine("sqlite:///:memory:")
    tables = [
        Base.metadata.tables[n] for n in (
            "probe_amplitude_calibrations", "probe_phase_calibrations",
            "probe_polarization_calibrations", "link_calibrations",
            "probe_path_loss_calibrations", "probe_calibration_validity",
        )
    ]
    Base.metadata.create_all(engine, tables=tables)
    with engine.begin() as conn:
        yield conn


def _insert(conn, table, **kw):
    cols = ", ".join(kw)
    marks = ", ".join(f":{k}" for k in kw)
    conn.execute(text(f"INSERT INTO {table} ({cols}) VALUES ({marks})"), kw)


# 两张表的非空无默认列（按 models 真实约束）补齐固定值
_AMP_REQUIRED = dict(polarization="V", frequency_points_mhz="[3500.0]",
                     tx_gain_dbi=8.0, rx_gain_dbi=8.0,
                     tx_gain_uncertainty_db=0.5, rx_gain_uncertainty_db=0.5,
                     calibrated_at=datetime(2026, 8, 20),
                     valid_until=datetime(2027, 1, 1))
_PL_REQUIRED = dict(sgh_model="SGH-3500", sgh_gain_dbi=15.0,
                    calibrated_at=datetime(2026, 8, 20),
                    valid_until=datetime(2027, 1, 1))


_DEMO = datetime(2026, 5, 1)        # 演示期（围栏内，删）
_ONSITE = datetime(2026, 7, 3)      # 现场 brownfield（围栏外 NULL，留）
_LOCAL_0702 = datetime(2026, 7, 2)  # 本地演练（围栏外但 mock 指纹，删）
_NEW = datetime(2026, 8, 20)        # provenance 时代（显式值，留）


class TestFencedDelete:
    """门 1：时间围栏判据的选择性（amplitude 表代表 6 张同构表）。"""

    def test_fence_keeps_onsite_brownfield_and_explicit_rows(self, db):
        mig = _load_migration()
        rows = {
            "demo_null": (_DEMO, None),        # 删
            "onsite_null": (_ONSITE, None),    # 留（现场 brownfield）
            "new_real": (_NEW, False),         # 留（显式 real）
            "new_mock": (_NEW, True),          # 留（显式 mock，R5 不清）
        }
        ids = {}
        for name, (ts, mock) in rows.items():
            ids[name] = str(uuid.uuid4())
            _insert(db, "probe_amplitude_calibrations",
                    id=ids[name], probe_id=1, created_at=ts, use_mock=mock,
                    **_AMP_REQUIRED)
        db.execute(text(mig.fenced_delete_sql("probe_amplitude_calibrations")))
        left = {r[0] for r in db.execute(
            text("SELECT id FROM probe_amplitude_calibrations"))}
        assert left == {ids["onsite_null"], ids["new_real"], ids["new_mock"]}, \
            "时间围栏必须只删演示期 NULL 行"


class TestPathLossFingerprint:
    """门 2：path_loss 的 mock 指纹条件补上围栏外演练行，且不伤 real。"""

    def test_fingerprint_catches_0702_but_not_onsite_real(self, db):
        mig = _load_migration()
        cases = {
            # (created_at, use_mock, vna_model) → 预期
            "demo": (_DEMO, None, "Mock VNA", False),          # 删（围栏）
            "local_0702": (_LOCAL_0702, None, "Mock VNA", False),  # 删（指纹）
            "onsite_real_null": (_ONSITE, None, "E5071C", True),   # 留
            "new_real": (_NEW, False, "E5071C", True),             # 留
            # 显式 mock × 指纹：R5 只清 NULL，显式 True 必须留 ——
            # 括号优先级变异 (fence OR fingerprint 提出括号) 在这红
            "explicit_mock_fp": (_NEW, True, "Mock VNA", True),
        }
        ids = {}
        for name, (ts, mock, vna, _) in cases.items():
            ids[name] = str(uuid.uuid4())
            _insert(db, "probe_path_loss_calibrations",
                    id=ids[name], chamber_id=str(uuid.uuid4()),
                    frequency_mhz=3500.0, probe_path_losses="{}",
                    created_at=ts, use_mock=mock, vna_model=vna,
                    **_PL_REQUIRED)
        db.execute(text(mig.path_loss_delete_sql()))
        left = {r[0] for r in db.execute(
            text("SELECT id FROM probe_path_loss_calibrations"))}
        expect = {ids[n] for n, c in cases.items() if c[3]}
        assert left == expect, "指纹条件不得误删现场/real 行"


class TestValidityOrphans:
    """门 3：validity 只删悬空引用行，引用仍存在的行必须幸存。"""

    def test_only_dangling_refs_deleted(self, db):
        mig = _load_migration()
        keep_cal = str(uuid.uuid4())
        _insert(db, "probe_amplitude_calibrations",
                id=keep_cal, probe_id=1, created_at=_NEW, use_mock=False,
                **_AMP_REQUIRED)
        _insert(db, "probe_calibration_validity",
                probe_id=1, amplitude_calibration_id=keep_cal)   # 留
        _insert(db, "probe_calibration_validity",
                probe_id=2, amplitude_calibration_id=str(uuid.uuid4()))  # 悬空，删
        _insert(db, "probe_calibration_validity", probe_id=3)    # 全 NULL 引用，留
        db.execute(text(mig.validity_orphan_delete_sql()))
        left = {r[0] for r in db.execute(
            text("SELECT probe_id FROM probe_calibration_validity"))}
        assert left == {1, 3}, "只有悬空引用行可删"


class TestNoProvenanceFence:
    """门 4（内审 F1）：无来源列表的时间围栏选择性 —— M8（丢 WHERE 全删）在这红。"""

    def test_baselines_fence_keeps_post_governance_rows(self, db):
        from app.db.database import Base
        Base.metadata.create_all(db.engine,
                                 tables=[Base.metadata.tables["calibration_baselines"]])
        mig = _load_migration()
        base = dict(chamber_id=str(uuid.uuid4()), calibration_type="phase",
                    frequency_mhz=3500.0, reference_channel_id="ch1",
                    delta_matrix="{}", baseline_date=_NEW,
                    valid_until=datetime(2027, 1, 1))
        demo_id, new_id = str(uuid.uuid4()), str(uuid.uuid4())
        _insert(db, "calibration_baselines", id=demo_id, created_at=_DEMO, **base)
        _insert(db, "calibration_baselines", id=new_id, created_at=_NEW, **base)
        db.execute(text(mig.no_provenance_delete_sql("calibration_baselines")))
        left = {r[0] for r in db.execute(text("SELECT id FROM calibration_baselines"))}
        assert left == {new_id}, "时间围栏必须保留治理基线后的行"


class TestUpgradeWiring:
    """门 5（内审 F1）：upgrade() 必须真的调用全部四个 DELETE 构造 ——
    M6（把 DELETE 循环删成 pass）在这红。不变量档：构造函数正确性由
    门 1–4 行为断言守，这里守「构造被 upgrade 布线」。"""

    def test_upgrade_body_wires_all_delete_builders(self):
        import ast
        src = _MIG_PATH.read_text()
        tree = ast.parse(src)
        up = next(n for n in tree.body
                  if isinstance(n, ast.FunctionDef) and n.name == "upgrade")
        called = {n.func.id for n in ast.walk(up)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        for builder in ("fenced_delete_sql", "path_loss_delete_sql",
                        "no_provenance_delete_sql", "validity_orphan_delete_sql"):
            assert builder in called, f"upgrade() 未调用 {builder} —— DELETE 布线丢失"
        # DROP 布线同守
        attrs = {n.func.attr for n in ast.walk(up)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        assert "drop_table" in attrs and "execute" in attrs


class TestR3NoResurrection:
    """R3 复活门：删掉的 model / schema 类不得回归。"""

    def test_probe_configuration_model_gone(self):
        import app.models.probe as m
        assert not hasattr(m, "ProbeConfiguration")

    def test_probe_configuration_schemas_gone(self):
        import app.schemas.probe as s
        for name in ("ProbeConfigurationCreate", "ProbeConfigurationUpdate",
                     "ProbeConfigurationResponse",
                     "ProbeConfigurationListResponse"):
            assert not hasattr(s, name), f"{name} 不得复活"
