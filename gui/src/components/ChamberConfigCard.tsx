import { useState, useEffect } from 'react'
import {
    Card,
    Stack,
    Group,
    Title,
    Text,
    Select,
    Button,
    Badge,
    Alert,
    Table,
    SimpleGrid,
    Modal,
    TextInput,
    NumberInput,
    Switch,
} from '@mantine/core'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
    fetchActiveChamber,
    fetchChamberConfigurations,
    fetchChamberPresets,
    activateChamber,
    createChamberFromTemplate,
    fetchChamberCalibration,
} from '../api/service'
import { CreateChamberForm } from './CreateChamberForm'

type ChamberConfigCardProps = {
    onNavigate?: (section: string) => void
}

export function ChamberConfigCard({ onNavigate }: ChamberConfigCardProps) {
    const queryClient = useQueryClient()
    const [createModalOpen, setCreateModalOpen] = useState(false)
    const [selectedPreset, setSelectedPreset] = useState<ChamberType>('type_a')

    // 自定义参数状态
    const [customName, setCustomName] = useState<string>('')
    const [lnaGain, setLnaGain] = useState<number | undefined>(undefined)
    const [lnaNoiseFigure, setLnaNoiseFigure] = useState<number | undefined>(undefined)
    const [paGain, setPaGain] = useState<number | undefined>(undefined)
    const [paP1dB, setPaP1dB] = useState<number | undefined>(undefined)

    console.log('[ChamberConfigCard] Component mounted')

    // 获取当前激活的暗室配置
    const { data: activeChamber, isLoading: isActiveLoading } = useQuery({
        queryKey: ['chamber', 'active'],
        queryFn: fetchActiveChamber,
        retry: 1,
    })

    // 获取所有暗室配置
    const { data: chambersData } = useQuery({
        queryKey: ['chambers'],
        queryFn: () => fetchChamberConfigurations(),
    })

    // 获取预设模板
    const { data: presetsData } = useQuery({
        queryKey: ['chamber', 'presets'],
        queryFn: fetchChamberPresets,
    })

    // 获取校准要求
    const { data: calibrationData } = useQuery({
        queryKey: ['chamber', 'calibration', activeChamber?.id],
        queryFn: () => fetchChamberCalibration(activeChamber!.id),
        enabled: !!activeChamber?.id,
    })

    // 激活暗室配置
    const activateMutation = useMutation({
        mutationFn: activateChamber,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['chamber', 'active'] })
            queryClient.invalidateQueries({ queryKey: ['chambers'] })
        },
    })

    // 从模板创建
    const createFromTemplateMutation = useMutation({
        mutationFn: createChamberFromTemplate,
        onSuccess: (newChamber) => {
            queryClient.invalidateQueries({ queryKey: ['chambers'] })
            queryClient.invalidateQueries({ queryKey: ['chamber', 'active'] })
            setCreateModalOpen(false)
            // 自动激活新创建的配置
            activateMutation.mutate(newChamber.id)
        },
    })

    const chambers = chambersData?.items ?? []
    const presets = presetsData?.presets ?? []

    // 调试日志
    console.log('[ChamberConfigCard] presetsData:', presetsData)
    console.log('[ChamberConfigCard] presets array:', presets)
    console.log('[ChamberConfigCard] presets.length:', presets.length)

    // 准备选择器数据
    const chamberSelectData = chambers.map((chamber) => ({
        value: chamber.id,
        label: `${chamber.name} ${chamber.is_active ? '(当前)' : ''}`,
    }))

    const presetSelectData = presets.map((preset) => ({
        value: preset.type,
        label: preset.name,
    }))

    console.log('[ChamberConfigCard] presetSelectData:', presetSelectData)

    const handleChamberChange = (chamberId: string | null) => {
        if (chamberId && chamberId !== activeChamber?.id) {
            activateMutation.mutate(chamberId)
        }
    }

    const handleCreateFromTemplate = () => {
        const payload: any = { preset_type: selectedPreset }

        if (customName.trim()) {
            payload.name = customName.trim()
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

        createFromTemplateMutation.mutate(payload)
    }

    // 重置表单状态
    const resetForm = () => {
        setCustomName('')
        setLnaGain(undefined)
        setLnaNoiseFigure(undefined)
        setPaGain(undefined)
        setPaP1dB(undefined)
    }

    // 关闭模态框时重置表单
    const handleCloseModal = () => {
        setCreateModalOpen(false)
        resetForm()
    }

    if (isActiveLoading) {
        return (
            <Card withBorder radius="md" padding="xl">
                <Text size="sm" c="gray.6">
                    正在加载暗室配置...
                </Text>
            </Card>
        )
    }

    return (
        <>
            <Card withBorder radius="md" padding="xl">
                <Stack gap="md">
                    {/* 标题和操作按钮 */}
                    <Group justify="space-between">
                        <Title order={3}>暗室配置</Title>
                        <Group gap="sm">
                            <Button
                                variant="subtle"
                                onClick={() => setCreateModalOpen(true)}
                            >
                                新建配置
                            </Button>
                            {onNavigate && (
                                <Button
                                    variant="subtle"
                                    onClick={() => onNavigate('systemCalibration')}
                                >
                                    配置校准
                                </Button>
                            )}
                        </Group>
                    </Group>

                    {/* 当前配置选择器 */}
                    <Select
                        label="当前激活配置"
                        description="选择要使用的暗室配置"
                        placeholder="选择暗室配置"
                        data={chamberSelectData}
                        value={activeChamber?.id ?? ''}
                        onChange={handleChamberChange}
                        disabled={activateMutation.isPending}
                    />

                    {/* 当前配置详情 */}
                    {activeChamber && (
                        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
                            {/* 左侧：基本信息 */}
                            <Stack gap="sm">
                                <Text size="sm" fw={600} c="gray.7">
                                    基本信息
                                </Text>
                                <Table withTableBorder withColumnBorders>
                                    <Table.Tbody>
                                        <Table.Tr>
                                            <Table.Td fw={500}>暗室类型</Table.Td>
                                            <Table.Td>
                                                <Badge variant="light" color="blue">
                                                    {activeChamber.chamber_type.toUpperCase()}
                                                </Badge>
                                            </Table.Td>
                                        </Table.Tr>
                                        <Table.Tr>
                                            <Table.Td fw={500}>暗室半径</Table.Td>
                                            <Table.Td>{activeChamber.chamber_radius_m.toFixed(2)} m</Table.Td>
                                        </Table.Tr>
                                        <Table.Tr>
                                            <Table.Td fw={500}>静区直径</Table.Td>
                                            <Table.Td>
                                                {activeChamber.quiet_zone_diameter_m?.toFixed(2) ?? 'N/A'} m
                                            </Table.Td>
                                        </Table.Tr>
                                        <Table.Tr>
                                            <Table.Td fw={500}>探头数量</Table.Td>
                                            <Table.Td>{activeChamber.num_probes}</Table.Td>
                                        </Table.Tr>
                                        <Table.Tr>
                                            <Table.Td fw={500}>频率范围</Table.Td>
                                            <Table.Td>
                                                {activeChamber.freq_min_mhz} - {activeChamber.freq_max_mhz} MHz
                                            </Table.Td>
                                        </Table.Tr>
                                    </Table.Tbody>
                                </Table>
                            </Stack>

                            {/* 右侧：硬件配置 */}
                            <Stack gap="sm">
                                <Text size="sm" fw={600} c="gray.7">
                                    硬件配置
                                </Text>
                                <Table withTableBorder withColumnBorders>
                                    <Table.Tbody>
                                        <Table.Tr>
                                            <Table.Td fw={500}>LNA</Table.Td>
                                            <Table.Td>
                                                <Group gap="xs">
                                                    <Badge color={activeChamber.has_lna ? 'green' : 'gray'}>
                                                        {activeChamber.has_lna ? '已配置' : '未配置'}
                                                    </Badge>
                                                    {activeChamber.has_lna && (
                                                        <Text size="xs" c="dimmed">
                                                            +{activeChamber.lna_gain_db} dB
                                                        </Text>
                                                    )}
                                                </Group>
                                            </Table.Td>
                                        </Table.Tr>
                                        <Table.Tr>
                                            <Table.Td fw={500}>PA</Table.Td>
                                            <Table.Td>
                                                <Group gap="xs">
                                                    <Badge color={activeChamber.has_pa ? 'green' : 'gray'}>
                                                        {activeChamber.has_pa ? '已配置' : '未配置'}
                                                    </Badge>
                                                    {activeChamber.has_pa && (
                                                        <Text size="xs" c="dimmed">
                                                            +{activeChamber.pa_gain_db} dB
                                                        </Text>
                                                    )}
                                                </Group>
                                            </Table.Td>
                                        </Table.Tr>
                                        <Table.Tr>
                                            <Table.Td fw={500}>双工器</Table.Td>
                                            <Table.Td>
                                                <Badge color={activeChamber.has_duplexer ? 'green' : 'gray'}>
                                                    {activeChamber.has_duplexer ? '已配置' : '未配置'}
                                                </Badge>
                                            </Table.Td>
                                        </Table.Tr>
                                        <Table.Tr>
                                            <Table.Td fw={500}>信道仿真器</Table.Td>
                                            <Table.Td>
                                                <Badge color={activeChamber.has_channel_emulator ? 'green' : 'gray'}>
                                                    {activeChamber.has_channel_emulator ? '已配置' : '未配置'}
                                                </Badge>
                                            </Table.Td>
                                        </Table.Tr>
                                    </Table.Tbody>
                                </Table>

                                {/* 支持的测试类型 */}
                                <Group gap="xs" mt="sm">
                                    <Text size="xs" fw={500} c="gray.7">
                                        支持测试:
                                    </Text>
                                    {activeChamber.supported_tests.map((test) => (
                                        <Badge key={test} size="sm" variant="dot">
                                            {test}
                                        </Badge>
                                    ))}
                                </Group>
                            </Stack>
                        </SimpleGrid>
                    )}

                    {/* 校准要求 */}
                    {calibrationData && (
                        <Alert title="校准要求" color="blue" variant="light">
                            <Stack gap="sm">
                                <Group gap="xs">
                                    <Text size="sm" fw={500}>
                                        必需校准项目 ({calibrationData.required_calibrations.length}):
                                    </Text>
                                    <Group gap="xs">
                                        {calibrationData.required_calibrations.map((item) => (
                                            <Badge key={item} size="sm" color="red">
                                                {item}
                                            </Badge>
                                        ))}
                                    </Group>
                                </Group>
                                {calibrationData.optional_calibrations.length > 0 && (
                                    <Group gap="xs">
                                        <Text size="sm" fw={500}>
                                            可选校准项目 ({calibrationData.optional_calibrations.length}):
                                        </Text>
                                        <Group gap="xs">
                                            {calibrationData.optional_calibrations.map((item) => (
                                                <Badge key={item} size="sm" color="gray">
                                                    {item}
                                                </Badge>
                                            ))}
                                        </Group>
                                    </Group>
                                )}
                            </Stack>
                        </Alert>
                    )}

                    {/* 备注 */}
                    {activeChamber?.description && (
                        <Text size="sm" c="dimmed">
                            {activeChamber.description}
                        </Text>
                    )}
                </Stack>
            </Card>

            {/* 创建配置模态框 */}
            <Modal
                opened={createModalOpen}
                onClose={() => setCreateModalOpen(false)}
                title="从模板创建暗室配置"
                size="md"
            >
                <CreateChamberForm
                    presets={presets}
                    onSubmit={(payload) => {
                        createFromTemplateMutation.mutate(payload)
                        setCreateModalOpen(false)
                    }}
                    onCancel={() => setCreateModalOpen(false)}
                    isLoading={createFromTemplateMutation.isPending}
                />
            </Modal>
        </>
    )
}
