"""时域记录的正式消费边界；不修改保存的历史材料。

现有写方仅模拟PDP或measure_pdp工程代理，没有经核验的独立参考方法。
原始数组和历史判词保留为诊断，不能授予标准PDP资格。
"""
from copy import deepcopy
from types import SimpleNamespace
from app.models.channel_calibration import (TemporalChannelCalibration, DopplerCalibration, SpatialCorrelationCalibration, AngularSpreadCalibration, EISValidation)

FORMAL_FIELDS = (
    'measured_rms_delay_spread_ns', 'measured_max_delay_ns',
    'measured_num_clusters', 'measured_cluster_delays_ns', 'measured_cluster_powers_db',
    'rms_error_percent', 'cluster_count_match', 'validation_pass', 'valid_until',
)

def diagnostic_data(row):
    return dict(formal_eligible=False, method_status='unverified',
                reason='未建立独立参考与标准PDP测量方法；仅供诊断审计',
                recorded_pdp=deepcopy(row.measured_pdp),
                recorded_results={key: deepcopy(getattr(row,key,None)) for key in FORMAL_FIELDS},
                recorded_status=row.status)

def temporal_detail(row):
    result={c.name:getattr(row,c.name) for c in TemporalChannelCalibration.__table__.columns}
    result.update({key:None for key in FORMAL_FIELDS})
    result.update(measured_pdp={},status='unknown',diagnostic_data=diagnostic_data(row))
    return result

def temporal_history(row):
    return dict(calibration_id=row.id,calibration_type='temporal',calibrated_at=row.calibrated_at,
                calibrated_by=row.calibrated_by,status='unknown',validation_pass=None,
                summary=dict(scenario=f'{row.scenario_type} {row.scenario_condition}',rms_error_percent=None,
                             formal_status='UNKNOWN',diagnostic_data=diagnostic_data(row)))

def temporal_session_view(db,session):
    """会话读取与完成同源：现有信道写方均未建立正式方法资格。"""
    if session is None: return None
    result={c.name:getattr(session,c.name) for c in session.__table__.columns}
    result.update(overall_pass=None,total_calibrations=0,passed_calibrations=0,failed_calibrations=0)
    return SimpleNamespace(**result)
