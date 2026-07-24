"""
Keysight PROPSIM F64 Channel Emulator HAL Driver
=================================================

型号专用驱动，实现 ChannelEmulatorDriver 抽象接口。
基于 PyVISA 通过 TCP/IP Socket (端口 3334, ATE/SCPI 硬件固定口) 与 F64 ATE Server 通信。

支持两种信道加载管线：
  ┌──────────────────────────────────────────────────────┐
  │  Pipeline A — GCM 原生模式                          │
  │  F64 内置 Channel Studio 信道建模引擎               │
  │  用户下发 .smu 仿真文件, F64 原生编译并播放         │
  │  SCPI: CALC:FILT:FILE → DIAG:SIMU:GO               │
  └──────────────────────────────────────────────────────┘
  ┌──────────────────────────────────────────────────────┐
  │  Pipeline B — ASC Runtime Emulation 模式            │
  │  外部 Channel Engine 计算探头权重, 生成 ASC 波形    │
  │  通过 FTP 传输 .rtc 文件到 F64, 以 Runtime API 播放 │
  │  SCPI: CALC:FILT:FILE → CH:MOD:CONT:ENV             │
  └──────────────────────────────────────────────────────┘

SCPI 参考文档:
  - Propsim User Reference, Ch.20 "Standard Tools Remote Control"
  - PROPSIM Runtime Emulation User Guide
  - Propsim ATE Environment and Practices AN

TCP 端口说明 (User Reference §1.1.2.1: "Fixed TCP/IP port for PROPSIM is 3334"):
  - 3334: ATE/SCPI 端口 — PROPSIM 硬件固定不可改, 本驱动强制使用 (见 __init__)
  - 23:   Telnet ATE 端口
  ⚠ 5025 (Keysight/R&S 风格 SCPI-RAW 口) 在 F64 上 *不工作*: 响应 desync + 文件
     加载报 -300。早期配置/注释误用 5025 = 两天 first-call blocker 根因之一。
     [现场 2026-05-27 实测: 3334 加载/运行/改参全 0 error, 5025 全 desync]
"""

import logging
import asyncio
import os
import re
import time
from app.hal.scpi_lock import ReentrantAsyncLock
import ftplib
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Iterable, List, Optional, Tuple
from datetime import datetime

from app.hal.base import (
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics,
)
from app.hal.channel_emulator import (
    CalibrationToneCapability,
    ChannelEmulatorDriver,
    ChannelLoadMode,
)

logger = logging.getLogger(__name__)


# ===========================================================================
# F64 专用枚举和常量
# ===========================================================================

class F64Pipeline(str, Enum):
    """信道加载管线类型"""
    GCM_NATIVE = "gcm"          # Pipeline A: F64 原生 GCM
    ASC_RUNTIME = "asc_runtime" # Pipeline B: 外部 ASC + Runtime Emulation
    B2_PARAMETRIC_TDL = "b2_parametric_tdl"  # Pipeline C: P2-14 B-2 参数化 TDL (.tap/.rtc 硬件实时衰落)


class F64BypassMode(int, Enum):
    """F64 静态旁路模式 (DIAG:SIMU:MODEL:STATIC)
    User Reference §20.4.6.25"""
    DISABLED = 0           # 正常衰落
    CHANNEL_MODEL = 1      # 信道模型旁路 (平均衰减, 零相位)
    BUTLER = 2             # Butler 矩阵旁路 (拓扑感知相位)
    CALIBRATION = 3        # 校准旁路 (所有通道等增益/等延迟/零相位)


class F64InputMeasMode(int, Enum):
    """F64 输入功率测量模式 (INP:MEAS:MODE:SET, User Reference §20.4.4.23)。

    对 TDD 5G 下行 (只在 DL 时隙有信号) 必须用 BURST —— 它"在信号占空期测量",
    抓 DL 突发的真实 avg/crest; CONTINUOUS 会把 UL/保护间隔静默一起平均进去 → 低估。
    """
    DISABLED = 0
    BASIC = 1
    CONTINUOUS = 2
    BURST = 3


# F64 远程文件存储路径默认 (Windows F64 ATE 出厂约定)。
# 跨实验室部署时, 在 InstrumentCategory.config 里覆盖 emulation_dir /
# waveform_dir 以匹配本地 F64 服务器文件结构 (e.g. Linux F64 用 /opt/...
# 或 Windows F64 安装在非 D:\ 盘)。
F64_EMULATION_DIR = r"D:\User Emulations"
F64_WAVEFORM_DIR = r"D:\User Emulations\ASC"

# F64 默认信道仿真文件 (3GPP FR1 OTA CDL-C UMa, 3600 MHz/N78, 4 输入 MIMO OTA)。
# 现场 2026-05-27 真机实测 100% load/run 通过, 用户指定为默认 (P0-8 Step 4)。
# 操作员覆盖优先级 (高 → 低):
#   1) set_channel_model(parameters={"emulation_file": <path>}) —— per-call
#   2) InstrumentConnection.connection_params["default_emulation_file"] —— per-binding
#   3) F64_DEFAULT_EMULATION_FILE —— 本常量 (系统默认)
#   4) f"{self.emulation_dir}\\{model_type}_{scenario}_{tx}x{rx}.smu" —— 兜底 auto-name
#
# ── 路径 A/B 边界 (P2-11 Phase 5 固化) ──────────────────────────────────────
# 本常量是**路径 A (bring-up / 暗室首测) 的默认锚点**: 开机即就位到一个被确认工作的
# 已知基准。**正式测试 (路径 B) 不靠它** —— TestCase.emulation_file 经 measure →
# sim_rules 显式驱动 (上面优先级 #1 per-call), GCM 真 F64 未指定时 measure 严格门
# fail-loud (precheck_strict_emulation_file)。路径切分见
# docs/architecture/testcase-driven-instrument-config.md §2 (A/B) + §7 (Phase 表)。
F64_DEFAULT_EMULATION_FILE = (
    r"D:\Scenario Packs\F9815064A TS 5G FR1 MIMO OTA\1.1"
    r"\3GPP_FR1_OTA_CDLC_UMa_3600M.wiz"
    r"\3GPP_FR1_OTA_CDLC_UMa_3600M.smu"
)

# 3600M 默认文件的 (tx_antennas, rx_antennas) MIMO 天线维度 (Codex on PR #97):
# 加载默认文件后, set_channel_model 据此同步 _tx/_rx 缓存; 否则 _tx/_rx 停构造默认
# 2x2, 下游 set_path_loss 等按错通道数配 → RF 失真。
# ⚠ 这是 MIMO 天线维度 (4x4 = BS 4 TX 层 × UE 4 RX 层), **不是物理口数** —— MPAC OTA
# 里物理输出 = 探头 (3600M MODEL:INFO?='4,128,32', 32 探头), 从仪器回读真实物理拓扑
# + 消费方改用探头数 = F64R-2「端口从拓扑回读」深水区 (P0-3 缩范围不碰)。非默认文件由
# operator 经 set_mimo_config 预设拓扑 (现有惯例)。
F64_DEFAULT_EMULATION_FILE_TOPOLOGY: Tuple[int, int] = (4, 4)

# VISA 超时常量 (毫秒)
VISA_TIMEOUT_DEFAULT = 5000
VISA_TIMEOUT_FILE_LOAD = 30000  # 大文件加载需要更长超时
VISA_TIMEOUT_AUTOSET = 15000    # 自动电平校准

# F64R-2 拓扑回读的合理性上界 (口数 / 通道数 / 组数)。
# F64 整机 64 个衰落通道、探头阵列几十路, 真实值远在此之下 —— 这道闸挡的是**回复错位**:
# 3334 会话串线后 `MODEL:INFO?` 可能拿到别的查询的数字 (本项目有实证)。若恰好凑成三个
# "正整数"(如 `4,1e20,1e20`), 下游 `range(1, 1e20)` 会把进程吃死, 而 broadcaster 每秒
# 调一次 get_metrics → 持锁狂发 SCPI, 驱动永久卡死不可恢复。超界一律判"读不到"。
_TOPOLOGY_SANITY_MAX = 1024

# 信道组数的绝对硬上界。每组要发 3 条查询且全程持锁, 组数被畸形回复撑大 = 驱动锁死。
# F64 整机 64 通道, 真实分组远小于此。
# ⚠ 这是**唯一**用于硬拒的组数上界 (另一条 `≤ 逻辑通道数` 也是硬事实)。手册推导出的
# `min(输入口数, 输出口数)` **只用于 WARNING 留痕**, 不参与硬拒 —— 推导 ≠ 仪器契约,
# 详见组回读处的注释。
_GROUP_COUNT_HARD_MAX = 64

# 按需补读失败后的静默期 (秒)。broadcaster 1 Hz 调 get_metrics, 补读若持续失败又不节流
# 就是每秒重跑整段回读并持锁 —— 真机不支持这几条命令时会把 SCPI 通道占死。
_TOPOLOGY_RETRY_COOLDOWN_S = 30.0

# 拓扑相关 fail-loud 文案统一附带的逃生门提示。现场高压时不该靠记忆去翻文档找绕过
# 开关 —— 尤其 `f64_output_gain_db` 这条路**没有** per-step 端口参数, topology_override
# 是唯一解, 报错里不写就等于没有。**引用本常量, 别手抄副本** (抄了改常量不会同步)。
_TOPOLOGY_ESCAPE_HINT = (
    "(真机若不支持 GROUP:*/MODEL:INFO?, 可在仪器 connection_params 配 "
    "topology_override 声明口号)"
)

# FTP 凭据 (PROPSIM 出厂默认)
F64_FTP_USER = "PROPSIM"
F64_FTP_PASS = "propsim"


# F64 ATE Server sometimes returns IEEE 488.2-shaped error strings as
# the *response* to a query instead of raising. Probe code that just
# checks "did we get a non-None string?" gets fooled — the payload says
# the command isn't supported but looks like a normal response to the
# transport. Detect these here so license-probe / feature-probe code
# can reject them uniformly.
#
# Shape:  '<+|-><code>,"<description>"'  with optional leading whitespace.
# Codes in -100..-109 / -113 / -114 mean "command not supported" — same
# buckets the propsim_f64_health categorizer treats as UNSUPPORTED.
_F64_SCPI_ERROR_RE = re.compile(
    r'^\s*([+-]?\d+)\s*,\s*"[^"]*"\s*$'
)


def _is_unsupported_error_payload(response: str) -> bool:
    """True iff ``response`` looks like an IEEE 488.2 error tuple whose
    code maps to UNSUPPORTED.

    Matches the canonical ``-100,"ATE command not supported"`` shape
    F64 emits when a SCPI command isn't in firmware (Codex P1 review
    on #15). Same code ranges as
    ``propsim_f64_health._categorize_status`` — adding a code there
    should also update this guard.

    Returns False for empty strings, normal-looking responses, and
    non-error tuples (e.g. ``0,"No error"`` is the SYST:ERR? "all
    clear" sentinel — not an unsupported flag, must NOT count as such).
    """
    if not response or not isinstance(response, str):
        return False
    m = _F64_SCPI_ERROR_RE.match(response)
    if m is None:
        return False
    try:
        code = int(m.group(1))
    except ValueError:
        return False
    # Same buckets as propsim_f64_health._categorize_status.
    # -100..-109: F64 ATE Server "command not in firmware"
    # -113/-114:  IEEE 488.2 undefined header / suffix
    if -109 <= code <= -100:
        return True
    if code in (-113, -114):
        return True
    return False

# *OPT? 查询返回里, 表示 "Internal Interference Generator" license 的候选 token.
# 不同 firmware revision 用不同代号, 命中任一即认定该 license 存在. CAICT 现场首
# 测后建议把列表收紧到实际返回的唯一值.
@dataclass(frozen=True)
class F64SysInfo:
    """Structured parse of PROPSIM F64 ``SYST:INFO?`` response (P3-4).

    F64's SYST:INFO? returns a comma-separated mix of positional + labeled
    fields. Pre-P3-4, ``connect()`` only extracted ``parts[1]`` for
    channel_count and threw the rest away. This dataclass surfaces:
        - product_family / firmware_version / band_label for the startup
          readiness report (operator at the console can confirm what F64
          firmware they're talking to without manually checking the
          device panel)
        - secondary_count (positional [4], semantic unclear — kept as raw
          int for future label-discovery)
        - extra_tokens for forward compatibility with firmware revisions
          adding new fields

    Field positions verified against:
        - propsim_f64.py inline comment (CAICT 2026-05-13 site reference)
        - test_f64_license_probe.py fixture strings (multiple
          firmware variants)

    Pure data — no methods, no I/O. The legacy keyword scan in
    ``_probe_installed_options()`` continues to handle license-token
    discovery; this dataclass is for hardware metadata only.
    """
    raw: str  # original SYST:INFO? response as received
    product_family: Optional[str] = None  # e.g. "PROPSIM F64"
    channel_count: Optional[int] = None  # positional [1]
    signal_type: Optional[str] = None  # positional [2], typically "RF"
    firmware_version: Optional[str] = None  # positional [3], e.g. "v1.0"
    secondary_count: Optional[int] = None  # positional [4]; semantics TBD
    band_label: Optional[str] = None  # labeled "Band: 450MHz - 3000MHz"
    extra_tokens: List[str] = field(default_factory=list)


def parse_f64_sys_info(raw: Optional[str]) -> F64SysInfo:
    """Parse a SYST:INFO? response string into structured fields (P3-4).

    Defensive: every field falls back to ``None`` if missing or
    unparseable. Empty input → ``F64SysInfo(raw="")`` with all
    fields None. Never raises.

    Recognized shapes (verified samples):
        Full:    "PROPSIM F64,64,RF,v1.0,16,Band: 450MHz - 3000MHz,Interference Generator,Calibration User Alignment"
        Trimmed: "PROPSIM F64,64,RF,v1.0,16,Band: 450MHz - 3000MHz"
        Minimal: "PROPSIM F64,64,RF,v1.0,16"
        Skinny:  "PROPSIM F64,64,RF"

    Tokens not matched by a positional slot or a known label end up in
    ``extra_tokens`` (license keywords like "Interference Generator"
    or future firmware additions) so they survive into the readiness
    report without parser changes.
    """
    if not raw:
        return F64SysInfo(raw=raw or "")
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        return F64SysInfo(raw=raw)

    product_family = parts[0] if len(parts) > 0 else None

    channel_count: Optional[int] = None
    if len(parts) > 1:
        try:
            channel_count = int(parts[1])
        except ValueError:
            pass

    signal_type = parts[2] if len(parts) > 2 else None
    firmware_version = parts[3] if len(parts) > 3 else None

    secondary_count: Optional[int] = None
    if len(parts) > 4:
        try:
            secondary_count = int(parts[4])
        except ValueError:
            pass

    band_label: Optional[str] = None
    extra: List[str] = []
    # Anything from index 5 onward: try the "Band:" label first; otherwise
    # bucket as extra_tokens (preserves license keywords + forward-compat
    # for unknown future fields). Case-insensitive label match because
    # firmware capitalisation has drifted historically.
    for p in parts[5:]:
        if p.lower().startswith("band:"):
            band_label = p[len("band:"):].strip()
        else:
            extra.append(p)

    return F64SysInfo(
        raw=raw,
        product_family=product_family,
        channel_count=channel_count,
        signal_type=signal_type,
        firmware_version=firmware_version,
        secondary_count=secondary_count,
        band_label=band_label,
        extra_tokens=extra,
    )


INTERFERENCE_GEN_OPTION_TOKENS = frozenset({
    "K01", "INTGEN", "INT-GEN", "INTERFERENCE-GEN", "OPT-INT-GEN",
    "INTERFERENCE_GENERATOR", "F64-K01",
})


