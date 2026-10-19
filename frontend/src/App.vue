<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'
import { api } from './api'
import { usePlanningStore } from './store'
import type { AccountOption } from './types'

const store = usePlanningStore()
const route = useRoute()
const fromManualTask = computed(() => route.path === '/results' && route.query.from === 'manual' && Boolean(route.query.batch))
const activeNav = computed(() => fromManualTask.value ? '/manual' : route.path)
const breadcrumbs = computed<{ label: string; to?: RouteLocationRaw }[]>(() => {
  if (fromManualTask.value) return [
    { label: '人工策划', to: '/manual' },
    { label: '策划任务列表', to: '/manual' },
    { label: '查看策划' },
  ]
  if (route.path === '/results') {
    const account = Boolean(route.query.account) && !route.query.batch
    const period = !account && (route.query.dimension === 'period' || Boolean(route.query.batch || route.query.cycle))
    const detail = Boolean(route.query.account || route.query.batch || route.query.cycle)
    const detailTitle = account ? '账号策划详情' : route.query.batch ? '批次策划详情' : '周期策划详情'
    const view = { label: period ? '周期视图' : '账号视图', to: { path: '/results', query: period ? { dimension: 'period' } : {} } }
    return detail
      ? [{ label: '策划结果', to: '/results' }, view, { label: detailTitle }]
      : [{ label: '策划结果', to: '/results' }, { label: view.label }]
  }
  if (route.path === '/manual') return [{ label: '人工策划', to: '/manual' }, { label: '策划任务列表' }]
  return [{ label: '运营工作台' }, { label: String(route.meta.title || '') }]
})
let resultsUiObserver: MutationObserver | undefined
let profileRequest: Promise<void> | undefined
const accountProfiles = new Map<string, AccountOption>()

function compactPlanningSourceBadges() {
  document.querySelectorAll<HTMLElement>('.account-week-plan-tags .tag.gray').forEach(badge => {
    const label = badge.textContent?.trim()
    let compactLabel = ''
    let hint = ''
    if (label === '手动策划' || label === '人工策划') {
      compactLabel = '人'
      hint = '人：手动策划'
    } else if (label === '自动策划' || label === 'AI 自动策划') {
      compactLabel = 'AI'
      hint = 'AI：自动策划'
    } else return

    badge.textContent = compactLabel
    badge.dataset.sourceHint = hint
    badge.tabIndex = 0
    badge.setAttribute('aria-label', hint)
  })
}

function compactAccountHistoryPeriodLabels() {
  document.querySelectorAll<HTMLElement>('.account-history-batch-head b').forEach(label => {
    if (label.dataset.periodRange) return
    const value = label.textContent?.trim() || ''
    const match = value.match(/^(.*?周)\s*·\s*(\d{4}-\d{2}-\d{2})\s*至\s*(\d{4}-\d{2}-\d{2})$/)
    if (!match) return
    const [, periodLabel, start, end] = match
    const range = `${start} 至 ${end}`
    label.textContent = periodLabel
    label.dataset.periodRange = range
    label.classList.add('ux-account-period-label')
    label.tabIndex = 0
    label.setAttribute('aria-label', `${periodLabel}，${range}`)
  })
}

function enhancePlanTopicDetailTriggers() {
  document.querySelectorAll<HTMLElement>('.account-week-plan-card').forEach(card => {
    const title = card.querySelector<HTMLElement>('h3')
    if (!title) return
    const topicTitle = title.textContent?.trim() || '未命名选题'
    card.setAttribute('aria-label', `查看单条策划：${topicTitle}`)
    title.classList.add('ux-topic-detail-trigger')
    if (title.dataset.planDetailTrigger === 'true') return

    title.dataset.planDetailTrigger = 'true'
    title.addEventListener('click', event => {
      event.stopPropagation()
      card.click()
    })
  })
}

function accountTypeLabel(profile?: AccountOption) {
  return profile?.account_type || (profile?.certified === true ? '认证' : profile?.certified === false ? '非认证' : '—')
}

function ensureAccountProfiles() {
  if (profileRequest) return profileRequest
  profileRequest = api.accounts(1000, true)
    .then(accounts => {
      accountProfiles.clear()
      accounts.forEach(account => accountProfiles.set(account.account_id, account))
    })
    .catch(() => { profileRequest = undefined })
  return profileRequest
}

function createMetaSpan(text: string, className?: string) {
  const span = document.createElement('span')
  if (className) span.className = className
  span.textContent = text
  return span
}

