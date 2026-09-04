# -*- coding: utf-8 -*-
"""P2-57：信道仿真器能力 manifest 的门。

⚠️ **这些门一律从代码结构（AST）派生，不靠「跑一遍 Mock 看通不通」。**
理由是本片故障的成因本身：`ChannelEmulatorDriver` 的 14 个抽象方法整段掉在
类体之外（嵌在模块级函数 `normalize_channel_model_entries` 内，自 2026-05-13），
而 **F64 与 Mock 各自实现了全部 14 个**，把缺陷完全掩盖 —— 行为门恒绿三个多月。
所以守它的必须是结构不变量。
"""

import ast
import importlib
import inspect
import pathlib

import pytest

from app.hal.channel_emulator import ChannelEmulatorDriver, ChannelLoadMode
from app.hal.channel_emulator_manifest import (
    CHANNEL_EMULATOR_OPERATIONS,
    channel_emulator_rejection,
    ChannelEmulatorLoadModeCapability,
    ChannelEmulatorManifest,
    ChannelEmulatorOperationCapability,
    channel_emulator_implements,
    channel_emulator_manifest_for,
    channel_emulator_manifest_of,
    channel_emulator_operation_names,
)
from app.hal.propsim_f64 import RealPropsimF64Driver
from app.hal.propsim_fs16 import RealPropsimFs16Driver


_APP = pathlib.Path(__file__).resolve().parents[1] / "app"

#: ⚠️ **从代码派生，不手写**（内审 F4）：初版手写了 f64 / fs16 两家，把
#: `MockChannelEmulator` 排除在对账之外 —— 而它在 mock 模式下是**生产驱动**
#: （`instrument_hal_service`），且「F64 与 Mock 各自实现了全集」正是本片那个
#: 结构缺陷藏了三个多月的原因。把 Mock 排除，等于把同一个盲点留了一半。
#:
#: ⚠️ **但只靠 `__subclasses__()` 有两个洞**（内审 R2 F3，探针实测）：
#:   ① 它只返回**直接**子类 —— `class F64Variant(RealPropsimF64Driver)` 完全
#:      不出现，而它继承 F64 的 manifest，三道门一道也看不见它；
#:   ② 它只看**已经 import 的**模块 —— 于是覆盖面等于「这个测试文件恰好
#:      import 了谁」。第 4 个驱动写在新模块、没人加 import，门静默不覆盖，
#:      而 `assert _DRIVERS` 依旧为真（假门的第 5 种形态：判定器取数不全）。
#: 所以先按**源码**找出该有谁（AST，含跨模块的传递继承），import 进来，
#: 再递归收集 —— 两个洞一起堵。


def _driver_class_names_from_source() -> dict[tuple[str, str], None]:
    """AST 扫全 `app/`：所有（传递）继承 `ChannelEmulatorDriver` 的类的 (模块, 类名)。

    传递闭包：先建「类名 → (模块, 基类名集合)」，再从 `ChannelEmulatorDriver`
    出发迭代到不动点，这样 `F64Variant(RealPropsimF64Driver)` 也会被收进来。
    """
    # ⚠️ key 必须是 **(模块, 类名)**，不能只用裸类名（内审 R3 F1 实测）：
    #    `app/services/mock_instruments.py` 里有一个**同名的非 CE 类**
    #    `class MockChannelEmulator:`，而 `sorted(rglob)` 下它排在 `app/hal/`
    #    之后 —— 裸类名做 key 时它把真驱动挤掉，于是 `MockChannelEmulator`
    #    根本不在期望集里，下面那句「取数不全的门是假门」自检对它恒真空。
    #    也就是说：本轮想关的「没人 import 就看不见」那个洞，对 Mock 一格没关上。
    defs: dict[tuple[str, str], set[str]] = {}
    for path in sorted(_APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module = path.relative_to(_APP.parent).with_suffix("").as_posix().replace("/", ".")
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            defs[(module, node.name)] = {
                b.id if isinstance(b, ast.Name) else b.attr
                for b in node.bases
                if isinstance(b, (ast.Name, ast.Attribute))
            }

    found: dict[tuple[str, str], None] = {}
    frontier = {"ChannelEmulatorDriver"}
    while frontier:
        nxt = set()
        for (module, name), bases in defs.items():
            if (module, name) in found or name in frontier:
                continue
            if bases & frontier:
                found[(module, name)] = None
                nxt.add(name)
        frontier = nxt
    return found


def _all_channel_emulator_drivers() -> dict:
    """`ChannelEmulatorDriver` 的全部具体子类（含间接） → (类, 源文件, 类名)。"""
    expected = _driver_class_names_from_source()
    for module, _name in sorted(expected):
        importlib.import_module(module)      # 关掉「没人 import 就看不见」那个洞

    def _walk(root):
        for cls in root.__subclasses__():
            yield cls
            yield from _walk(cls)            # 关掉「只看直接子类」那个洞

    # ⚠️ key 用 **(模块, 类名)**，且只收 `app/` 下的类（内审 R4 F5/F6）：
    #    · 裸类名做 key 时，两个同名 CE 驱动分处两模块会**一起**塌成一个 ——
    #      `expected` 与 `out` 以同样方式塌陷，双向相等照样为绿，门静默只覆盖一个
    #      （R3 F1 只修了 `defs` 那一半，这里补齐另一半）；
    #    · 不滤到 `app/` 时，任何在**模块级**定义 CE 子类的测试文件都会被拉进
    #      三道参数化门（`driver.adapter_manifest` 直接 AttributeError），类若在
    #      `api-service` 之外还会让 `relative_to` 抛 ValueError 直接收集失败。
    #      那是**恒红**——比恒绿更容易招来「加个白名单绕过」，门就名存实亡了。
    out = {}
    for cls in _walk(ChannelEmulatorDriver):
        # 取不到源码的类跳过 —— 它不可能是 `app/` 下的生产驱动。
        # ⚠️ **守的是 `TypeError`/`OSError`，不是 `None`**（实测，Python 3.13）：
        #    · `exec("class K(Base): pass", …)` → `__module__` 变 `'builtins'`，
        #      `getsourcefile` **抛 `TypeError: … is a built-in class`**；
        #    · `type("X", (F64,), {})` → `__module__` 变 `'abc'`（ABCMeta.__new__
        #      的调用帧），返回**真路径** `.../abc.py`，被下面的 `is_relative_to`
        #      挡掉，跟本 guard 无关。
        #    外审 #448 C1 提的是「返回 None 就跳过」，而上面两种机制**一种返回
        #    真路径、一种抛异常，都不返回 None** —— 按它写等于没守（内审实测：
        #    把 guard 改回裸 `assert` 仍 31 passed 全绿）。这里按实测的形态守。
        #    真驱动万一取不到源码也不会被放过：`expected` 纯 AST 派生、与
        #    `getsourcefile` 无关，下面那条双向相等断言会以「只在 AST 里：[...]」
        #    把它点名（内审变异实证）。
        try:
            src = inspect.getsourcefile(cls)
        except (TypeError, OSError):
            continue
        if not src:
            # 返回 None 的两种实测形态：`.so` 扩展类，以及 `__file__` 指向一个
            # 不存在的 .py 且模块无 loader。都不可能由生产 CE 驱动触发 ——
            # 这半个 guard 今天是纯防御，无用例覆盖（内审 M1 实证），如实记。
            continue
        path = pathlib.Path(src)
        if not path.is_relative_to(_APP):
            continue                         # 测试里临时定义的子类不参与对账
        rel = path.relative_to(_APP.parent).as_posix()
        module = rel[: -len(".py")].replace("/", ".")
        out[(module, cls.__name__)] = (cls, rel, cls.__name__)

    # ⚠️ 判据必须是**双向相等**，不能只查 `expected - out`（内审 R3 F1 的教训）：
    #    单向版本对「AST 少认了一个驱动」是**恒真空**的 —— 而那正是 F1 的形态
    #    （裸类名做 key，被排序靠后的同名类挤掉）。少认一个，门就静默不覆盖它，
    #    断言却依旧为绿。这是假门的第 5 种形态：判定器自己的取数不全。
    #    `out` 先滤到 `app/` 下 —— 测试里临时定义的驱动子类不参与对账。
    assert set(out) == set(expected), (
        f"AST 期望的 CE 驱动集合与运行期收集到的不等 —— 取数不全的门是假门。"
        f"\n  只在 AST 里：{sorted(set(expected) - set(out))}"
        f"\n  只在运行期：{sorted(set(out) - set(expected))}"
    )
    return out


_DRIVERS = _all_channel_emulator_drivers()


def _is_pure_refusal(owner, op: str) -> bool:
    """`owner` 上的 `op` 是不是一个「函数体只有 raise NotImplementedError」的自写桩。"""
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(owner)))
    fn = next(
        (n for n in tree.body[0].body
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == op),
        None,
    )
    return fn is not None and _body_is_pure_refusal(fn.body)


