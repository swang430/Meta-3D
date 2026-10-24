/** 运行记录未知不等于仪器已停止；只读重试及按已知编号取消不受此门限制。 */
export function calibrationActivityBlocked(measuring:boolean,pending:boolean,query:{
  isSuccess:boolean;isFetching:boolean;isPaused:boolean;isError:boolean
}):boolean{
  return measuring||pending||!query.isSuccess||query.isFetching||query.isPaused||query.isError
}
