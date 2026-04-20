import type { EdgeProps } from '@xyflow/react';
import { BaseEdge, EdgeLabelRenderer, getBezierPath } from '@xyflow/react';
import { Badge, Box } from '@mantine/core';

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
  
  const isCalibrated = calibratedLoss !== undefined && calibratedLoss !== null;
  const isInactive = data?.inactive === true;
  
  // Custom styles for edge
  const edgeStyle = {
    ...style,
    strokeWidth: isInactive ? 1 : 2,
    stroke: isInactive 
      ? '#D1D5DB' // Gray for inactive paths
      : (isCalibrated ? '#10B981' : '#3B82F6'), // Green if calibrated, Blue otherwise
    opacity: isInactive ? 0.4 : 1,
  };

  return (
    <>
      <BaseEdge path={edgePath} markerEnd={markerEnd} style={edgeStyle} />
      
      {!isInactive && (
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
              color={isCalibrated ? "teal" : "blue"}
              style={{ cursor: 'pointer', boxShadow: '0 1px 3px rgba(0,0,0,0.2)' }}
            >
              {isCalibrated 
                ? `${calibratedLoss?.toFixed(2)} dB (Cal)` 
                : `${cableLoss?.toFixed(1) || 0} dB`}
            </Badge>
          </Box>
        </EdgeLabelRenderer>
      )}
    </>
  );
};

export const customEdgeTypes = {
  signal: SignalEdge,
};
