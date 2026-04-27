"""
GCM OOP (OTA Orientation Profile) 文件解析器

解析 Keysight PROPSIM F64 GCM 工具生成的 .oop 文件。
.oop 文件精确记录了测试过程中每一个时间戳对应的
目标方位角 (Azimuth) 和仰角 (Elevation)。

OOP 文件用途:
    GCM 在执行 Automatic PAS Rotation 后，会将经过旋转补偿的
    DUT 空间采样序列写入 .oop 文件。外部测试系统需要读取该文件
    来协调转台 (Positioner) 和信道仿真器的时间同步。

    在 MIMO-First 系统中，PAS Rotation 已由 pas_rotation.py 实现，
    转台同步采用 "方式 A：软件指令同步" 模式。
    但为了与 GCM Native 模式互操作，需要能解析 GCM 输出的 .oop 文件。

OOP 文件格式 (从 Keysight 文档推断):
    - 纯文本，逗号分隔 (CSV-like)
    - 文件头: # 开头的注释行，包含元数据
    - 数据行: time_s, azimuth_deg, elevation_deg[, speed_deg_s]

    示例:
        # GCM OTA Orientation Profile
        # Model: UMa CDL-C NLOS
        # PAS Rotation: 7.5 deg
        # Date: 2026-04-27
        0.000, 0.0, 0.0, 5.0
        1.200, 15.0, 0.0, 5.0
        2.400, 30.0, 0.0, 5.0
        ...

用法:
    from app.services.channel_generation.oop_parser import (
        parse_oop_file,
        generate_oop_file,
        OOPProfile,
    )

    # 解析 GCM 输出
    profile = parse_oop_file("/path/to/project.oop")
    for step in profile.steps:
        await positioner.move_to(step.azimuth_deg, step.elevation_deg)

    # 生成 MIMO-First 格式的 OOP (用于与 GCM 交叉验证)
    profile = generate_oop_file(
        model_name="UMa CDL-C NLOS",
        azimuth_steps=[0, 15, 30, ...],
        pas_rotation_deg=7.5,
    )
    profile.save("/path/to/mimo_first_output.oop")
"""

import logging
import os
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


# ===========================================================================
# 数据类
# ===========================================================================

@dataclass
class OOPStep:
    """OOP 文件中的单个方向步骤"""
    time_s: float                # 时间戳 (秒)
    azimuth_deg: float           # 目标方位角 (度)
    elevation_deg: float = 0.0   # 目标仰角 (度)
    speed_deg_s: float = 5.0     # 转台转速 (度/秒)

    def to_dict(self) -> Dict[str, float]:
        return {
            "time_s": self.time_s,
            "azimuth_deg": self.azimuth_deg,
            "elevation_deg": self.elevation_deg,
            "speed_deg_s": self.speed_deg_s,
        }


@dataclass
class OOPProfile:
    """
    完整的 OTA Orientation Profile

    包含元数据 (信道模型、PAS 旋转角等) 和一系列方向步骤。
    可从 .oop 文件解析，也可由 MIMO-First 编排层生成。
    """
    # 元数据
    model_name: str = ""
    pas_rotation_deg: float = 0.0
    creation_date: str = ""
    source: str = "unknown"      # "gcm" 或 "mimo_first"
    comments: List[str] = field(default_factory=list)

    # 方向步骤序列
    steps: List[OOPStep] = field(default_factory=list)

    @property
    def total_duration_s(self) -> float:
        """总测试时长 (秒)"""
        if not self.steps:
            return 0.0
        return self.steps[-1].time_s

    @property
    def num_steps(self) -> int:
        return len(self.steps)

    @property
    def azimuth_range(self) -> tuple:
        """方位角范围 (min, max)"""
        if not self.steps:
            return (0.0, 0.0)
        azimuths = [s.azimuth_deg for s in self.steps]
        return (min(azimuths), max(azimuths))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "pas_rotation_deg": self.pas_rotation_deg,
            "creation_date": self.creation_date,
            "source": self.source,
            "num_steps": self.num_steps,
            "total_duration_s": self.total_duration_s,
            "azimuth_range": self.azimuth_range,
            "steps": [s.to_dict() for s in self.steps],
        }

    def save(self, filepath: str) -> None:
        """
        保存为 .oop 格式文件。

        Args:
            filepath: 输出文件路径
        """
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            # 写入元数据注释
            f.write(f"# OTA Orientation Profile\n")
            f.write(f"# Source: {self.source}\n")
            f.write(f"# Model: {self.model_name}\n")
            f.write(f"# PAS Rotation: {self.pas_rotation_deg} deg\n")
            f.write(f"# Date: {self.creation_date or datetime.now().isoformat()}\n")
            f.write(f"# Steps: {self.num_steps}\n")
            for comment in self.comments:
                f.write(f"# {comment}\n")
            f.write(f"#\n")
            f.write(f"# time_s, azimuth_deg, elevation_deg, speed_deg_s\n")

            # 写入数据行
            for step in self.steps:
                f.write(
                    f"{step.time_s:.3f}, "
                    f"{step.azimuth_deg:.1f}, "
                    f"{step.elevation_deg:.1f}, "
                    f"{step.speed_deg_s:.1f}\n"
                )

        logger.info(f"[OOP] Saved {self.num_steps} steps to {filepath}")