def _body_is_pure_refusal(stmts) -> bool:
    """这段函数体/分支体去掉 docstring 后，是不是只剩一条 `raise NotImplementedError`。"""
    body = [
        st for st in stmts
        if not (isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant)
                and isinstance(st.value.value, str))          # 去掉 docstring
    ]
    if len(body) != 1 or not isinstance(body[0], ast.Raise):
        return False
    exc = body[0].exc
    if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
        return exc.func.id == "NotImplementedError"
    return isinstance(exc, ast.Name) and exc.id == "NotImplementedError"


def _implemented_operations(cls) -> set[str]:
    """该类**有效实现**了哪些操作 —— MRO 找到定义方，再看它是不是个拒绝桩。

    ⚠️ 判据不用「类自己的方法名」（纯 AST）：薄子类是合法写法 ——
    `class F64Variant(RealPropsimF64Driver): pass` 继承了 F64 的全部实现，
    纯 AST 版会把它误判成「什么都没实现」而误伤。

    ⚠️ 也不能只判「解析到的函数 ≠ 基类的桩」（内审 R3 F3 实测）：那样一来，
    驱动**自己写一个明确的拒绝**——
    `async def stop_emulation(self): raise NotImplementedError("FS16 无仿真引擎")`
    ——就会被门逼着声明 `implemented`，而声明 implemented 会让
    `channel_emulator_implements` 翻 True、cleanup 真去调它、`measure.py` 的
    fail-loud 门放行。**门把 manifest 推向 fail-open，方向正是本片要治的那一侧。**
    所以自写的纯拒绝桩与继承来的基类桩同等对待：都不算实现。

    仍是结构判据（MRO + AST），不跑任何代码。
    """
    out = set()
    for op in CHANNEL_EMULATOR_OPERATIONS:
        owner = next((k for k in cls.__mro__ if op in k.__dict__), None)
        if owner is None or owner is ChannelEmulatorDriver:
            continue
        if _is_pure_refusal(owner, op):
            continue
        out.add(op)
    return out


def _dispatched_load_modes(cls) -> set[str]:
    """该类**有效的** `load_channel` 实际派发了哪些模式（AST 读那个函数体）。

    这是 load mode 的结构真值源：`load_channel` 里没有分支的模式，
    声明「支持」就是空头承诺 —— 调用方按声明选中它，最后拿到
    `NotImplementedError` 或 `return False`。
    """
    owner = next(k for k in cls.__mro__ if "load_channel" in k.__dict__)
    tree = ast.parse(
        pathlib.Path(inspect.getsourcefile(owner)).read_text(encoding="utf-8")
    )
    cls_node = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and n.name == owner.__name__
    )
    fn = next(
        n for n in cls_node.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "load_channel"
    )
    # ⚠️ 只收**分支条件**里的枚举引用（内审 R3 F4 实测）：原来收整个函数体，
    #    于是在拒绝文案的 f-string 里写一句
    #    `f"不支持 {ChannelLoadMode.PARAMETRIC_TDL.value}"` 就能让门放行 ——
    #    而「在拒绝信息里点名不支持的模式」是完全自然的写法，不是刻意绕。
    # ⚠️ 只认**分支条件**里的枚举引用，且该分支**不能是纯拒绝**（内审 R3 F4 / R4 F4）：
    #    · 收整个函数体 → 在拒绝文案 f-string 里点名该模式就能放行（自然写法，非刻意绕）；
    #    · 只收 `Compare` 仍不够 → `if mode == X: raise NotImplementedError(...)`
    #      本身就是个 Compare，而「用比较式拒绝一个模式」比在文案里点名更自然。
    #    ⚠️ `match/case` 与字典派发目前看不见 —— 那两种会让本门**假红**（保守侧），
    #      不会放行谎报；真要用那些写法时按同一判据扩，别加白名单。
    modes: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.If) or _body_is_pure_refusal(node.body):
            continue
        modes |= {
            n.attr.lower() for n in ast.walk(node.test)
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
            and n.value.id == "ChannelLoadMode"
        }
    return modes


def _own_methods(rel_path: str, class_name: str) -> set[str]:
    """该类**自己**定义的方法名（不含继承来的）—— AST 派生，不实例化。"""
    tree = ast.parse((_APP.parent / rel_path).read_text(encoding="utf-8"))
    cls = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and n.name == class_name
    )
    return {
        x.name for x in cls.body
        if isinstance(x, (ast.AsyncFunctionDef, ast.FunctionDef))
    }


