import { api } from '../api'

export const enterpriseApi = {
  bootstrap: () => api('/api/v2/organization/bootstrap'),
  usage: () => api('/api/v2/organization/usage'),
  options: () => api('/api/v2/organization/options'),
  devices: (params=new URLSearchParams()) => api(`/api/v2/organization/devices?${params}`),
  device: (id:string) => api(`/api/v2/organization/devices/${encodeURIComponent(id)}`),
  bindDevice: (id:string, value:any) => api(`/api/v2/organization/devices/${encodeURIComponent(id)}/binding`, {method:'PUT',body:JSON.stringify(value)}),
  unbindDevice: (id:string, reason:string) => api(`/api/v2/organization/devices/${encodeURIComponent(id)}/binding`, {method:'DELETE',body:JSON.stringify({reason})}),
  members: () => api('/api/v2/organization/members'),
  createMember: (value:any) => api('/api/v2/organization/members', {method:'POST',body:JSON.stringify(value)}),
  updateMember: (id:number, value:any) => api(`/api/v2/organization/members/${id}`, {method:'PUT',body:JSON.stringify(value)}),
  settings: () => api('/api/v2/organization/settings'),
  saveSettings: (value:any) => api('/api/v2/organization/settings', {method:'PUT',body:JSON.stringify(value)}),
  audit: (limit=50) => api(`/api/v2/organization/audit?limit=${limit}`),
  reports: (q='') => api(`/api/v2/organization/reports?q=${encodeURIComponent(q)}`),
  report: (id:string) => api(`/api/v2/organization/reports/${encodeURIComponent(id)}`),
  createRoom: (value:any) => api('/api/v2/organization/rooms', {method:'POST',body:JSON.stringify(value)}),
  createAccount: (value:any) => api('/api/v2/organization/accounts', {method:'POST',body:JSON.stringify(value)}),
  createAnchor: (value:any) => api('/api/v2/organization/anchors', {method:'POST',body:JSON.stringify(value)}),
}
