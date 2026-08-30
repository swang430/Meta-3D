#!/usr/bin/env python3
"""Preview or apply one evidence-backed CMW500 saved preset recovery."""

import argparse
import json
from uuid import UUID

from app.db.database import SessionLocal
from app.services.base_station_model_preset_recovery import (
    recover_cmw500_model_preset,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--connection-id", type=UUID, required=True)
    parser.add_argument("--model-id", type=UUID, required=True)
    parser.add_argument("--source-execution-id", type=UUID, required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist the recovered saved preset; default is read-only preview",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        result = recover_cmw500_model_preset(
            db,
            connection_id=args.connection_id,
            model_id=args.model_id,
            source_execution_id=args.source_execution_id,
            apply=args.apply,
        )
        if args.apply:
            db.commit()
        else:
            db.rollback()
        print(json.dumps({
            "changed": result.changed,
            "applied": result.applied,
            "source_execution_id": str(result.source_execution_id),
            "preset": result.preset.model_dump(mode="json"),
            "formal_qualification_granted": False,
        }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
