"""
Coordinate System Utilities

在 API Service 的坐标系和 Channel Engine 的坐标系之间进行转换。

API Service (Probe 模型):
    azimuth:   方位角 (0° ~ 360°)
    elevation: 仰角 (-90° ~ 90°), 0°=水平, 90°=正上, -90°=正下

Channel Engine (ProbePosition 模型):
    theta: 天顶角 (0° ~ 180°), 0°=北极(正上), 90°=水平, 180°=南极(正下)
    phi:   方位角 (0° ~ 360°)

转换关系:
    theta = 90 - elevation
    elevation = 90 - theta
    phi = azimuth (不变)
"""
import math
from typing import Dict, Tuple, Optional


def elevation_to_theta(elevation_deg: float) -> float:
    """
    将仰角 (elevation) 转换为天顶角 (theta)

    Args:
        elevation_deg: 仰角 (-90° ~ 90°)

    Returns:
        天顶角 (0° ~ 180°)
    """
    theta = 90.0 - elevation_deg
    if theta < 0 or theta > 180:
        raise ValueError(
            f"Invalid elevation {elevation_deg}°: "
            f"converted theta={theta}° is out of range [0°, 180°]"
        )
    return theta


def theta_to_elevation(theta_deg: float) -> float:
    """
    将天顶角 (theta) 转换为仰角 (elevation)

    Args:
        theta_deg: 天顶角 (0° ~ 180°)

    Returns:
        仰角 (-90° ~ 90°)
    """
    elevation = 90.0 - theta_deg
    if elevation < -90 or elevation > 90:
        raise ValueError(
            f"Invalid theta {theta_deg}°: "
            f"converted elevation={elevation}° is out of range [-90°, 90°]"
        )
    return elevation


def probe_db_to_channel_engine(
    azimuth: float,
    elevation: float,
    radius: float
) -> Dict[str, float]:
    """
    将 DB 探头坐标转换为 Channel Engine 坐标

    Args:
        azimuth: 方位角 (0° ~ 360°)
        elevation: 仰角 (-90° ~ 90°)
        radius: 半径 (m)

    Returns:
        {"theta": float, "phi": float, "r": float}
    """
    return {
        "theta": elevation_to_theta(elevation),
        "phi": azimuth,
        "r": radius,
    }


def channel_engine_to_probe_db(
    theta: float,
    phi: float,
    r: float
) -> Dict[str, float]:
    """
    将 Channel Engine 坐标转换为 DB 探头坐标

    Args:
        theta: 天顶角 (0° ~ 180°)
        phi: 方位角 (0° ~ 360°)
        r: 半径 (m)

    Returns:
        {"azimuth": float, "elevation": float, "radius": float}
    """
    return {
        "azimuth": phi,
        "elevation": theta_to_elevation(theta),
        "radius": r,
    }


def spherical_to_cartesian(
    azimuth_deg: float,
    elevation_deg: float,
    radius: float
) -> Tuple[float, float, float]:
    """
    球坐标 (azimuth, elevation, radius) 转换为笛卡尔坐标 (x, y, z)

    使用右手坐标系:
        x = r * cos(el) * sin(az)
        y = r * cos(el) * cos(az)
        z = r * sin(el)

    Args:
        azimuth_deg: 方位角 (度)
        elevation_deg: 仰角 (度)
        radius: 半径 (m)

    Returns:
        (x, y, z) 坐标 (m)
    """
    az_rad = math.radians(azimuth_deg)
    el_rad = math.radians(elevation_deg)

    x = radius * math.cos(el_rad) * math.sin(az_rad)
    y = radius * math.cos(el_rad) * math.cos(az_rad)
    z = radius * math.sin(el_rad)

    return (x, y, z)


def validate_probe_in_chamber(
    probe_position: Dict[str, float],
    chamber_radius_m: float,
    tolerance_m: float = 0.01
) -> Tuple[bool, Optional[str]]:
    """
    验证探头位置是否与暗室半径一致

    Args:
        probe_position: 探头位置 {"azimuth", "elevation", "radius"}
        chamber_radius_m: 暗室半径 (m)
        tolerance_m: 容差 (m)

    Returns:
        (is_valid, error_message)
    """
    probe_radius = probe_position.get("radius", 0)

    if abs(probe_radius - chamber_radius_m) > tolerance_m:
        return (
            False,
            f"探头半径 ({probe_radius:.3f}m) 与暗室半径 "
            f"({chamber_radius_m:.3f}m) 不一致 "
            f"(差异: {abs(probe_radius - chamber_radius_m):.3f}m)"
        )

    # 验证仰角范围
    elevation = probe_position.get("elevation", 0)
    if elevation < -90 or elevation > 90:
        return (False, f"仰角 {elevation}° 超出有效范围 [-90°, 90°]")

    # 验证方位角范围
    azimuth = probe_position.get("azimuth", 0)
    if azimuth < 0 or azimuth > 360:
        return (False, f"方位角 {azimuth}° 超出有效范围 [0°, 360°]")

    return (True, None)
