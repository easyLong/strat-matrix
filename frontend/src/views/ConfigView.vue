<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import LoadingSkeleton from '../components/LoadingSkeleton.vue'
import TaxonomyPanel from '../components/TaxonomyPanel.vue'
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
const lifecycleEditing = ref(false)
const activeLifecycleStage = ref('')
const remoteConfigPending = ref(false)
let configSyncTimer: number | undefined
let configSyncBusy = false
const lifecycleRules = computed(() => draft.value.lifecycle_rules)
const lifecycleMetricOptions = [
  { value: 'valid_content_count', label: '有效内容数', unit: '篇' },
  { value: 'rolling_interaction_count', label: '滚动篇均互动数', unit: '次/篇' },
  { value: 'followers_count', label: '粉丝数', unit: '人' },
]
const lifecycleOperatorOptions = [
  { value: 'lt', label: '<' },
  { value: 'lte', label: '≤' },
  { value: 'gte', label: '≥' },
  { value: 'gt', label: '>' },
  { value: 'eq', label: '=' },
]
const tagDirty = computed(() => Boolean(tagBaseline.value) && JSON.stringify(tagItems.value) !== tagBaseline.value)
const pageDirty = computed(() => dirty.value || tagDirty.value)
const hasUnsavedChanges = computed(() => editing.value && pageDirty.value)
const coldStartDefinition = computed(() => coldStartSummary(draft.value.lifecycle_rules))

function metricUnit(field: string) {
  return lifecycleMetricOptions.find(option => option.value === field)?.unit ?? ''
}

function coldStartSummary(rules: LifecycleRule[]) {
  const growth = rules.find(rule => rule.name === '流量增长期')
  const lowBoundary = growth?.conditions.filter(condition =>
    ['followers_count', 'valid_content_count'].includes(condition.field) && condition.operator === 'gte',
  ) ?? []
  if (!lowBoundary.length) return '未命中其他阶段时归入此阶段'
  const conditions = lowBoundary.map(condition => {
    const metric = lifecycleMetricOptions.find(option => option.value === condition.field)
    return `${metric?.label ?? condition.field} < ${condition.value} ${metric?.unit ?? ''}`
  })
  return `${conditions.join(' 或 ')}；未命中其他阶段时也归入此阶段`
}

function lifecycleRuleSummary(rule: LifecycleRule, rules: LifecycleRule[] = draft.value.lifecycle_rules) {
  if (rule.catchAll) return coldStartSummary(rules)
  if (rule.condition_mode === 'grouped') return lifecycleGroups(rule).map(group => group.map(condition => {
    const metric = lifecycleMetricOptions.find(option => option.value === condition.field)
    const operator = lifecycleOperatorOptions.find(option => option.value === condition.operator)
    return `${metric?.label ?? condition.field} ${operator?.label ?? condition.operator} ${condition.value} ${metric?.unit ?? ''}`
  }).join(' 且 ')).map(group => `（${group}）`).join(' 或 ')
  return rule.conditions.map((condition, index) => {
    const metric = lifecycleMetricOptions.find(option => option.value === condition.field)
    const operator = lifecycleOperatorOptions.find(option => option.value === condition.operator)
    const prefix = index === 0 ? '' : condition.join === 'OR' ? ' 或 ' : ' 且 '
    return `${prefix}${metric?.label ?? condition.field} ${operator?.label ?? condition.operator} ${condition.value} ${metric?.unit ?? ''}`
  }).join('')
}

const versionDetailRows = computed(() => versionDetail.value
  ? configDetailRows(versionDetail.value.config)
  : [])
const versionPrevious = computed(() => {
  if (!versionDetail.value) return null
  const index = versions.value.findIndex(item => item.version === versionDetail.value?.version)
  return index >= 0 ? versions.value[index + 1] ?? null : null
})
const versionChanges = computed(() => {
  if (!versionDetail.value || !versionPrevious.value) return []
  const current = configDetailRows(versionDetail.value.config)
  const previous = new Map(configDetailRows(versionPrevious.value.config).map(row => [row.key, row.value]))
  return current.flatMap(row => {
    const oldValue = previous.get(row.key)
    return oldValue === row.value ? [] : [{ ...row, oldValue: oldValue ?? '无', newValue: row.value }]
  })
})

