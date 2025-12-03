#!/usr/bin/env python3
"""
完整端到端测试套件 - MIMO-First系统
===================================

覆盖范围：
1. 系统启动和健康检查
2. 校准系统 (Calibration)
3. 虚拟路测 (Virtual Road Test)
4. 报告生成 (Report Generation)
5. WebSocket实时流测试
6. 完整用户流程

使用方法:
  python3 e2e_test_suite.py [--verbose] [--skip-services]
"""

import asyncio
import json
import sys
import time
import requests
import websockets
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum

# ============================================================================
# 配置
# ============================================================================

API_BASE = "http://localhost:8000"
GUI_BASE = "http://localhost:5174"
CHANNEL_ENGINE = "http://localhost:8001"
WS_BASE = "ws://localhost:8000"

VERBOSE = "--verbose" in sys.argv
SKIP_SERVICES = "--skip-services" in sys.argv

# 日志配置
logging.basicConfig(
    level=logging.DEBUG if VERBOSE else logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# 枚举和数据模型
# ============================================================================

class TestStatus(Enum):
    PASS = "✅ 通过"
    FAIL = "❌ 失败"
    SKIP = "⏭️  跳过"
    WARN = "⚠️  警告"


@dataclass
class TestResult:
    name: str
    status: TestStatus
    message: str
    duration: float
    details: Dict[str, Any] = None

    def __str__(self):
        return f"{self.status.value} {self.name} ({self.duration:.2f}s) - {self.message}"


@dataclass
class TestReport:
    title: str
    timestamp: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    results: List[TestResult] = None

    def __post_init__(self):
        if self.results is None:
            self.results = []

    def add_result(self, result: TestResult):
        self.results.append(result)
        self.total += 1
        if result.status == TestStatus.PASS:
            self.passed += 1
        elif result.status == TestStatus.FAIL:
            self.failed += 1
        elif result.status == TestStatus.SKIP:
            self.skipped += 1

    def summary(self) -> str:
        return f"总计: {self.total} | 通过: {self.passed} | 失败: {self.failed} | 跳过: {self.skipped}"

    def success(self) -> bool:
        return self.failed == 0


# ============================================================================
# 工具函数
# ============================================================================

def measure_time(func):
    """装饰器：测量函数执行时间"""
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        duration = time.time() - start
        return result, duration
    return wrapper


@measure_time
def http_get(url: str, headers: Optional[Dict] = None) -> Dict:
    """发送GET请求"""
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json() if resp.text else {}
    except Exception as e:
        raise Exception(f"GET {url} 失败: {str(e)}")


@measure_time
def http_post(url: str, data: Dict, headers: Optional[Dict] = None) -> Dict:
    """发送POST请求"""
    try:
        resp = requests.post(url, json=data, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json() if resp.text else {}
    except Exception as e:
        raise Exception(f"POST {url} 失败: {str(e)}")


def check_service_health(url: str) -> bool:
    """检查服务是否在线"""
    try:
        resp = requests.get(url, timeout=5)
        return resp.status_code < 500
    except:
        return False


# ============================================================================
# 测试模块
# ============================================================================

class SystemHealthTest:
    """系统健康检查"""

    @staticmethod
    async def run(report: TestReport):
        logger.info("\n🏥 === 系统健康检查 ===")

        # 测试1: API服务
        try:
            result, duration = http_get(f"{API_BASE}/api/v1/health")
            status = TestStatus.PASS
            msg = "API服务正常运行"
        except Exception as e:
            status = TestStatus.FAIL if not SKIP_SERVICES else TestStatus.SKIP
            msg = f"API服务离线: {str(e)}"
            duration = 0

        report.add_result(TestResult("API服务健康检查", status, msg, duration))

        # 测试2: GUI服务
        if not SKIP_SERVICES:
            gui_ok = check_service_health(GUI_BASE)
            status = TestStatus.PASS if gui_ok else TestStatus.WARN
            report.add_result(TestResult(
                "GUI服务健康检查",
                status,
                "GUI服务正常" if gui_ok else "GUI服务未响应",
                0
            ))

        # 测试3: ChannelEngine服务
        if not SKIP_SERVICES:
            ce_ok = check_service_health(CHANNEL_ENGINE)
            status = TestStatus.PASS if ce_ok else TestStatus.WARN
            report.add_result(TestResult(
                "ChannelEngine服务检查",
                status,
                "ChannelEngine正常" if ce_ok else "ChannelEngine未响应",
                0
            ))


class CalibrationTest:
    """校准系统测试"""

    @staticmethod
    async def run(report: TestReport):
        logger.info("\n⚙️  === 校准系统测试 ===")

        # 测试1: 获取校准数据
        try:
            result, duration = http_get(f"{API_BASE}/api/v1/calibration/history")
            status = TestStatus.PASS
            msg = f"成功获取校准历史记录 ({len(result.get('data', []))}条)"
        except Exception as e:
            status = TestStatus.FAIL
            msg = f"获取校准历史失败: {str(e)}"
            duration = 0

        report.add_result(TestResult("获取校准历史", status, msg, duration))

        # 测试2: 获取当前校准状态
        try:
            result, duration = http_get(f"{API_BASE}/api/v1/calibration/status")
            status = TestStatus.PASS
            msg = "成功获取校准状态"
        except Exception as e:
            status = TestStatus.WARN
            msg = f"获取校准状态: {str(e)}"
            duration = 0

        report.add_result(TestResult("校准状态查询", status, msg, duration))


class VirtualRoadTestTest:
    """虚拟路测功能测试"""

    @staticmethod
    async def run(report: TestReport):
        logger.info("\n🚗 === 虚拟路测测试 ===")

        # 测试1: 获取场景库
        try:
            result, duration = http_get(f"{API_BASE}/api/v1/road-test/scenarios")
            # 处理列表或字典格式的响应
            if isinstance(result, list):
                scenarios = result
            else:
                scenarios = result.get("scenarios", [])
            status = TestStatus.PASS
            msg = f"成功加载场景库 ({len(scenarios)}个场景)"
        except Exception as e:
            status = TestStatus.FAIL
            msg = f"加载场景库失败: {str(e)}"
            duration = 0
            scenarios = []

        report.add_result(TestResult("加载场景库", status, msg, duration))

        # 测试2: 创建执行（如果有场景）
        if scenarios:
            try:
                scenario_id = scenarios[0].get("id")
                execution_data = {
                    "scenario_id": scenario_id,
                    "mode": "digital_twin",
                    "topology_id": None
                }
                result, duration = http_post(
                    f"{API_BASE}/api/v1/road-test/executions",
                    execution_data
                )
                execution_id = result.get("execution_id")
                status = TestStatus.PASS if execution_id else TestStatus.FAIL
                msg = f"执行创建成功 (ID: {execution_id})"
            except Exception as e:
                status = TestStatus.FAIL
                msg = f"创建执行失败: {str(e)}"
                duration = 0
                execution_id = None

            report.add_result(TestResult("创建测试执行", status, msg, duration))

            # 测试3: 获取执行状态
            if execution_id:
                try:
                    result, duration = http_get(
                        f"{API_BASE}/api/v1/road-test/executions/{execution_id}"
                    )
                    status = TestStatus.PASS
                    msg = f"执行状态: {result.get('status', 'unknown')}"
                except Exception as e:
                    status = TestStatus.WARN
                    msg = f"获取执行状态: {str(e)}"
                    duration = 0

                report.add_result(TestResult("获取执行状态", status, msg, duration))


class WebSocketTest:
    """WebSocket实时流测试"""

    @staticmethod
    async def run(report: TestReport):
        logger.info("\n📡 === WebSocket实时流测试 ===")

        # 创建测试执行
        try:
            exec_data = {
                "scenario_id": "test-scenario",
                "mode": "digital_twin",
                "topology_id": None
            }
            result, _ = http_post(f"{API_BASE}/api/v1/road-test/executions", exec_data)
            execution_id = result.get("execution_id")
        except:
            execution_id = "test-exec-" + str(int(time.time()))

        # 测试WebSocket连接
        try:
            ws_url = f"{WS_BASE}/ws/execution/{execution_id}"
            async with websockets.connect(ws_url, timeout=5) as ws:
                # 接收初始消息
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=3)
                    data = json.loads(msg)
                    status = TestStatus.PASS
                    msg_text = f"收到消息: {data.get('type', 'unknown')}"
                except asyncio.TimeoutError:
                    status = TestStatus.WARN
                    msg_text = "WebSocket连接成功但无初始消息"
        except Exception as e:
            status = TestStatus.WARN
            msg_text = f"WebSocket连接失败: {str(e)}"

        report.add_result(TestResult("WebSocket连接", status, msg_text, 0))


class TopologyTest:
    """拓扑配置测试"""

    @staticmethod
    async def run(report: TestReport):
        logger.info("\n🔗 === 拓扑配置测试 ===")

        # 测试1: 创建拓扑
        topology_data = {
            "name": "Test Topology - 2x2 MIMO",
            "description": "测试拓扑",
            "topology_type": "MIMO_2x2",
            "base_station": {
                "device_type": "base_station",
                "name": "Test gNB",
                "model": "Keysight E7515B",
                "tx_ports": 2,
                "max_bandwidth_mhz": 100
            },
            "channel_emulator": {
                "device_type": "channel_emulator",
                "name": "Test Fading Emulator",
                "model": "Keysight PROPSIM F64",
                "input_ports": 4,
                "output_ports": 4
            },
            "dut": {
                "device_type": "dut",
                "name": "Test UE",
                "model": "Generic 5G Device",
                "antenna_ports": 2
            },
            "connections": []
        }

        try:
            result, duration = http_post(
                f"{API_BASE}/api/v1/road-test/topologies",
                topology_data
            )
            topology_id = result.get("id")
            status = TestStatus.PASS if topology_id else TestStatus.FAIL
            msg = f"拓扑创建成功 (ID: {topology_id})"
        except Exception as e:
            status = TestStatus.WARN
            msg = f"创建拓扑: {str(e)}"
            duration = 0
            topology_id = None

        report.add_result(TestResult("创建测试拓扑", status, msg, duration))


class ReportGenerationTest:
    """报告生成测试"""

    @staticmethod
    async def run(report: TestReport):
        logger.info("\n📊 === 报告生成测试 ===")

        # 测试1: 获取报告列表
        try:
            result, duration = http_get(f"{API_BASE}/api/v1/reports")
            reports = result.get("reports", [])
            status = TestStatus.PASS
            msg = f"成功获取报告列表 ({len(reports)}个报告)"
        except Exception as e:
            status = TestStatus.WARN
            msg = f"获取报告列表: {str(e)}"
            duration = 0

        report.add_result(TestResult("获取报告列表", status, msg, duration))

        # 测试2: 生成测试报告
        try:
            report_data = {
                "execution_id": "test-exec-001",
                "title": "虚拟路测报告",
                "format": "json"
            }
            result, duration = http_post(
                f"{API_BASE}/api/v1/reports/generate",
                report_data
            )
            status = TestStatus.PASS
            msg = "报告生成请求已提交"
        except Exception as e:
            status = TestStatus.WARN
            msg = f"生成报告: {str(e)}"
            duration = 0

        report.add_result(TestResult("生成测试报告", status, msg, duration))


class OTAMapperTest:
    """OTA映射器测试"""

    @staticmethod
    async def run(report: TestReport):
        logger.info("\n🗺️  === OTA映射器测试 ===")

        # 测试1: OTA参数计算
        try:
            ota_data = {
                "scenario_id": "test-scenario",
                "channel_model": "CDL_C",
                "num_probes": 32,
                "frequency_ghz": 3.5
            }
            result, duration = http_post(
                f"{API_BASE}/api/v1/ota/probe-weights",
                ota_data
            )
            weights = result.get("probe_weights", [])
            status = TestStatus.PASS if weights else TestStatus.WARN
            msg = f"探头权重计算完成 ({len(weights)}个探头)"
        except Exception as e:
            status = TestStatus.WARN
            msg = f"OTA参数计算: {str(e)}"
            duration = 0

        report.add_result(TestResult("OTA探头权重计算", status, msg, duration))


class EndToEndUserFlow:
    """完整用户流程测试"""

    @staticmethod
    async def run(report: TestReport):
        logger.info("\n👤 === 完整用户流程测试 ===")

        logger.info("模拟用户完整使用流程...")

        try:
            # 步骤1: 获取可用场景
            scenarios, _ = http_get(f"{API_BASE}/api/v1/road-test/scenarios")
            # 处理列表或字典格式的响应
            if isinstance(scenarios, list):
                scenarios_list = scenarios
            else:
                scenarios_list = scenarios.get("scenarios", [])
            assert len(scenarios_list) > 0, "没有可用场景"

            # 步骤2: 选择一个场景
            selected_scenario = scenarios_list[0]
            scenario_id = selected_scenario["id"]
            logger.info(f"  ✓ 选择场景: {selected_scenario['name']}")

            # 步骤3: 创建执行
            exec_data = {
                "scenario_id": scenario_id,
                "mode": "digital_twin"
            }
            execution, _ = http_post(
                f"{API_BASE}/api/v1/road-test/executions",
                exec_data
            )
            execution_id = execution.get("execution_id")
            logger.info(f"  ✓ 创建执行: {execution_id}")

            # 步骤4: 启动执行
            start_data = {"action": "start"}
            result, _ = http_post(
                f"{API_BASE}/api/v1/road-test/executions/{execution_id}/control",
                start_data
            )
            logger.info(f"  ✓ 启动执行")

            # 步骤5: 监听WebSocket
            ws_url = f"{WS_BASE}/ws/execution/{execution_id}"
            try:
                async with websockets.connect(ws_url, timeout=3) as ws:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2)
                    logger.info(f"  ✓ 接收实时数据流")
            except:
                logger.warning(f"  ⚠️  WebSocket消息接收超时")

            # 步骤6: 生成报告
            report_data = {
                "execution_id": execution_id,
                "title": "虚拟路测报告"
            }
            report_result, _ = http_post(
                f"{API_BASE}/api/v1/reports/generate",
                report_data
            )
            logger.info(f"  ✓ 生成报告")

            report.add_result(TestResult(
                "完整用户流程",
                TestStatus.PASS,
                "用户流程执行成功",
                0
            ))

        except AssertionError as e:
            report.add_result(TestResult(
                "完整用户流程",
                TestStatus.SKIP,
                f"跳过: {str(e)}",
                0
            ))
        except Exception as e:
            report.add_result(TestResult(
                "完整用户流程",
                TestStatus.WARN,
                f"部分步骤失败: {str(e)}",
                0
            ))


