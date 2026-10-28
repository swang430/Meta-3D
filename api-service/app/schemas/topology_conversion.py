"""旧图显式转换的局部严格声明；操作员确认不代表硬件资格。"""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator
from .topology_nominal import validate_number


class StrictConversionModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class TopologyInternalPath(StrictConversionModel):
    from_port: str
    to_port: str


class ConversionNodeEdit(StrictConversionModel):
    node_id: str
    target_type: Literal['ce_port','channel_emulator','bse_port','communication_tester','sa_port','signal_analyzer'] | None = None
    ports: list[str] | None = None
    port_directions: dict[str, Literal['input','output','bidirectional','unknown']] | None = None
    port_roles: dict[str, Literal['dl','ul']] | None = None
    internal_paths: list[TopologyInternalPath] | None = None
    ce_port: str | None = None

    @model_validator(mode='after')
    def explicit_nonnull(self):
        if any(getattr(self,key) is None for key in self.model_fields_set):
            raise ValueError('器件声明不能显式置空')
        if self.model_fields_set == {'node_id'}:
            raise ValueError('转换操作不能为空')
        if 'ce_port' in self.model_fields_set and (not self.ce_port or self.ce_port.strip()!=self.ce_port):
            raise ValueError('ce_port必须为非空且无首尾空白的显式身份')
        return self


class ConversionConnectionEdit(StrictConversionModel):
    connection_id: str
    source_pin: str | None = None
    target_pin: str | None = None
    cable_loss_db: float | None = None
    loss_owner_connection_id: str | None = None
    same_physical_cable_confirmed: bool = False

    @field_validator('cable_loss_db',mode='before')
    @classmethod
    def finite_loss(cls,value):
        validate_number(value,key='cable_loss_db',nonnegative=True)
        return value

    @model_validator(mode='after')
    def explicit_fields(self):
        fields=self.model_fields_set
        if any(getattr(self,key) is None for key in fields & {'source_pin','target_pin'}):
            raise ValueError('端点声明不能显式置空')
        if not fields - {'connection_id','same_physical_cable_confirmed'}:
            raise ValueError('转换操作不能为空')
        if 'loss_owner_connection_id' in fields and not self.same_physical_cable_confirmed:
            raise ValueError('设置或撤销归属须明确确认同一物理线缆')
        return self


class TopologyConversionRequest(StrictConversionModel):
    nodes: list[ConversionNodeEdit] = Field(default_factory=list)
    connections: list[ConversionConnectionEdit] = Field(default_factory=list)

    @model_validator(mode='after')
    def unique_operations(self):
        if not self.nodes and not self.connections:
            raise ValueError('转换清单不能为空')
        for rows,key in ((self.nodes,'node_id'),(self.connections,'connection_id')):
            ids=[getattr(row,key) for row in rows]
            if len(ids)!=len(set(ids)):
                raise ValueError('同一ID不能重复转换')
        return self


class TopologyConversionCommit(StrictConversionModel):
    source_digest: str
    changes: TopologyConversionRequest


class ConversionDifference(StrictConversionModel):
    object_kind: str
    object_id: str
    field: str
    before_present: bool
    before: Any = None
    after: Any


class TopologyConversionPreview(StrictConversionModel):
    revision: int = Field(strict=True, ge=0)
    source_digest: str
    changes: TopologyConversionRequest
    candidate: dict[str, Any]
    differences: list[ConversionDifference]
    warnings: list[str]
