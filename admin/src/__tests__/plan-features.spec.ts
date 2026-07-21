import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const service = vi.hoisted(() => ({
  definitions: vi.fn(),
  planFeatures: vi.fn(),
  organizations: vi.fn(),
  savePlanFeatures: vi.fn(),
  clearPlanFeature: vi.fn(),
}))

vi.mock('../services/platform', () => ({ platformApi: service }))

import PlanFeaturesView from '../views/PlanFeaturesView.vue'

describe('PlanFeaturesView', () => {
  beforeEach(() => {
    service.definitions.mockResolvedValue({items:[{feature_code:'device_center',feature_name:'设备中心',category:'enterprise',default_enabled:false}]})
    service.planFeatures.mockResolvedValue({items:[]})
    service.organizations.mockResolvedValue({tenants:[{id:1,name:'示例企业',plan_code:'trial'}]})
    service.savePlanFeatures.mockResolvedValue({ok:true})
    service.clearPlanFeature.mockResolvedValue({ok:true})
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  it('loads real data, tracks dirty state and saves a full assignment', async () => {
    const wrapper = mount(PlanFeaturesView)
    await flushPromises()
    expect(wrapper.text()).toContain('设备中心')
    expect(wrapper.text()).toContain('影响企业 1 家')
    const toggle = wrapper.get('input[type="checkbox"]')
    await toggle.setValue(true)
    expect(wrapper.text()).toContain('有未保存变化')
    await wrapper.get('button.primary').trigger('click')
    await flushPromises()
    expect(service.savePlanFeatures).toHaveBeenCalledWith('trial', [expect.objectContaining({feature_code:'device_center',enabled:true})])
  })

  it('renders a recoverable error state', async () => {
    service.definitions.mockRejectedValueOnce(new Error('服务暂不可用'))
    const wrapper = mount(PlanFeaturesView)
    await flushPromises()
    expect(wrapper.find('.state-inline.error').exists()).toBe(true)
    expect(wrapper.text()).toContain('重新加载')
  })
})
