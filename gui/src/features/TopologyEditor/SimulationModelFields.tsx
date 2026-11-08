import {Alert,Checkbox,NumberInput,Stack,Text} from '@mantine/core'

export function simulationQuantityForNode(type:string):'loss_db'|'gain_db'|null {
  if(['cable','receive_cable','air_path'].includes(type))return 'loss_db'
  if(['amplifier','probe','reference_antenna'].includes(type))return 'gain_db'
  return null
}

export function simulationModelValid(value:unknown,key:'loss_db'|'gain_db') {
  if(value===undefined)return true
  if(!value||typeof value!=='object'||Array.isArray(value))return false
  const row=value as Record<string,unknown>
  return Object.keys(row).length===2&&typeof row.frequency_mhz==='number'&&Number.isFinite(row.frequency_mhz)&&row.frequency_mhz>0&&
    typeof row[key]==='number'&&Number.isFinite(row[key])&&(key==='gain_db'||row[key]>=0)
}

/** 只编辑用户明确开启的合成模型，不从标称、证书或缺值生成默认参数。 */
export function SimulationModelFields({value,quantity,disabled,onChange}:{value:unknown;quantity:'loss_db'|'gain_db';disabled:boolean;
  onChange:(value:Record<string,number|string>|undefined)=>void}) {
  const enabled=value!==undefined
  const row=value&&typeof value==='object'&&!Array.isArray(value)?value as Record<string,unknown>:{}
  const numeric=(key:string)=>typeof row[key]==='number'||typeof row[key]==='string'?row[key] as number|string:''
  const set=(key:string,next:number|string)=>onChange({frequency_mhz:numeric('frequency_mhz'),[quantity]:numeric(quantity),[key]:next})
  return <Stack gap="xs">
    <Checkbox label="为此段声明模拟模型（非实测）" checked={enabled} disabled={disabled}
      onChange={e=>onChange(e.currentTarget.checked?{frequency_mhz:'',[quantity]:''}:undefined)}/>
    {enabled&&<>
      <Text size="xs">仅用于完整链路模拟，不改变标称或校准值。同一线缆只在器件或连线的一处声明，不能重复计入。</Text>
      <NumberInput label="模拟模型适用频率（MHz）" value={numeric('frequency_mhz')} disabled={disabled} onChange={v=>set('frequency_mhz',v)}/>
      <NumberInput label={quantity==='gain_db'?'模拟模型增益（dB，非实测）':'模拟模型损耗（dB，非实测）'} value={numeric(quantity)} disabled={disabled} onChange={v=>set(quantity,v)}/>
      {!simulationModelValid(value,quantity)&&<Alert color="yellow">请明确填写正频率和有限数值；损耗不能为负。不以空值代替零。</Alert>}
    </>}
  </Stack>
}
