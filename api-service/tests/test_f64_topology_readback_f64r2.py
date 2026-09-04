"""F64R-2: 端口/通道数从**仿真拓扑回读**, 不再用 tx×rx / 整机 64 猜。

背景 (2026-07-23 F64 驱动全量 review 母题②「该问仪器的地方在猜」):
驱动拿 `_tx_antennas × _rx_antennas` 当**物理输出口数**循环下发路损/增益。但
`tx×rx` 是**逻辑衰落通道**口径 —— MPAC OTA 里 4 个输入(BS 天线口) × 32 个输出
(探头) = 128 逻辑通道, 而物理输出口只有 32。拿 tx×rx(=16) 当输出口上界的后果:
**32 个探头只配到前 16 个, 17-32 号探头留在工程默认值上** = 现场"路损只设一半"。

正解 (PROPSIM User Reference, NotebookLM 查证):
  §20.4.3.6 `DIAG:SIMU:MODEL:INFO?` → `<inputs>,<channels>,<outputs>`
  §20.4.7.1 `GROUP:GET?`             → 信道组**数量**(纯数字)
  §20.4.7.4 `GROUP:CHANNELS:GET? <g>` → 该组通道 CSV
  §20.4.6.1  CENT 是 **per-group** 生效
  §20.4.6.4/6 同组判定 = **输入相同 或 输出相同**(满足其一即可) → 组数**不可推算**,
             全交叉拓扑下通道经两个维度连通可能只有 1 组, 必须 `GROUP:GET?` 回读
  §20.4.6.13 `MOB:MAN:CH` 是 **per-channel** 生效 (另有组版本 `:CHG`)

本文件钉四件事:
  1. 回读解析 + 边缘值 (读坏了宁可判"未知", 不半信半疑拿残缺列表配硬件);
  2. **口数正确** — 32 输出的仿真要把 32 个口全配上 (原始 bug 的直接回归);
  3. **fail-loud** — 拓扑未知时写操作拒绝下发 (不回退猜), 读操作降级并标注;
  4. **卸载清拓扑** — 卸载后拓扑必须跟 freq identity 一起清 (stale 拓扑比没有更危险:
     口数看着有效, 实际是**上一个仿真**的口)。
"""
from __future__ import annotations

from unittest.mock import MagicMock

import time

import pytest

from app.hal.propsim_f64 import RealPropsimF64Driver


def _driver(*, info="4,128,32", groups=None, err_on=None,
            in_ports=None, out_ports=None, state="STOPPED"):
    """mock 驱动。

    info: MODEL:INFO? 的原始回复 (None = 该查询抛异常, 模拟通信失败)。
    state: DIAG:SIMU:STATE? 的回复。默认 `STOPPED` = **已加载、没在播** ——
           这是唯一与"本 fake 会照常回答 MODEL:INFO? / GROUP:* 拓扑"自洽的默认值
           (见下方 ⚠⚠ 第 2 条)。要测"真没加载"请显式传 `state="CLOSED"`。
    groups / in_ports / out_ports: 显式指定分组与端口分配 (造非连续口、多组等形态)。
            **不给则默认造"全交叉 = 1 组"** —— 见下方分组规则说明。
    err_on: 命令子串 → 该查询抛异常。

    ⚠⚠ **分组必须符合手册物理规则, 别造不可能的拓扑** (2026-07-24 教训):
    手册 §20.4.6.1「同输入**或**同输出即同组」定义的是**连通分量**, 且同组有传递性
    (A、B 同输入, B、C 同输出 → A、C 同组)。推论:
      · 不同组之间输入集、输出集**都不相交**, 每组至少各独占 1 输入 + 1 输出;
      · 故 **组数 ≤ min(inputs, outputs)**;
      · **全交叉拓扑 (每个输入都连每个输出) 恒为 1 组** —— 4in×32out 的 128 条通道
        全部连成一片, 不是 32 组。
    本 fixture 原先默认造"每组占用全部输入口"的 32 组数据, 那按手册必然是同一组 ——
    **物理上不可能**。当时据此把驱动里的组数上界从 min 放宽成 max, 等于让 fake 教出来的
    错误模型改写了生产代码 (查手册才发现)。**测试失败不一定是代码错了, 也可能是 fake
    在教错的仪器模型 —— 拿不准就查手册, 别改代码迁就 fake。**

    ⚠⚠ **同一条规则的第 2 个实例: STATE? 也不能跟拓扑打架** (2026-07-24 F64R-1):
    本 fake 原先把 `DIAG:SIMU:STATE?` 硬答 `CLOSED`, 却同时照常回答 `MODEL:INFO?`
    的 "4,128,32" 和整套 `GROUP:*` —— 手册 §20.4.3.14 里 CLOSED 的定义就是
    **"Emulation has not been loaded"**, 没加载就没有模型可报口数, 驱动自己也拒绝在
    CLOSED 下试 MODEL:INFO?。F64R-2 时无人消费 STATE? 所以没暴露; F64R-1 把 STATE?
    接成运行态真值源后, 这个矛盾组合会让"仿真已被别人卸载 → 清加载态"的正确逻辑
    看起来像 bug。默认值因此改为 STOPPED (已加载未播放)。
    """
    drv = RealPropsimF64Driver("propsim-test", {})
    visa = MagicMock()
    drv._visa_resource = visa
    writes: list[str] = []

    n_in = n_out = n_ch = 0
    if info and info.count(",") == 2:
        try:
            n_in, n_ch, n_out = (int(x) for x in info.split(","))
        except ValueError:
            n_in = n_out = n_ch = 0
    if groups is None:
        # 默认 = **全交叉 1 组**(手册规则下唯一自洽的默认): 全部通道同组, 该组占用
        # 全部输入口和全部输出口。
        # ⚠ fake 自身的规模闸: 测"畸形/超大 info"的用例 (如 99999,99999,99999) 会让
        # **这个 fake** 先去造上亿个元素把自己吃死 —— 跟被测代码无关。超界就不造:
        # 那些用例里驱动在三值上界闸就 return 了, 本来也走不到组回读。
        sane = 0 < n_in <= 64 and 0 < n_out <= 64 and 0 < n_ch <= 4096
        groups = {1: list(range(1, n_ch + 1))} if sane else {}
    groups = groups or {}
    # 默认端口分配: 与"全交叉 1 组"自洽 —— 那一组占用全部输入口 + 全部输出口。
    group_in_ports = in_ports if in_ports is not None else {
        g: list(range(1, n_in + 1)) for g in groups
    }
    group_out_ports = out_ports if out_ports is not None else {
        g: list(range(1, n_out + 1)) for g in groups
    }

    # 仪器侧的仿真状态随命令迁移 (静态 fake 会自相矛盾: 发完 CLOSE 还报 STOPPED,
    # 加载路复查 "==CLOSED 才算真卸载" 就永远过不去)。只建模真机确定会变的两步:
    #   DIAG:SIMU:CLOSE  → CLOSED  (卸载)
    #   CALC:FILT:FILE   → STOPPED (打开, 已加载未播放)
    sim_state = [state]

    async def _write(cmd, timeout=None):
        writes.append(cmd)
        if cmd == "DIAG:SIMU:CLOSE":
            sim_state[0] = "CLOSED"
        elif cmd.startswith("CALC:FILT:FILE"):
            sim_state[0] = "STOPPED"

    async def _query(cmd, timeout=None, **_kw):
        if err_on and err_on in cmd:
            raise RuntimeError(f"boom on {cmd}")
        if "SYST:ERR" in cmd:
            return '0,"No error"'
        if cmd == "DIAG:SIMU:MODEL:INFO?":
            if info is None:
                raise RuntimeError("MODEL:INFO? 通信失败")
            return info
        if cmd == "GROUP:GET?":
            return str(len(groups))
        if cmd.startswith("GROUP:CHANNELS:GET?"):
            g = int(cmd.split("?", 1)[1].strip())
            return ",".join(str(c) for c in groups.get(g, []))
        if cmd.startswith("GROUP:INPUTS:GET?"):
            g = int(cmd.split("?", 1)[1].strip())
            return ",".join(str(p) for p in group_in_ports.get(g, []))
        if cmd.startswith("GROUP:OUTPUTS:GET?"):
            g = int(cmd.split("?", 1)[1].strip())
            return ",".join(str(p) for p in group_out_ports.get(g, []))
        if cmd == "DIAG:SIMU:STATE?":
            return sim_state[0]
        if cmd.startswith("CALC:FILT:CENT:CH?"):
            return "3550.0"
        if cmd.startswith("INP:LEV:AMP:CH?"):
            port = cmd.split("?", 1)[1].strip()
            prefix = f"INP:LEV:AMP:CH {port},"
            for write in reversed(writes):
                if write.startswith(prefix):
                    return write.split(",", 1)[1]
        return "1"  # *OPC? 等

    drv._write = _write  # type: ignore[assignment]
    drv._query = _query  # type: ignore[assignment]
    return drv, writes


