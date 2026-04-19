"""Instrument Pydantic schemas"""
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID


# ==================== Model Schemas ====================

class InstrumentModelBase(BaseModel):
    """Base instrument model schema"""
    vendor: str = Field(..., max_length=255)
    model: str = Field(..., max_length=255)
    full_name: Optional[str] = Field(None, max_length=500)
    capabilities: Dict[str, Any]
    datasheet_url: Optional[str] = Field(None, max_length=500)
    manual_url: Optional[str] = Field(None, max_length=500)
    display_order: int = Field(0, ge=0)
    is_available: bool = True
    notes: Optional[str] = None


class InstrumentModelCreate(InstrumentModelBase):
    """Request to create an instrument model"""
    category_id: UUID


class InstrumentModelUpdate(BaseModel):
    """Request to update an instrument model"""
    vendor: Optional[str] = Field(None, max_length=255)
    model: Optional[str] = Field(None, max_length=255)
    full_name: Optional[str] = Field(None, max_length=500)
    capabilities: Optional[Dict[str, Any]] = None
    datasheet_url: Optional[str] = Field(None, max_length=500)
    manual_url: Optional[str] = Field(None, max_length=500)
    display_order: Optional[int] = Field(None, ge=0)
    is_available: Optional[bool] = None
    notes: Optional[str] = None


class InstrumentModelResponse(InstrumentModelBase):
    """Instrument model response"""
    id: UUID
    category_id: UUID
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


# ==================== Connection Schemas ====================

class InstrumentConnectionBase(BaseModel):
    """Base instrument connection schema"""
    endpoint: Optional[str] = Field(None, max_length=500)
    controller_ip: Optional[str] = Field(None, max_length=100)
    port: Optional[int] = Field(None, ge=1, le=65535)
    protocol: Optional[str] = Field(None, max_length=50)
    username: Optional[str] = Field(None, max_length=100)
    connection_params: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


class InstrumentConnectionCreate(InstrumentConnectionBase):
    """Request to create an instrument connection"""
    category_id: UUID
    password: Optional[str] = Field(None, max_length=100, description="明文密码，将自动加密")
    created_by: str = Field(..., max_length=100)


class InstrumentConnectionUpdate(InstrumentConnectionBase):
    """Request to update an instrument connection"""
    password: Optional[str] = Field(None, max_length=100, description="明文密码，将自动加密")
    status: Optional[str] = Field(
        None,
        pattern="^(connected|disconnected|error|unknown)$"
    )


class InstrumentConnectionResponse(InstrumentConnectionBase):
    """Instrument connection response"""
    id: UUID
    category_id: UUID
    status: str
    last_connected_at: Optional[datetime]
    last_error: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    created_by: str

    class Config:
        from_attributes = True


# ==================== Category Schemas ====================

class InstrumentCategoryBase(BaseModel):
    """Base instrument category schema"""
    category_key: str = Field(..., max_length=100)
    category_name: str = Field(..., max_length=255)
    category_name_en: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    icon: Optional[str] = Field(None, max_length=100)
    display_order: int = Field(0, ge=0)
    is_active: bool = True


class InstrumentCategoryCreate(InstrumentCategoryBase):
    """Request to create an instrument category"""
    pass


class InstrumentCategoryUpdate(BaseModel):
    """Request to update an instrument category"""
    category_name: Optional[str] = Field(None, max_length=255)
    category_name_en: Optional[str] = Field(None, max_length=255)
    selected_model_id: Optional[UUID] = None
    description: Optional[str] = None
    icon: Optional[str] = Field(None, max_length=100)
    display_order: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None


class InstrumentCategoryResponse(InstrumentCategoryBase):
    """Instrument category response"""
    id: UUID
    selected_model_id: Optional[UUID]
    created_at: datetime
    updated_at: Optional[datetime]

    # 关联数据
    models: List[InstrumentModelResponse] = []
    connection: Optional[InstrumentConnectionResponse] = None

    class Config:
        from_attributes = True


class InstrumentCategoryListResponse(BaseModel):
    """List of instrument categories response"""
    total: int
    categories: List[InstrumentCategoryResponse]


# ==================== Catalog Schemas ====================

class InstrumentCatalogItem(BaseModel):
    """Single item in the instrument catalog"""
    category: InstrumentCategoryResponse
    available_models: List[InstrumentModelResponse]
    selected_model: Optional[InstrumentModelResponse]
    connection: Optional[InstrumentConnectionResponse]


class InstrumentCatalogResponse(BaseModel):
    """Complete instrument catalog response"""
    total_categories: int
    catalog: List[InstrumentCatalogItem]


# ==================== Frontend-Compatible Update Schema ====================

class FEConnectionUpdate(BaseModel):
    """前端发送的连接配置更新（字段名对齐前端 InstrumentConnection 类型）"""
    endpoint: Optional[str] = None
    controller: Optional[str] = None  # 前端叫 controller，对应 DB 的 protocol
    notes: Optional[str] = None
    connection_params: Optional[Dict[str, Any]] = None  # Option B port_maps 等额外配置


class UpdateInstrumentCategoryRequest(BaseModel):
    """Request to update an instrument category's selection and connection
    
    前端发送 { modelId, connection: { endpoint, controller, notes } }
    """
    # 前端发 modelId，后端存 selected_model_id
    modelId: Optional[str] = Field(
        None, alias="modelId",
        description="选择的仪器型号ID (前端字段名)"
    )
    selected_model_id: Optional[UUID] = Field(
        None,
        description="选择的仪器型号ID (后端字段名，兼容)"
    )
    connection: Optional[FEConnectionUpdate] = Field(
        None,
        description="连接配置"
    )

    def get_model_id(self) -> Optional[UUID]:
        """优先取 modelId，其次 selected_model_id"""
        if self.modelId:
            return UUID(self.modelId)
        return self.selected_model_id


# ==================== Log Schemas ====================

class InstrumentLogCreate(BaseModel):
    """Request to create an instrument log"""
    category_id: UUID
    event_type: str = Field(..., max_length=100)
    message: str
    level: str = Field("info", pattern="^(debug|info|warning|error|critical)$")
    details: Optional[Dict[str, Any]] = None
    performed_by: Optional[str] = Field(None, max_length=100)


class InstrumentLogResponse(BaseModel):
    """Instrument log response"""
    id: UUID
    category_id: UUID
    event_type: str
    message: str
    level: str
    details: Optional[Dict[str, Any]]
    timestamp: datetime
    performed_by: Optional[str]

    class Config:
        from_attributes = True


class InstrumentLogListResponse(BaseModel):
    """List of instrument logs response"""
    total: int
    logs: List[InstrumentLogResponse]


# ==================== Statistics ====================

class InstrumentStatistics(BaseModel):
    """Instrument system statistics"""
    total_categories: int
    total_models: int
    connected_instruments: int
    disconnected_instruments: int
    error_instruments: int
    by_category: Dict[str, Dict[str, Any]]  # {category_key: {status, model, ...}}
