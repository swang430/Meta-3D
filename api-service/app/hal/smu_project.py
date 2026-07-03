"""F64 .smu 工程文件 (INI 文本) 的中心频率真值解析 — P1-18 ③。

.smu 是 Channel Studio 工程, ``[Channel Group N]`` 节的 ``CenterFrequency``
键 (Hz 整数) 是该组载波的**工程真值**。文件名里的频率 token 是场景族标称,
系统性说谎 (2026-07-03 CAICT 实录: UMa_3600M 工程实为 3549.99 MHz /
UMa_1800M → 1842.50 / UMa_2450M → 2592.99), 只可作 loose 提示
(``nr_arfcn.parse_smu_center_freq_mhz``); 本模块给出可作登记真值的工程内声明。

消费方 (离线路径 —— F64 ATE Server 无 MMEM/FTP, 运行时拉不到工程文件):
- 资产登记 / 审计脚本 (P2-18 资产真值自动化的地基, 替代 onsite 脚本硬表);
- 操作员上传工程副本时的 SCD 声明校验。

实录格式 (SMB //192.168.0.132/Scenario Packs, 2026-07-03)::

    [Channel Group 0]
    CenterFrequency = 3549990000 Hz
"""
from __future__ import annotations

import re
from typing import Dict, Optional

# 节头: [Channel Group 0] — 组号捕获; 其他节 ([Link ...] 等) 里的同名键不收
_GROUP_HEADER_RE = re.compile(r"^\s*\[Channel Group\s+(\d+)\]\s*$")
# 任意节头 (进入非 Channel Group 节时退出收集态)
_ANY_HEADER_RE = re.compile(r"^\s*\[.+\]\s*$")
# 键行: CenterFrequency = 3549990000 Hz — 单位 Hz 可省, 值必须是正整数 Hz
_CENTER_FREQ_RE = re.compile(
    r"^\s*CenterFrequency\s*=\s*(\d+)\s*(?:Hz)?\s*$", re.IGNORECASE
)


def parse_smu_project_center_freqs_hz(text: Optional[str]) -> Dict[int, int]:
    """解析 .smu 工程文本, 返回 {Channel Group 组号: CenterFrequency Hz}。

    逐行状态机: 只认 ``[Channel Group N]`` 节内的 ``CenterFrequency`` 键;
    同组重复键取首个 (工程内不应重复, 防御性选择最早声明)。空/None 文本、
    无匹配节 → 空 dict (调用方 fail-loud 或回退由其自决)。
    """
    freqs: Dict[int, int] = {}
    if not text:
        return freqs
    current_group: Optional[int] = None
    for line in text.splitlines():
        m = _GROUP_HEADER_RE.match(line)
        if m:
            current_group = int(m.group(1))
            continue
        if _ANY_HEADER_RE.match(line):
            current_group = None  # 进入其他节, 停止收集
            continue
        if current_group is None:
            continue
        m = _CENTER_FREQ_RE.match(line)
        if m and current_group not in freqs:
            freqs[current_group] = int(m.group(1))
    return freqs


def parse_smu_project_primary_freq_mhz(text: Optional[str]) -> Optional[float]:
    """主载波 (Channel Group 0, 缺 0 取最小组号) 的工程中心频率 (MHz)。

    None = 文本空 / 无任何 Channel Group 声明。返回值即 SCD 应登记的
    center_frequency_mhz 真值 (e.g. 3549990000 Hz → 3549.99)。
    """
    freqs = parse_smu_project_center_freqs_hz(text)
    if not freqs:
        return None
    group = 0 if 0 in freqs else min(freqs)
    return freqs[group] / 1e6
