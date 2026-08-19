/**
 * Baseline Calibration Card Component
 * 
 * 相对校准（快速校准）功能入口
 */
import { useState, useEffect } from 'react';
import { useOperationalLab } from '../../features/OperationalLab';
import {
    Paper,
    Text,
    Group,
    Stack,
    Badge,
    Button,
    Select,
    NumberInput,
    Table,
    Loader,
    Center,
    Alert,
    Divider,
    ThemeIcon,
} from '@mantine/core';
import {
    IconRocket,
    IconRefresh,
    IconCheck,
    IconAlertTriangle,
    IconTarget,
} from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';

interface BaselineStatus {
    calibration_type: string;
    frequency_mhz: number;
    status: string;
    baseline_date: string | null;
    valid_until: string | null;
    days_remaining: number;
    total_channels: number;
    reference_channel_id: number;
    drift_within_threshold: boolean;
}

interface QuickCalibrationResult {
    success: boolean;
    reference_value_db: number;
    derived_channels: Array<{
        channel_id: number;
        derived_amplitude_db: number;
        delta_db: number;
    }>;
    drift_detected: boolean;
    max_drift_db: number;
}

const API_BASE = '/api/v1';

export function BaselineCalibrationCard() {
    const [loading, setLoading] = useState(false);
    const [baselines, setBaselines] = useState<BaselineStatus[]>([]);
    const [selectedType, setSelectedType] = useState<string>('amplitude');
    const [frequency, setFrequency] = useState<number>(3500);
    const [quickResult, setQuickResult] = useState<QuickCalibrationResult | null>(null);

    // P1-57（外审 R3）：暗室由全局 LabProfile 派生（原来写死全零 UUID，
    // 状态读的、快捷校准写的都是一个不存在的暗室）。缺绑定 → 不发请求。
    const { chamberId, beginWork } = useOperationalLab();

    const fetchBaselines = async () => {
        setLoading(true);
        try {
            const res = await fetch(`${API_BASE}/calibration/baseline/status/${chamberId}`);
            if (res.ok) {
                const data = await res.json();
                setBaselines(data.baselines || []);
            }
        } catch (error) {
            console.error('Failed to fetch baselines:', error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (!chamberId) { setBaselines([]); return }
        fetchBaselines();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [chamberId]);

    const handleQuickCalibration = async () => {
        if (!chamberId) return;
        const releaseWork = beginWork('calibration', '相对校准（quick）正在驱动硬件');
        setLoading(true);
        setQuickResult(null);
        try {
            const res = await fetch(
                `${API_BASE}/calibration/baseline/quick?chamber_id=${chamberId}&calibration_type=${selectedType}&frequency_mhz=${frequency}`,
                { method: 'POST' }
            );
            if (res.ok) {
                const data = await res.json();
                setQuickResult(data);
                notifications.show({
                    title: '快速校准完成',
                    message: data.drift_detected
                        ? `检测到漂移 (${data.max_drift_db.toFixed(2)} dB)，建议重建基线`
                        : '校准成功，漂移在阈值范围内',
                    color: data.drift_detected ? 'orange' : 'green',
                });
            } else {
                const err = await res.json();
                throw new Error(err.detail || 'No baseline found');
            }
        } catch (error) {
            notifications.show({
                title: '快速校准失败',
                message: String(error),
                color: 'red',
            });
        } finally {
            releaseWork();
            setLoading(false);
        }
    };

    const handleDriftCheck = async () => {
        if (!chamberId) return;
        const releaseWork = beginWork('calibration', '漂移检测正在驱动硬件');
        setLoading(true);
        try {
            const res = await fetch(
                `${API_BASE}/calibration/baseline/drift-check?chamber_id=${chamberId}&calibration_type=${selectedType}&frequency_mhz=${frequency}`,
                { method: 'POST' }
            );
            if (res.ok) {
                const data = await res.json();
                notifications.show({
                    title: '漂移检测完成',
                    message: data.recommendation,
                    color: data.within_threshold ? 'green' : 'orange',
                });
                fetchBaselines();
            }
        } catch (error) {
            notifications.show({
                title: '漂移检测失败',
                message: String(error),
                color: 'red',
            });
        } finally {
            releaseWork();
            setLoading(false);
        }
    };

    const getStatusBadge = (status: BaselineStatus) => {
        if (status.status !== 'valid') {
            return <Badge color="red" size="xs">已失效</Badge>;
        }
        if (status.days_remaining <= 7) {
            return <Badge color="orange" size="xs">即将过期</Badge>;
        }
        if (!status.drift_within_threshold) {
            return <Badge color="yellow" size="xs">漂移超限</Badge>;
        }
        return <Badge color="green" size="xs">有效</Badge>;
    };

    if (!chamberId) {
        // fail-closed：没有派生暗室就不读不写，明说原因而不是渲染空列表
        return (
            <Paper p="md" withBorder>
                <Alert color="yellow" title="当前 LabProfile 未绑定暗室">
                    相对校准需要明确的目标暗室 —— 请在顶部选择绑定暗室的 LabProfile。
                </Alert>
            </Paper>
        );
    }

    return (
        <Paper p="md" withBorder>
            <Group justify="space-between" mb="md">
                <Group gap="xs">
                    <ThemeIcon color="violet" variant="light" size="lg">
                        <IconRocket size={20} />
                    </ThemeIcon>
                    <div>
                        <Text size="sm" fw={600}>相对校准 (Quick Mode)</Text>
                        <Text size="xs" c="dimmed">仅测量参考通道，快速推导其他通道</Text>
                    </div>
                </Group>
                <Button
                    variant="light"
                    size="xs"
                    leftSection={<IconRefresh size={14} />}
                    onClick={fetchBaselines}
                    loading={loading}
                >
                    刷新
                </Button>
            </Group>

            {/* 操作区 */}
            <Stack gap="sm" mb="md">
                <Group>
                    <Select
                        size="xs"
                        label="校准类型"
                        value={selectedType}
                        onChange={(v) => setSelectedType(v || 'amplitude')}
                        data={[
                            { value: 'amplitude', label: '幅度校准' },
                            { value: 'phase', label: '相位校准' },
                            { value: 'path_loss', label: '路损校准' },
                        ]}
                        w={120}
                    />
                    <NumberInput
                        size="xs"
                        label="频率 (MHz)"
                        value={frequency}
                        onChange={(v) => setFrequency(Number(v) || 3500)}
                        min={600}
                        max={7125}
                        step={100}
                        w={100}
                    />
                </Group>

                <Group>
                    <Button
                        size="xs"
                        variant="filled"
                        color="green"
                        leftSection={<IconRocket size={14} />}
                        onClick={handleQuickCalibration}
                        loading={loading}
                        disabled={baselines.length === 0}
                    >
                        快速校准
                    </Button>
                    <Button
                        size="xs"
                        variant="light"
                        color="orange"
                        leftSection={<IconTarget size={14} />}
                        onClick={handleDriftCheck}
                        loading={loading}
                        disabled={baselines.length === 0}
                    >
                        漂移检测
                    </Button>
                </Group>
            </Stack>

            <Divider mb="md" />

            {/* 基线状态表 */}
            <Text size="xs" fw={500} mb="xs">当前基线</Text>

            {loading && baselines.length === 0 ? (
                <Center py="md">
                    <Loader size="sm" />
                </Center>
            ) : baselines.length === 0 ? (
                <Alert color="gray" variant="light">
                    暂无基线数据，请在"新建校准"中选择"校准基线 (Quick Mode)"建立基线
                </Alert>
            ) : (
                <Table striped>
                    <Table.Thead>
                        <Table.Tr>
                            <Table.Th>类型</Table.Th>
                            <Table.Th>频率</Table.Th>
                            <Table.Th>通道数</Table.Th>
                            <Table.Th>剩余天数</Table.Th>
                            <Table.Th>状态</Table.Th>
                        </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                        {baselines.map((bl, idx) => (
                            <Table.Tr key={idx}>
                                <Table.Td>{bl.calibration_type}</Table.Td>
                                <Table.Td>{bl.frequency_mhz} MHz</Table.Td>
                                <Table.Td>{bl.total_channels}</Table.Td>
                                <Table.Td>{bl.days_remaining} 天</Table.Td>
                                <Table.Td>{getStatusBadge(bl)}</Table.Td>
                            </Table.Tr>
                        ))}
                    </Table.Tbody>
                </Table>
            )}

            {/* 快速校准结果 */}
            {quickResult && (
                <>
                    <Divider my="md" />
                    <Text size="xs" fw={500} mb="xs">快速校准结果</Text>
                    <Alert
                        color={quickResult.drift_detected ? 'orange' : 'green'}
                        variant="light"
                        icon={quickResult.drift_detected ? <IconAlertTriangle size={16} /> : <IconCheck size={16} />}
                    >
                        <Text size="xs">
                            参考通道值: {quickResult.reference_value_db.toFixed(2)} dB |
                            推导通道数: {quickResult.derived_channels.length} |
                            最大漂移: {quickResult.max_drift_db.toFixed(3)} dB
                        </Text>
                    </Alert>
                </>
            )}
        </Paper>
    );
}
