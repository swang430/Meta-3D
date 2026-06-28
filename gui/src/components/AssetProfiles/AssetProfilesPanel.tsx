import { useState } from 'react'
import { Tabs } from '@mantine/core'
import { IconDeviceMobile, IconDeviceSim, IconWaveSine } from '@tabler/icons-react'
import { DUTProfileManager } from '../DUTProfile/DUTProfileManager'
import { SIMProfileManager } from '../SIMProfile/SIMProfileManager'
import { CustomCDLProfileManager } from '../CustomCDLProfile/CustomCDLProfileManager'

/**
 * 被测对象声明面板：把 DUT 能力声明与 SIM 卡池统一进一个界面的两个 Tab。
 *
 * 注意：数据层仍是两个独立实体（dut_profiles / sim_profiles，多对多卡池复用）——
 * 这里只做**界面整合**，把原先两个 nav 入口收进一个，减少导航来回切换。
 * 真正的 DUT↔SIM 配对发生在测试例配置（MIMOOTAConfigForm）时各选一个。
 */
export function AssetProfilesPanel() {
  const [tab, setTab] = useState<string | null>('dut')
  return (
    <Tabs value={tab} onChange={setTab}>
      <Tabs.List>
        <Tabs.Tab value="dut" leftSection={<IconDeviceMobile size={16} />}>
          DUT 车辆声明
        </Tabs.Tab>
        <Tabs.Tab value="sim" leftSection={<IconDeviceSim size={16} />}>
          SIM 卡池
        </Tabs.Tab>
        <Tabs.Tab value="cdl" leftSection={<IconWaveSine size={16} />}>
          自定义 CDL
        </Tabs.Tab>
      </Tabs.List>
      <Tabs.Panel value="dut" pt="md">
        <DUTProfileManager />
      </Tabs.Panel>
      <Tabs.Panel value="sim" pt="md">
        <SIMProfileManager />
      </Tabs.Panel>
      <Tabs.Panel value="cdl" pt="md">
        <CustomCDLProfileManager />
      </Tabs.Panel>
    </Tabs>
  )
}