# --------------------------------------------------------------------------
# 1. 结构不变量：抽象接口必须真的在类上
# --------------------------------------------------------------------------


def test_every_operation_is_actually_a_method_on_the_base_class():
    """14 个抽象操作必须**真的挂在 `ChannelEmulatorDriver` 上**。

    ⚠️ 这道门直接钉住本片的根因。它们曾整段掉在类体之外 ——
    `hasattr(ChannelEmulatorDriver, "upload_asc_files")` 为 `False`，
    于是未实现的驱动抛的是不受控的 `AttributeError`，而不是
    `NotImplementedError`；FS16 的文件头当时还写着「fall through to the
    abstract base's NotImplementedError」，那句是假的。

    变异：把任一方法移出类体（缩进到别的构造里）→ 本门红。
    """
    missing = [
        name for name in CHANNEL_EMULATOR_OPERATIONS
        if name not in _own_methods("app/hal/channel_emulator.py", "ChannelEmulatorDriver")
    ]
    assert not missing, (
        f"这些抽象操作不在 ChannelEmulatorDriver 的类体里：{missing}。"
        "检查它们是不是又掉进了某个模块级函数内部。"
    )


def test_operation_literal_matches_the_operation_tuple():
    """`Literal` 取值域与 `CHANNEL_EMULATOR_OPERATIONS` 集合相等。

    两者是同一事实的两处声明（`Literal` 不能从运行期元组构造），
    靠这道门维持一致 —— 加操作只改一处会红。
    """
    assert set(channel_emulator_operation_names()) == set(CHANNEL_EMULATOR_OPERATIONS)
    assert len(CHANNEL_EMULATOR_OPERATIONS) == len(set(CHANNEL_EMULATOR_OPERATIONS))


def test_load_mode_literal_matches_the_runtime_enum():
    """manifest 的 load mode 取值域 == 驱动侧 `ChannelLoadMode` 枚举。

    manifest 模块刻意不 import 驱动模块（驱动要 import manifest），
    所以这份取值域是独立写的第二处 —— 由本门维持相等。
    """
    from typing import get_args

    from app.hal.channel_emulator_manifest import ChannelEmulatorLoadMode

    assert set(get_args(ChannelEmulatorLoadMode)) == {m.value for m in ChannelLoadMode}


# --------------------------------------------------------------------------
# 2. 声明 ⊆ 实现：manifest 不许谎报
# --------------------------------------------------------------------------


@pytest.mark.parametrize("key", sorted(_DRIVERS))
def test_manifest_never_claims_an_operation_the_class_does_not_define(key):
    """声明 `implemented` 的操作，驱动类上必须有**它自己的**定义。

    「继承基类的 NotImplementedError 桩」**不算实现** —— 那正是 P2-57 之后
    `hasattr` 彻底失效的原因（补桩后它对每个驱动恒为真）。所以这道门按
    **类自己的方法集合**（AST）判，不用 `hasattr`。

    变异：给 FS16 的 manifest 把任一未实现操作改成 `implemented` → 红。
    """
    driver, rel, cls_name = _DRIVERS[key]
    # ⚠️ 内审 R2 F3：这里曾用 AST 的「类自己的方法名」，会把合法的薄子类
    #    （继承 F64 实现、自己不定义方法）误判成「什么都没实现」。换源到
    #    MRO 解析后与基类桩的比对 —— 继承来的真实现算实现，继承来的桩不算。
    own = _implemented_operations(driver)
    claimed = {
        item.operation for item in driver.adapter_manifest.operations
        if item.support == "implemented"
    }
    # ⚠️ **两个方向都断言**（内审 F3）：初版只查 `claimed - own`（谎报），
    #    而漏掉的 `own - claimed`（少报）才是危险的那一侧 ——
    #    谎报会抛 NotImplementedError 并被上层记进 warnings（吵闹、看得见）；
    #    少报会让 cleanup 静默不发停机、让 `f64_input_ref_dbm` 静默不下发。
    #    两个方向的代价刚好被摆反了。
    assert sorted(claimed) == sorted(own), (
        f"{cls_name} 的 manifest 与实现不符 —— "
        f"谎报（声明了但类上没有）：{sorted(claimed - own)}；"
        f"少报（实现了却没声明）：{sorted(own - claimed)}"
    )


def test_self_written_refusal_stub_does_not_count_as_implemented():
    """判定器自测：自写的纯拒绝桩**不算实现**，真实现**算**（内审 R4 F1）。

    ⚠️ 变异实证：把 `_is_pure_refusal` 改成恒 `False`（等于整段撤销 R4 前那次
    修复）→ 本文件 28 passed 全绿 —— 因为三个真驱动没有一个写过纯拒绝桩，
    缺陷在当前配置下不可观察。这正是本片反复遇到的形态，所以判定器自己也要被测。

    为什么这条重要：若纯拒绝桩被算成「实现」，对账门就会**逼**作者把 manifest
    改成 `implemented`，而那会让 `channel_emulator_implements` 翻 True、cleanup
    真去调它、`measure.py` 的 fail-loud 门放行 —— 门把 manifest 推向 fail-open，
    方向正是本片要治的那一侧。
    """
    class _RefusesExplicitly(RealPropsimFs16Driver):
        async def stop_emulation(self) -> bool:
            raise NotImplementedError("FS16 无仿真引擎，无需停机")

    class _ReallyImplements(RealPropsimFs16Driver):
        async def stop_emulation(self) -> bool:
            self._stopped = True
            return True

    assert "stop_emulation" not in _implemented_operations(_RefusesExplicitly)
    assert "stop_emulation" in _implemented_operations(_ReallyImplements)

    # docstring 不影响判定；抛别的异常类型不算「拒绝桩」
    class _RaisesSomethingElse(RealPropsimFs16Driver):
        async def stop_emulation(self) -> bool:
            """带 docstring 的真实现（抛的是别的异常）。"""
            raise RuntimeError("transport down")

    assert "stop_emulation" in _implemented_operations(_RaisesSomethingElse)


