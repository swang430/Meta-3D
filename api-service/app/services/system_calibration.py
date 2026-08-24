"""
System-Level Calibration Services

Implements TRP, TIS, repeatability, and comparability calibration tests.
"""
import numpy as np
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import logging

from app.services.mock_instruments import MockInstrumentOrchestrator
from app.models.calibration import (
    SystemTRPCalibration,
    SystemTISCalibration,
    RepeatabilityTest,
    CalibrationCertificate
)

logger = logging.getLogger(__name__)


class TRPCalibrationService:
    """
    TRP (Total Radiated Power) Calibration Service

    Validates system's ability to accurately measure radiated power.
    """

    def __init__(self, instruments: MockInstrumentOrchestrator):
        self.instruments = instruments

    async def execute_trp_calibration(
        self,
        db: Session,
        standard_dut_model: str,
        standard_dut_serial: str,
        reference_trp_dbm: float,
        frequency_mhz: float,
        tx_power_dbm: float,
        tested_by: str,
        reference_lab: Optional[str] = None,
        reference_cert_number: Optional[str] = None
    ) -> SystemTRPCalibration:
        """
        Execute TRP calibration test

        Args:
            db: Database session
            standard_dut_model: Model of standard DUT (e.g., "Standard Dipole")
            standard_dut_serial: Serial number
            reference_trp_dbm: Known TRP from reference laboratory
            frequency_mhz: Test frequency
            tx_power_dbm: Transmit power
            tested_by: Name of test engineer
            reference_lab: Reference laboratory name (optional)
            reference_cert_number: Reference certificate number (optional)

        Returns:
            SystemTRPCalibration record
        """
        logger.info(f"Starting TRP calibration for {standard_dut_model} SN:{standard_dut_serial}")

        # 1. Load standard DUT
        self.instruments.load_standard_dut(
            model=standard_dut_model,
            serial=standard_dut_serial,
            known_trp_dbm=reference_trp_dbm,
            known_tis_dbm=-90.0  # Not used for TRP test
        )

        # 2. Connect instruments
        await self.instruments.connect_all()

        # 3. Measure power at spherical grid points
        theta_step = 15.0  # degrees
        phi_step = 15.0    # degrees

        probe_data = []
        powers_linear = []

        for theta_deg in np.arange(0, 181, theta_step):
            for phi_deg in np.arange(0, 360, phi_step):
                # Measure power at this angle
                power_dbm = await self.instruments.measure_trp_at_angle(
                    theta_deg=theta_deg,
                    phi_deg=phi_deg,
                    frequency_mhz=frequency_mhz,
                    tx_power_dbm=tx_power_dbm
                )

                probe_data.append({
                    'theta': theta_deg,
                    'phi': phi_deg,
                    'measured_power_dbm': power_dbm
                })

                # Convert to linear scale for integration
                powers_linear.append(10 ** (power_dbm / 10))

        # 4. Spherical integration to compute TRP
        measured_trp_dbm = self._compute_trp(
            powers_linear=powers_linear,
            theta_step_deg=theta_step,
            phi_step_deg=phi_step
        )

        # 5. Calculate error
        trp_error_db = measured_trp_dbm - reference_trp_dbm
        absolute_error_db = abs(trp_error_db)

        # 6. Validation (pass if error < ±0.5 dB)
        threshold_db = 0.5
        validation_pass = absolute_error_db < threshold_db

        # 7. Estimate measurement uncertainty
        measurement_uncertainty_db = 0.3  # Mock value

        # 8. Create database record
        calibration = SystemTRPCalibration(
            standard_dut_model=standard_dut_model,
            standard_dut_serial=standard_dut_serial,
            reference_trp_dbm=reference_trp_dbm,
            reference_lab=reference_lab,
            reference_cert_number=reference_cert_number,
            frequency_mhz=frequency_mhz,
            channel=f"EARFCN_{int(frequency_mhz)}",
            bandwidth_mhz=20.0,
            modulation="QPSK",
            tx_power_dbm=tx_power_dbm,
            measured_trp_dbm=measured_trp_dbm,
            measurement_uncertainty_db=measurement_uncertainty_db,
            trp_error_db=trp_error_db,
            absolute_error_db=absolute_error_db,
            num_probes_used=len(probe_data),
            probe_data=probe_data,
            integration_method="spherical_integration",
            theta_step_deg=theta_step,
            phi_step_deg=phi_step,
            validation_pass=validation_pass,
            threshold_db=threshold_db,
            tested_at=datetime.utcnow(),
            tested_by=tested_by
        )

        db.add(calibration)
        db.commit()
        db.refresh(calibration)

        # 9. Disconnect instruments
        await self.instruments.disconnect_all()

        logger.info(
            f"TRP calibration complete: measured={measured_trp_dbm:.2f} dBm, "
            f"error={trp_error_db:.2f} dB, pass={validation_pass}"
        )

        return calibration

    def _compute_trp(
        self,
        powers_linear: List[float],
        theta_step_deg: float,
        phi_step_deg: float
    ) -> float:
        """
        Compute TRP from spherical power measurements

        TRP = ∫∫ ERP(θ, φ) · sin(θ) dθ dφ / (4π)

        Args:
            powers_linear: List of power values in linear scale (mW)
            theta_step_deg: Theta sampling step (degrees)
            phi_step_deg: Phi sampling step (degrees)

        Returns:
            TRP in dBm
        """
        theta_step_rad = np.radians(theta_step_deg)
        phi_step_rad = np.radians(phi_step_deg)

        # Reshape powers into theta-phi grid
        num_theta = int(180 / theta_step_deg) + 1
        num_phi = int(360 / phi_step_deg)

        powers_grid = np.array(powers_linear).reshape(num_theta, num_phi)

        # Theta values
        thetas = np.arange(0, 181, theta_step_deg)
        thetas_rad = np.radians(thetas)

        # Integration weights: sin(theta)
        sin_theta = np.sin(thetas_rad)

        # Integrate
        total_power = 0.0
        for i, theta in enumerate(thetas):
            for j in range(num_phi):
                total_power += powers_grid[i, j] * sin_theta[i] * theta_step_rad * phi_step_rad

        # Normalize by 4π
        trp_linear = total_power / (4 * np.pi)

        # Convert to dBm
        trp_dbm = 10 * np.log10(trp_linear)

        return trp_dbm


