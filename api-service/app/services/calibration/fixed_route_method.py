"""仅计算人工参考值；不访问HAL/数据库、不生成旧路损证书。"""
import math

from app.schemas.calibration_method import FixedRouteCalibrationDeclaration, FixedRouteCalibrationPreview


def preview_fixed_route(request: FixedRouteCalibrationDeclaration) -> FixedRouteCalibrationPreview:
    # 用户批准的方法见 docs/design/2026-10-22-pc-02a-calibration-method-reference.md §3。
    # 开关、PA、探头和参考天线作用已包含于整路，不再重复加减标称增益。
    value = request.ce_output_power_dbm - (request.sa_input_power_dbm + request.receive_cable_loss_db)
    if not math.isfinite(value):
        raise ValueError('参考值过大，无法计算有限的路径损耗或增益')
    return FixedRouteCalibrationPreview(
        declaration=request, net_loss_db=value,
        warning='仅按人工输入计算；未连接仪器、未核验开关通路或参考量，不是实测校准，不保存证书、不应用补偿、不改变就绪状态。',
    )
