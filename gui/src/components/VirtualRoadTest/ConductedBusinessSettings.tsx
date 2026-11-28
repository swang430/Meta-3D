import { Checkbox, NumberInput, Select, Stack, Text, TextInput } from '@mantine/core'
import type { ConductedPreparation, ConductedSelection, ConductedTestSettings } from '../../types/roadTest'

import { trafficOptions } from './roadTraffic'

export function ConductedBusinessSettings({selection, preset, onChange, mockOnly}: {
  selection: ConductedSelection
  preset: ConductedPreparation['scenario_snapshot']
  onChange: (selection: ConductedSelection) => void
  mockOnly: boolean
}) {
  const settings = selection.test_settings
  const update = (value: ConductedTestSettings) => onChange({...selection, test_settings: value})
  return <Stack gap="xs">
    <Checkbox label="单独配置本次业务与指标" checked={!!settings} onChange={e => {
      if (e.currentTarget.checked && preset?.traffic) update({traffic: {...preset.traffic}, kpi_definitions: preset.kpi_definitions})
      else onChange({...selection, test_settings: null})
    }}/>
    <Text size="sm">业务和指标初值来自场景预设，仅记录测试意图。模拟采样不参与正式判定。</Text>
    {settings && <>
      <Select label="基站协议（与场景设置核对）" clearable placeholder="沿用场景预设" value={settings.expected_network ?? null}
        data={[{value:'5G_NR',label:'5G NR'},{value:'LTE',label:'4G LTE'},{value:'C-V2X',label:'蜂窝车联网'}]}
        onChange={v=>update({...settings,expected_network:v==='5G_NR'||v==='LTE'||v==='C-V2X'?v:null})}/>
      <TextInput label="终端协议配置（仅记录）" maxLength={120} value={settings.terminal_protocol ?? ''}
        onChange={e=>update({...settings,terminal_protocol:e.currentTarget.value || null})}/>
      <Select label="业务类型" value={settings.traffic.type}
        data={trafficOptions}
        onChange={type=>type && update({...settings, traffic:{...settings.traffic,type}})}/>
      <NumberInput label="业务目标速率（Mbps）" min={0} value={settings.traffic.data_rate_mbps ?? ''}
        onChange={v=>update({...settings,traffic:{...settings.traffic,data_rate_mbps:typeof v === 'number'?v:null}})}/>
      {(settings.kpi_definitions ?? []).map((item,index)=><NumberInput key={index}
        label={`指标 ${item.kpi_type} 的目标（${item.unit}）`} value={item.target_value}
        onChange={v=>typeof v === 'number' && update({...settings,kpi_definitions:settings.kpi_definitions?.map((k,i)=>i===index?{...k,target_value:v}:k)})}/>)}
      {(mockOnly || settings.playback_seconds != null) && <NumberInput label="从起点开始模拟播放的秒数（留空播完整段）" min={0}
        error={settings.playback_seconds != null && settings.playback_seconds <= 0 ? '播放秒数必须大于零。' : undefined}
        value={settings.playback_seconds ?? ''} onChange={v=>update({...settings,playback_seconds:typeof v==='number'?v:null})}/>}
    </>}
  </Stack>
}