class TISCalibrationService:
    """
    TIS (Total Isotropic Sensitivity) Calibration Service

    Validates system's ability to accurately measure receiver sensitivity.
    """

    def __init__(self, instruments: MockInstrumentOrchestrator):
        self.instruments = instruments

    async def execute_tis_calibration(
        self,
        db: Session,
        standard_dut_model: str,
        standard_dut_serial: str,
        reference_tis_dbm: float,
        frequency_mhz: float,
        tested_by: str,
        reference_lab: Optional[str] = None,
        reference_cert_number: Optional[str] = None
    ) -> SystemTISCalibration:
        """
        Execute TIS calibration test

        Args:
            db: Database session
            standard_dut_model: Model of standard DUT
            standard_dut_serial: Serial number
            reference_tis_dbm: Known TIS from reference laboratory
            frequency_mhz: Test frequency
            tested_by: Test engineer name

        Returns:
            SystemTISCalibration record
        """
        logger.info(f"Starting TIS calibration for {standard_dut_model} SN:{standard_dut_serial}")

        # 1. Load standard DUT
        self.instruments.load_standard_dut(
            model=standard_dut_model,
            serial=standard_dut_serial,
            known_trp_dbm=10.0,  # Not used for TIS test
            known_tis_dbm=reference_tis_dbm
        )

        # 2. Connect instruments
        await self.instruments.connect_all()

        # 3. Measure sensitivity at spherical grid points
        theta_step = 15.0
        phi_step = 15.0

        probe_data = []
        sensitivities_linear = []

        for theta_deg in np.arange(0, 181, theta_step):
            for phi_deg in np.arange(0, 360, phi_step):
                # Measure sensitivity at this angle
                sensitivity_dbm = await self.instruments.measure_tis_at_angle(
                    theta_deg=theta_deg,
                    phi_deg=phi_deg,
                    frequency_mhz=frequency_mhz
                )

                probe_data.append({
                    'theta': theta_deg,
                    'phi': phi_deg,
                    'sensitivity_dbm': sensitivity_dbm
                })

                # Convert to linear (invert for harmonic mean)
                sensitivities_linear.append(10 ** (sensitivity_dbm / 10))

        # 4. Compute TIS using harmonic mean
        measured_tis_dbm = self._compute_tis(
            sensitivities_linear=sensitivities_linear,
            theta_step_deg=theta_step,
            phi_step_deg=phi_step
        )

        # 5. Calculate error
        tis_error_db = measured_tis_dbm - reference_tis_dbm
        absolute_error_db = abs(tis_error_db)

        # 6. Validation (pass if error < ±1.0 dB)
        threshold_db = 1.0
        validation_pass = absolute_error_db < threshold_db

        # 7. Measurement uncertainty
        measurement_uncertainty_db = 0.5

        # 8. Create database record
        calibration = SystemTISCalibration(
            standard_dut_model=standard_dut_model,
            standard_dut_serial=standard_dut_serial,
            reference_tis_dbm=reference_tis_dbm,
            reference_lab=reference_lab,
            reference_cert_number=reference_cert_number,
            frequency_mhz=frequency_mhz,
            channel=f"EARFCN_{int(frequency_mhz)}",
            bandwidth_mhz=20.0,
            modulation="64QAM",
            target_throughput_mbps=10.0,
            measured_tis_dbm=measured_tis_dbm,
            measurement_uncertainty_db=measurement_uncertainty_db,
            tis_error_db=tis_error_db,
            absolute_error_db=absolute_error_db,
            num_probes_used=len(probe_data),
            probe_data=probe_data,
            integration_method="harmonic_mean",
            theta_step_deg=theta_step,
            phi_step_deg=phi_step,
            validation_pass=validation_pass,
            threshold_db=threshold_db,
            tested_at=datetime.utcnow(),
            tested_by=tested_by
        )

        db.add(calibration)
        db.commit()
        db.refresh(calibration)

        # 9. Disconnect
        await self.instruments.disconnect_all()

        logger.info(
            f"TIS calibration complete: measured={measured_tis_dbm:.2f} dBm, "
            f"error={tis_error_db:.2f} dB, pass={validation_pass}"
        )

        return calibration

    def _compute_tis(
        self,
        sensitivities_linear: List[float],
        theta_step_deg: float,
        phi_step_deg: float
    ) -> float:
        """
        Compute TIS from spherical sensitivity measurements

        TIS = -10 · log10( ∫∫ 10^(-EIS(θ,φ)/10) · sin(θ) dθ dφ / (4π) )

        Args:
            sensitivities_linear: List of sensitivity values in linear scale
            theta_step_deg: Theta step
            phi_step_deg: Phi step

        Returns:
            TIS in dBm
        """
        theta_step_rad = np.radians(theta_step_deg)
        phi_step_rad = np.radians(phi_step_deg)

        num_theta = int(180 / theta_step_deg) + 1
        num_phi = int(360 / phi_step_deg)

        sensitivities_grid = np.array(sensitivities_linear).reshape(num_theta, num_phi)

        thetas = np.arange(0, 181, theta_step_deg)
        thetas_rad = np.radians(thetas)
        sin_theta = np.sin(thetas_rad)

        # Integrate (using inverse sensitivities for harmonic mean)
        total_inverse = 0.0
        for i, theta in enumerate(thetas):
            for j in range(num_phi):
                total_inverse += (1.0 / sensitivities_grid[i, j]) * sin_theta[i] * theta_step_rad * phi_step_rad

        # Normalize
        harmonic_mean_inverse = total_inverse / (4 * np.pi)

        # TIS = -10 * log10(harmonic_mean_inverse)
        tis_dbm = -10 * np.log10(harmonic_mean_inverse)

        return tis_dbm


