import type { Edge, EdgeProps, InternalNode } from '@xyflow/react';
import { BaseEdge, EdgeLabelRenderer, getBezierPath, Position, useInternalNode, ViewportPortal } from '@xyflow/react';
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
  markerStart,
}: Pick<EdgeProps,'sourceX'|'sourceY'|'targetX'|'targetY'|'sourcePosition'|'targetPosition'|'data'|'style'|'markerEnd'|'markerStart'>) => {
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
  const cableLoss = typeof data?.cable_loss_db === 'number' && Number.isFinite(data.cable_loss_db)
    ? data.cable_loss_db : undefined;
  const owner = data?.loss_owner_connection_id as string | undefined;
  const paGain = typeof data?.pa_gain_db === 'number' && Number.isFinite(data.pa_gain_db)
    ? data.pa_gain_db : undefined;
  const direction = data?.direction as string | undefined;
  
  const isCalibrated = calibratedLoss !== undefined && calibratedLoss !== null;
  const hasPA = paGain !== undefined;
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

  if (owner) {
    lossLabel = `旧值保留，不参与本组计算 · 归属 ${owner}`;
    labelColor = 'gray';
  } else if (isCalibrated) {
    lossLabel = `${calibratedLoss?.toFixed(2)} dB (Cal)`;
    labelColor = 'teal';
  } else if (hasPA) {
    // 仅作标称展示，不写回校准值或进入正式补偿。
    const netGain = cableLoss === undefined ? '未知' : `${(paGain - cableLoss).toFixed(1)}dB`;
    lossLabel = `旧PA ${paGain}dB | 净值 ${netGain}（标称，非实测）`;
    labelColor = 'orange';
  } else {
    lossLabel = cableLoss === undefined ? '损耗未知' : `${cableLoss.toFixed(1)} dB`;
    labelColor = 'blue';
  }

  return (
    <>
      <BaseEdge path={edgePath} markerEnd={markerEnd} markerStart={markerStart} style={edgeStyle} />
      
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
            {direction ? `${direction} · ` : ''}{lossLabel}{data?.portWarning ? ` · ${data.portWarning}` : ''}
          </Badge>
        </Box>
      </EdgeLabelRenderer>
    </>
  );
};

/** 几何只读现有同ID可见handle，可取反端坐标，但绝不新增连接能力或猜缺失pin。 */
export function readOnlyHandlePosition(node:InternalNode|undefined,pin:string|undefined,end:'source'|'target') {
  if(!node||!pin)return null;
  const bounds=node.internals.handleBounds;
  const handle=bounds?.[end]?.find(item=>item.id===pin)??bounds?.[end==='source'?'target':'source']?.find(item=>item.id===pin);
  if(!handle)return null;
  const {position,width,height,x,y}=handle,absolute=node.internals.positionAbsolute;
  return {x:absolute.x+x+(position===Position.Left?0:position===Position.Right?width:width/2),
    y:absolute.y+y+(position===Position.Top?0:position===Position.Bottom?height:height/2),position};
}

/** Strict EdgeWrapper会丢弃反端旧边；仅这类边在同一viewport读取可见端点绘制。 */
export function ReadOnlySignalEdge({edge,onClick}:{edge:Edge;onClick:()=>void}) {
  const source=useInternalNode(edge.source),target=useInternalNode(edge.target);
  const a=readOnlyHandlePosition(source,edge.sourceHandle??undefined,'source'),b=readOnlyHandlePosition(target,edge.targetHandle??undefined,'target');
  if(!a||!b)return null;
  return <ViewportPortal><svg style={{position:'absolute',left:0,top:0,width:1,height:1,overflow:'visible',pointerEvents:'none'}}>
    <g className="topology-readonly-edge" data-id={edge.id} style={{pointerEvents:'all'}} onClick={onClick}>
      <SignalEdge sourceX={a.x} sourceY={a.y} sourcePosition={a.position} targetX={b.x} targetY={b.y} targetPosition={b.position}
        data={edge.data} style={edge.style}/>
    </g>
  </svg></ViewportPortal>;
}

export const customEdgeTypes = {
  signal: SignalEdge,
};
