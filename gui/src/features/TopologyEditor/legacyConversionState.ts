import type {ConversionNodeEdit, ConversionConnectionEdit, TopologyConversionRequest} from '../../api/switchTopologyService';

export const conversionContextKey = (labId:string, topologyId:string) => JSON.stringify([labId,topologyId]);

// 只发送操作员触碰的键；undefined 不得退化为 null。
export function buildConversionRequest(nodes:ConversionNodeEdit[],connections:ConversionConnectionEdit[]):TopologyConversionRequest {
  const clean=(row:object)=>Object.fromEntries(Object.entries(row).filter(([,v])=>v!==undefined));
  for(const row of [...nodes,...connections])for(const [key,value] of Object.entries(row)) {
    if(value===undefined)continue;
    if(value===null && !['cable_loss_db','loss_owner_connection_id'].includes(key))throw Error(`${key} 不允许 null`);
    if(key==='loss_owner_connection_id' && (row as ConversionConnectionEdit).same_physical_cable_confirmed!==true)
      throw Error('设置或撤销归属均需明确确认同一物理线缆');
  }
  return {nodes:nodes.map(row=>clean(row) as unknown as ConversionNodeEdit),
    connections:connections.map(row=>clean(row) as unknown as ConversionConnectionEdit)};
}

// 会话取消/切换只清转换态，不接收、更不改写原画布 draft。
export function clearConversionSession<T>(draft:T) {return {draft,preview:null,nodeEdits:{},connectionEdits:{}};}