def _topology_fields():
    """`_clear_topology()` 实际复位的全部字段名 —— **从源码里抽**, 不是手抄清单。

    手抄清单有个致命弱点: 它自称"加新字段补进来就自动覆盖", 但没人补的时候它照样绿
    (`_topology_from_override` 就这么漏出去过)。改成解析 `_clear_topology` 的 AST,
    新字段一旦加进那个方法, 这里自动纳入 —— 漏在**别的**复位路径才会被抓出来, 这正是
    本仓库逃逸 5+ 轮的母题要防的。"""
    import ast
    import inspect
    import textwrap

    src = textwrap.dedent(inspect.getsource(RealPropsimF64Driver._clear_topology))
    names = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if (isinstance(tgt, ast.Attribute)
                        and isinstance(tgt.value, ast.Name) and tgt.value.id == "self"):
                    names.append(tgt.attr)
    assert names, "没能从 _clear_topology 抽出字段名 (实现变了?)"
    return tuple(names)


_TOPOLOGY_FIELDS = _topology_fields()


def _loss_ports(writes):
    return [int(w.split(" ", 1)[1].split(",")[0])
            for w in writes if w.startswith("OUTP:LOSS:SET ")]


# ───────────── 1. 回读解析 + 边缘值 ─────────────

class TestTopologyReadbackParsing:
    async def test_reads_real_topology_from_model_info(self):
        """MODEL:INFO? "4,128,32" → 4 输入 / 128 逻辑通道 / 32 物理输出口(探头)。"""
        drv, _ = _driver(info="4,128,32")
        await drv._readback_topology()
        assert drv._active_inputs == 4
        assert drv._active_channels == 128
        assert drv._active_outputs == 32
        assert drv.get_active_output_count() == 32
        assert drv.get_active_input_count() == 4

    async def test_reads_group_representative_channels(self):
        """**仪器报几组就按几组**, 每组取首通道作 CENT 代表 —— 组数不推算。

        4in×32out **全交叉 = 1 组**(手册 §20.4.6.1: 同输入或同输出即同组, 有传递性 →
        128 条通道全部连成一片)。多组形态见 `test_multi_group_disjoint_topology`。"""
        drv, _ = _driver(info="4,128,32")
        await drv._readback_topology()
        assert drv._group_repr_channels == [1]              # 全交叉恒 1 组
        assert len(drv._active_channel_numbers) == 128       # 但通道号全部读回

    async def test_multi_group_disjoint_topology(self):
        """多组 = 各组输入/输出**互不重叠**(手册推导下唯一可能的多组形态)。
        4 个输入各独占 8 个输出 → 4 组, 正好触到 min(4,32)=4 的上限。"""
        drv, _ = _driver(
            info="4,32,32",
            groups={g: list(range((g - 1) * 8 + 1, g * 8 + 1)) for g in range(1, 5)},
            in_ports={g: [g] for g in range(1, 5)},                       # 各占 1 输入
            out_ports={g: list(range((g - 1) * 8 + 1, g * 8 + 1)) for g in range(1, 5)},
        )
        await drv._readback_topology()
        assert drv._group_repr_channels == [1, 9, 17, 25]    # 4 组各自首通道
        assert drv.get_active_output_ports() == list(range(1, 33))

    async def test_single_group_topology_dispatches_once(self):
        """★ 全交叉拓扑 (仪器报 **1 组**) → CENT 只发 1 条, 不按输出数瞎发 32 条。
        钉的是"组数完全听仪器的", 防止有人照"按输出分组"的直觉把组数写死。"""
        # 全交叉 = 1 组, 该组占**全部** 4 输入 × 32 输出 (自洽; 端口数与 MODEL:INFO? 对得上)
        drv, writes = _driver(info="4,128,32",
                              groups={1: list(range(1, 129))},
                              in_ports={1: list(range(1, 5))},
                              out_ports={1: list(range(1, 33))})
        await drv._readback_topology()
        assert drv._group_repr_channels == [1]
        assert await drv.set_channel_model(
            "CDL-C", "UMa",
            {"emulation_file": "D:\\ok\\m.smu", "center_frequency_mhz": 3550.0},
        ) is True
        cent = [w for w in writes if w.startswith("CALC:FILT:CENT:CH ")]
        assert len(cent) == 1 and cent[0].startswith("CALC:FILT:CENT:CH 1,")

    @pytest.mark.parametrize("bad", ["", "   ", "4,128", "4,128,32,7", "a,b,c",
                                     "4,128,0", "4,-1,32", "4,128,1.5"])
    async def test_invalid_model_info_leaves_topology_unknown(self, bad):
        """段数不对 / 非数字 / 非正 / 非整数 → 整体判"未知", 不采信半个结果。"""
        drv, _ = _driver(info=bad)
        await drv._readback_topology()
        assert drv._active_outputs is None
        assert drv._active_inputs is None
        assert drv.get_active_output_count() is None

    async def test_model_info_query_exception_leaves_unknown(self):
        drv, _ = _driver(info=None)
        await drv._readback_topology()
        assert drv._active_outputs is None

    async def test_group_failure_does_not_lose_port_counts(self):
        """组信息读坏**不该**拖累端口数 —— 两者是独立消费方 (CENT vs 路损)。"""
        drv, _ = _driver(info="4,128,32", groups={})   # GROUP:GET? → "0"
        await drv._readback_topology()
        assert drv._active_outputs == 32              # 端口数仍可用
        assert drv._group_repr_channels is None       # 只有 CENT 不可用

    async def test_absurd_group_count_rejected(self):
        """组数 > 逻辑通道数不合理 (组是通道的划分) → 判读不到, 不照着荒谬组数狂发命令。"""
        drv, _ = _driver(info="1,2,2", groups={g: [1] for g in range(1, 6)})
        await drv._readback_topology()
        assert drv._group_repr_channels is None

    async def test_empty_group_channel_list_rejected(self):
        drv, _ = _driver(info="1,2,2", groups={1: [1], 2: []})
        await drv._readback_topology()
        assert drv._group_repr_channels is None


