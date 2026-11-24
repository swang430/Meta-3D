"""从冻结的实验室准备记录和逐项设备回读生成正式吞吐量统计。"""
import math

from app.hal.base_station import ThroughputMetrics
from app.hal.propsim_f64 import RealPropsimF64Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.schemas.road_test.execution import KPISummary


def real_driver_pair(drivers):
    return (type(drivers.get("baseStation")) is RealUxmDriver
            and type(drivers.get("channelEmulator")) is RealPropsimF64Driver)


def calibrated_setup(mode, setup):
    if mode != "conducted" or not isinstance(setup, dict) or setup.get("ready") is not True:
        return False
    binding = setup.get("binding")
    asset = setup.get("asset")
    if not isinstance(binding, dict) or binding.get("execution_mode") != "real" or binding.get("mock_only"):
        return False
    if not isinstance(asset, dict) or asset.get("mock_only"):
        return False
    preflight = binding.get("real_preflight")
    calibration = preflight.get("calibration") if isinstance(preflight, dict) else None
    return (isinstance(calibration, dict) and calibration.get("applicable") is True
            and bool(setup.get("calibration_id")) and calibration.get("id") == setup["calibration_id"]
            and bool(calibration.get("evidence_sha256")))


def confirmed_throughput_scope(metric, value, rates, *, current=False):
    if metric not in ("dl_throughput_mbps", "ul_throughput_mbps") or not isinstance(rates, ThroughputMetrics):
        return None
    readback_field = metric.replace("_mbps", "_current_mbps") if current else metric
    if (rates.throughput_scope == ThroughputMetrics.SCOPE_PCELL and rates.is_valid(readback_field.removesuffix("_mbps"))
            and value is not None and getattr(rates, readback_field) == value):
        return rates.throughput_scope
    return None


def measured_item(item):
    value = item.get("value")
    metric = item.get("metric")
    if item.get("provenance") != "server_measured":
        return False
    if metric == "connection_state":
        return item.get("source") == RealUxmDriver.__name__ and isinstance(value, bool)
    if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
        return False
    if metric == "playback_position_s":
        return item.get("unit") == "s" and item.get("source") == RealPropsimF64Driver.__name__
    return (metric in ("dl_throughput_mbps", "ul_throughput_mbps") and item.get("unit") == "Mbps"
            and item.get("source") == RealUxmDriver.__name__ and item.get("throughput_scope") == ThroughputMetrics.SCOPE_PCELL)


def throughput_summary(observations):
    result = []
    for metric, name in (("dl_throughput_mbps", "下行吞吐量"), ("ul_throughput_mbps", "上行吞吐量")):
        values = [item["value"] for item in observations if item.get("metric") == metric and measured_item(item)]
        if values:
            result.append(KPISummary(name=name, unit="Mbps", mean=sum(values) / len(values),
                                     min=min(values), max=max(values), passed=None))
    return result
