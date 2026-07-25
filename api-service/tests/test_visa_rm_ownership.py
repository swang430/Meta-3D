"""F64R-8: 驱动**不得**调用 `ResourceManager.close()` —— 它会连带关掉其它仪表的会话。

一句话背景: `ResourceManager` 是按后端缓存的单例, 而 `close()` 会把**它发出去的所有**
resource 一起关掉 ⇒ 任何一个仪表 disconnect 调 `rm.close()`, 就把同后端下其余仪表的
会话也关了 (现场表现: HAL 重载 / 单仪表重连后, 别的仪表"莫名其妙断了")。

**完整原因、环境差异 (装了 IVI 的机器会分成两组)、以及"为什么不关也不泄漏", 全部只在
`app/hal/_visa_reconnect.py` 的「ResourceManager 所有权」一节维护一份** —— 这里不复述,
免得两份说明各自漂移 (本系列刚吃过"同一规则存两份、只改了副本"的亏)。

本文件两层:
  · **行为测试** (`TestDisconnectDoesNotKillPeers`) —— 真契约: 两个驱动共用一个 RM 时,
    A 断开后 B 的会话**必须还活着**。对写法形态免疫。
  · **静态扫描** (下面三条) —— 快速定位: 跑得快、报错直接指到行号。
    ⚠ 但它只认写死的字段名 `_visa_rm` / `_rm`, **局部变量 (`rm = self._visa_rm;
    rm.close()`) / 别名字段 / 经 resource 反查 (`session._resource_manager.close()`)
    三种写法都能绕过**(2026-07-25 审查逐个变异实测全绿)。所以它是**辅助**不是契约 ——
    真正兜底的是上面那层行为测试。两者分工, 不是二选一。
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest

_HAL_DIR = pathlib.Path(__file__).resolve().parent.parent / "app" / "hal"


# ───────── 行为层: 真契约 (对写法形态免疫) ─────────

# 全部**持有 RM** 的真驱动 (module, 类名, RM 字段, session/resource 字段)。
# ⚠ 加新 VISA 驱动必须进表 —— `test_driver_table_covers_every_rm_owner` 扫源码反查,
# 漏了会红。字段名两种流派 (`_visa_rm`/`_visa_session` 与 `_rm`/`_visa_resource`) 都在。
_RM_OWNING_DRIVERS = [
    ("cmw500_base_station",  "RealCmw500Driver",            "_visa_rm", "_visa_session"),
    ("ets_positioner",       "RealEtsEmcenterDriver",       "_visa_rm", "_visa_session"),
    ("keysight_mxg",         "RealKeysightMxgDriver",       "_visa_rm", "_visa_session"),
    ("keysight_ena",         "RealKeysightEnaDriver",       "_visa_rm", "_visa_session"),
    ("keysight_x_series_sa", "RealKeysightXSeriesSaDriver", "_visa_rm", "_visa_session"),
    ("propsim_fs16",         "RealPropsimFs16Driver",       "_rm",      "_visa_resource"),
    ("rs_smw200a",           "RealRsSmw200aDriver",         "_visa_rm", "_visa_session"),
    ("rs_fsva",              "RealRsFsvaDriver",            "_visa_rm", "_visa_session"),
    ("propsim_f64",          "RealPropsimF64Driver",        "_rm",      "_visa_resource"),
    ("rf_switch",            "EtslSwitchDriver",            "_visa_rm", "_visa_session"),
    ("rs_fsw",               "RealRsFswDriver",             "_visa_rm", "_visa_session"),
    ("rs_zna",               "RealRsZnaDriver",             "_visa_rm", "_visa_session"),
    ("uxm_base_station",     "RealUxmDriver",               "_visa_rm", "_visa_session"),
]


class _FakeSession:
    """假 VISA resource/session。只关心"被关了没有"。

    ⚠ `_resource_manager` **必须有** (Codex 第四轮): 真 pyvisa `Resource.__init__` 里就有
    `self._resource_manager = resource_manager` 这个**反向引用**, 所以
    `session._resource_manager.close()` 在真机上**真的能摸到共享 RM 并关掉同伴**。
    fake 少了它, 那种写法只会抛 `AttributeError` —— 同步驱动把异常吞掉返回 False, 于是
    "变异变红"是因为**报错**而不是因为同伴被关, 换个 try/except 包一下就彻底假绿。
    (这是"fake 教了个跟真机不一样的模型"的又一例, 跟本系列此前踩的是同一个坑。)"""

    def __init__(self, name: str, rm: "_SharedFakeRM | None" = None) -> None:
        self.name = name
        self.closed = False
        self.timeout = 5000
        self._resource_manager = rm      # ← 真 Resource 有这个反向引用

    def close(self) -> None:
        self.closed = True

    # 驱动 disconnect 路上可能碰到的最小接口
    def write(self, cmd: str) -> None: ...
    def query(self, cmd: str) -> str:  # pragma: no cover - 视驱动而定
        return '0,"No error"'


class _SharedFakeRM:
    """**复刻真 pyvisa RM 的要害语义**: 自己发出去的 resource 都记在册,
    `close()` 会把**册子里全部** resource 关掉 (真实现是
    `for resource in self._created_resources: resource.close()`)。

    这正是"一个驱动关 RM → 其它仪表跟着断"的机制本身; 用它当 fake, 任何
    形态的 `rm.close()` (局部变量 / 别名字段 / 经 resource 反查) 都会被行为
    测试抓到 —— 而静态扫描只认写死的字段名。"""

    def __init__(self) -> None:
        self._created: list[_FakeSession] = []
        self.close_calls = 0

    def open_resource(self, name: str, **_kw) -> _FakeSession:
        s = _FakeSession(name, rm=self)   # 反向引用: 真 pyvisa 也是这么挂的
        self._created.append(s)
        return s

    def close(self) -> None:
        self.close_calls += 1
        for s in self._created:      # ← 连带关闭, 真 RM 就是这么干的
            s.close()

# 只匹配**真实调用**, 不匹配注释行 (注释里要能写 `不调 rm.close()` 说明为什么)
_RM_CLOSE_CALL = re.compile(r"^\s*(?!#)[^#\n]*\b(?:_visa_rm|_rm)\.close\s*\(")


def _hal_sources():
    return sorted(p for p in _HAL_DIR.glob("*.py") if p.name != "__init__.py")


def _rm_owning_classes():
    """AST 扫描全 HAL 目录, 返回 `({(module, 类名)}, {类外创建的 module})`。

    "创建了 RM"= 调用了名为 `ResourceManager` 的东西 —— **属性调用**
    (`pyvisa.ResourceManager(...)`) 与**裸调用** (`from pyvisa import ResourceManager`
    之后的 `ResourceManager(...)`) 都认, 所以换 import 写法逃不掉。

    ⚠ 已知边界: ① 嵌套类里的创建会同时算到外层类头上 (`ast.walk` 不区分层级) ——
    宁可多报不漏报; ② 若 RM 由**模块级工厂函数**创建、类里只调工厂, 按类归属就看不见
    —— 这种情况单独报出来让调用方 fail-loud, 而不是默默漏掉。"""
    owners: set[tuple[str, str]] = set()
    module_level: set[str] = set()

    def _local_rm_names(tree) -> set[str]:
        """本模块里**绑到 ResourceManager 的所有名字** (Codex 第四轮)。

        只认字面量 `ResourceManager` 是不够的 —— `from pyvisa import ResourceManager
        as VisaRM` 之后调 `VisaRM()`, 名字对不上就整个类漏掉、而"表里也没有"两边照样相等
        = 假绿。这里把 import 别名和简单赋值别名 (`RM = pyvisa.ResourceManager`) 都收进来。"""
        names = {"ResourceManager"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for a in node.names:
                    if a.name == "ResourceManager":
                        names.add(a.asname or a.name)
            elif isinstance(node, ast.Assign):
                v = node.value
                bound = (
                    (isinstance(v, ast.Attribute) and v.attr == "ResourceManager")
                    or (isinstance(v, ast.Name) and v.id in names)
                )
                if bound:
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            names.add(t.id)
        return names

    def _make_is_rm_call(local_names: set[str]):
        def _is_rm_call(node) -> bool:
            if not isinstance(node, ast.Call):
                return False
            f = node.func
            if isinstance(f, ast.Attribute):
                return f.attr == "ResourceManager"     # `<任意>.ResourceManager(...)`
            if isinstance(f, ast.Name):
                return f.id in local_names             # 含 import / 赋值别名
            return False
        return _is_rm_call

    for path in _hal_sources():
        tree = ast.parse(path.read_text())
        _is_rm_call = _make_is_rm_call(_local_rm_names(tree))
        in_class: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for sub in ast.walk(node):
                    if _is_rm_call(sub):
                        owners.add((path.stem, node.name))
                        in_class.add(id(sub))
        for node in ast.walk(tree):
            if _is_rm_call(node) and id(node) not in in_class:
                module_level.add(path.stem)
    return owners, module_level


def _strip_comments(lines):
    """剥掉行注释再做匹配。

    ⚠ 为什么必须剥 (本文件自己踩过): 驱动里现在有一行注释写着 "**不调**
    `self._rm.close()` ...", 而"这个方法关了自己的会话吗"那条检查是在整段 body 上
    `re.search(r"\\.close\\s*\\(")` —— **注释里的 `.close()` 把它满足了**, 于是把
    `to_thread(self._visa_resource.close)` 换成 `pass` 的变异照样全绿 = 假覆盖。
    (粗暴按 `#` 切; 字符串里含 `#` 会被误切, 但那只会让匹配**更不容易**成立 →
    偏向让测试响亮失败, 是安全方向。)"""
    return "\n".join(l.split("#", 1)[0] for l in lines)


def test_no_driver_closes_the_shared_resource_manager():
    """★ 全 HAL 目录零 `rm.close()` 调用。"""
    offenders = []
    for path in _hal_sources():
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if _RM_CLOSE_CALL.match(line):
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "驱动调用了 ResourceManager.close() —— RM 是进程级共享单例, 这会连带关掉**其它\n"
        "仪表**的会话 (现场表现: 重载后别的仪表莫名断线)。只关自己的 resource/session,\n"
        "RM 引用置 None 即可。权威说明: app/hal/_visa_reconnect.py「ResourceManager 所有权」\n"
        + "\n".join(offenders)
    )


def test_rm_is_a_shared_singleton_so_the_rule_is_load_bearing():
    """守门规则的**前提**也要钉住: 万一将来 pyvisa 改成非单例, 这条规则就该重新评估
    (而不是留着一条没人知道为什么存在的禁令)。"""
    pyvisa = pytest.importorskip("pyvisa")
    a = pyvisa.ResourceManager("@py")
    b = pyvisa.ResourceManager("@py")
    assert a is b, "pyvisa RM 不再是单例 —— F64R-8 的禁令前提变了, 请重新评估本规则"
    assert hasattr(a, "_created_resources"), (
        "RM 不再持有 _created_resources —— close() 的连带关闭语义可能已变, 请复核"
    )


def test_drivers_still_close_their_own_session():
    """反向: 删 `rm.close()` 不能变成"什么都不关"。每个创建 RM 的驱动必须在
    `disconnect` 里关自己的 resource/session (否则 socket 真泄漏 —— F64 的 3334
    端口只容一条远程连接, 泄漏一条就挡死下次 connect)。"""
    missing = []
    for path in _hal_sources():
        src = path.read_text()
        if "pyvisa.ResourceManager(" not in src:
            continue
        lines = src.splitlines()
        # ⚠ 一个文件里可能有**多个类** (真驱动 + Mock + 变体) —— `rf_switch.py` 就有三个,
        # 而 `MockRfSwitch.disconnect()` 只置状态不关会话 (它本来就没有会话)。所以要求
        # "**至少一个** disconnect 关了自己的会话", 不是"第一个"。
        # (本条最初只取第一个 disconnect, 把 Mock 的空实现当成了真驱动 → 误报。)
        starts = [
            i for i, l in enumerate(lines)
            if re.match(r"\s*(async )?def disconnect", l)
        ]
        if not starts:
            missing.append(f"{path.name}: 创建了 RM 但没有 disconnect()")
            continue
        closes_own = False
        for start in starts:
            indent = len(lines[start]) - len(lines[start].lstrip())
            end = len(lines)
            for i in range(start + 1, len(lines)):
                l = lines[i]
                if l.strip() and (len(l) - len(l.lstrip())) <= indent and re.match(
                    r"\s*(async )?def ", l
                ):
                    end = i
                    break
            body = _strip_comments(lines[start:end])   # ⚠ 必须剥注释, 见该函数说明
            # 关自己: `<x>.close()` 或 `to_thread(<x>.close)` (后者不带括号, 别漏)
            if re.search(r"\.close\s*\(|to_thread\(\s*[\w.\[\]]*\.close\s*[,)]", body):
                closes_own = True
                break
        if not closes_own:
            missing.append(
                f"{path.name}: 没有任何 disconnect() 关闭自己的 resource/session"
            )
    assert not missing, "删掉 rm.close() 后必须仍关自己的会话:\n" + "\n".join(missing)


# ═════════ 行为层: 真契约 ═════════

class TestDisconnectDoesNotKillPeers:
    """★ **本 PR 的真契约**: 两个驱动共用同一个 RM 时, A 断开后 B 的会话**必须还活着**。

    为什么必须有行为测试 (2026-07-25 审查逐个变异实测): 上面的静态扫描只认写死的字段名
    `_visa_rm` / `_rm`, 而下面三种写法**都会连带关掉其它仪表、却都能让静态扫描全绿** ——
      · 局部变量: `rm = self._visa_rm; rm.close()`  ← 把 disconnect 抽成 helper 就自然产生
      · 别名字段: `self._visa_resource_manager = self._visa_rm; ...close()`
      · 经 resource 反查: `self._visa_session._resource_manager.close()`
    源码文本是**标称**, 跨驱动会话存活才是**生效端**; 本仓历史正是"同一禁令反复逃逸"。
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("module,cls_name,rm_attr,session_attr", _RM_OWNING_DRIVERS)
    async def test_disconnect_leaves_peer_session_open(
        self, module, cls_name, rm_attr, session_attr
    ):
        """★ **逐个驱动**跑一遍, 不是抽两个当代表 (Codex P2)。

        只测两个的话, 其余 11 个里将来有谁用了静态扫描抓不到的写法 (局部变量 / 别名
        字段 / 经 resource 反查), **两层都不会响** —— 套件全绿而 disconnect 照样杀掉
        同伴会话。契约是全仓的, 覆盖也得是全仓的。"""
        import importlib

        mod = importlib.import_module(f"app.hal.{module}")
        cls = getattr(mod, cls_name)

        shared_rm = _SharedFakeRM()
        peer = shared_rm.open_resource("TCPIP0::192.0.2.9::INSTR")   # 别的仪表

        d = cls(f"{module}-t", {"ip": "192.0.2.1", "port": 5025})
        setattr(d, rm_attr, shared_rm)
        own = shared_rm.open_resource("TCPIP0::192.0.2.1::5025::SOCKET")
        setattr(d, session_attr, own)

        await d.disconnect()

        assert shared_rm.close_calls == 0, f"{module} 关了共享 RM"
        assert peer.closed is False, (
            f"{module} 断开把**别的仪表**的会话也关了 —— 现场表现: 重载后别的仪表莫名断线"
        )
        assert own.closed is True, (
            f"{module} 没关自己的会话 (别矫枉过正成什么都不关 —— socket 会泄漏)"
        )

    def test_driver_table_covers_every_rm_owner(self):
        """★ 表本身**不能漏** —— 新加 VISA 驱动却忘了进表, 上面那条就默默少跑一个,
        而"少跑"和"跑过且通过"在结果里长得一模一样。

        ⚠ 判据按**类**核对, 不按模块名 (Codex 第三轮): 按模块名 + 字面量
        `"pyvisa.ResourceManager(" in src` 有两个假绿洞 ——
          · 已在表里的模块**新增第二个 RM 持有类** → 模块名集合仍相等, 新类不进参数化;
          · 新驱动写 `from pyvisa import ResourceManager` / 起别名 → 字面量匹配不到,
            模块压根不出现在 `actual` 里, 两边仍然相等。
        改用 AST 找"**哪个类里创建了 ResourceManager**"(`pyvisa.ResourceManager(...)`
        的属性调用和 `ResourceManager(...)` 的裸调用都认)。"""
        listed = {(m, c) for m, c, _, _ in _RM_OWNING_DRIVERS}
        owners, module_level = _rm_owning_classes()

        assert not module_level, (
            "有模块在**类之外**创建 ResourceManager (工厂函数 / 模块级单例) —— 本检查按类\n"
            "归属, 覆盖不到这种写法, 会造成'新驱动未被行为测试覆盖但套件全绿'。\n"
            "请把创建挪进驱动类, 或在此显式登记并说明如何保证覆盖:\n"
            f"  {sorted(module_level)}"
        )
        assert owners == listed, (
            "RM 持有类与行为测试表不一致 —— 新驱动请加进 `_RM_OWNING_DRIVERS`:\n"
            f"  漏在表外: {sorted(owners - listed)}\n"
            f"  表里多余: {sorted(listed - owners)}"
        )

