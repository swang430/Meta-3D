# -*- coding: utf-8 -*-
"""P2-57：信道仿真器的能力 manifest。

**为什么不复用 `BaseStationAdapterManifest`**（用户 2026-09-02 拍板）：
基站 manifest 的脊梁是「MAC profile 的逐维度取值域」，而信道仿真器的脊梁是
**每个驱动操作各自实现没有** —— 硬套会带进一堆恒空的字段。所以这里以
`operation × support` 为主轴，另附 load mode。

**它要替换掉什么**：本模块出现之前，「这个驱动支不支持某操作」是用
`hasattr(emulator, "stop_emulation")` 这类**运行时探测**回答的。那个做法有两个
致命处：

  · 它问的是「类上有没有这个名字」，而不是「这个驱动真的实现了吗」——
    基类一旦有同名桩（哪怕只 `raise NotImplementedError`），探测就恒为真；
  · 反过来，基类**没有**桩时（P2-57 之前正是如此：14 个抽象方法整段掉在类体
    之外、嵌在一个模块级函数里），未实现的驱动抛的是不受控的 `AttributeError`，
    而不是可读的拒绝理由。

所以能力必须**显式声明**，且声明与实现由门对账，不靠 `hasattr` 猜。
"""

from __future__ import annotations

import re
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


_TOKEN_RE = re.compile(r"^[a-z][a-z0-9_]*$")

#: `ChannelEmulatorDriver` 上**必须存在**的抽象操作全集。
#:
#: ⚠️ 这个元组同时是三件事的真值源：① manifest 必须逐个声明（不许沉默省略）；
#:    ② 类体完整性门按它检查基类；③ 换源后的能力查询按它取值。
#:    加操作要同时更新这三处 —— 门会强制。
CHANNEL_EMULATOR_OPERATIONS: tuple[str, ...] = (
    "set_mimo_config",
    "set_path_loss",
    "set_doppler",
    "start_emulation",
    "stop_emulation",
    "get_channel_state",
    "upload_asc_files",
    "set_external_attenuators",
    "set_baseband_power",
    "get_calibration_tone_capabilities",
    "set_calibration_tone",
    "stop_calibration_tone",
    "set_passthrough_mode",
    "clear_passthrough_mode",
)

ChannelEmulatorOperation = Literal[
    "set_mimo_config",
    "set_path_loss",
    "set_doppler",
    "start_emulation",
    "stop_emulation",
    "get_channel_state",
    "upload_asc_files",
    "set_external_attenuators",
    "set_baseband_power",
    "get_calibration_tone_capabilities",
    "set_calibration_tone",
    "stop_calibration_tone",
    "set_passthrough_mode",
    "clear_passthrough_mode",
]

#: 与 `ChannelLoadMode` 枚举同源；这里独立写一份是为了让 manifest 模块
#: 不反向依赖驱动模块（驱动要 import manifest）。门断言两者集合相等。
ChannelEmulatorLoadMode = Literal[
    "native_model",
    "external_waveform",
    "parametric_tdl",
]


class ChannelEmulatorOperationCapability(BaseModel):
    """一个驱动操作的支持状态。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: ChannelEmulatorOperation
    #: `implemented` = 该驱动类**自己**定义了这个方法（继承基类的
    #: `NotImplementedError` 桩**不算**）；`not_implemented` = 尚未实现，
    #: 调用会被上层挡住；`not_applicable` = 该型号不存在这个概念。
    support: Literal["implemented", "not_implemented", "not_applicable"]
    reason: str
    source_reference: str | None = None

    @field_validator("reason")
    @classmethod
    def _reason_non_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("operation capability reason must be non-blank")
        return normalized


class ChannelEmulatorLoadModeCapability(BaseModel):
    """一种信道加载模式的支持状态。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: ChannelEmulatorLoadMode
    support: Literal["implemented", "not_implemented"]
    reason: str

    @field_validator("reason")
    @classmethod
    def _reason_non_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("load mode capability reason must be non-blank")
        return normalized