def test_capability_checks_in_measure_have_no_silent_negative_path():
    """`measure.py` 直通前置的两处能力判定必须是 **fail-loud** 形态（内审 R4 F3）。

    ⚠️ **这是一道粗筛（结构档），不是行为门 —— 如实说明。** 该分支内联在
    `MeasureExecutor` 的大函数里，行为门需要整套 step 脚手架（test_execution /
    db / 基站），本片没建。内审实证：把整段分支删掉，167 个相关用例全绿 ——
    这条路径在本片之前**行为覆盖就是 0**，本片没有改善这一点。

    钉住的事实：`f64_bypass_mode` 块里对 `set_passthrough_mode` 与
    `stop_emulation` 的判定都写成 `if not ce_plan.planned(...)`（P2-59 ① 起读冻结
    计划；此前是 `channel_emulator_implements(...)`）且
    分支体里有 `return`。此前 `stop_emulation` 那格是 `if …:` 无 else ——
    manifest 少报就**不停播放直接进直通**且零留痕，恰好造成它自己注释里说的
    「真因被掩盖成直通建立失败」。

    ⚠️ **已知旁路，如实记（内审 R6 F1 实测）**：本门只看这两格 `if` 自身的形状，
    **不检查它们是否在默认路径上**。把整格 guard 原样包进一个恒假的外层条件
    （内层 AST 一字不动）→ 本文件 30 passed 全绿，而默认路径退回「不停播放
    直接进直通」。要真堵住它得补行为门（整套 step 脚手架），那超出本片目的 ——
    所以这道门的定位是**粗筛**：防「改回静默跳过」这种直接退化，不防蓄意绕过。
    """
    tree = ast.parse(
        (_APP / "services/mimo_ota/executors/measure.py").read_text(encoding="utf-8")
    )
    loud = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.UnaryOp):
            continue
        if not isinstance(node.test.op, ast.Not):
            continue
        call = node.test.operand
        if not isinstance(call, ast.Call) or not call.args:
            continue
        if isinstance(call.func, ast.Attribute) and call.func.attr == "planned":
            op_node = call.args[0]  # P2-59 ①：`ce_plan.planned("<op>")`
        elif (isinstance(call.func, ast.Name)
              and call.func.id == "channel_emulator_implements"):
            op_node = call.args[1] if len(call.args) > 1 else None
        else:
            continue
        op = op_node.value if isinstance(op_node, ast.Constant) else None
        if op not in ("set_passthrough_mode", "stop_emulation"):
            continue
        # ⚠️ 判**最后一条语句**，不 `ast.walk` 整棵子树（内审 R5 F1 实测）：
        #    `walk` 版只能证明「这段里存在一个 return」，证明不了「否定路径必然
        #    return」。变异实证：保留 `if not …:` 外形、里面塞个死分支的 return，
        #    默认路径退回静默跳过 —— 193 passed 全绿。这是"保留 token 的错写法"
        #    绕过存在性门的典型，所以判据必须落到控制流的出口上。
        last = node.body[-1]
        assert isinstance(last, (ast.Return, ast.Raise)), (
            f"measure.py:{node.lineno} 的 {op} 能力判定分支没有 fail-loud 出口 —— "
            f"末句是 {type(last).__name__}，否定路径会继续往下走"
        )
        loud += 1
    assert loud == 2, (
        f"直通前置的 fail-loud 能力判定应有 2 处，实际 {loud} 处 —— "
        "要么被改回静默跳过，要么站点搬走了"
    )


@pytest.mark.parametrize("key", sorted(_DRIVERS))
def test_manifest_covers_every_operation_exactly_once(key):
    """每个驱动都必须逐个声明全部 14 个操作 —— 不许沉默省略。"""
    driver, _, _ = _DRIVERS[key]
    declared = [item.operation for item in driver.adapter_manifest.operations]
    assert sorted(declared) == sorted(CHANNEL_EMULATOR_OPERATIONS)


def test_fs16_declares_no_load_mode_until_playback_is_implemented():
    """FS16 **不宣称任何加载模式** —— 用户 2026-09-02 拍板收窄。

    此前 `get_supported_load_modes()` 返回 `[EXTERNAL_WAVEFORM]`，而
    `upload_asc_files` / `start_emulation` 从未实现 —— 那是把假承诺送进
    了**有 4 个真实消费方**的那个渠道（`load_channel` 自己的门、
    `measure.py` 的 GCM 分支、gcm/b2 两个 strategy）。
    """
    manifest = RealPropsimFs16Driver.adapter_manifest
    assert manifest.supported_load_modes() == ()
    inst = object.__new__(RealPropsimFs16Driver)
    assert RealPropsimFs16Driver.get_supported_load_modes(inst) == []
    # 未实现要给得出可操作理由，而不是让调用方撞 AttributeError
    reason = manifest.rejection_reason("upload_asc_files")
    assert reason and "not_implemented" in reason


def test_load_modes_come_from_the_manifest_not_from_per_driver_overrides():
    """`get_supported_load_modes()` 只有基类一处实现（其余驱动不得重写）。

    重写就是第二个源 —— 本片刚把 F64 / FS16 / Mock 三处重写删掉，
    改由 manifest 派生。
    """
    for rel, cls_name in (
        ("app/hal/propsim_f64.py", "RealPropsimF64Driver"),
        ("app/hal/propsim_fs16.py", "RealPropsimFs16Driver"),
        ("app/hal/channel_emulator.py", "MockChannelEmulator"),
    ):
        assert "get_supported_load_modes" not in _own_methods(rel, cls_name), (
            f"{cls_name} 重写了 get_supported_load_modes —— 那会造出第二个源"
        )


def test_a_driver_without_a_manifest_declares_no_load_mode():
    """没有 manifest 的 CE 子类**一个模式都不宣称**（fail-closed）。

    ⚠️ 内审 R2 F7 / 变异 MU1 实证：把基类的 `get_supported_load_modes()` 改回
    `return [EXTERNAL_WAVEFORM]`（恢复 P2-57 之前的 fail-open），
    `test_p2_57` + `test_diagnostic_sequences` **95 passed 全绿** ——
    因为全仓没有任何用例构造过「无 manifest 的 CE 子类」，缺陷在当前配置下
    不可观察。这条门就是那个缺失的观察点。

    fail-open 的实际代价有案底：FS16 从没实现 `upload_asc_files`，却因为继承
    这个默认值而宣称支持 .asc 上传播放，把假承诺送进了 4 个真实消费方。
    """
    class _NoManifestDriver(ChannelEmulatorDriver):
        # `InstrumentDriver` 的抽象方法给最小桩，纯粹为了能实例化
        async def connect(self): return True
        async def disconnect(self): return True
        async def configure(self, config): return True
        async def get_capabilities(self): return {}
        async def get_metrics(self): return {}
        async def reset(self): return True

    inst = object.__new__(_NoManifestDriver)
    assert inst.get_supported_load_modes() == []


