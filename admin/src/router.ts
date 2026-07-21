import{createRouter,createWebHistory}from'vue-router'
import{featureEnabled,hasPermission,session}from'./api'
import PlatformView from'./views/PlatformView.vue'
import EnterpriseDashboard from'./views/EnterpriseDashboard.vue'
import DeviceView from'./views/DeviceView.vue'
import AccountView from'./views/AccountView.vue'
import ReportView from'./views/ReportView.vue'
import AlertView from'./views/AlertView.vue'
import MemberView from'./views/MemberView.vue'
import RealtimeDevicesView from'./views/RealtimeDevicesView.vue'
import FeatureCenterView from'./views/FeatureCenterView.vue'
import FeatureSettingsView from'./views/FeatureSettingsView.vue'
import OnboardingView from'./views/OnboardingView.vue'
import PlaceholderView from'./views/PlaceholderView.vue'
import AccessStateView from'./views/AccessStateView.vue'
import PlatformDashboardView from'./views/PlatformDashboardView.vue'
import OrganizationFeaturesView from'./views/OrganizationFeaturesView.vue'

const platform=(path:string,name:string,title:string)=>({path:`/platform/${path}`,name,component:path==='overview'?PlatformDashboardView:path==='organizations'?PlatformView:path==='features'?FeatureCenterView:path==='organization-features'?OrganizationFeaturesView:PlaceholderView,meta:{audience:'platform',title}})
const enterprise=(path:string,name:string,title:string,component:any,feature?:string,permission?:string)=>({path:`/enterprise/${path}`,name,component,meta:{audience:'enterprise',title,feature,permission}})

export const router=createRouter({history:createWebHistory('/tk-admin/'),routes:[
 {path:'/',redirect:'/enterprise/dashboard'},
 platform('overview','platform-overview','平台总览'),platform('organizations','platform-organizations','企业管理'),platform('subscriptions','platform-subscriptions','订阅与套餐'),platform('features','platform-features','功能模块'),platform('organization-features','platform-organization-features','企业功能授权'),platform('devices','platform-devices','平台设备'),platform('providers','platform-providers','Provider'),platform('releases','platform-releases','版本发布'),platform('settings','platform-settings','系统配置'),platform('alerts','platform-alerts','平台告警'),platform('audit','platform-audit','平台审计'),
 enterprise('dashboard','enterprise-dashboard','工作台',EnterpriseDashboard),
 enterprise('live','enterprise-live','直播中心',AccountView,'live_dashboard','organization.read'),
 enterprise('devices','enterprise-devices','设备中心',RealtimeDevicesView,'device_center','devices.read'),
 enterprise('device-list','enterprise-device-list','设备列表',DeviceView,'device_center','devices.read'),
 enterprise('analytics','enterprise-analytics','运营分析',ReportView,'report_center','organization.read'),
 enterprise('alerts','enterprise-alerts','告警中心',AlertView,'alert_center','organization.read'),
 enterprise('organization','enterprise-organization','组织管理',MemberView,'member_management','members.manage'),
 enterprise('settings','enterprise-settings','系统设置',FeatureSettingsView,undefined,'organization.read'),
 enterprise('onboarding','enterprise-onboarding','企业开通向导',OnboardingView),
 {path:'/access-state',name:'access-state',component:AccessStateView,meta:{title:'访问说明'}},
 {path:'/platform',redirect:'/platform/overview'},{path:'/dashboard',redirect:'/enterprise/dashboard'},{path:'/realtime-devices',redirect:'/enterprise/devices'},{path:'/devices',redirect:'/enterprise/device-list'},{path:'/accounts',redirect:'/enterprise/live'},{path:'/reports',redirect:'/enterprise/analytics'},{path:'/alerts',redirect:'/enterprise/alerts'},{path:'/members',redirect:'/enterprise/organization'},{path:'/:pathMatch(.*)*',name:'not-found',component:AccessStateView,meta:{title:'页面不存在'}}
]})

router.beforeEach(to=>{
 if(!session.loggedIn)return true
 const audience=to.meta.audience as string|undefined
 if(audience==='platform'&&session.role!=='platform_super')return{name:'access-state',query:{reason:'forbidden'}}
 if(audience==='enterprise'&&session.role==='platform_super')return{name:'access-state',query:{reason:'choose-enterprise'}}
 if(audience==='enterprise'&&session.enterpriseToken){
  const feature=to.meta.feature as string|undefined,permission=to.meta.permission as string|undefined
  if(feature&&!featureEnabled(feature))return{name:'access-state',query:{reason:'feature',feature}}
  if(permission&&!hasPermission(permission))return{name:'access-state',query:{reason:'forbidden'}}
 }
 return true
})