# ───────────── 2. 口数正确 (原始 bug 的直接回归) ─────────────

class TestPortCountCorrectness:
    async def test_path_loss_covers_all_32_probes_not_just_16(self):
        """★ F64R-2 核心回归: 4in×32out 的仿真 (tx×rx 会算出 16) 必须把 **32 个探头
        全配上** —— 旧行为只配 1..16, 17-32 号探头留工程默认值 = 现场路损只设一半。"""
        drv, writes = _driver(info="4,128,32")
        drv._tx_antennas, drv._rx_antennas = 4, 4      # tx×rx=16, 正是旧的错口径
        await drv._readback_topology()
        assert await drv.set_path_loss(path_loss_db=12.0) is True
        assert _loss_ports(writes) == list(range(1, 33)), "32 个探头必须全部配到"

    async def test_doppler_uses_real_channel_count_not_hardware_64(self):
        """多普勒是逐通道下发, 上界该是**真实逻辑通道数**, 不是整机 64。"""
        drv, writes = _driver(info="1,4,4")
        drv._channel_count = 64                        # 整机容量, 不该被当上界
        await drv._readback_topology()
        assert await drv.set_doppler(frequency_hz=0.0) is True
        chans = [w for w in writes if w.startswith("DIAG:SIMU:MOB:MAN:CH")]
        assert len(chans) == 4                         # 4 条, 不是 64 条

    async def test_baseband_power_fallback_uses_real_input_count(self):
        drv, writes = _driver(info="4,128,32")
        drv._tx_antennas = 2                           # stale 缓存, 不该被用
        await drv._readback_topology()
        assert await drv.set_baseband_power(-15.0) is True
        inputs = [w for w in writes if w.startswith("INP:LEV:AMP:CH")]
        assert len(inputs) == 4                        # 4 个输入口, 不是 stale 的 2

    async def test_baseband_readback_matches_formatted_wire_value(self):
        drv, writes = _driver(info="1,4,4")
        await drv._readback_topology()
        assert await drv.set_baseband_power(-15.04) is True
        assert "INP:LEV:AMP:CH 1,-15.0" in writes

    async def test_explicit_input_ports_still_win(self):
        """上层参数决议层显式给口 → 仍优先于回读值 (回读只是缺省兜底)。"""
        drv, writes = _driver(info="4,128,32")
        await drv._readback_topology()
        assert await drv.set_baseband_power(-15.0, input_ports=[2, 3]) is True
        inputs = [w for w in writes if w.startswith("INP:LEV:AMP:CH")]
        assert len(inputs) == 2

    async def test_cent_dispatched_once_per_group_not_per_channel(self):
        """★ CENT 是 per-group 生效 → **按组数**发, 不是按通道数。

        4 组的非全交叉拓扑 (各组输入/输出互不重叠) → 32 条通道只发 **4 条**;
        旧代码按 `_channel_count`(整机 64) 循环, 两头都错。"""
        drv, writes = _driver(
            info="4,32,32",
            groups={g: list(range((g - 1) * 8 + 1, g * 8 + 1)) for g in range(1, 5)},
            in_ports={g: [g] for g in range(1, 5)},
            out_ports={g: list(range((g - 1) * 8 + 1, g * 8 + 1)) for g in range(1, 5)},
        )
        await drv._readback_topology()
        assert await drv.set_channel_model(
            "CDL-C", "UMa",
            {"emulation_file": "D:\\ok\\m.smu", "center_frequency_mhz": 3550.0},
        ) is True
        cent = [w for w in writes if w.startswith("CALC:FILT:CENT:CH ")]
        assert len(cent) == 4, "32 条通道该按 4 个组发 4 条"
        # 每条都打在某个组的代表通道上, 且互不重复
        sent = sorted(int(w.split(" ", 1)[1].split(",")[0]) for w in cent)
        assert sent == sorted(drv._group_repr_channels)


