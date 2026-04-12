"""
Calibration Report Generator Tests

Tests for the calibration report generation functionality.
"""

import pytest
import os
from datetime import datetime

from app.services.pdf_generator import PDFGenerator


class TestPDFGeneratorCalibrationSections:
    """Tests for PDF generator calibration sections"""

    def test_generate_calibration_probe_section(self):
        """Test generating probe calibration section"""
        generator = PDFGenerator()

        data = {
            'probe_calibration': {
                'amplitude': [
                    {
                        'probe_id': 0,
                        'polarization': 'V',
                        'validation_pass': True,
                        'calibrated_at': '2026-01-18 12:00:00',
                    },
                    {
                        'probe_id': 1,
                        'polarization': 'V',
                        'validation_pass': False,
                        'calibrated_at': '2026-01-18 12:00:00',
                    },
                ],
            },
            'probe_summary': {
                'total_executions': 2,
                'passed': 1,
                'failed': 1,
                'pass_rate': 50.0,
            },
        }

        elements = generator._generate_calibration_probe_section(data)
        assert len(elements) > 0

    def test_generate_calibration_probe_section_all_types(self):
        """Test generating probe calibration section with all types"""
        generator = PDFGenerator()

        data = {
            'probe_calibration': {
                'amplitude': [
                    {'probe_id': 0, 'polarization': 'V', 'validation_pass': True, 'calibrated_at': '2026-01-18'},
                ],
                'phase': [
                    {'probe_id': 1, 'reference_probe_id': 0, 'validation_pass': True, 'calibrated_at': '2026-01-18'},
                ],
                'polarization': [
                    {'probe_id': 0, 'validation_pass': True, 'calibrated_at': '2026-01-18'},
                ],
                'pattern': [
                    {'probe_id': 0, 'validation_pass': True, 'calibrated_at': '2026-01-18'},
                ],
                'link': [
                    {'probe_id': None, 'calibration_type': 'weekly', 'validation_pass': True, 'calibrated_at': '2026-01-18'},
                ],
            },
            'probe_summary': {
                'total_executions': 5,
                'passed': 5,
                'failed': 0,
                'pass_rate': 100.0,
            },
        }

        elements = generator._generate_calibration_probe_section(data)
        assert len(elements) > 0

    def test_generate_calibration_probe_section_empty(self):
        """Test generating probe calibration section with no data"""
        generator = PDFGenerator()
        data = {'probe_calibration': {}}
        elements = generator._generate_calibration_probe_section(data)
        assert len(elements) > 0  # Should have "No data" message

    def test_generate_calibration_channel_section(self):
        """Test generating channel calibration section"""
        generator = PDFGenerator()

        data = {
            'channel_calibration': {
                'temporal': [
                    {
                        'scenario_type': 'UMa',
                        'scenario_condition': 'LOS',
                        'fc_ghz': 3.5,
                        'rms_delay_spread_error_percent': 5.0,
                        'validation_pass': True,
                    },
                ],
                'doppler': [
                    {
                        'velocity_kmh': 120,
                        'fc_ghz': 3.5,
                        'max_doppler_measured_hz': 194.4,
                        'max_doppler_target_hz': 194.4,
                        'validation_pass': True,
                    },
                ],
            },
            'channel_summary': {
                'total_executions': 2,
                'passed': 2,
                'failed': 0,
                'pass_rate': 100.0,
            },
        }

        elements = generator._generate_calibration_channel_section(data)
        assert len(elements) > 0

    def test_generate_calibration_channel_section_all_types(self):
        """Test generating channel calibration section with all types"""
        generator = PDFGenerator()

        data = {
            'channel_calibration': {
                'temporal': [
                    {'scenario_type': 'UMa', 'scenario_condition': 'LOS', 'fc_ghz': 3.5,
                     'rms_delay_spread_error_percent': 5.0, 'validation_pass': True},
                ],
                'doppler': [
                    {'velocity_kmh': 120, 'fc_ghz': 3.5,
                     'max_doppler_measured_hz': 194.4, 'max_doppler_target_hz': 194.4, 'validation_pass': True},
                ],
                'spatial_correlation': [
                    {'scenario_type': 'UMa', 'scenario_condition': 'NLOS', 'antenna_spacing_wavelengths': 0.5,
                     'measured_correlation': 0.7, 'validation_pass': True},
                ],
                'angular_spread': [
                    {'scenario_type': 'UMa', 'scenario_condition': 'NLOS',
                     'azimuth_spread_measured_deg': 25.0, 'azimuth_spread_target_deg': 22.0, 'validation_pass': True},
                ],
                'quiet_zone': [
                    {'quiet_zone_shape': 'sphere', 'quiet_zone_diameter_m': 1.0,
                     'amplitude_uniformity_db': 0.5, 'phase_uniformity_deg': 10.0, 'validation_pass': True},
                ],
                'eis': [
                    {'dut_model': 'Test DUT', 'dut_type': 'vehicle',
                     'eis_measured_dbm': -100.0, 'eis_error_db': 0.3, 'validation_pass': True},
                ],
            },
            'channel_summary': {
                'total_executions': 6,
                'passed': 6,
                'failed': 0,
                'pass_rate': 100.0,
            },
        }

        elements = generator._generate_calibration_channel_section(data)
        assert len(elements) > 0

    def test_generate_calibration_channel_section_empty(self):
        """Test generating channel calibration section with no data"""
        generator = PDFGenerator()
        data = {'channel_calibration': {}}
        elements = generator._generate_calibration_channel_section(data)
        assert len(elements) > 0  # Should have "No data" message

    def test_generate_calibration_channel_section_failed_items(self):
        """Test channel section with failed calibrations"""
        generator = PDFGenerator()

        data = {
            'channel_calibration': {
                'temporal': [
                    {'scenario_type': 'UMa', 'scenario_condition': 'LOS', 'fc_ghz': 3.5,
                     'rms_delay_spread_error_percent': 15.0, 'validation_pass': False},
                    {'scenario_type': 'UMa', 'scenario_condition': 'NLOS', 'fc_ghz': 3.5,
                     'rms_delay_spread_error_percent': 5.0, 'validation_pass': True},
                ],
            },
            'channel_summary': {
                'total_executions': 2,
                'passed': 1,
                'failed': 1,
                'pass_rate': 50.0,
            },
        }

        elements = generator._generate_calibration_channel_section(data)
        assert len(elements) > 0


