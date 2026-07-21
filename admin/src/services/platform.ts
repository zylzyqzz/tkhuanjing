import { api } from '../api'

export const platformApi = {
  organizations: () => api('/tk-api/enterprise/platform/tenants'),
  definitions: () => api('/api/v2/platform/features'),
  saveDefinition: (id:number|null, value:any) => api(id ? `/api/v2/platform/features/${id}` : '/api/v2/platform/features', {method:id?'PUT':'POST', body:JSON.stringify(value)}),
  planFeatures: (plan:string) => api(`/api/v2/platform/plans/${plan}/features`),
  savePlanFeatures: (plan:string, items:any[]) => api(`/api/v2/platform/plans/${plan}/features`, {method:'PUT',body:JSON.stringify({items})}),
  clearPlanFeature: (plan:string, code:string) => api(`/api/v2/platform/plans/${plan}/features/${code}`, {method:'DELETE'}),
  organizationFeatures: (id:string|number) => api(`/api/v2/platform/organizations/${id}/features`),
  saveOrganizationFeatures: (id:string|number, items:any[]) => api(`/api/v2/platform/organizations/${id}/features`, {method:'PUT',body:JSON.stringify({items})}),
  clearOrganizationFeature: (id:string|number, code:string) => api(`/api/v2/platform/organizations/${id}/features/${code}`, {method:'DELETE'}),
  devices: (params:URLSearchParams) => api(`/api/v2/platform/devices?${params}`),
  deviceFeatures: (id:string) => api(`/api/v2/platform/devices/${encodeURIComponent(id)}/features`),
  saveDeviceFeatures: (id:string, items:any[]) => api(`/api/v2/platform/devices/${encodeURIComponent(id)}/features`, {method:'PUT',body:JSON.stringify({items})}),
  clearDeviceFeature: (id:string, code:string) => api(`/api/v2/platform/devices/${encodeURIComponent(id)}/features/${code}`, {method:'DELETE'}),
  roleFeatures: (organizationId:string|number, role:string) => api(`/api/v2/platform/organizations/${organizationId}/roles/${role}/features`),
  saveRoleFeatures: (organizationId:string|number, role:string, items:any[]) => api(`/api/v2/platform/organizations/${organizationId}/roles/${role}/features`, {method:'PUT',body:JSON.stringify({items})}),
  resetRoleFeatures: (organizationId:string|number, role:string) => api(`/api/v2/platform/organizations/${organizationId}/roles/${role}/features`, {method:'DELETE'}),
  rollouts: (featureId:number|string) => api(`/api/v2/platform/features/${featureId}/rollouts`),
  saveRollout: (featureId:number|string, rolloutId:number|null, value:any) => api(`/api/v2/platform/features/${featureId}/rollouts${rolloutId?`/${rolloutId}`:''}`, {method:rolloutId?'PUT':'POST',body:JSON.stringify(value)}),
  deleteRollout: (featureId:number|string, rolloutId:number) => api(`/api/v2/platform/features/${featureId}/rollouts/${rolloutId}`, {method:'DELETE'}),
}
