<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AccountTypeBadge from '../components/AccountTypeBadge.vue'
import LoadingSkeleton from '../components/LoadingSkeleton.vue'
import { api } from '../api'
import type { AccountOption, AccountPlanRecord, BatchDetail, BatchSummary } from '../types'
import { statusTone } from '../ui/status'

type CycleAccountGroup = {
  account_id: string
  account_name: string
  lifecycle_stage: string
  profile?: AccountOption
  items: AccountPlanRecord[]
}

const props = defineProps<{
  cycleStart: string
  cycleEnd: string
  batches: BatchSummary[]
}>()

const emit = defineEmits<{
  back: []
  openBatch: [batch: BatchSummary]
}>()

const loading = ref(false)
const error = ref('')
const details = ref<BatchDetail[]>([])
const accountCatalog = ref<AccountOption[]>([])
const expandedAccounts = ref(new Set<string>())

function accountProfile(accountId: string) {
  return accountCatalog.value.find(account => account.account_id === accountId)
}

function accountTypeLabel(profile?: AccountOption) {
  return profile?.account_type || (profile?.certified === true ? '认证' : profile?.certified === false ? '非认证' : '—')
}

function productionStatusLabel(item: AccountPlanRecord) {
  if (!item.topic_id) return '待生产'
  const states: Record<string, string> = { planned: '待生产', ready: '生成中', generated: '已完成', published: '已完成', failed: '生成失败' }
  return states[item.production_status ?? ''] ?? ({
    '已生成': '已完成', '已发布': '已完成', '生成中': '生成中', '生产中': '生成中',
    '生成失败': '生成失败', '生产失败': '生成失败', '生产异常': '生成失败',
  } as Record<string, string>)[item.status] ?? '待生产'
}

function topicTypeLabel(item: AccountPlanRecord) {
  if (!item.topic_id) return '待确定'
  const type = String(item.topic_type ?? '')
  if (type === '营销' || type === 'marketing' || type === 'marketing_priority') return '营销'
  if (type === '热点' || type === 'hotspot') return '热点'
  return '普通'
}

function weekdayLabel(date: string) {
  return new Intl.DateTimeFormat('zh-CN', { weekday: 'short', timeZone: 'UTC' }).format(new Date(`${date}T00:00:00Z`))
}

function sourceLabel(item: AccountPlanRecord) {
  return item.plan_type === 'manual' ? '人' : 'AI'
}

function sourceHint(item: AccountPlanRecord) {
  return item.plan_type === 'manual' ? '人：手动策划' : 'AI：自动策划'
}

function daysFor(group: CycleAccountGroup) {
  const start = new Date(`${props.cycleStart}T00:00:00Z`)
  return Array.from({ length: 7 }, (_, offset) => {
    const date = new Date(start)
    date.setUTCDate(start.getUTCDate() + offset)
    const value = date.toISOString().slice(0, 10)
    return {
      date: value,
      label: value.slice(5),
      weekday: weekdayLabel(value),
      items: group.items
        .filter(item => item.publish_date === value)
        .sort((a, b) => a.plan_type.localeCompare(b.plan_type) || a.id - b.id),
    }
  })
}

const cycleItems = computed<AccountPlanRecord[]>(() => details.value.flatMap(batch => batch.items.map(item => ({
  ...item,
  batch_id: batch.id,
  batch_code: batch.batch_code,
  batch_created_at: batch.created_at,
  plan_type: batch.plan_type,
  cycle_start: batch.cycle_start,
  cycle_end: batch.cycle_end,
}))))

const accountGroups = computed<CycleAccountGroup[]>(() => {
  const groups = new Map<string, CycleAccountGroup>()
  for (const item of cycleItems.value) {
    const existing = groups.get(item.account_id)
    if (existing) existing.items.push(item)
    else groups.set(item.account_id, {
      account_id: item.account_id,
      account_name: item.account_name,
      lifecycle_stage: item.lifecycle_stage || '—',
      profile: accountProfile(item.account_id),
      items: [item],
    })
  }
  return [...groups.values()]
    .map(group => ({ ...group, items: group.items.sort((a, b) => a.publish_date.localeCompare(b.publish_date) || a.id - b.id) }))
    .sort((a, b) => a.account_name.localeCompare(b.account_name, 'zh-CN'))
})

const dashboard = computed(() => ({
  accounts: accountGroups.value.length,
  batches: props.batches.length,
  plans: cycleItems.value.length,
  autoPlans: cycleItems.value.filter(item => item.plan_type === 'auto').length,
  manualPlans: cycleItems.value.filter(item => item.plan_type === 'manual').length,
}))

function toggleAccount(accountId: string) {
  const next = new Set(expandedAccounts.value)
  if (next.has(accountId)) next.delete(accountId)
  else next.add(accountId)
  expandedAccounts.value = next
}

function openItemBatch(item: AccountPlanRecord) {
  const batch = props.batches.find(candidate => candidate.id === item.batch_id)
  if (batch) emit('openBatch', batch)
}

