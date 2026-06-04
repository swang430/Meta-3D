"""P2-11 Phase 2: GCM .smu TestCase-驱动门 (单一真值源 fail-loud)。

正式测试 (路径 B) 的 GCM 模式必须由 TestCase 显式驱动 F64 的 .smu 仿真文件, 不能
静默 fallback 到 F64 驱动默认 .smu —— 默认文件频率可能跟 TestCase 错配 (见
docs/architecture/testcase-driven-instrument-config.md 路径 A/B 切分)。本门把这个
决策抽成纯函数, measure phase 在 GCM 分支调用。

跟 P1-8/9 (cal/dut) 同族的 silent-failure 防护; mock-aware 跟 precheck 门一致
(Codex on PR #75): 门只对真 F64 生效, 判定读 LIVE HAL。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# action 取值 (measure 据此决定放行 / FAIL / 降级 warning)
GATE_PROCEED = "proceed"               # 放行: TestCase 指定了 .smu, 或 mock/缺失 N/A
GATE_FAIL = "fail"                     # strict FAIL: 真 F64 + GCM + 未指定 .smu
GATE_WARN_FALLBACK = "warn_fallback"   # opt-out: 用 F64 驱动默认 .smu, 需 warning

_FAIL_MESSAGE = (
    "P2-11 Phase 2: engine_mode=keysight_gcm 但 TestCase 未指定 emulation_file → "
    "会 fallback 到 F64 驱动默认 .smu, 频率可能跟 TestCase 错配。请在 TestCase 显式"
    "指定 emulation_file, 或设 precheck_strict_emulation_file=False 走 bring-up "
    "默认 (路径 A)。"
)

_WARN_MESSAGE = (
    "P2-11: GCM 未指定 emulation_file → fallback F64 驱动默认 .smu "
    "(precheck_strict_emulation_file=False, bring-up 路径 A)"
)

# P2-12 (Codex #120 后端另一半): GCM 原生加载只认 .smu (Scenario/Channel Studio
# 文件)。.rtc=Runtime 管线 / .asc=ASC 引擎 都不是 GCM 原生文件 —— 指定它们给 GCM
# 是明确配置错误, 真 F64 信道加载才运行时失败。前端 #120 已 filter type=='smu', 但
# API 直传 / 绕过前端仍会进来, 这是同族防御深度的后端门。
_GCM_REQUIRED_EXT = ".smu"

_EXT_FAIL_MESSAGE = (
    "P2-12: engine_mode=keysight_gcm 只接受 .smu 仿真文件 (GCM 原生加载), 但 "
    "emulation_file={file!r} 扩展非 .smu (.rtc=Runtime 管线 / .asc=ASC 引擎) → "
    "F64 GCM 信道加载会运行时失败。请改用 .smu, 或设 "
    "precheck_strict_emulation_file=False 走 bring-up 放行。"
)

_EXT_WARN_MESSAGE = (
    "P2-12: GCM emulation_file={file!r} 扩展非 .smu "
    "(precheck_strict_emulation_file=False 放行), F64 运行时可能加载失败。"
)


def _has_required_ext(emulation_file: str) -> bool:
    """emulation_file 扩展是否 .smu (大小写不敏感)。GCM 原生加载的唯一合法扩展。"""
    return emulation_file.lower().endswith(_GCM_REQUIRED_EXT)


@dataclass(frozen=True)
class EmulationFileGateDecision:
    """GCM .smu 门决策。action ∈ {proceed, fail, warn_fallback}; message 供 FAIL/warn。"""

    action: str
    message: Optional[str] = None

    @property
    def should_fail(self) -> bool:
        return self.action == GATE_FAIL

    @property
    def should_warn(self) -> bool:
        return self.action == GATE_WARN_FALLBACK


def evaluate_emulation_file_gate(
    *,
    emulator_is_real: bool,
    emulation_file: Optional[str],
    strict: bool,
) -> EmulationFileGateDecision:
    """决定 GCM 模式下 measure 是否放行 .smu 配置 (仅在 engine_mode=GCM 时调用)。

    决策表 (按优先级):
    1. mock/缺失仿真器 (emulator_is_real=False) → PROCEED (N/A, 不加载真 .smu)。
    2. TestCase 指定了 emulation_file:
       2a. 扩展是 .smu → PROCEED (路径 B, 透传给 F64)。
       2b. 扩展非 .smu (.rtc/.asc) + strict → FAIL (GCM 只认 .smu; Codex #120
           后端另一半, 抓 API 直传 / 绕过前端 filter 的非 .smu)。
       2c. 扩展非 .smu + opt-out → WARN_FALLBACK (bring-up 放行, 运行时可能失败)。
    3. 真 F64 + 未指定 + strict → FAIL (不静默 fallback 驱动默认)。
    4. 真 F64 + 未指定 + opt-out → WARN_FALLBACK (路径 A bring-up 用驱动默认)。

    扩展校验天然 mock-aware: emulator_is_real=False 在第 1 条已 PROCEED, 不进
    2b/2c (mock 不真加载, 错扩展运行时不会失败)。校验对象是 caller 传入的
    resolved_emulation_file → 覆盖 scd_id resolve 出的 .smu 和裸 emulation_file 两路。

    注意 emulation_file 为空串也视作"未指定"(`not emulation_file`), 避免空串静默
    选中 fallback 路径却假装是 TestCase 驱动。
    """
    if not emulator_is_real:
        return EmulationFileGateDecision(GATE_PROCEED)
    if emulation_file:
        # P2-12: 指定了文件 → 先校验扩展 (GCM 只认 .smu)。strict 提前 FAIL,
        # opt-out 降级 warn (尊重 bring-up bypass 开关, 同 feedback_strict_gate_*)。
        if not _has_required_ext(emulation_file):
            if strict:
                return EmulationFileGateDecision(
                    GATE_FAIL, message=_EXT_FAIL_MESSAGE.format(file=emulation_file)
                )
            return EmulationFileGateDecision(
                GATE_WARN_FALLBACK,
                message=_EXT_WARN_MESSAGE.format(file=emulation_file),
            )
        return EmulationFileGateDecision(GATE_PROCEED)
    if strict:
        return EmulationFileGateDecision(GATE_FAIL, message=_FAIL_MESSAGE)
    return EmulationFileGateDecision(GATE_WARN_FALLBACK, message=_WARN_MESSAGE)
