import { useState } from 'react'
import { Stack, Select, Alert, Text, Group, TextInput, NumberInput, SimpleGrid, Button } from '@mantine/core'
import type { ChamberType, ChamberPresetInfo, ChamberFromPresetPayload } from '../types/api'

type CreateChamberFormProps = {
    presets: ChamberPresetInfo[]
    onSubmit: (payload: ChamberFromPresetPayload) => void
    onCancel: () => void
    isLoading?: boolean
}

export function CreateChamberForm({ presets, onSubmit, onCancel, isLoading }: CreateChamberFormProps) {
    const [selectedPreset, setSelectedPreset] = useState<ChamberType>('type_a')
    const [customName, setCustomName] = useState<string>('')
    const [chamberRadius, setChamberRadius] = useState<number | undefined>(undefined)
    const [quietZoneDiameter, setQuietZoneDiameter] = useState<number | undefined>(undefined)
    const [numProbes, setNumProbes] = useState<number | undefined>(undefined)
    const [lnaGain, setLnaGain] = useState<number | undefined>(undefined)
    const [lnaNoiseFigure, setLnaNoiseFigure] = useState<number | undefined>(undefined)
    const [paGain, setPaGain] = useState<number | undefined>(undefined)
    const [paP1dB, setPaP1dB] = useState<number | undefined>(undefined)

    const presetSelectData = presets.map((preset) => ({
        value: preset.type,
        label: preset.name,
    }))

    const selectedPresetInfo = presets.find((p) => p.type === selectedPreset)

    const handleSubmit = () => {
        const payload: ChamberFromPresetPayload = {
            preset_type: selectedPreset,
        }

        if (customName.trim()) {
            payload.name = customName.trim()
        }
        if (chamberRadius !== undefined) {
            payload.chamber_radius_m = chamberRadius
        }
        if (quietZoneDiameter !== undefined) {
            payload.quiet_zone_diameter_m = quietZoneDiameter
        }
        if (numProbes !== undefined) {
            payload.num_probes = numProbes
        }
        if (lnaGain !== undefined) {
            payload.lna_gain_db = lnaGain
        }
        if (lnaNoiseFigure !== undefined) {
            payload.lna_noise_figure_db = lnaNoiseFigure
        }
        if (paGain !== undefined) {
            payload.pa_gain_db = paGain
        }
        if (paP1dB !== undefined) {
            payload.pa_p1db_dbm = paP1dB
        }

        onSubmit(payload)
    }

    return (
        <Stack gap="md">
            <Select
                label="选择预设模板"
                description="选择一个预定义的暗室配置模板"
                placeholder="选择模板"
                data={presetSelectData}
                value={selectedPreset}
                onChange={(value) => setSelectedPreset(value as ChamberType)}
            />

            {/* 显示选中预设的详情 */}
            {selectedPresetInfo && (
                <Alert color="blue" variant="light">
                    <Stack gap="xs">
                        <Text size="sm" fw={500}>
                            {selectedPresetInfo.name}
                        </Text>
                        <Text size="xs" c="dimmed">
                            {selectedPresetInfo.description}
                        </Text>
                        <Group gap="md">
                            <Text size="xs">探头数量: {selectedPresetInfo.num_probes}</Text>
                            <Text size="xs">半径: {selectedPresetInfo.chamber_radius_m}m</Text>
                        </Group>
                    </Stack>
                </Alert>
            )}

            {/* 自定义名称输入 */}
            <TextInput
                label="暗室名称（可选）"
                description="留空则使用预设名称"
                placeholder="例如：5G 车载测试暗室"
                value={customName}
                onChange={(e) => setCustomName(e.currentTarget.value)}
            />

            {/* 核心物理参数覆盖 */}
            <Text size="sm" fw={600} mt="md">
                核心物理参数（可选覆盖）
            </Text>
            <SimpleGrid cols={3}>
                <NumberInput
                    label="暗室半径 (m)"
                    placeholder={selectedPresetInfo ? `默认: ${selectedPresetInfo.chamber_radius_m}m` : ''}
                    min={0.5}
                    max={20.0}
                    step={0.1}
                    decimalScale={2}
                    value={chamberRadius}
                    onChange={(val) => setChamberRadius(val as number | undefined)}
                    clearable
                />
                <NumberInput
                    label="静区直径 (m)"
                    placeholder="默认: 由预设决定"
                    min={0.1}
                    max={5.0}
                    step={0.1}
                    decimalScale={2}
                    value={quietZoneDiameter}
                    onChange={(val) => setQuietZoneDiameter(val as number | undefined)}
                    clearable
                />
                <NumberInput
                    label="探头数量"
                    placeholder={selectedPresetInfo ? `默认: ${selectedPresetInfo.num_probes}` : ''}
                    min={1}
                    max={128}
                    step={1}
                    value={numProbes}
                    onChange={(val) => setNumProbes(val as number | undefined)}
                    clearable
                />
            </SimpleGrid>

            {/* LNA 参数输入（仅当预设包含 LNA 时显示） */}
            {selectedPresetInfo?.has_lna && (
                <>
                    <Text size="sm" fw={600} mt="md">
                        LNA 参数（可选覆盖）
                    </Text>
                    <SimpleGrid cols={2}>
                        <NumberInput
                            label="LNA 增益 (dB)"
                            placeholder="默认: 20 dB"
                            min={0}
                            max={60}
                            step={0.1}
                            decimalScale={1}
                            value={lnaGain}
                            onChange={(val) => setLnaGain(val as number | undefined)}
                            clearable
                        />
                        <NumberInput
                            label="噪声系数 (dB)"
                            placeholder="默认: 2 dB"
                            min={0}
                            max={10}
                            step={0.1}
                            decimalScale={1}
                            value={lnaNoiseFigure}
                            onChange={(val) => setLnaNoiseFigure(val as number | undefined)}
                            clearable
                        />
                    </SimpleGrid>
                </>
            )}

            {/* PA 参数输入（仅当预设包含 PA 时显示） */}
            {selectedPresetInfo?.has_pa && (
                <>
                    <Text size="sm" fw={600} mt="md">
                        PA 参数（可选覆盖）
                    </Text>
                    <SimpleGrid cols={2}>
                        <NumberInput
                            label="PA 增益 (dB)"
                            placeholder="默认: 20 dB"
                            min={0}
                            max={60}
                            step={0.1}
                            decimalScale={1}
                            value={paGain}
                            onChange={(val) => setPaGain(val as number | undefined)}
                            clearable
                        />
                        <NumberInput
                            label="1dB 压缩点 (dBm)"
                            placeholder="默认: 20 dBm"
                            min={-10}
                            max={50}
                            step={0.1}
                            decimalScale={1}
                            value={paP1dB}
                            onChange={(val) => setPaP1dB(val as number | undefined)}
                            clearable
                        />
                    </SimpleGrid>
                </>
            )}

            <Group justify="flex-end" gap="sm" mt="md">
                <Button variant="subtle" onClick={onCancel} disabled={isLoading}>
                    取消
                </Button>
                <Button color="brand" onClick={handleSubmit} loading={isLoading}>
                    创建
                </Button>
            </Group>
        </Stack>
    )
}
