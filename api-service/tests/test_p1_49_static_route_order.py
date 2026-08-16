"""P1-49: static GET routes must precede sibling UUID routes."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app


_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=_engine,
)


@pytest.fixture
def isolated_client():
    Base.metadata.create_all(bind=_engine)
    previous = app.dependency_overrides.get(get_db)

    def _override_get_db():
        session = _TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous
        Base.metadata.drop_all(bind=_engine)


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/calibration/channel/temporal/latest",
        "/api/v1/topologies/default",
    ],
)
def test_static_route_reaches_handler_instead_of_uuid_validation(
    isolated_client,
    path,
):
    response = isolated_client.get(path)

    assert response.status_code == 404
    assert "uuid_parsing" not in response.text


@pytest.mark.parametrize(
    "path",
    [
        f"/api/v1/calibration/channel/temporal/{uuid4()}",
        f"/api/v1/topologies/{uuid4()}",
    ],
)
def test_uuid_detail_routes_remain_reachable(isolated_client, path):
    response = isolated_client.get(path)

    assert response.status_code == 404
    assert "uuid_parsing" not in response.text
