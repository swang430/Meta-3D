/**
 * Calibration Dependency Graph Component
 * 
 * 可视化校准项之间的依赖关系
 */
import { useState } from 'react';
import {
    Paper,
    Text,
    Group,
    Badge,
    Stack,
    Box,
    Tooltip,
    ActionIcon,
    ThemeIcon,
} from '@mantine/core';
import {
    IconCircleCheck,
    IconAlertTriangle,
    IconClock,
    IconArrowRight,
    IconRefresh,
} from '@tabler/icons-react';

interface CalibrationNode {
    id: string;
    name: string;
    status: 'valid' | 'expired' | 'invalidated' | 'pending';
    validUntil?: string;
    dependencies: string[];
}

// 校准项依赖关系
const calibrationNodes: CalibrationNode[] = [
    {
        id: 'probe_path_loss',
        name: '探头路损',
        status: 'valid',
        validUntil: '2026-07-27',
        dependencies: [],
    },
    {
        id: 'probe_phase',
        name: '探头相位',
        status: 'valid',
        validUntil: '2026-04-27',
        dependencies: ['probe_path_loss'],
    },
    {
        id: 'rf_chain_ul',
        name: 'RF链路(UL)',
        status: 'expired',
        validUntil: '2026-01-15',
        dependencies: ['probe_path_loss'],
    },
    {
        id: 'rf_chain_dl',
        name: 'RF链路(DL)',
        status: 'valid',
        validUntil: '2026-04-20',
        dependencies: ['probe_path_loss'],
    },
    {
        id: 'channel_phase',
        name: '通道相位',
        status: 'valid',
        validUntil: '2026-04-27',
        dependencies: ['probe_phase', 'rf_chain_ul', 'rf_chain_dl'],
    },
    {
        id: 'e2e_matrix',
        name: 'E2E补偿',
        status: 'invalidated',
        dependencies: ['channel_phase', 'rf_chain_ul', 'rf_chain_dl'],
    },
    {
        id: 'ce_internal',
        name: 'CE内部',
        status: 'valid',
        validUntil: '2026-04-20',
        dependencies: [],
    },
    {
        id: 'quiet_zone',
        name: '静区校准',
        status: 'valid',
        validUntil: '2026-06-15',
        dependencies: ['e2e_matrix', 'ce_internal'],
    },
];

const statusConfig = {
    valid: { color: 'green', icon: IconCircleCheck, label: '有效' },
    expired: { color: 'red', icon: IconAlertTriangle, label: '已过期' },
    invalidated: { color: 'orange', icon: IconAlertTriangle, label: '已失效' },
    pending: { color: 'gray', icon: IconClock, label: '待校准' },
};

interface NodeCardProps {
    node: CalibrationNode;
    isHighlighted: boolean;
    onHover: (id: string | null) => void;
}

function NodeCard({ node, isHighlighted, onHover }: NodeCardProps) {
    const StatusIcon = statusConfig[node.status].icon;
    const statusColor = statusConfig[node.status].color;

    return (
        <Tooltip
            label={node.validUntil ? `有效期至: ${node.validUntil}` : '无有效期信息'}
            position="top"
        >
            <Paper
                p="xs"
                withBorder
                style={{
                    borderColor: isHighlighted ? `var(--mantine-color-${statusColor}-5)` : undefined,
                    borderWidth: isHighlighted ? 2 : 1,
                    opacity: isHighlighted ? 1 : 0.85,
                    transition: 'all 0.2s ease',
                    cursor: 'pointer',
                }}
                onMouseEnter={() => onHover(node.id)}
                onMouseLeave={() => onHover(null)}
            >
                <Group gap="xs" wrap="nowrap">
                    <ThemeIcon size="sm" color={statusColor} variant="light">
                        <StatusIcon size={12} />
                    </ThemeIcon>
                    <Text size="xs" fw={500} lineClamp={1}>
                        {node.name}
                    </Text>
                </Group>
            </Paper>
        </Tooltip>
    );
}

