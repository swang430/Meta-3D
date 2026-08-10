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

    # ⚠️ 必须 walk_packages 不是 iter_modules（内审 F1 实跑证伪）：
    #   iter_modules 只列**一层**，`app/hal/vendor_x/ghost.py` 里的 Mock 类扫不到 ——
    #   门的 docstring 声称的域是"app.hal 里所有 Mock* 驱动类"，用 iter_modules
    #   就等于 docstring 本身是假陈述。
    modules = [app.hal]
    unimportable: list[str] = []
    for mod_info in pkgutil.walk_packages(app.hal.__path__, prefix="app.hal."):
        try:
            modules.append(importlib.import_module(mod_info.name))
        except Exception as exc:  # noqa: BLE001
            # ⚠️ 绝不静默 continue（外审 P2）：某个 HAL 模块在 CI 缺可选依赖而在生产
            #   能加载时，静默跳过会让整个模块脱离扫描 —— 门在 CI 绿着，生产里却漏着
            #   一个继承了 real/False 的 mock。**扫不全就不是一次成功的门。**
            unimportable.append(f"{mod_info.name}: {type(exc).__name__}: {exc}")
    assert not unimportable, (
        "以下 app.hal 模块无法导入，本门的扫描域不完整，结果不可信：\n  "
        + "\n  ".join(unimportable)
    )

    found: set[type] = set()
    for module in modules:
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if not issubclass(obj, InstrumentDriver) or obj is InstrumentDriver:
                continue
            # 只认住在 app.hal 包里的类（排除 import 进来的第三方/基类）。
            # ⚠️ 必须同时认 `app.hal` 本身（内审 F3）：
            #   `'app.hal'.startswith('app.hal.')` 是 **False**，
            #   光判前缀会漏掉直接定义在 `app/hal/__init__.py` 里的类。
            mod_name = getattr(obj, "__module__", "")
            if mod_name == "app.hal" or mod_name.startswith("app.hal."):
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
    """② 真驱动**注册表里**的每一个类都必须自称 real（反向，防把常量写反）。

    让它红的变异：给任一真驱动加 `simulated = True`。

    ⚠️ **已知入口域边界（内审 F4，如实申报而非假装覆盖）**：本条的域是
    `_real_driver_registry()`，**不是** app.hal 里的全部真驱动类。今天两者恰好重合
    （实测 app.hal 共 28 个驱动类 = 6 抽象 + 7 mock + 14 真，14 个真驱动全在注册表内），
    但将来新增一个**未注册**的真驱动，本条看不见它。
    之所以接受这个边界：真驱动的默认值（`real`/`False`）本身就在安全侧，
    要出事得有人主动把它写反 —— 与门① 那侧（漏声明即自称真机）的代价不对称。
    """
    assert cls.driver_source == "real", (
        f"{cls.__name__} 在真驱动注册表里却自称 {cls.driver_source!r}"
    )
    assert cls.simulated is False, (
        f"{cls.__name__} 的 simulated 是 {cls.simulated!r}，应为 False"
    )