# ===========================================================================
# 解析 (GCM → MIMO-First)
# ===========================================================================

def parse_oop_file(filepath: str) -> OOPProfile:
    """
    解析 GCM 生成的 .oop 文件。

    支持的格式:
    1. 标准 CSV 格式: time_s, azimuth_deg, elevation_deg[, speed_deg_s]
    2. 带注释头的扩展格式: # 开头的元数据行

    Args:
        filepath: .oop 文件路径

    Returns:
        OOPProfile 对象

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 文件格式错误
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"OOP file not found: {filepath}")

    profile = OOPProfile(source="gcm")
    profile.creation_date = datetime.now().isoformat()

    with open(filepath, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()

            # 跳过空行
            if not line:
                continue

            # 解析注释行 (元数据)
            if line.startswith("#"):
                _parse_comment_line(line, profile)
                continue

            # 解析数据行
            try:
                step = _parse_data_line(line)
                profile.steps.append(step)
            except ValueError as e:
                logger.warning(
                    f"[OOP] Line {line_num} parse error: {e} → '{line}'"
                )
                continue

    logger.info(
        f"[OOP] Parsed {filepath}: {profile.num_steps} steps, "
        f"model={profile.model_name}, "
        f"PAS rotation={profile.pas_rotation_deg}°"
    )
    return profile


def _parse_comment_line(line: str, profile: OOPProfile) -> None:
    """解析 # 开头的注释/元数据行"""
    content = line.lstrip("#").strip()

    if not content:
        return

    # 尝试提取键值对
    if ":" in content:
        key, _, value = content.partition(":")
        key = key.strip().lower()
        value = value.strip()

        if key == "model":
            profile.model_name = value
        elif key in ("pas rotation", "pas_rotation"):
            try:
                # 提取数值部分 (去掉 "deg" 等单位)
                num_str = value.split()[0] if value else "0"
                profile.pas_rotation_deg = float(num_str)
            except (ValueError, IndexError):
                pass
        elif key == "date":
            profile.creation_date = value
        elif key == "source":
            profile.source = value
        else:
            profile.comments.append(content)
    else:
        profile.comments.append(content)


def _parse_data_line(line: str) -> OOPStep:
    """
    解析单行数据。

    支持的分隔符: 逗号, 制表符, 空格
    """
    # 尝试不同的分隔符
    for sep in [",", "\t", None]:
        parts = line.split(sep) if sep else line.split()
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) >= 3:
            break

    if len(parts) < 3:
        raise ValueError(f"Expected at least 3 columns, got {len(parts)}")

    time_s = float(parts[0])
    azimuth_deg = float(parts[1])
    elevation_deg = float(parts[2])
    speed_deg_s = float(parts[3]) if len(parts) > 3 else 5.0

    return OOPStep(
        time_s=time_s,
        azimuth_deg=azimuth_deg,
        elevation_deg=elevation_deg,
        speed_deg_s=speed_deg_s,
    )