@pytest.mark.parametrize("key", sorted(_DRIVERS))
def test_declared_load_modes_are_actually_dispatched(key):
    """声明 `implemented` 的加载模式，`load_channel` 里必须真有那条分支。

    ⚠️ 内审 R2 F7 / 变异 MU4 实证：让 Mock 的 manifest 谎报 `parametric_tdl`
    已实现 → 三个相关测试文件 **41 passed 全绿**。操作那一维已经双向对账，
    **load mode 这一维当时只有 FS16 一条定值断言**，F64 / Mock 无人对账。

    这里补上它的结构真值源：`load_channel` 的模式派发。没有分支的模式，
    声明「支持」就是空头承诺 —— 调用方按声明选中它，最后拿到
    `NotImplementedError` 或一个静默的 `return False`。
    """
    driver, _, cls_name = _DRIVERS[key]
    declared = set(driver.adapter_manifest.supported_load_modes())
    dispatched = _dispatched_load_modes(driver)
    assert declared <= dispatched, (
        f"{cls_name} 声明支持 {sorted(declared - dispatched)}，"
        f"但它有效的 load_channel 只派发 {sorted(dispatched)}"
    )


# --------------------------------------------------------------------------
# 3. 零 `hasattr` 能力探测
# --------------------------------------------------------------------------


