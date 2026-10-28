import {useEffect,useRef,useState} from 'react';
import {Alert,Button,Checkbox,Group,Modal,Paper,Stack,Text} from '@mantine/core';
import {switchTopologyService} from '../../api/switchTopologyService';
import type {SwitchTopology,TopologyRevisionDetail,TopologyRevisionSummary,TopologyRestorePreview} from '../../api/switchTopologyService';
import {ownsRevisionRequest,revisionFailure} from './topologyRevisionState';
import type {RevisionContext} from './topologyRevisionState';

type Props={opened:boolean;labId:string;topology:SwitchTopology;dirty:boolean;blocked:boolean;
  isBlocked:()=>boolean;onClose:()=>void;onRestore:(targetRevision:number,expectedRevision:number)=>Promise<void>;
  onInspectLatest:()=>Promise<void>};
const raw=(value:unknown)=>JSON.stringify(value,null,2);
const failureText=(err:any)=>{
  const detail=err.response?.data?.detail??err.message??String(err);
  return `${revisionFailure(err.response?.status).message} ${typeof detail==='string'?detail:raw(detail)}`;
};

/** 只读请求拥有自己的代数，不参与父 Flow 的写 ticket 或采集锁。 */
export function TopologyHistoryPanel({opened,labId,topology,dirty,blocked,isBlocked,onClose,onRestore,onInspectLatest}:Props){
  const [skip,setSkip]=useState(0),[items,setItems]=useState<TopologyRevisionSummary[]>([]),[total,setTotal]=useState(0);
  const [selectedRevision,setSelectedRevision]=useState<number|null>(null);
  const [detail,setDetail]=useState<TopologyRevisionDetail|null>(null),[preview,setPreview]=useState<TopologyRestorePreview|null>(null);
  const [confirmed,setConfirmed]=useState(false),[error,setError]=useState(''),[pending,setPending]=useState(false);
  const scope=JSON.stringify([labId,topology.switch_category_id]);
  const serial=useRef(0),live=useRef(true);
  const context=useRef<RevisionContext>({scope,topologyId:topology.id??'',generation:0});
  if(context.current.scope!==scope||context.current.topologyId!==(topology.id??'')){
    context.current={scope,topologyId:topology.id??'',generation:++serial.current};
  }
  const start=()=>{
    const ticket={scope,topologyId:topology.id??'',generation:++serial.current};context.current=ticket;
    setPending(true);setError('');setConfirmed(false);setPreview(null);return ticket;
  };
  const owns=(ticket:RevisionContext)=>live.current&&ownsRevisionRequest(context.current,ticket);
  const load=async(offset:number)=>{
    if(!topology.id)return;
    const ticket=start();setSkip(offset);setSelectedRevision(null);setDetail(null);
    try{const result=await switchTopologyService.listRevisions(topology.id,labId,offset,50);
      if(owns(ticket)){setItems(result.items);setTotal(result.total)}}
    catch(err){if(owns(ticket)){setItems([]);setError(failureText(err))}}
    finally{if(owns(ticket))setPending(false)}
  };
  useEffect(()=>{
    live.current=true;setItems([]);setTotal(0);setSkip(0);setSelectedRevision(null);setDetail(null);setPreview(null);setConfirmed(false);setError('');
    if(opened)void load(0);
    return()=>{live.current=false;context.current={...context.current,generation:++serial.current}};
  },[opened,scope,topology.id,topology.revision]);
  const select=async(revision:number)=>{
    if(!topology.id)return;
    const ticket=start();setSelectedRevision(revision);setDetail(null);
    try{const result=await switchTopologyService.getRevision(topology.id,labId,revision);if(owns(ticket))setDetail(result)}
    catch(err){if(owns(ticket))setError(failureText(err))}
    finally{if(owns(ticket))setPending(false)}
  };
  const prepare=async()=>{
    if(isBlocked()||dirty||selectedRevision===null||!topology.id)return;
    const ticket=start();
    try{const result=await switchTopologyService.previewRestore(topology.id,labId,selectedRevision,topology.revision);if(owns(ticket))setPreview(result)}
    catch(err){if(owns(ticket))setError(failureText(err))}
    finally{if(owns(ticket))setPending(false)}
  };
  const restore=async()=>{
    if(isBlocked()||dirty||!confirmed||!preview||preview.current_revision!==topology.revision)return;
    const candidate=preview,ticket=start();
    try{await onRestore(candidate.target_revision,candidate.current_revision)}
    catch(err){if(owns(ticket))setError(failureText(err))}
    finally{if(owns(ticket))setPending(false)}
  };
  return <Modal opened={opened} onClose={onClose} title="保存修订历史" size="xl" closeOnClickOutside={false}>
    <Stack>
      <Alert color="orange">历史原件只读。恢复将生成新修订、清空已有内嵌校准值；不恢复采用、证书或执行资格。</Alert>
      <Text size="xs">Lab {labId} · 原图 {topology.id} · 当前保存 r{topology.revision}</Text>
      {dirty&&<Alert color="yellow">草稿未保存：允许只读查阅历史；请先保存或显式放弃草稿，再预览和执行恢复。</Alert>}
      <Group><Button variant="light" loading={pending} onClick={()=>void load(skip)}>刷新历史列表</Button>
        <Button variant="light" onClick={()=>void onInspectLatest()}>刷新查看服务器最新</Button></Group>
      {!pending&&total===0&&!error&&<Text>尚无修订留痕，从首次保存开始记录</Text>}
      {items.map(item=><Button key={item.revision} variant={selectedRevision===item.revision?'filled':'light'}
        onClick={()=>void select(item.revision)}>r{item.revision} · {item.operation} · {item.created_at}
        {item.restored_from_revision!==null?` · 恢复来源 r${item.restored_from_revision}`:''}</Button>)}
      <Group><Button disabled={skip===0||pending} onClick={()=>void load(Math.max(0,skip-50))}>上一页</Button>
        <Text size="xs">{skip+1}–{Math.min(skip+50,total)} / {total}（每页50）</Text>
        <Button disabled={skip+50>=total||pending} onClick={()=>void load(skip+50)}>下一页</Button></Group>
      {detail&&<Paper withBorder p="sm"><Text fw={600}>历史原件 r{detail.revision}（raw，只读）</Text>
        <pre style={{whiteSpace:'pre-wrap',maxHeight:260,overflow:'auto'}}>{raw(detail.snapshot)}</pre>
        <Text>当时状态，仅供查阅，不恢复</Text><pre style={{whiteSpace:'pre-wrap'}}>{raw(detail.recorded_metadata)}</pre></Paper>}
      <Button disabled={blocked||dirty||selectedRevision===null||pending} onClick={()=>void prepare()}>预览恢复差异</Button>
      {preview&&<Paper withBorder p="sm" data-testid="topology-restore-preview"><Stack gap="xs">
        <Text fw={600}>历史原件</Text><pre style={{whiteSpace:'pre-wrap',maxHeight:200,overflow:'auto'}}>{raw(preview.snapshot)}</pre>
        <Text fw={600}>将写入候选</Text><pre style={{whiteSpace:'pre-wrap',maxHeight:200,overflow:'auto'}}>{raw(preview.candidate)}</pre>
        <Text fw={600}>当前差异</Text><pre style={{whiteSpace:'pre-wrap',maxHeight:200,overflow:'auto'}}>{raw(preview.differences)}</pre>
        <Alert color="orange">恢复清空内嵌校准值，不自动重新采用，不代表通路合格</Alert>
        {preview.warnings.map((warning,i)=><Text key={i}>{warning}</Text>)}
      </Stack></Paper>}
      {error&&<Alert color="red" data-testid="topology-history-error">{error}</Alert>}
      <Checkbox checked={confirmed} onChange={event=>setConfirmed(event.currentTarget.checked)}
        label="确认将此历史声明恢复为新的保存修订" disabled={blocked||dirty||!preview||pending}/>
      <Group justify="flex-end"><Button variant="default" onClick={onClose}>关闭历史</Button>
        <Button data-testid="topology-restore-confirm" disabled={blocked||dirty||!confirmed||!preview||pending||preview.current_revision!==topology.revision}
          onClick={()=>void restore()}>恢复为新修订</Button></Group>
    </Stack>
  </Modal>;
}
