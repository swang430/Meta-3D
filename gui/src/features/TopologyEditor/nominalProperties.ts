import type {TopologyNode, TopologyConnection} from '../../api/switchTopologyService';

export interface NominalFieldMetadata {
  unit: 'dB' | 'dBi';
  source_note: string | null;
  frequency_range_mhz: [number, number] | null;
}
export interface NominalField {
  key: string;
  label: string;
  unit: 'dB' | 'dBi';
  nonnegative: boolean;
}
const fields: Record<string, readonly NominalField[]> = {
  amplifier: [{key:'gain_db',label:'PA标称增益',unit:'dB',nonnegative:false}],
  pad: [{key:'attenuation_db',label:'标称衰减',unit:'dB',nonnegative:true}],
  combiner: [{key:'loss_db',label:'标称插损',unit:'dB',nonnegative:true}],
};
const antennaFields: readonly NominalField[] = [{key:'gain_dbi',label:'标称天线增益',unit:'dBi',nonnegative:false}];
const emptyFields: readonly NominalField[] = [];
export const edgeNominalFields: readonly NominalField[] = [
  {key:'pa_gain_db',label:'旧PA标称增益',unit:'dB',nonnegative:false},
];
export const cableNominalFields: readonly NominalField[] = [
  {key:'cable_loss_db',label:'标称电缆损耗',unit:'dB',nonnegative:true},
];

export function nominalFieldsForNode(type: string): readonly NominalField[] {
  return ['probe','antenna','reference_antenna'].includes(type) ? antennaFields : fields[type] ?? emptyFields;
}

export function parseOptionalNominalNumber(value: number|string): number|null {
  if (value === '') return null;
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error('请输入有限数值');
  return value;
}

export function nominalMetadata(unit: 'dB'|'dBi', source: string,
  start: number|string, stop: number|string): NominalFieldMetadata {
  const a=parseOptionalNominalNumber(start), b=parseOptionalNominalNumber(stop);
  if ((a===null)!==(b===null) || a!==null && b!==null && (a<=0 || b<=0 || a>b)) {
    throw new Error('频率须同时填写两个有限正数，且起始不大于结束');
  }
  return {unit,source_note:source.trim()||null,frequency_range_mhz:a===null?null:[a,b!]};
}

function metadataMap(value: unknown): Record<string, any> {
  return value && typeof value==='object' && !Array.isArray(value) ? value as Record<string, any> : {};
}
function copyMetadata(metadata: NominalFieldMetadata): NominalFieldMetadata {
  return {...metadata,frequency_range_mhz:metadata.frequency_range_mhz?[...metadata.frequency_range_mhz]:null};
}
export function setNodeNominal(node: TopologyNode,key: string,value: number|null|undefined,metadata: NominalFieldMetadata): TopologyNode {
  return {...node,params:{...node.params,...(value===undefined?{}:{[key]:value}),nominal_metadata:{
    ...metadataMap(node.params.nominal_metadata),[key]:copyMetadata(metadata)}}};
}
export function setEdgeNominal(edge: TopologyConnection,key: string,value: number|null|undefined,metadata: NominalFieldMetadata): TopologyConnection & {nominal_metadata: Record<string, any>} {
  return {...edge,...(value===undefined?{}:{[key]:value}),nominal_metadata:{...metadataMap(edge.nominal_metadata),[key]:copyMetadata(metadata)}};
}
