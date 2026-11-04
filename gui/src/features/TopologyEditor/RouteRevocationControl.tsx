import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Checkbox, Stack, Text, Textarea } from '@mantine/core'
import { fetchRouteRevocation, revokeRouteApplication } from '../../api/labProfileService'
import type { RouteApplicationRecord } from '../../types/api'

export function RouteRevocationControl({labId,record,blocked}:{labId:string;record:RouteApplicationRecord;blocked:boolean}) {
  const [reason,setReason]=useState(''),[confirmed,setConfirmed]=useState(false)
  const cache=useQueryClient(),key=['route-revocation',labId,record.acquisition_run_id]
  const status=useQuery({queryKey:key,queryFn:()=>fetchRouteRevocation(labId,record.id,record.acquisition_run_id),retry:false})
  // POST回执和回执丢失后的GET恢复，均以同一撤销事实更新关联视图。
  useEffect(()=>{
    if(!status.data)return
    void cache.invalidateQueries({queryKey:['route-application-preview',labId]})
    void cache.invalidateQueries({queryKey:['route-availability',labId]})
  },[cache,labId,status.data?.id])
  const revoke=useMutation({mutationFn:()=>revokeRouteApplication(labId,record.id,record.acquisition_run_id,{confirmed:true,reason:reason.trim()}),
    onSuccess:async value=>{
      // 另一行可能正在读取同run的旧状态，不能让迟到null覆盖成功回执。
      await cache.cancelQueries({queryKey:key})
      cache.setQueryData(key,value)
      setConfirmed(false)
    },onError:()=>{void cache.invalidateQueries({queryKey:key})}})
  const current=!status.isFetching&&!status.isError&&!status.isPaused?status.data:undefined
  const allowed=current===null&&!blocked&&!revoke.isPending&&confirmed&&reason.trim().length>0&&reason.trim().length<=2000
  return <Stack gap="xs" data-testid="route-revocation">
    {status.isFetching?<Text size="xs">读取撤销状态…</Text>
      :status.isError||status.isPaused?<Alert color="yellow">撤销状态未知，不能据旧状态操作。</Alert>
      :current?<Alert color="yellow">已撤销后续选用：{current.reason} · {current.revoked_at}。原始记录及已冻结执行保留。</Alert>
      :<Text size="xs">未见撤销记录；不代表此记录当前适用或正式有效。</Text>}
    <Button size="xs" variant="subtle" disabled={revoke.isPending} onClick={()=>void status.refetch()}>重读撤销状态</Button>
    {current===null&&<details><summary>撤销本次采集的后续选用</summary><Stack gap="xs" mt="xs">
      <Text size="sm">同次采集的所有采用记录均停止供新执行选用；不会取消正在运行的测试，也不改写旧执行。历史报告影响须另外核查。</Text>
      <Textarea label="撤销原因" maxLength={2000} value={reason} disabled={revoke.isPending||blocked}
        onChange={event=>{setReason(event.currentTarget.value);setConfirmed(false);revoke.reset()}}/>
      <Checkbox label="我确认撤销这次采集的后续选用" checked={confirmed} disabled={revoke.isPending||blocked}
        onChange={event=>setConfirmed(event.currentTarget.checked)}/>
      <Button color="red" disabled={!allowed} loading={revoke.isPending} onClick={()=>revoke.mutate()}>确认撤销后续选用</Button>
      {blocked&&<Text size="sm">采集作业尚未确认结束，暂不开放撤销。</Text>}
    </Stack></details>}
    {revoke.isError&&<Alert color={current?'blue':'red'}>{current
      ?'原请求未获成功回执，随后读取服务器已确认撤销。'
      :'撤销请求未获成功回执。输入已保留，请重读状态核对；未将请求发送当作成功。'}</Alert>}
  </Stack>
}