class RealPropsimF64Driver(ChannelEmulatorDriver):
    """
    Keysight PROPSIM F64 真实 SCPI 驱动 (HAL Layer 3)
    ─────────────────────────────────────────────────
    继承链: InstrumentDriver → ChannelEmulatorDriver → RealPropsimF64Driver

    本驱动统一覆盖 GCM 原生管线和 ASC Runtime 管线的 SCPI 翻译。
    应用层通过 load_channel(mode=...) 统一入口选择管线,
    驱动内部自动管理仿真文件的加载、启动和停止。

    管线能力:
      - NATIVE_MODEL:      GCM 原生管线 (CALC:FILT:FILE → DIAG:SIMU:GO)
      - EXTERNAL_WAVEFORM:  ASC Runtime 管线 (FTP → CALC:FILT:FILE → CH:MOD:CONT:ENV)
    """

    # P2-3: F64 family CAN expose these tokens — whether a given unit
    # actually does depends on optional K01 license + on whether operator
    # has loaded a user alignment. Live ``self.capabilities`` is the
    # subset that this physical unit confirmed at connect().
    model_capabilities = frozenset({
        # F64 K01 internal interference generator (license-gated, probed
        # via *OPT?). Catalog answer for "can F64 do CE+SA path-loss cal":
        # yes, conditional on license.
        "ce.interference_generator",
        # F64 integrated setup calibration (per-deployment alignment table
        # loaded via SYST:CALIB:USER:SET). Catalog answer for "can F64
        # apply user alignment": yes, conditional on alignment being loaded.
        "ce.user_alignment",
    })

    # P2-17 (Codex #201 P2): STATIC 直通能力标志 — set_passthrough_mode 定义在
    # 基类, hasattr 判定会对 FS16 等误开 (高层方法 NotImplementedError)。attach
    # 直通编排等消费方按此标志 gate, 而不是 hasattr / 类名。
    SUPPORTS_STATIC_PASSTHROUGH: bool = True

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        # 连接参数
        self.ip_address: str = config.get("ip", "192.168.100.21")
        # PROPSIM F64 ATE/SCPI 端口固定为 3334 (User Reference §1.1.2.1:
        # "Fixed TCP/IP port for PROPSIM is 3334")。早期配置/默认误用 5025
        # (Keysight/R&S 风格的 SCPI-RAW 口) → 在 F64 上响应 desync + 文件加载报
        # -300。强制 3334、忽略 config 端口 (PROPSIM 此口硬件固定不可改)。
        # [现场 2026-05-27 实测: 3334 加载/运行/改参全 0 error, 5025 全 desync]
        self.port: int = 3334
        self.ftp_user: str = config.get("ftp_user", F64_FTP_USER)
        self.ftp_pass: str = config.get("ftp_pass", F64_FTP_PASS)
        # Phase 2h: 跨实验室部署时由 InstrumentCategory.config 覆盖
        self.emulation_dir: str = config.get("emulation_dir", F64_EMULATION_DIR)
        self.waveform_dir: str = config.get("waveform_dir", F64_WAVEFORM_DIR)
        # P0-8 Step 4: 默认信道仿真文件。操作员可经 connection_params 覆盖
        # (HAL service 在 init 时已 merge connection_params 进 config; 无需迁移)。
        # 设为 falsy ("" / None) 则回退到 auto-name (legacy 行为)。
        self._default_emulation_file: str = config.get(
            "default_emulation_file", F64_DEFAULT_EMULATION_FILE
        )
        # ── F64R-2: 拓扑**人工声明**兜底 (bring-up 绕过开关) ──
        # 回读永远优先; 只有**回读不到**时才用这里声明的值 (并打 WARNING)。
        # 为什么必须有: `GROUP:*` / `MODEL:INFO?` 这几条**没在真机验过**, 而本项目实证
        # 过"手册里有、这台机器回 -100 命令不存在"(MMEM/FTP/*OPT?)。若真机不支持, 路损/
        # 增益/多普勒/CENT 会全线 fail-loud 且**现场无解** —— 输入侧还能用 input_ports
        # 显式传, 输出侧一个口子都没有。这违反项目铁律「新增 fail-loud 门必须同步给
        # bring-up 绕过开关」(memory strict-gate-extend-bypass-toggle)。
        # 「不猜」不等于「不许操作员显式声明」: 猜是软件替人瞎填, 声明是人按实际接线负责。
        # 形如 {"inputs": [1,2], "outputs": [1,2,3,4], "channels": [1,2,3,4,5,6,7,8]}
        # (端口/通道**号**列表, 不是数量)。
        self._topology_override: Optional[Dict[str, List[int]]] = self._parse_topology_override(
            config.get("topology_override")
        )
        # 默认文件的已知 MIMO 拓扑, 加载后 set_channel_model 同步缓存 (Codex on PR #97),
        # 避免下游 set_path_loss 等按 stale 2x2 缓存配错通道数 (见常量注释)。
        self._default_emulation_file_topology: Optional[Tuple[int, int]] = config.get(
            "default_emulation_file_topology", F64_DEFAULT_EMULATION_FILE_TOPOLOGY
        )

        # Calibration-tone 能力: PROPSIM Internal Interference Generator 是
        # optional license. 默认在 connect() 中通过 *OPT? 探测 (见 base
        # _probe_installed_options + 本类 _apply_discovered_capabilities).
        # config 里显式给值 (True/False) 时跳过探测, 用于 mock / CI / 手动
        # override 场景:
        #   未设置        → connect() 时探测; 探测前为 None (按无 license 处理)
        #   True / False  → 显式声明, 跳过探测
        explicit = config.get("has_interference_generator")
        self._explicit_interference_gen: bool = explicit is not None
        self.has_interference_generator: Optional[bool] = (
            bool(explicit) if self._explicit_interference_gen else None
        )
        # P2-2: mirror the legacy bool into the canonical capability set.
        # When the explicit-override path declares True/False at construct
        # time, ``_apply_discovered_capabilities`` will never run (it's
        # short-circuited at line 1913), so the set must be seeded here
        # too — otherwise plan-level pre-flight (P1-1) would think this
        # F64 doesn't have the interference generator even though config
        # said it does.
        if self._explicit_interference_gen and self.has_interference_generator:
            from app.hal.capabilities import CE_INTERFERENCE_GENERATOR
            self._add_capability(CE_INTERFERENCE_GENERATOR)
        # 固定 ID 给单 tone, 重复 set 时先 remove 旧的避免 "identifier in use".
        self._cal_tone_id: str = config.get("cal_tone_id", "ce_sa_cal_tone")
        self._cal_tone_active: bool = False

        # User alignment (Integrated Setup Calibration, optional license).
        # alignment_name 在 connect() 后会尝试 SYST:CALIB:USER:SET 1,<name>
        # 重新装载 — F64 重启后已存盘的 alignment 默认不激活, 必须显式调用 SET.
        # 留空表示这台 F64 不使用 user alignment, 仅依赖工厂校准 + 我们自己的
        # ProbePathLossCalibration.
        self._preferred_alignment_name: Optional[str] = (
            config.get("alignment_name") or None
        )
        self._active_alignment: Optional[Dict[str, Any]] = None
        # P2-10 Step 3: user alignment 新鲜度阈值 (天)。alignment 补偿随温度/时间漂移,
        # 超过阈值 → precheck 标 stale 建议重标。lab 维护策略, connection_params override。
        # Codex on PR #125: operator 清空该 optional override 时 connection_params 会留
        # null/"" (key 在但值空, 不走 .get 默认) → int(None)/int("") 崩 driver 构造, 一个
        # 可选设置拖垮整个 CE driver。容错回退默认 30 (非法字符串同理)。
        _raw_max_age = config.get("alignment_max_age_days")
        try:
            self._alignment_max_age_days: int = (
                int(_raw_max_age) if _raw_max_age not in (None, "") else 30
            )
        except (ValueError, TypeError):
            self._alignment_max_age_days = 30

        # PyVISA 资源句柄
        self._visa_resource = None
        self._rm = None

        # 管线状态追踪
        self._active_pipeline: Optional[F64Pipeline] = None
        self._loaded_emulation_file: Optional[str] = None
        self._emulation_running: bool = False
        self._bypass_mode: F64BypassMode = F64BypassMode.DISABLED
        self._passthrough_active: bool = False

        # 信道参数缓存 (最近一次配置)
        self._current_model: Optional[str] = None
        self._current_scenario: Optional[str] = None

        # 操作员维护的可选信道模型清单 (CAICT 现场验证: F64 SCPI 不支持
        # MMEM, FTP 在这台 F64 上未启用 — 不能动态发现 D:\User Emulations
        # 下有哪些 .smu/.rtc 文件. 操作员把文件名列在 InstrumentConnection.
        # connection_params['available_channel_models'] 里, GUI 下拉框拉这
        # 个清单). 等 F64 那边启了 FTP 或者我们走通 SMB 之后, 这个 field
        # 由动态发现取代, 但 API 接口形态不变.
        # 每条可以是 str (只有文件名) 或 dict {filename, label, description}.
        self._available_channel_models: List[Any] = (
            config.get("available_channel_models") or []
        )
        # P1-21 ①: per-driver SCPI 命令互斥 — 全部 _do_write/_do_query IO 串行化
        # (broadcaster 与测量序列并发共用单 socket 会应答串线, 现场 P1 根因)。
        self._scpi_lock = ReentrantAsyncLock()  # 可重入: 事务内 self._query 直通
        self._center_freq_mhz: float = 3500.0
        # P2-11 (Codex on PR #109 P2): 是否**显式下发过**中心频 (CALC:FILT:CENT:CH)。
        # False 时 _center_freq_mhz 只是默认值 3500, 不能当真值上报 —— get_frequency_
        # identity 退回解析 .smu 文件名。True (configure/set_channel_model 显式给了
        # center_frequency_mhz) 时 _center_freq_mhz 才是实际下发频率, 优先于文件名
        # (抓 "3600M.smu 被 configure 重调到 3500" 的坑)。
        self._center_freq_programmed: bool = False
        self._channel_count: int = 64
        self._tx_antennas: int = 2
        self._rx_antennas: int = 2
        # P0-3 (2026-07-23): 加载 .smu 后从仪器 CALC:FILT:CENT:CH? 回读的真中心频
        # (get_frequency_identity 优先于文件名, 治 "3600M.smu 实为 3550")。None = 尚未
        # 加载 / 回读失败。
        self._readback_center_freq_mhz: Optional[float] = None

        # ── F64R-2 (2026-07-24): 加载后从仿真回读的**真实拓扑** ──
        # 治 review 母题②「端口靠 tx×rx 猜」。手册 §20.4.3.6 `MODEL:INFO?` 返回
        # `<inputs>,<channels>,<outputs>`: inputs=物理**输入**口 (BS 天线口),
        # outputs=物理**输出**口 (探头), channels=**逻辑衰落通道** (=inputs×outputs)。
        # ⚠ `tx×rx` 是逻辑通道口径, 在 MPAC OTA 里**不等于探头数** (4 输入 × 32 探头
        # = 128 通道, 而输出口只有 32)。拿 tx×rx 当输出口上界循环 → 32 探头只配到前 16,
        # 17-32 留工程默认 = 现场「路损只设一半」根因。
        # None = 尚未加载 / 回读失败 → **写**操作 fail-loud 拒绝, 不回退猜口数
        # (用户 2026-07-24 拍板); **读**操作 (get_metrics) 跳过该项并标注, 不整体失败。
        self._active_inputs: Optional[int] = None
        self._active_outputs: Optional[int] = None
        self._active_channels: Optional[int] = None
        # 端口**号**列表 (GROUP:INPUTS/OUTPUTS:GET? 逐组取并集)。⚠ 只有"口数"是不够的:
        # 数量 N 不等于端口号就是 1..N —— Scenario Wizard 可以把仿真分配到非连续的物理口
        # (例如实际占用输出口 {2,4}, 数量=2)。照 1..N 下发会**误配口 1、漏配口 4**, 跟
        # "17-32 号探头没配"是同一个病换个形态。所以端口号也问仪器, 不推算。
        # 当前端口号是否来自**人工声明**而非仪器回读 —— 上报出去让操作员一眼看出
        # "这些口号是人填的, 不是仪器说的"(否则诊断面会给一个错误的声明值背书)。
        self._topology_from_override: bool = False
        # 按需补读的**失败负缓存**时间戳 (monotonic 秒)。broadcaster 每秒调 get_metrics,
        # 若补读持续失败 (真机不支持 GROUP:* / 交叉校验不符) 而不节流, 就会每秒重跑整段
        # 回读 (5+3N 条) 并全程持锁 —— 不支持时每条还要吃 VISA 超时 + 排水, SCPI 通道
        # 直接被占死: 现场"打开 GUI 仪表盘 = 测试步骤发不出命令"。
        self._topology_retry_after: float = 0.0
        self._active_input_ports: Optional[List[int]] = None
        self._active_output_ports: Optional[List[int]] = None
        # 逻辑通道**号**列表 (GROUP:CHANNELS:GET? 逐组取并集)。同"端口号不保证 1..N"的
        # 道理: 通道号也可能非连续/有偏移, 逐通道命令 (MOB:MAN:CH) 得按真实号发。
        self._active_channel_numbers: Optional[List[int]] = None
        # CENT 是 **per-group** 生效 (手册 §20.4.6.1: "Frequency is set for given channel
        # and for all the other channels belonging to the same group")。
        # 组的判定 (§20.4.6.4/20.4.6.6): 两个通道满足**任一**条件即同组 —— **输入相同**,
        # **或输出相同**。注意是"或"不是"仅按输出": 全交叉拓扑 (每个输入都连每个输出) 下
        # 通道会经输入/输出两个维度互相连通, 可能整个仿真**只有 1 组**; 非全交叉才分多组。
        # ⚠ 所以**组数不可推算, 必须回读** (GROUP:GET?) —— 存每组代表通道号 (该组
        # GROUP:CHANNELS:GET? 的首通道), CENT 按实际组数逐组发一次。
        # None = 组信息未回读 → CENT 下发 fail-loud。
        self._group_repr_channels: Optional[List[int]] = None

        # P3-4: structured SYST:INFO? metadata populated during connect().
        # Pre-P3-4 only ``_channel_count`` survived; these surface in the
        # startup readiness log + driver_selftest CLI output so the operator
        # sees firmware revision and band coverage without reading SCPI
        # transcripts. ``sys_info`` is the full parsed dataclass; the
        # individual ``firmware_version`` / ``band_label`` mirrors are
        # convenience attrs for the existing log call sites.
        self.sys_info: Optional[F64SysInfo] = None
        self.firmware_version: Optional[str] = None
        self.band_label: Optional[str] = None
        self.product_family: Optional[str] = None

    # ===================================================================
    # 0. 管线能力声明与统一入口 (重写母类)
    # ===================================================================

    def get_supported_load_modes(self) -> List[ChannelLoadMode]:
        """
        F64 支持的信道加载模式。

        Returns:
            [NATIVE_MODEL, EXTERNAL_WAVEFORM, PARAMETRIC_TDL]

        PARAMETRIC_TDL (P2-14 B-2): .tap/.rtc 参数化模型, 加载机制同 ASC Runtime
        (FTP + CALC:FILT:FILE), F64 按文件内容判参数化实时衰落 vs 烘焙。具体 .tap
        schema / gaussian 谱可用性现场标定 (V1.0 §9)。
        """
        return [
            ChannelLoadMode.NATIVE_MODEL,
            ChannelLoadMode.EXTERNAL_WAVEFORM,
            ChannelLoadMode.PARAMETRIC_TDL,
        ]

    async def load_channel(
        self,
        mode: ChannelLoadMode,
        model_name: str,
        scenario: str,
        parameters: Dict[str, Any],
        waveform_dir: Optional[str] = None,
    ) -> bool:
        """
        F64 统一信道加载入口（重写母类）。

        根据 mode 分发到 GCM 或 ASC 管线:
          - NATIVE_MODEL     → Pipeline A: set_channel_model()  (GCM)
          - EXTERNAL_WAVEFORM → Pipeline B: upload_asc_files()  (ASC Runtime)

        应用层无需关心 F64 内部使用哪种 SCPI 管线。
        """
        logger.info(f"[F64] load_channel: mode={mode.value}, model={model_name}")

        if mode == ChannelLoadMode.NATIVE_MODEL:
            # pipeline 由 set_channel_model 成功时才置 (F1 对称: 别在此乐观置, 否则加载
            # 失败/STOP 前超时会残留 stale GCM 而旧仿真是别的 pipeline)
            return await self.set_channel_model(model_name, scenario, parameters)

        elif mode == ChannelLoadMode.EXTERNAL_WAVEFORM:
            if not waveform_dir:
                raise ValueError("waveform_dir 是 ASC Runtime 管线的必需参数")
            # pipeline 由 upload_asc_files 成功时才置 (F1: 别在 dispatcher 乐观置, 否则
            # FTP 失败 CLOSE 前残留 stale ASC_RUNTIME 而旧仿真仍加载 → gate 误放行)
            return await self.upload_asc_files(waveform_dir, model_name)

        elif mode == ChannelLoadMode.PARAMETRIC_TDL:
            # P2-14 B-2: 参数化 TDL (.tap/.rtc) 硬件实时衰落
            if not waveform_dir:
                raise ValueError("waveform_dir 是 B-2 PARAMETRIC_TDL 管线的必需参数 (.tap/.rtc 目录)")
            return await self.load_parametric_tdl(waveform_dir, model_name)

        raise NotImplementedError(f"未知加载模式: {mode.value}")

    # ===================================================================
    # P0-3 (2026-07-23): SCPI 状态/拓扑/频率回读原子 + 手册化 .smu 加载事务
    # 治现场"load 从没成功"(F64 review 母题④) + "该问仪器的地方在猜"(母题②③)。
    # 手册格式 (NotebookLM「PROPSIM 资料」查证 2026-07-23):
    #   STATE?        → 全大写无引号 7 值 (§20.4.3.14)
    #   MODEL:INFO?   → 'inputs,channels,outputs' 纯数字逗号无空格 (§20.4.3.6)
    #   CENT:CH? <ch> → 单值 MHz 无单位 (§20.4.6.2)
    # 全驱动推广 (GO 豁免 / path-loss / get_metrics 用这些回读) 留 F64R-1/F64R-2。
    # ===================================================================

    async def _query_simulation_state(self) -> Optional[str]:
        """DIAG:SIMU:STATE? → 归一化大写状态。§20.4.3.14: 全大写无引号,7 值
        CLOSED/OPENING/STOPPING/STOPPED/RUNNING/EDITING/CLOSING。读不到 → None。"""
        try:
            raw = await self._query("DIAG:SIMU:STATE?")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[F64] DIAG:SIMU:STATE? 查询失败: {e}")
            return None
        return raw.strip().upper() if raw and raw.strip() else None

    async def _readback_center_freq(self, ch: int = 1) -> Optional[float]:
        """CALC:FILT:CENT:CH? <ch> → 该通道组中心频 (MHz)。§20.4.6.2: 单值无单位,
        如 '1800'。读不到 / 解析失败 → None。"""
        try:
            raw = await self._query(f"CALC:FILT:CENT:CH? {ch}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[F64] CALC:FILT:CENT:CH? {ch} 查询失败: {e}")
            return None
        if not raw or not raw.strip():
            return None
        try:
            return float(raw.strip())
        except ValueError:
            logger.warning(f"[F64] CENT:CH? 返回非数值: {raw.strip()!r}")
            return None

    # ===================================================================
    # 状态复位单一入口 (2026-07-23 P0-3 状态机重构, Codex #223 + 矩阵审计):
    # identity/加载/运行态 6 字段的复位曾散落 ~20 处内联, 是"清 stale 漏一处"
    # 母题反复逃逸 (7 轮评审) 的根因。收敛为两个按**事件语义**声明的方法, 加新
    # 字段 / 加新 load 路径只改这里。见 memory clear-stale-state-enumerate-all-sources。
    #
    # 语义边界 (关键): **running 独立于 loaded**。
    #   - STOP = pause: 只停播放 (_emulation_running=False), 不卸载 → 不调这两个方法,
    #     调用点单独置 running=False (文件仍加载, identity 仍有效)。
    #   - CLOSE / *RST = unload: 停播放 + 卸载 → _apply_unload (清 identity+pipeline)。
    #   - 会话边界 (connect/disconnect/reset) → _apply_session_reset (再清 bypass)。
    # ===================================================================

    def _apply_unload(self) -> None:
        """卸载 / 加载失败后复位"已加载场景"状态 (调用点需自证 CLOSE/*RST 已发 →
        旧仿真已停+卸载)。清运行态 + 加载文件 + freq identity (programmed/readback) +
        pipeline + **拓扑真值** (F64R-2)。**不含 _bypass_mode** (bypass 是独立 config
        旋钮, 仅会话边界复位)。

        ⚠ 拓扑 (inputs/outputs/channels/组代表通道) 跟 freq identity 同属"由**已加载
        文件**决定"的一类 —— 卸载后必须一并清成 None, 否则下一个文件加载失败时会拿
        **上一个仿真**的口数去配端口 (stale 拓扑比没有拓扑更危险: 口数看着有效, 实际
        配到别的仿真的口上)。加新的"由文件决定"字段一律加在本方法, 别再内联复位。"""
        self._emulation_running = False
        self._loaded_emulation_file = None
        self._center_freq_programmed = False
        self._readback_center_freq_mhz = None
        self._active_pipeline = None
        self._clear_topology()

    def _clear_topology(self) -> None:
        """清空"由已加载文件决定"的拓扑真值 —— **拓扑字段的唯一复位入口**。

        被两处共用: `_apply_unload()`(卸载/加载失败) 与 `_readback_topology()` 入口
        (回读前先清, 见那里的说明)。加新的拓扑字段只改这一处 —— 散落内联复位正是
        P0-3 里同一个母题反复逃逸 7 轮的根因 (memory clear-stale-state-enumerate-all-sources)。"""
        self._active_inputs = None
        self._active_outputs = None
        self._active_channels = None
        self._active_input_ports = None
        self._active_output_ports = None
        self._active_channel_numbers = None
        self._group_repr_channels = None
        self._topology_from_override = False
        # 失败静默期也是"由已加载文件决定"的一类: 换仿真 / 会话边界都该立刻重试,
        # 不能继承上一轮的冷却 (放这里才被 _apply_session_reset 等所有复位路径覆盖)。
        self._topology_retry_after = 0.0

    def _apply_session_reset(self) -> None:
        """会话边界 (connect 起始 / disconnect 终态 / reset) 无条件全清 6 字段 =
        _apply_unload() + _bypass_mode 复位 (会话切换必须清 bypass, 否则跨会话残留)。"""
        self._apply_unload()
        self._bypass_mode = F64BypassMode.DISABLED

    async def _close_and_read_state(self) -> Optional[str]:
        """DIAG:SIMU:CLOSE + *OPC? + 回读 STATE? —— 三路加载 (GCM/ASC/B-2) 共用的"关闭并
        确认卸载"单一入口 (Codex #223 复审)。返回 CLOSE 后的归一化大写状态 (CLOSED/STOPPED/
        …) 或 None (查询失败)。

        ⚠ 语义 (关键): DIAG:SIMU:STOP=**暂停**(STOPPED=仍加载), DIAG:SIMU:CLOSE=**卸载**
        (CLOSED=已卸载)。调用方判 ==CLOSED 才算**确认卸载**; !=CLOSED (STOPPED=仍加载暂停,
        或 None=通信异常) → 旧场景仍加载, 调用方应**保留 identity + fail-loud 不硬闯 FILE**
        (旧盲发 CLOSE 后硬闯 FILE 是现场'load 从没成功'根因; 清 identity 会漏报旧场景)。
        调用方负责持 _scpi_lock。"""
        await self._write("DIAG:SIMU:CLOSE")
        await self._query("*OPC?")
        return await self._query_simulation_state()

    @staticmethod
    def _parse_topology_override(raw: Any) -> Optional[Dict[str, List[int]]]:
        """解析操作员声明的拓扑兜底 (见 `_topology_override` 字段注释)。

        要求 inputs / outputs / channels **三者齐全**且都是正整数号码列表 —— 缺一不可,
        因为消费方分别依赖它们 (路损用 outputs / 输入电平用 inputs / 多普勒用 channels),
        只声明一半会让另一半照样 fail-loud, 反而更难排查。任一项不合格 → 整体判无效 +
        ERROR 日志 (配错了要当场知道, 不能静默当没声明)。"""
        if not raw:
            return None
        if not isinstance(raw, dict):
            logger.error(f"[F64] topology_override 必须是对象, 实得 {type(raw).__name__} — 忽略")
            return None
        out: Dict[str, List[int]] = {}
        for key in ("inputs", "outputs", "channels"):
            vals = raw.get(key)
            if not isinstance(vals, (list, tuple)) or not vals:
                logger.error(f"[F64] topology_override.{key} 缺失或非非空列表 — 整体忽略")
                return None
            nums: List[int] = []
            for v in vals:
                if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
                    logger.error(f"[F64] topology_override.{key} 含非正整数 {v!r} — 整体忽略")
                    return None
                nums.append(v)
            out[key] = sorted(set(nums))
        logger.warning(
            f"[F64] 已启用拓扑人工声明兜底 (仅在回读失败时生效): 输入口={out['inputs']} "
            f"输出口={out['outputs']} 通道={len(out['channels'])} 个"
        )
        return out

    def _apply_topology_override(self) -> bool:
        """回读不到时套用人工声明的拓扑。返回是否套用了。

        ⚠ 只在**回读确实失败**后调用 —— 回读到的真值永远优先于人工声明 (人可能填错、
        或换了 .smu 忘了改)。套用时打 WARNING, 让操作员知道当前用的是声明值不是真值。

        ⚠⚠ **绝不覆盖已经读到的口数** (复审 P2, 逃生门差点把本 PR 治的病放回来):
        最常见的启用形态是"`MODEL:INFO?` 正常、只有 `GROUP:*` 不支持" —— 此时仪器已经
        明说输出口有 32 个, 若拿操作员照旧设备抄的 `outputs:[1,2,3,4]` 无条件覆盖, 就又
        变成"32 个探头只配 4 个"且返回 True, 连 get_metrics 都会报 `active_outputs=4`
        **反过来给错误背书**。两个值同时在手且打架时, 唯一正确的动作是 **ERROR + 拒绝
        套用**, 让人去查为什么对不上 —— 不是静默采信人。
        """
        ov = self._topology_override
        if not ov:
            return False
        # 与已回读到的口数交叉核对: 对不上 = 声明写错了 / 换了 .smu 没改声明 → 拒绝。
        for label, declared, readback in (
            ("inputs", len(ov["inputs"]), self._active_inputs),
            ("outputs", len(ov["outputs"]), self._active_outputs),
            ("channels", len(ov["channels"]), self._active_channels),
        ):
            if readback and readback != declared:
                logger.error(
                    "[F64] topology_override.%s 声明 %d 个, 但仪器 MODEL:INFO? 回读到 "
                    "%d 个 —— 两者矛盾, **拒绝套用声明值** (照声明配会漏配/错配)。"
                    "请核对声明与当前 .smu 是否为同一套接线。",
                    label, declared, readback,
                )
                return False
        self._active_input_ports = list(ov["inputs"])
        self._active_output_ports = list(ov["outputs"])
        self._active_channel_numbers = list(ov["channels"])
        # 口数: 回读到就保留仪器真值 (只有端口**号**是声明补的); 没读到才用声明数量。
        self._active_inputs = self._active_inputs or len(ov["inputs"])
        self._active_outputs = self._active_outputs or len(ov["outputs"])
        self._active_channels = self._active_channels or len(ov["channels"])
        # CENT 代表通道: 声明模式下无法知道真实分组, 保守起见**逐通道**下发 (CENT 对
        # 同组其余通道重复写是幂等的, 只是多几条命令; 漏发才是真问题)。
        self._group_repr_channels = list(ov["channels"])
        self._topology_from_override = True
        logger.warning(
            "[F64] 拓扑回读失败 → **套用人工声明值** (非仪器真值): 输入口=%s 输出口=%s; "
            "若与实际接线不符会配错口, 请尽快确认 GROUP:*/MODEL:INFO? 为何读不到",
            self._active_input_ports, self._active_output_ports,
        )
        return True

    @staticmethod
    def _parse_csv_ints(raw: Optional[str]) -> List[int]:
        """解析 F64 的 CSV 整数回复 ("1,2,3,4" → [1,2,3,4])。

        **任一段非法 → 返回 []**(整体判定"读不到"), 不返回残缺列表 —— 端口号是拿来
        寻址硬件的, 半信半疑的列表比没有更危险 (会配到错的口)。容 "1.0" 这类浮点写法,
        但拒 "1.9" (非整数不可能是端口号, 说明回复串线了)。"""
        if not raw:
            return []
        out: List[int] = []
        for seg in raw.strip().split(","):
            seg = seg.strip()
            if not seg:
                return []
            try:
                val = float(seg)
            except (TypeError, ValueError):
                return []
            if not val.is_integer():
                return []
            out.append(int(val))
        return out

    async def _readback_topology(self) -> None:
        """加载成功后回读**真实拓扑** (F64R-2, 治 review 母题②「该问仪器的地方在猜」)。

        序列 (手册 §20.4.3.6 + §20.4.7, NotebookLM + 本地 PDF 双查证):
          `DIAG:SIMU:MODEL:INFO?`      → `<inputs>,<channels>,<outputs>` (三个**数量**)
              inputs=物理输入口(BS 天线口) / channels=逻辑衰落通道 / outputs=物理输出口(探头)
          `GROUP:GET?`                 → 信道组**数量**(纯数字, 非组编号列表)
          `GROUP:CHANNELS:GET? <g>`    → 该组通道 CSV → 取**首通道**作该组 CENT 代表
          `GROUP:INPUTS:GET? <g>`      → 该组物理**输入口号** CSV  ┐逐组取并集 =
          `GROUP:OUTPUTS:GET? <g>`     → 该组物理**输出口号** CSV  ┘真实端口号集合

        ⚠ 为什么口数不够、还要端口**号**: 数量 N **不保证**端口号就是 1..N —— Scenario
        Wizard 可把仿真分配到非连续物理口 (如实际占用输出 {2,4}, 数量=2)。照 1..N 下发会
        误配口 1、漏配口 4。所以端口号也回读, 并与 MODEL:INFO? 的数量交叉校验, 不符 =
        判"读不到"(宁可 fail-loud, 不拿半信半疑的端口号配硬件)。

        ⚠ 前置条件: 仿真**已加载**。手册 §20.4.3.6 只定义了"currently run emulation"的
        返回, 未加载 (CLOSED) 时行为**手册未涵盖** → 只在 FILE 加载成功后调用, 不盲试。
        三条加载路 (GCM/ASC/B-2) 成功后都必须调本方法, 见各自成功分支。

        ⚠ **入口先无条件清空旧拓扑**: 否则"加载新文件成功、但回读失败"会残留**上一个
        仿真**的口数 —— 日志喊着 fail-loud、实际却照旧口数写满端口 (日志说谎), 甚至出现
        三个字段来自新仿真、一个来自旧仿真的**混代**状态。清了之后失败 = 干净的"未知"。

        ⚠ **不让 load 失败**: 加载本身已经成功 (FILE + *OPC? + SYST:ERR? 都过了), 拓扑
        读不到不该回滚它。失败 → 字段留 None + WARNING, 后果由消费方承担: **写**操作
        (set_path_loss / CENT / baseband_power) fail-loud 拒绝, **读**操作 (get_metrics)
        跳过该项并标注。调用方负责持 _scpi_lock。

        ⚠ 回读失败后, 若操作员配了 `topology_override` 则**套用人工声明值**兜底 (回读
        真值永远优先)。这是 bring-up 绕过开关 —— 见 `_topology_override` 字段注释。
        """
        # (失败静默期由 _clear_topology 统一清零 —— 它在下面的实现体入口被调用)
        await self._readback_topology_from_instrument()
        if not (self._active_output_ports and self._active_input_ports):
            # 回读的**任一环**失败都会落到这里 (共 9 个失败出口) —— 兜底只判一次终态,
            # 不在每个出口内联, 免得加新出口时漏掉 (本项目反复踩的 fan-out 母题)。
            self._apply_topology_override()

    async def _readback_topology_from_instrument(self) -> None:
        """`_readback_topology` 的实现体: 纯粹向仪器回读, 不含人工声明兜底。"""
        # 入口无条件清 —— "不写 = 继承上一个仿真的值"是本项目反复踩的母题。
        self._clear_topology()

        # ——拓扑三值 (inputs/channels/outputs)——
        try:
            dims = self._parse_csv_ints(await self._query("DIAG:SIMU:MODEL:INFO?"))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[F64] 拓扑回读失败 (MODEL:INFO? 异常: {e}) — 端口配置将 fail-loud")
            return
        if len(dims) != 3 or any(d <= 0 for d in dims):
            logger.warning(
                f"[F64] 拓扑回读无效 (MODEL:INFO? 期望 3 个正整数, 实得 {dims}) — "
                f"端口配置将 fail-loud"
            )
            return
        # ⚠ 上界**不能**用 `_channel_count`(SYST:INFO? 的整机衰落通道数, 如 64): 那是
        # 硬件资源数, 而 MODEL:INFO? 的 channels 是**逻辑**通道数 (inputs×outputs), OTA
        # 全交叉下 4×32=128 **本来就超过** 64 —— 拿它当闸会把完全正常的 OTA 仿真判成
        # "回复错位"。两个量单位不同, 不可互相约束。故用独立常数。
        sanity_max = _TOPOLOGY_SANITY_MAX
        if any(d > sanity_max for d in dims):
            # 上界闸: 3334 会话错位后回复偏移是本项目的实证失败模式, 若恰好凑成三个
            # "正整数"(如 4,1e20,1e20), 下游 range(1, 1e20) 会把进程吃死 —— broadcaster
            # 每秒调 get_metrics, 会持锁狂发 SCPI 直到整机不可恢复。宁可判读不到。
            logger.warning(
                f"[F64] 拓扑回读值超出合理上界 {sanity_max} (实得 {dims}, "
                f"疑似回复错位) — 端口配置将 fail-loud"
            )
            return
        self._active_inputs, self._active_channels, self._active_outputs = dims
        if self._active_inputs * self._active_outputs != self._active_channels:
            # 非全交叉拓扑是合法的 (不是所有输入都连所有输出), 只记录不拦 —— 但值得留痕:
            # MPAC OTA 全交叉场景下不相等往往意味着加载的不是预期的仿真。
            logger.info(
                f"[F64] 拓扑非全交叉: inputs={self._active_inputs} × "
                f"outputs={self._active_outputs} ≠ channels={self._active_channels}"
            )
        logger.info(
            f"[F64] 拓扑回读: 输入口={self._active_inputs} 输出口(探头)="
            f"{self._active_outputs} 逻辑通道={self._active_channels}"
        )

        # ——逐组回读: CENT 代表通道 + 真实端口号——
        # 独立于拓扑三值: 组信息读不到只让 CENT / 端口下发 fail-loud, 不影响已落库的
        # 三值 (get_metrics 仍能上报口数供人排查)。
        try:
            group_count_raw = self._parse_csv_ints(await self._query("GROUP:GET?"))
            if len(group_count_raw) != 1 or group_count_raw[0] <= 0:
                logger.warning(
                    f"[F64] 组数回读无效 (GROUP:GET? 期望单个正整数, 实得 "
                    f"{group_count_raw}) — CENT / 端口下发将 fail-loud"
                )
                return
            group_count = group_count_raw[0]
            # 组循环每组要发 3 条查询、全程持锁, 所以组数必须有硬上界: 畸形回复
            # (如 "1000,1024,1000") 三值都能过 _TOPOLOGY_SANITY_MAX, 若不再收紧,
            # 组数可达上千 → 3000+ 条 SCPI 串行, VISA 每条最长 5 s → 驱动被锁死数
            # 小时、broadcaster 全堵。
            # ——组数合理性: 硬拒 vs 只留痕, 分清两类依据——
            # 【硬拒】只用**不可能更宽**的两条: 组是通道的划分 (≤ 通道数) + 绝对常数
            # (挡"每组 3 条查询 × 上千组"的锁死)。这两条挡的是回复错位, 不会误伤真机。
            _group_ceiling = min(self._active_channels, _GROUP_COUNT_HARD_MAX)
            # 【只留痕】min(输入口数, 输出口数) 是手册 §20.4.6.1 的**推导**结论 (NotebookLM
            # 复核): "同输入**或**同输出即同组"定义连通分量且有传递性 → 组间输入集/输出集
            # 都不相交 → 每组至少各独占 1 输入 + 1 输出。实例: 4in×32out 全交叉 = 1 组;
            # 4 输入各独占 8 输出 = 4 组 (正好触 min(4,32)=4)。
            # ⚠ 但**推导不等于仪器契约**: .smu 工程里的 "[Channel Group N]" 可能是频率组
            # 等别的口径, 与路由连通分量不重合。拿推导做硬拒 → 真机一旦不符, 现场表现是
            # "命令全支持却什么都配不上", 日志还说"疑似回复错位", 排障方向被带偏。
            # 抗锁死的收益 HARD_MAX 已经拿到了, 这里再拒是重复收益 + 新增误拒风险 →
            # 超出只 WARNING 留痕, 照常继续。
            _physical_expect = min(self._active_inputs, self._active_outputs)
            if group_count > _physical_expect:
                logger.warning(
                    f"[F64] 组数 {group_count} 超出手册推导的物理预期 {_physical_expect} "
                    f"(输入 {self._active_inputs} / 输出 {self._active_outputs}) —— 仍按仪器"
                    f"回读值继续。若后续端口配置异常, 先怀疑组语义与路由连通分量不一致。"
                )
            if group_count > _group_ceiling:
                # 组是通道的划分, 组数不可能超通道数 —— 超了说明回复串线/解析错位,
                # 宁可判定读不到, 也不照着荒谬的组数循环几百条命令。
                logger.warning(
                    f"[F64] 组数 {group_count} 超出硬上限 {_group_ceiling} "
                    f"(= min(逻辑通道数 {self._active_channels}, 常数 "
                    f"{_GROUP_COUNT_HARD_MAX})) — 疑似回复错位, CENT / 端口下发将 fail-loud"
                )
                return
            reprs: List[int] = []
            in_ports: set[int] = set()
            out_ports: set[int] = set()
            all_chans: set[int] = set()
            # ⚠ 组**号**这里只能假定 1..N: 手册 (§20.4.7) 只给了 `GROup:GET?`(数量),
            # **没有** `GROup:LIST?` 这样的编号列举查询 —— 跟端口/通道号能回读不同, 组号
            # 无从问起。若真机组号非 1 起连续, `GROUP:CHANNELS:GET? 2` 会空/报错 → 下面
            # 的交叉校验兜底判"读不到" → 全线 fail-loud (降级是安全的, 但现象会是"命令
            # 都支持却什么都配不上", 排障时先怀疑这里)。
            for g in range(1, group_count + 1):
                chans = self._parse_csv_ints(await self._query(f"GROUP:CHANNELS:GET? {g}"))
                if not chans or any(c <= 0 for c in chans):
                    logger.warning(f"[F64] 组 {g} 通道列表回读无效 ({chans}) — CENT / 端口下发将 fail-loud")
                    return
                reprs.append(chans[0])   # 首通道即可: CENT 对同组其余通道一并生效
                all_chans.update(chans)  # 逐通道命令 (MOB:MAN:CH) 要按真实通道号发
                g_in = self._parse_csv_ints(await self._query(f"GROUP:INPUTS:GET? {g}"))
                g_out = self._parse_csv_ints(await self._query(f"GROUP:OUTPUTS:GET? {g}"))
                # 端口号必须是**正整数** —— 负数/0 是解析错位的信号 (回复串线), 照发会
                # 变成 `OUTP:LOSS:SET -1,...` 只能靠仪器拒绝兜底。
                if (not g_in or not g_out
                        or any(p <= 0 for p in g_in) or any(p <= 0 for p in g_out)):
                    logger.warning(
                        f"[F64] 组 {g} 端口号回读无效 (in={g_in} out={g_out}) — 端口下发将 fail-loud"
                    )
                    return
                in_ports.update(g_in)
                out_ports.update(g_out)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[F64] 组信息回读失败 ({e}) — CENT / 端口下发将 fail-loud")
            return

        # 交叉校验: 端口号集合大小必须等于 MODEL:INFO? 报的口数。不符 = 两个来源打架,
        # 判"读不到" —— 拿对不上的端口号配硬件比不配更危险。
        if (len(in_ports) != self._active_inputs
                or len(out_ports) != self._active_outputs
                or len(all_chans) != self._active_channels):
            logger.warning(
                f"[F64] 回读的号码集合与 MODEL:INFO? 的数量不符: 输入口 {sorted(in_ports)}"
                f"(期望 {self._active_inputs} 个) / 输出口 {sorted(out_ports)}"
                f"(期望 {self._active_outputs} 个) / 通道 {len(all_chans)} 个"
                f"(期望 {self._active_channels} 个) — 端口下发将 fail-loud"
            )
            return

        self._group_repr_channels = reprs
        self._active_input_ports = sorted(in_ports)
        self._active_output_ports = sorted(out_ports)
        self._active_channel_numbers = sorted(all_chans)
        logger.info(
            f"[F64] 信道组回读: {len(reprs)} 组, 代表通道={reprs}; "
            f"真实输入口={self._active_input_ports} 输出口={self._active_output_ports}; "
            f"通道号 {len(self._active_channel_numbers)} 个"
        )

    def _topology_source(self) -> str:
        """端口号的来源, 上报给操作员判断"这些口号能不能信"。

        readback = 仪器回读的真值 / declared = 回读失败后套用的**人工声明**兜底值 /
        unknown = 都没有。⚠ 只此一处定义 —— get_metrics 与 get_channel_state 两条上报
        路都引用它 (手抄副本会在加第四态时漏改一处, 本文件已有 _TOPOLOGY_ESCAPE_HINT
        的同类教训)。"""
        if self._topology_from_override:
            return "declared"
        return "readback" if self._active_output_ports else "unknown"

    async def _ensure_topology(self, *, throttle: bool = False) -> bool:
        """端口写操作前确保拓扑可用; 冷缓存时**按需补回读一次**。返回是否可用。

        ⚠ 为什么必须有这个 (F64R-2 复审 P1, 差点造成现场事故):
        `_readback_topology()` 只在三条 **load 成功**分支跑。但驱动的内存状态和 F64 的
        硬件状态是**两回事** —— 2026-07-21 现场实证: 重启后端后驱动缓存全空, 而 F64
        硬件**仍加载着信道在播放、UE 还 attach 着**。此时若拿"缓存是空的"当硬门, 所有
        端口写 (路损/增益/输入电平/CENT) 全被拒, 而唯一的恢复途径是重新 load —— load
        第一步就是 CLOSE, **会打断正在跑的仿真和 UE attach**。这就把"驱动忘了"升级成
        "现场重来"。同文件 `start_emulation` 早就写过同一条教训 (冷缓存不做 gate)。

        解法不是回退去猜, 而是**去问仪器**: 缓存空时先查 `STATE?`, 只要不是 CLOSED
        (说明硬件确实加载着仿真, `MODEL:INFO?` 的前置条件此刻满足) 就补跑一次回读。
        真读不到才 fail-loud —— 保住"不猜"的底线, 同时不误伤活着的仿真。
        """
        if self._active_output_ports and self._active_input_ports:
            return True
        if not self._visa_resource:
            return False
        # ⚠ 失败节流**只对高频轮询路生效** (throttle=True, 目前只有 get_metrics):
        # broadcaster 每秒调一次, 补读若持续失败 (真机不支持 GROUP:* / 交叉校验不符)
        # 不节流就是每秒重跑 5+3N 条查询且全程持锁; 命令不存在若表现为无应答, 每次还要
        # 吃 VISA 超时 + 排水 —— SCPI 通道被占死。
        # ⚠⚠ 但**人发起的写操作绝不节流** (throttle=False, 默认): 操作员完全可能在冷却
        # 期内从**前面板**加载 .smu (本项目现场的真实工作方式) —— 那时驱动无从知情, 若
        # 照样早退, 后续 set_path_loss / 输入参考 / crest 会在最长 N 秒里全线误拒, 报错
        # 还说"仿真未加载"并引人去配 topology_override (**错误的解药**), 而仪器上仿真
        # 明明在跑。人点一次就该真去问一次仪器。
        if throttle and time.monotonic() < self._topology_retry_after:
            return False
        async with self._scpi_lock:
            # 双重检查: 等锁期间别的协程可能已经补回读完了
            if self._active_output_ports and self._active_input_ports:
                return True
            state = await self._query_simulation_state()
            if state is None or state == "CLOSED":
                # 真没加载仿真 (或状态读不到) → 不盲试 MODEL:INFO? (手册未定义未加载时
                # 的行为), 让调用方 fail-loud。
                logger.warning(
                    f"[F64] 拓扑缓存为空且 STATE?={state} — 不补回读, 端口操作将 fail-loud"
                )
                self._topology_retry_after = time.monotonic() + _TOPOLOGY_RETRY_COOLDOWN_S
                return False
            logger.info(f"[F64] 拓扑缓存为空但仿真在 {state} 态 (疑似后端重启) — 按需补回读")
            await self._readback_topology()
        ok = bool(self._active_output_ports and self._active_input_ports)
        if not ok:
            self._topology_retry_after = time.monotonic() + _TOPOLOGY_RETRY_COOLDOWN_S
        return ok

    async def ensure_topology(self) -> bool:
        """公开版 `_ensure_topology` —— 供 **HTTP 端点 / 编排层**在读端口 getter 前调用。

        端口 getter (`get_active_output_ports` 等) 是同步的、只读内存缓存, 冷缓存时会
        返回 None。调用方若直接读它就 fail-loud, 会在"后端重启但 F64 仍在播"这个真实
        场景下误拒 (F64R-2 复审: /crest-factor 就这么退化成 400, 反而不如改动前)。
        先 await 本方法即可让驱动按需向仪器补读一次。"""
        return await self._ensure_topology()

    # ——公开能力查询 (给编排层用, 免得上层再读私有字段自己推 F64R-2)——

    def get_active_output_count(self) -> Optional[int]:
        """当前加载仿真的**物理输出口数** (= MPAC 探头数), 由 `MODEL:INFO?` 回读。

        None = 仿真未加载 / 回读失败。调用方此时应 **fail-loud**, 不要回退到
        `tx×rx` 或整机通道数去猜 —— 那正是 review 母题② 的错法: `tx×rx` 是**逻辑
        通道**口径, MPAC OTA 下 4 输入×32 探头 = 128 通道而输出口只有 32, 拿 tx×rx
        (=16) 当输出口上界会让 32 探头**只配到前 16**。"""
        return self._active_outputs

    def get_active_input_count(self) -> Optional[int]:
        """当前加载仿真的**物理输入口数** (= 基站天线口), 由 `MODEL:INFO?` 回读。
        None = 未加载 / 回读失败 → 调用方 fail-loud。"""
        return self._active_inputs

    def get_active_output_ports(self) -> Optional[List[int]]:
        """当前加载仿真占用的**物理输出口号列表** (探头), 由 `GROUP:OUTPUTS:GET?` 逐组
        取并集回读。要**逐口下发**的调用方用这个, 别用 count 去 `range(1, N+1)` ——
        端口号不保证连续 (仿真可能占用 {2,4}, 数量=2)。None = 未加载 / 回读失败。"""
        return list(self._active_output_ports) if self._active_output_ports else None

    def get_active_input_ports(self) -> Optional[List[int]]:
        """当前加载仿真占用的**物理输入口号列表** (基站天线口), 同上由 `GROUP:INPUTS:GET?`
        逐组取并集回读。None = 未加载 / 回读失败。"""
        return list(self._active_input_ports) if self._active_input_ports else None

    async def _load_smu_with_preflight(self, file_path: str) -> bool:
        """按 PROPSIM 手册教科书序列加载 .smu (P0-3, F64 review 母题④, 治现场
        'load 从没成功')。整段持 _scpi_lock (broadcaster 轮询不插入 CLOSE/FILE 之间)。

        序列 (ATE AN §5.3 + User Reference §20.4.3; STATE? 手册保证实现、必须硬依赖):
          drain → STATE? 判态 →(RUNNING 则 STOP+*OPC?; OPENING/STOPPING/CLOSING 则
          *OPC? 等稳)→ CLOSE → *OPC? → ★复查 STATE?==CLOSED (没真关就 fail-loud,不硬闯
          FILE —— 旧盲发 CLOSE 吞错是现场 CALC:FILT:FILE 超时根因)→ 抬超时 CALC:FILT:FILE
          → *OPC? → SYST:ERR? 门 → ★CENT:CH? 1 回读真频 (identity, 治文件名说谎)。

        成功 True + 更新 _readback_center_freq_mhz(真频); 失败 fail-loud False + 置
        _last_error。**失败时 helper 自己据 close_confirmed 精确清 identity** (CLOSE 确认卸载后
        失败 → 旧场景已卸载, 清 loaded/programmed/readback/emulation_running; CLOSE 未确认卸载
        / CLOSE 前失败 → 旧场景仍加载, 保留 identity 让一致性网仍能核对旧频率)。调用方
        只负责成功时设 _loaded_emulation_file 等身份缓存, 不再无条件清 (Codex #223 第四条)。

        ⚠ 拓扑回读 (F64R-2, 2026-07-24 补): 加载成功后接 `_readback_topology()` 落
        真实 inputs/outputs/channels + 组代表通道。**读不到不回滚加载** (加载本身已过
        错误门), 只留 None 让端口消费方 fail-loud —— 见 `_readback_topology` docstring。
        """
        freq: Optional[float] = None
        # close_confirmed: CLOSE 已**确认卸载** (STATE?==CLOSED) 才 True —— 只有此时旧场景
        # 真没了、identity 才该清。仅"CLOSE 已发"不够 (Codex #223 复审): STATE?=STOPPED 是
        # "仍加载但暂停"(CLOSE 未卸载), 旧场景冷缓存 GO 还能起, identity 须保留让一致性网核对
        # 旧频率。CLOSE 前失败 (STOP 超时) 同理保留。GCM/ASC/B-2 三路已统一走共享
        # _close_and_read_state, close_confirmed 语义一致。
        close_confirmed = False
        try:
            async with self._scpi_lock:
                # ——加载前: 确保干净、非瞬态——
                await self._drain_errors()
                state = await self._query_simulation_state()
                if state == "RUNNING":
                    await self._write("DIAG:SIMU:STOP")   # 手册: pause 语义
                    await self._query("*OPC?")             # STOP 后必 *OPC? 同步
                    # STOP 已暂停播放 (Codex #223 P2): _emulation_running 独立于 loaded ——
                    # STOP 停播放但不卸载文件。即使后续 CLOSE 未确认卸载 (except 保留
                    # identity: 旧 GCM 仍加载), 也不能报"还在跑" → STOP 确认后即置 False。
                    self._emulation_running = False
                elif state in ("OPENING", "STOPPING", "CLOSING"):
                    await self._query("*OPC?")             # 瞬态: 阻塞等稳 (别 while 轮询)
                    self._emulation_running = False        # 瞬态在停/关, 非运行态 (F4)
                # CLOSE + 复查真卸载 (走共享 _close_and_read_state)。STATE? 手册保证实现
                # (§20.4.3.14, 不会 -100), 读到非 CLOSED/None 都是"没确认卸载"(旧场景仍
                # 加载, None=真通信异常, 也不该硬闯 FILE) → fail-loud。
                close_state = await self._close_and_read_state()
                if close_state != "CLOSED":
                    self._last_error = (
                        f"load .smu 前置 CLOSE 后 STATE?={close_state}≠CLOSED — 未真卸载, "
                        f"不硬闯 CALC:FILT:FILE (file={file_path})"
                    )
                    logger.error(f"[F64] {self._last_error}")
                    # Codex #223 复审: STATE?≠CLOSED (如 STOPPED) = 旧场景**仍加载**(只暂停),
                    # CLOSE 未卸载 → **保留 identity** (冷缓存 GO 还能起旧场景, 一致性网该核对旧
                    # 频率, 别报 None 漏掉)。running 只在**确认非运行稳态**才清 —— STATE?=RUNNING
                    # 说明 CLOSE 没停、仍在发射, None 说明读失败, 都不清 (否则 disconnect 清理跳过
                    # stop_emulation, 现场可能仍发射)。
                    if close_state == "RUNNING":
                        self._emulation_running = True
                    elif close_state is not None:
                        self._emulation_running = False
                    return False
                close_confirmed = True  # STATE?==CLOSED: 旧场景确认卸载 → 后续失败可清 identity
                # ——加载 (大文件抬超时, 手册 §2.2.4 默认 2000ms 必 -400)——
                await self._write(
                    f"CALC:FILT:FILE {file_path}", timeout=VISA_TIMEOUT_FILE_LOAD
                )
                await self._query("*OPC?", timeout=VISA_TIMEOUT_FILE_LOAD)
                load_err = await self._first_error()
                if load_err is not None:
                    self._last_error = f"load .smu failed: {load_err} (file={file_path})"
                    logger.error(f"[F64] {self._last_error}")
                    self._apply_unload()  # CLOSE 已发 (旧仿真已停+卸载) → 清加载态
                    return False
                # ——加载后回读真频 (母题③: 频率来自仪器, 不靠文件名。CENT:CH? 1 读
                # 第一组的组中心频, 单值不越界)——
                freq = await self._readback_center_freq(1)
                # ——加载后回读真拓扑 (F64R-2 母题②: 端口数问仪器, 不靠 tx×rx 猜)。
                # 前置条件"仿真已加载"此刻才满足 (FILE + *OPC? + 错误门都过了)。
                # 内部不抛异常、失败只留 None + WARNING —— 加载已成功不因拓扑读不到回滚。
                await self._readback_topology()
        except Exception as e:  # noqa: BLE001
            # 会话坏 / VI_ERROR_TMO (现场实证的超时路径) → fail-loud, 不冒泡。
            # ⚠ 只在 CLOSE **已确认卸载** (close_confirmed) 时清 identity。CLOSE 前异常
            # (STOP 超时) 或 CLOSE 未确认卸载 (STATE? 没读到 CLOSED) → 旧场景仍加载, 保留
            # 旧频率 (清成 None 会让一致性网漏报仍在跑的旧 GCM) —— Codex #223 复审。
            self._last_error = f"load .smu exception: {e} (file={file_path})"
            logger.error(f"[F64] load .smu 异常: {e} (file={file_path})")
            if close_confirmed:
                self._apply_unload()  # 旧已确认卸载 → 清; 否则保留 (旧仍加载)
            return False
        # 锁外更新频率缓存 (回读值已取, 无需再持锁)
        self._readback_center_freq_mhz = freq
        if freq is not None:
            self._center_freq_mhz = freq
        return True

    async def load_local_scenario(self, file_path: str) -> bool:
        """现场 reset F64: 加载 F64 本地 .smu 场景文件 (不经 FTP, 文件已在 F64 D:盘)。

        2026-07-23 P0-3 按 PROPSIM 手册教科书序列**重写** (P2-1 移除的旧版盲发 CLOSE
        真机撞超时, 见 F64 review 母题④): 走共享 _load_smu_with_preflight ——
        STATE?判态 → STOP → CLOSE → 复查 CLOSED → FILE → *OPC? → SYST:ERR? →
        CENT:CH? 回读真频。成功后设 _loaded_emulation_file, 调用方接 start_emulation
        GO 播放。频率真值由 CENT:CH? 回读 (不靠文件名), 故 _center_freq_programmed=
        False (get_frequency_identity 走回读真频优先级)。
        """
        if not self._visa_resource:
            return False
        if not file_path:
            self._last_error = "load_local_scenario: 空文件路径"
            return False
        if not await self._load_smu_with_preflight(file_path):
            # helper 已置 _last_error 且据 close_confirmed 精确清 identity (确认卸载后失败清、
            # 未确认卸载/CLOSE 前失败保留仍加载的旧 GCM) —— 调用方不再无条件清 (Codex #223)。
            return False
        self._loaded_emulation_file = file_path
        self._center_freq_programmed = False  # 频率由 .smu 定, 已回读真值
        self._active_pipeline = F64Pipeline.GCM_NATIVE
        self._emulation_running = False  # CLOSE 已停, 未 GO
        logger.info(f"[F64] 本地场景已加载 (手册序列): {file_path}")
        return True

    async def load_parametric_tdl(self, waveform_dir: str, model_name: str) -> bool:
        """P2-14 B-2: 加载参数化 TDL (.tap/.rtc) 模型, F64 硬件 FPGA 实时合成衰落。

        加载 B-2 payload 里的【实际 .rtc/.smu】 —— **不走 ASC 的 runtime_emulation.smu
        fallback** (Codex P1 #167): 优先编译好的 .smu, 否则 .rtc (运行时容器直接 CALC:FILT:FILE);
        都没有 = payload 不含可加载参数化模型 → fail-loud。F64 按文件内容判参数化实时衰落 vs 烘焙。
        运行时几何骨架更新走 set_runtime_environment (CH:MOD:CONT:ENV)。

        现场验证 (V1.0 §9, 待真机标定): .tap schema 字段顺序 / gaussian 谱关键字可用性 /
        .rtc 直接加载 vs 需 .smu 包装 / 运行时切换抖动 / f_upd_max。
        """
        if not self._visa_resource:
            return False
        close_confirmed = False  # CLOSE 已**确认卸载**(STATE?==CLOSED)才 True — 异常路径据此判 identity (Codex #223 复审)
        try:
            logger.info("[F64/B2] Uploading PARAMETRIC_TDL payload: %s model=%s",
                        waveform_dir, model_name)
            remote_dir = f"{self.waveform_dir}\\{model_name or 'b2_tdl'}"
            transferred = await self._ftp_upload_directory(waveform_dir, remote_dir)
            if not transferred:
                logger.error("[F64/B2] FTP transfer failed - no files uploaded")
                return False

            # 选实际 B-2 加载体: 优先 .smu (编译好), 否则 .rtc (运行时容器); 都没有 → fail-loud
            smu = [f for f in transferred if f.endswith(".smu")]
            rtc = [f for f in transferred if f.endswith(".rtc")]
            if smu:
                load_file = f"{remote_dir}\\{smu[0]}"
            elif rtc:
                load_file = f"{remote_dir}\\{rtc[0]}"
            else:
                logger.error(
                    "[F64/B2] PARAMETRIC_TDL payload 不含 .smu/.rtc 可加载体, 拒绝加载: %s",
                    transferred,
                )
                return False

            # 加载事务 (Codex #203 R3 同型: drain → CLOSE+确认卸载 → FILT:FILE → *OPC? →
            # 错误门整体持锁, broadcaster 轮询不得污染/抢食队列; 锁可重入)。gate 只评估本次
            # CALC:FILT:FILE 产生的错误 (Codex on PR #93/#169): *OPC?=1 ≠ 加载成功 — 缺失/
            # 损坏/不支持的 .rtc/.smu 仍答 1, 唯一可靠失败信号是 SYST:ERR? (-200/-300)。
            # (CLOSE 移进锁内, 与 helper 对称: STATE? 读不被 broadcaster 打断)
            async with self._scpi_lock:
                await self._drain_errors()
                # CLOSE + 复查真卸载 (共享 _close_and_read_state, Codex #223 复审): STATE?≠
                # CLOSED (STOPPED=仍加载暂停) → 旧场景仍加载, 保留 identity + fail-loud 不硬闯
                # FILE (旧盲发 CLOSE 硬闯 FILE 是现场 load 从没成功根因; 治 GCM 也治 ASC/B-2)。
                close_state = await self._close_and_read_state()
                if close_state != "CLOSED":
                    self._last_error = (
                        f"B-2 前置 CLOSE 后 STATE?={close_state}≠CLOSED — 未真卸载, 不硬闯 "
                        f"CALC:FILT:FILE (旧场景仍加载; file={load_file})"
                    )
                    logger.error(f"[F64/B2] {self._last_error}")
                    # running 只在确认非运行稳态才清 (Codex #223: RUNNING=仍发射/None=读失败 不清)
                    if close_state == "RUNNING":
                        self._emulation_running = True
                    elif close_state is not None:
                        self._emulation_running = False
                    return False
                close_confirmed = True
                self._emulation_running = False
                await self._write(f"CALC:FILT:FILE {load_file}", timeout=VISA_TIMEOUT_FILE_LOAD)
                await self._query("*OPC?", timeout=VISA_TIMEOUT_FILE_LOAD)
                load_err = await self._first_error()
                if load_err is None:
                    # ——成功分支整段在锁内 (与 GCM 路对称)——
                    # ⚠ 必须持锁: 拓扑回读是"先清空再逐条填满"的多命令序列 (5+3N 条),
                    # 放锁外的话这段窗口里并发的**端口写** (如 /input-reference 端点) 会
                    # 读到清空后的 None → **加载明明成功却被拒**。
                    # (注: get_metrics 是不持锁直接读字段的, 锁保护不到它 —— 但字段级
                    #  赋值原子, 它最坏读到"跳过查询", 无害。别据此以为读路径被锁保护了。)
                    self._loaded_emulation_file = load_file
                    # P0-3 F1: B-2 参数化 TDL 载频不在 F64 GCM identity 状态 (由 payload/SCD
                    # 同源定, 非 CENT:CH? 回读) → identity 契约同 ASC: 报 None 让一致性网跳过
                    # F64 (或落 B-2 文件名解析)。清 GCM 步残留 programmed/readback, 否则
                    # GCM→B-2 切换后 identity 谎报上一 GCM 步真频。与 ASC 成功分支对称。
                    self._center_freq_programmed = False
                    self._readback_center_freq_mhz = None
                    # pipeline 在回读**之前**置 (与 ASC 路对称): 否则 metrics 可能读到
                    # "旧 pipeline + 新拓扑"的错配快照。
                    self._active_pipeline = F64Pipeline.B2_PARAMETRIC_TDL
                    # F64R-2: B-2 路同样落本仿真拓扑 (三路对称) —— 否则残留上一步的口数
                    # 去配这个模型。手册确认 .rtc/.tap 也须编译成 .smu 下发, 回读通用。
                    await self._readback_topology()
            if load_err is not None:
                # CLOSE 已确认卸载 → 清加载态 (loaded/identity/pipeline);
                # 否则 GCM→B-2(失败) 后 identity 谎报上一 GCM 步真频。
                self._apply_unload()
                self._last_error = f"B-2 PARAMETRIC_TDL load failed: {load_err}"
                logger.error(
                    "[F64/B2] 加载失败 — SYST:ERR? after load: %s (file=%s)",
                    load_err, load_file,
                )
                return False
            logger.info("[F64/B2] PARAMETRIC_TDL 加载完成: %s; 硬件实时衰落, 运行时走 CH:MOD:CONT:ENV",
                        load_file)
            return True
        except Exception as e:
            # P0-3 F1 (Codex #223 P2): CLOSE 已发后 FILE/*OPC? 超时等异常跳到此处, 会绕过
            # 上面成功/失败分支的 identity 清理 → 旧 GCM 真频泄漏 (超时正是现场 load 场景)。
            # CLOSE 已停旧仿真 → identity 字段全 stale, 清之; CLOSE 前异常 (如 FTP 失败) 旧
            # 仿真仍开, 不动 identity。
            if close_confirmed:
                self._apply_unload()  # CLOSE 已确认卸载 → 清加载态; 未确认/CLOSE 前异常不清 (旧仍加载)
            logger.error("[F64/B2] load_parametric_tdl failed: %s", e)
            self._last_error = str(e)
            return False

    # ===================================================================
    # 1. 连接生命周期 (InstrumentDriver 第一层)
    # ===================================================================

    async def connect(self) -> bool:
        """
        建立与 F64 ATE Server 的 PyVISA TCP/IP Socket 连接。

        连接流程:
          1. 创建 PyVISA ResourceManager
          2. 打开 TCP Socket 连接 (端口 3334, 硬件固定)
          3. 发送 *IDN? 验证身份
          4. 查询 SYST:INFO? 获取硬件配置
        """
        self._status = InstrumentStatus.CONNECTING
        # 连接起始复位网 (F3): connect 是新会话干净起点 → 全清 6 字段 (含 running/pipeline/
        # bypass), 防 disconnect→reconnect 或 socket 掉直连的 reconnect 后旧实例 stale 残留。
        self._apply_session_reset()
        try:
            import pyvisa
            self._rm = pyvisa.ResourceManager('@py')
            resource_string = f"TCPIP0::{self.ip_address}::{self.port}::SOCKET"

            self._visa_resource = await asyncio.to_thread(
                self._rm.open_resource, resource_string,
                read_termination='\n',
                write_termination='\n',
                timeout=VISA_TIMEOUT_DEFAULT
            )

            # 验证连接: IEEE 488.2 标准身份查询
            idn = await self._query("*IDN?")
            logger.info(f"[F64] Connected: {idn}")

            # 查询硬件信息: 通道数、频段、License
            sys_info_raw = await self._query("SYST:INFO?")
            logger.info(f"[F64] System Info: {sys_info_raw}")

            # P3-4: structured parse — beyond just channel_count, surface
            # firmware_version + band_label + product_family for the
            # readiness report. Defensive: unparseable fields fall back
            # to None / 64 default. See parse_f64_sys_info docstring for
            # the recognized shapes.
            self.sys_info = parse_f64_sys_info(sys_info_raw)
            if self.sys_info.channel_count is not None:
                self._channel_count = self.sys_info.channel_count
            else:
                self._channel_count = 64
            self.firmware_version = self.sys_info.firmware_version
            self.band_label = self.sys_info.band_label
            self.product_family = self.sys_info.product_family
            logger.info(
                f"[F64] Parsed: family={self.product_family!r}, "
                f"firmware={self.firmware_version!r}, "
                f"channels={self._channel_count}, "
                f"band={self.band_label!r}"
            )

            # 启动时探测安装选件 (license). 若 config 显式声明能力字段则跳过
            # 应用阶段, 仍执行探测仅为日志可见性.
            opts = await self._probe_installed_options()
            await self._apply_discovered_capabilities(opts)

            # User alignment auto-reload (User Reference §17.5):
            #   "Auto alignment results become obsolete when the emulator
            #    shuts down" — alignment 文件保留在盘上, 但每次开机后必须调
            #    SYST:CALIB:USER:SET 1,<name> 重新激活. 当前 active 状态先
            #    存到 _active_alignment 供 precheck phase 上报.
            self._active_alignment = await self.get_user_alignment_status()
            self._update_user_alignment_capability()
            if self._preferred_alignment_name:
                current = (
                    self._active_alignment.get("alignment_name")
                    if self._active_alignment else None
                )
                if current != self._preferred_alignment_name:
                    logger.info(
                        f"[F64] Re-loading user alignment "
                        f"\"{self._preferred_alignment_name}\" "
                        f"(was: {current!r})"
                    )
                    if await self.enable_user_alignment(self._preferred_alignment_name):
                        self._active_alignment = await self.get_user_alignment_status()
                        self._update_user_alignment_capability()
                    else:
                        logger.warning(
                            f"[F64] Could not activate user alignment "
                            f"\"{self._preferred_alignment_name}\" — "
                            f"emulator may be missing the file or the license."
                        )

            # 清空错误队列
            await self._clear_error_queue()

            self._status = InstrumentStatus.READY
            self._last_error = None
            return True

        except Exception as e:
            logger.error(f"[F64] Connection failed ({self.ip_address}:{self.port}): {e}")
            self._status = InstrumentStatus.ERROR
            self._last_error = str(e)
            return False

    async def disconnect(self) -> bool:
        """
        安全断开连接。

        断开流程:
          1. 若仿真正在运行, 先停止
          2. 关闭仿真文件
          3. 释放 VISA 资源
        """
        stop_confirmed = True
        try:
            if self._emulation_running:
                # Codex #206 R2: GOS 被拒 (SYST:ERR-only 失败) 时不能报"干净
                # 断开" — 断开照样继续 (重载场景必须能断), 但如实降返回值,
                # 让 HAL 重载/关闭日志暴露 "F64 可能仍在发射"。
                stop_confirmed = await self.stop_emulation()
                if not stop_confirmed:
                    logger.warning(
                        "[F64] disconnect: stop_emulation 被拒 — 连接将断开, "
                        "但 F64 可能仍在运行/发射, 需现场确认"
                    )
            if self._loaded_emulation_file:
                await self._write("DIAG:SIMU:CLOSE")
        except Exception as e:
            stop_confirmed = False
            logger.warning(f"[F64] Cleanup during disconnect: {e}")
        finally:
            # disconnect 终态**无条件**全清 6 字段放 finally (F2: 含 _bypass_mode —— 它是
            # 唯一 disconnect+connect 都曾漏清的字段, 跨会话残留)。即使 DIAG:SIMU:CLOSE 抛
            # 异常走 except 也不残留 stale (堵 failed-CLOSE→不重连→跑一致性网 窗口)。
            self._apply_session_reset()

        if self._visa_resource:
            try:
                await asyncio.to_thread(self._visa_resource.close)
            except Exception as e:
                logger.warning(f"[F64] VISA resource close error: {e}")
        if self._rm:
            try:
                self._rm.close()
            except Exception:
                pass

        self._visa_resource = None
        self._rm = None
        self._status = InstrumentStatus.DISCONNECTED
        # running/pipeline/identity/bypass 已在 finally 的 _apply_session_reset 全清
        return stop_confirmed

    def readiness_metadata(self) -> Dict[str, Any]:
        """P3-5: expose parsed SYST:INFO? fields to the HAL readiness
        report. Pre-P3-5 these were stored on the driver instance (P3-4)
        but the readiness payload had no field to carry them out, so the
        operator could only see them in stdout logs at connect time.

        Returns ``{}`` (not partial keys) when ``sys_info`` is None — we
        either parsed a full response or nothing useful, partial dicts
        would make GUI rendering branching harder for no signal.
        """
        if self.sys_info is None:
            return {}
        return {
            "firmware_version": self.firmware_version,
            "band_label": self.band_label,
            "product_family": self.product_family,
        }

    def _parse_loaded_center_freq_mhz(self) -> Optional[float]:
        """已加载 .smu 的**文件名** loose 频率 (P1-18 ⚠: 只可作提示不可作真值 ——
        文件名是场景族标称, 系统性说谎, 实录 UMa_3600M 工程实为 3549.99; 工程内
        真值解析见 ``smu_project``, 但 ATE 无 MMEM/FTP 拿不到工程文件, 运行时
        只能在未显式下发时以此作 get_frequency_identity 的降级参考)。

        复用 nr_arfcn.parse_smu_center_freq_mhz (P2-10 Step 1 抽共享) —— 跟 channel model
        inventory 盘点 .smu 频率元数据走同一套命名约定解析, 避免漂移成两套。
        """
        from app.hal.nr_arfcn import parse_smu_center_freq_mhz
        return parse_smu_center_freq_mhz(self._loaded_emulation_file)

    def get_frequency_identity(self):
        """P2-11: F64 当前加载信道的频率规范标识 (中心 ARFCN + 带宽), 供多方一致性校验。

        频率来源优先级 (Codex on PR #109 P2 — 报"实际下发", 不是"文件名 token"):
        1. **显式下发过的中心频** (`_center_freq_programmed`): configure / set_channel_model
           收到 `center_frequency_mhz` 时驱动 `CALC:FILT:CENT:CH`, 此即 F64 实际工作频率。
           优先 —— 能抓 "复用 3600M.smu 但 configure 重调到 3500" 这种文件名已 stale 的坑。
        2. **P0-3 母题③**: 否则用加载时 `CALC:FILT:CENT:CH?` 回读的真频
           (`_readback_center_freq_mhz`) —— 从仪器读, 治 "3600M.smu 实为 3550" 文件名说谎。
        3. **最后**才解析 `_loaded_emulation_file` 文件名 (回读失败 / ASC 路径无仿真时降级)。
        返回 None = 既没显式下发、文件名也无法解析 (e.g. ASC 路径 — 频率由 channel-engine
        按 TestCase 生成, 不在 F64 driver 状态; 校验跳过 F64, 由 ASC 同源保证)。
        带宽信道仿真器不强标识, 用 N78 标准 100M。
        """
        if self._center_freq_programmed:
            freq_mhz = self._center_freq_mhz
        elif self._readback_center_freq_mhz is not None:
            # P0-3 母题③: 没显式下发时优先 CENT:CH? 加载后回读的真频 (> 文件名 loose
            # 解析) —— 治 "3600M.smu 实为 3550" 系统性说谎, 消 18 资产手工实测负担。
            freq_mhz = self._readback_center_freq_mhz
        else:
            freq_mhz = self._parse_loaded_center_freq_mhz()
        if freq_mhz is None:
            return None
        from app.hal.nr_arfcn import FrequencyIdentity
        return FrequencyIdentity.from_center_freq_mhz(freq_mhz, 100.0)

    async def configure(self, config: Dict[str, Any]) -> bool:
        """
        通用配置入口, 支持以下 config 键:
          - center_frequency_mhz: 中心频率 (MHz)
          - channel_model: 信道模型名称 (触发 set_channel_model)
          - pipeline: "gcm" 或 "asc_runtime"
        """
        has_model = "channel_model" in config
        if config.get("center_frequency_mhz") is not None:  # None 视同缺省 (P1-18)
            self._center_freq_mhz = config["center_frequency_mhz"]
            # agent 门审 F2: 有 channel_model 时 programmed 交给 set_channel_model
            # 的 CENT 门后逻辑 (被拒不置) — 抢先置 True 会在 CENT 被拒 (set_channel
            # _model return False) 后残留"标称已下发但实际没发", get_frequency_
            # identity 报请求频率而非真实值 (test_real_dispatch 母题)。无 model
            # 分支只更内存缓存不发 SCPI, 保持旧语义 (缓存即真值, 无下发可拒)。
            if not has_model:
                self._center_freq_programmed = True
        # pipeline 只在**无 channel_model**(纯 pipeline 配置)时应用: 有 model 时 pipeline 由
        # set_channel_model 拥有 (成功置 GCM / 失败保留旧场景), 别在此乐观置 —— 否则 load 未确认
        # 卸载失败 (旧场景仍加载) 后残留 config 的新 pipeline (Codex #223 复审, 同 load_channel)。
        if "pipeline" in config and not has_model:
            self._active_pipeline = F64Pipeline(config["pipeline"])
        if has_model:
            # P1-18: Step 4 改为"parameters 显式给才写 CENT"后, 顶层频率不再
            # 靠"缺省写内存值"间接生效 — 显式并进 parameters 直通下发。
            params = dict(config.get("parameters", {}))
            if (
                config.get("center_frequency_mhz") is not None
                and params.get("center_frequency_mhz") is None
            ):
                params["center_frequency_mhz"] = config["center_frequency_mhz"]
            return await self.set_channel_model(
                config["channel_model"],
                config.get("scenario", "UMi"),
                params,
            )
        return True

    # ===================================================================
    # 1.5 信道模型清单 (操作员维护, 非动态发现)
    # ===================================================================

    async def list_channel_models(self) -> List[Dict[str, Any]]:
        """Operator-curated list of selectable .smu / .rtc channel models.

        Source of truth is
        ``InstrumentConnection.connection_params['available_channel_models']``;
        normalisation lives in ``channel_emulator.normalize_channel_model_entries``
        so the API endpoint's offline DB-fallback path returns the same
        shape as a live driver. Returns ``[]`` when nothing is configured.
        """
        from app.hal.channel_emulator import normalize_channel_model_entries
        return normalize_channel_model_entries(self._available_channel_models)

    # ===================================================================
    # 2. Pipeline A — GCM 原生管线 SCPI 翻译
    # ===================================================================

    async def set_channel_model(
        self,
        model_type: str,
        scenario: str,
        parameters: Dict[str, Any]
    ) -> bool:
        """
        加载信道模型到 F64。

        Pipeline A (GCM): 加载 .smu 仿真文件, F64 内部编译并播放。
        此方法实现 GCM 原生管线的完整 SCPI 流程:

          1. 关闭当前仿真文件 (安全防护)
          2. 加载新的 .smu 仿真文件
          3. 设置中心频率
          4. 配置端口连接拓扑

        ATE Practice Note §2.2.2:
          "DIAG:SIMU:CLOSE" 可以安全地在任何状态下调用, 不会产生错误。

        Args:
            model_type: GCM 模型类型 (e.g., "CDL-A", "CDL-C", "TDL-A")
            scenario: 场景类型 (e.g., "UMi", "UMa", "Indoor")
            parameters: 可选参数字典, 支持:
                - emulation_file: .smu 文件完整路径 (覆盖默认命名)
                - center_frequency_mhz: 中心频率 (MHz)
                - bandwidth_mhz: 仿真带宽 (MHz)
        """
        if not self._visa_resource:
            return False
        try:
            # pipeline 成功才置 (F1 对称, 见 helper 成功后): 别在顶部乐观置
            logger.info(f"[F64/GCM] Loading model: {model_type} scenario={scenario}")

            # Step 1-2: 构建仿真文件路径 (优先级见 F64_DEFAULT_EMULATION_FILE 注释)
            # 1) per-call parameters["emulation_file"]; 2) 驱动默认 (config / 常量);
            # 3) 兜底 auto-name (仅当默认被显式清空)
            emulation_file = parameters.get("emulation_file") or self._default_emulation_file
            if not emulation_file:
                # 默认被操作员显式清空 → 回退 auto-name (legacy)
                emulation_file = (
                    f"{self.emulation_dir}\\{model_type}_{scenario}"
                    f"_{self._tx_antennas}x{self._rx_antennas}.smu"
                )

            # Step 3: 手册化加载事务 (P0-3: 替旧"盲发 CLOSE + 无复查加载" — 现场
            # CALC:FILT:FILE 超时根因)。_load_smu_with_preflight 内含 STATE?判态 →
            # STOP → CLOSE → ★复查 CLOSED → FILE → *OPC? → SYST:ERR? 门 → CENT:CH?
            # 回读真频。失败 fail-loud (helper 已置 _last_error)。
            # (F64R-2: helper 内还接了拓扑回读 —— 落真实输入/输出**端口号** + 组代表
            #  通道, 供下面 Step 4 的 CENT per-group 下发和后续端口配置使用)
            if not await self._load_smu_with_preflight(emulation_file):
                # helper 据 close_confirmed 精确清 identity (确认卸载后失败清、未确认卸载/
                # CLOSE 前失败保留仍加载的旧 GCM) —— 调用方不再无条件清 (Codex #223)
                return False
            self._loaded_emulation_file = emulation_file
            self._active_pipeline = F64Pipeline.GCM_NATIVE  # 成功才置 (F1 对称, 参照 load_local)
            self._emulation_running = False  # CLOSE 已停, 未 GO

            # 加载默认文件 → 同步 MIMO 拓扑缓存 (Codex on PR #97)。
            # ⚠ F64R-2 后这里同步的 _tx/_rx 只是**声明式 MIMO 元数据** (给上报 /
            # set_mimo_config 一致性用), **不再驱动任何端口寻址** —— 端口一律走
            # _readback_topology() 从仪器回读的 inputs/outputs/channels。保留同步是为了
            # 让 set_mimo_config 的一致性拒绝和 metrics 上报不停在构造默认 2x2。
            # 非默认文件由 operator 经 set_mimo_config 设拓扑 (现有惯例)。
            if (
                emulation_file == self._default_emulation_file
                and self._default_emulation_file_topology is not None
            ):
                new_tx, new_rx = self._default_emulation_file_topology
                old = (self._tx_antennas, self._rx_antennas)
                if old != (new_tx, new_rx):
                    self._tx_antennas, self._rx_antennas = new_tx, new_rx
                    logger.info(
                        "[F64/GCM] 默认文件加载 → 同步 MIMO 拓扑 %dx%d → %dx%d",
                        old[0], old[1], new_tx, new_rx,
                    )

            # Step 4: 设置中心频率 — 仅 parameters 显式给了才下发 (P1-18 正修)。
            # 2026-07-03 现场 ⭐⭐⭐ bug: 原先缺省也无条件把 self._center_freq_mhz
            # (默认 3500 或上次遗留) 写满全部通道, 冲掉 .smu 工程内频率 —— 3550
            # 工程被写成 3500, 输入测量 / AUTOSET / 吞吐全链错位。缺省 = 不碰
            # CENT, 尊重工程 CenterFrequency; 显式下发才更新真值 + programmed
            # (P2-11 语义不变: programmed=False 时 get_frequency_identity 退回
            # CENT:CH? 回读真频 > .smu 文件名 loose 解析)。None 视同缺省 (显式 null
            # 不能变成字面 "CALC:FILT:CENT:CH 1,None" 下发)。
            if parameters.get("center_frequency_mhz") is not None:
                freq_mhz = parameters["center_frequency_mhz"]
                # R10 平行族: CENT 写序列过 _first_error 门 — 被拒 (超范围等) 不许假
                # 成功; 缓存/programmed 门过才更新 (R8 被拒状态不动)。
                # F64R-2: CENT 是 **per-group** 生效 (手册 §20.4.6.1: "Frequency is set
                # for given channel and for all the other channels belonging to the same
                # group"); 同组判定 = **输入相同或输出相同**(§20.4.6.4/6, 满足其一即可)。
                # 组数**不可推算, 必须回读**(GROUP:GET?): 全交叉拓扑下通道经输入/输出
                # 两个维度连通, 可能整个仿真只有 1 组。正确下发 = 按**实际组数**逐组发
                # 一次, 每次用该组代表通道号。旧的循环 1..64(_channel_count) 两头都错:
                # 同组通道被重复写(浪费+无谓抖动), 且 <64 通道的模型会撞不存在的通道 -200。
                # 整段持锁 (与 set_path_loss/doppler/baseband 四个消费方一致): 加载事务
                # 已释放锁, 若"读组代表通道"和"下发"之间另一协程换了仿真, CENT 就会打在
                # **上一个仿真**的组号上 (号在新仿真里存在 = 静默配错组)。
                async with self._scpi_lock:
                    repr_channels = self._group_repr_channels
                    if not repr_channels:
                        # 拓扑/组信息未知 → fail-loud, 不按猜测的通道循环下发。
                        # ⚠ 与下面被拒分支同样要**复位** programmed (Codex #211 母题): 新
                        # 文件此刻已 load 成功, 上一个 model 若置过 True, 那个频率已彻底
                        # 无效 —— 残留 True 会让 get_frequency_identity 谎报没真下发的旧频。
                        self._center_freq_programmed = False
                        self._last_error = (
                            "set_channel_model 中心频下发拒绝: 信道组信息未知 (GROUP:GET? / "
                            "GROUP:CHANNELS:GET? 回读失败) — 不按猜测的通道号下发 CENT。"
                            f"{_TOPOLOGY_ESCAPE_HINT}"
                        )
                        logger.error(f"[F64] {self._last_error}")
                        return False
                    _cent_ok = await self._gated_write_transaction(
                        "set_channel_model center-freq",
                        [
                            f"CALC:FILT:CENT:CH {ch},{freq_mhz}"
                            for ch in repr_channels
                        ],
                    )
                if not _cent_ok:
                    # Codex #211 follow-up: CENT 被拒时**复位** programmed (不只
                    # 是"不置") — 上一个 model 若已置 True, 新文件此刻已 load
                    # 成功 (第 908 行), 旧 programmed 频率彻底无效; 残留 True 会
                    # 让 get_frequency_identity 谎报没真下发的旧频率。复位 False
                    # → 退回**新**加载文件的文件名 loose 解析 (test_real_dispatch
                    # 母题; F2 只修了 configure 入口, 漏了 set_channel_model 自身)。
                    self._center_freq_programmed = False
                    return False
                self._center_freq_mhz = freq_mhz
                self._center_freq_programmed = True
            else:
                # 缺省加载 → 频率回归新工程内声明, 之前的显式下发值不再代表
                # 当前实际 — 复位 programmed, identity 退回文件名 loose 参考
                # (上报=实际的闭环, 否则换工程后仍报旧显式值)。
                self._center_freq_programmed = False

            # Step 5: 验证连接器映射
            # 查询第一个通道的物理连接, 确保路由正确
            connector_info = await self._query("ROUT:PATH:CONN? 1")
            logger.info(f"[F64/GCM] Channel 1 connector: {connector_info}")

            # 缓存当前模型信息
            self._current_model = model_type
            self._current_scenario = scenario

            logger.info(f"[F64/GCM] Model loaded: {emulation_file}")
            # R10 平行族: 尾部 _check_errors (只 log 无判定) 移除 — CENT 段
            # 已有门, ROUT 是查询 (失败走异常), 残留条目由下一事务 drain 清
            return True

        except Exception as e:
            logger.error(f"[F64/GCM] set_channel_model failed: {e}")
            self._last_error = str(e)
            return False

    # ===================================================================
    # 3. Pipeline B — ASC Runtime Emulation SCPI 翻译
    # ===================================================================

    async def upload_asc_files(
        self,
        asc_files_dir: str,
        cdl_model_name: str = ""
    ) -> bool:
        """
        上传 ASC 波形文件到 F64 并配置 Runtime Emulation 播放。

        Pipeline B 完整流程:
          1. 通过 FTP 将波形文件传输到 F64 本地磁盘
          2. 关闭当前仿真
          3. 加载包含 Runtime 模型的基础仿真文件 (.smu)
          4. 仿真文件内部引用 .rtc 运行时信道模型

        Runtime Emulation User Guide §4:
          RTC 文件必须在 Scenario Wizard 中预先关联到链路。
          运行时通过 CH:MOD:CONT:ENV 动态切换环境。

        Args:
            asc_files_dir: 包含 .asc/.rtc/.zip 波形文件的本地目录
            cdl_model_name: CDL 模型标签 (e.g. "UMa CDL-C NLOS")
        """
        if not self._visa_resource:
            return False
        close_confirmed = False  # CLOSE 已**确认卸载**(STATE?==CLOSED)才 True — 异常路径据此判 identity (Codex #223 复审)
        try:
            # pipeline 仅成功才置 (与 B-2 对称, F1): 否则 FTP 失败 (CLOSE 前) 残留 stale
            # ASC_RUNTIME 而旧仿真仍加载。见成功分支。
            logger.info(f"[F64/ASC] Uploading ASC payload: {asc_files_dir} model={cdl_model_name}")

            # Step 1: FTP 文件传输
            # F64 内置 Windows FTP 服务 (出厂默认: user=PROPSIM, pass=propsim)
            remote_dir = f"{self.waveform_dir}\\{cdl_model_name or 'custom'}"
            transferred_files = await self._ftp_upload_directory(asc_files_dir, remote_dir)
            if not transferred_files:
                logger.error("[F64/ASC] FTP transfer failed - no files uploaded")
                return False
            logger.info(f"[F64/ASC] Transferred {len(transferred_files)} files to {remote_dir}")

            # Step 3: 加载 Runtime 基础仿真文件
            # 该 .smu 文件必须预先通过 Scenario Wizard 创建,
            # 内部 Link Properties 引用 .rtc 运行时信道模型
            runtime_smu = f"{remote_dir}\\runtime_emulation.smu"

            # 如果目录中包含 .smu 文件则使用它
            smu_files = [f for f in transferred_files if f.endswith('.smu')]
            if smu_files:
                runtime_smu = f"{remote_dir}\\{smu_files[0]}"

            # Step 2+3 加载事务 (R10 平行族: 对齐 set_channel_model load 门,
            # P0-8 母题 — *OPC? 对缺失/损坏文件照答 1, 唯一失败信号是
            # SYST:ERR?; 原实现全程无门, Pipeline B 加载假成功)
            async with self._scpi_lock:
                await self._drain_errors()
                # CLOSE + 复查真卸载 (共享 _close_and_read_state, Codex #223 复审): STATE?≠
                # CLOSED (STOPPED=仍加载暂停) → 旧场景仍加载, 保留 identity + fail-loud 不硬闯
                # FILE (旧盲发 CLOSE 硬闯 FILE 是现场 load 从没成功根因; 治 GCM 也治 ASC/B-2)。
                close_state = await self._close_and_read_state()
                if close_state != "CLOSED":
                    self._last_error = (
                        f"ASC 前置 CLOSE 后 STATE?={close_state}≠CLOSED — 未真卸载, 不硬闯 "
                        f"CALC:FILT:FILE (旧场景仍加载; file={runtime_smu})"
                    )
                    logger.error(f"[F64/ASC] {self._last_error}")
                    # running 只在确认非运行稳态才清 (Codex #223: RUNNING=仍发射/None=读失败 不清)
                    if close_state == "RUNNING":
                        self._emulation_running = True
                    elif close_state is not None:
                        self._emulation_running = False
                    return False
                close_confirmed = True
                self._emulation_running = False
                await self._write(
                    f'CALC:FILT:FILE {runtime_smu}',
                    timeout=VISA_TIMEOUT_FILE_LOAD
                )
                await self._query("*OPC?", timeout=VISA_TIMEOUT_FILE_LOAD)
                load_err = await self._first_error()
                if load_err is None:
                    # ——成功分支整段在锁内 (与 GCM 路对称)——
                    # ⚠ 必须持锁: 拓扑回读是"先清空再逐条填满"的多命令序列, 放锁外的话
                    # 这段窗口里并发的**端口写**会读到清空后的 None → 加载成功却被拒。
                    # (get_metrics 不持锁, 锁保护不到它; 详见 B-2 路同位置注释。)
                    self._loaded_emulation_file = runtime_smu
                    self._active_pipeline = F64Pipeline.ASC_RUNTIME  # 成功才置 (F1)
                    # P0-3 F1: ASC 路频率由 channel-engine 按 TestCase 生成, 不在 F64 driver
                    # 状态 → identity 契约应报 None 让一致性网跳过 F64 (由 ASC 同源保证)。清
                    # 上一 GCM 步残留的 programmed/readback, 否则切 ASC 后 identity 谎报旧真频。
                    self._center_freq_programmed = False
                    self._readback_center_freq_mhz = None
                    # F64R-2: ASC 路同样落**本仿真**的拓扑 —— 不接的话会留着上一个仿真(如
                    # GCM 步的 32 探头)的口数去配这个 runtime_emulation.smu (可能只有 2 口),
                    # 按 32 口狂发 = stale 拓扑比没有更危险。手册确认 .asc/.rtc 都要编译成
                    # .smu 才能下发, MODEL:INFO?/GROUP:* 读的是这层 .smu 壳子, 回读通用。
                    await self._readback_topology()
            if load_err is not None:
                # CLOSE 已确认卸载 → 清加载态 (loaded/identity/pipeline)。保留旧 loaded =
                # 谎报"还开着", 后续 start_emulation guard 假过 GO 才炸。
                self._apply_unload()
                self._last_error = f"ASC runtime load failed: {load_err}"
                logger.error(
                    "[F64/ASC] 加载失败 — SYST:ERR? after load: %s (file=%s)",
                    load_err, runtime_smu,
                )
                return False

            logger.info(f"[F64/ASC] Runtime emulation loaded: {runtime_smu}")
            return True

        except Exception as e:
            # Codex #223: CLOSE 已发后 FILE/*OPC? 超时等异常跳到此处会绕过成功/失败分支的
            # 清理 → 旧 GCM 真频泄漏 (超时正是现场 load 场景)。CLOSE 已停旧仿真 → 清加载态;
            # CLOSE 前异常 (如 FTP 失败) 旧仿真仍开, 不动 identity。
            if close_confirmed:
                self._apply_unload()  # CLOSE 已确认卸载 → 清加载态; 未确认/CLOSE 前异常不清 (旧仍加载)
            logger.error(f"[F64/ASC] upload_asc_files failed: {e}")
            self._last_error = str(e)
            return False

    async def set_runtime_environment(
        self,
        channel_envs: Dict[int, Dict[str, Any]]
    ) -> bool:
        """
        Runtime Emulation 环境切换 (Pipeline B 专用)。

        在仿真运行时, 动态切换各通道的信道环境、增益、延迟和多普勒。

        Runtime Emulation User Guide §5.4.1:
          CH:MOD:CONT:ENV <ch>,<env>,<gain>,<delay_ns>,<doppler_hz>

        Args:
            channel_envs: 字典, key=通道号, value=环境参数:
                - environment: 环境名称或编号
                - gain_db: 通道增益 (负值, dB)
                - delay_ns: 延迟 (ns)
                - doppler_hz: 多普勒频移 (Hz)

        Example:
            await driver.set_runtime_environment({
                1: {"environment": "CDL_A_cluster1", "gain_db": -38.7, "delay_ns": 1510006, "doppler_hz": 0},
                2: {"environment": "CDL_A_cluster2", "gain_db": -37.3, "delay_ns": 1740025, "doppler_hz": 0},
            })
        """
        # ASC Runtime 与 B-2 PARAMETRIC_TDL 都用 CH:MOD:CONT:ENV 做运行时几何骨架切换
        # (Codex P1 #167: B-2 加载后 pipeline=B2_PARAMETRIC_TDL, 不放行会拒掉 B-2 的核心机制)。
        if not self._visa_resource or self._active_pipeline not in (
            F64Pipeline.ASC_RUNTIME, F64Pipeline.B2_PARAMETRIC_TDL,
        ):
            logger.warning("[F64] set_runtime_environment requires active ASC/B2 runtime pipeline")
            return False

        try:
            # 构建批量环境切换命令 (一条 SCPI 可切换多通道)
            # 格式: CH:MOD:CONT:ENV ch1,env1,gain1,delay1,doppler1,ch2,env2,...
            cmd_parts = []
            for ch_num, env_params in channel_envs.items():
                env_name = env_params.get("environment", 1)
                gain = env_params.get("gain_db", "")
                delay = env_params.get("delay_ns", "")
                doppler = env_params.get("doppler_hz", "")
                cmd_parts.append(f"{ch_num},{env_name},{gain},{delay},{doppler}")

            cmd = "CH:MOD:CONT:ENV " + ",".join(cmd_parts)
            await self._write(cmd)

            logger.info(f"[F64/ASC] Runtime environment updated for {len(channel_envs)} channels")
            return True
        except Exception as e:
            logger.error(f"[F64/ASC] set_runtime_environment failed: {e}")
            self._last_error = str(e)
            return False

    async def query_runtime_environment(self, channels: List[int]) -> Dict[int, Dict[str, Any]]:
        """
        查询 Runtime 通道当前环境状态。

        Runtime Emulation User Guide §5.4.2:
          CH:MOD:CONT:ENV? <ch1>,<ch2>,...
          响应: ch1,env,gain,delay,doppler,ch2,env,gain,delay,doppler

        Returns:
            字典, key=通道号, value={environment, gain_db, delay_ns, doppler_hz}
        """
        if not self._visa_resource:
            return {}

        try:
            ch_str = ",".join(str(ch) for ch in channels)
            response = await self._query(f"CH:MOD:CONT:ENV? {ch_str}")
        except Exception as e:
            # SCPI 层失败 (timeout / 仪表错误) — 整体返回空, 调用方自行重试
            logger.error(f"[F64] query_runtime_environment SCPI failed: {e}")
            return {}

        result: Dict[int, Dict[str, Any]] = {}
        parts = response.strip().split(",")
        # 每 5 个 token 为一组: ch, env, gain, delay, doppler. 单组解析失败
        # 跳过该组 (e.g. 仪表临时返回畸形 token), 其他组照常返回 — 比"全
        # 部丢弃"更有用.
        skipped = 0
        for i in range(0, len(parts), 5):
            if i + 5 > len(parts):
                # 末尾不足一组 — 截断, 不算错误
                break
            try:
                ch_num = int(parts[i].strip())
                result[ch_num] = {
                    "environment": parts[i + 1].strip(),
                    "gain_db": float(parts[i + 2]) if parts[i + 2].strip() else None,
                    "delay_ns": int(parts[i + 3]) if parts[i + 3].strip() else None,
                    "doppler_hz": int(parts[i + 4]) if parts[i + 4].strip() else None,
                }
            except (ValueError, IndexError) as e:
                skipped += 1
                logger.warning(
                    f"[F64] query_runtime_environment skipped malformed group "
                    f"at index {i}: {parts[i:i+5]!r} ({e})"
                )

        if skipped:
            logger.info(
                f"[F64] query_runtime_environment: parsed {len(result)} channels, "
                f"skipped {skipped} malformed groups"
            )
        return result

    # ===================================================================
    # 4. 通用仿真控制 (两种管线共享)
    # ===================================================================

    async def set_mimo_config(
        self,
        tx_antennas: int,
        rx_antennas: int,
        correlation_matrix: Optional[list[list[float]]] = None
    ) -> bool:
        """
        配置 MIMO 端口拓扑 (软 setter, F64 真正的拓扑在 .smu/.rtc 文件里).

        F64 的 MIMO 端口拓扑通过 Scenario Wizard 烘到仿真文件中, SCPI 不能
        动态改路径数. 本方法做两件事:
          1. 校验请求的 tx×rx 是否超出本机通道数 (connect 时探测的硬件容量)
          2. 缓存 (tx, rx) 作**声明式 MIMO 元数据**

        ⚠ F64R-2 起缓存的 (tx, rx) **不再用于任何端口寻址**。端口/通道数一律走
        `_readback_topology()` 从仪器回读的 inputs/outputs/channels (`MODEL:INFO?`) ——
        `tx×rx` 是**逻辑通道**口径, 在 MPAC OTA 里不等于物理输出口 (探头) 数, 拿它配
        端口正是 review 母题② 的错法。本缓存现在只服务于: 上报 (get_metrics /
        get_channel_state) 与本方法自身的一致性拒绝。

        若已有仿真文件加载, 拓扑已固定, 此时调用本方法 ≠ 缓存值就 **拒绝并
        返回 False** (避免上报的声明拓扑跟已加载文件打架). 真要改拓扑必须
        reload 不同的 .smu/.rtc.

        connector 重映射 (INP:CON:SET / OUTP:CON:SET) 是另一回事 (物理路由,
        不是逻辑路径数), 不在本方法范围.

        Returns:
            True  校验通过 (或与已加载文件一致, 无需改动)
            False 超出本机通道数 / 已加载文件且请求拓扑不一致
        """
        required_paths = tx_antennas * rx_antennas
        if required_paths > self._channel_count:
            msg = (
                f"requested MIMO {tx_antennas}x{rx_antennas} = {required_paths} "
                f"paths exceeds device capacity {self._channel_count}"
            )
            logger.error(f"[F64] set_mimo_config refused: {msg}")
            self._last_error = msg
            return False

        if self._loaded_emulation_file is not None:
            if (tx_antennas, rx_antennas) != (self._tx_antennas, self._rx_antennas):
                logger.warning(
                    f"[F64] set_mimo_config refused: file '{self._loaded_emulation_file}' "
                    f"is loaded with {self._tx_antennas}x{self._rx_antennas}; "
                    f"requested {tx_antennas}x{rx_antennas} would silently mismatch — "
                    f"reload a different file to change topology"
                )
                self._last_error = "topology fixed by loaded file"
                return False
            # 与已加载文件一致, no-op
            return True

        self._tx_antennas = tx_antennas
        self._rx_antennas = rx_antennas
        logger.info(f"[F64] MIMO config cached: {tx_antennas}x{rx_antennas}")
        return True

    async def set_path_loss(
        self,
        path_loss_db: float,
        distance_m: Optional[float] = None
    ) -> bool:
        """
        设置通道输出损耗 —— **给所有物理输出口写同一个值**。

        ⚠ 这不是 per-probe 校准值下发。真实暗室每个探头路损不同, 校准也确实按
        probe 逐个出值 (`path_loss_calibration_service`), 但那条通路目前**没有接到
        F64** (逐口版 `set_output_path_loss` 生产零调用方) —— 见 backlog F64R-5
        (需先定"补偿在基带 .asc 还是射频 OUTP:LOSS 做", 否则会补两遍)。

        使用 OUTP:LOSS:SET 为每个输出口设置路径损耗补偿。
        User Reference §20.4.5.19:
          OUTP:LOSS:SET <output>,<loss_db>
          取值范围: OUTP:LOSS:LIM? 查询 (典型: -30 ~ 80 dB)

        若指定 distance_m, 则使用自由空间路损公式计算:
          PL = 20*log10(d) + 20*log10(f) - 147.55
        """
        if not self._visa_resource:
            return False

        try:
            # 如果提供距离, 计算自由空间路损
            if distance_m is not None:
                import math
                freq_hz = self._center_freq_mhz * 1e6
                path_loss_db = (
                    20 * math.log10(distance_m)
                    + 20 * math.log10(freq_hz)
                    - 147.55
                )

            # F64R-2: 输出口数**问仪器** (加载后 MODEL:INFO? 回读的物理输出口 = 探头数),
            # 不再用 tx×rx 猜 —— tx×rx 是**逻辑通道**口径, MPAC OTA 下 4 输入 × 32 探头
            # = 128 通道而输出口只有 32, 拿 tx×rx(=16) 当上界会让 32 探头**只配到前 16**,
            # 17-32 留工程默认 = 现场「路损只设一半」根因 (review 母题②)。
            # ⚠ 整段持锁 (锁可重入, 内层 _gated_write_transaction 直接嵌套): 若只在下发
            # 时取锁, "读出口号"和"发出去"之间会有窗口 —— 另一个协程正在换仿真时, 本次
            # 就会拿**上一个仿真**的口号写到新仿真上 (号码若在新仿真里也存在 = 静默配错口)。
            async with self._scpi_lock:
                await self._ensure_topology()   # 冷缓存 (后端重启) 时按需补回读
                out_ports = self._active_output_ports
                if not out_ports:
                    # 用户 2026-07-24 拍板: 拓扑未知时 fail-loud, **不回退猜口数** ——
                    # 配错口比不配更伤 (操作员以为全配上了)。
                    self._last_error = (
                        "set_path_loss 拒绝: 物理输出口未知 (仿真未加载, 或拓扑/端口号"
                        "回读失败) — 不按猜测的端口号下发路损。" + _TOPOLOGY_ESCAPE_HINT
                    )
                    logger.error(f"[F64] {self._last_error}")
                    return False
                if not await self._gated_write_transaction(
                    "set_path_loss",
                    [
                        f"OUTP:LOSS:SET {out_ch},{path_loss_db:.1f}"
                        for out_ch in out_ports      # 真实端口号, 不是 1..N
                    ],
                ):
                    return False
            logger.info(
                f"[F64] Path loss set: {path_loss_db:.1f} dB on outputs {out_ports}"
            )
            return True
        except Exception as e:
            logger.error(f"[F64] set_path_loss failed: {e}")
            self._last_error = str(e)
            return False

    async def set_doppler(
        self,
        frequency_hz: float,
        velocity_kmh: Optional[float] = None
    ) -> bool:
        """
        设置移动速度 / 最大多普勒频移。

        User Reference §20.4.6.13:
          DIAG:SIMU:MOB:MAN:CH <channel>,<speed> [unit]
          支持单位: km/h (默认), m/s, Hz (直接指定多普勒)

        注意:
          - 静态 MIMO OTA 测试中 Doppler = 0 Hz
          - F64 Release 1.0 不支持 Runtime 模式下动态改变 Doppler
          - 此命令仅在仿真停止状态下有效
        """
        if not self._visa_resource:
            return False

        try:
            # F64R-2: 遍历**回读的真实通道号**, 不是 `range(1, N+1)`。手册 §20.4.6.13
            # `MOB:MAN:CH` 是**逐通道**生效 ("sets the mobile speed of the specific
            # channel"; 另有组版本 `:CHG`), 故逐通道循环本身正确 —— 错的是**编号来源**:
            # 旧代码用 _channel_count(=整机 64 硬件容量) 当上界, 128 通道的仿真漏配一半、
            # 4 通道的模型撞不存在的通道 -200 (§20.5.2)。而且跟端口同理, 通道号也不保证
            # 是 1..N 连续 —— 既然 GROUP:CHANNELS:GET? 已经把真实号读回来了, 就按它发。
            # 两参皆空 = 无事可做, **先于**拓扑门判定 —— 一次不下发任何命令的调用不该
            # 因为"拓扑未知"变成失败 (拓扑门是为"要下发却不知道发给谁"设的)。
            if frequency_hz is None and velocity_kmh is None:
                return True
            # 整段持锁 (同 set_path_loss): 判定用的通道号必须跟下发是同一个仿真的
            async with self._scpi_lock:
                await self._ensure_topology(throttle=True)   # 冷缓存 (后端重启) 时按需补回读
                channels = self._active_channel_numbers
                if not channels:
                    self._last_error = (
                        "set_doppler 拒绝: 逻辑通道号未知 (仿真未加载, 或拓扑回读失败) "
                        "— 不按猜测的通道号下发多普勒。" + _TOPOLOGY_ESCAPE_HINT
                    )
                    logger.error(f"[F64] {self._last_error}")
                    return False
                # 优先使用 Hz 单位直接指定多普勒
                cmds: List[str] = []
                if frequency_hz is not None:
                    cmds = [
                        f"DIAG:SIMU:MOB:MAN:CH {ch},{frequency_hz} Hz"
                        for ch in channels
                    ]
                    desc = f"Doppler {frequency_hz} Hz"
                else:
                    cmds = [
                        f"DIAG:SIMU:MOB:MAN:CH {ch},{velocity_kmh}"
                        for ch in channels
                    ]
                    desc = f"Speed {velocity_kmh} km/h"
                if not await self._gated_write_transaction("set_doppler", cmds):
                    return False
            logger.info(f"[F64] {desc} ({len(channels)} 个通道)")
            return True
        except Exception as e:
            logger.error(f"[F64] set_doppler failed: {e}")
            self._last_error = str(e)
            return False

    async def start_emulation(self) -> bool:
        """
        启动仿真播放。

        User Reference §20.4.6.1:
          DIAG:SIMU:GO — 启动仿真, 从当前 CIR 位置开始
          (若之前 STOP 则从停止点继续; 若 GOS 则从头开始)

        两种管线共用此命令:
          - GCM: 信道模型开始衰落播放
          - ASC Runtime: 开始 RTC 波形播放, 初始加载第一个环境
        """
        if not self._visa_resource:
            logger.error("[F64] Cannot start: no VISA resource")
            return False
        if not self._loaded_emulation_file:
            # 2026-07-21 现场: 重启后端后驱动冷缓存 _loaded_emulation_file=None, 但 F64
            # 硬件仍加载着信道在播放 → 原硬拒让 emulation-control/attach 重启假失败。
            # 冷缓存不该做 gate (同 runtime-gate-not-frozen-snapshot 母题, 本方法对
            # _bypass_mode 冷缓存已用无条件 STATIC 0 处理, 独漏 _loaded_emulation_file):
            # 放行到 GO, 真没加载文件时 GO 自身 -200 由下面错误门 fail-loud 兜。
            logger.warning("[F64] _loaded_emulation_file 冷缓存 None — 仍尝试 GO (错误门兜底)")

        try:
            # Codex #203 R3 P2: 整个 GO 序列 (清 stale → STATIC 0 → GO → *OPC?
            # → 错误门) 持锁为一个事务 — 单命令锁下 broadcaster 轮询会插进两步
            # 之间, 留下自己的错误条目 (GO 误报被拒) 或抢先消费 GO 的错误
            # (漏报)。_scpi_lock 可重入 (scpi_lock 模块), 事务内 self._write/
            # _query 经 _do_* 重入直通。
            async with self._scpi_lock:
                # Codex #203 P2: 先清 stale — gate 只评估本次 GO 产生的错误
                await self._drain_errors()
                # P2-17 ① + Codex #201 R2 P2: GO 前**无条件**写 STATIC 0 恢复
                # 衰落 — 不依赖内存缓存 (HAL 重载后冷缓存 DISABLED 而硬件还停
                # 在 attach 直通的 STATIC 3 → GO 必 -200)。写 0 幂等。
                if self._bypass_mode != F64BypassMode.DISABLED:
                    logger.info(
                        f"[F64] GO 前清直通: STATIC {self._bypass_mode.name} → DISABLED (恢复衰落)"
                    )
                await self._write("DIAG:SIMU:MODEL:STATIC 0")
                # 2026-07-21 现场实证 (幂等怪癖第三处, 同 GOS / STATIC 3→3):
                # 已在 STATIC 0 (如刚加载完新工程) 再写 0 → F64 报 -200
                # "Setting of simulation static model failed"。原单一错误门在
                # GO 后统读, 把这个无害的 0→0 拒绝误判成 GO 失败 → start 假
                # 失败。清直通目标 (确保 STATIC 0) 已达成 → 此处先排干把它
                # 吞掉, 让下面的错误门**只**反映 GO 本身 (真 STATIC 故障会让
                # GO 也 -200, 门仍兜底)。
                await self._drain_errors()
                await self._write("DIAG:SIMU:GO")
                await self._query("*OPC?")
                # Codex #202 R2 P2: GO 失败只经 SYST:ERR? 报 (*OPC? 照答 1) —
                # 错误队列门 fail-loud, 不许带着"没在跑"的 F64 返回 True。
                # 门判定+状态更新在锁内 (agent F4, 三事务口径一致)。
                go_err = await self._first_error()
                if go_err is not None:
                    # GO 报 -200 "Wrong device state" 有**两种成因、签名相同**:
                    #   (a) F64 已在衰落运行态 (幂等"已在跑") — 目标达成, 可豁免;
                    #   (b) 前面清直通的 STATIC 0 没生效 (仍 STATIC≠0), GO 被
                    #       by-design 拒 —— 实际没在播衰落, 豁免会让测量在直通
                    #       (无衰落) 路径跑假数据。
                    # Codex #221 P1: 原按签名盲豁免 (收口 agent F1 版) 会误吞 (b)
                    # —— 正是 STATIC 3 直通 attach→衰落 转换里 STATIC 0 被拒 (新
                    # 加的 drain 已把它吞掉) 后 GO 撞 STATIC≠0 的高频路径。改为
                    # **回查 STATIC 档消歧**: 只有确认 STATIC==0 (衰落态) 才豁免,
                    # 否则 (含读不到) fail-loud。
                    _exempt = False
                    if "-200" in go_err and "Wrong device state" in go_err:
                        static_now = None
                        try:
                            raw = await self._query("DIAG:SIMU:MODEL:STATIC?")
                            static_now = raw.strip() if raw else None
                        except Exception as e:  # noqa: BLE001
                            logger.warning(
                                f"[F64] GO 豁免前回查 STATIC? 失败 ({e}) — 保守 fail-loud"
                            )
                        if static_now == "0":
                            _exempt = True
                            logger.warning(
                                f"[F64] GO 被拒 ({go_err}) 但 STATIC=0 衰落态 — "
                                "判为已在播放, 豁免为成功"
                            )
                        else:
                            self._last_error = (
                                f"start_emulation rejected: {go_err} "
                                f"(STATIC={static_now}, 非衰落态 — 仍在直通/未切成功)"
                            )
                            logger.error(
                                f"[F64] GO 被拒且 STATIC={static_now}≠0 — 仿真未启动"
                            )
                            return False
                    if not _exempt:
                        # 其他错误文本 (含 STATIC 读不到时不进上面豁免分支): 被拒时
                        # 直通缓存也不动 (Codex #202 R8/R5 "被拒状态不动"对称路径) —
                        # 单一错误门分不清 STATIC/GO 哪步被拒, 保守保持"可能仍在直通"。
                        self._last_error = f"start_emulation rejected: {go_err}"
                        logger.error(f"[F64] GO 被拒 (SYST:ERR?): {go_err} — 仿真未启动")
                        return False
                self._bypass_mode = F64BypassMode.DISABLED
                self._passthrough_active = False
                self._emulation_running = True
                self._status = InstrumentStatus.BUSY
            logger.info("[F64] Emulation started")
            return True
        except Exception as e:
            logger.error(f"[F64] start_emulation failed: {e}")
            self._last_error = str(e)
            return False

    async def stop_emulation(self) -> bool:
        """
        停止仿真。

        User Reference §20.4.6.2:
          DIAG:SIMU:STOP — 暂停仿真 (可通过 GO 从当前位置继续)
          DIAG:SIMU:GOS — 停止并倒回起点 (下次 GO 从头开始)

        本方法使用 GOS (Stop & Rewind), 确保下次启动从干净状态开始。

        Codex #202 R5: GOS 失败只经 SYST:ERR? 报 — 写后错误门 fail-loud
        (同 GO 门), 否则 attach 直通预备 (stop → STATIC 3) 假成功, 直通
        没建立照样配小区, attach 失败又被误诊成 DUT/RF 问题。事务持锁
        (drain → GOS → 错误门), 被拒时驱动状态不动 (仪器实际仍在跑)。
        """
        if not self._visa_resource:
            return False
        try:
            # 门判定+状态更新一并在锁内 (agent F4: 锁外 check-then-act 会与
            # 并发 start_emulation 交错致驱动状态漂移一拍)。
            # ⚠ agent F1 (未实证风险): "已 STOPPED 态重复 GOS" / "无 sim open
            # 态 GOS" 的 SYST:ERR? 行为无 3334 干净会话实证 — 若 F64 报 benign
            # 错, 本门会假失败卡 attach 预备第一步 (现场收工态恰是 STOPPED+
            # STATIC3)。下次现场 SCPI 冒烟先验证 (onsite-tasks 清单有条目);
            # 撞上时逃生门 = attach 序列 establish_f64_passthrough=False。
            async with self._scpi_lock:
                await self._drain_errors()
                await self._write("DIAG:SIMU:GOS")
                stop_err = await self._first_error()
                if stop_err is not None:
                    # 2026-07-21 现场实证 (上面 agent F1 预言的场景): 已停态
                    # (STOPPED, 工程开着未播) 下发 GOS, F64 报
                    #   -200,"Execution error;Wrong device state for command"
                    # —— 语义 = "本来就没在跑"。stop 的目标 (确保停止) 已达成,
                    # 当成功; 仅此签名豁免, 其他错误仍 fail-loud。
                    if "-200" in stop_err and "Wrong device state" in stop_err:
                        logger.info(
                            f"[F64] GOS 在已停态被拒 ({stop_err}) — 视为已停止, 继续"
                        )
                    else:
                        self._last_error = f"stop_emulation rejected: {stop_err}"
                        logger.error(f"[F64] GOS 被拒 (SYST:ERR?): {stop_err}")
                        return False
                self._emulation_running = False
                self._status = InstrumentStatus.READY
            logger.info("[F64] Emulation stopped and rewound")
            return True
        except Exception as e:
            logger.error(f"[F64] stop_emulation failed: {e}")
            self._last_error = str(e)
            return False

    async def set_baseband_power(
        self, power_dbm: float, input_ports: Optional[List[int]] = None
    ) -> bool:
        """
        设置输入电平 (基带功率)。

        User Reference §20.4.4.3:
          INP:LEV:AMP:CH <input>,<amplitude_dBm>
          取值范围: INP:LEV:AMP:LIM? 查询 (典型: -23 ~ 0 dBm)

        input_ports: 要下发的物理输入口号 (1-based)。None/空列表 → 用**从仿真回读的真实
        输入口号列表** (`_active_input_ports`, 由 `GROUP:INPUTS:GET?` 逐组取并集), 而
        **不是** 1..N —— 口号不保证连续 (仿真可能只占 {3,5})。
        ✅ Codex #221 R5 P2 已解 (F64R-2, 2026-07-24): 旧回退用 `_tx_antennas`, 它在后端
        冷重启 / 操作员手动面板加载 4x4 .smu 后会停在构造默认 2 → 只覆盖输入 1/2、输入
        3/4 保留工程默认 → MIMO 输入参考不平衡 (端点还回 ok=true 误导)。现改为回读真实
        口号; 缓存空时 `_ensure_topology()` 按需补读一次, 仍读不到才 fail-loud。
        """
        if not self._visa_resource:
            return False
        try:
            # F64R-2: 显式给的口优先 (上层参数决议层可精确指定); 没给才用回读的真实口数。
            # 整段持锁 (同 set_path_loss): 判定用的口号必须跟下发是同一个仿真的
            async with self._scpi_lock:
                if not input_ports:
                    await self._ensure_topology(throttle=True)   # 冷缓存时按需补回读
                ports = list(input_ports) if input_ports else (
                    list(self._active_input_ports) if self._active_input_ports else []
                )
                if not ports:
                    self._last_error = (
                        "set_baseband_power 拒绝: 未显式指定 input_ports, 且物理输入口未知"
                        " (仿真未加载, 或拓扑/端口号回读失败) — 不按猜测的端口号下发输入电平。"
                        + _TOPOLOGY_ESCAPE_HINT
                    )
                    logger.error(f"[F64] {self._last_error}")
                    return False
                if not await self._gated_write_transaction(
                    "set_baseband_power",
                    [f"INP:LEV:AMP:CH {inp},{power_dbm:.1f}" for inp in ports],
                ):
                    return False
            logger.info(f"[F64] Input level set: {power_dbm:.1f} dBm (ports={ports})")
            return True
        except Exception as e:
            logger.error(f"[F64] set_baseband_power failed: {e}")
            self._last_error = str(e)
            return False

    async def set_external_attenuators(
        self,
        attenuation_map: Dict[int, float]
    ) -> bool:
        """
        设置各输出通道的衰减值 (外部衰减器补偿)。

        使用 OUTP:GAIN:CH 调节输出增益 (负值 = 衰减)。
        User Reference §20.4.5.8:
          OUTP:GAIN:CH <output>,<gain_dB>
        """
        if not self._visa_resource:
            return False
        try:
            # 衰减用负增益表示
            if not await self._gated_write_transaction(
                "set_external_attenuators",
                [
                    f"OUTP:GAIN:CH {output_ch},{-abs(atten_db):.2f}"
                    for output_ch, atten_db in attenuation_map.items()
                ],
            ):
                return False
            logger.info(f"[F64] Attenuators set for {len(attenuation_map)} outputs")
            return True
        except Exception as e:
            logger.error(f"[F64] set_external_attenuators failed: {e}")
            self._last_error = str(e)
            return False

    async def set_output_path_loss(self, output_num: int, loss_db: float) -> bool:
        """P2-10 Step 2: 单通道输出路损补偿 (per-output), 区别于 set_path_loss 的 batch 统一。

        set_path_loss 给所有输出统一 loss (校准早期简化); 真实暗室每个 probe 路损不同
        (校准 per-probe 出值), 精细工程需逐通道设。HAL 能力先行 (供 per-probe 校准应用 /
        topology 集成 / 现场调用), SCPI 同 set_path_loss:
          OUTP:LOSS:SET <output>,<loss_db>  (User Reference §20.4.5.19)
          取值范围: OUTP:LOSS:LIM? (典型 -30 ~ 80 dB)。
        """
        if not self._visa_resource:
            return False
        try:
            if not await self._gated_write_transaction(
                f"set_output_path_loss(out={output_num})",
                [f"OUTP:LOSS:SET {output_num},{loss_db:.1f}"],
            ):
                return False
            logger.info(f"[F64] Output {output_num} path loss set: {loss_db:.1f} dB")
            return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"[F64] set_output_path_loss(out={output_num}) failed: {e}")
            self._last_error = str(e)
            return False

    async def set_output_gain(self, output_num: int, gain_db: float) -> bool:
        """P2-10 Step 2: 单通道输出增益 (OUTP:GAIN:CH), 支持正负 —— 区别于
        set_external_attenuators 的 batch map + 强制负 (`-abs`, 只衰减)。

        正增益 (放大) 补偿 probe 链路插损; 负增益 = 衰减。是 loss (set_output_path_loss)
        之外的另一个输出端电平旋钮 (Step 2: 超出 loss 补偿的精细配置)。SCPI:
          OUTP:GAIN:CH <output>,<gain_db>  (User Reference §20.4.5.8)
        """
        if not self._visa_resource:
            return False
        try:
            if not await self._gated_write_transaction(
                f"set_output_gain(out={output_num})",
                [f"OUTP:GAIN:CH {output_num},{gain_db:.2f}"],
            ):
                return False
            logger.info(f"[F64] Output {output_num} gain set: {gain_db:.2f} dB")
            return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"[F64] set_output_gain(out={output_num}) failed: {e}")
            self._last_error = str(e)
            return False

    async def get_channel_state(self) -> Dict[str, Any]:
        """
        查询 F64 当前全面状态。

        汇总: 仿真状态、旁路模式、管线类型、中心频率、输入/输出电平等.

        语义: 静态字段 (pipeline / center_freq 等内存缓存) 总是返回. 动态
        查询 (旁路状态 / SCPI 版本) per-query try, 失败的项不出现在 state
        里, 错误进 query_errors. 上层可据此区分:
          - status='disconnected'  → 无 visa
          - 'error' in state       → 整机故障
          - 'query_errors' present → 部分查询失败, 主体状态可用
          - 三者皆无                → 全部成功
        """
        if not self._visa_resource:
            return {"status": "disconnected"}

        # 静态字段 (内存缓存, 不会失败)
        state: Dict[str, Any] = {
            "pipeline": self._active_pipeline.value if self._active_pipeline else None,
            "emulation_running": self._emulation_running,
            "loaded_file": self._loaded_emulation_file,
            "model": self._current_model,
            "scenario": self._current_scenario,
            "center_freq_mhz": self._center_freq_mhz,
            # ⚠ 声明式元数据 (F64R-2 起不再用于端口寻址), 排障时别拿它解释端口行为
            "mimo_config": f"{self._tx_antennas}x{self._rx_antennas}",
            # F64R-2: 真实拓扑 —— 操作员排"为什么 set_path_loss 被拒 / 某个探头没配上"
            # 时看这几个 (None = 未加载或回读失败, 正是被拒的原因)。
            "active_inputs": self._active_inputs,
            "active_outputs": self._active_outputs,
            "active_channels": self._active_channels,
            "active_input_ports": self._active_input_ports,
            "active_output_ports": self._active_output_ports,
            # 与 get_metrics 同步: declared = 口号是人填的兜底值, 不是仪器真值
            "topology_source": self._topology_source(),
        }
        query_errors: List[str] = []

        # 查询旁路状态
        try:
            bypass_str = await self._query("DIAG:SIMU:MODEL:STATIC?")
            state["bypass_mode"] = (
                int(bypass_str.strip()) if bypass_str.strip().isdigit() else 0
            )
        except Exception as e:
            query_errors.append(f"bypass_mode: {e}")

        # 查询 SCPI 版本
        try:
            scpi_ver = await self._query("SYST:VERS?")
            state["scpi_version"] = scpi_ver.strip()
        except Exception as e:
            query_errors.append(f"scpi_version: {e}")

        if query_errors:
            state["query_errors"] = query_errors

        return state

    # ===================================================================
    # 5. 校准与诊断 SCPI (两种管线共享)
    # ===================================================================

    async def set_bypass_mode(self, mode: F64BypassMode) -> bool:
        """
        设置静态旁路模式。

        User Reference §20.4.6.25:
          DIAG:SIMU:MODEL:STATIC <state>
          0=禁用, 1=信道旁路, 2=Butler, 3=校准旁路

        校准旁路 (mode=3) 用于 RF 链路校准:
          所有通道等增益/等延迟/零相位, 信号直通。

        P2-17 ① (2026-07-03 实证): STATIC 与回放**互斥** — 运行态切 STATIC≠0
        时 F64 自动转 STOPPED (直通稳态 = STOPPED + STATIC 3); STATIC≠0 下 GO
        被 -200 拒 (by design), 恢复衰落 = STATIC 0 + GO (start_emulation 已
        内建 GO 前清直通)。

        Codex #202 R5: STATIC 写失败只经 SYST:ERR? 报 — 写后错误门 fail-loud
        (同 GO/GOS 门), 被拒时 _bypass_mode/_emulation_running 不动 (仪器
        实际状态未变, 记了会漂移)。事务持锁 (drain → STATIC → 错误门)。
        """
        if not self._visa_resource:
            return False
        try:
            # 门判定+状态更新一并在锁内 (agent F4: 锁外 check-then-act 的
            # _emulation_running 读会与并发 start_emulation 交错致漂移)。
            async with self._scpi_lock:
                await self._drain_errors()
                await self._write(f"DIAG:SIMU:MODEL:STATIC {mode.value}")
                static_err = await self._first_error()
                if static_err is not None:
                    # 2026-07-21 现场实证 (GOS 同族幂等怪癖): F64 已处于目标
                    # STATIC 档时再设同档, 报 -200 "Setting of simulation
                    # static model failed"。冷启动缓存不可信 (重启后不知仪器
                    # 真实档位), 用"复位重试"消歧: 先 STATIC 0 清 (清一步的
                    # 错误忽略并排干), 再重设目标档, 以重试的错误门为准 —
                    # 真失败时重试仍会响亮 False。
                    # agent F2 (2026-07-22 收口审查): mode=DISABLED(0) 时复位
                    # 值==目标值, 复位重试是三连 0→0 怪叫必假失败 (下游
                    # clear_passthrough_mode → path_loss cal 把假失败写进证书
                    # warnings 误导排障) → 0 档首发被拒直接按幂等豁免成功
                    # (与 start_emulation GO 前 0→0 drain 同处理), 不进重试。
                    if mode == F64BypassMode.DISABLED:
                        # DISABLED 复位值==目标值, 复位重试无意义 (三连 0→0 怪叫)。
                        # Codex #221 R5 P1 + PROPSIM 手册 20.5.2/20.6.1 (NotebookLM
                        # 查证): 已在 0 档再设 0 的怪叫, 固件可能报 "Wrong device
                        # state"(状态机层拒绝) 或 "Setting of simulation static model
                        # failed"(底层执行失败) —— 两签名都可能, 靠字符串猜会把
                        # session desync / 仍在 STATIC 3 故障态误吞成功。手册推荐回查
                        # DIAG:SIMU:MODEL:STATIC? 确认真实档 (STOPPED/RUNNING 可靠回读,
                        # 会话异常读不到)。与 start_emulation GO 豁免同一消歧: 只有
                        # 确认 STATIC==0 (真禁用) 才豁免, 否则 (含读不到) fail-loud —
                        # 免真故障被吞成功污染 clear_passthrough → 校准证书。
                        static_now = None
                        try:
                            raw = await self._query("DIAG:SIMU:MODEL:STATIC?")
                            static_now = raw.strip() if raw else None
                        except Exception as e:  # noqa: BLE001
                            logger.warning(
                                f"[F64] DISABLED 豁免前回查 STATIC? 失败 ({e}) — 保守 fail-loud"
                            )
                        if static_now == "0":
                            logger.info(
                                f"[F64] STATIC 0 首发被拒 ({static_err}) 但回查 STATIC?=0 "
                                "确认已在禁用档 — 幂等豁免为成功"
                            )
                        else:
                            self._last_error = (
                                f"set_bypass_mode(DISABLED) rejected: {static_err} "
                                f"(回查 STATIC?={static_now}≠0 — 未真禁用/session desync)"
                            )
                            logger.error(
                                f"[F64] STATIC 0 被拒且回查 STATIC?={static_now}≠0 — "
                                "真故障/session desync, fail-loud"
                            )
                            return False
                    else:
                        logger.info(
                            f"[F64] STATIC {mode.value} 首发被拒 ({static_err}) — "
                            "按已在档/粘滞处理: STATIC 0 复位后重试一次"
                        )
                        await self._write("DIAG:SIMU:MODEL:STATIC 0")
                        await self._drain_errors()  # 清位错误不计 (0→0 同样会怪叫)
                        await self._write(f"DIAG:SIMU:MODEL:STATIC {mode.value}")
                        retry_err = await self._first_error()
                        if retry_err is not None:
                            self._last_error = (
                                f"set_bypass_mode({mode.name}) rejected: {retry_err}"
                            )
                            logger.error(
                                f"[F64] STATIC {mode.value} 复位重试仍被拒 "
                                f"(SYST:ERR?): {retry_err}"
                            )
                            return False
                # 运行态切 STATIC≠0 → F64 自动 STOPPED; 驱动状态跟着同步, 否则
                # _emulation_running 漂移 (输出测量冻结标注 P1-21 ④ 也依赖它)。
                if mode != F64BypassMode.DISABLED and self._emulation_running:
                    self._emulation_running = False
                    self._status = InstrumentStatus.READY
                    logger.info(
                        f"[F64] 运行态切 STATIC {mode.value} → F64 自动 STOPPED (驱动状态已同步)"
                    )
                self._bypass_mode = mode
            logger.info(f"[F64] Bypass mode: {mode.name}")
            return True
        except Exception as e:
            logger.error(f"[F64] set_bypass_mode failed: {e}")
            self._last_error = str(e)
            return False

    # ===================================================================
    # 5b. CE+SA 路损校准 tone 链路 (3GPP MIMO OTA, 取代 VNA)
    # ===================================================================
    # 服务层 ProbePathLossCalibrationService.acquire_sa_power_via_ce_tone()
    # 通过 capability dispatch 选 D 路径 (CE 自己出 CW) 或 B 路径 (上游 BSE/SG
    # 出 CW + CE 透传). 两条路径都在这里实现:
    #
    #   D — Internal Interference Generator (optional license):
    #       OUTPut:INTERFerence:ADD <port>, <id>, 2  (type=2 = CW)
    #       + STRATegy:SET 1 (恒定功率) + FREQ:SET + POW:SET + STatus 1
    #       (User Reference §13 + §20.4.9)
    #   B — Calibration bypass (无 license 也支持):
    #       DIAG:SIMU:MODEL:STATIC 3  (所有通道等增益/等延迟/零相位透传)
    #       配合上游 SG/BSE 出 CW, 信号经 CE 原样输出.
    # ===================================================================

    @staticmethod
    def _ce_port_to_output_num(ce_port: Optional[str]) -> str:
        """ce_port 解析为 SCPI 用的 output number string.

        - None → "1" (主端口默认)
        - 纯数字 ("1", "12") → 直接用
        - "B1.1" / "B1.2" 等 ETSL 风格 connector 表示法 → 取小数点后部分
          作为 output index (这是 CAICT 现场约定; 跨实验室部署在
          InstrumentCategory.config 里另写映射表覆盖)
        - 解析失败 → "1" + warn (生产部署应在 LabProfile 显式声明 ce_port)
        """
        if ce_port is None:
            return "1"
        s = str(ce_port).strip()
        if s.isdigit():
            return s
        # "B1.1" / "A2.3" → 小数点后的数字
        if "." in s:
            tail = s.rsplit(".", 1)[-1]
            if tail.isdigit():
                return tail
        logger.warning(
            "[F64] ce_port=%r unrecognized format, defaulting to output 1; "
            "configure LabProfile.ce_port explicitly for production",
            ce_port,
        )
        return "1"

    def get_calibration_tone_capabilities(self) -> List[CalibrationToneCapability]:
        """声明本 PROPSIM 的 CE+SA tone 能力.

        D 路径 (INTERNAL_CW_GENERATOR) 需要 Internal Interference Generator
        optional license. has_interference_generator 在 connect() 时由
        *OPT? 探测填充 (见 _apply_discovered_capabilities); config 显式声明
        会跳过探测. 探测前 / 未连接时为 None, 按无 license 处理.

        B 路径 (PASSTHROUGH_ONLY) 任何 PROPSIM 都支持 — 走 BypassMode
        .CALIBRATION (DIAG:SIMU:MODEL:STATIC 3), 全通道等增益等延迟透传.
        """
        caps: List[CalibrationToneCapability] = [
            CalibrationToneCapability.PASSTHROUGH_ONLY,
        ]
        if self.has_interference_generator:
            caps.insert(0, CalibrationToneCapability.INTERNAL_CW_GENERATOR)
        return caps

    async def set_calibration_tone(
        self,
        frequency_hz: float,
        power_dbm: float,
        ce_port: Optional[str] = None,
    ) -> bool:
        """[D 路径] 通过 Internal Interference Generator 出已知 CW tone.

        SCPI sequence (User Reference §20.4.9):
            OUTPut:INTERFerence:ADD <out>, <id>, 2     # type=2 = CW
            OUTPut:INTERFerence:STRATegy:SET <id>, 1   # 恒定功率
            OUTPut:INTERFerence:FREQuency:SET <id>, <MHz>
            OUTPut:INTERFerence:POWer:SET <id>, <dBm>
            OUTPut:INTERFerence:STatus <id>, 1         # 启用

        前置: has_interference_generator=True (license 已开).

        重复调用安全 — 先 REMove 旧 ID 避免 "identifier in use" 错误.
        """
        if not self._visa_resource:
            return False
        if not self.has_interference_generator:
            logger.error(
                "[F64] set_calibration_tone called but has_interference_generator"
                " is False. Configure instrument with this option enabled, or "
                "fall through to PASSTHROUGH path (BSE/SG upstream)."
            )
            return False

        out_num = self._ce_port_to_output_num(ce_port)
        cal_id = self._cal_tone_id
        freq_mhz = frequency_hz / 1e6

        try:
            # Codex #202 R10 P2: SCPI 拒绝 (-113/-200) 只进错误队列不抛异常,
            # 原 _check_errors 只 log → 假成功 (tone 没起来照测, SA 读噪声
            # 本底路损全错)。改锁事务 + _first_error 门 (五事务同型):
            # drain 吃防御 REMove 的预期 -200, 门只评估本次写序列的错误。
            async with self._scpi_lock:
                # 1. 先清掉同 id 的旧 interferer (重复调用幂等)
                try:
                    await self._write(f"OUTPut:INTERFerence:REMove {cal_id}")
                except Exception:
                    pass  # 没有旧的就忽略
                await self._drain_errors()  # 吃掉上行预期 -200 + stale

                # 2. 加 CW 干扰源到指定 output (type=2 = CW)
                await self._write(
                    f"OUTPut:INTERFerence:ADD {out_num},{cal_id},2"
                )
                # 3. 恒定功率策略 (而非 C/I-ratio, 校准要绝对值)
                await self._write(
                    f"OUTPut:INTERFerence:STRATegy:SET {cal_id},1"
                )
                # 4. 频率 (MHz) 和功率 (dBm)
                await self._write(
                    f"OUTPut:INTERFerence:FREQuency:SET {cal_id},{freq_mhz:.6f}"
                )
                await self._write(
                    f"OUTPut:INTERFerence:POWer:SET {cal_id},{power_dbm:.2f}"
                )
                # 5. 启用
                await self._write(f"OUTPut:INTERFerence:STatus {cal_id},1")

                tone_err = await self._first_error()
                if tone_err is not None:
                    self._last_error = f"set_calibration_tone rejected: {tone_err}"
                    logger.error(
                        f"[F64] tone 写序列被拒 (SYST:ERR?): {tone_err} — tone 未启用"
                    )
                    try:
                        await self._write(f"OUTPut:INTERFerence:REMove {cal_id}")
                    except Exception:
                        pass
                    self._cal_tone_active = False
                    return False
                self._cal_tone_active = True
            logger.info(
                "[F64] Calibration tone ON: out=%s freq=%.1fMHz power=%.1fdBm id=%s",
                out_num, freq_mhz, power_dbm, cal_id,
            )
            return True
        except Exception as e:
            logger.error(f"[F64] set_calibration_tone failed: {e}")
            self._last_error = str(e)
            # 失败时尝试清理避免半状态
            try:
                await self._write(f"OUTPut:INTERFerence:REMove {cal_id}")
            except Exception:
                pass
            self._cal_tone_active = False
            return False

    async def stop_calibration_tone(self) -> bool:
        """[D 路径] 关 CW tone 并移除 interferer.

        SCPI:
            OUTPut:INTERFerence:STatus <id>, 0   # 禁用
            OUTPut:INTERFerence:REMove <id>      # 移除

        finally 块里调用避免 CE 长时间发射. 没启用过也安全 — REMove
        不存在的 id 报 -200, 该场景 (防御性清理) 不判失败。

        Codex #202 R10 P2: 原实现吞写异常 + _check_errors 只 log → 恒 True,
        服务层的 `if not stop_calibration_tone()` 门在真驱动上永不触发,
        tone 停不掉时证书 warnings 仍然干净。改 fail-loud: 写异常 (仪器
        失联, tone 状态未知) → False; tone 真活跃时错误队列有条目 → False
        (真停失败); 均保持 _cal_tone_active 原值 (R8 "被拒状态不动" 同族,
        标"可能仍在发")。仅防御性清理场景 (-200 预期) 照旧 True。
        """
        if not self._visa_resource:
            return False
        cal_id = self._cal_tone_id
        try:
            async with self._scpi_lock:
                # agent 门审 F2: 快照锁内读 — 锁外读在并发 set‖stop 交错时
                # 会拿到 set 进锁前的旧值, 恰好绕过"活跃被拒不忽略"判定
                tone_was_active = self._cal_tone_active
                await self._drain_errors()  # 门只评估本次停止序列的错误
                write_failed: Optional[str] = None
                try:
                    await self._write(f"OUTPut:INTERFerence:STatus {cal_id},0")
                except Exception as e:  # noqa: BLE001
                    write_failed = f"STatus 0 write failed: {e}"
                try:
                    await self._write(f"OUTPut:INTERFerence:REMove {cal_id}")
                except Exception as e:  # noqa: BLE001
                    write_failed = write_failed or f"REMove write failed: {e}"
                if write_failed is not None:
                    self._last_error = f"stop_calibration_tone: {write_failed}"
                    logger.error(
                        f"[F64] tone 停止写失败 (仪器失联?): {write_failed} — "
                        f"tone 状态未知, 保持 active 标记"
                    )
                    return False
                stop_err = await self._first_error()
                if stop_err is not None and tone_was_active:
                    self._last_error = f"stop_calibration_tone rejected: {stop_err}"
                    logger.error(
                        f"[F64] tone 停止被拒 (SYST:ERR?): {stop_err} — "
                        f"F64 可能仍在发 tone"
                    )
                    return False
                self._cal_tone_active = False
            logger.info(f"[F64] Calibration tone OFF (id={cal_id})")
            return True
        except Exception as e:
            logger.error(f"[F64] stop_calibration_tone failed: {e}")
            self._last_error = str(e)
            return False

    async def set_passthrough_mode(
        self,
        ce_port: Optional[str] = None,
        ce_input_port: Optional[str] = None,
        mode: Optional[int] = None,
    ) -> bool:
        """[B 路径] 切到静态旁路透传. 默认 calibration bypass (STATIC 3).

        实现复用 set_bypass_mode:
            DIAG:SIMU:MODEL:STATIC <mode>   (User Reference §20.4.6.25)

        开关 2 (2026-07-21 现场): mode 可选 1/2/3 (F64BypassMode 非 DISABLED
        档), 默认 None → CALIBRATION(3)。官方定位 (ATE 实践笔记 p12):
        BUTLER(2) 相位按 Butler 矩阵排布 "improves diversity so that MIMO
        links can be established" — attach 后 4 层配置起不来时切 2;
        CALIBRATION(3) 统一 -10 dB 零相位, 官方给系统校准用 (attach 单层
        信令两态均实证 CONN, 05-27)。注意 2/1 档电平跟模型平均走, 不是
        固定 -10 dB。mode=0/非法值 → False (透传不能是"关闭", 走布尔契约)。

        在此模式下上游 SG/BSE 注入的信号经 CE 静态透传输出, 配合 switch
        路由到指定 probe. ce_port / ce_input_port 在静态旁路下不需要
        per-port 配置 (全局透传), 仅记录到状态用于 trace.
        """
        if mode is None:
            resolved = F64BypassMode.CALIBRATION
        else:
            # 门审 #216 F5: bool 是 int 子类 — mode=True 会静默变 STATIC 1
            # (模型旁路), API JSON true 同坑; 显式拒绝
            if isinstance(mode, bool):
                logger.error(
                    f"[F64] set_passthrough_mode: mode={mode!r} 是布尔值 "
                    "(合法 1/2/3 整数) — 拒绝"
                )
                self._last_error = f"invalid passthrough mode: {mode!r}"
                return False
            try:
                resolved = F64BypassMode(int(mode))
            except (ValueError, TypeError):
                logger.error(
                    f"[F64] set_passthrough_mode: 非法 mode={mode!r} "
                    "(合法 1/2/3) — 拒绝"
                )
                self._last_error = f"invalid passthrough mode: {mode!r}"
                return False
            if resolved == F64BypassMode.DISABLED:
                logger.error(
                    "[F64] set_passthrough_mode: mode=0 (DISABLED) 不是透传 — "
                    "退出透传请用 clear_passthrough_mode()"
                )
                self._last_error = "passthrough mode cannot be DISABLED"
                return False
        ok = await self.set_bypass_mode(resolved)
        if ok:
            self._passthrough_active = True
            logger.info(
                "[F64] Passthrough mode ON (out=%s, in=%s, %s bypass STATIC %d)",
                ce_port or "all", ce_input_port or "all",
                resolved.name, resolved.value,
            )
        return ok

    async def clear_passthrough_mode(self) -> bool:
        """[B 路径] 退出 calibration bypass, 恢复正常 fading 配置."""
        ok = await self.set_bypass_mode(F64BypassMode.DISABLED)
        if ok:
            self._passthrough_active = False
            logger.info("[F64] Passthrough mode OFF (bypass disabled)")
        return ok

    # ===================================================================
    # User alignment (Integrated Setup Calibration, optional license)
    # User Reference §17 + §20.4.2.18-21, .32-36.
    #
    # 用户级 alignment 补偿 F64 内部各通道随时间/温度/环境的相位&增益漂移.
    # 工厂校准 (§6.1) 给绝对计量基准, 用户 alignment 给相对一致性. 是
    # OPTIONAL license, 不是每台 F64 都激活.
    #
    # 这些方法通过 SCPI 实现的能力:
    #   - 查询当前是否激活 / alignment 名 / 元信息 (FW/SW/timestamp)
    #   - 重启后用名字重新激活 (alignment 数据本身已存盘, 但开机不自动 active)
    #   - 列出已连接的 ACU (Auto Calibration Unit) — 全自动 alignment 时用
    #
    # 不在 SCPI 接口里的 (必须人在仪器前操作):
    #   - 跑一次新 alignment (要插拔 thru 走 wizard)
    # ===================================================================

    async def get_user_alignment_status(self) -> Optional[Dict[str, Any]]:
        """查询当前激活的 user alignment 名 + 元信息.

        SCPI: SYST:CALIB:USER:GET? + SYST:CALIB:USER:INFO? (§20.4.2.19, .21)

        Returns:
            {"alignment_name": <name>, "info": <info string>}
                — 有激活的 alignment 时
            None — 未激活, 或查询失败 (firmware 不支持本组命令也会落到这里)
        """
        if not self._visa_resource:
            return None
        try:
            raw_name = await self._query("SYSTem:CALIBration:USER:GET?")
        except Exception as e:
            logger.warning(f"[F64] User alignment query failed: {e}")
            return None
        name = raw_name.strip().strip('"').strip("'")
        if not name:
            return None
        info = ""
        try:
            raw_info = await self._query("SYSTem:CALIBration:USER:INFO?")
            info = raw_info.strip().strip('"').strip("'")
        except Exception as e:
            logger.debug(
                f"[F64] User alignment info query failed (non-fatal): {e}"
            )
        return {"alignment_name": name, "info": info}

    async def enable_user_alignment(self, name: str) -> bool:
        """重新激活已存盘的 user alignment.

        典型场景: F64 重启后已存盘的 alignment 不会自动 active, 必须显式
        调用 SYST:CALIB:USER:SET 1,<name> (§20.4.2.18). 设完用 GET? 回读
        确认.

        Args:
            name: alignment 文件名 (跟 wizard 里 Configuration Name 一致)

        Returns:
            True  — set + GET? 回读匹配
            False — alignment 不存在 / VISA 异常 / 名字不匹配
        """
        if not name:
            raise ValueError("alignment name cannot be empty")
        if not self._visa_resource:
            return False
        try:
            await self._write(f"SYSTem:CALIBration:USER:SET 1,{name}")
            raw = await self._query("SYSTem:CALIBration:USER:GET?")
            active = raw.strip().strip('"').strip("'")
            if active == name:
                logger.info(f"[F64] User alignment activated: {name}")
                return True
            logger.warning(
                f"[F64] enable_user_alignment(\"{name}\"): post-set GET? "
                f"returned {active!r} — file may not exist on the emulator."
            )
            return False
        except Exception as e:
            logger.error(
                f"[F64] enable_user_alignment(\"{name}\") failed: {e}"
            )
            return False

    @staticmethod
    def _parse_alignment_date(info: Optional[str]) -> Optional["date"]:
        """P2-10 Step 3: 从 SYST:CALIB:USER:INFO? 的 info string 容错解析标定日期。

        info 格式是**现场真值** (firmware 相关, 未实测) —— 尝试常见日期格式 (ISO 优先),
        解析不出返回 None (freshness 标 unknown, 不误判)。现场确认格式后可 tighten。
        """
        if not info:
            return None
        import re
        from datetime import date
        # F64 INFO? 实测含 DD.MM.YYYY 点分隔 (test_propsim_user_alignment 示例
        # "FI..., 29.01.2024, ..."); 另容错 ISO / 斜杠。order 决定 group → (y,m,d) 映射。
        for pat, order in (
            (r"(\d{1,2})\.(\d{1,2})\.(\d{4})", "dmy"),  # 29.01.2024 (F64 INFO 实测格式)
            (r"(\d{4})-(\d{1,2})-(\d{1,2})", "ymd"),    # 2026-05-27 (ISO)
            (r"(\d{4})/(\d{1,2})/(\d{1,2})", "ymd"),    # 2026/05/27
            (r"(\d{1,2})/(\d{1,2})/(\d{4})", "mdy"),    # 05/27/2026
        ):
            m = re.search(pat, info)
            if not m:
                continue
            try:
                if order == "ymd":
                    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                if order == "dmy":
                    return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))  # mdy
            except ValueError:
                return None
        return None

    def alignment_freshness(
        self, info: Optional[str], *, today: "date", max_age_days: Optional[int] = None
    ) -> Dict[str, Any]:
        """P2-10 Step 3: 判断 user alignment 标定数据新鲜度 (该不该重标)。

        alignment 补偿内部通道相位/增益的温度&时间漂移, 标定数据随时间过期。解析 info
        里的标定日期跟 today 比 —— 超过 max_age_days → stale (建议重标)。

        - calibrated_date 解析不出 (info 无日期 / 格式未知) → freshness="unknown" (不误判)。
        - age <= max_age → "fresh"; > max_age → "stale"。

        today 注入 (单测可控, 避免 driver 内 date.today() 不可测); max_age_days 缺省用
        driver 的 _alignment_max_age_days (connection_params 可 override)。
        """
        max_age = self._alignment_max_age_days if max_age_days is None else max_age_days
        d = self._parse_alignment_date(info)
        if d is None:
            return {
                "freshness": "unknown",
                "calibrated_date": None,
                "age_days": None,
                "max_age_days": max_age,
            }
        age = (today - d).days
        return {
            "freshness": "stale" if age > max_age else "fresh",
            "calibrated_date": d.isoformat(),
            "age_days": age,
            "max_age_days": max_age,
        }

    async def list_external_units(self) -> List[Dict[str, Any]]:
        """列出连接到 F64 的 ACU (Auto Calibration Units).

        SCPI: SYST:EXT:UNIT:LIST? 0 (§20.4.2.32)
        响应示例: "ACU 12345 (C5),ACU 67890 (C6)"
        括号里是控制电缆所连的 BNC connector (C5/C7 等).

        Returns:
            每个检测到的 ACU 一条 {"unit": "ACU 12345", "connector": "C5"}.
            空列表表示没有 ACU 连接 (那么 alignment 只能走 manual mode).
        """
        if not self._visa_resource:
            return []
        try:
            # 第二参数 0 = 仅返回缓存, 不触发 scan; 用 1 会让 F64 重新扫描所有
            # connector, 耗时, 在 precheck 路径上不必要.
            raw = await self._query("SYSTem:EXTernal:UNIT:LIST? 0")
        except Exception as e:
            logger.warning(f"[F64] External unit list query failed: {e}")
            return []
        raw = raw.strip()
        if not raw:
            return []
        units: List[Dict[str, Any]] = []
        for token in raw.split(","):
            token = token.strip().strip('"').strip("'")
            if not token:
                continue
            unit_id = token
            connector: Optional[str] = None
            # Manual 解析 "ACU 12345 (C5)" 形式 — 末尾括号 = connector
            if "(" in token and token.endswith(")"):
                head, _, rest = token.rpartition("(")
                unit_id = head.strip()
                connector = rest.rstrip(")").strip() or None
            units.append({"unit": unit_id, "connector": connector})
        return units

    async def set_center_frequency(self, channel: int, freq_mhz: float) -> bool:
        """
        设置指定通道的中心频率。

        User Reference §20.4.3.11 (运行中可用):
          CALC:FILT:CENT:CH <channel>,<MHz>
        """
        if not self._visa_resource:
            return False
        try:
            await self._write(f"CALC:FILT:CENT:CH {channel},{freq_mhz}")
            return True
        except Exception as e:
            self._last_error = str(e)
            return False

    @staticmethod
    def _inp_meas_timeout_ms(measurement_time_s: float) -> int:
        """INP 测量族 (INP:LEV:MEAS? / AUTOSET 及其 *OPC?) 的超时 (P1-21 ③)。

        2026-07-03 实证: 这族命令是 **deferred-response** — 结果就绪才应答
        (要等满 measurement_time + 器件内部整理), 不是固定延迟; 固定短超时
        读法必错位 (超时后应答迟到, 下一条 query 读串, 现场会话连锁错位的
        源头之一)。按测量时长给 5s 缓冲, 下限保持 VISA_TIMEOUT_AUTOSET。
        """
        return max(VISA_TIMEOUT_AUTOSET, int((measurement_time_s + 5) * 1000))

    async def autoset_input_level(self, input_num: int, measurement_time_s: float = 3.0) -> Optional[float]:
        """
        自动测量并设置输入电平和峰均比。

        User Reference §20.4.4.7:
          INP:LEV:AUTOSET <input>,<time>
          time = 0.5, 1, 3, 5, 10 秒

        返回测量到的输入功率 (dBm), 或 None 表示失败。
        """
        if not self._visa_resource:
            return None
        try:
            # 先测量 (deferred-response — 超时按测量时长, P1-21 ③)
            result = await self._query(
                f"INP:LEV:MEAS? {input_num},{measurement_time_s}",
                timeout=self._inp_meas_timeout_ms(measurement_time_s)
            )
            # 响应格式: "<level_dBm>,<crest_factor_dB>"
            parts = result.strip().split(",")
            level_dbm = float(parts[0])
            crest_db = float(parts[1]) if len(parts) > 1 else 0

            # 自动设置
            await self._write(
                f"INP:LEV:AUTOSET {input_num},{measurement_time_s}",
            )
            # 用 IEEE 488.2 *OPC? 同步等待 autoset 完成 — 比硬 sleep 可靠:
            # *OPC? 阻塞直到所有挂起的 SCPI 操作完成, 立即返回 "1".
            # 超时按测量时长动态 (deferred-response, P1-21 ③)。
            await self._query(
                "*OPC?", timeout=self._inp_meas_timeout_ms(measurement_time_s)
            )

            logger.info(f"[F64] Input {input_num} autoset: {level_dbm} dBm, crest={crest_db} dB")
            return level_dbm
        except Exception as e:
            logger.error(f"[F64] autoset_input_level failed: {e}")
            return None

    # ===================================================================
    # 输入信号参考原子能力 (P0-8 Step 2 Phase 1)
    # ===================================================================
    # F64 每输入需正确的"平均电平 + crest factor"前端参考, 否则前端增益错 →
    # DL 失真 (bypass 与衰落模式都受影响) → DUT 解不出 PDSCH。这些是 driver 层
    # 薄封装; 跨 driver 闭环 (UXM 功率 ↔ F64 参考) + 编排在上层服务。
    # 设计见 docs/architecture/f64-input-level-and-dynamic-range.md。

    async def _query_float_pair(self, scpi: str) -> Optional[Tuple[float, float]]:
        """查询返回 "<a>,<b>" 的两浮点对 (limits 类); 解析失败返回 None。"""
        if not self._visa_resource:
            return None
        raw = ""
        try:
            raw = (await self._query(scpi)).strip()
            parts = raw.split(",")
            return (float(parts[0]), float(parts[1]))
        except (ValueError, IndexError) as e:
            logger.warning(f"[F64] {scpi} parse failed: {raw!r} ({e})")
            return None
        except Exception as e:
            logger.error(f"[F64] {scpi} failed: {e}")
            return None

    async def measure_input(
        self, input_num: int, measurement_time_s: float = 1.0
    ) -> Optional[Tuple[float, float]]:
        """测量 (不设) 输入的平均电平 + crest factor。

        INP:LEV:MEAS? <in>,<t> → "<avg_dBm>,<crest_dB>" (User Reference §20.4.4.6)。
        <t> = 0.5/1/3/5/10 秒。无信号/输出过强 → device error → 返回 None。
        返回 (avg_dbm, crest_db) 或 None。
        """
        if not self._visa_resource:
            return None
        resp = ""
        try:
            resp = (await self._query(
                f"INP:LEV:MEAS? {input_num},{measurement_time_s}",
                timeout=self._inp_meas_timeout_ms(measurement_time_s),
            )).strip()
            parts = resp.split(",")
            avg = float(parts[0])
            crest = float(parts[1]) if len(parts) > 1 else 0.0
            return (avg, crest)
        except (ValueError, IndexError) as e:
            logger.warning(f"[F64] measure_input({input_num}) parse failed: {resp!r} ({e})")
            return None
        except Exception as e:
            logger.error(f"[F64] measure_input({input_num}) failed: {e}")
            return None

    async def autoset_all_inputs(self, measurement_time_s: float = 3.0) -> bool:
        """对所有输入同时测量并设定 avg + crest (INP:LEV:AUTOSET 0,<t>, §20.4.4.7)。

        <in>=0 = 全部输入同测 (保 MIMO 平衡)。测量失败 (无信号/过强) 不改旧值、报错。
        用于"下行静态参考": 满 RB 代表性信号下测一次锁定 (见设计文档 §3.3/§4)。
        **失败 (device error) 时 fail-loud 返回 False**, 不让上层拿 stale 参考继续。
        """
        if not self._visa_resource:
            return False
        try:
            # ①-③ 持锁为一个事务 (Codex #203 R3 同型: 单命令锁下 broadcaster
            # 轮询会污染/抢食错误队列, gate 误报或漏报; 锁可重入)
            async with self._scpi_lock:
                # ① 清空遗留 stale 错误 (FIFO, 否则会被 ③ 误判成本次 AUTOSET 失败)
                await self._drain_errors()
                # ② AUTOSET 全输入 (*OPC? 超时按测量时长动态, deferred-response P1-21 ③)
                await self._write(f"INP:LEV:AUTOSET 0,{measurement_time_s}")
                await self._query(
                    "*OPC?", timeout=self._inp_meas_timeout_ms(measurement_time_s)
                )
                # ③ fail-loud: AUTOSET 失败 (无信号/过强) 报 device error (§20.4.4.7) →
                #    return False, 不能让 Phase 2 编排拿 stale/无效参考继续 (Codex on PR #95)
                autoset_err = await self._first_error()
            if autoset_err is not None:
                self._last_error = f"autoset failed: {autoset_err}"
                logger.error(f"[F64] autoset_all_inputs 失败 (SYST:ERR?): {autoset_err}")
                return False
            logger.info(f"[F64] autoset all inputs ok (t={measurement_time_s}s)")
            return True
        except Exception as e:
            logger.error(f"[F64] autoset_all_inputs failed: {e}")
            self._last_error = str(e)
            return False

    async def autoset_inputs(
        self, input_nums: Iterable[int], measurement_time_s: float = 3.0
    ) -> bool:
        """对**指定子集**输入逐个 AUTOSET (INP:LEV:AUTOSET <in>,<t>), fail-loud。

        与 ``autoset_all_inputs`` (INP:LEV:AUTOSET 0, 全输入同测、保 MIMO 平衡) 不同:
        本方法只对 ``input_nums`` 列表中的输入做 autoset, **避免对未连接输入触发
        no-signal device error** (Codex on PR #96: 子集拓扑下 INP:LEV:AUTOSET 0 会因
        未连接的输入而失败)。代价: 失去同测的 MIMO 平衡 (per-input 顺序而非并发)。

        失败 (任一输入报 device error) 即 fail-loud 返回 False, 不让上层拿部分更新的
        参考继续。空列表视为 no-op (True)。
        """
        if not self._visa_resource:
            return False
        inputs_list = list(input_nums)
        if not inputs_list:
            return True  # no-op
        try:
            for in_num in inputs_list:
                # 每个 input 的 (清 stale → AUTOSET → *OPC? → 错误门) 是一个
                # 判定单元, 整体持锁 (Codex #203 R3 同型; 逐 input 事务而非
                # 全循环持锁, 避免 N×AUTOSET 时长挡监控; 锁可重入)
                async with self._scpi_lock:
                    await self._drain_errors()
                    await self._write(f"INP:LEV:AUTOSET {in_num},{measurement_time_s}")
                    # Codex #202 R3: deferred-response 动态超时 (P1-21 ③) —
                    # 原 (t+2)s 在 3s 档只给 5s, 低于该命令族 15s 下限
                    await self._query(
                        "*OPC?", timeout=self._inp_meas_timeout_ms(measurement_time_s)
                    )
                    err = await self._first_error()
                if err is not None:
                    self._last_error = f"autoset input {in_num} failed: {err}"
                    logger.error(
                        "[F64] autoset_inputs({}) 失败 (SYST:ERR?): {}".format(in_num, err)
                    )
                    return False
            logger.info(
                "[F64] autoset inputs %s ok (t=%ss)", inputs_list, measurement_time_s
            )
            return True
        except Exception as e:
            logger.error(f"[F64] autoset_inputs failed: {e}")
            self._last_error = str(e)
            return False

    async def get_input_level_limits(
        self, input_num: int
    ) -> Optional[Tuple[float, float]]:
        """输入平均电平允许窗口 (INP:LEV:AMP:LIM? <in> → "<lo>,<hi>", §20.4.4.5)。

        电平不能设到窗口外。返回 (lower_dbm, upper_dbm) 或 None。
        """
        return await self._query_float_pair(f"INP:LEV:AMP:LIM? {input_num}")

    async def get_crest_limits(
        self, input_num: int
    ) -> Optional[Tuple[float, float]]:
        """crest factor 允许窗口 (INP:CRE:LIM? <in> → "<lo>,<hi>", §20.4.4.11)。"""
        return await self._query_float_pair(f"INP:CRE:LIM? {input_num}")

    async def get_crest_factor(self, input_num: int) -> Optional[float]:
        """读 crest factor (INP:CRE:GET? <in>, §20.4.4.10)。"""
        if not self._visa_resource:
            return None
        try:
            return float((await self._query(f"INP:CRE:GET? {input_num}")).strip())
        except Exception as e:
            logger.warning(f"[F64] get_crest_factor({input_num}) failed: {e}")
            return None

    async def set_crest_factor(self, input_num: int, crest_db: float) -> bool:
        """设 crest factor (INP:CRE:SET <in>,<dB>, §20.4.4.9)。

        超窗口会被自动设到最近合法值 (手册)。手动设法; 一般优先 autoset。
        """
        if not self._visa_resource:
            return False
        try:
            return await self._gated_write_transaction(
                f"set_crest_factor(in={input_num})",
                [f"INP:CRE:SET {input_num},{crest_db:.2f}"],
            )
        except Exception as e:
            logger.error(f"[F64] set_crest_factor({input_num}) failed: {e}")
            self._last_error = str(e)
            return False

    async def set_input_measurement_mode(
        self, input_num: int, mode: F64InputMeasMode
    ) -> bool:
        """设输入测量模式 (INP:MEAS:MODE:SET <in>,<mode>, §20.4.4.23)。

        TDD 5G DL 用 BURST (见 F64InputMeasMode)。<in>=0 = 全部输入。
        """
        if not self._visa_resource:
            return False
        try:
            return await self._gated_write_transaction(
                f"set_input_measurement_mode(in={input_num})",
                [f"INP:MEAS:MODE:SET {input_num},{int(mode)}"],
            )
        except Exception as e:
            logger.error(f"[F64] set_input_measurement_mode({input_num}) failed: {e}")
            self._last_error = str(e)
            return False

    async def get_input_measurement_mode(
        self, input_num: int
    ) -> Optional[F64InputMeasMode]:
        """读输入测量模式 (INP:MEAS:MODE:GET? <in>, §20.4.4.24)。"""
        if not self._visa_resource:
            return None
        try:
            raw = (await self._query(f"INP:MEAS:MODE:GET? {input_num}")).strip()
            return F64InputMeasMode(int(raw))
        except Exception as e:
            logger.warning(f"[F64] get_input_measurement_mode({input_num}) failed: {e}")
            return None

    async def set_burst_trigger_level(self, input_num: int, trigger_dbm: float) -> bool:
        """设 burst 测量绝对触发电平 (INP:MEAS:BURST:TRIG:SET <in>,<dBm>, §20.4.4.27)。

        仅在 burst 测量模式下可用。
        """
        if not self._visa_resource:
            return False
        try:
            return await self._gated_write_transaction(
                f"set_burst_trigger_level(in={input_num})",
                [f"INP:MEAS:BURST:TRIG:SET {input_num},{trigger_dbm:.2f}"],
            )
        except Exception as e:
            logger.error(f"[F64] set_burst_trigger_level({input_num}) failed: {e}")
            self._last_error = str(e)
            return False

    async def get_system_status(self) -> Optional[Tuple[bool, List[str]]]:
        """系统警告/告警状态 (SYST:STAT? §20.4.2.5)。

        覆盖 Input cut-off / Digital Clipping / Reference status / Unstable level。
        返回 "1" → (True, []); "0,<src1>,..." → (False, [srcs])。
        """
        if not self._visa_resource:
            return None
        try:
            raw = (await self._query("SYST:STAT?")).strip()
            parts = [p.strip() for p in raw.split(",")]
            if parts and parts[0] == "1":
                return (True, [])
            if parts and parts[0] == "0":
                return (False, [p for p in parts[1:] if p])
            return (False, [raw])  # 非预期格式: 当作有警告, 原样带出
        except Exception as e:
            logger.warning(f"[F64] get_system_status failed: {e}")
            return None

    async def get_group_clipping(
        self, group_num: int = 1, reset: bool = False
    ) -> Optional[float]:
        """通道组的平均 digital clipping, per-mille (GROup:CLIpping:GET? <g>,<reset>, §20.4.7.6)。

        per-mille = 削顶样本占比 (千分之)。reset=True 同时清零平均累计。
        avg+crest 超 ADC 满量程 → 这里非零 (闭环 verify 用)。
        """
        if not self._visa_resource:
            return None
        try:
            raw = (await self._query(
                f"GROup:CLIpping:GET? {group_num},{1 if reset else 0}"
            )).strip()
            return float(raw)
        except Exception as e:
            logger.warning(f"[F64] get_group_clipping({group_num}) failed: {e}")
            return None

    async def measure_rsrp(
        self,
        inputs: List[int],
        technology: str = "5G",
        bandwidth_mhz: int = 100,
        cell_id: int = 1,
        center_freq_mhz: float = 3500,
        scs_khz: int = 30
    ) -> Optional[float]:
        """
        内置 RSRP 测量功能。

        User Reference §20.4.4.53:
          INP:RSRP:MEAS? <N>,<inp1>,...,<inpN>,<tech>,<bw>,<cell>,<freq>[,<scs>]
          5G 参数: bandwidth_mhz (20/50/100), cell_id, center_freq_mhz, scs_khz

        注意: 测量通常需要 10-60 秒。

        Returns:
            RSRP in dBm, or None if failed
        """
        if not self._visa_resource:
            return None
        try:
            n = len(inputs)
            inp_str = ",".join(str(i) for i in inputs)
            cmd = f"INP:RSRP:MEAS? {n},{inp_str},{technology},{bandwidth_mhz},{cell_id},{center_freq_mhz}"
            if technology == "5G":
                cmd += f",{scs_khz}"

            # RSRP 测量需要较长超时
            result = await self._query(cmd, timeout=60000)
            rsrp_dbm = float(result.strip())
            logger.info(f"[F64] RSRP measurement: {rsrp_dbm} dBm")
            return rsrp_dbm
        except Exception as e:
            logger.error(f"[F64] measure_rsrp failed: {e}")
            return None

    async def set_output_phase(self, output_num: int, phase_deg: float) -> bool:
        """
        设置输出通道相位。

        User Reference §20.4.5.10:
          OUTP:PHA:DEG:CH <output>,<phase_degrees>
          取值范围: -200 ~ 200 度
        """
        if not self._visa_resource:
            return False
        try:
            await self._write(f"OUTP:PHA:DEG:CH {output_num},{phase_deg:.1f}")
            return True
        except Exception as e:
            self._last_error = str(e)
            return False

    async def get_output_calibration(
        self,
        output_num: int,
        *,
        retries: int = 3,
        retry_delay_s: float = 0.5,
    ) -> Optional[Dict[str, float]]:
        """
        获取输出通道校准数据 (含 not-ready 重试).

        User Reference §20.4.5.24:
          OUTP:CALIB:GET? <output>
          返回: <gain_dB>,<phase_degrees>

        紧接 autoset 后调用容易碰到 "not ready", retry 重试 retries 次,
        每次间 retry_delay_s; 全部 not-ready 或异常则 None.
        """
        if not self._visa_resource:
            return None
        raw = await self._query_with_retry(
            f"OUTP:CALIB:GET? {output_num}",
            retries=retries,
            delay_s=retry_delay_s,
        )
        if raw is None:
            return None
        try:
            parts = raw.split(",")
            return {
                "gain_db": float(parts[0]),
                "phase_deg": float(parts[1]) if len(parts) > 1 else 0.0,
            }
        except (ValueError, IndexError) as e:
            logger.error(f"[F64] get_output_calibration parse failed: {raw!r} ({e})")
            return None

    async def get_output_power(
        self,
        output_num: int,
        *,
        retries: int = 3,
        retry_delay_s: float = 0.5,
    ) -> Optional[float]:
        """
        获取输出功率测量值 (含 not-ready 重试).

        User Reference §20.4.5.22:
          OUTP:MEAS:RES:GET? <output>[,<option>]
          option 0: 基于输入功率计算 (legacy)
          option 1: 在输出端直接测量 (含内部干扰源)

        刚启动仿真 / 改路损 / autoset 后, F64 内部测量缓冲尚未填满会返回
        'not ready' — retry 多次后仍 not-ready 才放弃.

        ⚠ P1-21 ④ (2026-07-03 实证): 输出功率测量在仿真 **STOPPED 态冻结** —
        32 口同值 σ=0 的"合理数字", 不是当前实际 (输入侧测量族独立仍活)。
        停止态读数只可作最后运行时的快照参考; 消费方判 `_emulation_running`。
        """
        if not self._visa_resource:
            return None
        raw = await self._query_with_retry(
            f"OUTP:MEAS:RES:GET? {output_num}",
            retries=retries,
            delay_s=retry_delay_s,
        )
        if raw is None:
            return None
        try:
            return float(raw)
        except ValueError as e:
            logger.error(f"[F64] get_output_power parse failed: {raw!r} ({e})")
            return None

    async def set_input_phase(self, input_num: int, phase_deg: float) -> bool:
        """
        设置输入通道相位。

        User Reference §20.4.4.16:
          INP:PHA:DEG:CH <input>,<phase_degrees>
          取值范围: -200 ~ 200 度

        用于相位校准时补偿通道间的相位偏差。
        """
        if not self._visa_resource:
            return False
        try:
            await self._write(f"INP:PHA:DEG:CH {input_num},{phase_deg:.1f}")
            return True
        except Exception as e:
            self._last_error = str(e)
            return False

    async def enable_measurement_data_stream(
        self,
        target_ip: str,
        target_port: int = 3800,
        elements: Optional[Dict[int, int]] = None
    ) -> bool:
        """
        启用 UDP 测量数据推送流。

        User Reference §20.4.2.24 ~ §20.4.2.28:
          SYST:MEAS:TAR:SET 1,<port>,<ip>
          SYST:MEAS:ELE:SET <type>,<enable>,<interval_ms>

        元素类型:
          101=输入功率, 201=输出功率, 401=链路多普勒
          402=链路RSRP, 403=链路AoA, 404=链路AoD
        """
        if not self._visa_resource:
            return False
        try:
            # 设置目标
            await self._write(f"SYST:MEAS:TAR:SET 1,{target_port},{target_ip}")

            # 默认启用输入/输出功率, 100ms 间隔
            if elements is None:
                elements = {101: 100, 201: 100}

            for elem_type, interval_ms in elements.items():
                await self._write(f"SYST:MEAS:ELE:SET {elem_type},1,{interval_ms}")

            logger.info(f"[F64] Measurement stream enabled → {target_ip}:{target_port}")
            return True
        except Exception as e:
            logger.error(f"[F64] enable_measurement_data_stream failed: {e}")
            self._last_error = str(e)
            return False

    # ===================================================================
    # 6. 仪器基础信息 (InstrumentDriver 第一层)
    # ===================================================================

    async def get_metrics(self) -> InstrumentMetrics:
        """获取 F64 运行状态指标 (含逐通道功率)。

        F64R-2: 逐**真实输入口号** (`_active_input_ports`, 由 GROUP:INPUTS:GET? 回读)
        查 INP:MEAS:RES:GET? <i>; 逐**真实输出口号** (`_active_output_ports` = 探头)
        查 OUTP:MEAS:RES:GET? <i>。**不再用 _tx_antennas / tx×rx 猜**(tx×rx 是逻辑
        通道口径, OTA 下 ≠ 探头数), 也**不假定口号是 1..N**(可能非连续)。
        单路查询失败 (含 'not ready') 不影响
        其他路 — 该路记 None, 用 query_errors 累计错误以便 dashboard 区分
        "通道未就绪" 与 "整机故障".

        拓扑未知 (未加载 / 回读失败) 时**不猜口号去查**: 该组电平留空 dict 并在
        query_errors 里显式标注"跳过查询" —— 读操作降级但可见, 区别于 set_* 写操作的
        fail-loud (拿错口号写会真的配错硬件, 读只是没数)。
        """
        if not self._visa_resource:
            return InstrumentMetrics(
                timestamp=datetime.utcnow(),
                metrics={"error": "not connected"},
                status="error"
            )
        try:
            # F64R-2: **读路也要按需补回读**。写路 5 个消费方都会自愈, 而 broadcaster 每秒
            # 调的正是本方法 —— 后端重启后 (F64 仍加载着仿真在播) 若不补读, 逐口电平会恒
            # 为空 dict + "跳过查询", 直到操作员碰一次写端点才恢复。**监控面失明**比口数
            # 不全更糟: 现场判断输入参考/crest 生效与否就靠这块。
            # 热缓存零成本 (快路径直接 return); 真没加载时每秒多一条 STATE?。
            await self._ensure_topology(throttle=True)   # 唯一的高频轮询路
            metrics: Dict[str, Any] = {
                "channel_count": self._channel_count,
                "emulation_running": self._emulation_running,
                "pipeline": self._active_pipeline.value if self._active_pipeline else "none",
                "bypass_mode": self._bypass_mode.name,
                "loaded_file": self._loaded_emulation_file,
                # 声明式 MIMO 元数据 (上层 set_mimo_config 缓存的 tx/rx), F64R-2 起
                # **不再用于任何端口寻址** —— 端口一律用下面回读的真实拓扑。
                "tx_antennas": self._tx_antennas,
                "rx_antennas": self._rx_antennas,
                # F64R-2: 从**当前加载仿真**回读的真实拓扑 (MODEL:INFO?)。
                # None = 未加载 / 回读失败 (此时端口相关写操作会 fail-loud)。
                "active_inputs": self._active_inputs,
                "active_outputs": self._active_outputs,
                "active_channels": self._active_channels,
                # 真实端口**号**(可能非连续) —— 排"为什么某个探头没配上"时看这个
                "active_input_ports": self._active_input_ports,
                "active_output_ports": self._active_output_ports,
                # 口号来源: readback=仪器回读的真值 / declared=人工声明兜底(GROUP:* 读
                # 不到时) / unknown=都没有。**declared 时上面的口号是人填的, 不是仪器
                # 说的** —— 排障时别拿它当真值背书。
                "topology_source": self._topology_source(),
            }
            query_errors: List[str] = []

            # 输入电平: 逐**真实输入口号**查 (F64R-2, 不再用 _tx_antennas 猜, 也不假定 1..N)
            input_powers: Dict[int, Optional[float]] = {}
            # 先捕获成局部变量 (与下面输出侧同形态): get_metrics **不持锁**, 若在
            # `if` 与 `for` 之间另一协程走 load → _clear_topology() 置 None →
            # `for inp in None` TypeError, 被外层 except 吞成整块 metrics 消失、仪表盘闪断。
            in_ports_m = self._active_input_ports or []
            if in_ports_m:
                for inp in in_ports_m:
                    try:
                        raw = await self._query(f"INP:MEAS:RES:GET? {inp}")
                        raw_l = raw.strip().lower()
                        if not raw_l or "not ready" in raw_l:
                            input_powers[inp] = None
                        else:
                            input_powers[inp] = float(raw.strip())
                    except Exception as e:
                        input_powers[inp] = None
                        query_errors.append(f"input_{inp}: {e}")
            else:
                # 读操作**降级不 fail-loud** (区别于 set_* 写操作): 拓扑未知就不猜口号去查,
                # 但必须显式标注 —— 否则空 dict 会被读成"查了、没有电平", 而不是"没查"。
                query_errors.append(
                    "input_powers: 物理输入口未知 (仿真未加载 / 拓扑回读失败) — 跳过查询"
                )
            metrics["input_powers_dbm"] = input_powers

            # 输出电平: 逐**真实输出口号**(探头)查 (F64R-2, 不再用 tx×rx 猜)
            out_ports_m = self._active_output_ports or []
            if not out_ports_m:
                query_errors.append(
                    "output_powers: 物理输出口未知 (仿真未加载 / 拓扑回读失败) — 跳过查询"
                )
            output_powers: Dict[int, Optional[float]] = {}
            for out in out_ports_m:
                try:
                    raw = await self._query(f"OUTP:MEAS:RES:GET? {out}")
                    raw_l = raw.strip().lower()
                    if not raw_l or "not ready" in raw_l:
                        output_powers[out] = None
                    else:
                        output_powers[out] = float(raw.strip())
                except Exception as e:
                    output_powers[out] = None
                    query_errors.append(f"output_{out}: {e}")
            metrics["output_powers_dbm"] = output_powers
            # P1-21 ④: STOPPED 态输出测量冻结 (最后运行时快照, 非当前实际) —
            # cockpit / 监控消费方据此标注"停止态读数不可信", 输入侧不受影响。
            metrics["output_powers_frozen"] = not self._emulation_running

            if query_errors:
                metrics["query_errors"] = query_errors

            # 单路失败不降级整体状态 — 仿真在跑就是 normal
            return InstrumentMetrics(
                timestamp=datetime.utcnow(),
                metrics=metrics,
                status="normal" if self._emulation_running else "idle"
            )
        except Exception as e:
            logger.error(f"[F64] get_metrics failed: {e}")
            return InstrumentMetrics(
                timestamp=datetime.utcnow(),
                metrics={"error": str(e)},
                status="error"
            )

    async def get_capabilities(self) -> List[InstrumentCapability]:
        """返回 F64 支持的能力列表 (含 *OPT? 探测出的 license-aware 能力).

        非 license 能力 (Channel Emulation / GCM / Runtime / RSRP / Bypass)
        是 F64 出厂内置, 无条件声明. license 能力 (Internal Interference
        Generator) 取决于 *OPT? 探测结果, supported 字段反映实际状态.
        """
        caps: List[InstrumentCapability] = [
            InstrumentCapability(
                name="Channel Emulation",
                description=f"Up to {self._channel_count} fading channels",
                supported=True,
                parameters={"max_channels": self._channel_count}
            ),
            InstrumentCapability(
                name="GCM Native Pipeline",
                description="Channel Studio built-in GCM model compilation",
                supported=True
            ),
            InstrumentCapability(
                name="Runtime Emulation",
                description="External ASC/RTC waveform playback with dynamic environment control",
                supported=True
            ),
            InstrumentCapability(
                name="RSRP Measurement",
                description="Built-in LTE/5G RSRP measurement at inputs",
                supported=True,
                parameters={"technologies": ["LTE", "5G"]}
            ),
            InstrumentCapability(
                name="Calibration Bypass",
                description="3 bypass modes: Channel Model, Butler, Calibration",
                supported=True
            ),
        ]

        # License-aware: Internal Interference Generator (CW tone source).
        # has_interference_generator 在 connect() 时由 *OPT? 探测填充
        # (None = 探测前 / 探测失败, 当作不可用).
        caps.append(
            InstrumentCapability(
                name="Internal Interference Generator",
                description="Optional license for internal CW/noise tone "
                            "injection (calibration D path)",
                supported=bool(self.has_interference_generator),
                parameters={
                    "license_status": (
                        "licensed" if self.has_interference_generator
                        else "not_licensed"
                    ),
                    "matched_options": [
                        opt for opt in self._installed_options
                        if opt.upper() in INTERFERENCE_GEN_OPTION_TOKENS
                    ],
                },
            )
        )

        # 透明声明所有 *OPT? 探测出的选件 — 上层 (lab dashboard / commissioning
        # 报告) 能直接看到这台 F64 装了哪些 license, 不需要再额外查询.
        caps.append(
            InstrumentCapability(
                name="Installed Options",
                description=f"{len(self._installed_options)} license token(s) "
                            f"reported by *OPT?",
                supported=bool(self._installed_options),
                parameters={"options": list(self._installed_options)},
            )
        )

        return caps

    async def reset(self) -> bool:
        """
        重置 F64 到安全状态。

        IEEE 488.2 §10.32:
          *RST — 重置仪器
        User Reference §20.4.2.3:
          SYST:RES — 系统重置, 关闭仿真
        """
        if not self._visa_resource:
            return False
        try:
            await self._write("*RST")
            # *RST 已发 → 仪器必复位 (关闭旧仿真)。会话级全清 6 字段**立即**执行 (Codex #223:
            # clear-on-issue 非 clear-on-confirm —— 即使后续 *OPC? 超时也不残留 stale identity;
            # *RST write 本身抛=未发出, 才由 except 保留)。
            self._apply_session_reset()
            await self._query("*OPC?", timeout=VISA_TIMEOUT_FILE_LOAD)
            self._status = InstrumentStatus.READY
            logger.info("[F64] Reset complete")
            return True
        except Exception as e:
            logger.error(f"[F64] reset failed: {e}")
            self._last_error = str(e)
            return False

    # ===================================================================
    # 7. 内部工具方法
    # ===================================================================
    #
    # Only _do_write / _do_query are defined here — the base class's
    # _write / _query template methods handle async _do_* transparently
    # (see base.InstrumentDriver._query for the dispatch). Driver code
    # calls ``await self._query(...)`` because our _do_query is async.
    # ===================================================================

    # ── Connection-loss-aware retry (PyVISA equivalent of Aerotech #14) ─
    #
    # PyVISA surfaces dropped sockets as ``VisaIOError`` with one of two
    # status codes:
    #   - ``VI_ERROR_CONN_LOST`` (0xBFFF00B5) — TCP RST / FIN seen
    #   - ``VI_ERROR_INV_OBJECT`` (0xBFFF000E) — session handle dead
    # ``VI_ERROR_TMO`` (0xBFFF0015) is also a VisaIOError BUT means
    # "device too slow", NOT "connection broken" — same lesson as the
    # Aerotech Codex P2 (timeout != reconnect trigger). We explicitly
    # whitelist the two conn-lost codes and let everything else (timeout,
    # syntax errors, etc.) propagate.
    #
    # Reconnect strategy: close + reopen the VISA resource with the same
    # resource string. F64's SCPI state lives in the controller, not in
    # the socket — most state survives reconnect. The session-specific
    # bits (active alignment, queued errors) we don't re-issue here; if
    # the operator needs a hard reset they should call connect() again.

    @staticmethod
    def _is_visa_conn_lost(exc: BaseException) -> bool:
        """Delegate to the shared classifier so all VISA-backed drivers
        agree on which error codes mean 'reconnect to recover'."""
        from app.hal._visa_reconnect import is_visa_conn_lost
        return is_visa_conn_lost(exc)

    async def _silent_reconnect_visa(self) -> bool:
        """Reopen the VISA resource after a connection drop.

        Returns True on success. Best-effort closes the half-dead
        resource, then ``rm.open_resource`` again with the same string
        and timeout. We do NOT re-run ``connect()`` (which would issue
        ``*IDN?`` + ``SYST:INFO?`` + alignment reload — heavy + state-
        mutating); SCPI device state survives a TCP reconnect, so the
        bare resource is enough for the in-flight command to succeed.
        """
        if self._rm is None or not self.ip_address:
            return False
        # Tear down the broken resource. ``close()`` on a dead session
        # can itself raise — swallow, the underlying socket is gone.
        try:
            if self._visa_resource is not None:
                await asyncio.to_thread(self._visa_resource.close)
        except Exception:
            pass
        self._visa_resource = None

        try:
            resource_string = f"TCPIP0::{self.ip_address}::{self.port}::SOCKET"
            self._visa_resource = await asyncio.to_thread(
                self._rm.open_resource,
                resource_string,
                read_termination='\n',
                write_termination='\n',
                timeout=VISA_TIMEOUT_DEFAULT,
            )
            logger.info(
                f"[F64] silent reconnect succeeded — resource reopened "
                f"({resource_string})"
            )
            return True
        except Exception as e:
            logger.error(f"[F64] silent reconnect failed: {e}")
            self._visa_resource = None
            return False

    async def _do_write(self, cmd: str, timeout: Optional[int] = None) -> None:
        """发送 SCPI 写命令（由基类 _write() 自动调用，SCPI 日志已由基类记录）。

        P1-21 ①: 全部 SCPI IO 过 per-driver `_scpi_lock` — monitoring
        broadcaster (1s 循环 32+ 查询) 与测量序列共用单 socket, 无互斥并发
        = 应答串线/错位/僵死 (2026-07-03 现场 P1 根因)。锁同时消掉
        `_visa_resource.timeout` 属性覆盖/恢复的竞态。
        P1-21 ②: 超时 (VI_ERROR_TMO) 后在锁内做轻量排水 (SYST:ERR? 循环,
        会话恢复干净), 原异常照样上抛 — 调用方知道该命令失败, 但下一条
        命令不再读到迟到应答; 排水失败才需要上层重载。
        """
        async with self._scpi_lock:
            try:
                await self._do_write_unlocked(cmd, timeout)
            except Exception as e:
                if self._is_visa_timeout(e):
                    await self._drain_after_timeout(cmd)
                raise

    async def _do_query(self, cmd: str, timeout: Optional[int] = None) -> str:
        """发送 SCPI 查询命令并返回响应 — 互斥/排水语义同 `_do_write`。"""
        async with self._scpi_lock:
            try:
                return await self._do_query_unlocked(cmd, timeout)
            except Exception as e:
                if self._is_visa_timeout(e):
                    await self._drain_after_timeout(cmd)
                raise

    @staticmethod
    def _is_visa_timeout(exc: BaseException) -> bool:
        from app.hal._visa_reconnect import is_visa_timeout
        return is_visa_timeout(exc)

    async def _drain_after_timeout(self, timed_out_cmd: str) -> bool:
        """超时后轻量恢复 (P1-21 ②; #199/#202/#203 三轮收敛的两步式终态)。

        两步重对齐:
        1. **裸 read** (不发新查询) 短超时循环吃掉迟到应答 — query 是
           write+read, 会话一旦错位每次读到的都是前一条的应答, "连续 N 条
           clean"判定在错位链上不收敛 (每条都合法 clean, Codex #203 R2);
           只有不 write 的裸 read 能消耗多余应答: 读到 = 吃掉一拍,
           读超时 = 无残留、已对齐。
        2. SYST:ERR? 清错误队列 (已对齐, 读到的就是本查询的应答), 读到
           0,"No error" 即净 (#199: 只认可解析形态, 防 "0.0" 类杂音),
           上限 4 条 (2026-07-03 实测 2 条即净)。

        全程已持 _scpi_lock (由 _do_write/_do_query 调用)。失败只记日志 —
        原始超时异常由调用方上抛, 这里不再抛。
        """
        try:
            for _ in range(4):
                try:
                    original = self._visa_resource.timeout
                    self._visa_resource.timeout = 2000
                    try:
                        stale = await asyncio.to_thread(self._visa_resource.read)
                    finally:
                        self._visa_resource.timeout = original
                    logger.info(
                        f"[F64] 排水: 吃掉迟到应答 {str(stale).strip()[:60]!r}"
                    )
                except Exception:
                    break  # 读超时 = 无更多残留应答, 会话已对齐
            for i in range(4):
                resp = (await self._do_query_unlocked("SYST:ERR?", timeout=2000)).strip()
                if re.match(r'^\+?0\s*,\s*"?no error', resp, re.IGNORECASE):
                    logger.warning(
                        f"[F64] 超时排水完成 (残留已清 + {i + 1} 条 ERR) — 会话已净 "
                        f"(超时命令: {timed_out_cmd[:40]!r})"
                    )
                    return True
            logger.error("[F64] 超时排水仍未净 — 会话可能错位, 建议重载驱动")
        except Exception as drain_e:  # noqa: BLE001
            logger.error(
                f"[F64] 超时排水失败 ({type(drain_e).__name__}: {drain_e}) — "
                f"会话可能错位, 建议重载驱动"
            )
        return False

    async def _do_write_unlocked(self, cmd: str, timeout: Optional[int] = None) -> None:
        """实际写 IO (锁内)。conn-lost 一次静默重连重试; 其余异常原样上抛。"""
        for attempt in (0, 1):
            if timeout:
                original_timeout = self._visa_resource.timeout
                self._visa_resource.timeout = timeout
            try:
                await asyncio.to_thread(self._visa_resource.write, cmd)
                return
            except Exception as e:
                if attempt == 0 and self._is_visa_conn_lost(e):
                    logger.warning(
                        f"[F64] VISA connection lost on write '{cmd[:40]}...' "
                        f"({type(e).__name__}: code=0x{getattr(e, 'error_code', 0) & 0xFFFFFFFF:08X}) — "
                        f"silent reconnect"
                    )
                    if await self._silent_reconnect_visa():
                        continue  # retry once with fresh session
                raise
            finally:
                if timeout and self._visa_resource is not None:
                    try:
                        self._visa_resource.timeout = original_timeout
                    except Exception:
                        pass

    async def _do_query_unlocked(self, cmd: str, timeout: Optional[int] = None) -> str:
        """实际查询 IO (锁内) — retry 语义同 `_do_write_unlocked`。"""
        for attempt in (0, 1):
            if timeout:
                original_timeout = self._visa_resource.timeout
                self._visa_resource.timeout = timeout
            try:
                response = await asyncio.to_thread(self._visa_resource.query, cmd)
                return response
            except Exception as e:
                if attempt == 0 and self._is_visa_conn_lost(e):
                    logger.warning(
                        f"[F64] VISA connection lost on query '{cmd[:40]}...' "
                        f"({type(e).__name__}: code=0x{getattr(e, 'error_code', 0) & 0xFFFFFFFF:08X}) — "
                        f"silent reconnect"
                    )
                    if await self._silent_reconnect_visa():
                        continue
                raise
            finally:
                if timeout and self._visa_resource is not None:
                    try:
                        self._visa_resource.timeout = original_timeout
                    except Exception:
                        pass
        # Unreachable: the loop either returns or re-raises.
        return ""


    # _check_errors (drain + WARNING + 写 _last_error, 无判定无上界) 已退役
    # (R10 平行族收口 2026-07-04): 它的"只 log 不改控制流"是 11 个方法假成功
    # 的根源。查询→drain 用 _drain_errors (静默有界), 写→判定用 _first_error
    # / _gated_write_transaction。不要恢复此函数。

    async def _gated_write_transaction(self, label: str, commands: List[str]) -> bool:
        """锁事务: drain → 依序写 → _first_error 门。被拒 → False + 响亮日志。

        Codex #202 R10 平行族正修: 9 个参数设置方法原是"写 → _check_errors
        (只 log) → return True"— SCPI 拒绝 (-113/-222 等只进错误队列不抛异常)
        时假成功, 参数没生效上层却继续跑。收敛到本 helper: 失败写 _last_error
        + logger.error (经 JsonFormatter 落 logs/*.jsonl → /system-logs/tail
        → GUI Dashboard 日志面板, 操作员可见), 调用方拿 False 自行 fail-loud。
        """
        async with self._scpi_lock:
            await self._drain_errors()  # 门只评估本次写序列的错误
            for cmd in commands:
                await self._write(cmd)
            err = await self._first_error()
            if err is not None:
                self._last_error = f"{label} rejected: {err}"
                logger.error(
                    f"[F64] {label} 被拒 (SYST:ERR?): {err} — 参数未生效"
                )
                return False
        return True

    async def _first_error(self) -> Optional[str]:
        """查询 SYST:ERR?, 返回第一条真错误字符串; 无错返回 None。

        与 ``_check_errors`` (drain + log, 不影响控制流) 不同 —— 本方法供
        fail-loud gate 使用: 把错误返回给调用方判定 (例如加载失败立刻 return
        False)。F64 即便文件缺失/损坏 (或早期错端口) 也会对 *OPC? 答 "1", 唯一
        可靠的失败信号是 SYST:ERR? (-200 "No simulation opened" / -300)。
        """
        err = (await self._query("SYST:ERR?")).strip()
        code_str = err.split(",", 1)[0].strip()
        try:
            if int(code_str) == 0:
                return None
        except ValueError:
            pass
        if "No error" in err:
            return None
        return err

    async def _drain_errors(self) -> List[str]:
        """清空 SYST:ERR? 队列, 返回被清掉的真错误 (供日志); **不改** self._last_error。

        用于在会 fail-loud gate 的操作 (如加载) *之前* 清掉历史/前序命令遗留的队列项,
        确保之后的 gate 只评估本次操作产生的错误 (Codex on PR #93)。与 _check_errors
        (drain + WARNING + 写 _last_error) 的区别: 本方法静默清队列、不污染 _last_error。
        有界 (防 misbehaving 仪器死循环)。
        """
        drained: List[str] = []
        try:
            for _ in range(64):  # 正常队列 0-数条; 上界防御
                err = (await self._query("SYST:ERR?")).strip()
                code_str = err.split(",", 1)[0].strip()
                try:
                    is_clean = int(code_str) == 0
                except ValueError:
                    is_clean = "No error" in err
                if is_clean:
                    break
                drained.append(err)
            if drained:
                # agent F6: 本方法被 load×2/GO/GOS/STATIC 五个事务复用,
                # 文案不再写"加载前"以免排障读日志时误导时序
                logger.info("[F64] 事务前清空 %d 条遗留错误: %s", len(drained), drained)
        except Exception as e:
            logger.warning("[F64] drain errors failed: %s", e)
        return drained

    def _update_user_alignment_capability(self) -> None:
        """Mirror ``self._active_alignment`` into the canonical capability
        set (Codex P2 on PR #21).

        Called from ``connect()`` after each ``_active_alignment`` refresh
        so ``ce.user_alignment`` reflects runtime state, not just the
        token's presence in the vocabulary. Semantic: the token is set
        IFF this F64 currently has an active user alignment loaded —
        i.e. the SYST:CALIB:USER:SET 1,<name> handshake produced a row
        with a non-empty ``alignment_name``.

        Without this, P1-1's plan pre-flight would reject every step
        that ``needs: ["ce.user_alignment"]`` even on an F64 that
        actually has alignment active (the token sat in
        KNOWN_CAPABILITIES but no code ever populated it — exactly the
        speculative-vocabulary drift the module-level docstring warns
        against).
        """
        from app.hal.capabilities import CE_USER_ALIGNMENT

        has_active = bool(
            self._active_alignment
            and self._active_alignment.get("alignment_name")
        )
        if has_active:
            self._add_capability(CE_USER_ALIGNMENT)
        else:
            self._remove_capability(CE_USER_ALIGNMENT)

    async def _apply_discovered_capabilities(self, options: List[str]) -> None:
        """*OPT? 解析出的 token → has_interference_generator.

        Override base no-op. config 里显式给值时不覆盖 (尊重运维 / mock 决定).
        Token 匹配大小写不敏感, 候选见 INTERFERENCE_GEN_OPTION_TOKENS.
        """
        if self._explicit_interference_gen:
            return
        upper = {opt.upper() for opt in options}
        self.has_interference_generator = bool(
            upper & INTERFERENCE_GEN_OPTION_TOKENS
        )
        # P2-2: mirror to canonical capability set. New consumers should
        # read `driver.capabilities`; the legacy bool is kept for current
        # call sites + tests that already assert against it.
        from app.hal.capabilities import CE_INTERFERENCE_GENERATOR
        if self.has_interference_generator:
            self._add_capability(CE_INTERFERENCE_GENERATOR)
        else:
            self._remove_capability(CE_INTERFERENCE_GENERATOR)
        logger.info(
            f"[F64] Interference Generator license: "
            f"{self.has_interference_generator} (probed from {options or '(empty)'})"
        )

    # ──────────────────────────────────────────────────────────────────
    # F64-specific replacement for *OPT?
    # ──────────────────────────────────────────────────────────────────
    #
    # Verified CAICT 2026-05-13 (memory ``project_f64_ate_server_capabilities``):
    # the F64 ATE Server doesn't implement ``*OPT?`` — it answers
    # ``-100,"ATE command not supported"``. The base class default
    # therefore got nothing and ``_apply_discovered_capabilities`` always
    # received an empty list, silently setting ``has_interference_generator``
    # to False even on units that have the K01 license. Operators then
    # had to manually set ``config['has_interference_generator']`` to
    # work around the failure.
    #
    # The override below replaces ``*OPT?`` with a two-source probe:
    #
    #   (a) **SYST:INFO? keyword scan** — SYST:INFO? is the one
    #       confirmed-working introspection query on F64; its text
    #       contains free-form capability hints. We scan for known
    #       license-related keywords and emit canonical tokens. Cheap
    #       and never NAKs (the command itself works).
    #
    #   (b) **Soft feature probes** — for each option we care about,
    #       send a single read-only SCPI that's gated by the same
    #       license as the feature. If the controller answers, the
    #       license is installed; if it NAKs with -100/-113, the
    #       license is absent. Probes are NEVER write commands and
    #       NEVER mutate device state.
    #
    # Adding a new license check is one row in ``_F64_OPTION_PROBES``.
    # Each entry has a clear ``why`` so the next engineer doesn't have
    # to guess what feature the probe gates.
    #
    # The exact SCPI for each soft probe needs on-site verification
    # against the F64 firmware — comments below mark each entry's
    # provenance. If a probe turns out wrong, the worst case is a
    # false-negative (option not detected, operator falls back to
    # explicit config), never a false-positive.

    # (canonical_token, probe_scpi, rationale).
    # canonical_token is the value that lands in self._installed_options;
    # _apply_discovered_capabilities then maps it onto has_*  flags.
    _F64_OPTION_PROBES: List[tuple] = [
        # CAICT to-verify: OUTPut:INTERFerence:LIST? — read-only query
        # for currently-defined interferer ids. Expected to NAK with
        # -100 when the K01 (Internal Interference Generator) license
        # is missing, ACK (possibly with empty/0 payload) when present.
        # Token "INT-GEN" matches INTERFERENCE_GEN_OPTION_TOKENS.
        ("INT-GEN", "OUTPut:INTERFerence:LIST?",
         "K01 Interference Generator — gates set_calibration_tone()"),
        # SYSTem:CALibration:USER:LIST? — read-only query for stored
        # user-alignment names. Should NAK without the User Alignment
        # license; ACK (CSV or empty) when present.
        ("USER-ALIGN", "SYSTem:CALibration:USER:LIST?",
         "Integrated Setup Calibration (user alignment) license"),
    ]

    # Keyword → canonical token. Used by SYST:INFO? scan. All lower-case;
    # match is substring on the lower-cased SYST:INFO? response.
    _F64_SYSTINFO_KEYWORDS: Dict[str, str] = {
        "interference": "INT-GEN",
        "int-gen": "INT-GEN",
        "int_gen": "INT-GEN",
        "calibration user": "USER-ALIGN",
        "user alignment": "USER-ALIGN",
    }

    @staticmethod
    def _looks_like_unsupported_payload(response: str) -> bool:
        """Delegate to module-level helper so subclasses / tests share
        the same SCPI-error-payload detection logic. See module docstring
        on ``_is_unsupported_error_payload`` for the shapes recognised."""
        return _is_unsupported_error_payload(response)

    async def _probe_installed_options(self) -> List[str]:
        """F64-specific replacement for the base class ``*OPT?`` probe.

        Returns a list of canonical option tokens. Failure to detect an
        option (probe NAKs / SYST:INFO? missing keyword) is treated as
        "license absent" — safer default than assuming installed.

        Never raises; SYST:INFO? failure is logged + scan skipped, soft-
        probe failures are silently treated as "feature absent".
        """
        discovered: List[str] = []
        seen: set = set()

        # Step (a): SYST:INFO? keyword scan. SYST:INFO? is the confirmed-
        # working introspection query (returns the channel-count line we
        # already parse in connect() — see propsim_f64.py:257-266).
        try:
            info_raw = await self._query("SYST:INFO?")
            info_lower = (info_raw or "").lower()
            for keyword, token in self._F64_SYSTINFO_KEYWORDS.items():
                if keyword in info_lower and token not in seen:
                    discovered.append(token)
                    seen.add(token)
        except Exception as e:
            logger.warning(
                f"[F64] SYST:INFO? license scan failed: {e}",
                extra={"instrument_id": self.instrument_id},
            )

        # Step (b): soft feature probes. One round-trip per option;
        # don't propagate per-probe failures so a missing license can't
        # block startup.
        for token, probe_cmd, rationale in self._F64_OPTION_PROBES:
            if token in seen:
                continue
            try:
                response = await self._query(probe_cmd)
            except Exception:
                # NAK raised / transient I/O — treat as "license absent"
                # without spamming the log. The probe table is the
                # source of truth for what's expected to fail.
                continue
            if response is None:
                continue
            # CRITICAL: F64 sometimes returns the SCPI error payload
            # ``-100,"ATE command not supported"`` as the response
            # string instead of raising. (Codex P1 review on PR #15 —
            # the same controller behaviour the categoriser in
            # propsim_f64_health._categorize_status already maps to
            # UNSUPPORTED.) Without this guard we'd credit a license
            # that's actually missing and later send OUTPut:INTERFerence:*
            # commands the controller has already said it doesn't
            # implement.
            if self._looks_like_unsupported_payload(response):
                logger.debug(
                    f"[F64] feature probe '{probe_cmd}' returned SCPI "
                    f"error payload {response.strip()!r} → {token} absent"
                )
                continue
            discovered.append(token)
            seen.add(token)
            logger.debug(
                f"[F64] feature probe '{probe_cmd}' → {token} ({rationale})"
            )

        self._installed_options = discovered
        logger.info(
            f"[F64] installed options (feature-probed, not *OPT?): "
            f"{discovered or '(none)'}",
            extra={"instrument_id": self.instrument_id},
        )
        return discovered

    async def _query_with_retry(
        self,
        cmd: str,
        *,
        retries: int = 3,
        delay_s: float = 0.5,
    ) -> Optional[str]:
        """SCPI 查询 + not-ready / 异常重试.

        F64 在测量缓冲尚未填满时返回 'not ready' 字符串. 紧接 autoset / 仿真
        启动 / 路损改动后调用 OUTP:MEAS:RES:GET? / OUTP:CALIB:GET? 容易碰
        到. 这个 helper 把"重试 N 次, 每次间隔 delay_s"的样板封掉.

        Returns:
            stripped response 字符串 — 成功;
            None — 全部重试都 not-ready / 异常.
        """
        for attempt in range(retries):
            try:
                raw = await self._query(cmd)
                stripped = raw.strip()
                if not stripped or "not ready" in stripped.lower():
                    if attempt + 1 < retries:
                        logger.debug(
                            f"[F64] {cmd}: not ready, retry "
                            f"{attempt + 1}/{retries} in {delay_s}s"
                        )
                        await asyncio.sleep(delay_s)
                        continue
                    logger.warning(
                        f"[F64] {cmd}: not ready after {retries} attempts"
                    )
                    return None
                return stripped
            except Exception as e:
                if attempt + 1 < retries:
                    logger.warning(
                        f"[F64] {cmd} failed (attempt {attempt + 1}/{retries}): {e}"
                    )
                    await asyncio.sleep(delay_s)
                else:
                    logger.error(
                        f"[F64] {cmd} failed after {retries} attempts: {e}"
                    )
                    return None
        return None

    async def _clear_error_queue(self) -> None:
        """连接后清空全部历史错误"""
        try:
            for _ in range(100):  # 最多读 100 条防止死循环
                err = await self._query("SYST:ERR?")
                if err.strip().startswith("0"):
                    break
        except Exception:
            pass

    async def _ftp_upload_directory(
        self,
        local_dir: str,
        remote_dir: str
    ) -> List[str]:
        """
        通过 FTP 将整个目录上传到 F64。

        F64 内置 Windows 操作系统, 支持标准 FTP 协议。
        出厂默认账户: PROPSIM / propsim (User Reference §1.2.5.1)

        Args:
            local_dir: 本地目录路径
            remote_dir: F64 上的目标目录 (e.g., "D:\\User Emulations\\ASC\\CDL-A")

        Returns:
            成功上传的文件名列表
        """
        transferred = []
        try:
            def _do_ftp():
                ftp = ftplib.FTP(self.ip_address)
                ftp.login(self.ftp_user, self.ftp_pass)
                # 确保远程目录存在
                try:
                    ftp.mkd(remote_dir.replace("\\", "/"))
                except ftplib.error_perm:
                    pass  # 目录已存在
                ftp.cwd(remote_dir.replace("\\", "/"))

                for filename in os.listdir(local_dir):
                    filepath = os.path.join(local_dir, filename)
                    if os.path.isfile(filepath):
                        with open(filepath, 'rb') as f:
                            ftp.storbinary(f"STOR {filename}", f)
                        transferred.append(filename)
                        logger.debug(f"[F64/FTP] Uploaded: {filename}")
                ftp.quit()

            await asyncio.to_thread(_do_ftp)
        except Exception as e:
            logger.error(f"[F64/FTP] Upload failed: {e}")
        return transferred


