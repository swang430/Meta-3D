"""Export the UXM SCPI commands our driver depends on, as a markdown
checklist suitable for emailing to a chamber operator (CAICT etc.) to
verify firmware compatibility before a site debug.

Why a generator instead of a static doc:
  - Source of truth is the driver's UxmScpiCommands class — if someone
    adds a new SCPI command in code but forgets to update a static doc,
    the doc rots. This script reads the live class.

Run:
  cd api-service
  .venv/bin/python -m scripts.export_uxm_scpi_checklist

Output goes to stdout. Pipe to clipboard / file as you like.
"""
from __future__ import annotations

import inspect
from typing import Iterable, List, Tuple

from app.hal.uxm_base_station import UxmScpiCommands


# Group definitions: prefix patterns + human-readable category + license/feature note
# Order matters — first match wins, so put more specific prefixes first.
_GROUPS: List[Tuple[str, str, str]] = [
    # (substring match, category title, license note)
    ("CALL:NR5G", "UE info / RRC / CA control",
     "5G NR signaling app, RRC reconfig, Carrier Aggregation"),
    ("MEASure:NR5G", "5G NR measurements",
     "5G NR FRC throughput / CSI / EVM / UE report measurement licenses"),
    ("CONFig:NR5G", "Cell configuration",
     "5G NR signaling app (band/ARFCN/BW/SCS/MIMO/TDD)"),
    ("ROUTe:NR5G", "Antenna port routing",
     "MIMO 2x2 / 4x4 license, hardware antenna routing option"),
    ("SYSTem:", "System / app management",
     "core firmware, IEEE 488.2"),
    ("*", "IEEE 488.2 standard", "core firmware"),
]


def _commands() -> Iterable[Tuple[str, str]]:
    """Yield (attr_name, scpi_string) for every public string constant on
    UxmScpiCommands. Skips dunders + non-string fields."""
    for name, value in inspect.getmembers(UxmScpiCommands):
        if name.startswith("_"):
            continue
        if not isinstance(value, str):
            continue
        yield name, value


def _classify(scpi: str) -> Tuple[str, str]:
    """Return (group_title, license_note) for a given SCPI string."""
    # Strip leading {cell}/{idx} placeholders to compare against prefixes
    for substring, title, note in _GROUPS:
        if substring == "*":
            if scpi.startswith("*"):
                return title, note
        elif substring in scpi:
            return title, note
    return "Other", "—"


def main() -> None:
    rows = list(_commands())
    rows.sort(key=lambda r: r[1])  # by SCPI alphabetical inside each group

    # Group rows
    grouped: dict[str, list[Tuple[str, str, str]]] = {}
    license_notes: dict[str, str] = {}
    for name, scpi in rows:
        title, note = _classify(scpi)
        grouped.setdefault(title, []).append((name, scpi, note))
        license_notes[title] = note

    # Render markdown
    print("# UXM 5G NR — SCPI Compatibility Checklist")
    print()
    print(
        "Below是我们的驱动 (`app/hal/uxm_base_station.py::UxmScpiCommands`) "
        "在端到端 MIMO OTA 测试中会发到 UXM 的全部 SCPI 命令。请协助确认现场 "
        "UXM 的 firmware 是否支持每一组（任一组缺失意味着对应 phase 跑不通）。"
    )
    print()
    print(
        "命令里的 `{cell}` 占位符在调用时会替换为目标 cell 名 (默认 `CELL0`); "
        "`{bwp}` 替换为 BWP 名 (默认 `BWP0`); `{idx}` 替换为 SCell index 等。"
    )
    print()
    print(f"**Total commands**: {len(rows)} (auto-generated from driver code)")
    print()
    print("---")
    print()

    # Order groups for output — most likely-to-fail first
    group_order = [
        "Cell configuration",
        "5G NR measurements",
        "UE info / RRC / CA control",
        "Antenna port routing",
        "System / app management",
        "IEEE 488.2 standard",
        "Other",
    ]
    for title in group_order:
        if title not in grouped:
            continue
        print(f"## {title}")
        print()
        print(f"**License / firmware feature**: {license_notes[title]}")
        print()
        print("| Driver constant | SCPI command |")
        print("|---|---|")
        for name, scpi, _ in grouped[title]:
            # Escape pipes in SCPI for table safety
            safe_scpi = scpi.replace("|", "\\|")
            print(f"| `{name}` | `{safe_scpi}` |")
        print()

    print("---")
    print()
    print("## Verification request")
    print()
    print(
        "建议在 site debug 之前，由 CAICT 现场工程师在 UXM 的 SCPI Command "
        "Reference (与当前 firmware 版本匹配的那本) 里**逐组**核对上述命令是否："
    )
    print()
    print("1. 该 firmware 版本支持这条 SCPI（命令名拼写 / 参数名 / 占位符相同）")
    print("2. 该 license 已激活（`SYST:OPT?` 查询能看到对应的 license token）")
    print("3. 默认值 / 参数范围跟我们用的一致 (e.g., 我们用 SCS 30kHz, 是否支持？)")
    print()
    print(
        "若任一组里有命令对不上，请提前告知——我们可以在驱动里加 vendor-specific "
        "alias 或调整请求路径，比现场卡住强。"
    )


if __name__ == "__main__":
    main()
