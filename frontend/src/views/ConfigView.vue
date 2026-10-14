<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, type TagTaxonomyItem } from '../api'
import { usePlanningStore } from '../store'
import type { ConfigVersionSummary, LifecycleRule, StrategyConfig } from '../types'

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
const tagNames: Record<string, string> = { T1: '业务属性', T2: '经营作用', T3: '主题域', T4: '目标客群', T5: '生活场景' }
const tagTabs = ['T1', 'T2', 'T3', 'T4', 'T5', 'T6'] as const
const activeTag = ref<typeof tagTabs[number]>('T1')
const tagDescriptions: Record<string, string> = {
  T1: '定义选题是否具有明确业务或营销属性。',
  T2: '定义内容在账号经营中的主要作用。',
  T3: '定义内容所属的核心业务主题。',
  T4: '定义内容优先面向的核心用户群体。',
  T5: '定义内容触达用户的典型生活场景。',
}
const prototypeTags: Record<string, string[]> = {
  T1: ['非营销', '营销'],
  T2: ['流量', '转化'],
  T3: ['金融理财', '本地生活', '数码科技', '职场成长', '健康生活', '亲子家庭'],
  T4: ['年轻客群', '职场人群', '家庭客群', '宝妈客群', '银发客群'],
  T5: ['通勤', '周末休闲', '家庭消费', '餐饮', '出行', '居家'],
}
const newTagInputs = ref<Record<string, string>>({ T1: '', T2: '', T3: '', T4: '', T5: '' })
const tagAddOpen = ref(false)
const editing = ref(false)
const confirmation = ref<{ title: string; message: string; confirmLabel: string; cancelLabel: string; danger?: boolean } | null>(null)
let confirmationResolver: ((confirmed: boolean) => void) | undefined
const planningDays = computed(() => draft.value.planning_days)
const scheduleDay = computed({ get: () => draft.value.schedule_day, set: value => { draft.value.schedule_day = value } })
const scheduleTime = computed({ get: () => draft.value.schedule_time, set: value => { draft.value.schedule_time = value } })
const hotspotRatio = computed({ get: () => draft.value.hotspot_ratio, set: value => { draft.value.hotspot_ratio = value } })
const lifecycleEditing = ref(false)
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
const coldStartDefinition = computed(() => {
  const growth = lifecycleRules.value.find(rule => rule.name === '流量增长期')
  if (!growth || growth.conditions.length === 0 || growth.conditions.some((condition, index) =>
    condition.operator !== 'gte' || (index > 0 && condition.join !== 'OR'))) {
    return '未命中前置阶段条件的账号自动归入此阶段，确保每个账号都有且只有一个生命周期阶段。'
  }
  const conditions = growth.conditions.map(condition => {
    const metric = lifecycleMetricOptions.find(option => option.value === condition.field)
    return `${metric?.label ?? condition.field} < ${condition.value} ${metric?.unit ?? ''}`
  }).join('，且 ')
  return `未命中更高阶段，且 ${conditions}。边界随流量增长期的进入条件同步调整。`
})

function metricUnit(field: string) {
  return lifecycleMetricOptions.find(option => option.value === field)?.unit ?? ''
}

