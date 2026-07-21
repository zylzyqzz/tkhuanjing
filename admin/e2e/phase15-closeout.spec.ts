import { expect, test, type Page, type Route } from '@playwright/test'

const feature={id:1,feature_code:'device_center',feature_name:'设备中心',category:'enterprise',description:'设备状态',client_type:'all',default_enabled:true,status:'enabled',minimum_client_version:'',config_schema:{}}
const organization={id:1,name:'星云直播',tenant_code:'NEBULA',plan_code:'trial',status:'active'}
const device={device_id:'DEVICE-E2E-001',display_name:'洛杉矶一号机',online_state:'online',agent_version:'2.1.0',last_heartbeat_at:'2026-07-20T10:00:00Z',studio_state:'running',collector_state:'healthy',cpu_percent:25,memory_percent:48,network_latency_ms:42,upload_mbps:30,stream_bitrate_kbps:6000,dropped_frames:0,abnormal_reasons:[],binding:{id:1,room_id:1,account_id:1,anchor_id:1},room:{id:1,name:'洛杉矶直播间'},account:{id:1,display_name:'TikTok US 主账号'},anchor:{id:1,display_name:'Mia'}}

function json(route:Route,body:any,status=200){return route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)})}

async function platformMocks(page:Page,writes:string[]){
  await page.route('**/tk-api/session',r=>json(r,{error:{code:'AUTH_INVALID',message:'未登录'}},401))
  await page.route('**/tk-api/login',r=>json(r,{ok:true,logged_in:true,username:'admin',role:'platform_super',csrf:'csrf-e2e'}))
  await page.route('**/tk-api/enterprise/platform/tenants',r=>json(r,{tenants:[organization]}))
  await page.route('**/api/v2/platform/features',r=>json(r,{items:[feature]}))
  await page.route('**/api/v2/platform/plans/*/features*',r=>{if(r.request().method()!=='GET')writes.push('plan');return json(r,r.request().method()==='GET'?{items:[]}:{ok:true})})
  await page.route('**/api/v2/platform/organizations/1/features*',r=>{if(r.request().method()!=='GET')writes.push('organization');return json(r,r.request().method()==='GET'?{organization:{...organization,plan_code:'trial'},features:{device_center:{name:'设备中心',category:'enterprise',enabled:true,source:'default',reason:'',override:null}},config_version:2}:{ok:true,config_version:3})})
  await page.route('**/api/v2/platform/devices?*',r=>json(r,{items:[device],pagination:{total:1,limit:200,offset:0}}))
  await page.route('**/api/v2/platform/devices/DEVICE-E2E-001/features*',r=>{if(r.request().method()!=='GET')writes.push('device');return json(r,r.request().method()==='GET'?{device:{device_id:device.device_id,display_name:device.display_name,organization_id:1,agent_version:'2.1.0'},features:{device_center:{name:'设备中心',enabled:true,source:'default',rollout:null,override:null}},config_version:2}:{ok:true,config_version:3})})
}

async function login(page:Page,enterprise=false){
  await page.goto('./')
  await page.getByLabel('登录密码').fill('Test-Password-123!')
  if(enterprise)await page.getByLabel('企业代码（企业成员）').fill('NEBULA')
  await page.getByRole('button',{name:'安全登录 →'}).click()
}

test('platform administrator completes plan, organization and device feature flow',async({page})=>{
  const writes:string[]=[];await platformMocks(page,writes);page.on('dialog',dialog=>dialog.accept())
  await login(page)
  await expect(page.getByRole('heading',{name:'平台总览'})).toBeVisible()
  await page.getByRole('button',{name:'◇ 订阅与套餐 ›'}).click()
  await expect(page.getByRole('heading',{name:'套餐功能管理'})).toBeVisible()
  await page.locator('input[type="checkbox"]').uncheck();await page.getByRole('button',{name:'保存配置'}).click();await expect(page.getByText('已保存 trial 套餐，1 家企业将在下次刷新时获得新配置。')).toBeVisible()
  await page.getByRole('button',{name:'◎ 企业功能授权 ›'}).click();await expect(page.getByRole('heading',{name:'企业功能授权',level:1})).toBeVisible()
  await page.getByLabel('企业策略').selectOption('disabled');await page.getByRole('button',{name:'保存授权'}).click();await expect(page.getByText('授权已更新。星云直播 的客户端配置版本已刷新。')).toBeVisible()
  await page.getByRole('button',{name:'▣ 设备功能灰度 ›'}).click();await expect(page.getByRole('heading',{name:'设备功能灰度',level:1})).toBeVisible()
  await page.getByLabel('设备策略').selectOption('disabled');await page.getByPlaceholder('必填：测试目的、负责人或故障编号').fill('E2E 灰度验证');await page.getByRole('button',{name:'保存设备覆盖'}).click();await expect(page.getByText('设备覆盖已保存，该设备将在下一次 Bootstrap 同步后应用。')).toBeVisible()
  expect(writes).toEqual(expect.arrayContaining(['plan','organization','device']))
})