# ───────────── 3. 拓扑未知 → 写 fail-loud / 读降级 ─────────────

class TestFailLoudWhenTopologyUnknown:
    @pytest.mark.parametrize("name,call", [
        ("set_path_loss", lambda d: d.set_path_loss(path_loss_db=10.0)),
        ("set_doppler", lambda d: d.set_doppler(frequency_hz=0.0)),
        ("set_baseband_power", lambda d: d.set_baseband_power(-15.0)),
    ])
    async def test_write_ops_refuse_without_topology(self, name, call):
        """拓扑未知 (未加载 / 回读失败) → 写操作拒绝, **不回退猜口数** ——
        配错口比不配更伤 (操作员以为全配上了)。"""
        drv, writes = _driver(info=None)
        drv._tx_antennas, drv._rx_antennas = 4, 4     # 有猜的余地也不许猜
        drv._channel_count = 64
        await drv._readback_topology()
        assert await call(drv) is False, f"{name} 应 fail-loud"
        assert writes == [], f"{name} 不该下发任何命令"
        assert drv._last_error and "未知" in drv._last_error

    async def test_cent_refuses_without_group_info(self):
        """组信息未知 → CENT 拒发, 且 programmed 必须复位 (否则谎报下发过的频率)。"""
        drv, writes = _driver(info="4,128,32", groups={})
        drv._center_freq_programmed = True             # 上一个 model 的残留
        assert await drv.set_channel_model(
            "CDL-C", "UMa",
            {"emulation_file": "D:\\ok\\m.smu", "center_frequency_mhz": 3550.0},
        ) is False
        assert not [w for w in writes if w.startswith("CALC:FILT:CENT:CH ")]
        assert drv._center_freq_programmed is False

    async def test_get_metrics_degrades_but_does_not_fail(self):
        """读操作降级不 fail-loud, 但必须**显式标注跳过** —— 空 dict 不能被读成
        "查了、没有电平"。"""
        drv, _ = _driver(info=None)
        await drv._readback_topology()
        m = await drv.get_metrics()
        assert m.metrics["input_powers_dbm"] == {}
        assert m.metrics["output_powers_dbm"] == {}
        assert m.metrics["active_outputs"] is None
        errs = " ".join(m.metrics.get("query_errors") or [])
        assert "跳过查询" in errs

    async def test_get_metrics_queries_real_port_counts(self):
        drv, _ = _driver(info="4,128,32")
        await drv._readback_topology()
        m = await drv.get_metrics()
        assert len(m.metrics["input_powers_dbm"]) == 4
        assert len(m.metrics["output_powers_dbm"]) == 32   # 32 探头, 不是 tx×rx


# ───────────── 4. 卸载清拓扑 (fan-out 回归) ─────────────

class TestTopologyClearedOnUnload:
    async def test_unload_clears_topology(self):
        """卸载后拓扑必须跟 freq identity 一起清 —— 残留的是**上一个仿真**的口数,
        比没有更危险 (看着有效, 实际配到别的仿真的口上)。

        ⚠ 断言**遍历字段清单**而不是逐个列举: "加了新拓扑字段却漏在某条复位路径"是本仓库
        逃逸 5+ 轮的母题, 逐个列举的用例在漏了新字段时**仍然绿**。清单由
        `_topology_fields()` 从 `_clear_topology` 源码抽取, 不是手抄。"""
        drv, _ = _driver(info="4,128,32")
        await drv._readback_topology()
        assert drv._active_outputs == 32
        # 前置: 端口/通道三组字段都填上了 (bool 标志除外, 它只在声明兜底时为 True)
        assert all(getattr(drv, f) is not None for f in _TOPOLOGY_FIELDS
                   if f != "_topology_from_override"), "前置: 全填上了"
        drv._apply_unload()
        residual = [f for f in _TOPOLOGY_FIELDS if getattr(drv, f)]   # None/False 都算已清
        assert residual == [], f"卸载后残留拓扑字段: {residual}"

    async def test_session_reset_clears_topology(self):
        drv, _ = _driver(info="4,128,32")
        await drv._readback_topology()
        drv._apply_session_reset()
        residual = [f for f in _TOPOLOGY_FIELDS if getattr(drv, f)]   # None/False 都算已清
        assert residual == [], f"会话复位后残留拓扑字段: {residual}"

    async def test_failed_reload_does_not_leave_stale_topology(self):
        """新文件加载失败 (CLOSE 已确认卸载) → 旧拓扑必须清, 否则后续端口配置会拿
        **上一个仿真**的口数当真。"""
        drv, _ = _driver(info="4,128,32")
        await drv._readback_topology()
        assert drv._active_outputs == 32

        async def _query_err(cmd, timeout=None, **_kw):
            if "SYST:ERR" in cmd:
                return '-200,"No simulation opened"'
            if cmd == "DIAG:SIMU:STATE?":
                return "CLOSED"
            return "1"

        drv._query = _query_err  # type: ignore[assignment]
        assert await drv.load_local_scenario("D:\\bad\\missing.smu") is False
        assert drv._active_outputs is None, "加载失败后残留了上一个仿真的拓扑"
        assert drv.get_active_output_count() is None

    async def test_load_success_but_readback_fail_does_not_keep_old_topology(self):
        """★ 加载**成功**但拓扑回读失败 → 必须停在干净的"未知", 不许残留上一个仿真的口数。

        (审查实证的场景: 不清的话日志喊着"将 fail-loud"、`set_path_loss` 却照旧 32 口
        写满 —— **日志说谎**, 比没有拓扑更危险。)"""
        drv, writes = _driver(info="4,128,32")
        await drv._readback_topology()
        assert drv._active_outputs == 32

        async def _q_no_info(cmd, timeout=None, **_kw):
            if "MODEL:INFO?" in cmd:
                raise RuntimeError("回读超时")
            if "SYST:ERR" in cmd:
                return '0,"No error"'
            if cmd == "DIAG:SIMU:STATE?":
                return "CLOSED"
            if cmd.startswith("CALC:FILT:CENT:CH?"):
                return "3550.0"
            return "1"

        drv._query = _q_no_info  # type: ignore[assignment]
        assert await drv.load_local_scenario("D:\\ok\\other.smu") is True   # 加载本身成功
        assert drv._active_outputs is None
        assert drv._active_output_ports is None
        writes.clear()
        assert await drv.set_path_loss(path_loss_db=5.0) is False   # 日志说 fail-loud 就真的拒
        assert not [w for w in writes if w.startswith("OUTP:LOSS:SET")]

    async def test_partial_readback_does_not_mix_generations(self):
        """★ 三值来自新仿真、组信息来自旧仿真的**混代**状态不许出现。"""
        drv, _ = _driver(info="4,128,32")
        await drv._readback_topology()
        old_reprs = list(drv._group_repr_channels or [])
        assert old_reprs

        async def _q_no_group(cmd, timeout=None, **_kw):
            if cmd == "DIAG:SIMU:MODEL:INFO?":
                return "1,2,2"           # 新仿真的三值
            if cmd == "GROUP:GET?":
                raise RuntimeError("组查询超时")
            return "1"

        drv._query = _q_no_group  # type: ignore[assignment]
        await drv._readback_topology()
        assert drv._active_outputs == 2                 # 三值是新的
        assert drv._group_repr_channels is None         # 组信息不许留旧的
        assert drv._active_output_ports is None