function lifecycleRuleSummary(rule: LifecycleRule) {
  if (rule.catchAll) return '未命中前置阶段条件时归入此阶段'
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
    { key: 'planning_days', group: '账号与自动策划配置', label: '每周策划日', value: config.planning_days.map(day => ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][day - 1] ?? `周${day}`).join('、') },
    { key: 'schedule', group: '账号与自动策划配置', label: '自动策划调度时间', value: `每周${['一', '二', '三', '四', '五', '六', '日'][config.schedule_day - 1]} ${config.schedule_time}` },
    { key: 'marketing_max', group: '账号与自动策划配置', label: '营销内容周上限', value: `${config.marketing_max} 条 / 营销账号 / 周` },
    { key: 'hotspot_ratio', group: '账号与自动策划配置', label: '热点槽位占比', value: `${config.hotspot_ratio}%` },
    { key: 'rolling_posts', group: '账号经营策略配置', label: '滚动统计窗口', value: `${config.rolling_posts} 篇` },
  ]
  for (const stage of config.stage_targets) {
    rows.push({ key: `stage:${stage.name}:traffic`, group: '账号经营策略配置', label: `${stage.name} · 流量目标`, value: `${stage.traffic}%` })
    rows.push({ key: `stage:${stage.name}:conversion`, group: '账号经营策略配置', label: `${stage.name} · 转化目标`, value: `${stage.conversion}%` })
  }
  for (const rule of config.lifecycle_rules) {
    rows.push({ key: `lifecycle:${rule.name}`, group: '账号生命周期阶段定义', label: rule.name, value: lifecycleRuleSummary(rule) })
  }
  return rows
}

function showVersionDetail(version: ConfigVersionSummary) {
  versionDetail.value = version
}

function requestConfirmation(options: NonNullable<typeof confirmation.value>) {
  if (confirmationResolver) confirmationResolver(false)
  confirmation.value = options
  return new Promise<boolean>(resolve => { confirmationResolver = resolve })
}

function closeConfirmation(confirmed: boolean) {
  const resolve = confirmationResolver
  confirmationResolver = undefined
  confirmation.value = null
  resolve?.(confirmed)
}

function displayVersionNumber(version: ConfigVersionSummary) {
  const index = versions.value.findIndex(item => item.version === version.version)
  return index < 0 ? version.version : versions.value.length - index
}

function addLifecycleCondition(rule: LifecycleRule) {
  if (rule.catchAll) return
  rule.conditions.push({ field: 'valid_content_count', operator: 'gte', value: 0, join: 'AND' })
}

function removeLifecycleCondition(rule: LifecycleRule, index: number) {
  if (rule.catchAll) return
  if (rule.conditions.length <= 1) return
  rule.conditions.splice(index, 1)
}

function getTagItems(code: string): TagTaxonomyItem[] {
  return tagItems.value[code] ?? []
}

function addTag(code: string) {
  if (!editing.value) return
  const value = (newTagInputs.value[code] ?? '').trim()
  if (!value) return
  if (getTagItems(code).some(tag => tag.name === value)) {
    error.value = '同一维度中已存在该标签'
    return
  }
  tagItems.value[code].push({ id: null, name: value, enabled: true })
  newTagInputs.value[code] = ''
  tagAddOpen.value = false
  error.value = ''
}

function renameTag(code: string, tag: TagTaxonomyItem) {
  if (!editing.value) return
  const next = window.prompt('请输入新的标签名称', tag.name)?.trim()
  if (!next || next === tag.name) return
  if (next.length > 80 || getTagItems(code).some(item => item !== tag && item.name === next)) {
    error.value = '标签名称不能超过 80 字，且同一维度内不能重复'
    return
  }
  tag.name = next
  error.value = ''
}

