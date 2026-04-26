import type { EdgeProps } from '@xyflow/react';
import { BaseEdge, EdgeLabelRenderer, getBezierPath } from '@xyflow/react';
import { Badge, Box, Group } from '@mantine/core';

export const SignalEdge = ({
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  style,
  markerEnd,
}: EdgeProps) => {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  // Calculate visual properties
  const calibratedLoss = data?.calibrated_loss_db as number | undefined | null;
  const cableLoss = data?.cable_loss_db as number | undefined;
  const paGain = data?.pa_gain_db as number | undefined;
  const direction = data?.direction as string | undefined;
  
  const isCalibrated = calibratedLoss !== undefined && calibratedLoss !== null;
  const hasPA = paGain !== undefined && paGain !== null && paGain > 0;
  const isUplink = direction === 'UL';
  
  // Custom styles for edge
  const edgeColor = isUplink ? '#D946EF' : (isCalibrated ? '#10B981' : (hasPA ? '#F59E0B' : '#3B82F6'));
  const edgeStyle = {
    ...style,
    strokeWidth: 2,
    stroke: edgeColor,
    strokeDasharray: isUplink ? '5, 5' : 'none',
  };

  // Build label text
  let lossLabel: string;
  let labelColor: string;

  if (isCalibrated) {
    lossLabel = `${calibratedLoss?.toFixed(2)} dB (Cal)`;
    labelColor = 'teal';
  } else if (hasPA) {
    // Show net gain: PA gain minus cable loss
    const netGain = (paGain || 0) - (cableLoss || 0);
    lossLabel = `PA +${paGain}dB | Net +${netGain.toFixed(1)}dB`;
    labelColor = 'orange';
  } else {
    lossLabel = `${cableLoss?.toFixed(1) || 0} dB`;
    labelColor = 'blue';
  }

  return (
    <>
      <BaseEdge path={edgePath} markerEnd={markerEnd} style={edgeStyle} />
      
      <EdgeLabelRenderer>
        <Box
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            pointerEvents: 'all',
            zIndex: 10,
          }}
        >
          <Badge 
            size="xs" 
            variant="filled" 
            color={labelColor}
            style={{ cursor: 'pointer', boxShadow: '0 1px 3px rgba(0,0,0,0.2)' }}
          >
            {lossLabel}
          </Badge>
        </Box>
      </EdgeLabelRenderer>
    </>
  );
};

export const customEdgeTypes = {
  signal: SignalEdge,
};
