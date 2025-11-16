"""System calibration API endpoints"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from app.db.database import get_db
from app.schemas.calibration import (
    TRPCalibrationRequest,
    TRPCalibrationResponse,
    TISCalibrationRequest,
    TISCalibrationResponse,
    RepeatabilityTestRequest,
    RepeatabilityTestResponse,
    GenerateCertificateRequest,
    CertificateResponse,
    CertificateDetail,
)
from app.services.system_calibration import (
    TRPCalibrationService,
    TISCalibrationService,
    RepeatabilityTestService,
    CalibrationCertificateService,
)
from app.services.mock_instruments import MockInstrumentOrchestrator
from app.models.calibration import (
    SystemTRPCalibration,
    SystemTISCalibration,
    RepeatabilityTest,
    CalibrationCertificate,
)

router = APIRouter(prefix="/calibration", tags=["System Calibration"])


# ==================== TRP Calibration Endpoints ====================

@router.post("/trp", response_model=TRPCalibrationResponse, status_code=201)
async def execute_trp_calibration(
    request: TRPCalibrationRequest,
    db: Session = Depends(get_db)
):
    """
    Execute TRP (Total Radiated Power) calibration test.

    This endpoint validates the system's ability to accurately measure
    radiated power by comparing against a standard DUT with known TRP.

    **Validation Criteria**: |measured - reference| < ±0.5 dB
    """
    instruments = MockInstrumentOrchestrator()
    service = TRPCalibrationService(instruments)

    calibration = await service.execute_trp_calibration(
        db=db,
        standard_dut_model=request.standard_dut_model,
        standard_dut_serial=request.standard_dut_serial,
        reference_trp_dbm=request.reference_trp_dbm,
        frequency_mhz=request.frequency_mhz,
        tx_power_dbm=request.tx_power_dbm,
        tested_by=request.tested_by,
        reference_lab=request.reference_lab,
        reference_cert_number=request.reference_cert_number
    )

    return calibration


@router.get("/trp", response_model=List[TRPCalibrationResponse])
def list_trp_calibrations(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all TRP calibration records"""
    calibrations = db.query(SystemTRPCalibration).offset(skip).limit(limit).all()
    return calibrations


@router.get("/trp/{calibration_id}", response_model=TRPCalibrationResponse)
def get_trp_calibration(
    calibration_id: UUID,
    db: Session = Depends(get_db)
):
    """Get specific TRP calibration record"""
    calibration = db.query(SystemTRPCalibration).filter_by(id=calibration_id).first()
    if not calibration:
        raise HTTPException(status_code=404, detail="TRP calibration not found")
    return calibration


# ==================== TIS Calibration Endpoints ====================

@router.post("/tis", response_model=TISCalibrationResponse, status_code=201)
async def execute_tis_calibration(
    request: TISCalibrationRequest,
    db: Session = Depends(get_db)
):
    """
    Execute TIS (Total Isotropic Sensitivity) calibration test.

    This endpoint validates the system's ability to accurately measure
    receiver sensitivity.

    **Validation Criteria**: |measured - reference| < ±1.0 dB
    """
    instruments = MockInstrumentOrchestrator()
    service = TISCalibrationService(instruments)

    calibration = await service.execute_tis_calibration(
        db=db,
        standard_dut_model=request.standard_dut_model,
        standard_dut_serial=request.standard_dut_serial,
        reference_tis_dbm=request.reference_tis_dbm,
        frequency_mhz=request.frequency_mhz,
        tested_by=request.tested_by,
        reference_lab=request.reference_lab,
        reference_cert_number=request.reference_cert_number
    )

    return calibration


@router.get("/tis", response_model=List[TISCalibrationResponse])
def list_tis_calibrations(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all TIS calibration records"""
    calibrations = db.query(SystemTISCalibration).offset(skip).limit(limit).all()
    return calibrations


@router.get("/tis/{calibration_id}", response_model=TISCalibrationResponse)
def get_tis_calibration(
    calibration_id: UUID,
    db: Session = Depends(get_db)
):
    """Get specific TIS calibration record"""
    calibration = db.query(SystemTISCalibration).filter_by(id=calibration_id).first()
    if not calibration:
        raise HTTPException(status_code=404, detail="TIS calibration not found")
    return calibration


# ==================== Repeatability Test Endpoints ====================

@router.post("/repeatability", response_model=RepeatabilityTestResponse, status_code=201)
async def execute_repeatability_test(
    request: RepeatabilityTestRequest,
    db: Session = Depends(get_db)
):
    """
    Execute repeatability test.

    Measures the same parameter N times to assess measurement precision.

    **Validation Criteria**:
    - TRP: σ < 0.3 dB
    - TIS: σ < 0.5 dB
    - EIS: σ < 0.5 dB
    """
    instruments = MockInstrumentOrchestrator()
    service = RepeatabilityTestService(instruments)

    test_result = await service.execute_repeatability_test(
        db=db,
        test_type=request.test_type,
        dut_model=request.dut_model,
        dut_serial=request.dut_serial,
        num_runs=request.num_runs,
        frequency_mhz=request.frequency_mhz,
        tested_by=request.tested_by
    )

    return test_result


@router.get("/repeatability", response_model=List[RepeatabilityTestResponse])
def list_repeatability_tests(
    skip: int = 0,
    limit: int = 100,
    test_type: str = None,
    db: Session = Depends(get_db)
):
    """List repeatability test records"""
    query = db.query(RepeatabilityTest)
    if test_type:
        query = query.filter_by(test_type=test_type)
    tests = query.offset(skip).limit(limit).all()
    return tests


# ==================== Certificate Endpoints ====================

@router.post("/certificate", response_model=CertificateResponse, status_code=201)
def generate_certificate(
    request: GenerateCertificateRequest,
    db: Session = Depends(get_db)
):
    """
    Generate calibration certificate from test results.

    Combines TRP, TIS, and repeatability test results into a
    formal calibration certificate.
    """
    service = CalibrationCertificateService()

    certificate = service.generate_certificate(
        db=db,
        trp_calibration_id=str(request.trp_calibration_id),
        tis_calibration_id=str(request.tis_calibration_id),
        repeatability_test_id=str(request.repeatability_test_id),
        lab_name=request.lab_name,
        lab_address=request.lab_address,
        lab_accreditation=request.lab_accreditation,
        calibrated_by=request.calibrated_by,
        reviewed_by=request.reviewed_by,
        validity_months=request.validity_months
    )

    return certificate


@router.get("/certificate", response_model=List[CertificateResponse])
def list_certificates(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all calibration certificates"""
    certificates = db.query(CalibrationCertificate).offset(skip).limit(limit).all()
    return certificates


@router.get("/certificate/{certificate_id}", response_model=CertificateDetail)
def get_certificate(
    certificate_id: UUID,
    db: Session = Depends(get_db)
):
    """Get specific calibration certificate"""
    certificate = db.query(CalibrationCertificate).filter_by(id=certificate_id).first()
    if not certificate:
        raise HTTPException(status_code=404, detail="Certificate not found")
    return certificate


@router.get("/certificate/number/{certificate_number}", response_model=CertificateDetail)
def get_certificate_by_number(
    certificate_number: str,
    db: Session = Depends(get_db)
):
    """Get certificate by certificate number"""
    certificate = db.query(CalibrationCertificate).filter_by(
        certificate_number=certificate_number
    ).first()
    if not certificate:
        raise HTTPException(status_code=404, detail="Certificate not found")
    return certificate