async function enterpriseMocks(page:Page,role='viewer',onboardingCompleted=true){
  const permissions=role==='owner'?['organization.read','devices.read','devices.write','binding.read','binding.write','members.manage']:['organization.read','devices.read','binding.read']
  await page.route('**/tk-api/session',r=>json(r,{error:{code:'AUTH_INVALID',message:'未登录'}},401))
  await page.route('**/tk-api/login',r=>json(r,{error:{code:'AUTH_INVALID',message:'账号或密码错误'}},401))
  await page.route('**/api/v2/auth/login',r=>json(r,{token:'enterprise-e2e-token',permissions,member:{id:9,organization_id:1,username:role,display_name:role==='owner'?'企业主管':'只读人员',role}}))
  await page.route('**/api/v2/organization/bootstrap',r=>json(r,{organization:{id:1,name:'星云直播',code:'NEBULA',plan_code:'trial',onboarding:{step:onboardingCompleted?7:2,completed:onboardingCompleted}},member:{id:9,role},permissions,features:{device_center:{enabled:true},report_center:{enabled:true},alert_center:{enabled:false},member_management:{enabled:true},live_dashboard:{enabled:true}},limits:{},usage:{rooms:1,members:2,devices:1},navigation_context:{},config_version:8}))
  await page.route('**/api/v2/organization/onboarding',r=>json(r,{step:2,completed:false,total_steps:7}))
  await page.route('**/api/v2/organization/options',r=>json(r,{organization:{id:1,name:'星云直播'},rooms:[{id:1,name:'洛杉矶直播间'}],accounts:[{id:1,display_name:'TikTok US 主账号',room_id:1}],anchors:[{id:1,display_name:'Mia'}]}))
  await page.route('**/api/v2/organization/devices?*',r=>json(r,{items:[device],pagination:{total:1,limit:24,offset:0}}))
  await page.route('**/api/v2/organization/devices/DEVICE-E2E-001',r=>json(r,{device:{...device,metrics:{cpu_percent:25,memory_percent:48,network_latency_ms:42,upload_mbps:30,stream_bitrate_kbps:6000,dropped_frames:0}},binding:device.binding,binding_history:[{...device.binding,status:'active',version:1,room_name:'洛杉矶直播间',account_name:'TikTok US 主账号',anchor_name:'Mia',bound_at:'2026-07-20T09:00:00Z'}],metrics_60m:[],audit:[]}))
  await page.route('**/api/v2/organization/audit*',r=>json(r,{items:[],pagination:{total:0}}))
  await page.route('**/api/v2/organization/settings',r=>json(r,{error:{code:'PERMISSION_DENIED',message:'当前账号没有权限',details:{},request_id:'req_e2e'}},403))
}

test('enterprise owner resumes onboarding and reaches the role-aware dashboard',async({page})=>{
  await enterpriseMocks(page,'owner',false);await login(page,true)
  await expect(page.getByRole('heading',{name:'创建第一个直播间'})).toBeVisible()
  await page.getByRole('button',{name:'稍后继续'}).click()
  await expect(page.getByRole('heading',{name:'工作台'})).toBeVisible()
  await expect(page.getByText('企业经营与技术准备度')).toBeVisible()
})

test('enterprise viewer sees dynamic menu and device detail but cannot write',async({page})=>{
  await enterpriseMocks(page);await login(page,true)
  await expect(page.getByRole('heading',{name:'工作台'})).toBeVisible()
  await expect(page.getByRole('button',{name:'! 告警中心 ›'})).toHaveCount(0)
  await expect(page.getByRole('button',{name:'♙ 组织管理 ›'})).toHaveCount(0)
  await page.getByRole('button',{name:'▣ 设备中心 ›'}).click();await expect(page.getByRole('heading',{name:'设备中心',level:1})).toBeVisible()
  await page.getByRole('button',{name:/洛杉矶一号机/}).click();await expect(page.getByRole('heading',{name:'洛杉矶一号机'})).toBeVisible()
  await expect(page.getByRole('button',{name:'换绑'})).toHaveCount(0);await expect(page.getByRole('button',{name:'解绑'})).toHaveCount(0)
  const result=await page.evaluate(async()=>{const r=await fetch('/api/v2/organization/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:'{}'});return{status:r.status,body:await r.json()}})
  expect(result.status).toBe(403);expect(result.body.error.code).toBe('PERMISSION_DENIED')
})