function toggleTagDisabled(code: string, tag: TagTaxonomyItem) {
  if (!editing.value) return
  if (tag.enabled && getTagItems(code).filter(item => item.enabled).length === 1) {
    error.value = '每个维度至少保留一个启用标签'
    return
  }
  tag.enabled = !tag.enabled
  error.value = ''
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
    return requestConfirmation({ title: '离开策划配置？', message: '当前有未保存的配置修改，离开后这些内容将被放弃。', confirmLabel: '放弃修改并离开', cancelLabel: '继续编辑', danger: true })
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
        : (prototypeTags[code] ?? []).map(name => ({ id: null, name, enabled: true }))
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
    tagAddOpen.value = false
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
  if (!editing.value) return
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

async function cancelEditing() {
  if (!editing.value) return
  if (!await requestConfirmation({ title: '确认取消编辑？', message: '当前配置修改尚未保存。取消后，本次修改内容将被放弃。', confirmLabel: '放弃修改', cancelLabel: '继续编辑', danger: true })) return
  confirmCancelEditing()
}

function confirmCancelEditing() {
  if (!editing.value) return
  draft.value = cloneConfig(store.config)
  try {
    const baseline = JSON.parse(tagBaseline.value || '{}') as Record<string, TagTaxonomyItem[]>
    for (const code of Object.keys(tagNames)) tagItems.value[code] = (baseline[code] ?? []).map(item => ({ ...item }))
  } catch { /* Keep the current tag values if the baseline is unavailable. */ }
  tagAddOpen.value = false
  newTagInputs.value = { T1: '', T2: '', T3: '', T4: '', T5: '' }
  editing.value = false
  lifecycleEditing.value = false
  remoteConfigPending.value = false
  error.value = ''
  notice.value = ''
}

</script>

<template>
  <div class="page-head">
    <div><h1>策划配置</h1></div>
    <div class="page-actions">
      <button class="btn" type="button" :disabled="loading || busy || !store.databaseReady" @click="loadConfigData">刷新配置</button>
      <button v-if="!editing" class="btn primary" type="button" :disabled="loading || busy || !store.databaseReady" @click="startEditing">编辑配置</button>
      <template v-else>
        <button class="btn" type="button" :disabled="busy || !store.databaseReady" @click="restore">恢复当前配置</button>
        <button class="btn" type="button" :disabled="busy" @click="cancelEditing">取消编辑</button>
        <button class="btn primary" type="button" :disabled="busy || !store.databaseReady || !marketingValid || !strategyValid || !pageDirty" @click="saveAll">保存经营策略</button>
      </template>
    </div>
  </div>

  <div v-if="notice" class="banner success-banner" role="status">{{ notice }}</div>
  <div v-if="error" class="banner error-banner" role="alert">{{ error }}</div>
  <div v-if="remoteConfigPending" class="banner warning-banner" role="status">配置已在其它位置更新，当前编辑内容已保留。<button class="text-btn" type="button" :disabled="loading || busy" @click="loadConfigData">加载最新配置</button></div>

  <div v-if="loading" class="banner info-banner" role="status">正在读取当前策划配置…</div>
  <fieldset class="form-fieldset config-stack" :disabled="!editing || !store.databaseReady || busy || loading">
    <section class="card">
      <div class="card-head"><div><h2>账号与自动策划配置</h2></div><span class="tag blue">运营可配置</span></div>
      <div class="card-body">
        <div class="form-grid config-control-grid">
          <div class="field"><span>每周策划日</span><div class="day-picker"><button v-for="day in [{ n: 1, label: '周一' }, { n: 2, label: '周二' }, { n: 3, label: '周三' }, { n: 4, label: '周四' }, { n: 5, label: '周五' }, { n: 6, label: '周六' }, { n: 7, label: '周日' }]" :key="day.n" class="day-chip" :class="{ active: planningDays.includes(day.n) }" type="button" @click="togglePlanningDay(day.n)">{{ day.label }}</button></div></div>
          <label class="field"><span>自动策划调度时间</span><div class="schedule-picker"><select v-model.number="scheduleDay"><option :value="1">周一</option><option :value="2">周二</option><option :value="3">周三</option><option :value="4">周四</option><option :value="5">周五</option><option :value="6">周六</option><option :value="7">周日</option></select><input v-model="scheduleTime" type="time" /></div></label>
          <label class="field"><span>营销内容周上限</span><div class="input-unit"><input v-model.number="draft.marketing_max" type="number" min="0" /><span>条 / 营销账号 / 周</span></div></label>
          <label class="field"><span>热点槽位占比</span><div class="input-unit"><input v-model.number="hotspotRatio" type="number" min="0" max="100" /><span>%</span></div></label>
        </div>

        <p v-if="editing && !marketingValid" class="inline-error">请检查每周策划日、调度时间、营销上限和热点占比。</p>
        <div class="footer-actions"><span class="form-note">当前：每周 {{ planningDays.length }} 个槽位 / 账号 · {{ ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][scheduleDay - 1] }} {{ scheduleTime }}</span></div>
      </div>
    </section>

    <section class="card">
      <div class="card-head"><div><h2>账号经营策略配置</h2></div><span class="tag blue">运营可配置</span></div>
      <div class="card-body">
        <label class="field rolling-field"><span>滚动统计窗口</span><div class="input-unit"><input v-model.number="draft.rolling_posts" type="number" min="1" max="100" /><span>篇</span></div></label>
        <div class="stage-table-wrap">
          <table class="stage-table"><thead><tr><th>生命周期阶段</th><th>流量目标</th><th>转化目标</th><th>合计</th></tr></thead>
            <tbody><tr v-for="stage in draft.stage_targets" :key="stage.name">
              <td><b>{{ stage.name }}</b><span class="tag gray">系统自动识别</span></td>
              <td><div class="input-unit compact"><input v-model.number="stage.traffic" type="number" min="0" max="100" /><span>%</span></div></td>
              <td><div class="input-unit compact"><input v-model.number="stage.conversion" type="number" min="0" max="100" /><span>%</span></div></td>
              <td><span :class="['tag', stage.traffic + stage.conversion === 100 ? 'green' : 'red']">{{ stage.traffic + stage.conversion }}%</span></td>
            </tr></tbody>
          </table>
        </div>
        <div class="lifecycle-definition-head"><div><b>账号生命周期阶段定义</b></div></div>

        <div class="lifecycle-definition-list"><div v-for="rule in lifecycleRules" :key="rule.name" class="lifecycle-definition"><div class="lifecycle-stage-name"><b>{{ rule.name }}</b></div><div v-if="rule.catchAll" class="lifecycle-catch-all">{{ coldStartDefinition }}</div><div v-else class="lifecycle-condition-list"><div v-for="(condition, index) in rule.conditions" :key="`${rule.name}-${index}`" class="lifecycle-condition-row"><select v-model="condition.field" :disabled="!lifecycleEditing" aria-label="指标"><option v-for="option in lifecycleMetricOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select><select v-model="condition.operator" :disabled="!lifecycleEditing" aria-label="运算符"><option v-for="option in lifecycleOperatorOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select><input v-model.number="condition.value" :disabled="!lifecycleEditing" type="number" step="1" aria-label="阈值" /><span class="condition-unit">{{ metricUnit(condition.field) }}</span><select v-if="index > 0" v-model="condition.join" :disabled="!lifecycleEditing" class="condition-join" aria-label="条件关系"><option value="AND">且</option><option value="OR">或</option></select><button v-if="lifecycleEditing && rule.conditions.length > 1" class="icon-btn condition-remove" type="button" aria-label="删除条件" @click="removeLifecycleCondition(rule, index)">×</button></div><button v-if="lifecycleEditing" class="text-btn condition-add" type="button" @click="addLifecycleCondition(rule)">＋ 添加条件</button></div></div></div>
        <p v-if="editing && !strategyValid" class="inline-error">请检查滚动窗口、生命周期进入条件；每个阶段的流量与转化目标之和必须为 100%。</p>
      </div>
    </section>
  </fieldset>
  <section class="card">
    <div class="card-head"><div><h2>选题标签配置</h2></div><div class="page-actions"><button class="btn small" type="button" :disabled="!editing || busy || activeTag === 'T6' || !store.databaseReady" @click="tagAddOpen = !tagAddOpen">{{ tagAddOpen ? '取消新增' : '新增标签' }}</button></div></div>
    <div class="tag-tabs" role="tablist"><button v-for="code in tagTabs" :key="code" class="tag-tab" :class="{ active: activeTag === code }" type="button" role="tab" :aria-selected="activeTag === code" @click="activeTag = code">{{ code }} {{ code === 'T1' ? '业务属性' : code === 'T2' ? '经营作用' : code === 'T3' ? '主题域' : code === 'T4' ? '目标客群' : code === 'T5' ? '生活场景' : '用户需求' }}</button></div>
    <div class="card-body tag-content">
      <template v-if="activeTag !== 'T6'">
        <div class="tag-content-head"><div><b>{{ activeTag }} {{ tagNames[activeTag] }}</b></div><span class="tag blue">单选字典</span></div>
        <div class="tag-pills"><div v-for="tag in getTagItems(activeTag)" :key="tag.id ?? tag.name" class="pill-edit" :class="{ disabled: !tag.enabled }"><span>{{ tag.name }}</span><template v-if="editing"><button class="mini" type="button" @click="renameTag(activeTag, tag)">改名</button><button class="mini" type="button" @click="toggleTagDisabled(activeTag, tag)">{{ tag.enabled ? '停用' : '启用' }}</button></template></div><span v-if="getTagItems(activeTag).length === 0" class="taxonomy-empty">暂无标签，请添加</span></div>
        <div v-if="editing && tagAddOpen" class="taxonomy-add inline-add"><input v-model="newTagInputs[activeTag]" class="field-input" type="text" @keyup.enter.prevent="addTag(activeTag)" /><button class="btn" type="button" :disabled="!newTagInputs[activeTag]?.trim()" @click="addTag(activeTag)">＋ 添加标签</button></div>

      </template>

    </div>
  </section>
  <section class="card">
    <div class="card-head"><div><h2>配置快照</h2></div></div>
    <div class="table-wrap"><table><thead><tr><th>版本</th><th>生成时间</th><th>配置摘要</th><th>操作人</th><th>操作</th></tr></thead><tbody>
      <tr v-for="version in versions" :key="version.version"><td><b>V{{ displayVersionNumber(version) }}</b><span v-if="version.version === versions[0]?.version" class="tag green row-tag">当前</span></td><td>{{ version.created_at }}</td><td>每周 {{ version.config.planning_days.length }} 天 · 营销上限 {{ version.config.marketing_max }} · 滚动 {{ version.config.rolling_posts }} 篇 · 五阶段目标与定义</td><td>{{ version.created_by }}</td><td><div class="page-actions"><button class="text-btn" type="button" @click="showVersionDetail(version)">查看详情</button><button v-if="editing" class="text-btn" type="button" :disabled="busy || version.version === versions[0]?.version" @click="restoreVersion(version)">恢复此版本</button></div></td></tr>
      <tr v-if="versions.length === 0"><td colspan="5"><div class="empty-state">暂无配置记录</div></td></tr>
    </tbody></table></div>
  </section>
  <p class="page-footnote">当前有效配置组合版本：V{{ store.configVersion }}<span v-if="store.configUpdatedAt"> · 更新时间：{{ store.configUpdatedAt }}</span></p>

  <div v-if="versionDetail" class="drawer-mask show" @click.self="versionDetail = null">
    <aside class="drawer" role="dialog" aria-modal="true" :aria-label="`总配置版本 V${versionDetail.version} 详情`">
      <div class="drawer-head"><div><small>总配置 · {{ versionDetail.created_at }}</small><h2>V{{ displayVersionNumber(versionDetail) }} 配置详情</h2></div><button class="icon-btn" type="button" aria-label="关闭" @click="versionDetail = null">×</button></div>
      <div class="drawer-body">
        <h3>修改摘要</h3>
        <p v-if="versionPrevious" class="muted">与总配置 V{{ displayVersionNumber(versionPrevious) }} 对比</p>
        <div v-if="versionPrevious && versionChanges.length" class="table-wrap"><table><thead><tr><th>配置项</th><th>原值</th><th>新值</th></tr></thead><tbody><tr v-for="change in versionChanges" :key="change.key"><td>{{ change.label }}</td><td>{{ change.oldValue }}</td><td>{{ change.newValue }}</td></tr></tbody></table></div>
        <div v-else class="detail-note">{{ versionPrevious ? '该版本与上一版本配置内容相同。' : '没有更早的模块版本可供比较。' }}</div>
        <h3>完整配置</h3>
        <div class="config-version-group">
          <b>账号与自动策划配置</b>
          <div class="table-wrap"><table><tbody><tr v-for="row in versionDetailRows.filter(item => item.group === '账号与自动策划配置')" :key="row.key"><th>{{ row.label }}</th><td>{{ row.value }}</td></tr></tbody></table></div>
        </div>
        <div class="config-version-group">
          <b>账号经营策略配置</b>
          <div class="detail-note">滚动统计窗口：{{ versionDetail.config.rolling_posts }} 篇</div>
          <div class="table-wrap"><table><thead><tr><th>生命周期阶段</th><th>流量目标</th><th>转化目标</th><th>阶段定义</th></tr></thead><tbody>
            <tr v-for="stage in versionDetail.config.stage_targets" :key="stage.name"><td><b>{{ stage.name }}</b></td><td>{{ stage.traffic }}%</td><td>{{ stage.conversion }}%</td><td>{{ lifecycleRuleSummary(versionDetail.config.lifecycle_rules.find(rule => rule.name === stage.name) ?? { name: stage.name, conditions: [], catchAll: true }) }}</td></tr>
          </tbody></table></div>
        </div>
      </div>
      <div class="drawer-foot"><button class="btn" type="button" @click="versionDetail = null">关闭</button></div>
    </aside>
  </div>
  <div v-if="confirmation" class="app-confirm-mask" @click.self="closeConfirmation(false)" @keyup.esc.window="closeConfirmation(false)">
    <section class="app-confirm" role="alertdialog" aria-modal="true" aria-labelledby="app-confirm-title" aria-describedby="app-confirm-description">
      <div class="app-confirm-icon" :class="{ danger: confirmation.danger }" aria-hidden="true">{{ confirmation.danger ? '!' : 'i' }}</div>
      <h2 id="app-confirm-title">{{ confirmation.title }}</h2>
      <p id="app-confirm-description">{{ confirmation.message }}</p>
      <div class="app-confirm-actions"><button class="btn" type="button" @click="closeConfirmation(false)">{{ confirmation.cancelLabel }}</button><button :class="['btn', confirmation.danger ? 'app-confirm-danger' : 'primary']" type="button" @click="closeConfirmation(true)">{{ confirmation.confirmLabel }}</button></div>
    </section>
  </div>