def test_no_capability_probing_via_hasattr_anywhere_in_app():
    """全 `app/` 不得再用 `hasattr` / `getattr` **字面量**探测这 14 个操作。

    ⚠️ 覆盖面有限（内审 F7）：只认第二实参是字符串字面量的形式。
    `hasattr(ce, m)` 这种**变量**形式抓不到 —— `propsim_f64_p08_gate.py` 的
    `_REQUIRED_METHODS` 就曾是活反例（P2-57 已把两个共同操作从那个元组里移出）。
    下面另有一条门专盯「共同操作出现在集合字面量里」这个形态。


    ⚠️ 补桩之后 `hasattr` 对每个驱动恒为真 —— 那些「没有就跳过」的分支会
    全部翻成「调用然后崩」。本片把 8 处换源到 manifest；这道门防它们回来。

    只看**字符串字面量**形式的探测（`hasattr(x, "stop_emulation")`），
    注释与文档串不算 —— 用 AST，不用 grep。
    """
    offenders: list[str] = []
    for path in sorted(_APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        # ⚠️ 收集**全作用域**的字符串常量赋值，不只模块级（变异实证：把
        #    `_OP = "stop_emulation"` 放进函数体内就绕过了只扫 tree.body 的版本）。
        #    对这 14 个很具体的名字来说，任何 `x = "stop_emulation"` 之后
        #    `hasattr(y, x)` 都正是要抓的形态，不存在误伤。
        consts = {
            n.targets[0].id: n.value.value
            for n in ast.walk(tree)
            if isinstance(n, ast.Assign) and len(n.targets) == 1
            and isinstance(n.targets[0], ast.Name)
            and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id not in ("hasattr", "getattr") or len(node.args) < 2:
                continue
            probe = node.args[1]
            name = None
            if isinstance(probe, ast.Constant):
                name = probe.value
            elif isinstance(probe, ast.Name):
                # ⚠️ 也要解析模块级字符串常量（变异 M3 实证：把字面量抽成
                #    `_OP = "stop_emulation"` 再 `hasattr(x, _OP)` 就绕过去了）
                name = consts.get(probe.id)
            if name in CHANNEL_EMULATOR_OPERATIONS:
                offenders.append(f"{path.name}:{node.lineno} {node.func.id}(…, {name!r})")
    assert not offenders, "能力探测必须走 manifest：" + "; ".join(offenders)


# --------------------------------------------------------------------------
# 4. 判定器自测
# --------------------------------------------------------------------------


def test_driver_collection_survives_classes_with_no_source_file():
    """取不到源码的 CE 子类不许让整个门文件在收集期崩掉。

    ⚠️ 内审实证：本 guard 此前**零测试保护**（把它改回裸 `assert src, cls`，
    31 passed 全绿），而且守错了形态 —— 外审说的是「返回 None」，实测
    `exec` 造的类是**抛 `TypeError`**。这条门用真的 `exec` 类钉住实测形态。
    """
    import gc

    ns = {"Base": ChannelEmulatorDriver}
    exec("class _ExecMadeDriver(Base): pass", ns)          # noqa: S102
    try:
        with pytest.raises(TypeError):                      # 前提本身也钉住
            inspect.getsourcefile(ns["_ExecMadeDriver"])
        drivers = _all_channel_emulator_drivers()           # 不许抛
        assert "_ExecMadeDriver" not in {n for _, n in drivers}
    finally:
        ns.clear()
        gc.collect()        # 让它从 __subclasses__() 里消失，别污染别的用例


def test_every_channel_emulator_driver_declares_a_manifest():
    """每个 `ChannelEmulatorDriver` 子类都必须有**类级** `adapter_manifest`。

    ⚠️ 内审 F5：没有这道门时，新增第 4 个 CE 驱动忘写 manifest 会让
    `channel_emulator_implements` 一路返回 False —— 其中 cleanup 的停机是
    **静默跳过**（不吵）。而本片之前 `hasattr` 会找到它自己实现的
    `stop_emulation` 并调用 —— 在那一格上，本片把安全动作从「会做」变成了「不做」。
    """
    assert _DRIVERS, "找不到任何 ChannelEmulatorDriver 子类 —— 派生逻辑坏了"
    # ⚠️ 内审 R2 审计：原写法是 `cls.__dict__.get(...) or getattr(cls, ...)`，
    #    那个 getattr 兜底意味着**基类哪天自己带上 manifest，本门对每个驱动恒真**
    #    —— 退化成存在性档。这里改成先钉住「基类没有」，再允许沿 MRO 继承
    #    （薄子类继承父驱动的 manifest 是合法的）。
    assert "adapter_manifest" not in ChannelEmulatorDriver.__dict__, (
        "ChannelEmulatorDriver 自己带上了 adapter_manifest —— 那会让本门恒真，"
        "每个驱动都能靠继承一个假的共同基线蒙混过关"
    )
    for name, (cls, _, _) in sorted(_DRIVERS.items()):
        manifest = getattr(cls, "adapter_manifest", None)
        assert isinstance(manifest, ChannelEmulatorManifest), (
            f"{name} 没有声明 channel emulator manifest"
        )


def test_instance_level_manifest_is_honored_not_silently_ignored():
    """manifest 挂在**实例**上要被认，不能无声忽略，也不能抛异常。

    ⚠️ 本条是**上一版的反转**（内审 R2 F1/F2 推翻）。上一版让它抛 TypeError，
    三个问题：① 打破 `cleanup_chamber_instruments` 的 `Never raises` —— 探针实测
    抛出会穿出收尾函数，`stop_emulation` 一次没调、warning 也没留，比它要治的
    静默跳过更糟；② 只覆盖「类上没有 + 实例上有」，漏掉更常见的「类上有 +
    实例又覆盖」；③ `channel_emulator_rejection` 在同一个对象上答案相反。

    本仓既有的 `adapter_manifest` 约定本来就是实例级的（`base_station.py`），
    所以两种写法都认；「类级」那条纪律由构建期门负责。
    """
    class _InstanceOnly:
        pass

    obj = _InstanceOnly()
    obj.adapter_manifest = RealPropsimF64Driver.adapter_manifest
    assert channel_emulator_implements(obj, "stop_emulation") is True
    assert channel_emulator_rejection(obj, "stop_emulation") == ""

    # 实例覆盖类上那份 —— 覆盖生效，不被无声忽略
    class _ClassLevel:
        adapter_manifest = RealPropsimF64Driver.adapter_manifest

    inst = _ClassLevel()
    assert channel_emulator_implements(inst, "upload_asc_files") is True
    inst.adapter_manifest = RealPropsimFs16Driver.adapter_manifest
    assert channel_emulator_implements(inst, "upload_asc_files") is False

    # ⚠️ 第三处也要断言（内审 R3 F2 实测）：把 `get_supported_load_modes` 退回
    #    `getattr(type(self), ...)` 时 134 passed 全绿 —— 本门只查了两个查询面，
    #    而「同一对象三处答案不一致」正是要治的病，漏一处等于没治。
    class _LoadModeProbe(ChannelEmulatorDriver):
        adapter_manifest = RealPropsimFs16Driver.adapter_manifest   # 零模式
        async def connect(self): return True
        async def disconnect(self): return True
        async def configure(self, config): return True
        async def get_capabilities(self): return {}
        async def get_metrics(self): return {}
        async def reset(self): return True

    probe = object.__new__(_LoadModeProbe)
    assert probe.get_supported_load_modes() == []
    probe.adapter_manifest = RealPropsimF64Driver.adapter_manifest  # 实例覆盖
    assert probe.get_supported_load_modes() != [], (
        "get_supported_load_modes 没走共享取数函数 —— 实例级 manifest 被无声忽略"
    )


def test_mock_auto_attributes_are_not_mistaken_for_a_manifest():
    """`MagicMock()` / `AsyncMock()` 一律判**不支持**，不能 fail-open。

    ⚠️ 这是把取数从 `type(emulator)` 放宽到 `getattr(emulator, ...)` 时新开的口子：
    Mock 会**自动生成**任意属性，`getattr(mock, "adapter_manifest")` 返回一个
    真值 Mock，只判 `is not None` 就会让每个操作都"支持" —— 而测试替身遍布全仓。
    所以取数判的是 `isinstance(..., ChannelEmulatorManifest)`。

    变异：把 `channel_emulator_manifest_of` 的 isinstance 改回 `is not None` → 本门红。
    """
    from unittest.mock import AsyncMock, MagicMock

    for mock in (MagicMock(), AsyncMock()):
        assert channel_emulator_manifest_of(mock) is None
        assert channel_emulator_implements(mock, "stop_emulation") is False
        assert "没有声明" in channel_emulator_rejection(mock, "stop_emulation")


def test_naming_never_raises_even_for_a_hostile_metaclass():
    """取名字失败必须退化成一个名字，**不能抛**（内审 F3）。

    ⚠️ 这是 R1→R2 那个母题的重演：`channel_emulator_rejection` 的下游是
    `cleanup_chamber_instruments`（明文 `Never raises`），而它在 `measure.py` 的
    `finally:` 里 —— 抛出会顶替掉触发收尾的原始异常。实测：元类把 `__name__`
    定义成会抛的 property 时，新写法 `emulator.__name__` 抛 `RuntimeError`，
    而**旧写法不抛**。收 C2 的时候顺手把抛面放宽了，方向反了。
    """
    class _HostileMeta(type):
        @property
        def __name__(cls):                       # noqa: A003
            raise RuntimeError("取名字都能炸")

    class _Hostile(metaclass=_HostileMeta):
        pass

    reason = channel_emulator_rejection(_Hostile, "stop_emulation")
    assert "stop_emulation" in reason and "fail-closed" in reason


def test_rejection_reason_names_the_real_class_even_for_a_class_object():
    """拒绝理由必须点出**真实类名**，传类对象时不能变成字面量 "type"。

    ⚠️ 外审 #448 C2：`channel_emulator_manifest_of` 对类对象是正常工作的
    （`getattr(cls, "adapter_manifest")` 走得通），所以注册表自检 / 测试脚手架
    传类进来是合理用法。而 `type(emulator).__name__` 那时返回 "type" ——
    一条说了等于没说的理由，恰好抵消了本片「用可读拒绝理由取代不受控
    AttributeError」的全部意义。
    """
    class _NoManifestDriverLike:
        pass

    for target in (_NoManifestDriverLike, _NoManifestDriverLike()):
        reason = channel_emulator_rejection(target, "stop_emulation")
        assert "_NoManifestDriverLike" in reason, reason
        assert not reason.startswith("type "), reason


def test_operation_typos_raise_instead_of_reading_as_unsupported():
    """操作名拼错**当场炸**，不被当成「不支持」（内审 F2）。

    代价不对称：读成「不支持」会让 cleanup 静默跳过停机（仪器可能仍在发射，
    操作员零信号），而拼错本身是个笔误 —— 让它吵。
    """
    f64 = object.__new__(RealPropsimF64Driver)
    assert channel_emulator_implements(f64, "stop_emulation") is True
    with pytest.raises(ValueError):
        channel_emulator_implements(f64, "stop_emulaton")
    with pytest.raises(ValueError):
        channel_emulator_rejection(f64, "stop_emulaton")


def test_no_operation_name_collection_is_iterated_into_hasattr():
    """共同操作的名字不得被**迭代进 `hasattr`**（内审 F1/F7/R2 F6）。

    上面那条门抓的是 `hasattr(ce, "stop_emulation")` —— 第二实参是字面量。
    真实漏网的是另一形态：把名字放进一个集合再迭代
    （`propsim_f64_p08_gate.py` 的 `_REQUIRED_METHODS` 就是活反例）。

    ⚠️ 这道门被**连续绕过三次**，每次都是「判据只认我当时想到的那一种写法」：
      · 推导式 → 加了推导式判据；
      · 集合定义搬进函数体 → 只扫 `tree.body` 的版本失效（内审 R2 F6 实证：
        21 passed 全绿）；
      · 推导式改写成**普通 `for` 循环** → 只认 `ListComp/SetComp/GeneratorExp`
        的版本失效（内审 R2 F6 实证：21 passed 全绿）。
    所以现在判据统一成一句话，与写法无关：**凡是「迭代出来的变量」被喂进
    `hasattr`/`getattr`，就看它的迭代源含不含共同操作名** —— `ast.For` 与三种
    推导式同一条路径，字符串集合从**全作用域**收集。

    ⚠️ 判据刻意**不是**「集合里不许出现这些名字」—— 那会误伤合法写法：
    同一个文件里的 `_MANIFEST_OPS` 就是一个共同操作名的元组，但它是
    **喂给 `channel_emulator_implements` 的**，正是本片要的形态。
    """
    ops = set(CHANNEL_EMULATOR_OPERATIONS)
    offenders: list[str] = []
    for path in sorted(_APP.rglob("*.py")):
        if path.name == "channel_emulator_manifest.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))

        # 全作用域的字符串集合常量（不只模块级 —— 那正是第 2 次绕过）
        # ⚠️ 存**节点**不存结果，因为取值可能是 `A + B` 这样的拼接，要递归解。
        #    第 5 次绕过实证：`_probe = _REQUIRED_METHODS + ("stop_emulation",)`
        #    对只认字面量的版本是不可见的。
        const_nodes: dict[str, ast.AST] = {
            node.targets[0].id: node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign) and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        }

        def _names_of(iter_node, seen: frozenset = frozenset()) -> set[str]:
            if isinstance(iter_node, (ast.Tuple, ast.List, ast.Set)):
                return {
                    e.value for e in iter_node.elts
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)
                }
            if isinstance(iter_node, ast.BinOp) and isinstance(iter_node.op, ast.Add):
                return (_names_of(iter_node.left, seen)
                        | _names_of(iter_node.right, seen))
            if isinstance(iter_node, ast.Name):
                if iter_node.id in seen or iter_node.id not in const_nodes:
                    return set()
                return _names_of(const_nodes[iter_node.id], seen | {iter_node.id})
            return set()

        # ① 收集全部「迭代绑定」：普通 for 与三种推导式走同一条路径
        bindings: list[tuple[ast.AST, str, set[str], int]] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.For, ast.AsyncFor)):
                if isinstance(node.target, ast.Name):
                    bindings.append(
                        (node, node.target.id, _names_of(node.iter), node.lineno)
                    )
            elif isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp,
                                   ast.DictComp)):
                for gen in node.generators:
                    if isinstance(gen.target, ast.Name):
                        bindings.append(
                            (node, gen.target.id, _names_of(gen.iter), node.lineno)
                        )

        # ② 只看**这个绑定自己作用域内**的 hasattr —— 判据必须按包含关系定域。
        #    ⚠️ 本门初稿把 `probed` 收成文件级集合，于是同名循环变量互相串味：
        #    `propsim_f64_p08_gate.py` 里两个相邻推导式都叫 `m`，一个喂 `hasattr`
        #    （该抓），一个喂 `channel_emulator_implements`（正是本片要的形态），
        #    结果合法的那个被误报。假门的另一种形态：判据过宽 → 误伤 → 早晚被
        #    人加白名单绕过，门就名存实亡了。
        for node, var, src_names, lineno in bindings:
            hit = src_names & ops
            if not hit:
                continue
            probes_here = any(
                isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                and c.func.id in ("hasattr", "getattr") and len(c.args) >= 2
                and isinstance(c.args[1], ast.Name) and c.args[1].id == var
                for c in ast.walk(node)
            )
            if probes_here:
                offenders.append(f"{path.name}:{lineno} {sorted(hit)}")

    assert not offenders, (
        "共同操作被迭代进 hasattr —— 补桩后那种探测恒为真，能力必须问 manifest："
        + "; ".join(sorted(set(offenders)))
    )