export function CalibrationDependencyGraph() {
    const [hoveredNode, setHoveredNode] = useState<string | null>(null);

    // 找到所有与 hoveredNode 相关的节点
    const getRelatedNodes = (nodeId: string | null): Set<string> => {
        if (!nodeId) return new Set();

        const related = new Set<string>([nodeId]);
        const node = calibrationNodes.find(n => n.id === nodeId);

        if (node) {
            // 添加依赖
            node.dependencies.forEach(dep => related.add(dep));

            // 添加反向依赖（被依赖）
            calibrationNodes.forEach(n => {
                if (n.dependencies.includes(nodeId)) {
                    related.add(n.id);
                }
            });
        }

        return related;
    };

    const relatedNodes = getRelatedNodes(hoveredNode);

    // 按层级组织节点
    const level0 = calibrationNodes.filter(n => n.dependencies.length === 0);
    const level1 = calibrationNodes.filter(n =>
        n.dependencies.length > 0 &&
        n.dependencies.every(d => level0.find(l => l.id === d))
    );
    const level2 = calibrationNodes.filter(n =>
        !level0.includes(n) && !level1.includes(n)
    );

    // 统计
    const validCount = calibrationNodes.filter(n => n.status === 'valid').length;
    const expiredCount = calibrationNodes.filter(n => n.status === 'expired').length;
    const invalidatedCount = calibrationNodes.filter(n => n.status === 'invalidated').length;

    return (
        <Paper p="md" withBorder>
            <Group justify="space-between" mb="md">
                <Text size="sm" fw={600}>校准依赖关系</Text>
                <Group gap="xs">
                    <Badge size="xs" color="green" variant="light">{validCount} 有效</Badge>
                    <Badge size="xs" color="red" variant="light">{expiredCount} 过期</Badge>
                    <Badge size="xs" color="orange" variant="light">{invalidatedCount} 失效</Badge>
                </Group>
            </Group>

            <Stack gap="lg">
                {/* Level 0: 基础校准 */}
                <Box>
                    <Text size="xs" c="dimmed" mb="xs">基础层</Text>
                    <Group gap="sm">
                        {level0.map(node => (
                            <NodeCard
                                key={node.id}
                                node={node}
                                isHighlighted={relatedNodes.has(node.id) || !hoveredNode}
                                onHover={setHoveredNode}
                            />
                        ))}
                    </Group>
                </Box>

                {/* 箭头 */}
                <Group justify="center">
                    <IconArrowRight size={16} style={{ opacity: 0.3, transform: 'rotate(90deg)' }} />
                </Group>

                {/* Level 1: 中间层 */}
                <Box>
                    <Text size="xs" c="dimmed" mb="xs">中间层</Text>
                    <Group gap="sm">
                        {level1.map(node => (
                            <NodeCard
                                key={node.id}
                                node={node}
                                isHighlighted={relatedNodes.has(node.id) || !hoveredNode}
                                onHover={setHoveredNode}
                            />
                        ))}
                    </Group>
                </Box>

                {/* 箭头 */}
                <Group justify="center">
                    <IconArrowRight size={16} style={{ opacity: 0.3, transform: 'rotate(90deg)' }} />
                </Group>

                {/* Level 2: 顶层 */}
                <Box>
                    <Text size="xs" c="dimmed" mb="xs">系统层</Text>
                    <Group gap="sm">
                        {level2.map(node => (
                            <NodeCard
                                key={node.id}
                                node={node}
                                isHighlighted={relatedNodes.has(node.id) || !hoveredNode}
                                onHover={setHoveredNode}
                            />
                        ))}
                    </Group>
                </Box>
            </Stack>

            {/* 级联失效提示 */}
            {expiredCount > 0 || invalidatedCount > 0 ? (
                <Paper p="xs" mt="md" bg="orange.0" radius="sm">
                    <Group gap="xs">
                        <IconAlertTriangle size={14} color="orange" />
                        <Text size="xs" c="orange.8">
                            检测到 {expiredCount + invalidatedCount} 个校准项需要重新校准，可能影响下游校准有效性
                        </Text>
                    </Group>
                </Paper>
            ) : null}
        </Paper>
    );
}
