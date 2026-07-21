import { reactive } from 'vue'

export const session = reactive({loggedIn:false, username:'', role:'', tenantId:null as number|null, csrf:'', permissions:[] as string[], subscription:null as any, enterpriseToken:'',organizationCode:'',bootstrap:null as any,bootstrapLoading:false,bootstrapError:''})

export function clearMemberSession(){
  sessionStorage.removeItem('vd-member-token')
  sessionStorage.removeItem('vd-member')
  session.loggedIn=false
  session.username=''
  session.role=''
  session.tenantId=null
  session.permissions=[]
  session.enterpriseToken=''
  session.organizationCode=''
  session.bootstrap=null
}

export async function api(path:string, options:RequestInit={}) {
  const headers=new Headers(options.headers||{})
  if(session.csrf&&options.method&&options.method!=='GET') headers.set('X-CSRF-Token',session.csrf)
  if(session.enterpriseToken&&path.startsWith('/api/v2/')) headers.set('Authorization',`Bearer ${session.enterpriseToken}`)
  if(options.body&&!(options.body instanceof FormData)) headers.set('Content-Type','application/json')
  const response=await fetch(path,{credentials:'same-origin',...options,headers})
  const body=await response.json().catch(()=>({}))
  if(!response.ok) {
    const code=body.error?.code
    if(session.enterpriseToken&&response.status===401&&(code==='AUTH_INVALID'||code==='AUTH_EXPIRED'))clearMemberSession()
    const error:any=new Error(body.error?.message||body.detail||`请求失败 ${response.status}`);error.code=code;error.details=body.error?.details;error.requestId=body.error?.request_id;error.status=response.status;throw error
  }
  return body
}

export function applyMemberSession(data:any){session.loggedIn=true;session.username=data.member.username;session.role=data.member.role;session.tenantId=data.member.organization_id;session.permissions=data.permissions||['organization.read','devices.read','binding.read'];session.enterpriseToken=data.token;session.organizationCode=data.organization_code||'';sessionStorage.setItem('vd-member-token',data.token);sessionStorage.setItem('vd-member',JSON.stringify({...data.member,permissions:session.permissions,organization_code:session.organizationCode}))}

export function applySession(data:any){
  session.loggedIn=!!data.logged_in||!!data.ok; session.username=data.username||''; session.role=data.role||'platform_super';
  session.tenantId=data.tenant_id??null; session.csrf=data.csrf||session.csrf; session.permissions=data.permissions||[]; session.subscription=data.subscription_summary||null
}

export async function loadBootstrap(){
  if(!session.enterpriseToken)return null
  session.bootstrapLoading=true;session.bootstrapError=''
  try{const value=await api('/api/v2/organization/bootstrap');session.bootstrap=value;session.permissions=value.permissions||session.permissions;session.organizationCode=value.organization?.code||session.organizationCode;return value}
  catch(error:any){session.bootstrapError=error.message;throw error}
  finally{session.bootstrapLoading=false}
}

export function featureEnabled(code?:string){return !code||session.bootstrap?.features?.[code]?.enabled===true}
export function hasPermission(permission?:string){return !permission||session.permissions.includes(permission)||session.permissions.includes('*')}
