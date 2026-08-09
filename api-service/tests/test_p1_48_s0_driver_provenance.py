"""P1-48 S0 门：驱动类的真假标记必须跟权威表一致。

背景：`driver_source` / `simulated` 两个 ClassVar 是 P1-37 引入的仪表粒度真假标记。
基类默认 `real` / `False`，Mock 子类应当覆盖成 `mock` / `True`。
2026-08-09 勘察发现 `MockVNA` 与 `MockSignalGenerator` **漏了覆盖**，
于是这两个模拟驱动在标记上**自称真机** —— 它们 `np.random` 造的数可被下游判成实测。

⚠️ 本门的三条断言**全部从生产表派生，不手写清单** —— 手写清单正是上一版
（`test_p1_37_mock_scpi_logging.py` 逐个 import 那 5 个类）漏掉这两个类的原因。
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil

import pytest

from app.hal.base import InstrumentDriver
from app.services.instrument_hal_service import (
    _MOCK_DRIVER_CLASSES,
    _real_driver_registry,
)


def _scan_hal_driver_classes() -> set[type]:
    """包扫描 app.hal，返回其中**定义于 app.hal 包内**的全部驱动类。

    ⚠️ 刻意**不用** `InstrumentDriver.__subclasses__()`：那会把别的测试文件里
    临时定义的子类一并捞进来，造成"单文件跑绿、全量跑红"的假红
    （跟 alembic 那次 logger 污染同形）。这里按模块名过滤，只认真正住在
    `app.hal` 包里的类。
    """
    import app.hal

    found: set[type] = set()
    for mod_info in pkgutil.iter_modules(app.hal.__path__, prefix="app.hal."):
        module = importlib.import_module(mod_info.name)
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if not issubclass(obj, InstrumentDriver) or obj is InstrumentDriver:
                continue
            # 只认在 app.hal 包里定义的（排除 import 进来的第三方/基类）
            if getattr(obj, "__module__", "").startswith("app.hal."):
                found.add(obj)
    return found


@pytest.mark.parametrize("cls", _MOCK_DRIVER_CLASSES, ids=lambda c: c.__name__)
def test_g19_every_mock_driver_declares_itself_mock(cls):
    """① 权威 mock 表里的**每一个**类都必须自称 mock。

    让它红的变异：删掉任一 Mock 类的 `simulated = True` 或 `driver_source = "mock"`。
    """
    assert cls.driver_source == "mock", (
        f"{cls.__name__} 的 driver_source 是 {cls.driver_source!r}，"
        f"它在 _MOCK_DRIVER_CLASSES 里却自称真机 —— "
        f"下游按这个字段判真假的地方会把它造的数当实测"
    )
    assert cls.simulated is True, (
        f"{cls.__name__} 的 simulated 是 {cls.simulated!r}，应为 True"
    )


def _all_real_driver_classes() -> list[type]:
    registry = _real_driver_registry()
    return sorted(
        {cls for by_model in registry.values() for cls in by_model.values()},
        key=lambda c: c.__name__,
    )


@pytest.mark.parametrize(
    "cls", _all_real_driver_classes(), ids=lambda c: c.__name__
)
def test_g19_every_real_driver_declares_itself_real(cls):
    """② 真驱动注册表里的**每一个**类都必须自称 real（反向，防把常量写反）。

    让它红的变异：给任一真驱动加 `simulated = True`。
    """
    assert cls.driver_source == "real", (
        f"{cls.__name__} 在真驱动注册表里却自称 {cls.driver_source!r}"
    )
    assert cls.simulated is False, (
        f"{cls.__name__} 的 simulated 是 {cls.simulated!r}，应为 False"
    )


def test_g19_mock_table_covers_every_mock_class_in_hal():
    """③ 集合等式：权威 mock 表 == app.hal 里所有名字以 Mock 开头的驱动类。

    这一条守的是「新增 Mock 类漏进表」——①② 都是遍历表，表里没有的类它们看不见。

    让它红的变异：
      - 新写一个 `MockFoo(InstrumentDriver)` 放进 app.hal 而不加进表 → 红；
      - 把某个类从表里删掉（它仍在 app.hal 里）→ 红。
    """
    scanned = {c for c in _scan_hal_driver_classes() if c.__name__.startswith("Mock")}
    declared = set(_MOCK_DRIVER_CLASSES)

    missing_from_table = scanned - declared
    stale_in_table = declared - scanned

    assert not missing_from_table, (
        f"这些 Mock 驱动类在 app.hal 里，却不在 _MOCK_DRIVER_CLASSES 表里："
        f"{sorted(c.__name__ for c in missing_from_table)} —— "
        f"is_mock_driver() 会把它们判成真机"
    )
    assert not stale_in_table, (
        f"这些类在表里但 app.hal 包扫描不到（改名了？删了？）："
        f"{sorted(c.__name__ for c in stale_in_table)}"
    )
