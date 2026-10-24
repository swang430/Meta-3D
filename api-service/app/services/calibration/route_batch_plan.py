"""PC06A1：零硬件I/O构造保存路线的逐项清单；start复用同一函数重核。"""
import hashlib
import json
from uuid import UUID

from sqlalchemy.orm import Session
from app.models.lab_profile import LabProfile
from app.models.switch_topology import SwitchTopology
from app.schemas.fixed_route_acquisition import FixedRouteRequest
from app.schemas.route_batch import BatchPlanRequest,BatchPlan,BatchPlanItem
from app.services.calibration.configuration_scope import build_selected_route_calibration_scope
from app.services.calibration.route_calibration import resolve_explicit_route_selection,route_switch_steps,RouteScopeConflict
from app.services.declared_rf_routes import resolve_saved_rf_path


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def build_batch_plan(db: Session,lab_id: UUID,request: BatchPlanRequest,hal) -> BatchPlan:
    """HAL参数仅保留共用接口，预览绝不查询/写入任何硬件。

    switch_steps是保存映射声明，不是本次写读receipt，也不是现场RF验收。
    Task3在实际转换时核验身份/互锁、操作员接线声明及本次严格写读。
    """
    lab=db.get(LabProfile,lab_id)
    topology=db.get(SwitchTopology,request.topology_id)
    if lab is None or topology is None:
        raise LookupError('实验室或拓扑不存在')
    if topology.chamber_id!=lab.chamber_config_id:
        raise RouteScopeConflict('拓扑不属于当前实验室绑定的暗室')
    mode=next((m for m in topology.operating_modes or [] if m.get('id')==request.operating_mode),None)
    if mode is None:
        raise ValueError('请选择保存的正常测试模式')
    active_ids=mode.get('active_connections') or [c['id'] for c in topology.connections or [] if request.operating_mode in c.get('modes',[])]
    active=[c for c in topology.connections or [] if c.get('id') in active_ids]
    references={(r.chain_id,r.frequency_mhz):r for r in request.references}
    items=[]
    selected=[]
    for chain in sorted(request.chain_ids):
        _,edges=resolve_saved_rf_path(topology.nodes or [],active,chain)
        route=resolve_explicit_route_selection(db,lab_id,topology.id,request.operating_mode,chain,[e['id'] for e in edges])
        scope=build_selected_route_calibration_scope(db,lab_id,request.operating_mode,topology_id=topology.id,chain_id=chain)
        if not scope.configuration_complete:
            raise ValueError('当前单项配置不完整：'+'；'.join(scope.warnings))
        steps=route_switch_steps(db,topology,route.nodes,route.connections,lab)
        selected.append((route,steps))
        for frequency in sorted(request.frequencies_mhz):
            ref=references[(chain,frequency)]
            child=FixedRouteRequest(chain_id=chain,configuration_digest=scope.digest,topology_id=topology.id,
                operating_mode=request.operating_mode,route_digest=route.route_digest,frequency_mhz=frequency,
                requested_power_dbm=request.requested_power_dbm,reference_antenna=ref.reference_antenna,
                receive_cable_loss_db=ref.receive_cable_loss_db,receive_cable_source=ref.receive_cable_source,
                fixed_route_confirmed=request.fixed_route_confirmed,safety_confirmed=request.safety_confirmed,
                sample_count=request.sample_count)
            items.append(BatchPlanItem(item_id=_digest([chain,frequency]),request=child,route_selection=route,
                configuration_scope=scope,switch_steps=steps,transition_kind='manual',
                transition_reasons=('核对本项参考天线位置与接线；自动资格须由本次作业严格写读核验',)))
    # 批复用同一物理CE只能由同继电器不同位置的互斥保存映射实现，不把分配器当开关。
    from app.hal.propsim_f64 import RealPropsimF64Driver
    for index,(route,steps) in enumerate(selected):
        for other,other_steps in selected[:index]:
            if RealPropsimF64Driver._ce_port_to_output_num(route.ce_port)!=RealPropsimF64Driver._ce_port_to_output_num(other.ce_port):
                continue
            exclusive=any(a['category_id']==b['category_id'] and
                a['mapping'].get('switch_id',a['mapping'].get('relay'))==b['mapping'].get('switch_id',b['mapping'].get('relay')) and
                a['mapping']['input_port']==b['mapping']['input_port'] and
                a['mapping'].get('output_port',a['mapping'].get('position'))!=b['mapping'].get('output_port',b['mapping'].get('position'))
                for a in steps for b in other_steps)
            if not exclusive:
                raise ValueError('批复用CE输出必须保存互斥开关映射')
    payload=dict(version=1,lab_profile_id=str(lab_id),topology_id=str(topology.id),operating_mode=request.operating_mode,
        items=[i.model_dump(mode='json') for i in items])
    digest=_digest(payload)
    if request.preview_digest is not None and request.preview_digest!=digest:
        raise ValueError('预览摘要已变化，请重新预览')
    return BatchPlan(lab_profile_id=lab_id,topology_id=topology.id,items=items,preview_digest=digest)