function enhanceBatchAccountCards() {
  const cards = document.querySelectorAll<HTMLElement>('.planning-account-groups .planning-account-group')
  if (!cards.length) return

  cards.forEach(card => {
    card.classList.add('ux-account-card')
    const head = card.querySelector<HTMLElement>('.planning-account-group-head')
    const nameRow = head?.querySelector<HTMLElement>('.batch-account-name')
    const titleButton = nameRow?.querySelector<HTMLButtonElement>('.account-detail-link')
    const idTag = nameRow?.querySelector<HTMLElement>('.tag.gray')
    const actions = head?.querySelector<HTMLElement>('.batch-account-head-actions')
    const expandButton = actions?.querySelector<HTMLButtonElement>('.batch-account-expand')
    if (!head || !nameRow || !titleButton || !idTag || !actions || !expandButton) return

    const accountId = idTag.textContent?.trim() || ''
    const accountName = titleButton.textContent?.trim() || accountId
    const profile = accountProfiles.get(accountId)
    const identityWrap = nameRow.parentElement as HTMLElement
    const profileSignature = [
      accountId,
      accountName,
      accountTypeLabel(profile),
      profile?.organization || '',
      profile?.um_no || '',
      profile?.platform || '',
      profile?.persona || '',
    ].join('|')

    identityWrap.classList.add('ux-account-identity')
    nameRow.classList.add('ux-account-title-row')
    idTag.classList.add('ux-original-account-id')
    identityWrap.parentElement?.classList.add('ux-account-main')

    if (card.dataset.profileSignature !== profileSignature) {
      let avatar = head.querySelector<HTMLElement>('.ux-account-avatar')
      if (!avatar) {
        avatar = document.createElement('div')
        avatar.className = 'ux-account-avatar'
        avatar.setAttribute('aria-hidden', 'true')
        identityWrap.parentElement?.insertBefore(avatar, identityWrap)
      }
      avatar.textContent = (accountName || '账').slice(0, 1).toLocaleUpperCase()

      let typeTag = nameRow.querySelector<HTMLElement>('.ux-account-type')
      if (!typeTag) {
        typeTag = document.createElement('span')
        typeTag.className = 'ux-account-type'
        titleButton.insertAdjacentElement('afterend', typeTag)
      }
      typeTag.textContent = accountTypeLabel(profile)

      let meta = identityWrap.querySelector<HTMLElement>('.ux-account-meta')
      if (!meta) {
        meta = document.createElement('div')
        meta.className = 'ux-account-meta'
        nameRow.insertAdjacentElement('afterend', meta)
      }
      meta.replaceChildren(createMetaSpan(accountId, 'ux-account-id'))
      if (profile?.organization) meta.append(createMetaSpan(profile.organization))
      if (profile?.um_no) meta.append(createMetaSpan(`UM ${profile.um_no}`))
      if (profile?.platform) meta.append(createMetaSpan(profile.platform))

      let persona = identityWrap.querySelector<HTMLElement>('.ux-account-persona')
      if (!persona) {
        persona = document.createElement('div')
        persona.className = 'ux-account-persona'
        persona.innerHTML = '<small>人设</small><span></span>'
        meta.insertAdjacentElement('afterend', persona)
      }
      const personaValue = persona.querySelector<HTMLElement>('span')
      if (personaValue) personaValue.textContent = profile?.persona || '未配置'
      card.dataset.profileSignature = profileSignature
    }

    const countTag = actions.querySelector<HTMLElement>('.tag.blue')
    if (countTag) {
      countTag.classList.add('ux-plan-count')
      const count = countTag.textContent?.match(/\d+/)?.[0]
      const nextCountLabel = count ? `${count} 条策划` : countTag.textContent?.trim() || ''
      if (countTag.textContent?.trim() !== nextCountLabel) countTag.textContent = nextCountLabel
    }

    let buttonLabel = expandButton.querySelector<HTMLElement>('.ux-expand-label')
    if (!buttonLabel) {
      buttonLabel = document.createElement('span')
      buttonLabel.className = 'ux-expand-label'
      expandButton.insertBefore(buttonLabel, expandButton.firstChild)
    }
    const nextButtonLabel = expandButton.getAttribute('aria-expanded') === 'true' ? '收起计划' : '查看计划'
    if (buttonLabel.textContent !== nextButtonLabel) buttonLabel.textContent = nextButtonLabel
  })

  if (accountProfiles.size === 0) void ensureAccountProfiles().then(() => enhanceBatchAccountCards())
}

function enhanceResultsUi() {
  compactPlanningSourceBadges()
  compactAccountHistoryPeriodLabels()
  enhancePlanTopicDetailTriggers()
  enhanceBatchAccountCards()
}

onMounted(() => {
  void store.initialize()
  enhanceResultsUi()
  resultsUiObserver = new MutationObserver(() => enhanceResultsUi())
  resultsUiObserver.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['aria-expanded'] })
})
onBeforeUnmount(() => resultsUiObserver?.disconnect())

