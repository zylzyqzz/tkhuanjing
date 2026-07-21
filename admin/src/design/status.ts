export const statusText:Record<string,string>={
  online:'在线',unstable:'不稳定',offline:'离线',disabled:'已停用',
  healthy:'正常',degraded:'延迟',interrupted:'中断',unknown:'未配置',
  idle:'未开播',live:'直播中',ended:'已结束',failed:'异常结束',
  open:'待处理',processing:'处理中',resolved:'已恢复',ignored:'已忽略'
}
export const displayStatus=(value:string)=>statusText[value]||value||'未配置'
