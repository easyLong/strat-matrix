<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import PageBreadcrumbs from '../components/PageBreadcrumbs.vue'
import { usePageBreadcrumbs } from '../composables/usePageBreadcrumbs'
import LoadingSkeleton from '../components/LoadingSkeleton.vue'
import TaxonomyPanel from '../components/TaxonomyPanel.vue'
import ConfigOverview from '../components/config/ConfigOverview.vue'
import ConfigHistory from '../components/config/ConfigHistory.vue'
import LifecycleRulesEditor from '../components/config/LifecycleRulesEditor.vue'
import { recommendedTaxonomy, tagNames } from '../topicTaxonomy'
import { formatDateTime } from '../planningTime'
import { api, type TagTaxonomyItem } from '../api'
import { usePlanningStore } from '../store'
import type { ConfigVersionSummary, LifecycleCondition, LifecycleRule, StrategyConfig } from '../types'

const store = usePlanningStore()
const router = useRouter()

function cloneConfig(value: StrategyConfig): StrategyConfig {
  return {
    marketing_max: value.marketing_max,
    planning_days: [...value.planning_days],
    schedule_day: value.schedule_day,
    schedule_time: value.schedule_time,
    hotspot_ratio: value.hotspot_ratio,
    rolling_posts: value.rolling_posts,
    stage_targets: value.stage_targets.map(stage => ({ ...stage })),
    lifecycle_rules: value.lifecycle_rules.map(rule => ({ ...rule, conditions: rule.conditions.map(condition => ({ ...condition })) })),
  }
}

const draft = ref<StrategyConfig>(cloneConfig(store.config))
const busy = ref(false)
const loading = ref(false)
const notice = ref('')
const error = ref('')
const versions = ref<ConfigVersionSummary[]>([])
const versionDetail = ref<ConfigVersionSummary | null>(null)
const dirty = computed(() => JSON.stringify(draft.value) !== JSON.stringify(store.config))
let removeRouteGuard: (() => void) | undefined
const tagVersion = ref(0)
const tagItems = ref<Record<string, TagTaxonomyItem[]>>({ T1: [], T2: [], T3: [], T4: [], T5: [] })
const tagBaseline = ref('')
const editing = ref(false)
const historyView = ref(false)
const confirmation = ref<{ title: string; message: string; confirmLabel: string; cancelLabel: string; danger?: boolean; safePrimary?: boolean } | null>(null)
const confirmationPanel = ref<HTMLElement | null>(null)
const confirmationSafeAction = ref<HTMLButtonElement | null>(null)
let confirmationReturnFocus: HTMLElement | null = null
let confirmationResolver: ((confirmed: boolean) => void) | undefined
const planningDays = computed(() => draft.value.planning_days)
const scheduleDay = computed({ get: () => draft.value.schedule_day, set: value => { draft.value.schedule_day = value } })
const scheduleTime = computed({ get: () => draft.value.schedule_time, set: value => { draft.value.schedule_time = value } })
const hotspotRatio = computed({ get: () => draft.value.hotspot_ratio, set: value => { draft.value.hotspot_ratio = value } })
const remoteConfigPending = ref(false)
let configSyncTimer: number | undefined
let configSyncBusy = false
const lifecycleRules = computed(() => draft.value.lifecycle_rules)
const tagDirty = computed(() => Boolean(tagBaseline.value) && JSON.stringify(tagItems.value) !== tagBaseline.value)
const pageDirty = computed(() => dirty.value || tagDirty.value)
const hasUnsavedChanges = computed(() => editing.value && pageDirty.value)
usePageBreadcrumbs(() => {
  const root = { label: 'AI策划配置', action: async () => {
    if (busy.value) return
    if (editing.value) await cancelEditing()
    else closeHistory()
  } }
  if (historyView.value) return [
    root,
    { label: '历史配置', action: () => { versionDetail.value = null } },
    ...(versionDetail.value ? [{ label: `V${displayVersionNumber(versionDetail.value)} 配置详情` }] : []),
  ]
  return editing.value ? [root, { label: '编辑配置' }] : [root]
})

function requestConfirmation(options: NonNullable<typeof confirmation.value>) {
  if (confirmationResolver) confirmationResolver(false)
  confirmationReturnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
  confirmation.value = options
  void nextTick(() => { confirmationSafeAction.value?.focus() })
  return new Promise<boolean>(resolve => { confirmationResolver = resolve })
}