class TestCalibrationReportAPI:
    """Tests for calibration report API endpoints"""

    @pytest.fixture
    def client(self):
        """Create test client with initialized database"""
        from fastapi.testclient import TestClient
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        from app.db.database import Base, get_db
        from app.main import app

        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        def override_get_db():
            db = TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db

        yield TestClient(app)

        app.dependency_overrides.clear()

    def test_generate_comprehensive_report_endpoint(self, client):
        """Test comprehensive report generation endpoint"""
        response = client.post(
            "/api/v1/calibration-reports/comprehensive",
            json={
                "include_probe": True,
                "include_channel": True,
                "title": "Test Report"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "report_path" in data

    def test_generate_probe_report_endpoint(self, client):
        """Test probe report generation endpoint"""
        response = client.post(
            "/api/v1/calibration-reports/probe",
            json={}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_generate_channel_report_endpoint(self, client):
        """Test channel report generation endpoint"""
        response = client.post(
            "/api/v1/calibration-reports/channel",
            json={}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_generate_probe_report_with_filter(self, client):
        """Test probe report with filters"""
        response = client.post(
            "/api/v1/calibration-reports/probe",
            json={
                "probe_ids": [0, 1, 2],
                "calibration_type": "amplitude"
            }
        )
        assert response.status_code == 200

    def test_generate_channel_report_with_filter(self, client):
        """Test channel report with filters"""
        response = client.post(
            "/api/v1/calibration-reports/channel",
            json={
                "calibration_type": "temporal"
            }
        )
        assert response.status_code == 200
