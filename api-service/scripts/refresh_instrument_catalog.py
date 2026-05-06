"""Instrument Catalog Refresh — 原地更新 instrument_models, 不 wipe 其他表

跟 seed_instruments.py 的区别:
  - seed_instruments.py: TRUNCATE everything → 重建. 会丢:
      * switch_topologies (操作员编辑过的暗室拓扑)
      * instrument_connections (操作员配置的 IP / endpoint)
      * 任何 selected_model_id 选择
  - 本脚本: 只 UPDATE 已有 instrument_models 行的:
      * vendor
      * full_name
      * capabilities (JSONB)
    其他都不动.

什么时候用本脚本:
  你修改了 seed_instruments.py 里 CATEGORIES 的某个 model capability,
  想让 PG 落实新值, 但 **不能丢操作员状态** (拓扑 / 连接 / 选择).

什么时候用 seed_instruments.py:
  从零起步 / 整个目录结构变了 (加新 category 行 / 加新 model 行) /
  你确认现场操作员状态可以丢.

用法:
    cd /Users/Simon/Tools/MIMO-First/api-service
    .venv/bin/python scripts/refresh_instrument_catalog.py

输出: 每个发生变更的 model 打印一行 "📝 Updated ...", 接着列出每个
字段的 before → after. 跑完打印 summary (updated / skipped 统计).

幂等: 重跑 = 同样结果. 没有变化的 model 完全跳过 (不写 DB).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Make `app.config` and `scripts.seed_instruments` importable when invoked
# directly (`.venv/bin/python scripts/refresh_instrument_catalog.py`) from
# the api-service directory.
_API_SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_API_SERVICE_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402

from app.config import settings  # noqa: E402
from scripts.seed_instruments import CATEGORIES  # noqa: E402


def _coerce_caps(raw: Any) -> dict:
    """capabilities column is JSONB on PG (returns dict) but JSON-string on
    some dialects. Tolerate both."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def _diff_caps(existing: dict, desired: dict) -> list[str]:
    """Return human-readable diff lines for a capabilities dict.

    Order: keys present in both (changed only) → keys only in desired
    (added) → keys only in existing (removed).
    """
    lines: list[str] = []
    all_keys = sorted(set(existing) | set(desired))
    for k in all_keys:
        a, b = existing.get(k), desired.get(k)
        if a == b:
            continue
        if k not in existing:
            lines.append(f"capabilities.{k}: (新增) {b!r}")
        elif k not in desired:
            lines.append(f"capabilities.{k}: (删除, 原值 {a!r})")
        else:
            lines.append(f"capabilities.{k}: {a!r} → {b!r}")
    return lines


def main() -> None:
    db_url = settings.database_url
    db_target = db_url.split("@")[1] if "@" in db_url else db_url

    print("=" * 60)
    print("  Instrument Catalog Refresh (in-place, no wipe)")
    print(f"  Target DB: {db_target}")
    print("=" * 60)

    engine = create_engine(db_url)

    updated = 0
    nochange = 0
    skipped_missing_category = 0
    skipped_missing_model = 0

    with engine.begin() as conn:
        for cat_def in CATEGORIES:
            cat_key = cat_def["key"]
            cat_row = conn.execute(
                text("SELECT id FROM instrument_categories WHERE category_key = :k"),
                {"k": cat_key},
            ).fetchone()
            if cat_row is None:
                print(
                    f"⚠️  Category '{cat_key}' 不在 DB — 跳过 "
                    "(先跑 seed_instruments.py 建表再用本工具)"
                )
                skipped_missing_category += 1
                continue
            cat_id = cat_row[0]

            for model_def in cat_def["models"]:
                model_name = model_def["model"]
                row = conn.execute(
                    text(
                        """
                        SELECT id, vendor, full_name, capabilities
                        FROM instrument_models
                        WHERE category_id = :cid AND model = :m
                        """
                    ),
                    {"cid": cat_id, "m": model_name},
                ).fetchone()
                if row is None:
                    print(
                        f"⚠️  Model '{cat_key}/{model_name}' 不在 DB — 跳过 "
                        "(本工具只更新, 不插入)"
                    )
                    skipped_missing_model += 1
                    continue

                existing_caps = _coerce_caps(row[3])
                desired_caps = model_def["capabilities"]
                desired_vendor = model_def["vendor"]
                desired_full = model_def["full_name"]

                changes: list[str] = []
                if row[1] != desired_vendor:
                    changes.append(f"vendor: '{row[1]}' → '{desired_vendor}'")
                if row[2] != desired_full:
                    changes.append(f"full_name: '{row[2]}' → '{desired_full}'")
                changes.extend(_diff_caps(existing_caps, desired_caps))

                if not changes:
                    nochange += 1
                    continue

                conn.execute(
                    text(
                        """
                        UPDATE instrument_models
                        SET vendor = :vendor,
                            full_name = :full_name,
                            capabilities = :caps,
                            updated_at = NOW()
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": row[0],
                        "vendor": desired_vendor,
                        "full_name": desired_full,
                        "caps": json.dumps(desired_caps),
                    },
                )
                updated += 1
                print(f"\n📝 Updated {cat_key}/{model_name}:")
                for c in changes:
                    print(f"     • {c}")

    print()
    print("=" * 60)
    print(f"  已更新 (updated):           {updated}")
    print(f"  无变化 (no change):         {nochange}")
    print(f"  缺少 category 跳过:         {skipped_missing_category}")
    print(f"  缺少 model 跳过:            {skipped_missing_model}")
    print("=" * 60)

    if skipped_missing_category > 0 or skipped_missing_model > 0:
        print(
            "⚠️  Catalog 里有 DB 还没有的条目. 跑一次 seed_instruments.py 把它们建出来,\n"
            "    再回来跑本工具更新 capabilities. (本工具不主动 INSERT 是为了避免\n"
            "    误把过期 catalog 里的条目重新带回 DB.)"
        )

    if updated == 0 and nochange > 0:
        print("✅ DB 已经跟 catalog 一致, 无需更新.")


if __name__ == "__main__":
    main()