function closeConfirmation(confirmed: boolean) {
  const resolve = confirmationResolver
  confirmationResolver = undefined
  confirmation.value = null
  resolve?.(confirmed)
  const previous = confirmationReturnFocus
  void nextTick(() => { previous?.focus({ preventScroll: true }) })
}

function dismissConfirmation() {
  closeConfirmation(false)
}

function handleConfirmationKeys(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.preventDefault(); dismissConfirmation(); return }
  if (event.key !== 'Tab') return
  const buttons = confirmationPanel.value?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')
  if (!buttons?.length) return
  const first = buttons[0], last = buttons[buttons.length - 1]
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}

function movePlanningDay(event: KeyboardEvent, index: number) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  const buttons = (event.currentTarget as HTMLElement).parentElement?.querySelectorAll<HTMLButtonElement>('button')
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? 6 : (index + (event.key === 'ArrowRight' ? 1 : -1) + 7) % 7
  buttons?.[next]?.focus()
}

function displayVersionNumber(version: ConfigVersionSummary) {
  const index = versions.value.findIndex(item => item.version === version.version)
  return index < 0 ? version.version : versions.value.length - index
}

function togglePlanningDay(day: number) {
  const days = new Set(planningDays.value)
  if (days.has(day)) {
    if (days.size === 1) return
    days.delete(day)
  } else days.add(day)
  draft.value.planning_days = [...days].sort((a, b) => a - b)
}

watch(() => store.config, value => { draft.value = cloneConfig(value) }, { deep: true })
watch(() => store.databaseReady, ready => {
  if (ready) { void loadConfigData() }
}, { immediate: true })
const beforeUnload = (event: BeforeUnloadEvent) => {
  if (!hasUnsavedChanges.value) return
  event.preventDefault()
  event.returnValue = '当前存在未保存修改，离开后修改内容将丢失。'
}
const syncOnFocus = () => { void syncSavedConfig() }
const syncOnVisible = () => { if (!document.hidden) void syncSavedConfig() }
onMounted(() => {
  window.addEventListener('beforeunload', beforeUnload)
  window.addEventListener('focus', syncOnFocus)
  document.addEventListener('visibilitychange', syncOnVisible)
  configSyncTimer = window.setInterval(() => { void syncSavedConfig() }, 10000)
  removeRouteGuard = router.beforeEach((to, from) => {
    if (to.fullPath === from.fullPath || !hasUnsavedChanges.value) return true
    return requestConfirmation({ title: '离开策划配置？', message: '当前有未保存的配置修改，离开后这些内容将被放弃。', confirmLabel: '放弃修改并离开', cancelLabel: '继续编辑', danger: true, safePrimary: true })
  })
})
onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', beforeUnload)
  window.removeEventListener('focus', syncOnFocus)
  document.removeEventListener('visibilitychange', syncOnVisible)
  if (configSyncTimer !== undefined) window.clearInterval(configSyncTimer)
  removeRouteGuard?.()
})

async function syncSavedConfig() {
  if (!store.databaseReady || loading.value || busy.value || configSyncBusy || document.hidden) return
  configSyncBusy = true
  try {
    const latest = await api.config()
    if (loading.value || busy.value) return
    const changed = latest.version !== store.configVersion || JSON.stringify(latest.config) !== JSON.stringify(store.config)
    if (!changed) {
      remoteConfigPending.value = false
      return
    }
    if (pageDirty.value || editing.value) {
      remoteConfigPending.value = true
      return
    }
    store.applyConfig(latest)
    remoteConfigPending.value = false
    await loadVersions()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '同步策划配置失败'
  } finally {
    configSyncBusy = false
  }
}

async function loadVersions() {
  try {
    versions.value = await api.configVersions()
  }
  catch (exc) { error.value = exc instanceof Error ? exc.message : '读取配置历史失败' }
}

async function loadConfigData() {
  if (hasUnsavedChanges.value && !await requestConfirmation({ title: '加载最新配置？', message: '当前有未保存的配置修改，加载最新配置后这些修改将被放弃。', confirmLabel: '加载最新配置', cancelLabel: '继续编辑', danger: true })) return
  editing.value = false
  loading.value = true
  error.value = ''
  try {
    await Promise.all([store.refreshConfig(), loadVersions(), loadTagTaxonomy()])
    remoteConfigPending.value = false
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '读取策划配置失败'
  } finally {
    loading.value = false
  }
}

