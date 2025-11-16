#!/usr/bin/env python3
"""
Test script for Channel Engine Service
Tests health check and probe weight generation endpoints
"""

import httpx
import json
import sys

BASE_URL = "http://localhost:8000"


def test_health_check():
    """测试健康检查端点"""
    print("=" * 60)
    print("测试 1: 健康检查")
    print("=" * 60)

    try:
        response = httpx.get(f"{BASE_URL}/api/v1/health")
        print(f"状态码: {response.status_code}")
        print(f"响应:\n{json.dumps(response.json(), indent=2, ensure_ascii=False)}")

        if response.status_code == 200:
            print("✓ 健康检查测试通过")
            return True
        else:
            print("✗ 健康检查测试失败")
            return False

    except Exception as e:
        print(f"✗ 健康检查测试失败: {e}")
        return False


def test_probe_weight_generation():
    """测试探头权重生成端点"""
    print("\n" + "=" * 60)
    print("测试 2: 探头权重生成")
    print("=" * 60)

    # 构建测试请求 - 8个探头的简单环形阵列
    request_data = {
        "scenario": {
            "scenario_type": "UMa",
            "cluster_model": "CDL-C",
            "frequency_mhz": 3500,
            "use_median_lsps": False
        },
        "probe_array": {
            "num_probes": 8,
            "radius": 3.0,
            "probe_positions": [
                {"probe_id": 1, "theta": 90, "phi": 0, "r": 3.0, "polarization": "V"},
                {"probe_id": 2, "theta": 90, "phi": 45, "r": 3.0, "polarization": "V"},
                {"probe_id": 3, "theta": 90, "phi": 90, "r": 3.0, "polarization": "V"},
                {"probe_id": 4, "theta": 90, "phi": 135, "r": 3.0, "polarization": "V"},
                {"probe_id": 5, "theta": 90, "phi": 180, "r": 3.0, "polarization": "V"},
                {"probe_id": 6, "theta": 90, "phi": 225, "r": 3.0, "polarization": "V"},
                {"probe_id": 7, "theta": 90, "phi": 270, "r": 3.0, "polarization": "V"},
                {"probe_id": 8, "theta": 90, "phi": 315, "r": 3.0, "polarization": "V"}
            ]
        },
        "mimo_config": {
            "num_tx_antennas": 2,
            "num_rx_antennas": 2,
            "tx_antenna_spacing": 0.5,
            "rx_antenna_spacing": 0.5
        }
    }

    print("请求配置:")
    print(f"- 场景: {request_data['scenario']['scenario_type']} + {request_data['scenario']['cluster_model']}")
    print(f"- 频率: {request_data['scenario']['frequency_mhz']} MHz")
    print(f"- 探头数量: {request_data['probe_array']['num_probes']}")
    print(f"- MIMO: {request_data['mimo_config']['num_tx_antennas']}T{request_data['mimo_config']['num_rx_antennas']}R")

    try:
        response = httpx.post(
            f"{BASE_URL}/api/v1/ota/generate-probe-weights",
            json=request_data,
            timeout=30.0
        )
        print(f"\n状态码: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print(f"\n✓ 探头权重生成成功!")
            print(f"\n信道统计信息:")
            stats = result['channel_statistics']
            print(f"  - 路径损耗: {stats['pathloss_db']:.2f} dB")
            print(f"  - 信道条件: {stats['condition']}")
            print(f"  - 簇数量: {stats['num_clusters']}")

            print(f"\n前3个探头权重:")
            for i, weight in enumerate(result['probe_weights'][:3]):
                print(f"  探头 #{weight['probe_id']}:")
                print(f"    - 幅度: {weight['weight']['magnitude']:.4f}")
                print(f"    - 相位: {weight['weight']['phase_deg']:.2f}°")
                print(f"    - 启用: {weight['enabled']}")

            print(f"\n消息: {result['message']}")
            return True
        else:
            print(f"✗ 探头权重生成失败")
            print(f"响应:\n{json.dumps(response.json(), indent=2, ensure_ascii=False)}")
            return False

    except Exception as e:
        print(f"✗ 探头权重生成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_root_endpoint():
    """测试根端点"""
    print("\n" + "=" * 60)
    print("测试 3: 根端点")
    print("=" * 60)

    try:
        response = httpx.get(f"{BASE_URL}/")
        print(f"状态码: {response.status_code}")
        print(f"响应:\n{json.dumps(response.json(), indent=2, ensure_ascii=False)}")

        if response.status_code == 200:
            print("✓ 根端点测试通过")
            return True
        else:
            print("✗ 根端点测试失败")
            return False

    except Exception as e:
        print(f"✗ 根端点测试失败: {e}")
        return False


if __name__ == '__main__':
    print("=" * 60)
    print("Channel Engine Service - 端到端测试")
    print("=" * 60)
    print("\n⚠️  请确保服务正在运行:")
    print("   cd /home/user/Meta-3D/channel-engine-service")
    print("   source ../ChannelEgine/.venv/bin/activate")
    print("   python -m app.main")
    print("\n")

    # 运行测试
    results = []
    results.append(("根端点", test_root_endpoint()))
    results.append(("健康检查", test_health_check()))
    results.append(("探头权重生成", test_probe_weight_generation()))

    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"{name}: {status}")

    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    print(f"\n总计: {passed_count}/{total_count} 测试通过")

    if passed_count == total_count:
        print("\n🎉 所有测试通过! 服务运行正常。")
        sys.exit(0)
    else:
        print("\n⚠️  部分测试失败，请检查服务配置。")
        sys.exit(1)
