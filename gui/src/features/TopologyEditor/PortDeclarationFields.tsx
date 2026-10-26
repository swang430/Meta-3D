import {Button, Group, Select, Stack, Text, TextInput} from '@mantine/core';
import type {TopologyNode} from '../../api/switchTopologyService';
import {directionLabels, isBaseStation, portCountLabel, resolveNodePorts} from './nodePortHelpers';

interface Props {
  node:TopologyNode;
  text:string;
  disabled:boolean;
  onTextChange:(text:string)=>void;
  onChange:(delta:Record<string,unknown>)=>void;
  onRestore:()=>void;
}

/** 只发params增量；打开/取消不物化默认清单、unknown或BSE角色。 */
export function PortDeclarationFields({node,text,disabled,onTextChange,onChange,onRestore}:Props) {
  const ids=text.split(/[,，\n]/).map(p=>p.trim()).filter(Boolean);
  const bse=isBaseStation(node),parsed=resolveNodePorts(node);
  const applyPorts=(value:string)=>{
    if(disabled)return;
    onTextChange(value);
    const ports=value.split(/[,，\n]/).map(p=>p.trim()).filter(Boolean),delta:Record<string,unknown>={ports};
    for(const key of ['port_directions',...(bse?['port_roles']:[])]){
      const map=node.params[key];
      if(map&&typeof map==='object'&&!Array.isArray(map))delta[key]=Object.fromEntries(Object.entries(map).filter(([id])=>ports.includes(id)));
    }
    onChange(delta);
  };
  return <Stack gap="xs">
    <Text size="xs">{portCountLabel(node)}</Text>
    {!parsed.declared&&<Text size="xs" c="orange">显示内容为未确认建议/旧版示意；点击应用端口声明后才是明确清单。</Text>}
    <TextInput label="声明端口" description="ID用逗号分隔；仅声明接线，不是设备能力证明。仍被引用的端口不能移除。"
      value={text} disabled={disabled} onChange={e=>applyPorts(e.currentTarget.value)}/>
    {[...new Set(ids)].map(id=><Group key={id} align="end" wrap="nowrap">
      <Text size="xs">{id}</Text>
      <Select label={`端口角色 ${id}`} data={Object.entries(directionLabels).map(([value,label])=>({value,label}))}
        value={node.params.port_directions?.[id]??'unknown'} disabled={disabled} allowDeselect={false}
        onChange={value=>{if(!disabled&&value)onChange({ports:ids,port_directions:{...node.params.port_directions,[id]:value}})}}/>
      {bse&&<Select label={`BSE角色 ${id}`} data={[{value:'dl',label:'下行 dl'},{value:'ul',label:'上行 ul'},{value:'undeclared',label:'未声明'}]}
        value={node.params.port_roles?.[id]??'undeclared'} disabled={disabled} allowDeselect={false}
        onChange={value=>{if(disabled||!value)return;const roles={...node.params.port_roles,[id]:value};if(value==='undeclared')delete roles[id];onChange({ports:ids,port_roles:roles})}}/>}
      <Button size="xs" variant="subtle" disabled={disabled} aria-label={`移除端口 ${id}`} onClick={()=>applyPorts(ids.filter(p=>p!==id).join(', '))}>移除</Button>
    </Group>)}
    {bse&&<Text size="xs" c="dimmed">物理连接器只读：{JSON.stringify(node.params.physical_port_display??{})}；实际映射以运行路径为准。</Text>}
    <Group>
      <Button size="xs" variant="light" disabled={disabled} onClick={()=>applyPorts(text)}>应用端口声明</Button>
      <Button size="xs" variant="light" disabled={disabled} onClick={()=>{if(!disabled)onChange({ports:ids,port_directions:{}})}}>清空通用方向</Button>
      <Button size="xs" variant="subtle" disabled={disabled} onClick={onRestore}>恢复原端口声明</Button>
    </Group>
    <Text size="xs" c="dimmed">可直接在清单追加ID新增端口；双向声明不表示内部通路已验证。删口不会自动删除内部pair；应用时核对内部通路和所有模式显式路径/关联边。</Text>
  </Stack>;
}