function configDetailRows(config: StrategyConfig) {
  const rows: { key: string; group: string; label: string; value: string }[] = [
    { key: 'planning_days', group: '内容策划配置', label: '每周策划日', value: config.planning_days.map(day => ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][day - 1] ?? `周${day}`).join('、') },
    { key: 'schedule', group: '内容策划配置', label: '自动策划调度时间', value: `每周${['一', '二', '三', '四', '五', '六', '日'][config.schedule_day - 1]} ${config.schedule_time}` },
    { key: 'marketing_max', group: '内容策划配置', label: '营销内容周上限', value: `${config.marketing_max} 条 / 营销账号 / 周` },
    { key: 'hotspot_ratio', group: '内容策划配置', label: '热点选题占比', value: `${config.hotspot_ratio}%` },
    { key: 'rolling_posts', group: '策划规则配置', label: '滚动统计窗口', value: `${config.rolling_posts} 篇` },
  ]
  for (const stage of config.stage_targets) {
    rows.push({ key: `stage:${stage.name}:traffic`, group: '策划规则配置', label: `${stage.name} · 流量目标`, value: `${stage.traffic}%` })
    rows.push({ key: `stage:${stage.name}:conversion`, group: '策划规则配置', label: `${stage.name} · 转化目标`, value: `${stage.conversion}%` })
  }
  for (const rule of config.lifecycle_rules) {
    rows.push({ key: `lifecycle:${rule.name}`, group: '策划规则配置', label: rule.name, value: lifecycleRuleSummary(rule, config.lifecycle_rules) })
  }
  return rows
}

function showVersionDetail(version: ConfigVersionSummary) {
  versionDetail.value = version
}

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

