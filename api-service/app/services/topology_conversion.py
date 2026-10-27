"""不接触数据库或HAL的旧图转换；仅修改显式白名单，原量值和引用不迁移。"""
from copy import deepcopy
from hashlib import sha256
import json
from app.schemas.topology_conversion import TopologyConversionRequest
from app.schemas.topology_nominal import same_json, MISSING
from app.services.topology_loss import effective_connection_loss

GRAPH_FIELDS=('nodes','connections','operating_modes')


def conversion_source_digest(source: dict) -> str:
    def numbers(value):
        # 与现有same_json一致：JSON数字1和1.0等价，bool仍独立。
        if type(value) is float and value.is_integer():
            return int(value)
        if isinstance(value,dict):
            return {key:numbers(item) for key,item in value.items()}
        if isinstance(value,list):
            return [numbers(item) for item in value]
        return value
    payload={key:source[key] for key in ('id','chamber_id','switch_category_id',*GRAPH_FIELDS)}
    return sha256(json.dumps(numbers(payload),sort_keys=True,ensure_ascii=False,
                             separators=(',',':'),allow_nan=False).encode()).hexdigest()


def build_conversion(source: dict, changes: TopologyConversionRequest) -> dict:
    candidate={key:deepcopy(source[key]) for key in GRAPH_FIELDS}
    nodes={row['id']:row for row in candidate['nodes']}
    edges={row['id']:row for row in candidate['connections']}
    groups=({'ce_port','channel_emulator'},{'bse_port','communication_tester'},{'sa_port','signal_analyzer'})
    for edit in changes.nodes:
        if edit.node_id not in nodes:
            raise ValueError(f'未知器件ID：{edit.node_id}')
        node=nodes[edit.node_id]
        values=edit.model_dump(exclude_unset=True)
        target=values.pop('target_type',None)
        values.pop('node_id')
        if target is not None:
            if not any(node['type'] in group and target in group for group in groups):
                raise ValueError(f'器件 {edit.node_id} 不能跨类别转换')
            if (node['type']=='ce_port' and target=='channel_emulator'
                    and not node.get('params',{}).get('ce_port') and not values.get('ce_port')):
                raise ValueError(f'器件 {edit.node_id} 转换须显式提交ce_port，不从label推断')
            node['type']=target
        if values:
            node.setdefault('params',{}).update(values)
    touched_ownership=set()
    for edit in changes.connections:
        if edit.connection_id not in edges:
            raise ValueError(f'未知连线ID：{edit.connection_id}')
        edge=edges[edit.connection_id]
        values=edit.model_dump(exclude_unset=True)
        values.pop('connection_id'); values.pop('same_physical_cable_confirmed',None)
        if 'loss_owner_connection_id' in values:
            touched_ownership.update((edit.connection_id,edge.get('loss_owner_connection_id'),values['loss_owner_connection_id']))
            if values['loss_owner_connection_id'] is None:
                edge.pop('loss_owner_connection_id',None)
                values.pop('loss_owner_connection_id')
        edge.update(values)
    if any(edit.connection_id in touched_ownership and 'cable_loss_db' in edit.model_fields_set
           for edit in changes.connections):
        raise ValueError('设置或撤销归属不能同时修改本组两侧原损耗，请分步操作')
    return candidate


def conversion_differences(source, candidate):
    differences=[]
    for kind in ('nodes','connections'):
        old={row['id']:row for row in source[kind]}
        for row in candidate[kind]:
            before=old[row['id']]
            pairs=[('',before,row)] if kind=='connections' else [('',before,row),('params.',before.get('params',{}),row.get('params',{}))]
            for prefix,left,right in pairs:
                for key in left.keys() | right.keys():
                    if kind=='nodes' and not prefix and key=='params':
                        continue
                    if not same_json(left.get(key,MISSING),right.get(key,MISSING)):
                        item=dict(object_kind=kind,object_id=row['id'],field=prefix+key,
                                  before_present=key in left,after=right.get(key))
                        if key in left:item['before']=deepcopy(left[key])
                        differences.append(item)
    return differences


def conversion_warnings(source,candidate):
    def shown(value):
        return '未知' if value is None else str(value)
    warnings=['仅操作员声明，不证明实物导通、量值真实性或校准资格；配置变化需复核。']
    for node in candidate['nodes']:
        if not node.get('params',{}).get('ports'):
            warnings.append(f'器件 {node["id"]} 端口未声明')
    edges={edge['id']:edge for edge in candidate['connections']}
    for edge in candidate['connections']:
        owner=edges.get(edge.get('loss_owner_connection_id'))
        if owner:
            warnings.append(f'归属 {edge["id"]} → {owner["id"]}：两侧原值保留，旧值不参与本组计算；'
                f'owner有效源={"calibrated_loss_db" if owner.get("calibrated_loss_db") is not None else "cable_loss_db"}，'
                f'有效值={shown(effective_connection_loss(owner))}。通用路径只计owner一次；'
                '正式旧binding仅末边引用owner时换源，不对上游多段求和；confirmed整链和历史不变。')
    # 预览复用真实消费者，不另写求和公式；未声明草稿不因无法运行变成非法图。
    from app.services.topology_service import TopologyService
    from app.services.topology_loss import loss_source_for_terminal
    before_service,after_service=TopologyService(source),TopologyService(candidate)
    for mode in candidate['operating_modes']:
        before={path.path_id:path for path in before_service.resolve_paths(mode['id'])}
        for path in after_service.resolve_paths(mode['id']):
            old=before.get(path.path_id)
            def terminal_value(graph,item):
                if item is None or not item.hops:return None
                selected=[edge.id for _,edge in item.hops]
                return effective_connection_loss(loss_source_for_terminal(
                    graph['nodes'],graph['connections'],selected))
            warnings.append(f'模式 {mode["id"]} 路径 {path.path_id}：通用总损耗 '
                f'{shown(old.total_loss_db if old else None)} → {shown(path.total_loss_db)} dB；'
                f'正式末边损耗 {shown(terminal_value(source,old))} → {shown(terminal_value(candidate,path))} dB；'
                'unknown不补零，历史confirmed整链不变。')
    return warnings
