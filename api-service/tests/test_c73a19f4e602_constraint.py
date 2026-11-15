"""验证通信制式约束迁移：已有约束不重建，错误定义不得静默覆盖。"""
import importlib.util
import os
from pathlib import Path
import uuid

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import sqlalchemy as sa

from app.models.standard_channel import StandardChannelDefinition


_TABLE = "standard_channel_definitions"
_CHECK = "ck_scd_rat_channel_identity"
_EXPECTED = str(next(
    c for c in StandardChannelDefinition.__table__.constraints
    if c.name == _CHECK
).sqltext)


@pytest.fixture(params=["sqlite", "postgresql"])
def connection(request):
    url = "sqlite://"
    if request.param == "postgresql":
        url = os.environ.get("DEL02_TEST_DATABASE_URL")
        if not url:
            pytest.skip("未提供独立 PostgreSQL 测试库")
    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            transaction = conn.begin()
            if request.param == "postgresql":
                schema = "del02_constraint_" + uuid.uuid4().hex
                conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
                conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            try:
                yield conn
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def _upgrade(conn):
    path = Path(__file__).resolve().parents[1] / "alembic/versions/c73a19f4e602_add_rat_to_standard_channels.py"
    spec = importlib.util.spec_from_file_location("rat_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with Operations.context(MigrationContext.configure(conn)):
        migration.upgrade()


def _create(conn, check=None, legacy=False):
    columns = [sa.Column("id", sa.Integer, primary_key=True),
               sa.Column("arfcn", sa.Integer, nullable=not legacy)]
    if not legacy:
        columns += [sa.Column("radio_technology", sa.String(16), nullable=False),
                    sa.Column("channel_kind", sa.String(32), nullable=False),
                    sa.Column("lte_dl_earfcn", sa.Integer)]
    if check is not None:
        columns.append(sa.CheckConstraint(check, name=_CHECK))
    sa.Table(_TABLE, sa.MetaData(), *columns).create(conn)


def test_existing_matching_constraint_is_retained(connection):
    _create(connection, _EXPECTED)
    before = sa.inspect(connection).get_check_constraints(_TABLE)
    _upgrade(connection)
    assert sa.inspect(connection).get_check_constraints(_TABLE) == before


@pytest.mark.parametrize("wrong", [
    "arfcn IS NOT NULL",
    # 只移动括号，去掉所有括号后与正确表达式相同，但含义不同。
    "(radio_technology = 'nr5g' AND channel_kind = 'nr_arfcn' "
    "AND arfcn IS NOT NULL AND lte_dl_earfcn IS NULL OR "
    "radio_technology = 'lte') AND channel_kind = 'lte_dl_earfcn' "
    "AND arfcn IS NULL AND lte_dl_earfcn IS NOT NULL",
])
def test_wrong_same_name_fails_without_replacing_constraint(connection, wrong):
    _create(connection, wrong)
    before = sa.inspect(connection).get_check_constraints(_TABLE)
    with pytest.raises(RuntimeError, match=_CHECK):
        _upgrade(connection)
    assert sa.inspect(connection).get_check_constraints(_TABLE) == before


def test_legacy_nr_row_and_new_constraint_are_preserved(connection):
    _create(connection, legacy=True)
    connection.execute(sa.text(f"INSERT INTO {_TABLE} (id, arfcn) VALUES (1, 640000)"))
    _upgrade(connection)
    row = connection.execute(sa.text(
        f"SELECT arfcn, radio_technology, channel_kind, lte_dl_earfcn FROM {_TABLE} WHERE id=1"
    )).one()
    assert tuple(row) == (640000, "nr5g", "nr_arfcn", None)
    assert [c['name'] for c in sa.inspect(connection).get_check_constraints(_TABLE)] == [_CHECK]
    connection.execute(sa.text(
        f"INSERT INTO {_TABLE} VALUES (2, NULL, 'lte', 'lte_dl_earfcn', 100)"
    ))
    with pytest.raises(sa.exc.IntegrityError):
        with connection.begin_nested():
            connection.execute(sa.text(
                f"INSERT INTO {_TABLE} VALUES (3, 640000, 'lte', 'lte_dl_earfcn', 100)"
            ))
