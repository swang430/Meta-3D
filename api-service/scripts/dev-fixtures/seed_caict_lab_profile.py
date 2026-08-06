"""Seed the canonical 'CAICT-Lab-1' LabProfile from current DB state.

Bundles:
- the explicitly named CAICT ChamberConfiguration as chamber_config_id
- the latest passing CalibrationCertificate as active_calibration_certificate_id
- all active InstrumentCategory rows as instrument_bindings

Idempotent: if a LabProfile named 'CAICT-Lab-1' already exists, the script
updates its bindings/refs in place rather than creating a duplicate. The
on-disk InstrumentConnection.endpoint is copied into the binding so the
profile is self-contained and can be replicated to another lab.

Usage:
    cd api-service
    .venv/bin/python scripts/seed_caict_lab_profile.py
"""
import logging
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import desc

from app.db.database import SessionLocal
from app.models import (
    CalibrationCertificate,
    ChamberConfiguration,
    LabProfile,
)
from app.models.instrument import InstrumentCategory, InstrumentConnection

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("seed_caict")

LAB_NAME = "CAICT-Lab-1"
LAB_ORG = "中国信通院"
LAB_LOCATION = "Beijing, China"
CHAMBER_NAME = "CAICT-16-Probe-Dual"


def _resolve_chamber(db) -> ChamberConfiguration:
    matches = db.query(ChamberConfiguration).filter(
        ChamberConfiguration.name == CHAMBER_NAME
    ).all()
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one ChamberConfiguration named {CHAMBER_NAME!r}, "
            f"found {len(matches)}. Seed/repair that explicit chamber first."
        )
    return matches[0]


def _resolve_calibration(db) -> CalibrationCertificate | None:
    """Pick the latest issued certificate that overall_pass=True. Optional."""
    return (
        db.query(CalibrationCertificate)
        .filter(CalibrationCertificate.overall_pass.is_(True))
        .order_by(desc(CalibrationCertificate.issued_at))
        .first()
    )


def _build_instrument_bindings(db) -> list[dict]:
    """One binding per active InstrumentCategory; pulls the per-category
    InstrumentConnection.endpoint into the binding so the profile is
    self-describing.
    """
    bindings: list[dict] = []
    cats = (
        db.query(InstrumentCategory)
        .filter(InstrumentCategory.is_active == True)  # noqa: E712
        .all()
    )
    for cat in cats:
        conn = (
            db.query(InstrumentConnection)
            .filter(InstrumentConnection.category_id == cat.id)
            .first()
        )
        bindings.append(
            {
                "category_id": str(cat.id),
                "category_key": cat.category_key,
                "instrument_model_id": None,  # filled in when a specific model is chosen
                "connection_endpoint": (conn.endpoint if conn else None),
                "driver_mode": "auto",  # honor global HAL_MODE; per-instrument override possible
                "role": f"primary_{cat.category_key}",
            }
        )
    return bindings


def main() -> int:
    db = SessionLocal()
    try:
        chamber = _resolve_chamber(db)
        cert = _resolve_calibration(db)
        bindings = _build_instrument_bindings(db)
        logger.info(
            "Resolved sources: chamber=%s, cert=%s, instrument_bindings=%d",
            chamber.name,
            cert.certificate_number if cert else "(none)",
            len(bindings),
        )

        existing = db.query(LabProfile).filter(LabProfile.name == LAB_NAME).first()
        if existing:
            logger.info("[update] LabProfile %s exists (id=%s) — refreshing", LAB_NAME, existing.id)
            existing.chamber_config_id = chamber.id
            existing.active_calibration_certificate_id = cert.id if cert else None
            existing.instrument_bindings = bindings
            existing.organization = LAB_ORG
            existing.location = LAB_LOCATION
            existing.is_active = True
            db.commit()
            db.refresh(existing)
            logger.info("[ok]   refreshed CAICT-Lab-1 (id=%s)", existing.id)
            return 0

        profile = LabProfile(
            name=LAB_NAME,
            description="3GPP Static MIMO OTA primary lab — seeded from active chamber + latest cert",
            organization=LAB_ORG,
            location=LAB_LOCATION,
            chamber_config_id=chamber.id,
            active_calibration_certificate_id=cert.id if cert else None,
            instrument_bindings=bindings,
            network_config={
                "subnet": "192.168.1.0/24",
                "time_sync_server": "ntp.caict.local",
            },
            extra_metadata={
                "accreditation_body": "CNAS",
                "contact": "ota-lab@caict.cn",
                "seeded_by": "seed_caict_lab_profile.py",
            },
            is_active=True,
            created_by="seed_script",
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        logger.info("[ok]   created CAICT-Lab-1 (id=%s)", profile.id)
        return 0

    except Exception as e:
        logger.exception("Seed failed: %s", e)
        db.rollback()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
