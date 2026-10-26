import {Button,Group,Select,Stack,Text} from '@mantine/core';
import type {TopologyInternalPath,TopologyNode} from '../../api/switchTopologyService';
import {directionLabels,resolveNodePorts} from './nodePortHelpers';
import {noInternalForwardingTypes} from './internalPathHelpers';

interface Props {node:TopologyNode;disabled:boolean;onChange:(paths:TopologyInternalPath[])=>void;onRestore:()=>void}
/** 内部白名单只在原抽屉编辑，不创建 ReactFlow 外边或自动控制配置。 */
export function InternalPathFields({node,disabled,onChange,onRestore}:Props){
  const parsed=resolveNodePorts(node),raw=node.params.internal_paths;
  const paths:TopologyInternalPath[]=Array.isArray(raw)?raw:[];
  const forbidden=noInternalForwardingTypes.has(node.type);
  const change=(next:TopologyInternalPath[])=>{if(!disabled)onChange(next)};
  const options=(end:'from'|'to')=>parsed.ports.filter(id=>parsed.effectiveDirections[id]!== (end==='from'?'output':'input'))
    .map(id=>({value:id,label:`${id} · ${directionLabels[parsed.effectiveDirections[id]]}`}));
  return <Stack gap="xs">
    <Text fw={600}>内部通路</Text>
    <Text size="xs" c="dimmed">有向端口对白名单，对所有模式生效；仅声明接线约束，不证明实物导通或采集资格，不叠加损耗/增益。</Text>
    <Text size="xs">{!Object.hasOwn(node.params,'internal_paths')?'旧版未声明（缺键），不自动补齐':Array.isArray(raw)?paths.length?'仅以下方向允许穿越；反向须另行声明':'已声明无内部贯通':'旧声明形态无效，请核对后重新声明'}</Text>
    {node.type==='termination'?<Text size="xs">负载为终止器件，不允许内部中转。</Text>:forbidden?
      <Text size="xs">本片不配置此类仪器内部转发；源端与终端仍沿原运行映射。</Text>:<>
      {!parsed.declared&&<Text size="xs" c="orange">须先显式声明端口；旧画布建议不作为内部通路依据。</Text>}
      {parsed.ports.some(id=>parsed.effectiveDirections[id]==='unknown')&&<Text size="xs" c="orange">方向未声明可保存草稿，但不能作为可采集/正式运行完整通路。</Text>}
      {['air_path','reference_antenna'].includes(node.type)&&<Text size="xs">此处含虚拟参考端点，不等同RF物理连接器。</Text>}
      {paths.map((pair,index)=><Group key={index} align="end" wrap="nowrap">
        <Select label={`内部输入口 ${index+1}`} data={options('from')} value={pair?.from_port??null} disabled={disabled} allowDeselect={false}
          onChange={value=>{if(value)change(paths.map((p,i)=>i===index?{...p,from_port:value}:p))}}/>
        <Select label={`内部输出口 ${index+1}`} data={options('to').filter(p=>p.value!==pair?.from_port)} value={pair?.to_port??null} disabled={disabled} allowDeselect={false}
          onChange={value=>{if(value)change(paths.map((p,i)=>i===index?{...p,to_port:value}:p))}}/>
        <Button size="xs" aria-label={`删除内部通路 ${index+1}`} disabled={disabled} onClick={()=>change(paths.filter((_,i)=>i!==index))}>删除</Button>
      </Group>)}
      <Button size="xs" variant="light" disabled={disabled||!parsed.declared||(node.type==='amplifier'&&paths.length>=1)}
        onClick={()=>change([...paths,{from_port:'',to_port:''}])}>添加内部通路</Button>
    </>}
    {node.type==='switch_slot'&&<Text size="xs">此处不配置自动控制。仍须在原仪器管理→射频开关→端口映射配置 port_maps，并在探头声明映射名。</Text>}
    <Group>
      <Button size="xs" variant="light" disabled={disabled} onClick={()=>change([])}>声明无内部贯通</Button>
      <Button size="xs" variant="subtle" disabled={disabled} onClick={()=>{if(!disabled)onRestore()}}>恢复原内部声明</Button>
    </Group>
  </Stack>;
}