def _mock_fallback_class_names() -> set[str]:
    """从 `_initialize_from_db` 的源码里 AST 提取 `MOCK_FALLBACK` 的值集（类名）。

    ⚠️ **为什么读它**（外审 P1 指正）：`MOCK_FALLBACK` 是**驱动装载时真正查的那张表**
    （`_MOCK_DRIVER_CLASSES` 的注释自己写着 "the method-local one used at driver-load time"），
    而 `_MOCK_DRIVER_CLASSES` 只是给外部调用方问"这是不是真驱动"用的副本。
    两者必须恒等 —— 否则 HAL 会装上一个 `is_mock_driver()` 判成真机的 mock。

    ⚠️ **为什么用 AST 而不是把它提级成模块级常量**：提级要改生产代码，属"加机制"；
    本门只需读那张表的内容，AST 解析是"换源"，不动生产代码。
    """
    import ast
    import inspect
    import textwrap

    from app.services.instrument_hal_service import InstrumentHALService

    src = textwrap.dedent(inspect.getsource(InstrumentHALService._initialize_from_db))
    tree = ast.parse(src)
    # ⚠️ 外审 R2-P1a：原实现读到**第一个**字面量就 return，后面一句
    #    `MOCK_FALLBACK.update({...})` 或条件重新赋值它完全看不见 → 门恒绿。
    #    所以先把「本门赖以成立的前提」逐条查掉，任一不成立即硬失败。
    literal_nodes, later_touches, local_imports = [], [], []
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.AnnAssign) and node.target is not None:
            targets = [node.target]
        elif isinstance(node, ast.Assign):
            targets = node.targets
        for t in targets:
            if isinstance(t, ast.Name) and t.id == "MOCK_FALLBACK":
                literal_nodes.append(node)
            if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) \
                    and t.value.id == "MOCK_FALLBACK":
                later_touches.append(f"下标赋值 line {getattr(node, 'lineno', '?')}")
        # ⚠️ 只把**会改内容**的方法算成 mutation。`.get()` / `.values()` / `.items()`
        #    是只读的，把它们算进来会造成误红 —— 而误红的最省事转绿方式是放宽断言，
        #    那正好把门掏空（本门第一版就踩了这个，红在生产代码正常的 .get()/.values() 上）。
        _MUTATING = {"update", "setdefault", "pop", "popitem", "clear"}
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and isinstance(node.func.value, ast.Name) \
                and node.func.value.id == "MOCK_FALLBACK" \
                and node.func.attr in _MUTATING:
            later_touches.append(f".{node.func.attr}() line {getattr(node, 'lineno', '?')}")
        # 局部 import 能把**不同的类**绑到已有名字上（外审 R2-P1b）。
        # ⚠️ 但方法内本来就有多处为避开循环导入的局部 import（生产代码的合法写法），
        #    所以判据不是"有没有局部 import"，而是"它绑定的名字**是否与 MOCK_FALLBACK
        #    用到的名字相交**" —— 相交才有可能把另一个类顶替进来。
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                local_imports.append((bound, getattr(node, "lineno", "?")))

    assert literal_nodes, (
        "在 _initialize_from_db 里找不到 MOCK_FALLBACK —— 它被改名或挪走了？"
        "本门依赖它做真值源，请更新本门而不是删掉这条断言"
    )
    assert len(literal_nodes) == 1, (
        f"MOCK_FALLBACK 被赋值 {len(literal_nodes)} 次 —— 本门只解析静态字面量，"
        f"运行时的有效映射可能与第一个不同。请改解析方式，别放宽这条"
    )
    assert not later_touches, (
        f"MOCK_FALLBACK 在字面量之后还被改动过：{later_touches} —— "
        f"本门看不见这些改动，运行时可能装上未列入权威表的 mock。请改解析方式，别放宽这条"
    )
    value = literal_nodes[0].value
    assert isinstance(value, ast.Dict), (
        "MOCK_FALLBACK 不再是字典字面量，本门的 AST 解析已失效 —— "
        "不要放宽这条断言，去改解析方式"
    )
    names = set()
    for v in value.values:
        assert isinstance(v, ast.Name), (
            f"MOCK_FALLBACK 的值出现了非简单名字的表达式 "
            f"({ast.dump(v)[:80]})，本门解析不了，请更新解析方式"
        )
        names.add(v.id)

    shadowed = [(b, ln) for b, ln in local_imports if b in names]
    assert not shadowed, (
        f"方法内的局部 import 绑定了 MOCK_FALLBACK 用到的名字：{shadowed} —— "
        f"它可能把**另一个类**顶替进来，而本门按名字解析到模块全局的那个类，"
        f"会解析成不同的东西。请改解析方式（读有效映射），别放宽这条断言"
    )
    return names
    raise AssertionError(
        "在 _initialize_from_db 里找不到 MOCK_FALLBACK —— 它被改名或挪走了？"
        "本门依赖它做真值源，请更新本门而不是删掉这条断言"
    )


