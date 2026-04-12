/**
 * Calibration Timeline Component
 * 
 * 显示校准历史时间线，按时间排列各类校准事件
 */
import { useState, useEffect } from 'react';
import {
    Paper,
    Text,
    Timeline,
    Group,
    Badge,
    ActionIcon,
    Tooltip,
    Stack,
    Select,
    Loader,
    Center,
} from '@mantine/core';
import {
    IconCircleCheck,
    IconAlertTriangle,
    IconClock,
    IconRefresh,
    IconAntenna,
    IconWaveSine,
    IconRouter,
    IconSettings,
} from '@tabler/icons-react';

interface CalibrationEvent {
    id: string;
    type: 'path_loss' | 'phase' | 'rf_chain' | 'e2e' | 'ce_internal';
    status: 'valid' | 'expired' | 'invalidated' | 'pending';
    calibrated_at: string;
    calibrated_by: string;
    valid_until: string;
    description?: string;
}

// Mock data for demonstration
const mockEvents: CalibrationEvent[] = [
    {
        id: '1',
        type: 'path_loss',
        status: 'valid',
        calibrated_at: '2026-01-27T10:30:00',
        calibrated_by: 'system',
        valid_until: '2026-07-27',
        description: '探头路损校准 @3500MHz',
    },
    {
        id: '2',
        type: 'phase',
        status: 'valid',
        calibrated_at: '2026-01-27T09:15:00',
        calibrated_by: 'admin',
        valid_until: '2026-04-27',
        description: '16 通道相位一致性校准',
    },
    {
        id: '3',
        type: 'rf_chain',
        status: 'expired',
        calibrated_at: '2025-10-15T14:00:00',
        calibrated_by: 'system',
        valid_until: '2026-01-15',
        description: '上行链路 LNA 增益校准',
    },
    {
        id: '4',
        type: 'ce_internal',
        status: 'valid',
        calibrated_at: '2026-01-20T11:45:00',
        calibrated_by: 'vendor',
        valid_until: '2026-04-20',
        description: 'Spirent CE 内部校准',
    },
    {
        id: '5',
        type: 'e2e',
        status: 'valid',
        calibrated_at: '2026-01-25T16:20:00',
        calibrated_by: 'system',
        valid_until: '2026-04-25',
        description: '端到端补偿矩阵更新',
    },
];

const typeConfig = {
    path_loss: { icon: IconAntenna, color: 'blue', label: '路损校准' },
    phase: { icon: IconWaveSine, color: 'violet', label: '相位校准' },
    rf_chain: { icon: IconRouter, color: 'orange', label: 'RF链路校准' },
    e2e: { icon: IconSettings, color: 'green', label: 'E2E校准' },
    ce_internal: { icon: IconSettings, color: 'cyan', label: 'CE内部校准' },
};

const statusConfig = {
    valid: { color: 'green', label: '有效' },
    expired: { color: 'red', label: '已过期' },
    invalidated: { color: 'orange', label: '已失效' },
    pending: { color: 'gray', label: '待校准' },
};

export function CalibrationTimeline() {
    const [events, setEvents] = useState<CalibrationEvent[]>([]);
    const [loading, setLoading] = useState(true);
    const [typeFilter, setTypeFilter] = useState<string | null>(null);

    useEffect(() => {
        // Simulate API call
        setTimeout(() => {
            setEvents(mockEvents);
            setLoading(false);
        }, 500);
    }, []);

    const handleRefresh = () => {
        setLoading(true);
        setTimeout(() => {
            setEvents(mockEvents);
            setLoading(false);
        }, 500);
    };

    const filteredEvents = typeFilter
        ? events.filter((e) => e.type === typeFilter)
        : events;

    const formatDate = (dateStr: string) => {
        const date = new Date(dateStr);
        return date.toLocaleDateString('zh-CN', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    };

    if (loading) {
        return (
            <Paper p="md" withBorder>
                <Center h={200}>
                    <Loader size="md" />
                </Center>
            </Paper>
        );
    }

    return (
        <Paper p="md" withBorder>
            <Group justify="space-between" mb="md">
                <Text size="sm" fw={600}>校准时间线</Text>
                <Group gap="xs">
                    <Select
                        size="xs"
                        placeholder="筛选类型"
                        clearable
                        data={[
                            { value: 'path_loss', label: '路损校准' },
                            { value: 'phase', label: '相位校准' },
                            { value: 'rf_chain', label: 'RF链路' },
                            { value: 'e2e', label: 'E2E校准' },
                            { value: 'ce_internal', label: 'CE校准' },
                        ]}
                        value={typeFilter}
                        onChange={setTypeFilter}
                        w={120}
                    />
                    <Tooltip label="刷新">
                        <ActionIcon variant="light" onClick={handleRefresh}>
                            <IconRefresh size={16} />
                        </ActionIcon>
                    </Tooltip>
                </Group>
            </Group>

            <Timeline active={0} bulletSize={28} lineWidth={2}>
                {filteredEvents.map((event) => {
                    const TypeIcon = typeConfig[event.type].icon;
                    const typeColor = typeConfig[event.type].color;
                    const statusInfo = statusConfig[event.status];

                    return (
                        <Timeline.Item
                            key={event.id}
                            bullet={<TypeIcon size={14} />}
                            color={typeColor}
                            title={
                                <Group gap="xs">
                                    <Text size="sm" fw={500}>{typeConfig[event.type].label}</Text>
                                    <Badge size="xs" color={statusInfo.color} variant="light">
                                        {statusInfo.label}
                                    </Badge>
                                </Group>
                            }
                        >
                            <Stack gap={2}>
                                <Text size="xs" c="dimmed">
                                    {event.description}
                                </Text>
                                <Group gap="xs">
                                    <IconClock size={12} style={{ opacity: 0.5 }} />
                                    <Text size="xs" c="dimmed">
                                        {formatDate(event.calibrated_at)} · {event.calibrated_by}
                                    </Text>
                                </Group>
                                {event.status === 'valid' && (
                                    <Text size="xs" c="dimmed">
                                        有效期至: {event.valid_until}
                                    </Text>
                                )}
                            </Stack>
                        </Timeline.Item>
                    );
                })}
            </Timeline>

            {filteredEvents.length === 0 && (
                <Center py="xl">
                    <Text size="sm" c="dimmed">暂无校准记录</Text>
                </Center>
            )}
        </Paper>
    );
}