def test_missing_manifest_is_fail_closed():
    """没有 `adapter_manifest` 的对象一律判为不支持。

    新增型号必须显式声明才能被调用 —— 不再继承一个假的共同基线。
    """
    class _NoManifest:
        pass

    assert channel_emulator_implements(_NoManifest(), "stop_emulation") is False
    assert channel_emulator_implements(object(), "upload_asc_files") is False


def test_manifest_rejects_silent_omission_and_duplicates():
    def _ops(names):
        return tuple(
            ChannelEmulatorOperationCapability(
                operation=n, support="implemented", reason="r"
            )
            for n in names
        )

    # 漏一个 → 拒
    with pytest.raises(Exception):
        ChannelEmulatorManifest(
            schema_version=1, adapter_id="x", model_name="X", vendor="v",
            load_modes=(), operations=_ops(CHANNEL_EMULATOR_OPERATIONS[:-1]),
        )
    # 重复 → 拒
    with pytest.raises(Exception):
        ChannelEmulatorManifest(
            schema_version=1, adapter_id="x", model_name="X", vendor="v",
            load_modes=(), operations=_ops(
                CHANNEL_EMULATOR_OPERATIONS + (CHANNEL_EMULATOR_OPERATIONS[0],)),
        )
    # 全集 → 过
    ok = ChannelEmulatorManifest(
        schema_version=1, adapter_id="x", model_name="X", vendor="v",
        load_modes=(), operations=_ops(CHANNEL_EMULATOR_OPERATIONS),
    )
    assert ok.implements("stop_emulation") is True
    with pytest.raises(ValueError):
        ok.implements("no_such_operation")


def test_load_mode_duplicates_are_rejected():
    with pytest.raises(Exception):
        ChannelEmulatorManifest(
            schema_version=1, adapter_id="x", model_name="X", vendor="v",
            load_modes=(
                ChannelEmulatorLoadModeCapability(
                    mode="native_model", support="implemented", reason="r"),
                ChannelEmulatorLoadModeCapability(
                    mode="native_model", support="not_implemented", reason="r"),
            ),
            operations=tuple(
                ChannelEmulatorOperationCapability(
                    operation=n, support="not_implemented", reason="r")
                for n in CHANNEL_EMULATOR_OPERATIONS),
        )