class TestAscAndB2PathsAlsoReadTopology:
    """★ 三条加载路 (GCM / ASC / B-2) 都必须落**本仿真**的拓扑。

    审查实证的原始缺陷: 只有 GCM 路接了回读, ASC/B-2 既不回读也不清 → GCM 步加载
    32 探头后切 ASC (实际 2 口), `set_path_loss` 仍按 **32 口**下发。而 ASC 还是**默认
    管线** (engine_mode 默认 mimo_first_asc), 冷启动跑 ASC 则拓扑恒 None、所有端口写
    操作全拒 = 功能回归。
    """

    async def _drv_for_upload(self, info):
        drv, writes = _driver(info=info)

        async def _ftp(local, remote):
            return ["runtime_emulation.smu"]

        drv._ftp_upload_directory = _ftp  # type: ignore[assignment]
        return drv, writes

    async def test_asc_load_reads_topology(self):
        drv, _ = await self._drv_for_upload("2,4,2")
        assert await drv.upload_asc_files("/tmp/asc", "m") is True
        assert drv.get_active_output_count() == 2
        assert drv.get_active_output_ports() == [1, 2]

    async def test_asc_load_replaces_previous_topology(self):
        """GCM(32 口) → ASC(2 口): 必须换成 2 口, 不能留着 32 口去配。"""
        drv, writes = await self._drv_for_upload("4,128,32")
        await drv._readback_topology()
        assert drv._active_outputs == 32

        # 换成 2 口的仿真回复
        drv, writes2 = await self._drv_for_upload("2,4,2")
        drv._active_inputs, drv._active_outputs = 4, 32      # 假装上一步 GCM 的残留
        drv._active_output_ports = list(range(1, 33))
        assert await drv.upload_asc_files("/tmp/asc", "m") is True
        assert drv.get_active_output_ports() == [1, 2], "ASC 加载后仍是上一个仿真的 32 口"
        writes2.clear()
        assert await drv.set_path_loss(path_loss_db=5.0) is True
        assert _loss_ports(writes2) == [1, 2]               # 2 口, 不是 32 口

    async def test_b2_load_reads_topology(self):
        drv, _ = _driver(info="2,4,2")

        async def _ftp(local, remote):
            return ["model.smu"]

        drv._ftp_upload_directory = _ftp  # type: ignore[assignment]
        assert await drv.load_parametric_tdl("/tmp/b2", "m") is True
        assert drv.get_active_output_count() == 2
        assert drv.get_active_output_ports() == [1, 2]


class TestRealPortNumbers:
    """★ 端口**号**也问仪器 —— 只知道"几个口"不够。"""

    async def test_non_contiguous_output_ports_dispatched_as_is(self):
        """仿真占用输出口 {2,4} (数量=2)。照 1..N 发会**误配口 1、漏配口 4**。"""
        # 1 输入 × 2 输出 = **1 组**(两条通道同输入 ⇒ 同组), 该组占输出口 {2,4}
        drv, writes = _driver(
            info="1,2,2",
            groups={1: [1, 2]},
            in_ports={1: [1]},
            out_ports={1: [2, 4]},               # 非连续: 2 和 4
        )
        await drv._readback_topology()
        assert drv.get_active_output_ports() == [2, 4]
        assert await drv.set_path_loss(path_loss_db=7.0) is True
        assert _loss_ports(writes) == [2, 4], "照 1..N 发了, 没用真实端口号"

    async def test_non_contiguous_input_ports_used_for_baseband(self):
        drv, writes = _driver(
            info="2,4,2",
            groups={1: [1, 2], 2: [3, 4]},
            in_ports={1: [3], 2: [5]},           # 各占 1 个输入口 (3 / 5), 互不重叠
            out_ports={1: [1], 2: [2]},
        )
        await drv._readback_topology()
        assert drv.get_active_input_ports() == [3, 5]
        assert await drv.set_baseband_power(-15.0) is True
        inp = [w for w in writes if w.startswith("INP:LEV:AMP:CH")]
        assert [int(w.split(" ", 1)[1].split(",")[0]) for w in inp] == [3, 5]

    async def test_port_count_mismatch_rejected(self):
        """端口号集合大小与 MODEL:INFO? 报的口数打架 → 判读不到 (两个来源不一致时
        不许挑一个信)。"""
        drv, _ = _driver(
            info="1,2,2",                        # 说有 2 个输出口
            groups={1: [1], 2: [2]},
            in_ports={1: [1], 2: [1]},
            out_ports={1: [1], 2: [1]},          # 实际只回读到 1 个 (并集大小=1)
        )
        await drv._readback_topology()
        assert drv._active_output_ports is None
        assert await drv.set_path_loss(path_loss_db=1.0) is False


