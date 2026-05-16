"""Pins ``app/services/lab_resolution.py`` — shared LabProfile resolver
used by every flow with an optional ``lab_profile_id`` parameter.

Covers all five branches of `resolve_lab_profile`:
- explicit id, found and active   → returns it
- explicit id, not found           → ValueError
- explicit id, inactive            → ValueError
- no id, no active labs            → LabResolutionError(kind="none")
- no id, one active lab            → returns it (back-compat fallback)
- no id, two+ active labs          → LabResolutionError(kind="ambiguous")
  carrying the candidate list so the API layer can render an
  actionable 422.

The legacy `_resolve_lab_profile` raised plain ValueError for the
ambiguity case, which propagated to a 500. The structured exception
is the whole point of the refactor — pin it.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.lab_profile import LabProfile
from app.services.lab_resolution import (
    LabResolutionError,
    LabSummary,
    resolve_lab_profile,
)


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def _setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()


def _add_lab(db, *, name: str, active: bool = True) -> LabProfile:
    lab = LabProfile(id=uuid.uuid4(), name=name, is_active=active)
    db.add(lab)
    db.commit()
    db.refresh(lab)
    return lab


# ---------------------------------------------------------------------------
# Explicit lab_profile_id path
# ---------------------------------------------------------------------------

class TestExplicitId:
    def test_returns_lab_when_active(self, db):
        lab = _add_lab(db, name="explicit-active")
        result = resolve_lab_profile(db, lab.id)
        assert result.id == lab.id

    def test_raises_value_error_when_missing(self, db):
        with pytest.raises(ValueError, match="not found"):
            resolve_lab_profile(db, uuid.uuid4())

    def test_raises_value_error_when_inactive(self, db):
        lab = _add_lab(db, name="explicit-inactive", active=False)
        with pytest.raises(ValueError, match="inactive"):
            resolve_lab_profile(db, lab.id)


# ---------------------------------------------------------------------------
# Fallback path (lab_profile_id=None)
# ---------------------------------------------------------------------------

class TestFallbackPath:
    def test_one_active_lab_is_returned(self, db):
        """Back-compat: existing scripts that omit lab_profile_id and
        rely on the single-active lab keep working."""
        lab = _add_lab(db, name="solo-active")
        # also add an inactive one — must NOT count toward "active"
        _add_lab(db, name="ignored-inactive", active=False)
        result = resolve_lab_profile(db, None)
        assert result.id == lab.id

    def test_zero_active_raises_kind_none(self, db):
        # an inactive lab exists but shouldn't satisfy the fallback
        _add_lab(db, name="inactive-only", active=False)
        with pytest.raises(LabResolutionError) as exc_info:
            resolve_lab_profile(db, None)
        err = exc_info.value
        assert err.kind == "none"
        assert err.active_labs == []
        assert "No active LabProfile" in str(err)

    def test_two_active_raises_kind_ambiguous_with_candidates(self, db):
        """Codex-bait avoided: the API layer's 422 detail builds its
        picker from this candidate list, so verify both labs land
        in the right shape (id + name) and that the order is stable
        (sorted by name)."""
        lab_b = _add_lab(db, name="b-second")
        lab_a = _add_lab(db, name="a-first")
        with pytest.raises(LabResolutionError) as exc_info:
            resolve_lab_profile(db, None)
        err = exc_info.value
        assert err.kind == "ambiguous"
        assert len(err.active_labs) == 2
        # Sorted by name → "a-first" first, "b-second" second.
        assert err.active_labs[0] == LabSummary(id=lab_a.id, name="a-first")
        assert err.active_labs[1] == LabSummary(id=lab_b.id, name="b-second")
        # Message names both, so a developer reading a log can act.
        msg = str(err)
        assert "a-first" in msg
        assert "b-second" in msg
        assert str(lab_a.id) in msg
        assert str(lab_b.id) in msg

    def test_three_plus_active_still_ambiguous(self, db):
        """Smoke that the ambiguous path handles arbitrary cardinality,
        not just exactly 2."""
        for n in ("lab-x", "lab-y", "lab-z"):
            _add_lab(db, name=n)
        with pytest.raises(LabResolutionError) as exc_info:
            resolve_lab_profile(db, None)
        assert exc_info.value.kind == "ambiguous"
        assert len(exc_info.value.active_labs) == 3
