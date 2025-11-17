"""
Comparability Test Service

Implements inter-laboratory comparison (round-robin) testing
"""
import numpy as np
from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy.orm import Session
import logging
from uuid import UUID, uuid4

from app.models.calibration import ComparabilityTest

logger = logging.getLogger(__name__)


class ComparabilityTestService:
    """
    Service for executing comparability (round-robin) tests

    Compares measurements from this laboratory against reference laboratories
    to ensure measurement consistency across different facilities.
    """

    def execute_comparability_test(
        self,
        db: Session,
        round_robin_id: Optional[UUID],
        lab_name: str,
        lab_id: str,
        lab_accreditation: str,
        dut_model: str,
        dut_serial: str,
        local_trp_dbm: float,
        local_tis_dbm: float,
        local_eis_dbm: Optional[float],
        reference_measurements: List[Dict],
        tested_by: str
    ) -> ComparabilityTest:
        """
        Execute comparability test

        Args:
            db: Database session
            round_robin_id: UUID for round-robin test (shared across labs)
            lab_name: This laboratory's name
            lab_id: This laboratory's ID
            lab_accreditation: Accreditation standard
            dut_model: DUT model
            dut_serial: DUT serial number
            local_trp_dbm: TRP measured by this lab
            local_tis_dbm: TIS measured by this lab
            local_eis_dbm: EIS measured by this lab (optional)
            reference_measurements: List of measurements from other labs
                Format: [{
                    'lab_name': str,
                    'lab_id': str,
                    'trp_dbm': float,
                    'tis_dbm': float,
                    'eis_dbm': float,
                    'measured_at': datetime
                }, ...]
            tested_by: Engineer name

        Returns:
            ComparabilityTest record
        """
        logger.info(f"Starting comparability test for lab: {lab_name}")

        # Generate round-robin ID if not provided
        if not round_robin_id:
            round_robin_id = uuid4()

        # Calculate bias against each reference lab
        trp_bias_list = []
        tis_bias_list = []
        eis_bias_list = []

        for ref in reference_measurements:
            trp_bias = local_trp_dbm - ref['trp_dbm']
            tis_bias = local_tis_dbm - ref['tis_dbm']

            trp_bias_list.append({
                'lab_name': ref['lab_name'],
                'bias_db': trp_bias
            })
            tis_bias_list.append({
                'lab_name': ref['lab_name'],
                'bias_db': tis_bias
            })

            if local_eis_dbm is not None and ref.get('eis_dbm') is not None:
                eis_bias = local_eis_dbm - ref['eis_dbm']
                eis_bias_list.append({
                    'lab_name': ref['lab_name'],
                    'bias_db': eis_bias
                })

        # Calculate mean bias
        trp_mean_bias = np.mean([b['bias_db'] for b in trp_bias_list]) if trp_bias_list else 0.0
        tis_mean_bias = np.mean([b['bias_db'] for b in tis_bias_list]) if tis_bias_list else 0.0
        eis_mean_bias = np.mean([b['bias_db'] for b in eis_bias_list]) if eis_bias_list else None

        # Validation: pass if all biases < ±1.0 dB
        threshold_db = 1.0

        trp_pass = all(abs(b['bias_db']) < threshold_db for b in trp_bias_list)
        tis_pass = all(abs(b['bias_db']) < threshold_db for b in tis_bias_list)
        eis_pass = all(abs(b['bias_db']) < threshold_db for b in eis_bias_list) if eis_bias_list else True

        validation_pass = trp_pass and tis_pass and eis_pass

        # DUT stability check (simplified: assume stable if we have reference data)
        dut_stable = len(reference_measurements) > 0

        # Create test record
        test = ComparabilityTest(
            round_robin_id=round_robin_id,
            lab_name=lab_name,
            lab_id=lab_id,
            lab_accreditation=lab_accreditation,
            dut_model=dut_model,
            dut_serial=dut_serial,
            dut_stable=dut_stable,
            local_trp_dbm=local_trp_dbm,
            local_tis_dbm=local_tis_dbm,
            local_eis_dbm=local_eis_dbm,
            local_measured_at=datetime.utcnow(),
            reference_measurements=reference_measurements,
            trp_bias_db=trp_bias_list,
            tis_bias_db=tis_bias_list,
            eis_bias_db=eis_bias_list if eis_bias_list else None,
            trp_mean_bias_db=float(trp_mean_bias),
            tis_mean_bias_db=float(tis_mean_bias),
            eis_mean_bias_db=float(eis_mean_bias) if eis_mean_bias is not None else None,
            validation_pass=validation_pass,
            threshold_db=threshold_db,
            notes=self._generate_notes(trp_bias_list, tis_bias_list, eis_bias_list, threshold_db),
            tested_at=datetime.utcnow(),
            tested_by=tested_by
        )

        db.add(test)
        db.commit()
        db.refresh(test)

        logger.info(
            f"Comparability test complete: "
            f"TRP bias={trp_mean_bias:.2f} dB, "
            f"TIS bias={tis_mean_bias:.2f} dB, "
            f"pass={validation_pass}"
        )

        return test

    def _generate_notes(
        self,
        trp_bias: List[Dict],
        tis_bias: List[Dict],
        eis_bias: List[Dict],
        threshold_db: float
    ) -> str:
        """Generate summary notes for comparability test"""
        notes = []

        # TRP analysis
        trp_max_bias = max([abs(b['bias_db']) for b in trp_bias]) if trp_bias else 0
        if trp_max_bias > threshold_db:
            notes.append(f"TRP 最大偏差 {trp_max_bias:.2f} dB 超出阈值 ±{threshold_db} dB")

        # TIS analysis
        tis_max_bias = max([abs(b['bias_db']) for b in tis_bias]) if tis_bias else 0
        if tis_max_bias > threshold_db:
            notes.append(f"TIS 最大偏差 {tis_max_bias:.2f} dB 超出阈值 ±{threshold_db} dB")

        # EIS analysis
        if eis_bias:
            eis_max_bias = max([abs(b['bias_db']) for b in eis_bias])
            if eis_max_bias > threshold_db:
                notes.append(f"EIS 最大偏差 {eis_max_bias:.2f} dB 超出阈值 ±{threshold_db} dB")

        if not notes:
            notes.append("所有测量值与参考实验室的偏差均在可接受范围内")

        return "; ".join(notes)

    def get_round_robin_summary(
        self,
        db: Session,
        round_robin_id: UUID
    ) -> Dict:
        """
        Get summary of all laboratories in a round-robin test

        Args:
            db: Database session
            round_robin_id: Round-robin test ID

        Returns:
            Dictionary with summary statistics
        """
        tests = db.query(ComparabilityTest).filter_by(
            round_robin_id=round_robin_id
        ).all()

        if not tests:
            return {'error': 'No tests found for this round-robin ID'}

        # Collect all measurements
        labs = []
        for test in tests:
            labs.append({
                'lab_name': test.lab_name,
                'trp_dbm': test.local_trp_dbm,
                'tis_dbm': test.local_tis_dbm,
                'eis_dbm': test.local_eis_dbm,
            })

        # Calculate statistics
        trp_values = [lab['trp_dbm'] for lab in labs if lab['trp_dbm'] is not None]
        tis_values = [lab['tis_dbm'] for lab in labs if lab['tis_dbm'] is not None]

        summary = {
            'round_robin_id': str(round_robin_id),
            'num_labs': len(labs),
            'labs': labs,
            'trp': {
                'mean': float(np.mean(trp_values)) if trp_values else None,
                'std_dev': float(np.std(trp_values, ddof=1)) if len(trp_values) > 1 else None,
                'min': float(np.min(trp_values)) if trp_values else None,
                'max': float(np.max(trp_values)) if trp_values else None,
                'range': float(np.max(trp_values) - np.min(trp_values)) if trp_values else None,
            },
            'tis': {
                'mean': float(np.mean(tis_values)) if tis_values else None,
                'std_dev': float(np.std(tis_values, ddof=1)) if len(tis_values) > 1 else None,
                'min': float(np.min(tis_values)) if tis_values else None,
                'max': float(np.max(tis_values)) if tis_values else None,
                'range': float(np.max(tis_values) - np.min(tis_values)) if tis_values else None,
            }
        }

        return summary
