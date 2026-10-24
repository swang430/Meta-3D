"""PC-02A 固定通路方法：人工参考值的计算预览，不是实测证书。"""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

ReferenceText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
FiniteNumber = Annotated[float, Field(strict=True, allow_inf_nan=False)]


class FixedRouteCalibrationDeclaration(BaseModel):
    model_config = ConfigDict(extra='forbid')
    lab_profile_id: UUID = Field(description='操作员指定实验室；本接口不核验保存配置或实物身份')
    chain_id: ReferenceText
    ce_port: ReferenceText = Field(description='F64物理输出连接器')
    switch_identity: ReferenceText = Field(description='固定通路中射频开关的身份记录')
    fixed_route: ReferenceText = Field(description='开关固定的输入到输出通路；不发切换命令')
    switch_mode: Literal['fixed'] = 'fixed'
    reference_antenna: ReferenceText = Field(description='终点参考天线身份及参考位置记录')
    frequency_mhz: FiniteNumber = Field(gt=0, description='三项参考值适用的同一工作频率（MHz）')
    ce_output_power_dbm: FiniteNumber = Field(description='F64物理输出口功率（dBm），不得用设定值代替')
    ce_power_source: ReferenceText = Field(description='输出口功率记录来源，不是自动核验结果')
    sa_input_power_dbm: FiniteNumber = Field(description='分析仪输入口绝对功率（dBm），不是功率密度')
    sa_power_source: ReferenceText
    receive_cable_loss_db: FiniteNumber = Field(description='参考天线到分析仪接收线缆损耗（dB）；衰减为正，增益为负')
    receive_cable_source: ReferenceText


class FixedRouteCalibrationPreview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    method: Literal['fixed_route_port_to_reference_v1'] = 'fixed_route_port_to_reference_v1'
    declaration: FixedRouteCalibrationDeclaration
    net_loss_db: FiniteNumber = Field(description='F64输出口功率 -（分析仪输入口功率 + 接收线缆损耗）；负值为整路增益')
    input_provenance: Literal['operator_entered'] = 'operator_entered'
    formal_eligible: Literal[False] = False
    warning: str
