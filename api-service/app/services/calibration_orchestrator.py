"""
Calibration Orchestrator

校准编排器 - 根据暗室配置自动决定和执行校准流程。

CAL-04.5: 根据 ChamberConfiguration 自动推断需要的校准项目，
并按正确的顺序协调执行。

设计原则:
1. 配置驱动: 校准项目由暗室配置决定，而非硬编码
2. 依赖管理: 校准项目有执行顺序依赖 (如路损校准先于 TRP)
3. 状态追踪: 追踪每个校准项的状态和有效期
4. 增量执行: 支持只执行缺失或过期的校准

参考: docs/design/MPAC-OTA-Chamber-Topology.md
"""
from typing import List, Dict, Optional, Any, Set
from datetime import datetime, timedelta
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import desc
from enum import Enum
import logging

from app.models.chamber import ChamberConfiguration
from app.models.probe_calibration import (
    ProbePathLossCalibration,
    RFChainCalibration,
    MultiFrequencyPathLoss,
    CalibrationStatus as CalibrationStatusEnum,
    ChannelPhaseCalibration,
    CEInternalCalibration,
)
from app.models.calibration import (
    QuietZoneCalibration,
)
from app.services.path_loss_calibration_service import (
    ProbePathLossCalibrationService,
    RFChainCalibrationService,
    MultiFrequencyPathLossService,
)

logger = logging.getLogger(__name__)


class CalibrationItem(str, Enum):
    """校准项目枚举"""
    PROBE_PATH_LOSS = "probe_path_loss"           # 探头路损校准
    QUIET_ZONE_UNIFORMITY = "quiet_zone_uniformity"  # 静区均匀性
    UPLINK_CHAIN = "ul_chain_gain"                # 上行链路 (LNA)
    DOWNLINK_CHAIN = "dl_chain_gain"              # 下行链路 (PA)
    DUPLEXER_ISOLATION = "duplexer_isolation"     # 双工器隔离度
    CE_BYPASS = "ce_bypass_calibration"           # CE 直通校准
    CE_BIDIRECTIONAL = "ce_bidirectional_calibration"  # CE 双向校准
    PROBE_MUTUAL_COUPLING = "probe_mutual_coupling"  # 探头互耦
    MULTI_FREQUENCY = "multi_frequency_path_loss"  # 多频点路损


class CalibrationPriority(int, Enum):
    """校准优先级 (数字越小越优先)"""
    CRITICAL = 1   # 基础校准，必须首先完成
    HIGH = 2       # 链路校准
    MEDIUM = 3     # 可选校准
    LOW = 4        # 增强校准


# 校准项目配置
CALIBRATION_CONFIG = {
    CalibrationItem.PROBE_PATH_LOSS: {
        "name": "探头路损校准",
        "description": "测量 SGH 到每个探头的空间路径损耗",
        "priority": CalibrationPriority.CRITICAL,
        "validity_days": 180,
        "dependencies": [],
        "required_for": ["TRP", "TIS", "MIMO_OTA"],
    },
    CalibrationItem.QUIET_ZONE_UNIFORMITY: {
        "name": "静区均匀性校准",
        "description": "验证静区内的场均匀性",
        "priority": CalibrationPriority.CRITICAL,
        "validity_days": 365,
        "dependencies": [CalibrationItem.PROBE_PATH_LOSS],
        "required_for": ["TRP", "TIS", "MIMO_OTA"],
    },
    CalibrationItem.UPLINK_CHAIN: {
        "name": "上行链路校准",
        "description": "校准 LNA 增益和上行链路总增益",
        "priority": CalibrationPriority.HIGH,
        "validity_days": 90,
        "dependencies": [],
        "required_for": ["TRP"],
        "condition": lambda c: c.has_lna,
    },
    CalibrationItem.DOWNLINK_CHAIN: {
        "name": "下行链路校准",
        "description": "校准 PA 增益和下行链路总增益",
        "priority": CalibrationPriority.HIGH,
        "validity_days": 90,
        "dependencies": [],
        "required_for": ["TIS"],
        "condition": lambda c: c.has_pa,
    },
    CalibrationItem.DUPLEXER_ISOLATION: {
        "name": "双工器隔离度校准",
        "description": "测量双工器 TX/RX 端口隔离度",
        "priority": CalibrationPriority.HIGH,
        "validity_days": 180,
        "dependencies": [],
        "required_for": ["TRP", "TIS"],
        "condition": lambda c: c.has_duplexer,
    },
    CalibrationItem.CE_BYPASS: {
        "name": "信道仿真器直通校准",
        "description": "校准 CE 直通模式下的增益和相位",
        "priority": CalibrationPriority.MEDIUM,
        "validity_days": 90,
        "dependencies": [],
        "required_for": ["MIMO_OTA"],
        "condition": lambda c: c.has_channel_emulator,
    },
    CalibrationItem.CE_BIDIRECTIONAL: {
        "name": "信道仿真器双向校准",
        "description": "校准 CE 双向直通模式",
        "priority": CalibrationPriority.MEDIUM,
        "validity_days": 90,
        "dependencies": [CalibrationItem.CE_BYPASS],
        "required_for": ["MIMO_OTA"],
        "condition": lambda c: c.has_channel_emulator and c.ce_bidirectional,
    },
    CalibrationItem.PROBE_MUTUAL_COUPLING: {
        "name": "探头互耦校准",
        "description": "测量探头间的互耦合系数",
        "priority": CalibrationPriority.MEDIUM,
        "validity_days": 365,
        "dependencies": [CalibrationItem.PROBE_PATH_LOSS],
        "required_for": ["MIMO_OTA"],
        "condition": lambda c: c.supports_mimo_ota,
    },
    CalibrationItem.MULTI_FREQUENCY: {
        "name": "多频点路损校准",
        "description": "扫频测量路损，支持频率插值",
        "priority": CalibrationPriority.LOW,
        "validity_days": 180,
        "dependencies": [CalibrationItem.PROBE_PATH_LOSS],
        "required_for": [],
    },
}