const nav = [
  { to: '/config', icon: 'M4 6h16M4 12h16M4 18h16M9 3v6m6 0v6m-7 0v6', label: 'AI策划配置' },
  { to: '/manual', icon: 'm15 5 4 4M4 20l4-1L20 7a2.8 2.8 0 0 0-4-4L4 15z', label: '人工策划' },
  { to: '/results', icon: 'M4 4h16v16H4zM9 4v16M4 10h16M13 14h3m-3 3h3', label: '策划结果' },
]
</script>

<template>
  <div class="app-shell">
      <aside class="sidebar">
        <div class="sidebar-brand"><span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="m6 18 9-9m-5-4 1-3 1 3 3 1-3 1-1 3-1-3-3-1zM17 14l1-2 1 2 2 1-2 1-1 2-1-2-2-1z" /></svg></span><strong>多账号智能策划</strong></div>
        <div class="sidebar-title">运营工作台</div>
        <nav aria-label="一级功能导航">
          <RouterLink v-for="item in nav" :key="item.to" :to="item.to" active-class="" exact-active-class="" :class="['nav-item', { 'router-link-active': item.to === activeNav }]" :aria-current="item.to === activeNav ? 'page' : undefined">
            <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="item.icon" /></svg><span>{{ item.label }}</span>
          </RouterLink>
        </nav>
        <div class="sidebar-foot"><span :class="['status-dot', { online: store.databaseReady }]" />{{ store.connectionMessage }}</div>
      </aside>
    <div class="app-main-shell">
      <header class="topbar"><nav class="breadcrumb" aria-label="当前位置"><template v-for="(item, index) in breadcrumbs" :key="`${index}-${item.label}`"><svg v-if="index" width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m6 4 4 4-4 4" /></svg><RouterLink v-if="item.to" :to="item.to">{{ item.label }}</RouterLink><span v-else :aria-current="index === breadcrumbs.length - 1 ? 'page' : undefined">{{ item.label }}</span></template></nav></header>
      <main class="main">
        <div v-if="store.initialized && !store.databaseReady" class="banner warning-banner" role="status">
          {{ store.connectionMessage }}
        </div>
        <RouterView />
      </main>
    </div>
  </div>
</template>

<style>
.breadcrumb a{color:inherit;text-decoration:none}.breadcrumb a:hover{color:var(--primary-600)}
.account-week-plan-tags .tag.gray[data-source-hint],.ux-account-period-label[data-period-range]{position:relative;cursor:help}
.account-week-plan-tags .tag.gray[data-source-hint]::after,.ux-account-period-label[data-period-range]::after{position:absolute;z-index:1300;bottom:calc(100% + 8px);left:50%;width:max-content;max-width:240px;padding:7px 9px;border:1px solid var(--neutral-200);border-radius:7px;background:var(--surface);box-shadow:var(--shadow-3);color:var(--neutral-700);font-size:12px;font-weight:400;line-height:18px;opacity:0;pointer-events:none;transform:translate(-50%,4px);transition:opacity .12s ease,transform .12s ease;white-space:nowrap}
.account-week-plan-tags .tag.gray[data-source-hint]::after{content:attr(data-source-hint)}
.ux-account-period-label[data-period-range]::after{content:attr(data-period-range)}
.account-week-plan-tags .tag.gray[data-source-hint]:hover::after,.account-week-plan-tags .tag.gray[data-source-hint]:focus-visible::after,.ux-account-period-label[data-period-range]:hover::after,.ux-account-period-label[data-period-range]:focus-visible::after{opacity:1;transform:translate(-50%,0)}
.account-week-plan-tags .tag.gray[data-source-hint]:focus-visible,.ux-account-period-label[data-period-range]:focus-visible{outline:2px solid var(--primary-300);outline-offset:2px;border-radius:4px}

.account-week-plan-card .ux-topic-detail-trigger{position:relative;cursor:pointer;transition:color .14s ease}
.account-week-plan-card .ux-topic-detail-trigger::after{margin-left:6px;color:var(--primary-600);content:'查看详情';font-size:10px;font-weight:500;opacity:.62;white-space:nowrap}
.account-week-plan-card .ux-topic-detail-trigger:hover{color:var(--primary-600)}

