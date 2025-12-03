"""Test Sequence API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from app.db.database import get_db
from app.schemas.test_plan import (
    TestSequenceResponse,
    TestSequenceListResponse,
    TestSequenceCategoriesResponse,
)
from app.services.test_plan_service import TestSequenceService

router = APIRouter(prefix="/test-sequences", tags=["Test Sequence Library"])


@router.get("", response_model=TestSequenceListResponse)
def get_test_sequences(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    category: Optional[str] = None,
    is_public: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """
    Get test sequences with filters

    Parameters:
    - skip: Number of records to skip (pagination)
    - limit: Maximum number of records to return
    - category: Filter by category
    - is_public: Filter by public/private status
    """
    try:
        service = TestSequenceService()
        sequences, total = service.get_sequences(
            db=db,
            skip=skip,
            limit=limit,
            category=category,
            is_public=is_public
        )
        return TestSequenceListResponse(items=sequences)
    except Exception as e:
        # Database unavailable - return empty list
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Database unavailable for test sequences: {e}")
        return TestSequenceListResponse(items=[])


@router.get("/categories", response_model=TestSequenceCategoriesResponse)
def get_sequence_categories(db: Session = Depends(get_db)):
    """Get all sequence categories"""
    try:
        service = TestSequenceService()
        categories = service.get_categories(db)
        return TestSequenceCategoriesResponse(categories=categories)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Database unavailable for categories: {e}")
        return TestSequenceCategoriesResponse(categories=[])


@router.get("/popular", response_model=TestSequenceListResponse)
def get_popular_sequences(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """Get most popular test sequences"""
    try:
        service = TestSequenceService()
        sequences = service.get_popular_sequences(db, limit=limit)
        return TestSequenceListResponse(items=sequences)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Database unavailable for popular sequences: {e}")
        return TestSequenceListResponse(items=[])


@router.get("/{sequence_id}", response_model=TestSequenceResponse)
def get_test_sequence(
    sequence_id: UUID,
    db: Session = Depends(get_db)
):
    """Get a single test sequence by ID"""
    service = TestSequenceService()
    sequence = service.get_sequence(db, sequence_id)

    if not sequence:
        raise HTTPException(status_code=404, detail="Test sequence not found")

    return sequence
