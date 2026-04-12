"""
Calibration Report Generator

Generates comprehensive PDF reports for probe and channel calibration data.
Integrates with PDFGenerator for report generation.
"""

import os
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.services.pdf_generator import PDFGenerator
from app.models.probe_calibration import (
    ProbeAmplitudeCalibration,
    ProbePhaseCalibration,
    ProbePolarizationCalibration,
    ProbePattern,
    LinkCalibration,
    ProbePathLossCalibration,
    RFChainCalibration,
    MultiFrequencyPathLoss,
)
from app.models.channel_calibration import (
    ChannelCalibrationSession,
    TemporalChannelCalibration,
    DopplerCalibration,
    SpatialCorrelationCalibration,
    AngularSpreadCalibration,
    ChannelQuietZoneCalibration,
    EISValidation,
)

logger = logging.getLogger(__name__)


class CalibrationReportGenerator:
    """Service for generating calibration reports"""

    def __init__(self, db: Session):
        self.db = db
        self.pdf_generator = PDFGenerator()

    def generate_comprehensive_report(
        self,
        session_id: Optional[UUID] = None,
        output_path: Optional[str] = None,
        include_probe: bool = True,
        include_channel: bool = True,
        title: Optional[str] = None,
    ) -> str:
        """
        Generate a comprehensive calibration report

        Args:
            session_id: Optional session ID to filter calibrations
            output_path: Path to save PDF file
            include_probe: Include probe calibration data
            include_channel: Include channel calibration data
            title: Report title

        Returns:
            Path to generated PDF file
        """
        # Collect data
        report_data = self._collect_report_data(
            session_id=session_id,
            include_probe=include_probe,
            include_channel=include_channel,
        )

        # Set title
        if title:
            report_data['title'] = title
        elif session_id:
            session = self.db.query(ChannelCalibrationSession).filter(
                ChannelCalibrationSession.id == session_id
            ).first()
            if session:
                report_data['title'] = f"Calibration Report: {session.name}"
            else:
                report_data['title'] = "System Calibration Report"
        else:
            report_data['title'] = "System Calibration Report"

        # Generate output path if not provided
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = "data/reports/calibration"
            os.makedirs(output_dir, exist_ok=True)
            output_path = f"{output_dir}/calibration_report_{timestamp}.pdf"

        # Generate template configuration
        template = self._create_calibration_template()

        # Generate PDF
        return self.pdf_generator.generate_report(report_data, template, output_path)

    def generate_probe_calibration_report(
        self,
        probe_ids: Optional[List[int]] = None,
        calibration_type: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> str:
        """Generate report for probe calibrations only"""
        report_data = self._collect_probe_data(
            probe_ids=probe_ids,
            calibration_type=calibration_type,
        )

        report_data['title'] = "Probe Calibration Report"
        report_data['report_type'] = "Probe Calibration"

        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = "data/reports/calibration"
            os.makedirs(output_dir, exist_ok=True)
            output_path = f"{output_dir}/probe_calibration_{timestamp}.pdf"

        template = self._create_probe_template()
        return self.pdf_generator.generate_report(report_data, template, output_path)

    def generate_channel_calibration_report(
        self,
        session_id: Optional[UUID] = None,
        calibration_type: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> str:
        """Generate report for channel calibrations only"""
        report_data = self._collect_channel_data(
            session_id=session_id,
            calibration_type=calibration_type,
        )

        report_data['title'] = "Channel Calibration Report"
        report_data['report_type'] = "Channel Calibration"

        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = "data/reports/calibration"
            os.makedirs(output_dir, exist_ok=True)
            output_path = f"{output_dir}/channel_calibration_{timestamp}.pdf"

        template = self._create_channel_template()
        return self.pdf_generator.generate_report(report_data, template, output_path)

    def generate_chamber_calibration_report(
        self,
        chamber_id: UUID,
        frequency_mhz: Optional[float] = None,
        output_path: Optional[str] = None,
    ) -> str:
        """
        Generate report for chamber-specific calibrations

        Includes path loss, RF chain, and multi-frequency calibration data
        for a specific chamber configuration.

        Args:
            chamber_id: Chamber configuration ID
            frequency_mhz: Optional frequency filter
            output_path: Path to save PDF file

        Returns:
            Path to generated PDF file
        """
        from app.models.chamber import ChamberConfiguration

        # Get chamber info
        chamber = self.db.query(ChamberConfiguration).filter(
            ChamberConfiguration.id == chamber_id
        ).first()

        if not chamber:
            raise ValueError(f"Chamber not found: {chamber_id}")

        report_data = self._collect_chamber_calibration_data(
            chamber_id=chamber_id,
            frequency_mhz=frequency_mhz,
        )

        report_data['title'] = f"Chamber Calibration Report: {chamber.name}"
        report_data['report_type'] = "Chamber Calibration"
        report_data['chamber_info'] = {
            'id': str(chamber.id),
            'name': chamber.name,
            'chamber_type': chamber.chamber_type,
            'chamber_radius_m': chamber.chamber_radius_m,
            'num_probes': chamber.num_probes,
            'has_lna': chamber.has_lna,
            'lna_gain_db': chamber.lna_gain_db,
            'has_pa': chamber.has_pa,
            'pa_gain_db': chamber.pa_gain_db,
            'has_duplexer': chamber.has_duplexer,
            'supports_trp': chamber.supports_trp,
            'supports_tis': chamber.supports_tis,
            'supports_mimo_ota': chamber.supports_mimo_ota,
        }

        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = "data/reports/calibration"
            os.makedirs(output_dir, exist_ok=True)
            output_path = f"{output_dir}/chamber_calibration_{chamber.name}_{timestamp}.pdf"

        template = self._create_chamber_template()
        return self.pdf_generator.generate_report(report_data, template, output_path)

    def _collect_chamber_calibration_data(
        self,
        chamber_id: UUID,
        frequency_mhz: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Collect calibration data for a specific chamber"""
        data = {
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'chamber_calibration': {},
            'execution_summary': {},
        }

        total = 0
        passed = 0

        # Path loss calibrations
        query = self.db.query(ProbePathLossCalibration).filter(
            ProbePathLossCalibration.chamber_id == chamber_id
        )
        if frequency_mhz:
            query = query.filter(ProbePathLossCalibration.frequency_mhz == frequency_mhz)
        calibrations = query.order_by(desc(ProbePathLossCalibration.calibrated_at)).limit(20).all()

        path_loss_data = []
        for cal in calibrations:
            total += 1
            is_valid = cal.status == 'valid'
            if is_valid:
                passed += 1
            path_loss_data.append({
                'id': str(cal.id),
                'frequency_mhz': cal.frequency_mhz,
                'num_probes': len(cal.probe_path_losses) if cal.probe_path_losses else 0,
                'validation_pass': is_valid,
                'calibrated_at': str(cal.calibrated_at) if cal.calibrated_at else None,
                'calibrated_by': cal.calibrated_by,
                'valid_until': str(cal.valid_until) if cal.valid_until else None,
                'sgh_model': cal.sgh_model,
                'sgh_gain_dbi': cal.sgh_gain_dbi,
                'avg_path_loss_db': cal.avg_path_loss_db,
                'max_path_loss_db': cal.max_path_loss_db,
                'min_path_loss_db': cal.min_path_loss_db,
                'std_dev_db': cal.std_dev_db,
            })
        data['chamber_calibration']['path_loss'] = path_loss_data

        # RF chain calibrations (uplink)
        query = self.db.query(RFChainCalibration).filter(
            RFChainCalibration.chamber_id == chamber_id,
            RFChainCalibration.chain_type == 'uplink'
        )
        if frequency_mhz:
            query = query.filter(RFChainCalibration.frequency_mhz == frequency_mhz)
        uplink_cals = query.order_by(desc(RFChainCalibration.calibrated_at)).limit(10).all()

        uplink_data = []
        for cal in uplink_cals:
            total += 1
            is_valid = cal.status == 'valid'
            if is_valid:
                passed += 1
            uplink_data.append({
                'id': str(cal.id),
                'frequency_mhz': cal.frequency_mhz,
                'validation_pass': is_valid,
                'calibrated_at': str(cal.calibrated_at) if cal.calibrated_at else None,
                'calibrated_by': cal.calibrated_by,
                'valid_until': str(cal.valid_until) if cal.valid_until else None,
                'has_lna': cal.has_lna,
                'lna_model': cal.lna_model,
                'lna_gain_measured_db': cal.lna_gain_measured_db,
                'lna_noise_figure_db': cal.lna_noise_figure_db,
                'total_chain_gain_db': cal.total_chain_gain_db,
            })
        data['chamber_calibration']['uplink'] = uplink_data

        # RF chain calibrations (downlink)
        query = self.db.query(RFChainCalibration).filter(
            RFChainCalibration.chamber_id == chamber_id,
            RFChainCalibration.chain_type == 'downlink'
        )
        if frequency_mhz:
            query = query.filter(RFChainCalibration.frequency_mhz == frequency_mhz)
        downlink_cals = query.order_by(desc(RFChainCalibration.calibrated_at)).limit(10).all()

        downlink_data = []
        for cal in downlink_cals:
            total += 1
            is_valid = cal.status == 'valid'
            if is_valid:
                passed += 1
            downlink_data.append({
                'id': str(cal.id),
                'frequency_mhz': cal.frequency_mhz,
                'validation_pass': is_valid,
                'calibrated_at': str(cal.calibrated_at) if cal.calibrated_at else None,
                'calibrated_by': cal.calibrated_by,
                'valid_until': str(cal.valid_until) if cal.valid_until else None,
                'has_pa': cal.has_pa,
                'pa_model': cal.pa_model,
                'pa_gain_measured_db': cal.pa_gain_measured_db,
                'pa_p1db_measured_dbm': cal.pa_p1db_measured_dbm,
                'has_duplexer': cal.has_duplexer,
                'duplexer_insertion_loss_db': cal.duplexer_insertion_loss_db,
                'total_chain_gain_db': cal.total_chain_gain_db,
            })
        data['chamber_calibration']['downlink'] = downlink_data

        # Multi-frequency path loss
        query = self.db.query(MultiFrequencyPathLoss).filter(
            MultiFrequencyPathLoss.chamber_id == chamber_id
        )
        multi_freq_cals = query.order_by(desc(MultiFrequencyPathLoss.calibrated_at)).limit(20).all()

        multi_freq_data = []
        for cal in multi_freq_cals:
            total += 1
            is_valid = cal.status == 'valid'
            if is_valid:
                passed += 1
            multi_freq_data.append({
                'id': str(cal.id),
                'probe_id': cal.probe_id,
                'polarization': cal.polarization,
                'validation_pass': is_valid,
                'calibrated_at': str(cal.calibrated_at) if cal.calibrated_at else None,
                'valid_until': str(cal.valid_until) if cal.valid_until else None,
                'freq_start_mhz': cal.freq_start_mhz,
                'freq_stop_mhz': cal.freq_stop_mhz,
                'num_points': cal.num_points,
            })
        data['chamber_calibration']['multi_frequency'] = multi_freq_data

        # Summary
        data['execution_summary'] = {
            'total_executions': total,
            'passed': passed,
            'failed': total - passed,
            'pending': 0,
            'pass_rate': (passed / total * 100) if total > 0 else 0,
        }

        return data

    def _collect_report_data(
        self,
        session_id: Optional[UUID],
        include_probe: bool,
        include_channel: bool,
    ) -> Dict[str, Any]:
        """Collect all calibration data for comprehensive report"""
        data = {
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'generated_by': 'MIMO OTA Calibration System',
            'report_type': 'Comprehensive Calibration',
        }

        # Session info
        if session_id:
            session = self.db.query(ChannelCalibrationSession).filter(
                ChannelCalibrationSession.id == session_id
            ).first()
            if session:
                data['session'] = {
                    'id': str(session.id),
                    'name': session.name,
                    'description': session.description,
                    'status': session.status,
                    'started_at': str(session.started_at) if session.started_at else None,
                    'completed_at': str(session.completed_at) if session.completed_at else None,
                    'total_calibrations': session.total_calibrations,
                    'passed_calibrations': session.passed_calibrations,
                    'failed_calibrations': session.failed_calibrations,
                    'overall_pass': session.overall_pass,
                }

        # Collect probe data
        if include_probe:
            probe_data = self._collect_probe_data()
            data['probe_calibration'] = probe_data.get('probe_calibration', {})
            data['probe_summary'] = probe_data.get('execution_summary', {})

        # Collect channel data
        if include_channel:
            channel_data = self._collect_channel_data(session_id=session_id)
            data['channel_calibration'] = channel_data.get('channel_calibration', {})
            data['channel_summary'] = channel_data.get('execution_summary', {})

        # Calculate overall summary
        data['execution_summary'] = self._calculate_overall_summary(data)

        return data

    def _collect_probe_data(
        self,
        probe_ids: Optional[List[int]] = None,
        calibration_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Collect probe calibration data"""
        data = {
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'probe_calibration': {},
            'execution_summary': {},
        }

        total = 0
        passed = 0

        # Amplitude calibrations
        if not calibration_type or calibration_type == 'amplitude':
            query = self.db.query(ProbeAmplitudeCalibration)
            if probe_ids:
                query = query.filter(ProbeAmplitudeCalibration.probe_id.in_(probe_ids))
            calibrations = query.order_by(desc(ProbeAmplitudeCalibration.calibrated_at)).limit(100).all()

            amplitude_data = []
            for cal in calibrations:
                total += 1
                if cal.validation_pass:
                    passed += 1
                amplitude_data.append({
                    'id': str(cal.id),
                    'probe_id': cal.probe_id,
                    'polarization': cal.polarization,
                    'validation_pass': cal.validation_pass,
                    'calibrated_at': str(cal.calibrated_at) if cal.calibrated_at else None,
                    'calibrated_by': cal.calibrated_by,
                    'frequency_points': cal.frequency_points_mhz,
                    'tx_gain_dbi': cal.tx_gain_dbi,
                    'rx_gain_dbi': cal.rx_gain_dbi,
                })
            data['probe_calibration']['amplitude'] = amplitude_data

        # Phase calibrations
        if not calibration_type or calibration_type == 'phase':
            query = self.db.query(ProbePhaseCalibration)
            if probe_ids:
                query = query.filter(ProbePhaseCalibration.probe_id.in_(probe_ids))
            calibrations = query.order_by(desc(ProbePhaseCalibration.calibrated_at)).limit(100).all()

            phase_data = []
            for cal in calibrations:
                total += 1
                if cal.validation_pass:
                    passed += 1
                phase_data.append({
                    'id': str(cal.id),
                    'probe_id': cal.probe_id,
                    'reference_probe_id': cal.reference_probe_id,
                    'polarization': cal.polarization,
                    'validation_pass': cal.validation_pass,
                    'calibrated_at': str(cal.calibrated_at) if cal.calibrated_at else None,
                    'calibrated_by': cal.calibrated_by,
                    'phase_offset_deg': cal.phase_offset_deg,
                    'group_delay_ns': cal.group_delay_ns,
                })
            data['probe_calibration']['phase'] = phase_data

        # Polarization calibrations
        if not calibration_type or calibration_type == 'polarization':
            query = self.db.query(ProbePolarizationCalibration)
            if probe_ids:
                query = query.filter(ProbePolarizationCalibration.probe_id.in_(probe_ids))
            calibrations = query.order_by(desc(ProbePolarizationCalibration.calibrated_at)).limit(100).all()

            polarization_data = []
            for cal in calibrations:
                total += 1
                if cal.validation_pass:
                    passed += 1
                polarization_data.append({
                    'id': str(cal.id),
                    'probe_id': cal.probe_id,
                    'probe_type': cal.probe_type,
                    'validation_pass': cal.validation_pass,
                    'calibrated_at': str(cal.calibrated_at) if cal.calibrated_at else None,
                    'calibrated_by': cal.calibrated_by,
                    'xpd_db': cal.xpd_db,
                    'axial_ratio_db': cal.axial_ratio_db,
                })
            data['probe_calibration']['polarization'] = polarization_data

        # Pattern data (ProbePattern - not really a "calibration" but pattern measurement)
        if not calibration_type or calibration_type == 'pattern':
            query = self.db.query(ProbePattern)
            if probe_ids:
                query = query.filter(ProbePattern.probe_id.in_(probe_ids))
            patterns = query.order_by(desc(ProbePattern.measured_at)).limit(100).all()

            pattern_data = []
            for pat in patterns:
                total += 1
                # Pattern is considered "valid" if it exists and status is valid
                is_valid = pat.status == 'valid'
                if is_valid:
                    passed += 1
                pattern_data.append({
                    'id': str(pat.id),
                    'probe_id': pat.probe_id,
                    'frequency_mhz': pat.frequency_mhz,
                    'validation_pass': is_valid,
                    'calibrated_at': str(pat.measured_at) if pat.measured_at else None,
                    'calibrated_by': pat.measured_by,
                    'beamwidth_3db_deg': pat.hpbw_azimuth_deg,
                    'main_lobe_gain_dbi': pat.peak_gain_dbi,
                })
            data['probe_calibration']['pattern'] = pattern_data

        # Link calibrations
        if not calibration_type or calibration_type == 'link':
            query = self.db.query(LinkCalibration)
            calibrations = query.order_by(desc(LinkCalibration.calibrated_at)).limit(100).all()

            link_data = []
            for cal in calibrations:
                total += 1
                if cal.validation_pass:
                    passed += 1
                link_data.append({
                    'id': str(cal.id),
                    'probe_id': None,  # LinkCalibration is system-wide, not per-probe
                    'calibration_type': cal.calibration_type,
                    'validation_pass': cal.validation_pass,
                    'calibrated_at': str(cal.calibrated_at) if cal.calibrated_at else None,
                    'calibrated_by': cal.calibrated_by,
                    'deviation_db': cal.deviation_db,
                    'standard_dut_model': cal.standard_dut_model,
                })
            data['probe_calibration']['link'] = link_data

        # Path loss calibrations (CAL-02: SGH → Probe spatial path loss)
        if not calibration_type or calibration_type == 'path_loss':
            calibrations = self.db.query(ProbePathLossCalibration).order_by(
                desc(ProbePathLossCalibration.calibrated_at)
            ).limit(50).all()

            path_loss_data = []
            for cal in calibrations:
                total += 1
                is_valid = cal.status == 'valid'
                if is_valid:
                    passed += 1

                # 计算探头数量
                num_probes = len(cal.probe_path_losses) if cal.probe_path_losses else 0

                path_loss_data.append({
                    'id': str(cal.id),
                    'chamber_id': str(cal.chamber_id),
                    'frequency_mhz': cal.frequency_mhz,
                    'num_probes': num_probes,
                    'validation_pass': is_valid,
                    'calibrated_at': str(cal.calibrated_at) if cal.calibrated_at else None,
                    'calibrated_by': cal.calibrated_by,
                    'valid_until': str(cal.valid_until) if cal.valid_until else None,
                    # SGH 参考天线
                    'sgh_model': cal.sgh_model,
                    'sgh_gain_dbi': cal.sgh_gain_dbi,
                    # 统计数据
                    'avg_path_loss_db': cal.avg_path_loss_db,
                    'max_path_loss_db': cal.max_path_loss_db,
                    'min_path_loss_db': cal.min_path_loss_db,
                    'std_dev_db': cal.std_dev_db,
                    # 环境条件
                    'temperature_celsius': cal.temperature_celsius,
                    'humidity_percent': cal.humidity_percent,
                })
            data['probe_calibration']['path_loss'] = path_loss_data

        # RF chain calibrations (CAL-03/04: LNA/PA gain calibration)
        if not calibration_type or calibration_type == 'rf_chain':
            calibrations = self.db.query(RFChainCalibration).order_by(
                desc(RFChainCalibration.calibrated_at)
            ).limit(50).all()

            rf_chain_data = []
            for cal in calibrations:
                total += 1
                is_valid = cal.status == 'valid'
                if is_valid:
                    passed += 1

                rf_chain_data.append({
                    'id': str(cal.id),
                    'chamber_id': str(cal.chamber_id),
                    'chain_type': cal.chain_type,
                    'frequency_mhz': cal.frequency_mhz,
                    'validation_pass': is_valid,
                    'calibrated_at': str(cal.calibrated_at) if cal.calibrated_at else None,
                    'calibrated_by': cal.calibrated_by,
                    'valid_until': str(cal.valid_until) if cal.valid_until else None,
                    # LNA 参数 (上行链路)
                    'has_lna': cal.has_lna,
                    'lna_model': cal.lna_model,
                    'lna_gain_measured_db': cal.lna_gain_measured_db,
                    'lna_noise_figure_db': cal.lna_noise_figure_db,
                    # PA 参数 (下行链路)
                    'has_pa': cal.has_pa,
                    'pa_model': cal.pa_model,
                    'pa_gain_measured_db': cal.pa_gain_measured_db,
                    'pa_p1db_measured_dbm': cal.pa_p1db_measured_dbm,
                    # 双工器参数
                    'has_duplexer': cal.has_duplexer,
                    'duplexer_insertion_loss_db': cal.duplexer_insertion_loss_db,
                    'duplexer_isolation_measured_db': cal.duplexer_isolation_measured_db,
                    # 链路总增益
                    'total_chain_gain_db': cal.total_chain_gain_db,
                    # 环境条件
                    'temperature_celsius': cal.temperature_celsius,
                })
            data['probe_calibration']['rf_chain'] = rf_chain_data

        # Multi-frequency path loss calibrations (CAL-08: frequency sweep)
        if not calibration_type or calibration_type == 'multi_freq_path_loss':
            calibrations = self.db.query(MultiFrequencyPathLoss).order_by(
                desc(MultiFrequencyPathLoss.calibrated_at)
            ).limit(50).all()

            multi_freq_data = []
            for cal in calibrations:
                total += 1
                is_valid = cal.status == 'valid'
                if is_valid:
                    passed += 1

                multi_freq_data.append({
                    'id': str(cal.id),
                    'chamber_id': str(cal.chamber_id),
                    'probe_id': cal.probe_id,
                    'polarization': cal.polarization,
                    'validation_pass': is_valid,
                    'calibrated_at': str(cal.calibrated_at) if cal.calibrated_at else None,
                    'calibrated_by': cal.calibrated_by,
                    'valid_until': str(cal.valid_until) if cal.valid_until else None,
                    # 频率范围
                    'freq_start_mhz': cal.freq_start_mhz,
                    'freq_stop_mhz': cal.freq_stop_mhz,
                    'freq_step_mhz': cal.freq_step_mhz,
                    'num_points': cal.num_points,
                })
            data['probe_calibration']['multi_freq_path_loss'] = multi_freq_data

        # Summary
        data['execution_summary'] = {
            'total_executions': total,
            'passed': passed,
            'failed': total - passed,
            'pending': 0,
            'pass_rate': (passed / total * 100) if total > 0 else 0,
        }

        return data

    def _collect_channel_data(
        self,
        session_id: Optional[UUID] = None,
        calibration_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Collect channel calibration data"""
        data = {
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'channel_calibration': {},
            'execution_summary': {},
        }

        total = 0
        passed = 0

        # Temporal calibrations
        if not calibration_type or calibration_type == 'temporal':
            query = self.db.query(TemporalChannelCalibration)
            if session_id:
                query = query.filter(TemporalChannelCalibration.session_id == session_id)
            calibrations = query.order_by(desc(TemporalChannelCalibration.calibrated_at)).limit(100).all()

            temporal_data = []
            for cal in calibrations:
                total += 1
                if cal.validation_pass:
                    passed += 1
                temporal_data.append({
                    'id': str(cal.id),
                    'scenario_type': cal.scenario_type,
                    'scenario_condition': cal.scenario_condition,
                    'fc_ghz': cal.fc_ghz,
                    'validation_pass': cal.validation_pass,
                    'calibrated_at': str(cal.calibrated_at) if cal.calibrated_at else None,
                    'rms_delay_spread_measured_ns': cal.measured_rms_delay_spread_ns,
                    'rms_delay_spread_target_ns': cal.reference_rms_delay_spread_ns,
                    'rms_delay_spread_error_percent': cal.rms_error_percent,
                })
            data['channel_calibration']['temporal'] = temporal_data

        # Doppler calibrations
        if not calibration_type or calibration_type == 'doppler':
            query = self.db.query(DopplerCalibration)
            if session_id:
                query = query.filter(DopplerCalibration.session_id == session_id)
            calibrations = query.order_by(desc(DopplerCalibration.calibrated_at)).limit(100).all()

            doppler_data = []
            for cal in calibrations:
                total += 1
                if cal.validation_pass:
                    passed += 1
                doppler_data.append({
                    'id': str(cal.id),
                    'velocity_kmh': cal.velocity_kmh,
                    'fc_ghz': cal.fc_ghz,
                    'validation_pass': cal.validation_pass,
                    'calibrated_at': str(cal.calibrated_at) if cal.calibrated_at else None,
                    'expected_doppler_hz': cal.expected_doppler_hz,
                    'spectral_correlation': cal.spectral_correlation,
                    'doppler_spread_error_percent': cal.doppler_spread_error_percent,
                })
            data['channel_calibration']['doppler'] = doppler_data

        # Spatial correlation calibrations
        if not calibration_type or calibration_type == 'spatial_correlation':
            query = self.db.query(SpatialCorrelationCalibration)
            if session_id:
                query = query.filter(SpatialCorrelationCalibration.session_id == session_id)
            calibrations = query.order_by(desc(SpatialCorrelationCalibration.calibrated_at)).limit(100).all()

            spatial_data = []
            for cal in calibrations:
                total += 1
                if cal.validation_pass:
                    passed += 1
                spatial_data.append({
                    'id': str(cal.id),
                    'scenario_type': cal.scenario_type,
                    'scenario_condition': cal.scenario_condition,
                    'antenna_spacing_wavelengths': cal.antenna_spacing_wavelengths,
                    'validation_pass': cal.validation_pass,
                    'calibrated_at': str(cal.calibrated_at) if cal.calibrated_at else None,
                    'measured_correlation': cal.measured_correlation,
                    'target_correlation': cal.target_correlation,
                })
            data['channel_calibration']['spatial_correlation'] = spatial_data

        # Angular spread calibrations
        if not calibration_type or calibration_type == 'angular_spread':
            query = self.db.query(AngularSpreadCalibration)
            if session_id:
                query = query.filter(AngularSpreadCalibration.session_id == session_id)
            calibrations = query.order_by(desc(AngularSpreadCalibration.calibrated_at)).limit(100).all()

            angular_data = []
            for cal in calibrations:
                total += 1
                if cal.validation_pass:
                    passed += 1
                angular_data.append({
                    'id': str(cal.id),
                    'scenario_type': cal.scenario_type,
                    'scenario_condition': cal.scenario_condition,
                    'validation_pass': cal.validation_pass,
                    'calibrated_at': str(cal.calibrated_at) if cal.calibrated_at else None,
                    'azimuth_spread_measured_deg': cal.azimuth_spread_measured_deg,
                    'azimuth_spread_target_deg': cal.azimuth_spread_target_deg,
                })
            data['channel_calibration']['angular_spread'] = angular_data

        # Quiet zone calibrations
        if not calibration_type or calibration_type == 'quiet_zone':
            query = self.db.query(ChannelQuietZoneCalibration)
            if session_id:
                query = query.filter(ChannelQuietZoneCalibration.session_id == session_id)
            calibrations = query.order_by(desc(ChannelQuietZoneCalibration.calibrated_at)).limit(100).all()

            qz_data = []
            for cal in calibrations:
                total += 1
                if cal.validation_pass:
                    passed += 1
                qz_data.append({
                    'id': str(cal.id),
                    'quiet_zone_shape': cal.quiet_zone_shape,
                    'quiet_zone_diameter_m': cal.quiet_zone_diameter_m,
                    'fc_ghz': cal.fc_ghz,
                    'validation_pass': cal.validation_pass,
                    'calibrated_at': str(cal.calibrated_at) if cal.calibrated_at else None,
                    'amplitude_uniformity_db': cal.amplitude_uniformity_db,
                    'phase_uniformity_deg': cal.phase_uniformity_deg,
                })
            data['channel_calibration']['quiet_zone'] = qz_data

        # EIS validations
        if not calibration_type or calibration_type == 'eis':
            query = self.db.query(EISValidation)
            if session_id:
                query = query.filter(EISValidation.session_id == session_id)
            calibrations = query.order_by(desc(EISValidation.measured_at)).limit(100).all()

            eis_data = []
            for cal in calibrations:
                total += 1
                if cal.validation_pass:
                    passed += 1
                eis_data.append({
                    'id': str(cal.id),
                    'dut_model': cal.dut_model,
                    'dut_type': cal.dut_type,
                    'fc_ghz': cal.fc_ghz,
                    'validation_pass': cal.validation_pass,
                    'measured_at': str(cal.measured_at) if cal.measured_at else None,
                    'eis_measured_dbm': cal.eis_measured_dbm,
                    'eis_reference_dbm': cal.eis_reference_dbm,
                    'eis_error_db': cal.eis_error_db,
                })
            data['channel_calibration']['eis'] = eis_data

        # Summary
        data['execution_summary'] = {
            'total_executions': total,
            'passed': passed,
            'failed': total - passed,
            'pending': 0,
            'pass_rate': (passed / total * 100) if total > 0 else 0,
        }

        return data

    def _calculate_overall_summary(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate overall summary from probe and channel data"""
        probe_summary = data.get('probe_summary', {})
        channel_summary = data.get('channel_summary', {})

        total = probe_summary.get('total_executions', 0) + channel_summary.get('total_executions', 0)
        passed = probe_summary.get('passed', 0) + channel_summary.get('passed', 0)
        failed = probe_summary.get('failed', 0) + channel_summary.get('failed', 0)

        return {
            'total_executions': total,
            'passed': passed,
            'failed': failed,
            'pending': 0,
            'pass_rate': (passed / total * 100) if total > 0 else 0,
            'probe_total': probe_summary.get('total_executions', 0),
            'probe_pass_rate': probe_summary.get('pass_rate', 0),
            'channel_total': channel_summary.get('total_executions', 0),
            'channel_pass_rate': channel_summary.get('pass_rate', 0),
        }

    def _create_calibration_template(self) -> Dict[str, Any]:
        """Create template configuration for comprehensive calibration report"""
        return {
            'page_size': 'A4',
            'page_orientation': 'portrait',
            'margins': {'left': 20, 'right': 20, 'top': 25, 'bottom': 25},
            'sections': [
                {
                    'type': 'cover',
                    'order': 0,
                    'title': '',
                },
                {
                    'type': 'execution_summary',
                    'order': 1,
                    'title': 'Calibration Summary',
                },
                {
                    'type': 'calibration_probe_summary',
                    'order': 2,
                    'title': 'Probe Calibration Results',
                    'page_break_after': True,
                },
                {
                    'type': 'calibration_channel_summary',
                    'order': 3,
                    'title': 'Channel Calibration Results',
                    'page_break_after': True,
                },
            ],
        }

    def _create_probe_template(self) -> Dict[str, Any]:
        """Create template for probe calibration report"""
        return {
            'page_size': 'A4',
            'page_orientation': 'portrait',
            'sections': [
                {'type': 'cover', 'order': 0},
                {'type': 'execution_summary', 'order': 1, 'title': 'Probe Calibration Summary'},
                {'type': 'calibration_probe_summary', 'order': 2, 'title': 'Calibration Details'},
            ],
        }

    def _create_channel_template(self) -> Dict[str, Any]:
        """Create template for channel calibration report"""
        return {
            'page_size': 'A4',
            'page_orientation': 'portrait',
            'sections': [
                {'type': 'cover', 'order': 0},
                {'type': 'execution_summary', 'order': 1, 'title': 'Channel Calibration Summary'},
                {'type': 'calibration_channel_summary', 'order': 2, 'title': 'Calibration Details'},
            ],
        }

    def _create_chamber_template(self) -> Dict[str, Any]:
        """Create template for chamber calibration report"""
        return {
            'page_size': 'A4',
            'page_orientation': 'portrait',
            'margins': {'left': 20, 'right': 20, 'top': 25, 'bottom': 25},
            'sections': [
                {
                    'type': 'cover',
                    'order': 0,
                },
                {
                    'type': 'chamber_info',
                    'order': 1,
                    'title': 'Chamber Configuration',
                },
                {
                    'type': 'execution_summary',
                    'order': 2,
                    'title': 'Calibration Summary',
                },
                {
                    'type': 'calibration_path_loss',
                    'order': 3,
                    'title': 'Path Loss Calibration',
                    'description': 'SGH to probe spatial path loss measurements',
                },
                {
                    'type': 'calibration_rf_chain',
                    'order': 4,
                    'title': 'RF Chain Calibration',
                    'description': 'Uplink (LNA) and Downlink (PA) gain measurements',
                    'page_break_after': True,
                },
                {
                    'type': 'calibration_multi_frequency',
                    'order': 5,
                    'title': 'Multi-Frequency Path Loss',
                    'description': 'Frequency sweep calibration data',
                },
            ],
        }

    # ==================== CAL-09: 数据导出与合规功能 ====================

    def export_calibration_data(
        self,
        chamber_id: Optional[UUID] = None,
        export_format: str = "json",
        output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        导出校准数据
        
        Args:
            chamber_id: 可选的暗室 ID 过滤
            export_format: 导出格式 (json, csv)
            output_path: 输出路径
            
        Returns:
            导出结果
        """
        import json
        import csv
        
        # 收集数据
        if chamber_id:
            data = self._collect_chamber_calibration_data(chamber_id)
        else:
            data = self._collect_probe_data()
        
        # 生成输出路径
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = "data/exports/calibration"
            os.makedirs(output_dir, exist_ok=True)
            output_path = f"{output_dir}/calibration_export_{timestamp}.{export_format}"
        
        if export_format == "json":
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        elif export_format == "csv":
            # 针对 CSV 格式，展平数据结构
            flat_data = self._flatten_calibration_data(data)
            if flat_data:
                with open(output_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=flat_data[0].keys())
                    writer.writeheader()
                    writer.writerows(flat_data)
        else:
            return {
                "success": False,
                "error": f"不支持的导出格式: {export_format}"
            }
        
        return {
            "success": True,
            "format": export_format,
            "output_path": output_path,
            "record_count": len(self._flatten_calibration_data(data)),
            "exported_at": datetime.now().isoformat()
        }

    def generate_calibration_certificate(
        self,
        chamber_id: UUID,
        certificate_number: Optional[str] = None,
        issued_by: str = "MPAC OTA Test System",
        output_path: Optional[str] = None,
    ) -> str:
        """
        生成 ISO 格式校准证书
        
        Args:
            chamber_id: 暗室配置 ID
            certificate_number: 证书编号
            issued_by: 签发机构
            output_path: 输出路径
            
        Returns:
            证书文件路径
        """
        from app.models.chamber import ChamberConfiguration
        
        # 获取暗室信息
        chamber = self.db.query(ChamberConfiguration).filter(
            ChamberConfiguration.id == chamber_id
        ).first()
        
        if not chamber:
            raise ValueError(f"Chamber not found: {chamber_id}")
        
        # 生成证书编号
        if not certificate_number:
            certificate_number = f"CAL-{datetime.now().strftime('%Y%m%d')}-{str(chamber_id)[:8].upper()}"
        
        # 收集校准数据
        cal_data = self._collect_chamber_calibration_data(chamber_id)
        
        # 构建证书数据
        certificate_data = {
            'title': '校准证书 / Calibration Certificate',
            'certificate_number': certificate_number,
            'issued_by': issued_by,
            'issued_date': datetime.now().strftime('%Y-%m-%d'),
            'valid_until': (datetime.now().replace(year=datetime.now().year + 1)).strftime('%Y-%m-%d'),
            'chamber_info': {
                'name': chamber.name,
                'type': chamber.chamber_type,
                'id': str(chamber.id),
            },
            'calibration_summary': cal_data.get('execution_summary', {}),
            'calibration_items': [],
            'compliance_statement': (
                "本证书证明上述校准项目符合以下标准要求：\n"
                "This certificate certifies that the above calibration items comply with:\n"
                "- 3GPP TS 38.521-4 (NR User Equipment OTA conformance)\n"
                "- CTIA Test Plan for Wireless Device OTA Performance\n"
                "- ISO/IEC 17025 (测量能力和校准实验室能力)"
            ),
            'notes': (
                "校准有效期内，应按规定周期进行复校验证。\n"
                "环境条件变化可能影响校准结果的有效性。"
            ),
        }
        
        # 添加校准项目列表
        for cal_type, calibrations in cal_data.get('chamber_calibration', {}).items():
            if calibrations:
                latest = calibrations[0] if isinstance(calibrations, list) else calibrations
                certificate_data['calibration_items'].append({
                    'type': cal_type,
                    'status': '合格' if latest.get('validation_pass') else '待校准',
                    'last_calibration': latest.get('calibrated_at'),
                    'valid_until': latest.get('valid_until'),
                })
        
        # 生成输出路径
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = "data/certificates"
            os.makedirs(output_dir, exist_ok=True)
            output_path = f"{output_dir}/certificate_{chamber.name}_{timestamp}.pdf"
        
        # 创建证书模板
        template = self._create_certificate_template()
        
        # 生成 PDF
        return self.pdf_generator.generate_report(certificate_data, template, output_path)

    def generate_audit_report(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        output_path: Optional[str] = None,
    ) -> str:
        """
        生成校准审计报告
        
        记录指定时间段内的所有校准活动。
        
        Args:
            start_date: 起始日期
            end_date: 结束日期
            output_path: 输出路径
            
        Returns:
            报告文件路径
        """
        if not start_date:
            start_date = datetime.now().replace(day=1)  # 本月初
        if not end_date:
            end_date = datetime.now()
        
        # 收集所有校准数据
        all_data = self._collect_probe_data()
        
        # 过滤时间范围
        filtered_calibrations = []
        for cal_type, calibrations in all_data.get('probe_calibration', {}).items():
            for cal in calibrations:
                cal_date_str = cal.get('calibrated_at')
                if cal_date_str:
                    try:
                        cal_date = datetime.fromisoformat(cal_date_str.replace(' ', 'T'))
                        if start_date <= cal_date <= end_date:
                            cal['calibration_type'] = cal_type
                            filtered_calibrations.append(cal)
                    except (ValueError, TypeError):
                        pass
        
        # 统计
        total = len(filtered_calibrations)
        passed = sum(1 for c in filtered_calibrations if c.get('validation_pass'))
        
        audit_data = {
            'title': '校准审计报告 / Calibration Audit Report',
            'report_type': 'Audit',
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'period': {
                'start': start_date.strftime('%Y-%m-%d'),
                'end': end_date.strftime('%Y-%m-%d'),
            },
            'summary': {
                'total_calibrations': total,
                'passed': passed,
                'failed': total - passed,
                'pass_rate': (passed / total * 100) if total > 0 else 0,
            },
            'calibrations': filtered_calibrations,
        }
        
        # 生成输出路径
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = "data/reports/audit"
            os.makedirs(output_dir, exist_ok=True)
            output_path = f"{output_dir}/audit_report_{timestamp}.pdf"
        
        template = self._create_calibration_template()
        return self.pdf_generator.generate_report(audit_data, template, output_path)

    def _flatten_calibration_data(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """将嵌套的校准数据展平为 CSV 友好格式"""
        flat_list = []
        
        for section_key in ['probe_calibration', 'chamber_calibration', 'channel_calibration']:
            section = data.get(section_key, {})
            for cal_type, calibrations in section.items():
                if isinstance(calibrations, list):
                    for cal in calibrations:
                        flat_record = {
                            'section': section_key,
                            'calibration_type': cal_type,
                        }
                        flat_record.update(cal)
                        flat_list.append(flat_record)
        
        return flat_list

    def _create_certificate_template(self) -> Dict[str, Any]:
        """创建校准证书模板"""
        return {
            'page_size': 'A4',
            'margins': {'top': 2, 'bottom': 2, 'left': 2, 'right': 2},
            'header': {
                'title': '校准证书',
                'show_logo': True,
            },
            'footer': {
                'show_page_numbers': True,
                'text': 'Calibration Certificate - Confidential',
            },
            'sections': [
                {
                    'type': 'certificate_header',
                    'order': 1,
                    'title': 'Certificate Information',
                },
                {
                    'type': 'calibration_items',
                    'order': 2,
                    'title': 'Calibration Items',
                },
                {
                    'type': 'compliance_statement',
                    'order': 3,
                    'title': 'Compliance Statement',
                },
            ],
        }
