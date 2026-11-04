"""四类未获独立方法资格的信道记录只读投影；原行保留。"""
from copy import deepcopy
from app.models.channel_calibration import DopplerCalibration, SpatialCorrelationCalibration, AngularSpreadCalibration, EISValidation

# 无独立方法/参考资格契约；不凭客户端、非Mock类或旧PASS授予正式资格。
METHODS = {
    'doppler': (DopplerCalibration, ('spectral_correlation', 'doppler_spread_error_percent'), 'measured_spectrum'),
    'spatial_correlation': (SpatialCorrelationCalibration, ('measured_correlation_magnitude', 'measured_correlation_phase_deg', 'samples', 'confidence_interval', 'magnitude_error', 'phase_error_deg'), None),
    'angular_spread': (AngularSpreadCalibration, ('fitted_mean_azimuth_deg', 'fitted_rms_angular_spread_deg', 'fitted_r_squared', 'rms_error_deg'), 'measured_aps'),
    'eis': (EISValidation, ('peak_eis_dbm', 'peak_azimuth_deg', 'peak_elevation_deg', 'median_eis_dbm', 'eis_spread_db'), 'eis_map'),
}

def channel_diagnostic_detail(row, kind):
    model, fields, array = METHODS[kind]
    fields = (*fields, 'validation_pass', 'valid_until')
    result = {c.name: getattr(row, c.name) for c in model.__table__.columns}
    provenance = deepcopy(row.diagnostic_provenance) if isinstance(row.diagnostic_provenance, dict) else {'source': 'unknown'}
    result['diagnostic_data'] = {
        'formal_eligible': False, 'method_status': 'unverified',
        'reason': '仅供诊断审计，未建立独立方法与参考资格',
        'provenance': provenance,
        'recorded_provenance': deepcopy(row.diagnostic_provenance),
        'recorded_results': {key: deepcopy(getattr(row, key)) for key in fields},
        'recorded_data': deepcopy(getattr(row, array)) if array else None,
        'recorded_status': row.status,
    }
    result.update({key: None for key in fields})
    if array: result[array] = {}
    result['status'] = 'unknown'
    return result

def channel_diagnostic_history(row, kind):
    detail = channel_diagnostic_detail(row, kind)
    return dict(calibration_id=row.id, calibration_type=kind,
        calibrated_at=row.measured_at if kind == 'eis' else row.calibrated_at,
        calibrated_by=row.measured_by if kind == 'eis' else row.calibrated_by,
        status='unknown', validation_pass=None,
        summary={'formal_status': 'UNKNOWN', 'diagnostic_data': detail['diagnostic_data']})