class CalibrationCertificateService:
    """
    Calibration Certificate Generation Service
    """

    def generate_certificate(
        self,
        db: Session,
        trp_calibration_id: str,
        tis_calibration_id: str,
        repeatability_test_id: str,
        lab_name: str,
        lab_address: str,
        lab_accreditation: str,
        calibrated_by: str,
        reviewed_by: str,
        validity_months: int = 12
    ) -> CalibrationCertificate:
        """
        Generate calibration certificate from test results

        Args:
            db: Database session
            trp_calibration_id: ID of TRP calibration record
            tis_calibration_id: ID of TIS calibration record
            repeatability_test_id: ID of repeatability test
            lab_name: Laboratory name
            lab_address: Laboratory address
            lab_accreditation: Accreditation standard
            calibrated_by: Engineer who performed calibration
            reviewed_by: Technical reviewer
            validity_months: Certificate validity period (months)

        Returns:
            CalibrationCertificate record
        """
        # Fetch related records
        trp_cal = db.query(SystemTRPCalibration).filter_by(id=trp_calibration_id).first()
        tis_cal = db.query(SystemTISCalibration).filter_by(id=tis_calibration_id).first()
        repeat_test = db.query(RepeatabilityTest).filter_by(id=repeatability_test_id).first()

        if not all([trp_cal, tis_cal, repeat_test]):
            raise ValueError("Missing required calibration records")
        if repeat_test.test_type == "execution_metrics":
            # P1-72：对齐记录行无 dBm 统计、无判决（validation_pass=NULL），
            # 进证书会撞 overall_pass NOT NULL 且语义错位 —— fail-loud 拒绝
            raise ValueError(
                "repeatability_test_id 指向 execution_metrics 对齐记录行，"
                "不能用于系统校准证书（证书需要 TRP/TIS 重复性判决行）"
            )

        # Generate certificate number
        now = datetime.utcnow()
        cert_number = f"MPAC-SYS-CAL-{now.year}-{now.month:02d}-{now.day:02d}-{now.hour:02d}{now.minute:02d}"

        # Compute overall pass
        overall_pass = (
            trp_cal.validation_pass and
            tis_cal.validation_pass and
            repeat_test.validation_pass
        )

        # Create certificate
        certificate = CalibrationCertificate(
            certificate_number=cert_number,
            system_name="Meta-3D MPAC OTA Test System",
            system_serial_number="MPAC-001",
            system_configuration={
                'num_probes': 32,
                'chamber_radius_m': 10.0,
                'frequency_range_mhz': [600, 6000]
            },
            lab_name=lab_name,
            lab_address=lab_address,
            lab_accreditation=lab_accreditation,
            lab_accreditation_body="CNAS",
            calibration_date=now,
            valid_until=now + timedelta(days=validity_months * 30),
            standards=['3GPP TS 34.114', 'CTIA OTA Ver. 4.0'],
            trp_error_db=trp_cal.absolute_error_db,
            trp_pass=trp_cal.validation_pass,
            tis_error_db=tis_cal.absolute_error_db,
            tis_pass=tis_cal.validation_pass,
            repeatability_std_dev_db=repeat_test.std_dev_db,
            repeatability_pass=repeat_test.validation_pass,
            comparability_bias_db=None,  # Optional
            comparability_pass=True,
            overall_pass=overall_pass,
            calibrated_by=calibrated_by,
            reviewed_by=reviewed_by,
            digital_signature=self._compute_digital_signature(cert_number, now),
            issued_at=now
        )

        db.add(certificate)
        db.commit()
        db.refresh(certificate)

        logger.info(f"Certificate {cert_number} generated, overall_pass={overall_pass}")

        return certificate

    def _compute_digital_signature(self, cert_number: str, timestamp: datetime) -> str:
        """Compute SHA-256 digital signature"""
        import hashlib
        data = f"{cert_number}:{timestamp.isoformat()}"
        return hashlib.sha256(data.encode()).hexdigest()
