"""P2-12 slice 1: 标准信道文件命名契约 (Standard Channel Definition naming)。

软件掌控 .smu 命名 (用户 2026-06-01 确立, 见 docs/architecture/testcase-driven-
instrument-config.md §9)。**命名标准是我们的, 不是 F64 的**: config → 标准名 是确定性
函数, 两个方向都我们拥有 → 反解必然正确 (不像 P2-10 Step 1 的 parse_smu_center_freq_mhz
赌厂商命名约定)。

格式: MF_<band>_<ARFCN>_BW<bw>_<model>_<scenario>_<MIMO>_<pol>_v<version>.smu
例:   MF_N78_640000_BW100_CDLC_UMa_4x4_DP_v3.smu
  - ARFCN (非 frequency_mhz, 规范真值) / 极化 (V/H/DP) / 版本号 (重标递增, 可追溯)。
  - 字段一律 alnum 无下划线 (下划线是分隔符, 否则反解错位)。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.hal.nr_arfcn import freq_mhz_to_nr_arfcn, parse_smu_center_freq_mhz

STANDARD_PREFIX = "MF"
_ALNUM_RE = re.compile(r"^[A-Za-z0-9]+$")


@dataclass(frozen=True)
class StandardChannelName:
    """SCD 规范配置里进标准文件名的字段。字段一律 alnum 无下划线/连字符
    (model 写 filename-safe 形式, e.g. CDL-C → "CDLC")。"""

    band: str            # "N78"
    arfcn: Optional[int] # NR-ARFCN；LTE 必须为 None
    bandwidth_mhz: int   # 100
    model: str           # "CDLC"
    scenario: str        # "UMa"
    mimo: str            # "4x4"
    polarization: str    # "V" / "H" / "DP" (MIMO OTA 核心参数)
    version: int         # 3 (重标/重生成递增)
    radio_technology: str = "nr5g"
    channel_kind: str = "nr_arfcn"
    lte_dl_earfcn: Optional[int] = None


def _require_alnum(field: str, value: str) -> None:
    if not isinstance(value, str) or not _ALNUM_RE.match(value):
        raise ValueError(
            f"标准信道名字段 {field}={value!r} 必须 alnum 无下划线/连字符 "
            f"(下划线是分隔符, 否则反解会错位)"
        )


def format_standard_channel_filename(scn: StandardChannelName) -> str:
    """SCD config → 标准 .smu 文件名 (确定性, 我们拥有)。字段非法 → ValueError (早失败)。"""
    for fld in ("band", "model", "scenario", "mimo", "polarization"):
        _require_alnum(fld, getattr(scn, fld))
    if scn.bandwidth_mhz <= 0 or scn.version <= 0:
        raise ValueError("bandwidth_mhz / version 必须为正整数")
    if scn.radio_technology == "lte":
        if scn.channel_kind != "lte_dl_earfcn":
            raise ValueError("LTE 标准信道必须使用 channel_kind=lte_dl_earfcn")
        if scn.arfcn is not None:
            raise ValueError("LTE EARFCN 不得写入 NR arfcn 槽")
        if scn.lte_dl_earfcn is None or scn.lte_dl_earfcn < 0:
            raise ValueError("LTE lte_dl_earfcn 必须为非负整数")
        return (
            f"{STANDARD_PREFIX}_LTE_{scn.band}_EARFCN{scn.lte_dl_earfcn}"
            f"_BW{scn.bandwidth_mhz}_{scn.model}_{scn.scenario}_{scn.mimo}"
            f"_{scn.polarization}_v{scn.version}.smu"
        )
    if scn.radio_technology != "nr5g" or scn.channel_kind != "nr_arfcn":
        raise ValueError("NR 标准信道必须使用 nr5g/nr_arfcn")
    if scn.arfcn is None or scn.arfcn <= 0 or scn.lte_dl_earfcn is not None:
        raise ValueError("NR arfcn 必须为正整数且不得设置 lte_dl_earfcn")
    return (
        f"{STANDARD_PREFIX}_{scn.band}_{scn.arfcn}_BW{scn.bandwidth_mhz}"
        f"_{scn.model}_{scn.scenario}_{scn.mimo}_{scn.polarization}_v{scn.version}.smu"
    )


_STANDARD_RE = re.compile(
    rf"^{STANDARD_PREFIX}_([A-Za-z0-9]+)_(\d+)_BW(\d+)_([A-Za-z0-9]+)_([A-Za-z0-9]+)"
    rf"_([A-Za-z0-9]+)_([A-Za-z0-9]+)_v(\d+)\.smu$"
)
_LTE_STANDARD_RE = re.compile(
    rf"^{STANDARD_PREFIX}_LTE_([A-Za-z0-9]+)_EARFCN(\d+)_BW(\d+)_"
    rf"([A-Za-z0-9]+)_([A-Za-z0-9]+)_([A-Za-z0-9]+)_([A-Za-z0-9]+)_v(\d+)\.smu$"
)


def parse_standard_channel_filename(filename: Optional[str]) -> Optional[StandardChannelName]:
    """反解**我们标准命名**的 .smu → config (精确, 因为格式我们拥有)。

    非本标准格式 (厂商原始 .smu / 手工乱命名) → None。带路径时取 basename。
    """
    if not filename:
        return None
    base = filename.replace("\\", "/").rsplit("/", 1)[-1]
    lte_match = _LTE_STANDARD_RE.match(base)
    if lte_match:
        band, earfcn, bw, model, scenario, mimo, pol, ver = lte_match.groups()
        return StandardChannelName(
            band=band, arfcn=None, bandwidth_mhz=int(bw), model=model,
            scenario=scenario, mimo=mimo, polarization=pol, version=int(ver),
            radio_technology="lte", channel_kind="lte_dl_earfcn",
            lte_dl_earfcn=int(earfcn),
        )
    m = _STANDARD_RE.match(base)
    if not m:
        return None
    band, arfcn, bw, model, scenario, mimo, pol, ver = m.groups()
    return StandardChannelName(
        band=band, arfcn=int(arfcn), bandwidth_mhz=int(bw), model=model,
        scenario=scenario, mimo=mimo, polarization=pol, version=int(ver),
    )


@dataclass(frozen=True)
class ChannelNameFreqCheck:
    """实际 .smu 文件名 vs SCD 声明 ARFCN 的 cross-check 结果 (P2-12: Step 1 解析器从
    真值源降为 cross-check)。"""

    consistent: bool
    declared_arfcn: int
    actual_arfcn: Optional[int]  # 从文件名解析的 ARFCN; None = 解析不出 (无从核对)
    source: str                  # "standard" | "loose" | "unparseable"

    def failure_reason(self) -> Optional[str]:
        if self.consistent:
            return None
        return (
            f"标准信道文件名频率 ARFCN {self.actual_arfcn} ≠ SCD 声明 "
            f"{self.declared_arfcn} (文件被重命名 / 重调 / 关联错; source={self.source})"
        )

    @property
    def must_fail(self) -> bool:
        """只有**我们标准命名** (source=standard) 的不一致才值得 fail-loud —— 标准名与
        SCD 强绑定, 不一致必是改名/错关联。厂商名 (source=loose) 的频率 token 只是场景族
        标称, 2026-07-03 现场实证会说谎 (UMa_3600M 工程实为 3549.99 MHz), 不作拦截依据
        (真值 = SCD 声明侧的工程实测频率)。caller 一律用本属性而非 `not consistent`。"""
        return (not self.consistent) and self.source == "standard"


def check_channel_filename_freq(
    actual_filename: Optional[str], declared_arfcn: int,
) -> ChannelNameFreqCheck:
    """cross-check: 实际 .smu 文件名解析出的频率 vs SCD 声明的 ARFCN。

    频率来源优先级: 先试**我们标准名精确反解** (source=standard); 否则退回 Step 1
    **松解析** `parse_smu_center_freq_mhz` (source=loose, e.g. 路径 c 关联的厂商 .smu)。
    都解析不出 (source=unparseable) → 无从核对 → 不强判不一致 (consistent=True 但 source
    标 unparseable, 跟 Phase 1 None-skip 一致; SCD 声明本就是真值)。

    不一致的处置分级 (122eeae 现场软化 + P1-18 定案, 见 `must_fail`):
    - source=standard (我们自己的 MF_ 命名, 反解必然正确) 且 ≠ 声明 → fail-loud;
    - source=loose (厂商文件名) 且 ≠ 声明 → 只警告不拦 —— 厂商文件名是场景族
      标称, 系统性说谎 (实录 UMa_3600M 工程实为 3549.99), SCD 声明 (工程解析
      `smu_project` / 实测) 才是真值, 不能让说谎的文件名否决正确的声明。
    """
    std = parse_standard_channel_filename(actual_filename)
    if std is not None:
        actual_arfcn: Optional[int] = std.arfcn
        source = "standard"
    else:
        freq = parse_smu_center_freq_mhz(actual_filename)
        if freq is None:
            return ChannelNameFreqCheck(True, declared_arfcn, None, "unparseable")
        try:
            actual_arfcn = freq_mhz_to_nr_arfcn(freq)
        except ValueError:  # 解析出的频率超 NR-ARFCN 范围 → 当解析不出
            return ChannelNameFreqCheck(True, declared_arfcn, None, "unparseable")
        source = "loose"
    return ChannelNameFreqCheck(
        consistent=(actual_arfcn == declared_arfcn),
        declared_arfcn=declared_arfcn,
        actual_arfcn=actual_arfcn,
        source=source,
    )
