"""只读完整校准路径；未保存草稿不从客户端导入。"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.route_calibration import RouteSelection, RouteApplicationPreview
from app.services.calibration.route_calibration import list_route_selections, RouteScopeConflict, evaluate_route_application
from app.services.calibration.configuration_scope import build_calibration_scope

router = APIRouter(prefix='/lab-profiles', tags=['拓扑校准路径'])


@router.get('/{lab_profile_id}/route-calibration-paths', response_model=list[RouteSelection])
def paths(lab_profile_id: UUID, topology_id: UUID, operating_mode: str, db: Session = Depends(get_db)):
    try:
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