async function loadTagTaxonomy() {
  try {
    const loaded = await api.tagTaxonomy()
    tagVersion.value = loaded.version
    const normalizedItems: Record<string, TagTaxonomyItem[]> = {}
    for (const code of Object.keys(tagNames)) {
      normalizedItems[code] = loaded.items[code]?.length
        ? loaded.items[code].map(item => ({ ...item }))
        : recommendedTaxonomy()[code]
      tagItems.value[code] = normalizedItems[code]
    }
    // Compare against what the page actually displays. When the server has no
    // taxonomy rows yet, prototype defaults are read-only display fallbacks,
    // not unsaved user edits.
    tagBaseline.value = JSON.stringify(normalizedItems)
    // The previous page saved disabled names only in this browser. Offer them as
    // an unsaved draft when the server has no disabled labels yet.
    if (!Object.values(loaded.items).some(items => items.some(item => !item.enabled))) {
      try {
        const legacy = JSON.parse(localStorage.getItem('strat-matrix.config-ui') ?? '{}')
        const oldDisabled = legacy.disabledTags as Record<string, string[]> | undefined
        let restored = false
        for (const code of Object.keys(tagNames)) {
          const items = tagItems.value[code]
          for (const item of items) {
            if (oldDisabled?.[code]?.includes(item.name) && items.filter(tag => tag.enabled).length > 1) {
              item.enabled = false
              restored = true
            }
          }
        }
        if (restored) notice.value = '已读取此浏览器旧的停用标签，请核对并保存到服务端'
      } catch { /* Invalid old browser settings do not affect server data. */ }
    }
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '读取标签配置失败' }
}

const marketingValid = computed(() =>
  Number.isInteger(draft.value.marketing_max) && draft.value.marketing_max >= 0 &&
  planningDays.value.length > 0 && planningDays.value.length === new Set(planningDays.value).size &&
  planningDays.value.every(day => Number.isInteger(day) && day >= 1 && day <= 7) &&
  Number.isInteger(scheduleDay.value) && scheduleDay.value >= 1 && scheduleDay.value <= 7 &&
  /^([01]\d|2[0-3]):[0-5]\d$/.test(scheduleTime.value) &&
  Number.isInteger(hotspotRatio.value) && hotspotRatio.value >= 0 && hotspotRatio.value <= 100,
)
const strategyValid = computed(() =>
  Number.isInteger(draft.value.rolling_posts) && draft.value.rolling_posts >= 1 && draft.value.rolling_posts <= 100 &&
  draft.value.stage_targets.length === 5 &&
  draft.value.stage_targets.every(stage =>
    Number.isInteger(stage.traffic) && Number.isInteger(stage.conversion) &&
    stage.traffic >= 0 && stage.conversion >= 0 &&
    stage.traffic + stage.conversion === 100,
  ) &&
  lifecycleRules.value.length === 5 &&
  lifecycleRules.value.slice(0, 4).every(rule => !rule.catchAll && rule.conditions.length > 0 &&
    rule.conditions.every(condition => Number.isInteger(condition.value) && condition.value >= 0)) &&
  lifecycleRules.value[4]?.catchAll === true && lifecycleRules.value[4]?.conditions.length === 0,
)

function restore() {
  if (!editing.value) return
  draft.value = cloneConfig(store.config)
  notice.value = '已恢复到当前保存的配置'
  error.value = ''
}

async function saveAll() {
  if (!editing.value || !store.databaseReady || busy.value || !marketingValid.value || !strategyValid.value || !pageDirty.value) return
  const editedConfig = cloneConfig(draft.value)
  let latestSavedConfig: Awaited<ReturnType<typeof api.saveConfig>> | undefined
  busy.value = true
  notice.value = ''
  error.value = ''
  try {
    if (dirty.value) latestSavedConfig = await api.saveConfig(editedConfig, store.configVersion)
    if (latestSavedConfig) store.applyConfig(latestSavedConfig)
    if (tagDirty.value) {
      const savedTags = await api.saveTagTaxonomy(tagItems.value, tagVersion.value)
      tagVersion.value = savedTags.version
      tagItems.value = savedTags.items
      tagBaseline.value = JSON.stringify(tagItems.value)
      localStorage.removeItem('strat-matrix.config-ui')
    }
    await loadVersions()
    draft.value = cloneConfig(store.config)
    editing.value = false
        notice.value = '策划配置已保存'
  } catch (exc) {
    if (latestSavedConfig) {
      store.applyConfig(latestSavedConfig)
      draft.value = editedConfig
      void loadVersions()
    }
    error.value = exc instanceof Error ? exc.message : '保存失败'
  } finally {
    busy.value = false
  }
}

