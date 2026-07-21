import { beforeEach, describe, expect, it } from 'vitest'
import { router } from '../router'
import { session } from '../api'

describe('route authorization', () => {
  beforeEach(async () => {
    session.loggedIn=true
    session.enterpriseToken='member-token'
    session.role='viewer'
    session.permissions=['organization.read']
    session.bootstrap={features:{device_center:{enabled:true},alert_center:{enabled:false}}}
    await router.push('/access-state')
  })

  it('rejects direct access when the base permission is missing', async () => {
    await router.push('/enterprise/devices')
    expect(router.currentRoute.value.name).toBe('access-state')
    expect(router.currentRoute.value.query.reason).toBe('forbidden')
  })

  it('rejects a feature-disabled route even when the base permission exists', async () => {
    await router.push('/enterprise/alerts')
    expect(router.currentRoute.value.name).toBe('access-state')
    expect(router.currentRoute.value.query.reason).toBe('feature')
  })

  it('prevents platform users from directly entering tenant pages', async () => {
    session.role='platform_super';session.enterpriseToken='';session.permissions=['*']
    await router.push('/enterprise/dashboard')
    expect(router.currentRoute.value.query.reason).toBe('choose-enterprise')
  })
})