def test_g19_mock_fallback_matches_authoritative_table():
    """④ 运行时真正装载用的 MOCK_FALLBACK，其值集必须等于权威白名单。

    这一条守的是外审 P1 指出的洞：门③ 按"类名 + 包位置"推断谁是 mock，
    而**真正生效的那一端**是 `MOCK_FALLBACK`。一个 `SimulatedVNA`、或从别的包
    import 进来的 `MockVendorVNA`，接进 `MOCK_FALLBACK` 却漏进 `_MOCK_DRIVER_CLASSES`，
    门③ 看不见 —— 而运行时 HAL 会装上它，`is_mock_driver()` 判成真机，
    它造的数就穿过了所有按真假判定的门。

    让它红的变异：
      - 往 `MOCK_FALLBACK` 加一项而不加进 `_MOCK_DRIVER_CLASSES` → 红；
      - 从 `MOCK_FALLBACK` 删一项（权威表仍有）→ 红。
    """
    from app.services import instrument_hal_service as svc_mod
    from app.services.instrument_hal_service import is_mock_driver

    # ⚠️ 外审 R2-P1b：只比**名字**的话，「同名不同类」会让两边差集都空、门全绿。
    #    名字不是生效端，类对象才是 —— 解析成类对象再比身份。
    fallback_classes = set()
    for name in sorted(_mock_fallback_class_names()):
        assert hasattr(svc_mod, name), (
            f"MOCK_FALLBACK 里的 {name} 在 instrument_hal_service 模块命名空间解析不到 —— "
            f"本门无法确认它是哪个类，请更新解析方式"
        )
        fallback_classes.add(getattr(svc_mod, name))

    declared = set(_MOCK_DRIVER_CLASSES)
    only_in_fallback = fallback_classes - declared
    only_in_table = declared - fallback_classes

    assert not only_in_fallback, (
        f"这些类装载时会被当 mock 装上，却不在 _MOCK_DRIVER_CLASSES 里："
        f"{sorted(c.__name__ for c in only_in_fallback)} —— is_mock_driver() 判它们是真机"
    )
    assert not only_in_table, (
        f"这些类在权威表里，却不在装载时的 MOCK_FALLBACK 里："
        f"{sorted(c.__name__ for c in only_in_table)} —— 两张表已分叉"
    )

    # 末了直接问**运行时真正生效的那个函数**（外审建议的第二条路）
    for cls in sorted(fallback_classes, key=lambda c: c.__name__):
        probe = cls.__new__(cls)  # 不跑 __init__，只验 isinstance 判定
        assert is_mock_driver(probe), (
            f"{cls.__name__} 装载时会被当 mock 用，但 is_mock_driver() 判它不是 mock"
        )


def test_g19_mock_table_covers_every_mock_class_in_hal():
    """③ 集合等式：权威 mock 表 == app.hal 里所有名字以 Mock 开头的驱动类。

    这一条守的是「新增 Mock 类漏进表」——①② 都是遍历表，表里没有的类它们看不见。

    让它红的变异：
      - 新写一个 `MockFoo(InstrumentDriver)` 放进 app.hal 而不加进表 → 红；
      - 把某个类从表里删掉（它仍在 app.hal 里）→ 红。
    """
    all_hal_drivers = _scan_hal_driver_classes()
    scanned_mock_named = {c for c in all_hal_drivers if c.__name__.startswith("Mock")}
    declared = set(_MOCK_DRIVER_CLASSES)

    missing_from_table = scanned_mock_named - declared
    # ⚠️ stale 那半必须对**全集**判，不能对 `Mock*` 子集判（内审 F2 实跑证伪）：
    #   一个行为是 mock 但没按 Mock* 命名的类（如 `SimulatedVNA`），**正确地**进了权威表，
    #   对子集判会报"表里但包扫描不到（改名了？删了？）" —— 做对了反而红。
    #   而面对这条误红，最省事的转绿做法是**把它从表里删掉**，那恰好让
    #   is_mock_driver() 判它是真机 = 放行。门绝不能把人往不安全那侧推。
    stale_in_table = declared - all_hal_drivers

    assert not missing_from_table, (
        f"这些 Mock 驱动类在 app.hal 里，却不在 _MOCK_DRIVER_CLASSES 表里："
        f"{sorted(c.__name__ for c in missing_from_table)} —— "
        f"is_mock_driver() 会把它们判成真机"
    )
    assert not stale_in_table, (
        f"这些类在表里但 app.hal 包扫描不到（改名了？删了？）："
        f"{sorted(c.__name__ for c in stale_in_table)}"
    )