class TestGroupLoopFailureModes:
    """组循环中途出问题的形态 —— 用上 `err_on` 钩子 (复审 F10: 之前留了参数没人传,
    等于"计划中但没写"的用例)。"""

    @pytest.mark.parametrize("failing_cmd", [
        "GROUP:GET?", "GROUP:CHANNELS:GET?", "GROUP:INPUTS:GET?", "GROUP:OUTPUTS:GET?",
    ])
    async def test_any_group_query_exception_leaves_ports_unknown(self, failing_cmd):
        """组循环里任一条查询抛异常 → 端口/通道号判"读不到", 写操作 fail-loud。
        口数(三值)已落库不受影响 —— 两者是独立消费方。"""
        drv, writes = _driver(info="4,128,32", err_on=failing_cmd)
        await drv._readback_topology()
        assert drv._active_outputs == 32                  # 三值仍在
        assert drv.get_active_output_ports() is None      # 号码没了
        assert await drv.set_path_loss(path_loss_db=1.0) is False
        assert writes == []

    @pytest.mark.parametrize("bad_ports", [
        {1: [0]},          # 0 不是合法端口号
        {1: [-1]},         # 负数 = 解析错位
        {1: []},           # 空回复
    ])
    async def test_invalid_port_numbers_rejected(self, bad_ports):
        """端口号必须是正整数 —— 照发会变成 `OUTP:LOSS:SET -1,...` 只能靠仪器兜底。"""
        drv, _ = _driver(info="1,1,1", groups={1: [1]},
                         in_ports={1: [1]}, out_ports=bad_ports)
        await drv._readback_topology()
        assert drv.get_active_output_ports() is None

    async def test_group_count_as_list_rejected(self):
        """GROUP:GET? 该回单个数字; 回成列表 = 回复串线 → 判读不到。"""
        drv, _ = _driver(info="1,1,1")

        async def _q(cmd, timeout=None, **_kw):
            if cmd == "GROUP:GET?":
                return "1,2,3"                 # 列表形态, 不是单个组数
            if cmd == "DIAG:SIMU:MODEL:INFO?":
                return "1,1,1"
            if "SYST:ERR" in cmd:
                return '0,"No error"'
            return "1"

        drv._query = _q  # type: ignore[assignment]
        await drv._readback_topology()
        assert drv._group_repr_channels is None

    async def test_channel_number_count_mismatch_rejected(self):
        """通道号并集大小与 MODEL:INFO? 的 channels 打架 → 判读不到 (与端口侧对称)。"""
        drv, _ = _driver(
            info="1,4,2",                       # 说有 4 个逻辑通道
            groups={1: [1], 2: [1]},            # 实际并集只有 {1} = 1 个
            in_ports={1: [1], 2: [1]},
            out_ports={1: [1], 2: [2]},
        )
        await drv._readback_topology()
        assert drv._active_channel_numbers is None
        assert await drv.set_doppler(frequency_hz=0.0) is False


class TestDopplerUsesRealChannelNumbers:
    """set_doppler 也按**真实通道号**发 (复审 F5: 号码已读回却仍 range(1,N+1))。"""

    async def test_non_contiguous_channel_numbers_dispatched_as_is(self):
        # 1 输入 × 2 输出 = 1 组 (同输入 ⇒ 同组), 组内通道号 7、9 (非连续, 不从 1 起)
        drv, writes = _driver(
            info="1,2,2",
            groups={1: [7, 9]},
            in_ports={1: [1]},
            out_ports={1: [1, 2]},
        )
        await drv._readback_topology()
        assert await drv.set_doppler(frequency_hz=0.0) is True
        chans = [int(w.split(" ", 1)[1].split(",")[0])
                 for w in writes if w.startswith("DIAG:SIMU:MOB:MAN:CH")]
        assert chans == [7, 9], "按 1..N 发了, 没用真实通道号"

    async def test_no_params_is_noop_even_without_topology(self):
        """两参皆空 = 无事可做 → True, 不因"拓扑未知"变失败 (复审 F8 修的顺序)。"""
        drv, writes = _driver(info=None)
        await drv._readback_topology()
        assert await drv.set_doppler(frequency_hz=None, velocity_kmh=None) is True
        assert writes == []


class TestColdCacheOnDemandReadback:
    """★ 后端重启后驱动缓存空、F64 硬件仍在播放 —— 不许把"驱动忘了"升级成"现场重来"。

    (复审 P1: 只在 load 路填充 = 新建一道冷缓存硬门, 而恢复途径 load 的第一步 CLOSE
    会打断正在跑的仿真和 UE attach。)"""

    # ★ 三个写方法**逐个**钉住 (删掉任一处 ensure 都要变红)。只钉 set_path_loss 会让
    # 另两处的 ensure 零覆盖 —— 复审用变异实证过这种"只补一半"。
    @pytest.mark.parametrize("call,prefix", [
        (lambda d: d.set_path_loss(path_loss_db=5.0), "OUTP:LOSS:SET"),
        (lambda d: d.set_baseband_power(-15.0), "INP:LEV:AMP:CH"),
        (lambda d: d.set_doppler(frequency_hz=0.0), "DIAG:SIMU:MOB:MAN:CH"),
    ])
    async def test_cold_cache_refills_from_instrument_when_simulation_alive(self, call, prefix):
        drv, writes = _driver(info="4,128,32")
        # 模拟后端重启: 缓存全空, 但仪器仍在 STOPPED (加载着仿真)
        drv._clear_topology()

        async def _q(cmd, timeout=None, **_kw):
            if cmd == "DIAG:SIMU:STATE?":
                return "STOPPED"                  # 仿真还在, 只是驱动忘了
            return await _orig_q(cmd, timeout)

        _orig_q = drv._query
        drv._query = _q  # type: ignore[assignment]
        assert await call(drv) is True
        assert [w for w in writes if w.startswith(prefix)], "冷缓存没按需补回读"

    async def test_cold_cache_with_closed_simulation_still_fails_loud(self):
        """真的没加载仿真 (CLOSED) → 不盲试 MODEL:INFO?, 照常 fail-loud。"""
        drv, writes = _driver(info="4,128,32", state="CLOSED")
        drv._clear_topology()                     # 缓存空 + CLOSED = 自洽的"没加载"
        assert await drv.set_path_loss(path_loss_db=5.0) is False
        assert writes == []