async function load() {
  if (!props.batches.length) {
    details.value = []
    return
  }
  loading.value = true
  error.value = ''
  try {
    const [batchDetails, accounts] = await Promise.all([
      Promise.all(props.batches.map(batch => api.batch(batch.id))),
      api.accounts(1000, true),
    ])
    details.value = batchDetails
    accountCatalog.value = accounts
    if (!expandedAccounts.value.size && accountGroups.value[0]) {
      expandedAccounts.value = new Set([accountGroups.value[0].account_id])
    }
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '读取周期详情失败'
  } finally {
    loading.value = false
  }
}

watch(() => props.batches.map(batch => batch.id).join(','), () => { void load() }, { immediate: true })
</script>

<template>
  <section class="card cycle-detail-card">
    <div class="card-head">
      <div>
        <h2>周期详情</h2>
        <small>{{ cycleStart }} 至 {{ cycleEnd }}</small>
      </div>
      <button class="btn" type="button" @click="emit('back')">返回周期列表</button>
    </div>

    <LoadingSkeleton v-if="loading" :rows="8" />
    <div v-else-if="error" class="banner error-banner" role="alert">{{ error }}</div>
    <template v-else>
      <section class="cycle-dashboard" aria-label="周期概览">
        <div><small>账号数</small><strong>{{ dashboard.accounts }}</strong></div>
        <div><small>批次数</small><strong>{{ dashboard.batches }}</strong></div>
        <div><small>策划总数</small><strong>{{ dashboard.plans }}</strong></div>
        <div><small>AI 策划</small><strong>{{ dashboard.autoPlans }}</strong></div>
        <div><small>人工策划</small><strong>{{ dashboard.manualPlans }}</strong></div>
      </section>

      <div v-if="accountGroups.length" class="cycle-account-list">
        <article v-for="group in accountGroups" :key="group.account_id" class="cycle-account-card">
          <header class="cycle-account-head">
            <div class="cycle-account-main">
              <div class="cycle-account-avatar" aria-hidden="true">{{ (group.account_name || '账').slice(0, 1) }}</div>
              <div class="cycle-account-identity">
                <div class="cycle-account-title">
                  <strong>{{ group.account_name }}</strong>
                  <AccountTypeBadge :type="accountTypeLabel(group.profile)" />
                  <span v-if="group.lifecycle_stage && group.lifecycle_stage !== '—'" class="tag purple">{{ group.lifecycle_stage }}</span>
                </div>
                <div class="cycle-account-meta">
                  <span>{{ group.account_id }}</span>
                  <span v-if="group.profile?.organization">{{ group.profile.organization }}</span>
                  <span v-if="group.profile?.um_no">UM {{ group.profile.um_no }}</span>
                  <span v-if="group.profile?.platform">{{ group.profile.platform }}</span>
                </div>
                <div class="cycle-account-persona"><small>人设</small><span>{{ group.profile?.persona || '未配置' }}</span></div>
              </div>
            </div>
            <div class="cycle-account-actions">
              <span class="tag blue">{{ group.items.length }} 条策划</span>
              <button class="btn cycle-expand-btn" type="button" :aria-expanded="expandedAccounts.has(group.account_id)" @click="toggleAccount(group.account_id)">
                {{ expandedAccounts.has(group.account_id) ? '收起计划' : '查看计划' }}
              </button>
            </div>
          </header>

          <div v-if="expandedAccounts.has(group.account_id)" class="cycle-week-wrap">
            <div class="cycle-week-grid">
              <section v-for="day in daysFor(group)" :key="day.date" class="cycle-day">
                <header><div><b>{{ day.label }}</b><small>{{ day.weekday }}</small></div><span>{{ day.items.length }} 条</span></header>
                <div v-if="day.items.length" class="cycle-day-items">
                  <button v-for="item in day.items" :key="item.id" type="button" class="cycle-plan-card" @click="openItemBatch(item)">
                    <div class="account-week-plan-tags">
                      <span class="tag gray" :data-source-hint="sourceHint(item)" :aria-label="sourceHint(item)" tabindex="0">{{ sourceLabel(item) }}</span>
                      <span :class="['tag', statusTone(productionStatusLabel(item))]">{{ productionStatusLabel(item) }}</span>
                    </div>
                    <b>{{ item.topic_title || '待确定选题' }}</b>
                    <small>{{ item.content_type || '—' }} · {{ topicTypeLabel(item) }}</small>
                    <span class="cycle-plan-batch">{{ item.batch_code }}</span>
                  </button>
                </div>
                <div v-else class="cycle-day-empty">暂无计划</div>
              </section>
            </div>
          </div>
        </article>
      </div>
      <div v-else class="empty-state"><b>该周期暂无策划结果</b></div>
    </template>
  </section>
</template>