class ChannelEmulatorManifest(BaseModel):
    """一个信道仿真器 adapter 的不可变能力声明。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    adapter_id: str
    model_name: str
    vendor: str
    load_modes: tuple[ChannelEmulatorLoadModeCapability, ...]
    operations: tuple[ChannelEmulatorOperationCapability, ...]

    @field_validator("adapter_id")
    @classmethod
    def _valid_adapter_id(cls, value: str) -> str:
        normalized = value.strip()
        if not _TOKEN_RE.fullmatch(normalized):
            raise ValueError("adapter_id must be a lowercase identifier")
        return normalized

    @model_validator(mode="after")
    def _covers_every_operation_exactly_once(self) -> "ChannelEmulatorManifest":
        """操作声明必须**恰好覆盖全集一次** —— 不许沉默省略。

        这是本 manifest 的 fail-closed 核心：漏声明一个操作，
        就等于回到「没人知道它支不支持」的旧状态，而那正是本片要治的病。
        多声明（重复）同样拒 —— 同一操作两个答案，取哪个都是猜。
        """

        declared = [item.operation for item in self.operations]
        if len(set(declared)) != len(declared):
            raise ValueError("channel emulator operations must be unique")
        missing = sorted(set(CHANNEL_EMULATOR_OPERATIONS) - set(declared))
        if missing:
            raise ValueError(
                "channel emulator manifest does not declare: " + ", ".join(missing)
            )
        return self

    @model_validator(mode="after")
    def _load_modes_are_unique(self) -> "ChannelEmulatorManifest":
        modes = [item.mode for item in self.load_modes]
        if len(set(modes)) != len(modes):
            raise ValueError("channel emulator load modes must be unique")
        return self

    # ------------------------------------------------------------------
    # 查询面：这些方法替换掉散落各处的 hasattr 探测
    # ------------------------------------------------------------------

    def implements(self, operation: str) -> bool:
        """该 adapter 是否**真的实现**了这个操作。

        替换 `hasattr(emulator, operation)`：后者问的是「类上有没有这个名字」，
        P2-57 给基类补齐 14 个 `NotImplementedError` 桩之后，那个问法对**每一个**
        驱动都恒为真 —— 也就是彻底失效。
        """

        if operation not in CHANNEL_EMULATOR_OPERATIONS:
            raise ValueError(f"unknown channel emulator operation: {operation!r}")
        for item in self.operations:
            if item.operation == operation:
                return item.support == "implemented"
        # `_covers_every_operation_exactly_once` 保证走不到这里
        raise ValueError(f"manifest does not declare {operation!r}")

    def rejection_reason(self, operation: str) -> str | None:
        """未实现时给出可操作的理由；已实现返回 None。"""

        if self.implements(operation):
            return None
        for item in self.operations:
            if item.operation == operation:
                return (
                    f"{self.model_name} 不支持 {operation}"
                    f"（{item.support}）：{item.reason}"
                )
        return None

    def supported_load_modes(self) -> tuple[str, ...]:
        return tuple(
            item.mode for item in self.load_modes if item.support == "implemented"
        )


def channel_emulator_operation_names() -> tuple[str, ...]:
    """给门用：`Literal` 的取值域与 `CHANNEL_EMULATOR_OPERATIONS` 必须相等。"""

    return tuple(get_args(ChannelEmulatorOperation))


def channel_emulator_manifest_of(emulator: object) -> "ChannelEmulatorManifest | None":
    """取该对象的 manifest —— 类属性、实例属性都认；不是 manifest 的一律当没有。

    ⚠️ **上一版只读 `type(emulator)` 并在实例上发现 manifest 时抛 TypeError，
    内审 R2 把那个写法整个推翻了**，三条理由：

      · 它打破 `cleanup_chamber_instruments` 明文的 `Never raises` 契约，
        而那个函数在 `measure.py` 的 `finally:` 里 —— 抛出会**顶替掉触发
        收尾的原始异常**，还会跳过其后的落证与 commit。收尾语境里
        「判不出就崩」比「判不出就跳过」更糟，而本轮本来就是来治后者的；
      · 它只覆盖「类上没有 + 实例上有」，而**最可能发生**的「类上有 +
        实例又覆盖一份」仍是无声忽略 —— 堵住的恰好是已有构建期门守着的那格；
      · 本仓既有的 `adapter_manifest` 约定本来就是**实例级**的
        （`base_station.py` 的 `self.adapter_manifest = ...`）。既然两种写法
        都合理，就都读，不去发明一条只有本模块知道的规矩。

    「类级」这条纪律交给构建期门（`test_every_channel_emulator_driver_declares_a_manifest`）
    —— 它对真实驱动子类恒有效，且不会在运行期制造异常。

    ⚠️ 判 `isinstance` 而不是 `is not None`：`AsyncMock()` / `MagicMock()`
    会**自动生成**任意属性，`getattr(mock, "adapter_manifest")` 返回一个真值
    Mock 对象。只判非空就会在测试替身上 fail-**open**（每个操作都"支持"），
    方向正好反了。
    """

    manifest = getattr(emulator, "adapter_manifest", None)
    return manifest if isinstance(manifest, ChannelEmulatorManifest) else None


def channel_emulator_implements(emulator: object, operation: str) -> bool:
    """替换 `hasattr(emulator, operation)` 的**唯一**问法。

    ⚠️ 为什么必须换掉 `hasattr`：P2-57 把 14 个抽象方法搬回
    `ChannelEmulatorDriver` 之后，基类对每个操作都有一个
    `raise NotImplementedError` 的桩 —— 于是 `hasattr` 对**任何**驱动恒为真，
    那些「没有就跳过」的分支会全部翻成「调用然后崩」。
    换句话说：搬回类里与换掉 hasattr **必须同片**，否则前者制造回归。

    没有 `adapter_manifest` 的对象一律判为**不支持**（fail-closed）：
    新增型号必须显式声明才能被调用，不再继承一个假的共同基线。
    """

    # ⚠️ **不吞 ValueError**：操作名拼错要当场炸，不能被当成「不支持」。
    #    代价不对称 —— 误判「支持」会抛 NotImplementedError 并被上层记进
    #    warnings（看得见）；误判「不支持」会**静默跳过**，而其中就有
    #    cleanup 的停机动作（仪器可能仍在发射，操作员零信号）。
    #    这一格是**编码笔误**，不是仪器故障，所以它该穿透 best-effort 语境：
    #    第一次跑测试就会红，而不是在现场变成一次沉默的不停机。
    if operation not in CHANNEL_EMULATOR_OPERATIONS:
        raise ValueError(f"unknown channel emulator operation: {operation!r}")
    manifest = channel_emulator_manifest_of(emulator)
    if manifest is None:
        return False
    return manifest.implements(operation)


def channel_emulator_rejection(emulator: object, operation: str) -> str:
    """未实现时给调用方一条**可操作**的理由（替代不受控的 AttributeError）。

    与 `channel_emulator_implements` 同口径：同一个取 manifest 的函数、
    同一条拼错就炸的规矩（内审 F6 指出两者曾一个吞一个炸；R2 又指出它们
    在「实例级 manifest」上答案相反 —— 两次都是同一个病：两处各写一遍）。
    """

    if operation not in CHANNEL_EMULATOR_OPERATIONS:
        raise ValueError(f"unknown channel emulator operation: {operation!r}")
    manifest = channel_emulator_manifest_of(emulator)
    if manifest is None:
        # 传进来的可能是**类对象** —— `channel_emulator_manifest_of` 对类是正常
        # 工作的，所以那是个合法入参形态（外审 #448 C2 指出）。那时
        # `type(emulator).__name__` 是字面量 "type"，一条说了等于没说的理由，
        # 恰好抵消了本模块「用可读拒绝理由取代不受控 AttributeError」的意义。
        # ⚠️ 措辞收窄（内审 F2）：初版这里写「注册表自检 / 测试脚手架都会这么用」
        #    —— 全仓 12 个调用点**全部传实例**，那句话没有实例支撑，是我编的。
        # ⚠️ 取名必须**不抛**（内审 F3）：下游 `cleanup_chamber_instruments` 明文
        #    `Never raises`，而它在 `measure.py` 的 `finally:` 里。实测元类可以把
        #    `__name__` 定义成会抛的 property —— 那正是 R1→R2 已经踩过一次的坑。
        try:
            name = (
                emulator.__name__ if isinstance(emulator, type)
                else type(emulator).__name__
            )
        except Exception:  # noqa: BLE001
            name = "<取名失败的对象>"
        return (
            f"{name} 没有声明 channel emulator manifest，"
            f"因此不认为它实现了 {operation}（fail-closed）"
        )
    return manifest.rejection_reason(operation) or ""


def channel_emulator_manifest_for(
    *,
    adapter_id: str,
    model_name: str,
    vendor: str,
    implemented: tuple[str, ...],
    load_modes: tuple[str, ...] = (),
    reason: str = "declared by a test double / diagnostic harness",
) -> ChannelEmulatorManifest:
    """按「实现了哪些操作」快速构造 manifest，其余自动标 `not_implemented`。

    ⚠️ **只给测试替身与诊断脚手架用，生产驱动一律逐格字面声明。**
    理由：`ChannelEmulatorManifest` 的 fail-closed 核心是「必须逐个声明全部
    14 个操作」——本工厂会替你把没点名的补成 `not_implemented`，那对替身是
    便利，对生产驱动就是把「忘了声明」和「确实不支持」混成同一件事。
    生产侧那三个 manifest（F64 / FS16 / Mock）都是手写全量的。
    """

    unknown = sorted(set(implemented) - set(CHANNEL_EMULATOR_OPERATIONS))
    if unknown:
        raise ValueError(f"unknown channel emulator operations: {unknown}")
    return ChannelEmulatorManifest(
        schema_version=1,
        adapter_id=adapter_id,
        model_name=model_name,
        vendor=vendor,
        load_modes=tuple(
            ChannelEmulatorLoadModeCapability(
                mode=mode, support="implemented", reason=reason
            )
            for mode in load_modes
        ),
        operations=tuple(
            ChannelEmulatorOperationCapability(
                operation=name,
                support="implemented" if name in implemented else "not_implemented",
                reason=reason,
            )
            for name in CHANNEL_EMULATOR_OPERATIONS
        ),
    )
