"""F64R-8: 驱动**不得**调用 `ResourceManager.close()` —— 它会连带关掉其它仪表的会话。

背景 (2026-07-25 实测, pyvisa 1.16.2):
  · `ResourceManager` 是**按后端缓存的单例**: `ResourceManager('@py')` 两次取到同一个
    对象; 本机默认后端解析成 `py`, 所以 `ResourceManager()` 与 `ResourceManager('@py')`
    **也是同一个对象** —— 本仓 13 个 VISA 驱动不分写法**共用一个 RM**;
  · `ResourceManager.close()` 源码 = `for resource in self._created_resources:
    resource.close()`, 官方 docstring 原文 "this will also terminate connections
    obtained from other ResourceManager instances"。
  ⇒ 任何一个仪表 disconnect 调 `rm.close()`, 就把其余全部仪表的会话一起关了。
    现场表现: HAL 重载 / 单仪表重连后, 别的仪表"莫名其妙断了"。

权威说明在 `app/hal/_visa_reconnect.py` 的「ResourceManager 所有权」一节。

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

import pathlib
import re

import pytest

_HAL_DIR = pathlib.Path(__file__).resolve().parent.parent / "app" / "hal"


# ───────── 行为层: 真契约 (对写法形态免疫) ─────────

class _FakeSession:
    """假 VISA resource/session。只关心"被关了没有"。"""

    def __init__(self, name: str) -> None:
        self.name = name
        self.closed = False
        self.timeout = 5000

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
        s = _FakeSession(name)
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
    async def test_fs16_disconnect_leaves_peer_session_open(self):
        from app.hal.propsim_fs16 import RealPropsimFs16Driver

        shared_rm = _SharedFakeRM()
        peer = shared_rm.open_resource("TCPIP0::192.0.2.9::INSTR")   # 别的仪表

        d = RealPropsimFs16Driver("fs16-t", {"ip": "192.0.2.1"})
        d._rm = shared_rm
        d._visa_resource = shared_rm.open_resource("TCPIP0::192.0.2.1::5025::SOCKET")

        assert await d.disconnect() is True
        assert d._visa_resource is None
        assert shared_rm.close_calls == 0, "驱动关了共享 RM"
        assert peer.closed is False, (
            "FS16 断开把**别的仪表**的会话也关了 —— 现场表现: 重载后别的仪表莫名断线"
        )
        assert shared_rm._created[1].closed is True, "自己的会话没关 (别矫枉过正成什么都不关)"

    @pytest.mark.asyncio
    async def test_fsw_disconnect_leaves_peer_session_open(self):
        """换一个**另一种 disconnect 形态**的驱动 (同步 close + `_set_status`),
        证明契约不是只对某一种写法成立。"""
        from app.hal.rs_fsw import RealRsFswDriver

        shared_rm = _SharedFakeRM()
        peer = shared_rm.open_resource("TCPIP0::192.0.2.9::INSTR")

        d = RealRsFswDriver("fsw-t", {"ip": "192.0.2.2"})
        d._visa_rm = shared_rm
        d._visa_session = shared_rm.open_resource("TCPIP0::192.0.2.2::INSTR")

        assert await d.disconnect() is True
        assert shared_rm.close_calls == 0
        assert peer.closed is False, "FSW 断开把别的仪表的会话也关了"
        assert shared_rm._created[1].closed is True
