import {useEffect, useState} from 'react';
import {NumberInput, Stack, Text, TextInput} from '@mantine/core';
import {nominalMetadata, parseOptionalNominalNumber} from './nominalProperties';
import type {NominalField, NominalFieldMetadata} from './nominalProperties';

interface Props {
  fields: readonly NominalField[];
  values: Record<string, unknown>;
  metadata: unknown;
  disabled: boolean;
  /** undefined 仅表示未编辑数值；明确清空仍为 null。 */
  onChange: (key:string,value:number|null|undefined,metadata:NominalFieldMetadata)=>void;
  /** 中间输入不写入草稿，但必须阻止外层应用旧值。 */
  onValidityChange?: (valid:boolean)=>void;
  metadataOnly?: boolean;
}

function Field({field, value, metadata, disabled, onChange, onValidityChange, metadataOnly}: {
  field:NominalField;value:unknown;metadata:any;disabled:boolean;metadataOnly?:boolean;
  onChange:Props['onChange'];onValidityChange:(key:string,valid:boolean)=>void;
}) {
  const finite=typeof value==='number'&&Number.isFinite(value);
  const [number,setNumber]=useState<number|string>(finite?value:'');
  const [source,setSource]=useState(typeof metadata?.source_note==='string'?metadata.source_note:'');
  const [start,setStart]=useState<number|string>(metadata?.frequency_range_mhz?.[0]??'');
  const [stop,setStop]=useState<number|string>(metadata?.frequency_range_mhz?.[1]??'');
  const [error,setError]=useState<string|null>(null);
  const [numberEdited,setNumberEdited]=useState(false);
  const badLegacy=value!==null&&value!==undefined&&!finite;
  const commit=(next:number|string,note:string,a:number|string,b:number|string,edited=numberEdited)=>{
    try {
      const parsed=edited?parseOptionalNominalNumber(next):undefined;
      if(field.nonnegative&&parsed!==null&&parsed!==undefined&&parsed<0)throw new Error('标称值不能为负数');
      const meta=nominalMetadata(field.unit,note,a,b);
      setError(null);onValidityChange(field.key,true);
      onChange(field.key,parsed,meta);
    }catch(e){setError(e instanceof Error?e.message:String(e));onValidityChange(field.key,false)}
  };
  return <Stack gap="xs">
    <Text size="xs" c="dimmed">{metadata ? `标称/非实测；${typeof metadata.source_note==='string'&&metadata.source_note.trim()?'来源说明不构成资格证据':'来源未声明，不能作为资格证据'}`
      : value===null||value===undefined ? '标称值未声明；非实测' : '旧版标称/来源未声明；非实测'}</Text>
    {badLegacy&&<Text size="xs" c="orange">旧值格式未核实（原值只读）：{JSON.stringify(value)}；未主动编辑时保留原值。</Text>}
    {!metadataOnly&&<NumberInput label={`${field.label} (${field.unit})`} value={number} disabled={disabled}
      clampBehavior="none" error={error} onChange={next=>{setNumberEdited(true);setNumber(next);commit(next,source,start,stop,true)}}/>}
    <TextInput label={`${field.label}来源说明`} value={source} disabled={disabled} error={metadataOnly?error:undefined}
      onChange={event=>{const note=event.currentTarget.value;setSource(note);commit(number,note,start,stop)}}/>
    <NumberInput label={`${field.label}适用起始频率 (MHz)`} value={start} disabled={disabled} clampBehavior="none" error={error}
      onChange={next=>{setStart(next);commit(number,source,next,stop)}}/>
    <NumberInput label={`${field.label}适用结束频率 (MHz)`} value={stop} disabled={disabled} clampBehavior="none"
      onChange={next=>{setStop(next);commit(number,source,start,next)}}/>
  </Stack>;
}

export function NominalPropertyFields({fields,values,metadata,disabled,onChange,onValidityChange,metadataOnly}:Props) {
  const [invalid,setInvalid]=useState<Record<string,boolean>>({});
  const valid=Object.values(invalid).every(value=>!value);
  useEffect(()=>{onValidityChange?.(valid)},[valid,onValidityChange]);
  return <Stack gap="md">{fields.map(field=><Field key={field.key} field={field} value={values[field.key]}
    metadata={metadata&&typeof metadata==='object'?(metadata as Record<string,unknown>)[field.key]:undefined}
    disabled={disabled} metadataOnly={metadataOnly} onChange={onChange}
    onValidityChange={(key,isValid)=>setInvalid(current=>({...current,[key]:!isValid}))}/>)}</Stack>;
}
