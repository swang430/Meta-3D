"""SIM 身份核对 (P2-13 Phase 2: 防插错卡)。

attach 记录的 IMSI vs TestCase 选中的 SIMProfile 声明 IMSI 比 —— 不一致 = 实际 attach 的卡
跟 TestCase 选的卡对不上 (插错卡 / attach 时 IMSI 敲错), 测的不是预期那张卡, 结果无意义。

本阶段比的是 dut_attach.imsi (attach 时记录) vs SIMProfile.imsi (声明)。未来档 A (UXM 上报
真·实测认证 IMSI) 接上后, 同一核对器可换成"实测协商 IMSI vs 声明"。

IMSI 是 PII: 结果里只存脱敏 (前 8 位 = MCC+MNC+MSIN 头, 够定位是哪张卡, 不暴露完整订户号)。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SIMIdentityResult:
    consistent: bool
    declared_imsi_masked: Optional[str]
    attached_imsi_masked: Optional[str]


def _mask_imsi(imsi: Optional[str]) -> Optional[str]:
    """IMSI 脱敏: 前 8 位 + '…' (前 8 = MCC+MNC+MSIN 头, 够区分卡; 不暴露完整订户号)。"""
    if not imsi:
        return None
    s = str(imsi).strip()
    return s[:8] + "…" if len(s) > 8 else s


def check_sim_identity(*, declared_imsi: str, attached_imsi: str) -> SIMIdentityResult:
    """声明 IMSI vs attach IMSI 精确比 (strip 归一化后)。两边都得有值, caller 负责 None 跳过。"""
    d = str(declared_imsi).strip()
    a = str(attached_imsi).strip()
    return SIMIdentityResult(
        consistent=(d == a),
        declared_imsi_masked=_mask_imsi(d),
        attached_imsi_masked=_mask_imsi(a),
    )