</template>

<style scoped>
.app-confirm-mask{position:fixed;inset:0;z-index:80;display:grid;place-items:center;padding:20px;background:rgba(11,30,56,.46);backdrop-filter:blur(2px)}
.app-confirm{width:min(420px,100%);padding:26px 28px 22px;border:1px solid #e7ebf2;border-radius:14px;background:#fff;box-shadow:0 20px 60px rgba(18,34,61,.22);text-align:center;animation:app-confirm-in .16s ease-out}
.app-confirm-icon{display:grid;place-items:center;width:42px;height:42px;margin:0 auto 14px;border:1px solid #c8e0ff;border-radius:50%;background:#f2f7ff;color:#1677ff;font-size:21px;font-weight:750}
.app-confirm-icon.danger{border-color:#f4d9a8;background:#fff8e9;color:#c98213;font-size:23px}
.app-confirm h2{margin:0;color:#17233d;font-size:18px;line-height:1.4}
.app-confirm p{margin:9px 0 24px;color:#66738a;font-size:13px;line-height:1.7}
.app-confirm-actions{display:flex;justify-content:center;gap:10px}
.app-confirm-actions .btn{min-width:112px}
.app-confirm-danger{border-color:#d94145;background:#d94145;color:#fff}
.app-confirm-danger:hover{border-color:#bd3035;background:#bd3035}
@keyframes app-confirm-in{from{opacity:0;transform:translateY(5px) scale(.985)}to{opacity:1;transform:translateY(0) scale(1)}}
</style>

