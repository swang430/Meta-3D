import { useState } from 'react'
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
} from '@mantine/core'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import {
    fetchActiveChamber,
    fetchAllChamberConfigurations,
    fetchChamberPresets,
    activateChamber,
    createChamberFromTemplate,
    duplicateChamber,
    deleteChamber,
    fetchChamberCalibration,
} from '../api/service'
import { CreateChamberForm } from './CreateChamberForm'

type ChamberConfigCardProps = {
    onNavigate?: (section: string) => void
}

export function ChamberConfigCard({ onNavigate }: ChamberConfigCardProps) {
    const queryClient = useQueryClient()
    const [createModalOpen, setCreateModalOpen] = useState(false)
    const [selectedPreset, _setSelectedPreset] = useState<string>('type_a')

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

    // 获取所有暗室配置 (分页聚合全部, 否则 124 个暗室只取前 20, CAICT-FS 等靠后暗室
    // 在下拉框里"消失")。
    // queryKey 用 ['chambers','all']: 本次把 queryFn 从返回 ChamberListResponse({items})
    // 改成返回数组, 旧 ['chambers'] 缓存里残留的 {items,total} 对象会让下面 chambers.map
    // 崩 (TypeError: chambers.map is not a function)。换 key 走全新缓存即拿数组; 现有
    // invalidateQueries(['chambers']) 按前缀仍能命中 ['chambers','all']。
    const { data: chambersData } = useQuery({
        queryKey: ['chambers', 'all'],
        queryFn: fetchAllChamberConfigurations,
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

    // 复制暗室配置 (系统预设要改先复制)
    const duplicateMutation = useMutation({
        mutationFn: duplicateChamber,
        onSuccess: (cloned) => {
            queryClient.invalidateQueries({ queryKey: ['chambers'] })
            notifications.show({
                color: 'green',
                title: '已创建副本',
                message: `${cloned.name} — 现在可以编辑这份副本了`,
            })
            // 自动激活副本，方便用户直接进入编辑
            activateMutation.mutate(cloned.id)
        },
        onError: (err: any) => {
            notifications.show({
                color: 'red',
                title: '复制失败',
                message: err?.response?.data?.detail ?? err?.message ?? String(err),
            })
        },
    })

    // 删除暗室 (后端连同探头 + RF 拓扑一起删; 预设/激活/被 lab 引用会被后端拦并给 409/400)
    const deleteMutation = useMutation({
        mutationFn: deleteChamber,
        onSuccess: (res: any) => {
            queryClient.invalidateQueries({ queryKey: ['chambers'] })
            queryClient.invalidateQueries({ queryKey: ['chamber', 'active'] })
            queryClient.invalidateQueries({ queryKey: ['probes'] })
            notifications.show({
                color: 'green',
                title: '已删除暗室',
                message: `连同探头 ${res?.deleted_probes ?? 0}、拓扑 ${res?.deleted_topologies ?? 0} 一并删除`,
            })
            setConfirmDelete(null)
        },
        onError: (err: any) => {
            notifications.show({
                color: 'red',
                title: '删除失败',
                message: err?.response?.data?.detail ?? err?.message ?? String(err),
            })
            setConfirmDelete(null)
        },
    })

    // 暗室管理弹窗 + 待确认删除项
    const [manageOpen, setManageOpen] = useState(false)
    const [confirmDelete, setConfirmDelete] = useState<{ id: string; name: string } | null>(null)

    // 防御: 即便缓存里塞进了非数组 (旧 {items,total} 结构残留), 也不让 .map 崩。
    const chambers = Array.isArray(chambersData) ? chambersData : []
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

    const _handleCreateFromTemplate = () => {
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
    const _handleCloseModal = () => {
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
                        <Group gap="sm" align="center">
                            <Title order={3}>暗室配置</Title>
                            {activeChamber?.is_system_preset && (
                                <Badge color="gray" variant="light" size="sm">
                                    系统预设（只读）
                                </Badge>
                            )}
                        </Group>
                        <Group gap="sm">
                            {activeChamber && (
                                <Button
                                    variant={activeChamber.is_system_preset ? 'filled' : 'subtle'}
                                    color={activeChamber.is_system_preset ? 'brand' : undefined}
                                    onClick={() => duplicateMutation.mutate(activeChamber.id)}
                                    loading={duplicateMutation.isPending}
                                    title={
                                        activeChamber.is_system_preset
                                            ? '系统预设不能直接修改 — 复制一份再改'
                                            : '复制此暗室为新副本'
                                    }
                                >
                                    复制配置
                                </Button>
                            )}
                            <Button
                                variant="subtle"
                                onClick={() => setCreateModalOpen(true)}
                            >
                                新建配置
                            </Button>
                            <Button
                                variant="subtle"
                                onClick={() => setManageOpen(true)}
                            >
                                管理暗室
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
                        description={`选择要使用的暗室配置 (共 ${chamberSelectData.length} 个, 可搜索)`}
                        placeholder="选择或搜索暗室配置"
                        data={chamberSelectData}
                        value={activeChamber?.id ?? ''}
                        onChange={handleChamberChange}
                        disabled={activateMutation.isPending}
                        searchable
                        nothingFoundMessage="无匹配暗室"
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

            {/* 暗室管理: 列出全部, 逐个删除 (替代手工脚本) */}
            <Modal opened={manageOpen} onClose={() => setManageOpen(false)} title="管理暗室" size="lg">
                <Stack gap="sm">
                    <Text size="xs" c="dimmed">
                        共 {chambers.length} 个暗室。删除会<b>连同该暗室的探头与 RF 拓扑一并删除</b>；
                        系统预设、当前激活、被 Lab Profile 引用的暗室不可删（后端会拦截并提示）。
                    </Text>
                    <Table.ScrollContainer minWidth={480} mah={420}>
                        <Table highlightOnHover withTableBorder stickyHeader>
                            <Table.Thead>
                                <Table.Tr>
                                    <Table.Th>名称</Table.Th>
                                    <Table.Th>类型</Table.Th>
                                    <Table.Th w={80}>操作</Table.Th>
                                </Table.Tr>
                            </Table.Thead>
                            <Table.Tbody>
                                {chambers.map((c) => {
                                    const blocked = c.is_system_preset || c.is_active
                                    return (
                                        <Table.Tr key={c.id}>
                                            <Table.Td>
                                                {c.name}
                                                {c.is_active && (
                                                    <Badge ml="xs" size="xs" color="brand">当前</Badge>
                                                )}
                                                {c.is_system_preset && (
                                                    <Badge ml="xs" size="xs" color="gray" variant="light">预设</Badge>
                                                )}
                                            </Table.Td>
                                            <Table.Td>{c.chamber_type}</Table.Td>
                                            <Table.Td>
                                                <Button
                                                    size="compact-xs"
                                                    variant="subtle"
                                                    color="red"
                                                    disabled={blocked}
                                                    title={blocked ? '系统预设 / 当前激活暗室不可删除' : '删除此暗室'}
                                                    onClick={() => setConfirmDelete({ id: c.id, name: c.name })}
                                                >
                                                    删除
                                                </Button>
                                            </Table.Td>
                                        </Table.Tr>
                                    )
                                })}
                            </Table.Tbody>
                        </Table>
                    </Table.ScrollContainer>
                </Stack>
            </Modal>

            {/* 删除确认 */}
            <Modal
                opened={!!confirmDelete}
                onClose={() => setConfirmDelete(null)}
                title="确认删除暗室"
                size="sm"
            >
                <Stack gap="md">
                    <Text size="sm">
                        确定删除暗室「{confirmDelete?.name}」？将<b>连同其探头与 RF 拓扑一并永久删除</b>，不可恢复。
                    </Text>
                    <Group justify="flex-end" gap="sm">
                        <Button variant="default" onClick={() => setConfirmDelete(null)}>
                            取消
                        </Button>
                        <Button
                            color="red"
                            loading={deleteMutation.isPending}
                            onClick={() => confirmDelete && deleteMutation.mutate(confirmDelete.id)}
                        >
                            删除
                        </Button>
                    </Group>
                </Stack>
            </Modal>
        </>
    )
}