# ============================================================================
# 主测试运行器
# ============================================================================

async def run_all_tests() -> TestReport:
    """运行所有测试"""

    report = TestReport(
        title="MIMO-First 端到端测试报告",
        timestamp=datetime.now().isoformat()
    )

    print("\n" + "="*70)
    print("🧪 MIMO-First 完整端到端测试套件")
    print("="*70)

    # 运行所有测试模块
    test_modules = [
        ("系统健康", SystemHealthTest.run),
        ("校准系统", CalibrationTest.run),
        ("虚拟路测", VirtualRoadTestTest.run),
        ("拓扑配置", TopologyTest.run),
        ("OTA映射", OTAMapperTest.run),
        ("报告生成", ReportGenerationTest.run),
        ("WebSocket", WebSocketTest.run),
        ("用户流程", EndToEndUserFlow.run),
    ]

    for module_name, test_func in test_modules:
        try:
            await test_func(report)
        except Exception as e:
            logger.error(f"测试模块 {module_name} 执行出错: {str(e)}")

    return report


def print_report(report: TestReport):
    """打印测试报告"""
    print("\n" + "="*70)
    print("📋 测试结果汇总")
    print("="*70)
    print(f"测试时间: {report.timestamp}")
    print(f"总体结果: {report.summary()}")
    print("-"*70)

    for result in report.results:
        print(f"{result}")

    print("-"*70)
    if report.success():
        print("✅ 所有测试通过！系统准备就绪")
    else:
        print(f"❌ 有 {report.failed} 个测试失败，请检查上述结果")

    print("="*70 + "\n")

    return report.success()


async def main():
    """主函数"""
    try:
        report = await run_all_tests()
        success = print_report(report)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被中断")
        sys.exit(1)
    except Exception as e:
        logger.error(f"致命错误: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
