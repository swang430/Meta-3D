"""NR band 运行基线查表 (P1-19 ④) — EMQuest .prm 全集实录。

真值源: 2026-07-03 CAICT 现场对 EMQuest 参数文件 (10 band) 的二进制解析,
与 F64 Scenario Pack 工程频率互证 (N3/N41/N78/N79 四个 TDD band 精确配对)。
数据在 ``app/data/nr_band_baselines.json``; 本模块只做加载与查询。

消费方:
- ``RealUxmDriver.set_cell_config``: 目标 ARFCN 与基线一致时自动补
  SSB/PointA 三件套 (合拍条件严格 —— 自定义频率不乱补, 见调用点注释);
- onsite 脚本 / 后续 P2-18 资产真值自动化。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "nr_band_baselines.json"


@lru_cache(maxsize=1)
def _load() -> Dict[str, Dict[str, Any]]:
    with open(_DATA_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    return {k.upper(): v for k, v in raw.items() if not k.startswith("_")}


def get_band_baseline(band: Optional[str]) -> Optional[Dict[str, Any]]:
    """按 band 名 (大小写不敏感, "n78"/"N78") 取运行基线; 未收录返回 None。"""
    if not band:
        return None
    return _load().get(str(band).upper())
