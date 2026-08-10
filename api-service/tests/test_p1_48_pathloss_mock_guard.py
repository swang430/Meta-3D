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
