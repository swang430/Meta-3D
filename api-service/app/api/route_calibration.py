"""保存路径的采集采用；未保存草稿不从客户端导入，不签认证资格。"""
from uuid import UUID
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.route_calibration import RouteSelection, RouteApplicationPreview, ConfirmRouteApplication, RouteApplicationRecord
from app.services.calibration.route_calibration import (list_route_selections,list_individual_route_selections, RouteScopeConflict,
    evaluate_route_application,confirm_route_application,list_route_applications,RouteApplicationConflict)
from app.services.calibration.configuration_scope import build_calibration_scope,build_selected_route_calibration_scope

router = APIRouter(prefix='/lab-profiles', tags=['拓扑校准路径'])


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
        raise HTTPException(422,str(exc)) from exc


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
