import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import * as apiModule from '../api'

const replace = vi.hoisted(() => vi.fn())
vi.mock('vue-router', () => ({useRouter:() => ({replace})}))

import OnboardingView from '../views/OnboardingView.vue'

describe('OnboardingView', () => {
  it('restores the server step and persists progress without blocking the page', async () => {
    apiModule.session.bootstrap={organization:{name:'示例企业',code:'DEMO',onboarding:{step:2,completed:false}}}
    const request=vi.spyOn(apiModule,'api').mockResolvedValue({ok:true})
    const wrapper=mount(OnboardingView)
    await flushPromises()
    expect(wrapper.text()).toContain('创建第一个直播间')
    await wrapper.get('input[placeholder="例如：洛杉矶 1 号直播间"]').setValue('洛杉矶直播间')
    const buttons=wrapper.findAll('button')
    const next=buttons.find(x=>x.text()==='继续')
    expect(next).toBeTruthy()
    await next!.trigger('click')
    await flushPromises()
    expect(request).toHaveBeenCalledWith('/api/v2/organization/rooms',expect.objectContaining({method:'POST'}))
    expect(request).toHaveBeenCalledWith('/api/v2/organization/onboarding',expect.objectContaining({method:'PUT'}))
  })
})