# --------------------------------------------------------------------------
# 5. cleanup 的停机分支：两个方向都要留痕（此前行为覆盖为 0）
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cleanup_warns_loudly_when_it_skips_stopping_the_emulator():
    """CE 没声明 `stop_emulation` 时，cleanup **跳过停机必须留痕**。

    ⚠️ 内审 F2 指出：此前那个 `if` 没有 else —— manifest 少报或操作名拼错
    都会让收尾**静默不发停机**，而同一段代码上面就写着「仪器可能仍在发射」。
    两个方向的代价不对称：误判「支持」只是多一行 warning；误判「不支持」是
    操作员零信号地把仪器留在发射态。

    这条分支此前**行为覆盖为 0**（变异跑实证：把操作名拼错，全部测试仍绿）。
    """
    from unittest.mock import AsyncMock

    from app.services.mimo_ota.cleanup import cleanup_chamber_instruments

    class _NoStop:
        adapter_manifest = RealPropsimFs16Driver.adapter_manifest  # 未实现 stop

    class _Hal:
        drivers = {"channelEmulator": _NoStop()}

    result = await cleanup_chamber_instruments(_Hal(), execution_id="t")
    joined = " | ".join(result.warnings)
    assert "跳过了停机" in joined, result.warnings
    assert "not_implemented" in joined, result.warnings


@pytest.mark.asyncio
async def test_cleanup_stops_the_emulator_when_the_manifest_says_it_can():
    """反向：声明实现了就必须真的调用 —— 防「留痕」被写成「一律跳过」。"""
    from unittest.mock import AsyncMock

    from app.services.mimo_ota.cleanup import cleanup_chamber_instruments

    stop = AsyncMock(return_value=True)

    class _CanStop:
        adapter_manifest = RealPropsimF64Driver.adapter_manifest
        stop_emulation = stop

    class _Hal:
        drivers = {"channelEmulator": _CanStop()}

    result = await cleanup_chamber_instruments(_Hal(), execution_id="t")
    stop.assert_awaited_once()
    assert not [w for w in result.warnings if "跳过了停机" in w]


@pytest.mark.asyncio
async def test_cleanup_never_raises_on_odd_emulator_shapes():
    """收尾对**对象形态异常**一律回落成 warning，绝不抛出（内审 R2 F1）。

    ⚠️ 这条钉住的是上一版真造出来的回归：当时 `channel_emulator_implements`
    对「manifest 挂在实例上」抛 `TypeError`，探针实测 —— `cleanup_chamber_instruments`
    **直接抛出**，`stop_emulation` 一次没调、warning 一条没留。而它的调用点在
    `measure.py` 的 `finally:` 里：抛出会**顶替掉触发收尾的原始异常**，并跳过其后
    的落证与 `db.commit()`。也就是说，那一版把「不停机」升级成了
    「不停机 + 无提示 + 掩盖原错」，比它要治的静默跳过更差。

    `Never raises` 是这个函数写在 docstring 里的契约，这里给它一道真门。
    """
    from unittest.mock import AsyncMock, MagicMock

    from app.services.mimo_ota.cleanup import cleanup_chamber_instruments

    class _InstanceManifestCE:
        def __init__(self):
            # 照 base_station.py 的既有约定写 —— 实例级 manifest
            self.adapter_manifest = RealPropsimFs16Driver.adapter_manifest

    for ce in (_InstanceManifestCE(), AsyncMock(), MagicMock(), object()):
        class _Hal:
            drivers = {"channelEmulator": ce}

        result = await cleanup_chamber_instruments(_Hal(), execution_id="t")
        assert any("跳过了停机" in w for w in result.warnings), (
            f"{type(ce).__name__}: 跳过停机没有留痕"
        )


@pytest.mark.asyncio
async def test_cleanup_risk_wording_matches_whether_the_model_can_transmit():
    """「仪器可能仍在发射」这句话只对**真可能发射**的型号说（内审 R3 F6）。

    ⚠️ 初版对所有跳过情况都写这句。FS16 根本没有仿真引擎、连 `start_emulation`
    都没实现，不可能在发射 —— 那句话对它是假的，却会随**每一次**执行落进
    `cleanup_warnings`。恒定的假警报比没有警报更坏：它训练操作员忽略这一条，
    等真出事时那条 warning 已经没人看了。

    判据从 manifest 自己派生：连 `start_emulation` 都没实现 → 本链路不会让它
    进入发射态；能 start 却不能 stop（或压根没 manifest、判不出）→ 照旧吵。
    """
    from app.services.mimo_ota.cleanup import cleanup_chamber_instruments

    class _Fs16Like:
        adapter_manifest = RealPropsimFs16Driver.adapter_manifest   # start/stop 皆无

    class _StartsButCannotStop:
        adapter_manifest = channel_emulator_manifest_for(
            adapter_id="half", model_name="Half", vendor="test",
            implemented=("start_emulation",),
        )

    async def _warn_of(ce):
        class _Hal:
            drivers = {"channelEmulator": ce}
        return " | ".join((await cleanup_chamber_instruments(
            _Hal(), execution_id="t")).warnings)

    quiet = await _warn_of(_Fs16Like())
    assert "跳过了停机" in quiet
    assert "仪器可能仍在发射" not in quiet, (
        "对没有仿真引擎的型号说「可能仍在发射」是假警报：" + quiet
    )

    loud = await _warn_of(_StartsButCannotStop())
    assert "仪器可能仍在发射" in loud, (
        "能 start 却不能 stop 才是真危险，这一格不许被顺手降级：" + loud
    )
    # 判不出（没 manifest）也照旧吵 —— 不确定时站在吵的一侧
    assert "仪器可能仍在发射" in await _warn_of(object())

    # ⚠️ 三条**致发射路径**逐条都要能触发吵（内审 R4 F2）：初版只看
    #    `start_emulation`，于是「能直通 / 能发校准音、但没实现 start_emulation」
    #    的驱动会被告知「不会进入发射态」—— 假的安心，比假警报更坏。
    for op in ("start_emulation", "set_passthrough_mode", "set_calibration_tone"):
        only = channel_emulator_manifest_for(
            adapter_id="one_path", model_name="OnePath", vendor="test",
            implemented=(op,),
        )

        class _OnePath:
            adapter_manifest = only

        assert "仪器可能仍在发射" in await _warn_of(_OnePath()), (
            f"只实现了 {op} 也是能发射的，不许划到安静侧"
        )

    # ⚠️ **load_modes 是另一条轴**（内审 R5 F2）：`load_channel` 系列不在那 14 个
    #    操作里，只在 op 轴上枚举表达不完整。声明能播放波形 = 能发射。
    class _PlaysWaveforms:
        adapter_manifest = channel_emulator_manifest_for(
            adapter_id="playback", model_name="Playback Only", vendor="test",
            implemented=(), load_modes=("external_waveform",),
        )

    assert "仪器可能仍在发射" in await _warn_of(_PlaysWaveforms()), (
        "声明了加载模式就是能播放，不许只看 op 轴就划到安静侧"
    )