# ======================================================================
# Legacy Controller 兼容层
# (用于 channel_generation 模块的 GCM/ASC Strategy 类, 后续版本将迁移到上面的 Driver)
# ======================================================================

class PropsimF64Controller:
    """
    Keysight PROPSIM F64 旧版控制器 (兼容 channel_generation strategies)

    提供简化的方法接口供 PropsimNativeGCMStrategy 和 MimoEngineASCStrategy 调用。
    内部委托给 RealPropsimF64Driver 或使用 Mock 逻辑。

    注意: 此类将在下个版本废弃, 请使用 RealPropsimF64Driver。
    """

    def __init__(self, ip_address: str = "192.168.100.21"):
        self.ip_address = ip_address
        logger.info(f"Initialized PROPSIM F64 Controller (Legacy) at {self.ip_address}")

    def load_gcm_project(self, channel_model_name: str) -> bool:
        """Pipeline A: 触发 GCM 原生加载"""
        logger.info(f"[HAL: F64-GCM] Loading native GCM preset: {channel_model_name}")
        return True

    def transfer_file(self, local_zip_path: str) -> str:
        """Pipeline B: FTP 传输波形文件到 F64"""
        logger.info(f"[HAL: F64-FTP] Transferring {local_zip_path} to {self.ip_address}")
        remote_path = f"{F64_WAVEFORM_DIR}\\custom_asc_payload.zip"
        return remote_path

    def load_runtime_emulation_data(self, remote_file_path: str) -> bool:
        """Pipeline B: 加载 Runtime Emulation 数据"""
        logger.info(f"[HAL: F64-RUNTIME] Loading RTC from {remote_file_path}")
        return True

    def trigger_playback(self) -> None:
        """两种管线共用: 开始仿真"""
        logger.info("[HAL: F64] Triggering emulation playback")
