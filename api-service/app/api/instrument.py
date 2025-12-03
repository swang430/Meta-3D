"""Instrument API endpoints"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
import logging

from app.db.database import get_db
from app.models.instrument import InstrumentCategory, InstrumentModel, InstrumentConnection
from app.schemas.instrument import (
    InstrumentCatalogResponse,
    InstrumentCatalogItem,
    InstrumentCategoryResponse,
    UpdateInstrumentCategoryRequest
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/instruments/catalog", response_model=InstrumentCatalogResponse)
def get_instrument_catalog(db: Session = Depends(get_db)):
    """Get complete instrument catalog"""
    try:
        categories = db.query(InstrumentCategory).order_by(
            InstrumentCategory.display_order
        ).all()

        catalog = []
        for category in categories:
            models = db.query(InstrumentModel).filter(
                InstrumentModel.category_id == category.id
            ).order_by(InstrumentModel.display_order).all()

            selected_model = None
            if category.selected_model_id:
                selected_model = db.query(InstrumentModel).filter(
                    InstrumentModel.id == category.selected_model_id
                ).first()

            connection = db.query(InstrumentConnection).filter(
                InstrumentConnection.category_id == category.id
            ).first()

            catalog.append(InstrumentCatalogItem(
                category=category,
                available_models=models,
                selected_model=selected_model,
                connection=connection
            ))

        return InstrumentCatalogResponse(
            total_categories=len(categories),
            catalog=catalog
        )

    except Exception as e:
        logger.error(f"Error fetching instrument catalog: {e}")
        return InstrumentCatalogResponse(total_categories=0, catalog=[])


@router.put("/instruments/{category_key}", response_model=InstrumentCategoryResponse)
def update_instrument_category(
    category_key: str,
    request: UpdateInstrumentCategoryRequest,
    db: Session = Depends(get_db)
):
    """Update instrument category selection and connection"""
    category = db.query(InstrumentCategory).filter(
        InstrumentCategory.category_key == category_key
    ).first()

    if not category:
        raise HTTPException(404, f"Category '{category_key}' not found")

    # Update selected model
    if request.selected_model_id is not None:
        # Verify model exists and belongs to this category
        model = db.query(InstrumentModel).filter(
            InstrumentModel.id == request.selected_model_id,
            InstrumentModel.category_id == category.id
        ).first()

        if not model:
            raise HTTPException(400, "Invalid model ID for this category")

        category.selected_model_id = request.selected_model_id

    # Update or create connection
    if request.connection:
        connection = db.query(InstrumentConnection).filter(
            InstrumentConnection.category_id == category.id
        ).first()

        if not connection:
            connection = InstrumentConnection(
                category_id=category.id,
                created_by="system"
            )
            db.add(connection)

        for key, value in request.connection.dict(exclude_unset=True).items():
            if value is not None:
                # TODO: Encrypt password if provided
                setattr(connection, key, value)

    db.commit()
    db.refresh(category)

    return category