.planning-account-groups{display:grid!important;gap:14px!important;padding:0 20px 20px!important}
.planning-account-groups .planning-account-group.ux-account-card{overflow:hidden;margin:0!important;border:1px solid var(--neutral-200)!important;border-radius:14px!important;background:var(--surface)!important;box-shadow:0 1px 2px rgba(15,23,42,.03);transition:border-color .16s ease,box-shadow .16s ease}
.planning-account-groups .planning-account-group.ux-account-card:hover{border-color:var(--neutral-300)!important;box-shadow:0 7px 24px rgba(15,23,42,.055)}
.planning-account-groups .ux-account-card .planning-account-group-head{display:flex!important;align-items:center!important;justify-content:space-between!important;gap:22px!important;min-height:0!important;padding:18px 20px!important;background:var(--surface)!important}
.planning-account-groups .ux-account-main{display:flex!important;align-items:flex-start!important;gap:14px!important;min-width:0!important;flex:1 1 auto}
.planning-account-groups .ux-account-avatar{display:grid;place-items:center;flex:0 0 42px;width:42px;height:42px;border-radius:12px;background:var(--primary-50);color:var(--primary-600);font-size:16px;font-weight:700}
.planning-account-groups .ux-account-identity{display:flex!important;flex-direction:column;gap:7px!important;min-width:0}
.planning-account-groups .ux-account-title-row{display:flex!important;align-items:center!important;flex-wrap:wrap!important;gap:8px!important}
.planning-account-groups .ux-account-title-row .account-detail-link{color:var(--neutral-900)!important;font-size:15px!important;font-weight:650!important;line-height:22px!important}
.planning-account-groups .ux-account-title-row .account-detail-link:hover{color:var(--primary-600)!important}
.planning-account-groups .ux-original-account-id{display:none!important}
.planning-account-groups .ux-account-type{display:inline-flex;align-items:center;height:22px;padding:0 8px;border:1px solid var(--primary-100);border-radius:6px;background:var(--primary-50);color:var(--primary-600);font-size:11px;font-weight:500;line-height:20px;white-space:nowrap}
.planning-account-groups .ux-account-meta{display:flex;align-items:center;flex-wrap:wrap;color:var(--neutral-400);font-size:11px;line-height:18px}
.planning-account-groups .ux-account-meta span{display:inline-flex;align-items:center}
.planning-account-groups .ux-account-meta span+span::before{width:1px;height:11px;margin:0 9px;background:var(--neutral-200);content:''}
.planning-account-groups .ux-account-id{font-variant-numeric:tabular-nums}
.planning-account-groups .ux-account-persona{display:flex;align-items:center;gap:7px;min-width:0}
.planning-account-groups .ux-account-persona small{flex:none;padding:2px 6px;border-radius:5px;background:var(--neutral-100);color:var(--neutral-500);font-size:10px;line-height:16px}
.planning-account-groups .ux-account-persona span{max-width:520px;overflow:hidden;color:var(--neutral-600);font-size:12px;line-height:18px;text-overflow:ellipsis;white-space:nowrap}
.planning-account-groups .ux-account-card .batch-account-head-actions{display:flex!important;align-items:center!important;gap:10px!important;flex:none}
.planning-account-groups .ux-plan-count{height:24px;padding:0 9px!important;border-radius:6px!important;font-size:11px!important;line-height:24px!important}
.planning-account-groups .ux-account-card .batch-account-expand{display:inline-flex!important;align-items:center!important;gap:6px!important;width:auto!important;height:34px!important;padding:0 10px!important;border-color:var(--neutral-200)!important;border-radius:8px!important;color:var(--neutral-600)!important}
.planning-account-groups .ux-account-card .batch-account-expand:hover{border-color:var(--primary-200)!important;background:var(--primary-50)!important;color:var(--primary-600)!important}
.planning-account-groups .ux-expand-label{font-size:12px;line-height:18px;white-space:nowrap}
.planning-account-groups .ux-account-card>.account-week-carousel{margin:0!important;padding:16px 18px 18px!important;border-top:1px solid var(--neutral-100);background:linear-gradient(180deg,var(--neutral-50),var(--surface) 76px)}
.planning-account-groups .ux-account-card .account-week-calendar{padding:0!important}
.planning-account-groups .ux-account-card .account-week-day{border-radius:10px!important;background:var(--surface)!important;box-shadow:0 1px 2px rgba(15,23,42,.025)}
.planning-account-groups .ux-account-card .account-week-plan-card{border-radius:8px!important;transition:border-color .14s ease,box-shadow .14s ease,transform .14s ease}
.planning-account-groups .ux-account-card .account-week-plan-card:hover{border-color:var(--primary-200)!important;box-shadow:0 5px 16px rgba(15,23,42,.06);transform:translateY(-1px)}

@media(max-width:900px){
  .planning-account-groups{padding:0 12px 16px!important}
  .planning-account-groups .ux-account-card .planning-account-group-head{align-items:flex-start!important;flex-direction:column!important;padding:16px!important}
  .planning-account-groups .ux-account-card .batch-account-head-actions{width:100%;justify-content:space-between!important}
  .planning-account-groups .ux-account-persona span{max-width:420px}
}
@media(max-width:580px){
  .planning-account-groups .ux-account-main{gap:10px!important}
  .planning-account-groups .ux-account-avatar{width:36px;height:36px;flex-basis:36px;border-radius:10px}
  .planning-account-groups .ux-account-persona span{max-width:230px}
  .planning-account-groups .ux-account-card>.account-week-carousel{padding:12px 8px 14px!important}
}
</style>
