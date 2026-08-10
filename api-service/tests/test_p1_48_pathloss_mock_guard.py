"""P1-48：要求「真测」路损时，模拟的 VNA 驱动一律拒绝。

治的毛病：那三处原先**只判 vna 是不是 None**，而方法的 docstring 自己就把
`MockVNA` 列在候选驱动里 —— MockVNA 在位时，它 `np.random` 造出来的扫描数据
会被当成实测、算出路损值、**挂着真型号名落库成一张有效的校准证书**。

后果比「报告印了个假数字」重：报告里的「路损验证」由「有没有证书」派生，
所以这张证书会把一处诚实的「未验证」**翻成「已验证」**；而证书还会被后续所有
测试拿去做补偿 —— 假数据从这里扩散。
"""
from __future__ import annotations

import pytest

from app.hal import MockVNA
from app.services.path_loss_calibration_service import _reject_simulated_vna


class _RealLikeVNA:
    """真驱动类不在 mock 白名单里，应当放行。"""


def test_simulated_vna_is_rejected():
    with pytest.raises(RuntimeError) as e:
        _reject_simulated_vna(MockVNA("mock-vna", {"model": "Mock"}), "真测路损")
    msg = str(e.value)
    assert "模拟驱动" in msg
    assert "MockVNA" in msg, "错误里要点名到底是哪个类，否则排查时看不出"


def test_missing_vna_is_rejected():
    with pytest.raises(RuntimeError) as e:
        _reject_simulated_vna(None, "真测路损")
    assert "没有 VNA" in str(e.value)


def test_real_vna_passes():
    """反向：真驱动必须放行 —— 只测拒绝方向的话，写死成永远抛异常也能绿。"""
    _reject_simulated_vna(_RealLikeVNA(), "真测路损")


def test_all_three_real_measurement_paths_use_the_guard():
    """三条要求真测的路径都要过这道关 —— 漏一条那条就还能出假证书。

    让它报错的改法：把任一处的 `_reject_simulated_vna(...)` 换回只判 None。
    """
    import ast
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[1] / "app/services/path_loss_calibration_service.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))

    guarded = sum(
        1 for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id == "_reject_simulated_vna"
    )
    assert guarded >= 3, (
        f"只有 {guarded} 处调用了拒绝函数，应至少 3 处"
        f"（传统 VNA 路径 / 上行 / 下行）—— 漏掉的那条还能用模拟数据出证书"
    )


def test_ce_sa_primary_path_also_rejects_simulated():
    """⭐ 外审抓出：CE+SA 才是主路径，我上一版只拦了 DEPRECATED 的 VNA 旧路径。

    暗室配了 `cable_sgh_to_sa_loss_db` 就走 CE+SA —— 那条路完全绕过 VNA 那道门。
    而 `MockSignalAnalyzer.measure_channel_power()` 返回随机值。

    让它报错的改法：把 CE+SA 那条路上的两句 `_reject_simulated_instrument` 删掉。
    """
    import ast
    import pathlib

    from app.hal import MockSignalAnalyzer
    from app.services.path_loss_calibration_service import _reject_simulated_instrument

    with pytest.raises(RuntimeError) as e:
        _reject_simulated_instrument(
            MockSignalAnalyzer("mock-sa", {"model": "Mock"}), "signalAnalyzer", "真测")
    assert "模拟驱动" in str(e.value)

    # 主路径上真的接了这道关（不是只有函数存在）。
    # 拦截放在**实际取驱动并采集**的那个内层函数里 —— 比拦在外层更靠近生效端。
    # 调用链：_real_path_loss_measurement_via_ce_sa → acquire_sa_power_via_ce_tone
    #        → _acquire_sa_power_via_ce_tone_inner（拦在这）
    src = (pathlib.Path(__file__).resolve().parents[1]
           / "app/services/path_loss_calibration_service.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == "_acquire_sa_power_via_ce_tone_inner"), None)
    assert fn, "找不到实际取 CE/SA 驱动的那个函数 —— 改名了？请更新本门"
    guards = [n for n in ast.walk(fn)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
              and n.func.id == "_reject_simulated_instrument"]
    assert len(guards) >= 2, (
        f"取 CE/SA 驱动的地方只有 {len(guards)} 处拦截，应至少 2 处（CE 与 SA 各一）"
    )

    # 而且主路径确实会走到那里（链路不能断）
    outer = next((n for n in ast.walk(tree)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and n.name == "_real_path_loss_measurement_via_ce_sa"), None)
    assert outer, "找不到 CE+SA 主路径函数"
    reaches = any(
        isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
        and "acquire_sa_power_via_ce_tone" in c.func.attr
        for c in ast.walk(outer)
    )
    assert reaches, "主路径不再走那条采集链了 —— 拦截可能已经被绕开"


def test_error_message_does_not_point_back_to_the_fake_data_path():
    """⭐ 外审抓出：我原先给的第二条出路是错的。

    `use_mock=True` 走 mock 测量后证书**仍然写成 VALID**，
    `vna_model="Mock VNA"` 只是文本标记，`get_latest_calibration()` 照样选中它做补偿。
    那条「出路」会把被门拦下的操作员直接引回同一条假数据链。

    让它报错的改法：把那句建议加回错误信息里。
    """
    from app.hal import MockVNA
    from app.services.path_loss_calibration_service import _reject_simulated_vna

    with pytest.raises(RuntimeError) as e:
        _reject_simulated_vna(MockVNA("mock-vna", {"model": "Mock"}), "真测")
    msg = str(e.value)
    assert "use_mock=True" not in msg, (
        f"错误信息里又出现了 use_mock=True 这条出路 —— 它会把人引回假数据链：\n{msg}"
    )


def test_b_path_upstream_source_and_rf_switch_also_rejected():
    """⭐ 外审抓出：B 路径的上游信号源、以及射频开关，也都只判了 None。

    - CE/SA 是真机但 BSE/SG 绑模拟驱动 → 它的 set_cw/start_tx 会「成功」，
      SA 读数照样算成 VALID 证书；
    - 模拟开关 `set_mapped_path()` 返回 True 但**物理矩阵根本没切** →
      测的是当前那条错通路，结果却签成目标 chain/probe 的证书。

    让它报错的改法：把这两处的 `_reject_simulated_instrument` 删掉。
    """
    import ast
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[1]
           / "app/services/path_loss_calibration_service.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    for fn_name, expect in [
        ("_acquire_sa_power_via_ce_tone_inner", 3),   # CE + SA + 上游源
        ("_route_switch_to_chain", 1),                # 射频开关
    ]:
        fn = next((n for n in ast.walk(tree)
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and n.name == fn_name), None)
        assert fn, f"找不到 {fn_name} —— 改名了？请更新本门"
        got = len([n for n in ast.walk(fn)
                   if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id == "_reject_simulated_instrument"])
        assert got >= expect, (
            f"{fn_name} 里只有 {got} 处拦截，应至少 {expect} 处 —— "
            f"漏掉的那个仪器是模拟的时候，结果照样会签成有效证书"
        )