async function restoreVersion(version: ConfigVersionSummary) {
  if (busy.value || version.version === versions.value[0]?.version) return
  const visibleVersion = displayVersionNumber(version)
  if (!await requestConfirmation({ title: `恢复总配置 V${visibleVersion}？`, message: '恢复后将以该快照创建新的总配置版本，并覆盖当前账号配置与经营策略。', confirmLabel: '确认恢复', cancelLabel: '返回查看', danger: true })) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await store.restoreConfig(version.version)
    await loadVersions()
    notice.value = `总配置已基于 V${visibleVersion} 创建新版本`
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '恢复失败'
  } finally { busy.value = false }
}

function startEditing() {
  if (!store.databaseReady || busy.value || loading.value) return
  editing.value = true
  error.value = ''
  notice.value = ''
}

async function openHistory() {
  if (loading.value || busy.value || !store.databaseReady) return
  historyView.value = true
  versionDetail.value = null
  error.value = ''
  await loadVersions()
}

function closeHistory() {
  historyView.value = false
  versionDetail.value = null
  error.value = ''
}

async function cancelEditing() {
  if (!editing.value) return
  if (!await requestConfirmation({ title: '取消编辑', message: '当前配置修改尚未保存。取消后，本次修改内容将被放弃。', confirmLabel: '确认取消', cancelLabel: '继续编辑', danger: true, safePrimary: true })) return
  confirmCancelEditing()
}

function confirmCancelEditing() {
  if (!editing.value) return
  draft.value = cloneConfig(store.config)
  try {
    const baseline = JSON.parse(tagBaseline.value || '{}') as Record<string, TagTaxonomyItem[]>
    for (const code of Object.keys(tagNames)) tagItems.value[code] = (baseline[code] ?? []).map(item => ({ ...item }))
  } catch { /* Keep the current tag values if the baseline is unavailable. */ }
  editing.value = false
  remoteConfigPending.value = false
  error.value = ''
  notice.value = ''
}

</script>

