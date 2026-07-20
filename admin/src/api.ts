import { reactive } from 'vue'

export const session = reactive({loggedIn:false, username:'', role:'', tenantId:null as number|null, csrf:'', permissions:[] as string[], subscription:null as any, enterpriseToken:''})

export async function api(path:string, options:RequestInit={}) {
  const headers=new Headers(options.headers||{})
  if(session.csrf&&options.method&&options.method!=='GET') headers.set('X-CSRF-Token',session.csrf)
  if(session.enterpriseToken&&path.startsWith('/api/v2/')) headers.set('Authorization',`Bearer ${session.enterpriseToken}`)
  if(options.body&&!(options.body instanceof FormData)) headers.set('Content-Type','application/json')
  const response=await fetch(path,{credentials:'same-origin',...options,headers})
  const body=await response.json().catch(()=>({}))
  if(!response.ok) throw new Error(body.error?.message||body.detail||`请求失败 ${response.status}`)
  return body
}

export function applyMemberSession(data:any){session.loggedIn=true;session.username=data.member.username;session.role=data.member.role;session.tenantId=data.member.organization_id;session.permissions=data.permissions||['organization.read','devices.read','binding.read'];session.enterpriseToken=data.token;sessionStorage.setItem('vd-member-token',data.token);sessionStorage.setItem('vd-member',JSON.stringify({...data.member,permissions:session.permissions}))}

export function applySession(data:any){
  session.loggedIn=!!data.logged_in||!!data.ok; session.username=data.username||''; session.role=data.role||'platform_super';
  session.tenantId=data.tenant_id??null; session.csrf=data.csrf||session.csrf; session.permissions=data.permissions||[]; session.subscription=data.subscription_summary||null
}
