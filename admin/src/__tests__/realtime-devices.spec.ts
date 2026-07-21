import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const service = vi.hoisted(() => ({ options:vi.fn(), devices:vi.fn() }))
const push = vi.hoisted(() => vi.fn())
vi.mock('../services/enterprise', () => ({enterpriseApi:service}))
vi.mock('vue-router', () => ({useRouter:() => ({push})}))

import RealtimeDevicesView from '../views/RealtimeDevicesView.vue'

describe('RealtimeDevicesView', () => {
  beforeEach(() => {
    vi.useFakeTimers({shouldAdvanceTime:true})
    service.options.mockResolvedValue({rooms:[],accounts:[],anchors:[]})
    service.devices.mockResolvedValue({items:[{device_id:'DEVICE-001',display_name:'一号电脑',online_state:'online',agent_version:'2.1.0',studio_state:'running',collector_state:'healthy',cpu_percent:20,memory_percent:40,network_latency_ms:30,upload_mbps:25,abnormal_reasons:[],room:null,account:null}],pagination:{total:1}})
  })

  it('loads devices, sends advanced filters and opens detail', async () => {
    const wrapper = mount(RealtimeDevicesView)
    await flushPromises()
    expect(wrapper.text()).toContain('一号电脑')
    await wrapper.get('input[placeholder="输入名称、编号、门店或负责人"]').setValue('一号')
    await wrapper.get('.device-filter-panel button.primary').trigger('click')
    await flushPromises()
    const params = service.devices.mock.calls.at(-1)?.[0] as URLSearchParams
    expect(params.get('keyword')).toBe('一号')
    await wrapper.get('article[role="button"]').trigger('click')
    expect(push).toHaveBeenCalledWith({name:'enterprise-device-detail',params:{deviceId:'DEVICE-001'}})
    wrapper.unmount()
  })

  it('renders empty and error states without fake data', async () => {
    service.devices.mockResolvedValueOnce({items:[],pagination:{total:0}})
    const empty = mount(RealtimeDevicesView)
    await flushPromises()
    expect(empty.find('.empty-state').exists()).toBe(true)
    empty.unmount()
    service.devices.mockRejectedValueOnce(new Error('连接失败'))
    const failed = mount(RealtimeDevicesView)
    await flushPromises()
    expect(failed.find('.state-panel.error').exists()).toBe(true)
    failed.unmount()
  })
})