class CalibrationItemStatus:
    """单个校准项的状态（重命名以避免与 models.CalibrationStatus 枚举冲突）"""
    def __init__(
        self,
        item: CalibrationItem,
        is_required: bool,
        is_valid: bool,
        valid_until: Optional[datetime] = None,
        calibration_id: Optional[UUID] = None,
        message: str = ""
    ):
        self.item = item
        self.is_required = is_required
        self.is_valid = is_valid
        self.valid_until = valid_until
        self.calibration_id = calibration_id
        self.message = message

    @property
    def is_expired(self) -> bool:
        if not self.valid_until:
            return True
        return datetime.utcnow() > self.valid_until

    @property
    def days_until_expiry(self) -> Optional[int]:
        if not self.valid_until:
            return None
        delta = self.valid_until - datetime.utcnow()
        return delta.days

    def to_dict(self) -> Dict[str, Any]:
        config = CALIBRATION_CONFIG.get(self.item, {})
        return {
            "item": self.item.value,
            "name": config.get("name", self.item.value),
            "is_required": self.is_required,
            "is_valid": self.is_valid,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "calibration_id": str(self.calibration_id) if self.calibration_id else None,
            "days_until_expiry": self.days_until_expiry,
            "message": self.message
        }


class CalibrationOrchestrator:
    """
    校准编排器

    根据暗室配置自动决定需要的校准项目，追踪校准状态，
    并协调校准流程的执行。
    """

    def __init__(self, db: Session, use_mock: bool = True):
        self.db = db
        self.use_mock = use_mock

        # 初始化各校准服务
        self.path_loss_service = ProbePathLossCalibrationService(db, use_mock)
        self.rf_chain_service = RFChainCalibrationService(db, use_mock)
        self.multi_freq_service = MultiFrequencyPathLossService(db, use_mock)

    def get_required_calibrations(
        self,
        chamber: ChamberConfiguration
    ) -> List[CalibrationItem]:
        """
        根据暗室配置获取必需的校准项目

        Args:
            chamber: 暗室配置

        Returns:
            必需的校准项目列表 (按优先级排序)
        """
        required = []

        for item, config in CALIBRATION_CONFIG.items():
            # 检查条件
            condition = config.get("condition")
            if condition and not condition(chamber):
                continue

            # 添加到列表
            required.append(item)

        # 按优先级排序
        required.sort(key=lambda x: CALIBRATION_CONFIG[x]["priority"].value)

        return required

    def get_optional_calibrations(
        self,
        chamber: ChamberConfiguration
    ) -> List[CalibrationItem]:
        """获取可选的校准项目"""
        required = set(self.get_required_calibrations(chamber))
        optional = []

        for item, config in CALIBRATION_CONFIG.items():
            if item not in required:
                # 检查条件 - 只有满足条件但不在必需列表中的才是可选
                condition = config.get("condition")
                if condition is None or condition(chamber):
                    optional.append(item)

        return optional

    def check_calibration_status(
        self,
        chamber_id: UUID,
        frequency_mhz: float = 3500.0
    ) -> Dict[CalibrationItem, CalibrationItemStatus]:
        """
        检查暗室的校准状态

        Args:
            chamber_id: 暗室配置 ID
            frequency_mhz: 参考频率

        Returns:
            每个校准项的状态字典
        """
        chamber = self.db.query(ChamberConfiguration).filter(
            ChamberConfiguration.id == chamber_id
        ).first()

        if not chamber:
            return {}

        required_items = self.get_required_calibrations(chamber)
        statuses = {}

        for item in CalibrationItem:
            is_required = item in required_items
            is_valid = False
            valid_until = None
            calibration_id = None
            message = ""

            # 检查每种校准类型的状态
            if item == CalibrationItem.PROBE_PATH_LOSS:
                cal = self.path_loss_service.get_latest_calibration(chamber_id, frequency_mhz)
                if cal:
                    is_valid = cal.status == "valid"
                    valid_until = cal.valid_until
                    calibration_id = cal.id
                else:
                    message = "No path loss calibration found"

            elif item == CalibrationItem.UPLINK_CHAIN:
                cal = self.rf_chain_service.get_latest_uplink_calibration(chamber_id, frequency_mhz)
                if cal:
                    is_valid = cal.status == "valid"
                    valid_until = cal.valid_until
                    calibration_id = cal.id
                elif not chamber.has_lna:
                    is_valid = True
                    message = "LNA not configured, calibration not needed"
                else:
                    message = "No uplink calibration found"

            elif item == CalibrationItem.DOWNLINK_CHAIN:
                cal = self.rf_chain_service.get_latest_downlink_calibration(chamber_id, frequency_mhz)
                if cal:
                    is_valid = cal.status == "valid"
                    valid_until = cal.valid_until
                    calibration_id = cal.id
                elif not chamber.has_pa:
                    is_valid = True
                    message = "PA not configured, calibration not needed"
                else:
                    message = "No downlink calibration found"

            elif item == CalibrationItem.MULTI_FREQUENCY:
                # 检查是否有多频点校准覆盖目标频率
                cal = self.db.query(MultiFrequencyPathLoss).filter(
                    MultiFrequencyPathLoss.chamber_id == chamber_id,
                    MultiFrequencyPathLoss.status == "valid",
                    MultiFrequencyPathLoss.freq_start_mhz <= frequency_mhz,
                    MultiFrequencyPathLoss.freq_stop_mhz >= frequency_mhz
                ).order_by(desc(MultiFrequencyPathLoss.calibrated_at)).first()

                if cal:
                    is_valid = True
                    valid_until = cal.valid_until
                    calibration_id = cal.id
                else:
                    message = "No multi-frequency calibration covering target frequency"

            elif item == CalibrationItem.QUIET_ZONE_UNIFORMITY:
                cal = self.db.query(QuietZoneCalibration).filter(
                    QuietZoneCalibration.validation_pass == True
                ).order_by(desc(QuietZoneCalibration.tested_at)).first()
                if cal:
                    is_valid = True
                    valid_until = cal.tested_at + timedelta(days=365) if cal.tested_at else None
                    calibration_id = cal.id
                else:
                    message = "No quiet zone uniformity calibration found"

            elif item == CalibrationItem.DUPLEXER_ISOLATION:
                # 双工器隔离度从 RFChainCalibration 中带出
                cal = self.db.query(RFChainCalibration).filter(
                    RFChainCalibration.chamber_id == chamber_id,
                    RFChainCalibration.has_duplexer == True,
                    RFChainCalibration.status == "valid"
                ).order_by(desc(RFChainCalibration.calibrated_at)).first()
                if cal:
                    is_valid = True
                    valid_until = cal.valid_until
                    calibration_id = cal.id
                elif not chamber.has_duplexer:
                    is_valid = True
                    message = "Duplexer not configured, calibration not needed"
                else:
                    message = "No duplexer isolation calibration found"

            elif item == CalibrationItem.CE_BYPASS:
                cal = self.db.query(CEInternalCalibration).filter(
                    CEInternalCalibration.status == "calibrated",
                    CEInternalCalibration.calibration_type == "full"
                ).order_by(desc(CEInternalCalibration.calibrated_at)).first()
                if cal:
                    is_valid = True
                    valid_until = cal.valid_until
                    calibration_id = cal.id
                elif not chamber.has_channel_emulator:
                    is_valid = True
                    message = "CE not configured, calibration not needed"
                else:
                    message = "No CE bypass calibration found"

            elif item == CalibrationItem.CE_BIDIRECTIONAL:
                cal = self.db.query(CEInternalCalibration).filter(
                    CEInternalCalibration.status == "calibrated"
                ).order_by(desc(CEInternalCalibration.calibrated_at)).first()
                if cal:
                    is_valid = True
                    valid_until = cal.valid_until
                    calibration_id = cal.id
                elif not (chamber.has_channel_emulator and chamber.ce_bidirectional):
                    is_valid = True
                    message = "CE bidirectional not configured"
                else:
                    message = "No CE bidirectional calibration found"

            elif item == CalibrationItem.PROBE_MUTUAL_COUPLING:
                cal = self.db.query(ChannelPhaseCalibration).filter(
                    ChannelPhaseCalibration.chamber_id == chamber_id,
                    ChannelPhaseCalibration.status == "valid"
                ).order_by(desc(ChannelPhaseCalibration.calibrated_at)).first()
                if cal:
                    is_valid = True
                    valid_until = cal.valid_until
                    calibration_id = cal.id
                elif not chamber.supports_mimo_ota:
                    is_valid = True
                    message = "MIMO OTA not supported, mutual coupling check not needed"
                else:
                    message = "No mutual coupling calibration found"

            else:
                message = f"Unknown calibration type: {item.value}"

            statuses[item] = CalibrationItemStatus(
                item=item,
                is_required=is_required,
                is_valid=is_valid,
                valid_until=valid_until,
                calibration_id=calibration_id,
                message=message
            )

        return statuses

    def get_calibration_plan(
        self,
        chamber_id: UUID,
        frequency_mhz: float = 3500.0,
        force_recalibrate: bool = False
    ) -> Dict[str, Any]:
        """
        生成校准计划

        Args:
            chamber_id: 暗室配置 ID
            frequency_mhz: 目标频率
            force_recalibrate: 是否强制重新校准所有项目

        Returns:
            校准计划，包含需要执行的项目和顺序
        """
        statuses = self.check_calibration_status(chamber_id, frequency_mhz)

        # 确定需要执行的校准项目
        items_to_calibrate = []

        for item, status in statuses.items():
            if not status.is_required:
                continue

            if force_recalibrate or not status.is_valid or status.is_expired:
                items_to_calibrate.append(item)

        # 根据依赖关系排序
        sorted_items = self._topological_sort(items_to_calibrate)

        # 计算预计时间
        estimated_duration_minutes = len(sorted_items) * 15  # 每项约 15 分钟

        return {
            "chamber_id": str(chamber_id),
            "frequency_mhz": frequency_mhz,
            "items_to_calibrate": [item.value for item in sorted_items],
            "total_items": len(sorted_items),
            "estimated_duration_minutes": estimated_duration_minutes,
            "all_statuses": {
                item.value: status.to_dict()
                for item, status in statuses.items()
            }
        }

    def _topological_sort(
        self,
        items: List[CalibrationItem]
    ) -> List[CalibrationItem]:
        """根据依赖关系对校准项目进行拓扑排序"""
        # 构建依赖图
        in_degree = {item: 0 for item in items}
        graph = {item: [] for item in items}

        item_set = set(items)

        for item in items:
            config = CALIBRATION_CONFIG.get(item, {})
            for dep in config.get("dependencies", []):
                if dep in item_set:
                    graph[dep].append(item)
                    in_degree[item] += 1

        # Kahn's algorithm
        result = []
        queue = [item for item in items if in_degree[item] == 0]

        # 按优先级排序队列
        queue.sort(key=lambda x: CALIBRATION_CONFIG[x]["priority"].value)

        while queue:
            current = queue.pop(0)
            result.append(current)

            for neighbor in graph[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
                    queue.sort(key=lambda x: CALIBRATION_CONFIG[x]["priority"].value)

        return result

    # ==================== CAL-05: 依赖管理功能 ====================

    def check_dependency_chain(
        self,
        chamber_id: UUID,
        item: CalibrationItem,
        frequency_mhz: float = 3500.0
    ) -> Dict[str, Any]:
        """
        检查校准项的依赖链完整性
        
        Args:
            chamber_id: 暗室配置 ID
            item: 要检查的校准项
            frequency_mhz: 参考频率
            
        Returns:
            依赖链状态
        """
        statuses = self.check_calibration_status(chamber_id, frequency_mhz)
        config = CALIBRATION_CONFIG.get(item, {})
        dependencies = config.get("dependencies", [])
        
        missing_deps = []
        expired_deps = []
        valid_deps = []
        
        for dep in dependencies:
            if dep in statuses:
                status = statuses[dep]
                if not status.is_valid:
                    missing_deps.append(dep.value)
                elif status.is_expired:
                    expired_deps.append(dep.value)
                else:
                    valid_deps.append(dep.value)
        
        chain_valid = len(missing_deps) == 0 and len(expired_deps) == 0
        
        return {
            "item": item.value,
            "chain_valid": chain_valid,
            "dependencies": {
                "required": [d.value for d in dependencies],
                "valid": valid_deps,
                "missing": missing_deps,
                "expired": expired_deps
            },
            "can_execute": chain_valid,
            "blocking_items": missing_deps + expired_deps
        }

    def get_dependents(
        self,
        item: CalibrationItem
    ) -> List[CalibrationItem]:
        """
        获取依赖于指定校准项的所有下游校准项
        
        Args:
            item: 校准项
            
        Returns:
            依赖于此项的下游校准项列表
        """
        dependents = []
        
        for other_item, config in CALIBRATION_CONFIG.items():
            if item in config.get("dependencies", []):
                dependents.append(other_item)
        
        return dependents

    def invalidate_dependent_data(
        self,
        chamber_id: UUID,
        item: CalibrationItem,
        cascade: bool = True
    ) -> Dict[str, Any]:
        """
        级联失效下游校准数据
        
        当某个校准项失效时，所有依赖它的下游校准也应失效。
        
        Args:
            chamber_id: 暗室配置 ID
            item: 失效的校准项
            cascade: 是否级联失效
            
        Returns:
            失效操作结果
        """
        invalidated = [item.value]
        
        if cascade:
            # 获取所有下游依赖
            to_invalidate = [item]
            visited = set()
            
            while to_invalidate:
                current = to_invalidate.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                
                dependents = self.get_dependents(current)
                for dep in dependents:
                    if dep not in visited:
                        to_invalidate.append(dep)
                        invalidated.append(dep.value)
        
        # 实际更新数据库中的校准状态
        db_updated = 0
        unique_invalidated = list(set(invalidated))

        # 校准类型 → ORM 表的映射
        item_table_map = {
            CalibrationItem.PROBE_PATH_LOSS.value: ProbePathLossCalibration,
            CalibrationItem.UPLINK_CHAIN.value: RFChainCalibration,
            CalibrationItem.DOWNLINK_CHAIN.value: RFChainCalibration,
            CalibrationItem.MULTI_FREQUENCY.value: MultiFrequencyPathLoss,
            CalibrationItem.PROBE_MUTUAL_COUPLING.value: ChannelPhaseCalibration,
            CalibrationItem.CE_BYPASS.value: CEInternalCalibration,
            CalibrationItem.CE_BIDIRECTIONAL.value: CEInternalCalibration,
        }

        for item_value in unique_invalidated:
            model = item_table_map.get(item_value)
            if model is None:
                continue

            try:
                # 构建基础查询
                query = self.db.query(model).filter(model.status == "valid")

                # 如果模型有 chamber_id 列，按暗室过滤
                if hasattr(model, 'chamber_id'):
                    query = query.filter(model.chamber_id == chamber_id)

                # 对链路校准区分上下行
                if model == RFChainCalibration:
                    if item_value == CalibrationItem.UPLINK_CHAIN.value:
                        query = query.filter(RFChainCalibration.chain_type == "uplink")
                    elif item_value == CalibrationItem.DOWNLINK_CHAIN.value:
                        query = query.filter(RFChainCalibration.chain_type == "downlink")

                count = query.update({"status": CalibrationStatusEnum.INVALIDATED.value})
                db_updated += count
                if count > 0:
                    logger.info(f"Invalidated {count} record(s) in {model.__tablename__} for {item_value}")
            except Exception as e:
                logger.warning(f"Failed to invalidate {item_value}: {e}")

        self.db.commit()
        logger.info(f"Cascade invalidation complete for chamber {chamber_id}: {db_updated} DB records updated")

        return {
            "chamber_id": str(chamber_id),
            "triggered_by": item.value,
            "invalidated_items": unique_invalidated,
            "cascade": cascade,
            "db_records_updated": db_updated
        }

    def get_recalibration_triggers(
        self,
        chamber_id: UUID
    ) -> List[Dict[str, Any]]:
        """
        获取重新校准触发条件
        
        检查哪些校准项需要重新校准及原因。
        
        Args:
            chamber_id: 暗室配置 ID
            
        Returns:
            需要重新校准的项目及原因
        """
        triggers = []
        statuses = self.check_calibration_status(chamber_id)
        
        for item, status in statuses.items():
            if not status.is_required:
                continue
                
            config = CALIBRATION_CONFIG.get(item, {})
            reasons = []
            
            # 检查失效原因
            if not status.is_valid:
                reasons.append("never_calibrated")
            elif status.is_expired:
                reasons.append("expired")
            elif status.days_until_expiry is not None and status.days_until_expiry < 7:
                reasons.append("expiring_soon")
            
            # 检查依赖失效
            for dep in config.get("dependencies", []):
                if dep in statuses:
                    dep_status = statuses[dep]
                    if not dep_status.is_valid or dep_status.is_expired:
                        reasons.append(f"dependency_invalid:{dep.value}")
            
            if reasons:
                triggers.append({
                    "item": item.value,
                    "name": config.get("name", item.value),
                    "priority": config.get("priority", CalibrationPriority.LOW).value,
                    "reasons": reasons,
                    "days_until_expiry": status.days_until_expiry,
                    "last_calibration": status.valid_until.isoformat() if status.valid_until else None
                })
        
        # 按优先级排序
        triggers.sort(key=lambda x: x["priority"])
        
        return triggers

    def schedule_calibration(
        self,
        chamber_id: UUID,
        frequency_mhz: float = 3500.0,
        calibrated_by: str = "auto_scheduler"
    ) -> Dict[str, Any]:
        """
        调度自动校准任务
        
        根据过期和依赖状态自动生成校准计划。
        
        Args:
            chamber_id: 暗室配置 ID
            frequency_mhz: 目标频率
            calibrated_by: 校准执行者
            
        Returns:
            调度结果
        """
        triggers = self.get_recalibration_triggers(chamber_id)
        
        if not triggers:
            return {
                "chamber_id": str(chamber_id),
                "scheduled": False,
                "message": "所有校准均有效，无需调度",
                "items": []
            }
        
        # 筛选需要立即执行的项目
        urgent_items = []
        scheduled_items = []
        
        for trigger in triggers:
            if "expired" in trigger["reasons"] or "never_calibrated" in trigger["reasons"]:
                urgent_items.append(trigger["item"])
            elif any(r.startswith("dependency_invalid") for r in trigger["reasons"]):
                # 依赖失效也需要尽快处理
                urgent_items.append(trigger["item"])
            elif "expiring_soon" in trigger["reasons"]:
                scheduled_items.append(trigger["item"])
        
        # 获取要执行的校准项
        items_to_execute = [
            CalibrationItem(item) for item in set(urgent_items)
        ]
        
        # 按依赖排序
        sorted_items = self._topological_sort(items_to_execute)
        
        return {
            "chamber_id": str(chamber_id),
            "scheduled": len(sorted_items) > 0,
            "urgent_items": [item.value for item in sorted_items],
            "pending_items": scheduled_items,
            "total_urgent": len(sorted_items),
            "total_pending": len(scheduled_items),
            "estimated_duration_minutes": len(sorted_items) * 15,
            "message": f"调度了 {len(sorted_items)} 个紧急校准项目" if sorted_items else "无紧急校准"
        }

    async def execute_calibration_plan(
        self,
        chamber_id: UUID,
        frequency_mhz: float,
        items: List[CalibrationItem],
        calibrated_by: str,
        sgh_model: str = "Generic SGH",
        sgh_gain_dbi: float = 10.0,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        执行校准计划

        Args:
            chamber_id: 暗室配置 ID
            frequency_mhz: 校准频率
            items: 要执行的校准项目列表
            calibrated_by: 校准人员
            sgh_model: SGH 型号
            sgh_gain_dbi: SGH 增益
            progress_callback: 进度回调函数

        Returns:
            执行结果
        """
        results = {}
        total = len(items)

        for i, item in enumerate(items):
            if progress_callback:
                progress_callback({
                    "current_item": item.value,
                    "progress": (i / total) * 100,
                    "message": f"Executing {CALIBRATION_CONFIG[item]['name']}"
                })

            try:
                if item == CalibrationItem.PROBE_PATH_LOSS:
                    result = await self.path_loss_service.start_calibration(
                        chamber_id=chamber_id,
                        frequency_mhz=frequency_mhz,
                        sgh_model=sgh_model,
                        sgh_gain_dbi=sgh_gain_dbi,
                        calibrated_by=calibrated_by
                    )

                elif item == CalibrationItem.UPLINK_CHAIN:
                    result = await self.rf_chain_service.calibrate_uplink(
                        chamber_id=chamber_id,
                        frequency_mhz=frequency_mhz,
                        calibrated_by=calibrated_by
                    )

                elif item == CalibrationItem.DOWNLINK_CHAIN:
                    result = await self.rf_chain_service.calibrate_downlink(
                        chamber_id=chamber_id,
                        frequency_mhz=frequency_mhz,
                        calibrated_by=calibrated_by
                    )

                else:
                    # TODO: 实现其他校准类型
                    result = type('Result', (), {
                        'success': False,
                        'message': f'Calibration type {item.value} not implemented',
                        'data': {}
                    })()

                results[item.value] = {
                    "success": result.success,
                    "message": result.message,
                    "data": result.data
                }

            except Exception as e:
                logger.error(f"Calibration {item.value} failed: {e}")
                results[item.value] = {
                    "success": False,
                    "message": str(e),
                    "data": {}
                }

        if progress_callback:
            progress_callback({
                "current_item": "complete",
                "progress": 100,
                "message": "Calibration plan execution completed"
            })

        # 统计结果
        successful = sum(1 for r in results.values() if r["success"])
        failed = total - successful

        return {
            "chamber_id": str(chamber_id),
            "total_items": total,
            "successful": successful,
            "failed": failed,
            "results": results,
            "overall_success": failed == 0
        }

    def get_compensation_factors(
        self,
        chamber_id: UUID,
        probe_id: int,
        polarization: str,
        frequency_mhz: float
    ) -> Dict[str, float]:
        """
        获取测量补偿因子

        用于 TRP/TIS 测量时的补偿。

        Args:
            chamber_id: 暗室配置 ID
            probe_id: 探头 ID
            polarization: 极化类型
            frequency_mhz: 测量频率

        Returns:
            补偿因子字典 {path_loss_db, ul_gain_db, dl_gain_db, total_compensation_db}
        """
        chamber = self.db.query(ChamberConfiguration).filter(
            ChamberConfiguration.id == chamber_id
        ).first()

        if not chamber:
            return {"error": "Chamber not found"}

        factors = {
            "path_loss_db": 0.0,
            "ul_gain_db": 0.0,
            "dl_gain_db": 0.0,
            "duplexer_loss_db": 0.0,
        }

        # 获取路损
        path_loss = self.path_loss_service.get_path_loss_for_probe(
            chamber_id, probe_id, polarization, frequency_mhz
        )
        if path_loss:
            factors["path_loss_db"] = path_loss

        # 获取上行链路增益 (TRP 测量用)
        if chamber.has_lna:
            ul_gain = self.rf_chain_service.get_uplink_gain(chamber_id, frequency_mhz)
            if ul_gain:
                factors["ul_gain_db"] = ul_gain

        # 获取下行链路增益 (TIS 测量用)
        if chamber.has_pa:
            dl_gain = self.rf_chain_service.get_downlink_gain(chamber_id, frequency_mhz)
            if dl_gain:
                factors["dl_gain_db"] = dl_gain

        # 计算总补偿
        # TRP: P_dut = P_measured + PathLoss - UL_Gain
        # TIS: P_dut = P_delivered - PathLoss + DL_Gain
        factors["trp_compensation_db"] = factors["path_loss_db"] - factors["ul_gain_db"]
        factors["tis_compensation_db"] = -factors["path_loss_db"] + factors["dl_gain_db"]

        return factors
