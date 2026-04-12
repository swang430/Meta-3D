"""
Channel Emulator Internal Calibration Service

信道仿真器内部校准服务

CAL-06: 集成 Channel Emulator 厂商校准程序

核心功能:
1. 调用厂商校准程序 (Vendor Calibration)
2. 验证 CE 输出精度 (Output Verification)
3. 导入厂商校准数据 (Calibration Data Import)

典型 CE 厂商:
- Spirent (Vertex)
- Keysight (Propsim)
- Anite (Propsim FS8)
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from uuid import UUID, uuid4
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.probe_calibration import CEInternalCalibration as CEInternalCalibrationModel

logger = logging.getLogger(__name__)


# ==================== 常量定义 ====================

# CE 校准有效期 (天)
CE_CALIBRATION_VALIDITY_DAYS = 90

# 输出精度门限
CE_OUTPUT_POWER_TOLERANCE_DB = 0.5
CE_OUTPUT_PHASE_TOLERANCE_DEG = 5.0
CE_DELAY_TOLERANCE_NS = 1.0


# ==================== 数据模型 ====================

class CEVendor(str, Enum):
    """CE 厂商"""
    SPIRENT = "spirent"
    KEYSIGHT = "keysight"
    ANITE = "anite"
    UNKNOWN = "unknown"


class CECalibrationStatus(str, Enum):
    """CE 校准状态"""
    NOT_CALIBRATED = "not_calibrated"
    CALIBRATED = "calibrated"
    EXPIRED = "expired"
    NEEDS_ATTENTION = "needs_attention"
    FAILED = "failed"


class CECalibrationType(str, Enum):
    """CE 校准类型"""
    FULL = "full"               # 完整校准
    POWER = "power"             # 功率校准
    PHASE = "phase"             # 相位校准
    DELAY = "delay"             # 时延校准
    FREQUENCY = "frequency"     # 频率响应校准


@dataclass
class CEChannelCalibrationData:
    """CE 通道校准数据"""
    channel_id: int
    frequency_mhz: float
    power_offset_db: float
    phase_offset_deg: float
    delay_offset_ns: float
    
    def to_dict(self) -> Dict:
        return {
            "channel_id": self.channel_id,
            "frequency_mhz": self.frequency_mhz,
            "power_offset_db": self.power_offset_db,
            "phase_offset_deg": self.phase_offset_deg,
            "delay_offset_ns": self.delay_offset_ns
        }


@dataclass
class CECalibrationResult:
    """CE 校准结果"""
    id: UUID
    ce_id: str
    vendor: CEVendor
    calibration_type: CECalibrationType
    channels: List[CEChannelCalibrationData]
    frequency_range_mhz: tuple
    overall_status: CECalibrationStatus
    max_power_deviation_db: float
    max_phase_deviation_deg: float
    max_delay_deviation_ns: float
    pass_criteria: bool
    calibrated_at: datetime
    valid_until: datetime
    calibrated_by: str
    notes: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "id": str(self.id),
            "ce_id": self.ce_id,
            "vendor": self.vendor.value,
            "calibration_type": self.calibration_type.value,
            "channels": [ch.to_dict() for ch in self.channels],
            "frequency_range_mhz": list(self.frequency_range_mhz),
            "overall_status": self.overall_status.value,
            "max_power_deviation_db": self.max_power_deviation_db,
            "max_phase_deviation_deg": self.max_phase_deviation_deg,
            "max_delay_deviation_ns": self.max_delay_deviation_ns,
            "pass_criteria": self.pass_criteria,
            "calibrated_at": self.calibrated_at.isoformat(),
            "valid_until": self.valid_until.isoformat(),
            "calibrated_by": self.calibrated_by,
            "notes": self.notes
        }


@dataclass
class CEStatus:
    """CE 整体状态"""
    ce_id: str
    vendor: CEVendor
    connected: bool
    firmware_version: str
    last_calibration: Optional[datetime]
    calibration_status: CECalibrationStatus
    days_until_expiry: Optional[int]
    num_channels: int
    supported_frequencies_mhz: tuple
    
    def to_dict(self) -> Dict:
        return {
            "ce_id": self.ce_id,
            "vendor": self.vendor.value,
            "connected": self.connected,
            "firmware_version": self.firmware_version,
            "last_calibration": self.last_calibration.isoformat() if self.last_calibration else None,
            "calibration_status": self.calibration_status.value,
            "days_until_expiry": self.days_until_expiry,
            "num_channels": self.num_channels,
            "supported_frequencies_mhz": list(self.supported_frequencies_mhz)
        }


# ==================== 服务类 ====================

class CEInternalCalibrationService:
    """
    信道仿真器内部校准服务
    
    负责与 CE 厂商校准程序集成，验证 CE 输出精度。
    """
    
    def __init__(self, db: Session, use_mock: bool = True):
        self.db = db
        self.use_mock = use_mock
        self._calibration_cache: Dict[str, CECalibrationResult] = {}
    
    async def get_ce_status(
        self,
        ce_id: str
    ) -> CEStatus:
        """
        获取 CE 状态
        
        Args:
            ce_id: CE 标识符
            
        Returns:
            CE 状态信息
        """
        logger.info(f"获取 CE 状态: {ce_id}")
        
        if self.use_mock:
            # 模拟 CE 状态
            import random
            
            calibration = self._calibration_cache.get(ce_id)
            
            # 缓存未命中，回退到数据库
            if calibration is None:
                db_record = self.db.query(CEInternalCalibrationModel).filter(
                    CEInternalCalibrationModel.ce_id == ce_id,
                    CEInternalCalibrationModel.status.in_(["calibrated"])
                ).order_by(desc(CEInternalCalibrationModel.calibrated_at)).first()
                
                if db_record:
                    now = datetime.now()
                    if db_record.valid_until and now > db_record.valid_until:
                        status = CECalibrationStatus.EXPIRED
                        days_until_expiry = 0
                    else:
                        status = CECalibrationStatus.CALIBRATED
                        days_until_expiry = (db_record.valid_until - now).days if db_record.valid_until else None
                    last_calibration = db_record.calibrated_at
                else:
                    status = CECalibrationStatus.NOT_CALIBRATED
                    days_until_expiry = None
                    last_calibration = None
            else:
                now = datetime.now()
                if now > calibration.valid_until:
                    status = CECalibrationStatus.EXPIRED
                    days_until_expiry = 0
                else:
                    status = CECalibrationStatus.CALIBRATED
                    days_until_expiry = (calibration.valid_until - now).days
                last_calibration = calibration.calibrated_at
            
            return CEStatus(
                ce_id=ce_id,
                vendor=CEVendor.SPIRENT,
                connected=True,
                firmware_version="8.1.0.1234",
                last_calibration=last_calibration,
                calibration_status=status,
                days_until_expiry=days_until_expiry,
                num_channels=32,
                supported_frequencies_mhz=(400, 7200)
            )
        else:
            # TODO: 实际查询 CE 设备
            raise NotImplementedError("真实 CE 状态查询尚未实现")
    
    async def run_vendor_calibration(
        self,
        ce_id: str,
        calibration_type: CECalibrationType = CECalibrationType.FULL,
        frequency_mhz: float = 3500.0,
        calibrated_by: str = "system"
    ) -> CECalibrationResult:
        """
        执行厂商校准程序
        
        Args:
            ce_id: CE 标识符
            calibration_type: 校准类型
            frequency_mhz: 校准频率
            calibrated_by: 校准人员
            
        Returns:
            校准结果
        """
        logger.info(f"执行 CE 厂商校准: ce={ce_id}, type={calibration_type.value}")
        
        if self.use_mock:
            # 模拟校准过程
            import numpy as np
            
            # 生成模拟通道校准数据
            channels = []
            max_power_dev = 0.0
            max_phase_dev = 0.0
            max_delay_dev = 0.0
            
            for ch in range(32):
                power_offset = np.random.normal(0, 0.2)
                phase_offset = np.random.normal(0, 2.0)
                delay_offset = np.random.normal(0, 0.3)
                
                max_power_dev = max(max_power_dev, abs(power_offset))
                max_phase_dev = max(max_phase_dev, abs(phase_offset))
                max_delay_dev = max(max_delay_dev, abs(delay_offset))
                
                channels.append(CEChannelCalibrationData(
                    channel_id=ch,
                    frequency_mhz=frequency_mhz,
                    power_offset_db=power_offset,
                    phase_offset_deg=phase_offset,
                    delay_offset_ns=delay_offset
                ))
            
            # 判断是否通过
            pass_criteria = (
                max_power_dev <= CE_OUTPUT_POWER_TOLERANCE_DB and
                max_phase_dev <= CE_OUTPUT_PHASE_TOLERANCE_DEG and
                max_delay_dev <= CE_DELAY_TOLERANCE_NS
            )
            
            result = CECalibrationResult(
                id=uuid4(),
                ce_id=ce_id,
                vendor=CEVendor.SPIRENT,
                calibration_type=calibration_type,
                channels=channels,
                frequency_range_mhz=(frequency_mhz - 100, frequency_mhz + 100),
                overall_status=CECalibrationStatus.CALIBRATED if pass_criteria else CECalibrationStatus.NEEDS_ATTENTION,
                max_power_deviation_db=max_power_dev,
                max_phase_deviation_deg=max_phase_dev,
                max_delay_deviation_ns=max_delay_dev,
                pass_criteria=pass_criteria,
                calibrated_at=datetime.now(),
                valid_until=datetime.now() + timedelta(days=CE_CALIBRATION_VALIDITY_DAYS),
                calibrated_by=calibrated_by,
                notes="Mock calibration completed successfully"
            )
            
            # 缓存结果
            self._calibration_cache[ce_id] = result
            
            # 持久化到数据库
            try:
                db_record = CEInternalCalibrationModel(
                    id=result.id,
                    ce_id=ce_id,
                    vendor=CEVendor.SPIRENT.value,
                    calibration_type=calibration_type.value,
                    frequency_start_mhz=frequency_mhz - 100,
                    frequency_stop_mhz=frequency_mhz + 100,
                    channel_count=32,
                    channels_data=[ch.to_dict() for ch in channels],
                    max_power_deviation_db=max_power_dev,
                    max_phase_deviation_deg=max_phase_dev,
                    max_delay_deviation_ns=max_delay_dev,
                    pass_criteria=pass_criteria,
                    power_tolerance_db=CE_OUTPUT_POWER_TOLERANCE_DB,
                    phase_tolerance_deg=CE_OUTPUT_PHASE_TOLERANCE_DEG,
                    delay_tolerance_ns=CE_DELAY_TOLERANCE_NS,
                    firmware_version="8.1.0.1234",
                    calibrated_at=result.calibrated_at,
                    calibrated_by=calibrated_by,
                    notes="Mock calibration completed successfully",
                    valid_until=result.valid_until,
                    status="calibrated" if pass_criteria else "failed"
                )
                self.db.add(db_record)
                self.db.commit()
                logger.info(f"CE 校准结果已持久化到数据库: {result.id}")
            except Exception as e:
                self.db.rollback()
                logger.error(f"CE 校准结果持久化失败: {e}")
            
            logger.info(
                f"CE 校准完成: power_dev={max_power_dev:.3f}dB, "
                f"phase_dev={max_phase_dev:.2f}°, pass={pass_criteria}"
            )
            
            return result
        else:
            # TODO: 调用厂商 API
            raise NotImplementedError("真实 CE 校准尚未实现")
    
    async def verify_ce_output(
        self,
        ce_id: str,
        frequency_mhz: float = 3500.0,
        test_power_dbm: float = -30.0
    ) -> Dict[str, Any]:
        """
        验证 CE 输出精度
        
        通过发送测试信号并测量输出来验证 CE 性能。
        
        Args:
            ce_id: CE 标识符
            frequency_mhz: 测试频率
            test_power_dbm: 测试功率
            
        Returns:
            验证结果
        """
        logger.info(f"验证 CE 输出: ce={ce_id}, freq={frequency_mhz}MHz")
        
        if self.use_mock:
            import numpy as np
            
            # 模拟验证结果
            measured_power_dbm = test_power_dbm + np.random.normal(0, 0.3)
            measured_phase_deg = np.random.normal(0, 3.0)
            
            power_error = abs(measured_power_dbm - test_power_dbm)
            
            return {
                "ce_id": ce_id,
                "frequency_mhz": frequency_mhz,
                "verification_passed": power_error <= CE_OUTPUT_POWER_TOLERANCE_DB,
                "test_power_dbm": test_power_dbm,
                "measured_power_dbm": measured_power_dbm,
                "power_error_db": power_error,
                "measured_phase_deg": measured_phase_deg,
                "power_tolerance_db": CE_OUTPUT_POWER_TOLERANCE_DB,
                "phase_tolerance_deg": CE_OUTPUT_PHASE_TOLERANCE_DEG
            }
        else:
            raise NotImplementedError("真实 CE 输出验证尚未实现")
    
    async def import_calibration_data(
        self,
        ce_id: str,
        file_path: str,
        file_format: str = "json"
    ) -> Dict[str, Any]:
        """
        导入厂商校准数据
        
        从文件导入厂商提供的校准数据。
        
        Args:
            ce_id: CE 标识符
            file_path: 校准数据文件路径
            file_format: 文件格式 (json, csv, xml)
            
        Returns:
            导入结果
        """
        logger.info(f"导入 CE 校准数据: ce={ce_id}, file={file_path}")
        
        path = Path(file_path)
        
        if not path.exists():
            return {
                "success": False,
                "error": f"文件不存在: {file_path}",
                "imported_channels": 0
            }
        
        try:
            if file_format == "json":
                with open(path, 'r') as f:
                    data = json.load(f)
            else:
                return {
                    "success": False,
                    "error": f"不支持的文件格式: {file_format}",
                    "imported_channels": 0
                }
            
            # 解析校准数据
            channels = []
            for ch_data in data.get("channels", []):
                channels.append(CEChannelCalibrationData(
                    channel_id=ch_data.get("channel_id", 0),
                    frequency_mhz=ch_data.get("frequency_mhz", 3500.0),
                    power_offset_db=ch_data.get("power_offset_db", 0.0),
                    phase_offset_deg=ch_data.get("phase_offset_deg", 0.0),
                    delay_offset_ns=ch_data.get("delay_offset_ns", 0.0)
                ))
            
            # 创建校准结果
            result = CECalibrationResult(
                id=uuid4(),
                ce_id=ce_id,
                vendor=CEVendor(data.get("vendor", "unknown")),
                calibration_type=CECalibrationType(data.get("type", "full")),
                channels=channels,
                frequency_range_mhz=tuple(data.get("frequency_range_mhz", [400, 7200])),
                overall_status=CECalibrationStatus.CALIBRATED,
                max_power_deviation_db=data.get("max_power_deviation_db", 0.0),
                max_phase_deviation_deg=data.get("max_phase_deviation_deg", 0.0),
                max_delay_deviation_ns=data.get("max_delay_deviation_ns", 0.0),
                pass_criteria=True,
                calibrated_at=datetime.fromisoformat(data.get("calibrated_at", datetime.now().isoformat())),
                valid_until=datetime.fromisoformat(data.get("valid_until", (datetime.now() + timedelta(days=90)).isoformat())),
                calibrated_by=data.get("calibrated_by", "imported"),
                notes=f"Imported from {file_path}"
            )
            
            # 缓存结果
            self._calibration_cache[ce_id] = result
            
            return {
                "success": True,
                "ce_id": ce_id,
                "imported_channels": len(channels),
                "calibration_id": str(result.id),
                "valid_until": result.valid_until.isoformat()
            }
            
        except Exception as e:
            logger.error(f"导入校准数据失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "imported_channels": 0
            }
    
    def get_channel_compensation(
        self,
        ce_id: str,
        channel_id: int,
        frequency_mhz: float
    ) -> Optional[CEChannelCalibrationData]:
        """
        获取通道补偿值
        
        Args:
            ce_id: CE 标识符
            channel_id: 通道 ID
            frequency_mhz: 频率
            
        Returns:
            通道校准数据
        """
        calibration = self._calibration_cache.get(ce_id)
        
        if not calibration:
            return None
        
        for ch in calibration.channels:
            if ch.channel_id == channel_id:
                return ch
        
        return None