<template>
  <div class="page-head config-page-head">
    <div class="page-actions">
      <template v-if="!editing && !historyView">
        <button class="btn primary" type="button" :disabled="loading || busy || !store.databaseReady" @click="startEditing">编辑配置</button>
        <button class="btn" type="button" :disabled="loading || busy || !store.databaseReady" @click="openHistory">历史配置</button>
      </template>
      <button v-else-if="historyView" class="btn" type="button" @click="closeHistory">返回配置</button>
      <template v-else>
        <button class="btn" type="button" :disabled="busy || !store.databaseReady" @click="restore">恢复当前配置</button>
        <button class="btn danger-outline" type="button" :disabled="busy" @click="cancelEditing">取消编辑</button>
        <button class="btn primary" type="button" :disabled="busy || !store.databaseReady || !marketingValid || !strategyValid || !pageDirty" @click="saveAll"><span v-if="busy" class="loading-spinner" aria-hidden="true" />{{ busy ? '保存中…' : '保存配置' }}</button>
      </template>
    </div>
  </div>

  <div v-if="notice" class="banner success-banner" role="status">{{ notice }}</div>
  <div v-if="error" class="banner error-banner" role="alert">{{ error }}</div>
  <div v-if="remoteConfigPending" class="banner warning-banner" role="status">配置已在其它位置更新，当前编辑内容已保留。</div>

  <section v-if="loading || !store.initialized" class="card"><LoadingSkeleton :rows="8" /></section>
  <template v-if="editing && !loading && store.initialized">
  <fieldset class="form-fieldset config-stack" :disabled="!store.databaseReady || busy || loading">
    <section class="card">
      <div class="card-head"><div><h2>策划内容配置</h2></div></div>
      <div class="card-body">
        <div class="form-grid config-control-grid">
          <div class="field"><span>每周策划日</span><div class="day-picker"><button v-for="day in [{ n: 1, label: '周一' }, { n: 2, label: '周二' }, { n: 3, label: '周三' }, { n: 4, label: '周四' }, { n: 5, label: '周五' }, { n: 6, label: '周六' }, { n: 7, label: '周日' }]" :key="day.n" class="day-chip" :class="{ active: planningDays.includes(day.n) }" type="button" :aria-pressed="planningDays.includes(day.n)" @keydown="movePlanningDay($event, day.n - 1)" @click="togglePlanningDay(day.n)">{{ day.label }}</button></div></div>
          <label class="field"><span>自动策划调度时间</span><div class="schedule-picker"><select v-model.number="scheduleDay"><option :value="1">周一</option><option :value="2">周二</option><option :value="3">周三</option><option :value="4">周四</option><option :value="5">周五</option><option :value="6">周六</option><option :value="7">周日</option></select><input v-model="scheduleTime" type="time" /></div></label>
          <label class="field"><span>营销内容周上限</span><div class="input-unit"><input v-model.number="draft.marketing_max" type="number" min="0" /><span>条 / 营销账号 / 周</span></div></label>
          <label class="field"><span>热点选题占比</span><div class="input-unit"><input v-model.number="hotspotRatio" type="number" min="0" max="100" /><span>%</span></div></label>
        </div>

        <p v-if="editing && !marketingValid" class="inline-error">请检查每周策划日、调度时间、营销上限和热点占比。</p>

      </div>
    </section>

    <section class="card">
      <div class="card-head"><div><h2>策划规则配置</h2></div></div>
      <div class="card-body">
        <LifecycleRulesEditor v-model="draft.lifecycle_rules" />
        <div class="lifecycle-definition-head"><div><b>阶段经营目标</b></div></div>
        <div class="stage-table-wrap">
          <table class="stage-table"><thead><tr><th>生命周期阶段</th><th>流量目标</th><th>转化目标</th><th>合计</th></tr></thead>
            <tbody><tr v-for="stage in draft.stage_targets" :key="stage.name">
              <td><b>{{ stage.name }}</b></td>
              <td><div class="input-unit compact"><input v-model.number="stage.traffic" type="number" min="0" max="100" /><span>%</span></div></td>
              <td><div class="input-unit compact"><input v-model.number="stage.conversion" type="number" min="0" max="100" /><span>%</span></div></td>
              <td><span :class="['tag', stage.traffic + stage.conversion === 100 ? 'green' : 'red']">{{ stage.traffic + stage.conversion }}%</span></td>
            </tr></tbody>
          </table>
        </div>
        <label class="field rolling-field"><span>滚动统计窗口</span><div class="input-unit"><input v-model.number="draft.rolling_posts" type="number" min="1" max="100" /><span>篇</span></div></label>
        <div class="lifecycle-definition-head"><div><b>选题标签配置</b></div></div>
        <TaxonomyPanel v-model="tagItems" :editing="editing" :disabled="busy || !store.databaseReady" />
        <p v-if="editing && !strategyValid" class="inline-error">请检查滚动窗口、生命周期进入条件；每个阶段的流量与转化目标之和必须为 100%。</p>
      </div>
    </section>
  </fieldset>
  </template>
  <template v-else-if="!historyView && !loading && store.initialized">
  <ConfigOverview :config="draft" :tag-items="tagItems" />
  </template>
  <ConfigHistory v-if="historyView && !loading && store.initialized" v-model:detail="versionDetail" :versions="versions" :disabled="busy" @restore="restoreVersion" />
  <div v-if="confirmation" class="app-confirm-mask" @click.self="dismissConfirmation">
    <section ref="confirmationPanel" class="app-confirm" role="alertdialog" aria-modal="true" aria-labelledby="app-confirm-title" aria-describedby="app-confirm-description" @keydown.stop="handleConfirmationKeys">
      <div class="app-confirm-icon" :class="{ danger: confirmation.danger }" aria-hidden="true">{{ confirmation.danger ? '!' : 'i' }}</div>
      <h2 id="app-confirm-title">{{ confirmation.title }}</h2>
      <p id="app-confirm-description">{{ confirmation.message }}</p>
      <div class="app-confirm-actions">
        <template v-if="confirmation.danger && confirmation.safePrimary">
          <button class="btn" type="button" @click="closeConfirmation(true)">{{ confirmation.confirmLabel }}</button>
          <button ref="confirmationSafeAction" class="btn app-confirm-danger" type="button" @click="closeConfirmation(false)">{{ confirmation.cancelLabel }}</button>
        </template>
        <template v-else-if="confirmation.danger">
          <button ref="confirmationSafeAction" class="btn" type="button" @click="closeConfirmation(false)">{{ confirmation.cancelLabel }}</button>
          <button class="btn app-confirm-danger" type="button" @click="closeConfirmation(true)">{{ confirmation.confirmLabel }}</button>
        </template>
        <button v-else class="btn primary" type="button" @click="closeConfirmation(true)">{{ confirmation.confirmLabel }}</button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.config-stack{gap:20px;margin-bottom:20px}