class TestTopologyOverrideBringUpEscape:
    """★ 人工声明兜底 —— `GROUP:*` 这几条**没在真机验过**, 而本项目实证过"手册里有、
    这台机器回 -100"。若真机不支持, 路损/增益/多普勒/CENT 会全线拒且**现场无解**
    (输入侧还能显式传 ports, 输出侧一个口子都没有)。铁律: 新增 fail-loud 门必须同步
    给 bring-up 绕过开关。"""

    _OVERRIDE = {"inputs": [1, 2], "outputs": [1, 2, 3, 4],
                 "channels": [1, 2, 3, 4, 5, 6, 7, 8]}

    def _drv_with_override(self, *, info, override=None):
        drv, writes = _driver(info=info)
        drv._topology_override = RealPropsimF64Driver._parse_topology_override(
            override if override is not None else self._OVERRIDE
        )
        return drv, writes

    async def test_override_applied_when_readback_fails(self):
        """回读失败 (命令不支持) → 套用声明值, 路损照声明的口下发。"""
        drv, writes = self._drv_with_override(info=None)   # MODEL:INFO? 抛异常
        await drv._readback_topology()
        assert drv.get_active_output_ports() == [1, 2, 3, 4]
        assert await drv.set_path_loss(path_loss_db=6.0) is True
        assert _loss_ports(writes) == [1, 2, 3, 4]

    async def test_override_applies_on_any_readback_failure_stage(self):
        """回读的**任一环**失败都该兜底 (不只 MODEL:INFO? 那一环)。

        ⚠ 声明值必须与 MODEL:INFO? 报的口数**一致** (2 输入 / 4 输出 / 8 通道 ↔
        "2,8,4") —— 三值读到了、只有 GROUP:* 失败时, 声明的是"口号"而非"口数",
        对不上会被矛盾检测拒绝 (那是另一条用例钉的行为)。"""
        for failing in ("GROUP:GET?", "GROUP:CHANNELS:GET?", "GROUP:OUTPUTS:GET?"):
            drv, _ = _driver(info="2,8,4", err_on=failing)
            drv._topology_override = RealPropsimF64Driver._parse_topology_override(self._OVERRIDE)
            await drv._readback_topology()
            assert drv.get_active_output_ports() == [1, 2, 3, 4], f"{failing} 未兜底"

    async def test_override_refused_when_contradicting_readback(self):
        """★ 仪器说 32 个输出口、人声明 4 个 → **拒绝套用**, 不是静默采信人。

        这是逃生门最危险的形态 (复审 P2): "MODEL:INFO? 正常、只有 GROUP:* 不支持"
        恰恰是 override 最可能被启用的场景, 操作员若照旧设备抄了 4 口, 无条件覆盖会让
        32 个探头只配 4 个**并返回 True**, get_metrics 还报 active_outputs=4 给错误
        背书 —— 本 PR 要治的病从逃生门原样回来。两个值同时在手且打架 = fail-loud。"""
        drv, _ = _driver(info="4,128,32", err_on="GROUP:GET?")
        drv._topology_override = RealPropsimF64Driver._parse_topology_override(self._OVERRIDE)
        await drv._readback_topology()
        assert drv.get_active_output_ports() is None, "矛盾的声明值被采信了"
        assert await drv.set_path_loss(path_loss_db=1.0) is False
        # 仪器读到的口数保留 (供排障), 但端口号仍是未知 → 写操作拒绝
        assert drv._active_outputs == 32

    async def test_metrics_marks_declared_topology_source(self):
        """套用声明值时 metrics 必须标 `topology_source=declared` —— 否则诊断面会
        拿人填的口号当仪器真值给操作员背书。"""
        drv, _ = self._drv_with_override(info=None)
        await drv._readback_topology()
        m = await drv.get_metrics()
        assert m.metrics["topology_source"] == "declared"

    async def test_readback_value_wins_over_override(self):
        """★ 回读到的真值**永远优先** —— 人可能填错, 或换了 .smu 忘了改声明。"""
        drv, _ = self._drv_with_override(info="4,128,32")
        await drv._readback_topology()
        assert drv.get_active_output_ports() == list(range(1, 33)), "声明值盖住了真值"

    async def test_doppler_and_baseband_also_covered_by_override(self):
        """兜底要覆盖全部消费方, 不能只救路损 (漏一个就仍然现场无解)。"""
        drv, writes = self._drv_with_override(info=None)
        await drv._readback_topology()
        assert await drv.set_doppler(frequency_hz=0.0) is True
        assert await drv.set_baseband_power(-15.0) is True
        chans = [w for w in writes if w.startswith("DIAG:SIMU:MOB:MAN:CH")]
        inputs = [w for w in writes if w.startswith("INP:LEV:AMP:CH")]
        assert len(chans) == 8 and len(inputs) == 2

    @pytest.mark.parametrize("bad", [
        {"inputs": [1], "outputs": [1]},                 # 缺 channels
        {"inputs": [], "outputs": [1], "channels": [1]},  # 空列表
        {"inputs": [0], "outputs": [1], "channels": [1]},  # 非正整数
        {"inputs": [1], "outputs": ["a"], "channels": [1]},  # 非整数
        "not-a-dict",
    ])
    def test_malformed_override_rejected_wholesale(self, bad):
        """配错了整体作废 + ERROR 日志 —— 半个声明比没有更糟 (另一半照样拒, 更难查)。"""
        assert RealPropsimF64Driver._parse_topology_override(bad) is None