<style scoped>
.cycle-dashboard{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:1px;margin:16px 20px 20px;border:1px solid var(--neutral-200);border-radius:12px;overflow:hidden;background:var(--neutral-200)}
.cycle-dashboard>div{display:flex;flex-direction:column;gap:8px;min-height:74px;padding:14px 16px;background:var(--surface)}
.cycle-dashboard small{color:var(--neutral-500);font-size:12px}.cycle-dashboard strong{color:var(--neutral-800);font-size:22px;line-height:1;font-variant-numeric:tabular-nums}
.cycle-account-list{display:grid;gap:14px;padding:0 20px 20px}.cycle-account-card{overflow:hidden;border:1px solid var(--neutral-200);border-radius:14px;background:var(--surface);box-shadow:0 1px 2px rgba(15,23,42,.03)}
.cycle-account-head{display:flex;align-items:center;justify-content:space-between;gap:22px;padding:18px 20px}.cycle-account-main{display:flex;align-items:flex-start;gap:14px;min-width:0;flex:1}.cycle-account-avatar{display:grid;place-items:center;flex:0 0 42px;width:42px;height:42px;border-radius:12px;background:var(--primary-50);color:var(--primary-600);font-size:16px;font-weight:700}.cycle-account-identity{display:flex;flex-direction:column;gap:7px;min-width:0}.cycle-account-title{display:flex;align-items:center;flex-wrap:wrap;gap:8px}.cycle-account-title>strong{color:var(--neutral-900);font-size:15px;line-height:22px}.cycle-account-meta{display:flex;align-items:center;flex-wrap:wrap;color:var(--neutral-400);font-size:11px;line-height:18px}.cycle-account-meta span+span::before{display:inline-block;width:1px;height:11px;margin:0 9px;background:var(--neutral-200);content:'';vertical-align:-1px}.cycle-account-persona{display:flex;align-items:center;gap:7px;min-width:0}.cycle-account-persona small{flex:none;padding:2px 6px;border-radius:5px;background:var(--neutral-100);color:var(--neutral-500);font-size:10px;line-height:16px}.cycle-account-persona span{max-width:560px;overflow:hidden;color:var(--neutral-600);font-size:12px;line-height:18px;text-overflow:ellipsis;white-space:nowrap}.cycle-account-actions{display:flex;align-items:center;gap:10px;flex:none}.cycle-expand-btn{height:34px;padding:0 10px;font-size:12px}
.cycle-week-wrap{padding:16px 18px 18px;border-top:1px solid var(--neutral-100);background:linear-gradient(180deg,var(--neutral-50),var(--surface) 76px);overflow-x:auto}.cycle-week-grid{display:grid;grid-template-columns:repeat(7,minmax(150px,1fr));gap:10px;min-width:1120px}.cycle-day{overflow:hidden;min-height:170px;border:1px solid var(--neutral-200);border-radius:10px;background:var(--surface)}.cycle-day>header{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 11px;border-bottom:1px solid var(--neutral-100);background:var(--neutral-50)}.cycle-day>header>div{display:flex;align-items:baseline;gap:6px}.cycle-day>header b{color:var(--neutral-700);font-size:13px}.cycle-day>header small,.cycle-day>header span{color:var(--neutral-400);font-size:10px}.cycle-day-items{display:grid;gap:8px;padding:9px}.cycle-plan-card{position:relative;display:flex;flex-direction:column;align-items:flex-start;gap:6px;width:100%;padding:10px;border:1px solid var(--neutral-200);border-radius:8px;background:var(--surface);color:inherit;text-align:left;cursor:pointer;transition:border-color .14s ease,box-shadow .14s ease,transform .14s ease}.cycle-plan-card:hover{border-color:var(--primary-200);box-shadow:0 5px 16px rgba(15,23,42,.06);transform:translateY(-1px)}.cycle-plan-card>b{display:-webkit-box;overflow:hidden;color:var(--neutral-700);font-size:12px;line-height:18px;-webkit-line-clamp:2;-webkit-box-orient:vertical}.cycle-plan-card>small{color:var(--neutral-400);font-size:10px}.cycle-plan-batch{color:var(--neutral-400);font-size:9px}.cycle-day-empty{display:grid;place-items:center;min-height:110px;color:var(--neutral-300);font-size:11px}
@media(max-width:980px){.cycle-dashboard{grid-template-columns:repeat(3,minmax(0,1fr));margin:12px}.cycle-account-list{padding:0 12px 16px}.cycle-account-head{align-items:flex-start;flex-direction:column;padding:16px}.cycle-account-actions{width:100%;justify-content:space-between}.cycle-account-persona span{max-width:420px}}
@media(max-width:580px){.cycle-dashboard{grid-template-columns:repeat(2,minmax(0,1fr))}.cycle-account-main{gap:10px}.cycle-account-avatar{width:36px;height:36px;flex-basis:36px;border-radius:10px}.cycle-account-persona span{max-width:230px}.cycle-week-wrap{padding:12px 8px 14px}}
</style>
