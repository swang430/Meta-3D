"""NR-ARFCN ↔ 频率转换 + 频率规范标识 (P2-11 Phase 1).

用户 2026-05-30 确立的架构原则: **系统中频率的规范标识是「中心频点 ARFCN + 带宽」,
不是 frequency_mhz**。

- ARFCN 是 3GPP TS 38.104 标准定义的**整数** channel number, 精确 → 没有浮点容差问题。
  (容差恰恰是"用近似 MHz 而非标准 ARFCN"混出来的。)
- 中心频点 (不是起始/边缘频率), 带宽单独标识。
- 能回读完整频率身份的仪表归一到 (中心 ARFCN, 带宽) 再比对；只能证明中心
  频率的仪表（当前 F64）由上层保留带宽 unknown，不在这里伪造带宽。

这同时是 P1-17 ARFCN bug 的根本解: 那个 bug (profile 标称 frequency_mhz=3600 但实际
下发 ARFCN→3489) 正是因为没拿 ARFCN 当真值。

NR-ARFCN 公式 (3GPP TS 38.104 §5.4.2.1, Table 5.4.2.1-1):

    F_REF = F_REF_Offs + ΔF_Global × (N_REF − N_REF_Offs)

| 频率范围 (MHz)  | ΔF_Global (kHz) | F_REF_Offs (MHz) | N_REF_Offs | N_REF 范围        |
|-----------------|-----------------|------------------|------------|-------------------|
| 0 – 3000        | 5               | 0                | 0          | 0 – 599999        |
| 3000 – 24250    | 15              | 3000             | 600000     | 600000 – 2016666  |
| 24250 – 100000  | 60              | 24250.08         | 2016667    | 2016667 – 3279165 |
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# (ΔF_Global_kHz, F_REF_Offs_MHz, N_REF_Offs, F_low_MHz, F_high_MHz)
_NR_ARFCN_RANGES = (
    (5, 0.0, 0, 0.0, 3000.0),
    (15, 3000.0, 600000, 3000.0, 24250.0),
    (60, 24250.08, 2016667, 24250.0, 100000.0),
)


def freq_mhz_to_nr_arfcn(freq_mhz: float) -> int:
    """中心频率 (MHz) → NR-ARFCN (整数 channel number, 3GPP TS 38.104)。

    用 round 而非 floor: 频率落在 raster 点上时给最近的 ARFCN; 严格 raster 校验
    (频率必须精确落在 channel raster) 不在本函数范围 —— 本函数是"归一到标准标识"用,
    校验一致性看归一后的 ARFCN 整数是否相等。
    """
    for delta_khz, f_offs, n_offs, f_low, f_high in _NR_ARFCN_RANGES:
        if f_low <= freq_mhz < f_high:
            return round(n_offs + (freq_mhz - f_offs) / (delta_khz / 1000.0))
    raise ValueError(
        f"频率 {freq_mhz} MHz 超出 NR-ARFCN 定义范围 (0–100000 MHz)"
    )


def nr_arfcn_to_freq_mhz(arfcn: int) -> float:
    """NR-ARFCN → 中心频率 (MHz)。"""
    # 按 N_REF 范围反查 (用 ΔF×N 算 F_REF)
    bounds = (
        (0, 599999, 5, 0.0, 0),
        (600000, 2016666, 15, 3000.0, 600000),
        (2016667, 3279165, 60, 24250.08, 2016667),
    )
    for n_low, n_high, delta_khz, f_offs, n_offs in bounds:
        if n_low <= arfcn <= n_high:
            return f_offs + (delta_khz / 1000.0) * (arfcn - n_offs)
    raise ValueError(f"ARFCN {arfcn} 超出 NR-ARFCN 定义范围 (0–3279165)")


# .smu / .asc 文件名里的频率 token 正则: `_<3-5位数字>M` (后接 . 或 _ 或结尾),
# 避免误匹配 "FR1" / "UMa" 等。e.g. "3GPP_FR1_OTA_CDLC_UMa_3600M.smu" → 3600。
_SMU_FREQ_TOKEN_RE = re.compile(r"[_-](\d{3,5})M(?=[._]|$)")


def parse_smu_center_freq_mhz(filename: Optional[str]) -> Optional[float]:
    """从信道文件名 (.smu / .asc) 解析中心频率 (MHz)。

    Channel Studio / 厂商 .smu 命名约定把频率编进文件名 (频率固定在文件里, 见 P2-11
    Phase 2 GCM 缺口讨论)。取**最后**一个 `_<数字>M` token (最可能是频率, 排在场景/
    带宽描述之后)。None = filename 空 / 无频率 token。

    单一真值: propsim_f64 (回读已加载 .smu 频率) 和 channel model inventory (盘点可用
    .smu 的频率元数据, P2-10 Step 1) 共用此解析, 避免命名约定漂移成两套。
    """
    if not filename:
        return None
    matches = _SMU_FREQ_TOKEN_RE.findall(filename)
    if not matches:
        return None
    return float(matches[-1])


@dataclass(frozen=True)
class FrequencyIdentity:
    """频率的**规范标识** = (中心频点 ARFCN, 带宽 MHz)。

    系统中所有仪表的中心频率都归一到这个表示再比对。相等 = ARFCN 整数相等 **且**
    带宽相等 —— 精确比对, 无浮点容差 (ARFCN 是标准整数; 带宽是离散档位)。

    用法::

        a = FrequencyIdentity.from_center_freq_mhz(3600.0, 100.0)
        b = FrequencyIdentity.from_center_freq_mhz(3500.0, 100.0)
        a == b   # False (ARFCN 不同: 640000 vs 633333)
        a.describe()  # "ARFCN 640000 (3600.0 MHz) / BW 100.0 MHz"
    """
    center_arfcn: int
    bandwidth_mhz: float

    @classmethod
    def from_center_freq_mhz(
        cls, center_freq_mhz: float, bandwidth_mhz: float
    ) -> "FrequencyIdentity":
        return cls(
            center_arfcn=freq_mhz_to_nr_arfcn(center_freq_mhz),
            bandwidth_mhz=float(bandwidth_mhz),
        )

    @property
    def center_freq_mhz(self) -> float:
        """从 ARFCN 反算的中心频率 (MHz), 人类可读视图 (派生, 非真值)。"""
        return nr_arfcn_to_freq_mhz(self.center_arfcn)

    def describe(self) -> str:
        return (
            f"ARFCN {self.center_arfcn} ({self.center_freq_mhz:.2f} MHz) / "
            f"BW {self.bandwidth_mhz:g} MHz"
        )