class TestPublicEnsureTopology:
    """`ensure_topology()` 公开版给端点/编排层用 —— 它们只能读同步 getter, 不 await
    这一步就会在"后端重启但 F64 仍在播"时退化成拒绝 (反而不如改动前)。"""

    async def test_get_metrics_refills_cold_cache_and_queries_real_ports(self):
        """★ 读路也要补读 (删掉 get_metrics 里的 ensure 这条会红)。

        后端重启后 broadcaster 每秒调的正是 get_metrics —— 不补读就恒为空 dict +
        "跳过查询", 监控面失明直到有人碰一次写端点。"""
        drv, _ = _driver(info="4,128,32")
        drv._clear_topology()                         # 冷缓存
        _orig_q = drv._query

        async def _q(cmd, timeout=None, **_kw):
            if cmd == "DIAG:SIMU:STATE?":
                return "RUNNING"                      # 硬件仍加载着仿真在播
            if "MEAS:RES:GET?" in cmd:
                return "-20.5"
            return await _orig_q(cmd, timeout)

        drv._query = _q  # type: ignore[assignment]
        m = await drv.get_metrics()
        assert len(m.metrics["output_powers_dbm"]) == 32, "没补读 → 监控面失明"
        assert m.metrics["topology_source"] == "readback"

    @staticmethod
    def _failing_driver():
        """拓扑冷缓存 + 回读必失败 (模拟真机不支持 GROUP:*/MODEL:INFO?)。"""
        drv, _ = _driver(info="4,128,32")
        drv._clear_topology()
        probes = {"n": 0}

        async def _q(cmd, timeout=None, **_kw):
            if cmd == "DIAG:SIMU:STATE?":
                probes["n"] += 1
                return "RUNNING"
            if cmd == "DIAG:SIMU:MODEL:INFO?":
                raise RuntimeError("固件不支持 (-100)")
            if "SYST:ERR" in cmd:
                return '0,"No error"'
            return "1"

        drv._query = _q  # type: ignore[assignment]
        return drv, probes

    async def test_polling_path_is_throttled_after_failure(self):
        """★ **轮询路**(get_metrics) 补读持续失败时要节流: broadcaster 1 Hz × 每次整段
        回读 (5+3N 条) 且全程持锁 = SCPI 通道被占死。"""
        drv, probes = self._failing_driver()
        for _ in range(5):
            assert await drv._ensure_topology(throttle=True) is False
        assert probes["n"] == 1, f"轮询路未节流, 探测了 {probes['n']} 次"

    async def test_human_initiated_writes_are_never_throttled(self):
        """★ **人发起的写**绝不节流 —— 操作员完全可能在冷却期内从**前面板**加载 .smu
        (现场真实工作方式), 驱动无从知情。照样早退 = 最长 N 秒里全线误拒, 报错还说
        "仿真未加载"并引人去配 override (错误的解药), 而仪器上仿真明明在跑。"""
        drv, probes = self._failing_driver()
        for _ in range(5):
            assert await drv.ensure_topology() is False       # 默认 throttle=False
        assert probes["n"] == 5, f"人点一次就该真问一次仪器, 实际只探测了 {probes['n']} 次"

    # ★ 三个写方法**逐个**钉住 (Codex #224 P2: 参数化 throttle 时 set_doppler /
    # set_baseband_power 两处被误传 throttle=True, 而已有测试没先置冷却抓不到 ——
    # 无冷却时 throttle=True 也能补读, 只有"冷却激活"才暴露差别)。
    @pytest.mark.parametrize("call,prefix", [
        (lambda d: d.set_path_loss(path_loss_db=3.0), "OUTP:LOSS:SET"),
        (lambda d: d.set_baseband_power(-15.0), "INP:LEV:AMP:CH"),
        (lambda d: d.set_doppler(frequency_hz=0.0), "DIAG:SIMU:MOB:MAN:CH"),
    ])
    async def test_write_path_recovers_immediately_after_front_panel_load(self, call, prefix):
        """★ 前面板换 .smu 的完整闭环: 轮询失败置了**激活的冷却** → 人点写操作 →
        必须立刻重探成功 (写路传了 throttle=True 这条就红)。"""
        drv, writes = _driver(info="4,128,32")
        drv._clear_topology()
        alive = {"v": False}
        _orig_q = drv._query

        async def _q(cmd, timeout=None, **_kw):
            if cmd == "DIAG:SIMU:STATE?":
                return "RUNNING" if alive["v"] else "CLOSED"
            return await _orig_q(cmd, timeout)

        drv._query = _q  # type: ignore[assignment]
        assert await drv._ensure_topology(throttle=True) is False   # 轮询: CLOSED → 置冷却
        alive["v"] = True                                           # 操作员从前面板加载了
        assert await call(drv) is True, "被上一轮的冷却挡住了 (写路被节流)"
        assert [w for w in writes if w.startswith(prefix)]

    async def test_session_reset_clears_retry_cooldown(self):
        """冷却也是"由已加载文件决定"的一类 → 会话边界必须一起清 (它曾漏在
        `_clear_topology` 之外, 让新会话继承上个会话的静默期)。"""
        drv, _ = _driver(info="4,128,32")
        drv._topology_retry_after = time.monotonic() + 999
        drv._apply_session_reset()
        assert drv._topology_retry_after == 0.0

    async def test_successful_load_clears_retry_cooldown(self):
        """换了仿真要立刻按新拓扑重试, 不能被上一个仿真的失败冷却挡住。"""
        drv, _ = _driver(info="4,128,32")
        drv._topology_retry_after = time.monotonic() + 999
        await drv._readback_topology()                # 主动回读 (load 成功路)
        assert drv._topology_retry_after == 0.0
        assert drv.get_active_output_ports() == list(range(1, 33))

    async def test_public_wrapper_refills_cold_cache(self):
        drv, _ = _driver(info="4,128,32")
        drv._clear_topology()

        _orig_q = drv._query

        async def _q(cmd, timeout=None, **_kw):
            if cmd == "DIAG:SIMU:STATE?":
                return "RUNNING"                    # 仿真还在跑
            return await _orig_q(cmd, timeout)

        drv._query = _q  # type: ignore[assignment]
        assert await drv.ensure_topology() is True
        assert drv.get_active_output_ports() == list(range(1, 33))


class TestAbsurdValuesDoNotHangDriver:
    """★ 畸形回复不许把驱动拖死 —— broadcaster 每秒调 get_metrics, 一旦进天文数字
    循环就是持锁狂发 SCPI、整机不可恢复。"""

    @pytest.mark.parametrize("info", ["4,1e20,1e20", "99999,99999,99999", "1,2,2000"])
    async def test_out_of_range_dims_rejected(self, info):
        drv, writes = _driver(info=info)
        await drv._readback_topology()
        assert drv._active_outputs is None
        assert await drv.set_path_loss(path_loss_db=1.0) is False
        assert writes == []
        m = await drv.get_metrics()
        assert m.metrics["output_powers_dbm"] == {}      # 不进天文数字循环
