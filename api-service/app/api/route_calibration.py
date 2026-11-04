"""保存路径的采集采用；未保存草稿不从客户端导入，不签认证资格。"""
from uuid import UUID
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Response, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.route_calibration import RouteSelection, RouteApplicationPreview, ConfirmRouteApplication, RouteApplicationRecord
from app.services.calibration.route_calibration import (list_route_selections,list_individual_route_selections, RouteScopeConflict,
    evaluate_route_application,confirm_route_application,list_route_applications,RouteApplicationConflict)
from app.services.calibration.configuration_scope import build_calibration_scope,build_selected_route_calibration_scope
from app.schemas.route_calibration import RevokeRouteCalibration, RouteRevocationRecord
from app.services.calibration.route_revocation import read_route_revocation, revoke_route_calibration
from app.schemas.route_calibration import RouteCalibrationAvailability, RouteAvailabilityRow
from app.services.calibration.route_calibration import resolve_effective_route_compensation

router = APIRouter(prefix='/lab-profiles', tags=['拓扑校准路径'])


@router.get('/{lab_profile_id}/route-calibration-availability', response_model=RouteCalibrationAvailability,
            responses={400: {'description': '当前目标或配置无法解析', 'content': {'application/json': {
                'schema': {'type': 'object', 'properties': {'detail': {'type': 'string'}}, 'required': ['detail']}}}}})
def calibration_availability(lab_profile_id: UUID,
        frequency_mhz: float = Query(..., gt=0, allow_inf_nan=False),
        operating_mode: str = Query('mimo_ota', min_length=1), db: Session = Depends(get_db)):
    """只读预览精确目标频点的逐链选源；不是完整方法适用性、认证或硬件执行授权。"""
    try:
        selection = resolve_effective_route_compensation(db, lab_profile_id, operating_mode,
                                                        frequency_mhz, lock_sources=False)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    fields = RouteAvailabilityRow.model_fields
    rows = [RouteAvailabilityRow.model_validate({key: row[key] for key in fields})
            for row in selection['route_entries']]
    covered = sum(row.source_kind != 'unavailable' and row.value_db is not None
                  and row.measurement_provenance == 'real' for row in rows)
    return RouteCalibrationAvailability(lab_profile_id=lab_profile_id,
        topology_id=selection['topology_id'], operating_mode=operating_mode, frequency_mhz=frequency_mhz,
        checked_at=selection['selected_at'], routes=rows, required_chain_count=len(rows),
        covered_chain_count=covered, all_chains_have_sources=bool(rows) and covered == len(rows),
        warnings=selection['warnings'], limitations=[
            '只核对目标精确频点的逐链净损耗来源；不证明完整带宽、空间范围或不确定度覆盖。',
            '来源齐全不代表计量认证或正式通过；执行仍须重新检查、冻结并通过既有资格门。',
            '预览是当前读取时点，后续配置或撤销可能变化，不代替执行冻结。'])


@router.get('/{lab_profile_id}/route-calibration-applications/{application_id}/revocation',
            response_model=RouteRevocationRecord | None,
            responses={404: {'description': '本实验室中没有这条采用记录'}})
def revocation_status(lab_profile_id: UUID, application_id: UUID, db: Session = Depends(get_db)):
    """读取独立撤销状态；null仅表示没有撤销记录，不授予校准资格。"""
    try:
        return read_route_revocation(db, lab_profile_id, application_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post('/{lab_profile_id}/route-calibration-applications/{application_id}/revocation',
             response_model=RouteRevocationRecord, status_code=201,
             responses={200: {'model': RouteRevocationRecord, 'description': '同理由重试，返回原撤销记录'},
                        404: {'description': '本实验室中没有这条采用记录'},
                        409: {'description': '该次采集已按另一理由撤销'}})
def revoke_application(lab_profile_id: UUID, application_id: UUID, body: RevokeRouteCalibration,
                       response: Response, db: Session = Depends(get_db)):
    """停止同次采集的后续选用，不修改原始采用及历史执行。"""
    try:
        record, created = revoke_route_calibration(db, lab_profile_id, application_id, body)
        response.status_code = 201 if created else 200
        return record
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RouteApplicationConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get('/{lab_profile_id}/route-calibration-paths', response_model=list[RouteSelection])
def paths(lab_profile_id: UUID, topology_id: UUID, operating_mode: str, db: Session = Depends(get_db),
          selection_scope: Literal['simultaneous','individual']='simultaneous'):
    try:
        if selection_scope=='individual':
            routes=list_individual_route_selections(db,lab_profile_id,topology_id,operating_mode)
            return [route.model_copy(update={'configuration_digest':build_selected_route_calibration_scope(
                db,lab_profile_id,operating_mode,topology_id=topology_id,chain_id=route.chain_id).digest}) for route in routes]
        routes = list_route_selections(db,lab_profile_id,topology_id,operating_mode)
        scope = build_calibration_scope(db,lab_profile_id,operating_mode,topology_id=topology_id)
        return [route.model_copy(update={'configuration_digest':scope.digest}) for route in routes]
    except RouteScopeConflict as exc:
        raise HTTPException(409,str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404,str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422,f'模式 {operating_mode}：{exc}') from exc


@router.get('/{lab_profile_id}/fixed-route-acquisitions/{run_id}/application-preview',response_model=RouteApplicationPreview)
def application_preview(lab_profile_id: UUID,run_id: UUID,db: Session=Depends(get_db)):
    try:
        return evaluate_route_application(db,lab_profile_id,run_id)
    except LookupError as exc:
        raise HTTPException(404,str(exc)) from exc


@router.post('/{lab_profile_id}/route-calibration-applications',response_model=RouteApplicationRecord,status_code=201)
def confirm_application(lab_profile_id: UUID,body: ConfirmRouteApplication,response: Response,db: Session=Depends(get_db)):
    try:
        # 当前API没有认证身份链，不能把网络地址或固定姓名伪装成已核验操作员。
        record,created=confirm_route_application(db,lab_profile_id,body,actor=None)
        response.status_code=201 if created else 200
        return record
    except LookupError as exc:
        raise HTTPException(404,str(exc)) from exc
    except RouteApplicationConflict as exc:
        raise HTTPException(409,str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc


@router.get('/{lab_profile_id}/route-calibration-applications',response_model=list[RouteApplicationRecord])
def application_history(lab_profile_id: UUID,topology_id: UUID,chain_id: str,db: Session=Depends(get_db)):
    try:
        return list_route_applications(db,lab_profile_id,topology_id,chain_id)
    except LookupError as exc:
        raise HTTPException(404,str(exc)) from exc
