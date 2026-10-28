export type RevisionContext={scope:string;topologyId:string;generation:number};
export type RevisionGuards={dirty:boolean;writing:boolean;collectionBusy:boolean;unknownWrite:boolean};
export function ownsRevisionRequest(a:RevisionContext,b:RevisionContext):boolean {
  return a.scope===b.scope&&a.topologyId===b.topologyId&&a.generation===b.generation;
}
export function canRestore(s:RevisionGuards):boolean {
  return !s.dirty&&!s.writing&&!s.collectionBusy&&!s.unknownWrite;
}
export function revisionFailure(status:number|undefined):{kind:'conflict'|'unknown'|'rejected';message:string} {
  if(status===409)return {kind:'conflict',message:'服务器已变化，草稿和输入已保留；请显式刷新核对，不会自动覆盖。'};
  if(status===undefined||status>=500)return {kind:'unknown',message:'保存结果未知；请刷新服务器修订核对，禁止自动重试恢复。离开不会取消服务器请求，返回后请核查服务器最新修订。'};
  return {kind:'rejected',message:'请求被拒绝，草稿和输入已保留。'};
}