.config-stack>.card{margin-bottom:0}
.config-stack .card-head{padding:16px 24px}
.config-stack .card-head h2{font-size:16px;line-height:24px;font-weight:600}
.config-stack .card-body{padding:16px 24px}
.config-stack .config-control-grid{gap:12px 28px}
.config-stack .field{gap:8px;font-size:13px;font-weight:400}
.config-stack .day-picker{gap:5px}
.config-stack .day-chip{position:relative;height:32px;padding:0 11px;border-radius:999px;font-size:13px;font-weight:500}
.config-stack .day-chip::after{content:'';position:absolute;inset:-6px 0}
.config-stack .day-chip.active::before{content:'✓';margin-right:5px}
.config-stack .schedule-picker{width:280px;max-width:100%;gap:6px}
.config-stack .schedule-picker select,.config-stack .schedule-picker input{height:32px;min-height:32px;font-size:12px}
.config-stack .schedule-picker input{width:116px}
.config-stack .input-unit{height:32px}
.config-stack .input-unit input{width:64px;height:32px;min-height:32px;padding:0 8px;font-size:13px}
.config-stack .input-unit span{font-size:11px;padding-right:8px}
.config-stack .rolling-field{flex-direction:row;align-items:center;gap:10px;margin-bottom:10px}
.config-stack .stage-table-wrap{border:1px solid var(--neutral-200);border-radius:7px}
.config-stack .stage-table{min-width:460px}
.config-stack .stage-table th,.config-stack .stage-table td{height:44px;padding:6px 12px;font-size:13px;font-variant-numeric:tabular-nums}
.config-stack .stage-table .tag{margin-left:0;padding:2px 7px;font-size:11px}
.config-stack .lifecycle-stage-name{padding:0}
.config-stack .lifecycle-stage-name b{font-size:14px;line-height:22px;font-weight:600}
.config-stack .condition-unit{grid-column:4;font-size:11px}
.config-stack .condition-join{grid-column:5;width:44px!important}
.config-stack .condition-remove{grid-column:6;width:22px;height:26px;font-size:18px!important}
.config-stack .condition-remove:hover{color:var(--danger);background:var(--danger-bg);border-radius:5px}
.config-stack .condition-add{justify-self:start;padding:2px 0;font-size:11px}
.config-stack .lifecycle-catch-all{font-size:12px;line-height:1.6;color:var(--neutral-500)}
@media(max-width:780px){.config-stack .config-control-grid{grid-template-columns:minmax(0,1fr);gap:12px}.config-stack .card-body{padding:12px}}
@media(max-width:580px){.config-stack .condition-unit{grid-column:3;grid-row:2}.config-stack .condition-join{grid-column:4;grid-row:2}.config-stack .condition-remove{grid-column:5;grid-row:2}}
.tag-content-title{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.tag-tabs-with-hint{display:flex;align-items:center;flex-wrap:wrap;gap:0 20px;padding:0 24px;border-bottom:1px solid var(--neutral-200)}
.tag-tabs-with-hint .tag-tabs{min-width:0;max-width:100%;padding:0;border-bottom:0}
.tag-user-need-hint{min-height:44px;font-weight:500}
.tag-content-head{align-items:center;justify-content:flex-start;flex-wrap:wrap;gap:14px;min-height:34px}
.tag-context-popover{position:fixed;z-index:70;box-sizing:border-box;width:132px;max-width:calc(100vw - 16px);padding:5px;border:1px solid var(--neutral-200);border-radius:8px;background:var(--surface);box-shadow:var(--shadow-3)}
.tag-context-popover.is-renaming{width:264px;padding:12px}
.tag-menu-item{display:flex;align-items:center;gap:9px;width:100%;height:32px;padding:0 9px;border:0;border-radius:5px;background:transparent;color:var(--neutral-600);font:inherit;font-size:12px;text-align:left;cursor:pointer}
.tag-menu-item:hover,.tag-menu-item:focus-visible{outline:none;background:var(--primary-50);color:var(--primary-600)}
.tag-menu-item.is-danger{color:var(--danger)}
.tag-menu-item.is-danger:hover,.tag-menu-item.is-danger:focus-visible{background:var(--danger-bg);color:var(--danger-hover)}
.tag-menu-item:disabled{opacity:.6;cursor:default}
.tag-menu-error{display:block;margin:7px 6px 4px;color:var(--danger);font-size:11px;line-height:1.5}
.tag-selection-actions{display:flex;align-items:center;justify-content:flex-end;gap:14px;margin-top:10px}
.tag-rename-input{box-sizing:border-box;width:100%;min-width:0;height:32px;padding:0 9px;border:1px solid var(--neutral-200);border-radius:6px;color:var(--neutral-900);background:var(--surface);font:inherit;font-size:12px}
.tag-rename-input:focus{outline:2px solid var(--focus-color);border-color:var(--primary-600)}
.tag-action-muted{color:var(--neutral-400)}
.tag-pills{--label-color:var(--primary-600);--label-background:var(--primary-50);--label-border:var(--primary-100)}
.tag-content .tag-pills{align-items:flex-start;gap:6px;min-height:0;padding:2px 0}
.tag-pills>.pill-edit{display:inline-flex;align-items:center;justify-content:center;min-width:0;min-height:26px;max-width:100%;padding:3px 9px;border:1px solid var(--label-border);border-radius:5px;background:var(--label-background);color:var(--label-color);font-family:inherit;font-size:12px;font-weight:500;line-height:18px;overflow-wrap:anywhere;text-align:left;cursor:pointer;transition:border-color .15s,box-shadow .15s}
.tag-pills>.pill-edit:not(:disabled):hover{border-color:var(--label-color)}
.tag-pills>.pill-edit.disabled{border-style:dashed;border-color:var(--neutral-200);background:var(--neutral-50);color:var(--neutral-400);text-decoration:none}
.tag-pills>.pill-edit.selected{border-color:var(--label-color);box-shadow:0 0 0 1px var(--label-color)}
.tag-pills>.pill-edit:focus-visible{outline:2px solid var(--primary-600);outline-offset:2px}
.tag-pills>.pill-edit:disabled{cursor:default;opacity:.6}
.app-confirm-mask{position:fixed;inset:0;z-index:80;display:grid;place-items:center;padding:20px;background:var(--mask)}
.app-confirm{width:min(400px,100%);padding:26px 28px 22px;border:1px solid #e7ebf2;border-radius:16px;background:var(--surface);box-shadow:var(--shadow-4);text-align:left;animation:app-confirm-in .16s ease-out}
.app-confirm-icon{display:grid;place-items:center;width:42px;height:42px;margin:0 0 16px;border:1px solid var(--primary-100);border-radius:50%;background:#f2f7ff;color:var(--primary-600);font-size:21px;font-weight:750}
.app-confirm-icon.danger{border-color:var(--processing-bg);background:var(--processing-bg);color:var(--processing);font-size:23px}
.app-confirm h2{margin:0;color:var(--neutral-900);font-size:18px;line-height:1.4}
.app-confirm p{margin:9px 0 24px;color:var(--neutral-500);font-size:13px;line-height:1.7}
.app-confirm-actions{display:flex;justify-content:flex-end;gap:8px}
.app-confirm-actions .btn{min-width:112px}
.app-confirm-danger{border-color:var(--danger);background:var(--danger);color:var(--surface)}
.app-confirm-danger:hover{border-color:var(--danger-hover);background:var(--danger-hover)}
@keyframes app-confirm-in{from{opacity:0;transform:translateY(5px) scale(.985)}to{opacity:1;transform:translateY(0) scale(1)}}
</style>


<style scoped>
.config-page-head .page-actions{margin-left:auto}
</style>
