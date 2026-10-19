<script setup lang="ts">
import { computed } from 'vue'
import AccountTypeBadge from './AccountTypeBadge.vue'
import type { AccountOption, AccountPlanRecord } from '../types'

const props = defineProps<{
  accountId: string
  accountName: string
  lifecycleStage: string
  items: AccountPlanRecord[]
  profile?: AccountOption
  expanded: boolean
}>()

const emit = defineEmits<{
  toggle: []
  openAccount: []
}>()

const plannedDays = computed(() => new Set(props.items.map(item => item.publish_date)).size)
const completedCount = computed(() => props.items.filter(item => ['generated', 'published'].includes(item.production_status ?? '') || ['已生成', '已发布'].includes(item.status)).length)
const failedCount = computed(() => props.items.filter(item => item.production_status === 'failed' || ['生成失败', '生产失败', '生产异常'].includes(item.status)).length)
const initials = computed(() => (props.accountName || props.accountId || '账').trim().slice(0, 1).toLocaleUpperCase())
const accountType = computed(() => props.profile?.account_type || (props.profile?.certified === true ? '认证' : props.profile?.certified === false ? '非认证' : '—'))
</script>

<template>
  <article class="batch-account-profile-card" :class="{ expanded }">
    <header class="batch-account-profile-head">
      <div class="batch-account-profile-main">
        <div class="batch-account-avatar" aria-hidden="true">{{ initials }}</div>
        <div class="batch-account-identity">
          <div class="batch-account-title-row">
            <button class="batch-account-title" type="button" @click="emit('openAccount')">{{ accountName }}</button>
            <AccountTypeBadge :type="accountType" />
            <span v-if="lifecycleStage && lifecycleStage !== '—'" class="tag purple">{{ lifecycleStage }}</span>
          </div>
          <div class="batch-account-meta-row">
            <span>{{ accountId }}</span>
            <span v-if="profile?.organization">{{ profile.organization }}</span>
            <span v-if="profile?.um_no">UM {{ profile.um_no }}</span>
          </div>
          <div class="batch-account-persona">
            <small>人设</small>
            <span>{{ profile?.persona || '未配置' }}</span>
          </div>
        </div>
      </div>

      <div class="batch-account-summary">
        <div><strong>{{ items.length }}</strong><small>策划</small></div>
        <div><strong>{{ plannedDays }}</strong><small>有计划天数</small></div>
        <div><strong>{{ completedCount }}</strong><small>已完成</small></div>
        <div v-if="failedCount > 0" class="danger"><strong>{{ failedCount }}</strong><small>异常</small></div>
        <button class="batch-account-toggle" type="button" :aria-expanded="expanded" @click="emit('toggle')">
          <span>{{ expanded ? '收起计划' : '查看计划' }}</span>
          <svg :class="{ expanded }" width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m5 7.5 5 5 5-5" /></svg>
        </button>
      </div>
    </header>

    <div v-if="expanded" class="batch-account-profile-body">
      <slot />
    </div>
  </article>
</template>

<style scoped>
.batch-account-profile-card{overflow:hidden;border:1px solid var(--neutral-200);border-radius:14px;background:var(--surface);box-shadow:0 1px 2px rgba(15,23,42,.03);transition:border-color .16s ease,box-shadow .16s ease}
.batch-account-profile-card:hover{border-color:var(--neutral-300);box-shadow:0 6px 22px rgba(15,23,42,.05)}
.batch-account-profile-card.expanded{border-color:var(--primary-200);box-shadow:0 8px 28px rgba(15,23,42,.06)}
.batch-account-profile-head{display:flex;align-items:center;justify-content:space-between;gap:22px;padding:18px 20px}
.batch-account-profile-main{display:flex;align-items:flex-start;gap:14px;min-width:0}
.batch-account-avatar{display:grid;place-items:center;flex:0 0 42px;width:42px;height:42px;border-radius:12px;background:var(--primary-50);color:var(--primary-600);font-size:16px;font-weight:700}
.batch-account-identity{display:flex;flex-direction:column;gap:7px;min-width:0}
.batch-account-title-row{display:flex;align-items:center;flex-wrap:wrap;gap:8px}
.batch-account-title{padding:0;border:0;background:transparent;color:var(--neutral-900);font-size:15px;font-weight:650;line-height:22px;cursor:pointer;text-align:left}
.batch-account-title:hover{color:var(--primary-600)}
.batch-account-title:focus-visible{outline:2px solid var(--primary-300);outline-offset:3px;border-radius:4px}
.batch-account-meta-row{display:flex;align-items:center;flex-wrap:wrap;gap:0;color:var(--neutral-400);font-size:11px;line-height:18px}
.batch-account-meta-row span{display:inline-flex;align-items:center}
.batch-account-meta-row span+span::before{width:1px;height:11px;margin:0 9px;background:var(--neutral-200);content:''}
.batch-account-persona{display:flex;align-items:center;gap:7px;min-width:0}
.batch-account-persona small{flex:none;padding:2px 6px;border-radius:5px;background:var(--neutral-100);color:var(--neutral-500);font-size:10px;line-height:16px}
.batch-account-persona span{max-width:520px;color:var(--neutral-600);font-size:12px;line-height:18px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.batch-account-summary{display:flex;align-items:center;justify-content:flex-end;gap:18px;flex:none}
.batch-account-summary>div{display:flex;flex-direction:column;align-items:flex-end;gap:2px;min-width:44px}
.batch-account-summary strong{color:var(--neutral-800);font-size:15px;line-height:20px;font-variant-numeric:tabular-nums}
.batch-account-summary small{color:var(--neutral-400);font-size:10px;line-height:16px;white-space:nowrap}
.batch-account-summary .danger strong{color:var(--danger,#dc2626)}
.batch-account-toggle{display:inline-flex;align-items:center;gap:6px;height:34px;padding:0 10px;border:1px solid var(--neutral-200);border-radius:8px;background:var(--surface);color:var(--neutral-600);font-size:12px;cursor:pointer;transition:background .16s ease,border-color .16s ease,color .16s ease}
.batch-account-toggle:hover{border-color:var(--primary-200);background:var(--primary-50);color:var(--primary-600)}
.batch-account-toggle svg{transition:transform .16s ease}.batch-account-toggle svg.expanded{transform:rotate(180deg)}
.batch-account-profile-body{padding:0 18px 18px;border-top:1px solid var(--neutral-100);background:linear-gradient(180deg,var(--neutral-50),var(--surface) 72px)}
.batch-account-profile-body :deep(.account-week-carousel){margin-top:16px}
@media(max-width:900px){.batch-account-profile-head{align-items:flex-start;flex-direction:column}.batch-account-summary{width:100%;justify-content:flex-start;flex-wrap:wrap}.batch-account-summary>div{align-items:flex-start}.batch-account-toggle{margin-left:auto}}
@media(max-width:580px){.batch-account-profile-head{padding:14px}.batch-account-profile-main{gap:10px}.batch-account-avatar{width:36px;height:36px;flex-basis:36px;border-radius:10px}.batch-account-persona span{max-width:240px}.batch-account-summary{gap:12px}.batch-account-profile-body{padding:0 10px 12px}}
</style>