# ===========================================================================
# 生成 (MIMO-First → .oop)
# ===========================================================================

def generate_oop_file(
    model_name: str,
    azimuth_steps: List[float],
    elevation_steps: Optional[List[float]] = None,
    pas_rotation_deg: float = 0.0,
    dwell_time_s: float = 1.2,
    speed_deg_s: float = 5.0,
    source: str = "mimo_first",
) -> OOPProfile:
    """
    生成 MIMO-First 格式的 OOP Profile。

    用于:
    - 与 GCM Native 模式下的 .oop 文件进行交叉验证
    - 导出到第三方转台控制系统
    - 提供给 Commissioning 首测服务的转台控制序列

    Args:
        model_name: 信道模型名称 (e.g., "UMa CDL-C NLOS")
        azimuth_steps: 方位角序列 (度)
        elevation_steps: 仰角序列 (度, 默认全为 0°)
        pas_rotation_deg: PAS 旋转偏移 (度, 由 pas_rotation.py 计算)
        dwell_time_s: 每个方位角的驻留时间 (秒)
        speed_deg_s: 转台转速 (度/秒)
        source: 来源标识

    Returns:
        OOPProfile 对象
    """
    if elevation_steps is None:
        elevation_steps = [0.0] * len(azimuth_steps)

    if len(elevation_steps) != len(azimuth_steps):
        raise ValueError(
            f"azimuth_steps ({len(azimuth_steps)}) 和 "
            f"elevation_steps ({len(elevation_steps)}) 长度不一致"
        )

    profile = OOPProfile(
        model_name=model_name,
        pas_rotation_deg=pas_rotation_deg,
        creation_date=datetime.now().isoformat(),
        source=source,
        comments=[
            f"Generated by MIMO-First Channel Engine",
            f"Dwell time: {dwell_time_s}s, Speed: {speed_deg_s} deg/s",
        ],
    )

    current_time = 0.0
    for i, (az, el) in enumerate(zip(azimuth_steps, elevation_steps)):
        # 应用 PAS 旋转补偿 (反向旋转)
        compensated_az = (az - pas_rotation_deg) % 360.0

        profile.steps.append(OOPStep(
            time_s=round(current_time, 3),
            azimuth_deg=round(compensated_az, 1),
            elevation_deg=round(el, 1),
            speed_deg_s=speed_deg_s,
        ))

        # 下一步的时间 = 驻留时间 + 移动时间
        if i < len(azimuth_steps) - 1:
            next_az = (azimuth_steps[i + 1] - pas_rotation_deg) % 360.0
            move_time = abs(next_az - compensated_az) / speed_deg_s
            current_time += dwell_time_s + move_time

    logger.info(
        f"[OOP] Generated {profile.num_steps} steps for {model_name}, "
        f"PAS offset={pas_rotation_deg}°, "
        f"total={profile.total_duration_s:.1f}s"
    )
    return profile


# ===========================================================================
# 工具函数
# ===========================================================================

def convert_oop_to_positioner_commands(
    profile: OOPProfile,
) -> List[Dict[str, Any]]:
    """
    将 OOP Profile 转换为 Positioner HAL 命令序列。

    供 CommissioningService 或测试执行器直接使用。

    Returns:
        命令列表: [{
            "command": "move_to",
            "azimuth": float,
            "elevation": float,
            "wait_s": float,        # 到达后驻留时间
            "expected_time_s": float # 预计到达时刻
        }]
    """
    commands = []
    for i, step in enumerate(profile.steps):
        # 计算驻留时间 (当前步骤到下一步骤的时间差 - 移动时间)
        if i < len(profile.steps) - 1:
            next_step = profile.steps[i + 1]
            dt = next_step.time_s - step.time_s
            move_time = abs(next_step.azimuth_deg - step.azimuth_deg) / step.speed_deg_s
            dwell = max(0.0, dt - move_time)
        else:
            dwell = 1.0  # 最后一步默认驻留 1 秒

        commands.append({
            "command": "move_to",
            "azimuth": step.azimuth_deg,
            "elevation": step.elevation_deg,
            "wait_s": round(dwell, 3),
            "expected_time_s": step.time_s,
        })

    return commands