function lifecycleGroups(rule: LifecycleRule): LifecycleCondition[][] {
  const groups: LifecycleCondition[][] = []
  for (const condition of rule.conditions) {
    if (!groups.length || condition.join === 'OR') groups.push([])
    groups[groups.length - 1]!.push(condition)
  }
  return groups
}
function setLifecycleGroups(rule: LifecycleRule, groups: LifecycleCondition[][]) {
  rule.conditions = groups.flatMap((group, groupIndex) => group.map((condition, index) => ({ ...condition, join: groupIndex > 0 && index === 0 ? 'OR' : 'AND' })))
}
function editLifecycleRule(rule: LifecycleRule) {
  if (rule.condition_mode !== 'grouped') {
    let groups: LifecycleCondition[][] = []
    rule.conditions.forEach((condition, index) => {
      if (index === 0 || condition.join === 'OR') groups.push([{ ...condition }])
      else groups = groups.map(group => [...group, { ...condition }])
    })
    setLifecycleGroups(rule, groups)
    rule.condition_mode = 'grouped'
  }
  activeLifecycleStage.value = rule.name
}
function addLifecycleCondition(rule: LifecycleRule, groupIndex: number) {
  const groups = lifecycleGroups(rule)
  groups[groupIndex]!.push({ field: 'valid_content_count', operator: 'gte', value: 0, join: 'AND' })
  setLifecycleGroups(rule, groups)
}
function addLifecycleGroup(rule: LifecycleRule) {
  setLifecycleGroups(rule, [...lifecycleGroups(rule), [{ field: 'valid_content_count', operator: 'gte', value: 0, join: 'OR' }]])
}
function removeLifecycleCondition(rule: LifecycleRule, groupIndex: number, conditionIndex: number) {
  const groups = lifecycleGroups(rule)
  groups[groupIndex]!.splice(conditionIndex, 1)
  if (!groups[groupIndex]!.length) groups.splice(groupIndex, 1)
  if (groups.length) setLifecycleGroups(rule, groups)
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
  lifecycleEditing.value = false
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
    lifecycleEditing.value = false
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
  lifecycleEditing.value = true
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
  lifecycleEditing.value = false
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
      <div class="card-head"><div><h2>内容策划配置</h2></div></div>
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
        <div class="lifecycle-definition-head"><div><b>生命周期阶段判定</b></div></div>
        <div class="lifecycle-definition-list">
          <div v-for="rule in lifecycleRules" :key="rule.name" class="lifecycle-definition lifecycle-grouped-rule">
            <div class="lifecycle-rule-heading"><b>{{ rule.name }}</b><span class="lifecycle-rule-summary">{{ lifecycleRuleSummary(rule) }}</span><button v-if="!rule.catchAll && lifecycleEditing" class="text-btn" type="button" @click="activeLifecycleStage === rule.name ? activeLifecycleStage = '' : editLifecycleRule(rule)">{{ activeLifecycleStage === rule.name ? '确认' : '编辑' }}</button></div>
            <template v-if="!rule.catchAll">
              <template v-for="(group, groupIndex) in lifecycleGroups(rule)" :key="groupIndex">
                <div v-if="groupIndex" class="lifecycle-or">或</div>
                <div class="lifecycle-condition-group">
                  <div v-for="(condition, conditionIndex) in group" :key="conditionIndex" class="lifecycle-group-row">
                    <span v-if="conditionIndex" class="lifecycle-and">且</span><span v-else class="lifecycle-and-placeholder"></span>
                    <select v-model="condition.field" aria-label="指标"><option v-for="option in lifecycleMetricOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select>
                    <select v-model="condition.operator" aria-label="运算符"><option v-for="option in lifecycleOperatorOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select>
                    <input v-model.number="condition.value" type="number" min="0" step="1" aria-label="阈值" /><span>{{ metricUnit(condition.field) }}</span>
                    <button v-if="rule.conditions.length > 1" class="icon-btn" type="button" aria-label="删除条件" @click="removeLifecycleCondition(rule, groupIndex, conditionIndex)">×</button>
                  </div>
                  <button class="text-btn" type="button" @click="addLifecycleCondition(rule, groupIndex)">＋ 添加且条件</button>
                </div>
              </template>
              <button class="text-btn lifecycle-add-group" type="button" @click="addLifecycleGroup(rule)">＋ 添加或条件组</button>
            </template>
          </div>
        </div>
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
  <section class="card config-overview-card">
    <div class="card-head"><div><h2>内容策划配置</h2></div></div>
    <div class="card-body config-overview-body">
      <div class="config-at-glance">
        <div class="config-glance-item config-glance-days"><span>每周策划日</span><div class="config-glance-days-list"><b v-for="day in planningDays" :key="day">{{ ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][day - 1] }}</b></div></div>
        <div class="config-glance-item"><span>自动策划调度时间</span><b>每周{{ ['一', '二', '三', '四', '五', '六', '日'][scheduleDay - 1] }} {{ scheduleTime }}</b></div>
        <div class="config-glance-item"><span>营销内容周上限</span><b>{{ draft.marketing_max }} 条 / 营销账号</b></div>
        <div class="config-glance-item"><span>热点选题占比</span><b>{{ draft.hotspot_ratio }}%</b></div>
      </div>
    </div>
  </section>
  <section class="card config-overview-card">
    <div class="card-head"><div><h2>策划规则配置</h2></div></div>
    <div class="card-body config-overview-body">
      <section class="config-readonly-panel">
        <div class="config-readonly-panel-head"><h3>生命周期阶段判定</h3></div>
        <div class="stage-table-wrap">
          <table class="stage-table config-readonly-stage-table lifecycle-summary-table"><thead><tr><th>阶段</th><th>进入条件</th></tr></thead>
            <tbody><tr v-for="rule in lifecycleRules" :key="rule.name">
              <td><b>{{ rule.name }}</b></td><td>{{ lifecycleRuleSummary(rule, lifecycleRules) }}</td>
            </tr></tbody>
          </table>
        </div>
      </section>
      <section class="config-readonly-panel">
        <div class="config-readonly-panel-head"><h3>阶段经营目标</h3></div>
        <div class="stage-table-wrap">
          <table class="stage-table config-readonly-stage-table"><thead><tr><th>生命周期阶段</th><th>流量目标</th><th>转化目标</th></tr></thead>
            <tbody><tr v-for="stage in draft.stage_targets" :key="stage.name">
              <td><b>{{ stage.name }}</b></td><td>{{ stage.traffic }}%</td><td>{{ stage.conversion }}%</td>
            </tr></tbody>
          </table>
        </div>
      </section>
      <section class="config-readonly-panel">
        <div class="config-readonly-panel-head"><h3>滚动统计窗口</h3><span><b>{{ draft.rolling_posts }} 篇</b></span></div>
      </section>
      <section class="config-readonly-panel config-readonly-tag-panel">
        <div class="config-readonly-panel-head"><h3>选题标签配置</h3></div>
        <TaxonomyPanel :model-value="tagItems" />
      </section>
    </div>
  </section>
  </template>
  <section v-if="historyView && !loading && store.initialized" class="card">
    <div class="table-wrap"><table><thead><tr><th>版本</th><th>生成时间</th><th>配置摘要</th><th>操作人</th><th>操作</th></tr></thead><tbody>
      <tr v-for="version in versions" :key="version.version"><td><b>V{{ displayVersionNumber(version) }}</b><span v-if="version.version === versions[0]?.version" class="tag green row-tag">当前</span></td><td>{{ formatDateTime(version.created_at) }}</td><td>每周 {{ version.config.planning_days.length }} 天 · 营销上限 {{ version.config.marketing_max }} · 滚动 {{ version.config.rolling_posts }} 篇 · 五阶段目标与定义</td><td>{{ version.created_by }}</td><td><div class="page-actions"><button class="text-btn" type="button" @click="showVersionDetail(version)">查看详情</button><button v-if="version.version !== versions[0]?.version" class="text-btn" type="button" :disabled="busy" @click="restoreVersion(version)">恢复此版本</button></div></td></tr>
      <tr v-if="versions.length === 0"><td colspan="5"><div class="empty-state">暂无配置记录</div></td></tr>
    </tbody></table></div>
  </section>

  <div v-if="versionDetail" class="drawer-mask show" @click.self="versionDetail = null">
    <aside class="drawer" role="dialog" aria-modal="true" :aria-label="`总配置版本 V${versionDetail.version} 详情`">
      <div class="drawer-head"><div><small>总配置 · {{ formatDateTime(versionDetail.created_at) }}</small><h2>V{{ displayVersionNumber(versionDetail) }} 配置详情</h2></div><button class="icon-btn" type="button" aria-label="关闭" @click="versionDetail = null">×</button></div>
      <div class="drawer-body">
        <h3>修改摘要</h3>
        <p v-if="versionPrevious" class="muted">与总配置 V{{ displayVersionNumber(versionPrevious) }} 对比</p>
        <div v-if="versionPrevious && versionChanges.length" class="table-wrap"><table><thead><tr><th>配置项</th><th>原值</th><th>新值</th></tr></thead><tbody><tr v-for="change in versionChanges" :key="change.key"><td>{{ change.label }}</td><td>{{ change.oldValue }}</td><td>{{ change.newValue }}</td></tr></tbody></table></div>
        <div v-else class="detail-note">{{ versionPrevious ? '该版本与上一版本配置内容相同。' : '没有更早的模块版本可供比较。' }}</div>
        <h3>完整配置</h3>
        <div class="config-version-group">
          <b>内容策划配置</b>
          <div class="table-wrap"><table><tbody><tr v-for="row in versionDetailRows.filter(item => item.group === '内容策划配置')" :key="row.key"><th>{{ row.label }}</th><td>{{ row.value }}</td></tr></tbody></table></div>
        </div>
        <div class="config-version-group">
          <b>策划规则配置</b>
          <div class="table-wrap"><table><thead><tr><th>生命周期阶段判定</th><th>进入条件</th></tr></thead><tbody>
            <tr v-for="rule in versionDetail.config.lifecycle_rules" :key="rule.name"><td><b>{{ rule.name }}</b></td><td>{{ lifecycleRuleSummary(rule, versionDetail.config.lifecycle_rules) }}</td></tr>
          </tbody></table></div>
          <div class="table-wrap"><table><thead><tr><th>阶段经营目标</th><th>流量目标</th><th>转化目标</th></tr></thead><tbody>
            <tr v-for="stage in versionDetail.config.stage_targets" :key="stage.name"><td><b>{{ stage.name }}</b></td><td>{{ stage.traffic }}%</td><td>{{ stage.conversion }}%</td></tr>
          </tbody></table></div>
          <div class="detail-note">滚动统计窗口：{{ versionDetail.config.rolling_posts }} 篇</div>
        </div>
      </div>
      <div class="drawer-foot"><button class="btn" type="button" @click="versionDetail = null">关闭</button></div>
    </aside>
  </div>
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
.config-overview-body .lifecycle-summary-table th:first-child { width: 160px; }
.config-overview-body .lifecycle-summary-table th:nth-child(2), .config-overview-body .lifecycle-summary-table td:nth-child(2) { width: auto; text-align: left; white-space: normal; overflow-wrap: anywhere; }
.config-stack .lifecycle-grouped-rule{display:block;padding:12px 14px}
.lifecycle-rule-heading{display:flex;align-items:center;gap:14px;min-height:32px}.lifecycle-rule-heading>b{flex:0 0 90px}.config-stack .lifecycle-rule-heading>.text-btn{display:none}.lifecycle-rule-summary{flex:1;padding:7px 10px;border-radius:6px;background:var(--neutral-50);color:var(--neutral-600);font-size:12px;line-height:20px}
.lifecycle-condition-group{margin:10px 0;padding:12px;border:1px solid var(--neutral-200);border-radius:7px}.lifecycle-group-row{display:flex;align-items:center;gap:8px;margin-bottom:8px;color:var(--neutral-500);font-size:12px}.lifecycle-group-row select,.lifecycle-group-row input{height:32px;padding:0 8px;border:1px solid var(--neutral-200);border-radius:6px;background:var(--surface)}.lifecycle-group-row select:first-of-type{width:155px}.lifecycle-group-row select:nth-of-type(2){width:64px}.lifecycle-group-row input{width:86px}.lifecycle-and,.lifecycle-or{color:var(--primary-600);background:var(--primary-50);border-radius:12px;padding:3px 8px;font-size:12px}.lifecycle-and-placeholder{width:28px}.lifecycle-or{display:inline-block}.lifecycle-add-group{margin-top:4px}@media(max-width:600px){.lifecycle-rule-heading{flex-wrap:wrap}.lifecycle-rule-summary{flex-basis:100%;order:3}.lifecycle-group-row{flex-wrap:wrap}}
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
.config-stack .lifecycle-definition-head{margin:14px 0 10px;padding-top:12px;font-size:13px}
.config-stack .lifecycle-definition-list{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;align-items:start}
.config-stack .lifecycle-definition{min-width:0;grid-template-columns:minmax(0,1fr);gap:8px;padding:11px 12px;background:var(--neutral-50);border-color:var(--neutral-200)}
.config-stack .lifecycle-stage-name{padding:0}
.config-stack .lifecycle-stage-name b{font-size:14px;line-height:22px;font-weight:600}
.config-stack .lifecycle-condition-list{gap:6px}
.config-stack .lifecycle-condition-row{display:grid;grid-template-columns:minmax(110px,1fr) 48px 68px 40px 44px 22px;gap:6px;max-width:560px}
.config-stack .lifecycle-condition-row select,.config-stack .lifecycle-condition-row input{width:100%;min-width:0;height:32px;padding:0 6px;border-radius:6px;font-size:13px}
.config-stack .lifecycle-condition-row input{text-align:center}
.config-stack .condition-unit{grid-column:4;font-size:11px}
.config-stack .condition-join{grid-column:5;width:44px!important}
.config-stack .condition-remove{grid-column:6;width:22px;height:26px;font-size:18px!important}
.config-stack .condition-remove:hover{color:var(--danger);background:var(--danger-bg);border-radius:5px}
.config-stack .condition-add{justify-self:start;padding:2px 0;font-size:11px}
.config-stack .lifecycle-definition.is-catch-all{grid-column:1/-1;grid-template-columns:100px minmax(0,1fr);align-items:center;background:var(--neutral-50)}
.config-stack .lifecycle-catch-all{font-size:12px;line-height:1.6;color:var(--neutral-500)}
@media(max-width:1100px){.config-stack .lifecycle-definition-list{grid-template-columns:minmax(0,1fr)}}
@media(max-width:780px){.config-stack .config-control-grid{grid-template-columns:minmax(0,1fr);gap:12px}.config-stack .card-body{padding:12px}.config-stack .lifecycle-definition.is-catch-all{grid-template-columns:minmax(0,1fr);gap:5px}}
@media(max-width:580px){.config-stack .lifecycle-condition-row{grid-template-columns:48px 64px minmax(0,1fr) 44px 22px}.config-stack .lifecycle-condition-row select:first-child{grid-column:1/-1;grid-row:1;min-width:0}.config-stack .lifecycle-condition-row select:nth-child(2){grid-column:1;grid-row:2}.config-stack .lifecycle-condition-row input{grid-column:2;grid-row:2}.config-stack .condition-unit{grid-column:3;grid-row:2}.config-stack .condition-join{grid-column:4;grid-row:2}.config-stack .condition-remove{grid-column:5;grid-row:2}.config-stack .lifecycle-definition{padding:10px}.config-readonly-stage-table{min-width:540px}}
.config-readonly-panel-head h3{font-size:14px;line-height:22px;font-weight:600}
.config-readonly-stage-table th,.config-readonly-stage-table td{padding:8px;font-size:13px;line-height:20px}
.config-readonly-stage-table th:nth-child(1){width:22%}
.config-readonly-stage-table th:nth-child(2),.config-readonly-stage-table th:nth-child(3){width:10%}
.config-readonly-stage-table th:nth-child(4){width:58%}
.config-readonly-tag-title{font-size:12px;line-height:18px}
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
.config-readonly-tag-row .tag-pills{gap:6px}
.config-readonly-tag-row .tag{padding:2px 7px;border:1px solid var(--label-border);border-radius:4px;background:var(--label-background);color:var(--label-color);font-size:11px;line-height:16px}
.config-readonly-tag-row .tag.disabled{border-style:dashed;border-color:var(--neutral-200);background:var(--neutral-50);color:var(--neutral-400)}
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
.config-readonly-columns{grid-template-columns:minmax(0,1fr)}.config-readonly-tag-panel{padding:0;overflow:hidden}.config-readonly-tag-panel .config-readonly-panel-head{padding:15px 18px;margin:0}
</style>
