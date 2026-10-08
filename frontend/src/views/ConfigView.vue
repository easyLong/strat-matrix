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
const versions = ref<Record<'marketing' | 'strategy', ConfigVersionSummary[]>>({ marketing: [], strategy: [] })
const activeModule = ref<'marketing' | 'strategy'>('marketing')
const moduleNames = { marketing: '营销配置', strategy: '经营策略' }
const dirty = computed(() => JSON.stringify(draft.value) !== JSON.stringify(store.config))
const marketingFields = (config: StrategyConfig) => ({
  marketing_max: config.marketing_max,
  planning_days: config.planning_days,
  schedule_day: config.schedule_day,
  schedule_time: config.schedule_time,
  hotspot_ratio: config.hotspot_ratio,
})
const strategyFields = (config: StrategyConfig) => ({
  rolling_posts: config.rolling_posts,
  stage_targets: config.stage_targets,
  lifecycle_rules: config.lifecycle_rules,
})
const marketingDirty = computed(() => JSON.stringify(marketingFields(draft.value)) !== JSON.stringify(marketingFields(store.config)))
const strategyDirty = computed(() => JSON.stringify(strategyFields(draft.value)) !== JSON.stringify(strategyFields(store.config)))
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
const planningDays = computed(() => draft.value.planning_days)
const scheduleDay = computed({ get: () => draft.value.schedule_day, set: value => { draft.value.schedule_day = value } })
const scheduleTime = computed({ get: () => draft.value.schedule_time, set: value => { draft.value.schedule_time = value } })
const hotspotRatio = computed({ get: () => draft.value.hotspot_ratio, set: value => { draft.value.hotspot_ratio = value } })
const lifecycleEditing = ref(false)
const lifecycleRules = computed(() => draft.value.lifecycle_rules)
const lifecycleMetricOptions = [
  { value: 'valid_content_count', label: '有效内容数', unit: '篇' },
  { value: 'rolling_interaction_count', label: '滚动周期内互动数', unit: '次' },
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

function metricUnit(field: string) {
  return lifecycleMetricOptions.find(option => option.value === field)?.unit ?? ''
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
  if (!pageDirty.value) return
  event.preventDefault()
  event.returnValue = '当前存在未保存修改，离开后修改内容将丢失。'
}
onMounted(() => {
  window.addEventListener('beforeunload', beforeUnload)
  removeRouteGuard = router.beforeEach((to, from) => {
    if (to.fullPath === from.fullPath || !pageDirty.value) return true
    return window.confirm('当前存在未保存修改，离开后修改内容将丢失。点击“确定”放弃修改并离开，点击“取消”继续编辑。')
  })
})
onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', beforeUnload)
  removeRouteGuard?.()
})

async function loadVersions() {
  try {
    const [marketing, strategy] = await Promise.all([
      api.configModuleVersions('marketing'), api.configModuleVersions('strategy'),
    ])
    versions.value = { marketing, strategy }
  }
  catch (exc) { error.value = exc instanceof Error ? exc.message : '读取配置历史失败' }
}

async function loadConfigData() {
  loading.value = true
  error.value = ''
  try {
    await Promise.all([store.refreshConfig(), loadVersions(), loadTagTaxonomy()])
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
    for (const code of Object.keys(tagNames)) {
      tagItems.value[code] = loaded.items[code]?.length
        ? loaded.items[code].map(item => ({ ...item }))
        : (prototypeTags[code] ?? []).map(name => ({ id: null, name, enabled: true }))
    }
    tagBaseline.value = JSON.stringify(Object.fromEntries(
      Object.keys(tagNames).map(code => [code, loaded.items[code] ?? []]),
    ))
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

async function saveTagTaxonomy() {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const saved = await api.saveTagTaxonomy(tagItems.value, tagVersion.value)
    tagVersion.value = saved.version
    tagItems.value = saved.items
    tagBaseline.value = JSON.stringify(tagItems.value)
    localStorage.removeItem('strat-matrix.config-ui')
    notice.value = `T1–T5 标签配置已保存为 V${saved.version}，选题库同步事件已进入待投递队列`
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '保存标签配置失败' }
  finally { busy.value = false }
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
  draft.value = cloneConfig(store.config)
  notice.value = '已恢复到当前保存的配置'
  error.value = ''
}

async function save(module: 'marketing' | 'strategy') {
  if (!store.databaseReady || !(module === 'marketing' ? marketingValid.value && marketingDirty.value : strategyValid.value && strategyDirty.value)) return
  const otherModuleDraft = cloneConfig(draft.value)
  const payload = cloneConfig(store.config)
  Object.assign(payload, module === 'marketing' ? marketingFields(draft.value) : strategyFields(draft.value))
  busy.value = true
  notice.value = ''
  error.value = ''
  try {
    await store.saveConfigModule(module, payload)
    if (module === 'marketing') {
      draft.value.rolling_posts = otherModuleDraft.rolling_posts
      draft.value.stage_targets = otherModuleDraft.stage_targets
      draft.value.lifecycle_rules = otherModuleDraft.lifecycle_rules
    } else {
      draft.value.marketing_max = otherModuleDraft.marketing_max
      draft.value.planning_days = otherModuleDraft.planning_days
      draft.value.schedule_day = otherModuleDraft.schedule_day
      draft.value.schedule_time = otherModuleDraft.schedule_time
      draft.value.hotspot_ratio = otherModuleDraft.hotspot_ratio
    }
    await loadVersions()
    notice.value = `${moduleNames[module]}已保存为新版本`
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '保存失败'
  } finally {
    busy.value = false
  }
}

async function restoreVersion(version: number) {
  if (!window.confirm(`仅恢复${moduleNames[activeModule.value]} V${version}，并创建该模块新版本？`)) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await store.restoreConfigModule(activeModule.value, version)
    await loadVersions()
    notice.value = `${moduleNames[activeModule.value]}已基于 V${version} 创建新版本，其他模块未改变`
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '恢复失败'
  } finally { busy.value = false }
}

</script>

<template>
  <div class="page-head">
    <div><h1>策划配置</h1><p>维护运营规则与生命周期经营目标；账号阶段由系统识别。</p></div>
    <div class="page-actions">
      <button class="btn" type="button" :disabled="loading || busy || !store.databaseReady" @click="loadConfigData">刷新配置</button>
      <button class="btn" type="button" :disabled="busy || !store.databaseReady" @click="restore">恢复当前配置</button>
    </div>
  </div>

  <div v-if="notice" class="banner success-banner" role="status">{{ notice }}</div>
  <div v-if="error" class="banner error-banner" role="alert">{{ error }}</div>
  <div v-if="store.configIsDemo" class="banner info-banner"><b>演示配置：</b>当前数值由示例数据填充。分别保存营销配置或经营策略后，所选模块会生成正式版本。</div>
  <div v-if="loading" class="banner info-banner" role="status">正在读取当前策划配置…</div>
  <fieldset class="form-fieldset config-stack" :disabled="!store.databaseReady || busy">
    <section class="card">
      <div class="card-head"><div><h2>账号与自动策划配置</h2><small>控制每周槽位、自动执行时间和特殊内容比例</small></div><span class="tag blue">运营可配置</span></div>
      <div class="card-body">
        <div class="form-grid config-control-grid">
          <div class="field"><span>每周策划日</span><div class="day-picker"><button v-for="day in [{ n: 1, label: '周一' }, { n: 2, label: '周二' }, { n: 3, label: '周三' }, { n: 4, label: '周四' }, { n: 5, label: '周五' }, { n: 6, label: '周六' }, { n: 7, label: '周日' }]" :key="day.n" class="day-chip" :class="{ active: planningDays.includes(day.n) }" type="button" @click="togglePlanningDay(day.n)">{{ day.label }}</button></div><small>每选择 1 天，代表每个符合条件账号每周生成 1 个自动策划槽位；至少选择 1 天。</small></div>
          <label class="field"><span>自动策划调度时间</span><div class="schedule-picker"><select v-model.number="scheduleDay"><option :value="1">周一</option><option :value="2">周二</option><option :value="3">周三</option><option :value="4">周四</option><option :value="5">周五</option><option :value="6">周六</option><option :value="7">周日</option></select><input v-model="scheduleTime" type="time" /></div><small>全局仅 1 个周度触发点，默认每周二 22:00，统一使用国内时间。</small></label>
          <label class="field"><span>营销内容周上限</span><div class="input-unit"><input v-model.number="draft.marketing_max" type="number" min="0" /><span>条 / 营销账号 / 周</span></div><small>0 表示本周期不安排营销内容；实际数量不超过可执行槽位数。</small></label>
          <label class="field"><span>热点槽位占比</span><div class="input-unit"><input v-model.number="hotspotRatio" type="number" min="0" max="100" /><span>%</span></div><small>仅决定批次预规划热点槽位数量，不提前锁定具体热点选题。</small></label>
        </div>
        <div class="banner info-banner"><b>热点槽位：</b>自动策划时按占比提前规划，具体热点选题在目标槽位前一天 22:00 确定。</div>
        <p v-if="!marketingValid" class="inline-error">请检查每周策划日、调度时间、营销上限和热点占比。</p>
        <div class="footer-actions"><span class="form-note">当前：每周 {{ planningDays.length }} 个槽位 / 账号 · {{ ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][scheduleDay - 1] }} {{ scheduleTime }}</span><button class="btn primary" type="button" :disabled="busy || !store.databaseReady || !marketingValid || !marketingDirty" @click="save('marketing')">保存账号配置</button></div>
      </div>
    </section>

    <section class="card">
      <div class="card-head"><div><h2>经营策略配置</h2><small>五个生命周期阶段的流量与转化目标</small></div><span class="tag blue">运营可配置</span></div>
      <div class="card-body">
        <label class="field rolling-field"><span>滚动统计窗口</span><div class="input-unit"><input v-model.number="draft.rolling_posts" type="number" min="1" max="100" /><span>篇</span></div><small>阶段目标按最近的有效内容滚动计算。</small></label>
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
        <div class="lifecycle-definition-head"><div><b>生命周期阶段定义</b><small>使用有效内容数、滚动周期互动数和粉丝数等可量化指标；按成熟度从高到低匹配，命中第一个阶段后停止。</small></div><button class="btn small" type="button" @click="lifecycleEditing = !lifecycleEditing">{{ lifecycleEditing ? '完成编辑' : '编辑定义' }}</button></div>
        <div class="banner info-banner lifecycle-coverage-note"><b>唯一归属规则：</b>一个账号只允许归属一个阶段。前四个阶段按条件匹配，未命中时归入“冷启验证期”。</div>
        <div class="lifecycle-definition-list"><div v-for="rule in lifecycleRules" :key="rule.name" class="lifecycle-definition"><div class="lifecycle-stage-name"><b>{{ rule.name }}</b><small>{{ rule.catchAll ? '兜底阶段' : '进入条件' }}</small></div><div v-if="rule.catchAll" class="lifecycle-catch-all">未命中前置阶段条件的账号自动归入此阶段，确保每个账号都有且只有一个生命周期阶段。</div><div v-else class="lifecycle-condition-list"><div v-for="(condition, index) in rule.conditions" :key="`${rule.name}-${index}`" class="lifecycle-condition-row"><select v-model="condition.field" :disabled="!lifecycleEditing" aria-label="指标"><option v-for="option in lifecycleMetricOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select><select v-model="condition.operator" :disabled="!lifecycleEditing" aria-label="运算符"><option v-for="option in lifecycleOperatorOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select><input v-model.number="condition.value" :disabled="!lifecycleEditing" type="number" step="1" aria-label="阈值" /><span class="condition-unit">{{ metricUnit(condition.field) }}</span><select v-if="index > 0" v-model="condition.join" :disabled="!lifecycleEditing" class="condition-join" aria-label="条件关系"><option value="AND">且</option><option value="OR">或</option></select><button v-if="lifecycleEditing && rule.conditions.length > 1" class="icon-btn condition-remove" type="button" aria-label="删除条件" @click="removeLifecycleCondition(rule, index)">×</button></div><button v-if="lifecycleEditing" class="text-btn condition-add" type="button" @click="addLifecycleCondition(rule)">＋ 添加条件</button></div></div></div>
        <p v-if="!strategyValid" class="inline-error">请检查滚动窗口、生命周期进入条件；每个阶段的流量与转化目标之和必须为 100%。</p>
        <div class="footer-actions"><button class="btn primary" type="button" :disabled="busy || !store.databaseReady || !strategyValid || !strategyDirty" @click="save('strategy')">保存经营策略</button></div>
      </div>
    </section>
  </fieldset>
  <section class="card">
    <div class="card-head"><div><h2>多维标签配置 <button class="help-btn" type="button" title="T1–T5 为运营维护字典，T6 用户需求由模型单选识别">?</button></h2><small>T1–T5 固定字典单选 · 当前 V{{ tagVersion }}；历史已引用标签停用后仅影响后续新识别。</small></div><div class="page-actions"><button class="btn small" type="button" :disabled="busy || activeTag === 'T6' || !store.databaseReady" @click="tagAddOpen = !tagAddOpen">{{ tagAddOpen ? '取消新增' : '新增标签' }}</button><button class="btn small primary" type="button" :disabled="busy || !store.databaseReady || !tagDirty" @click="saveTagTaxonomy">保存标签配置</button></div></div>
    <div class="tag-tabs" role="tablist"><button v-for="code in tagTabs" :key="code" class="tag-tab" :class="{ active: activeTag === code }" type="button" role="tab" :aria-selected="activeTag === code" @click="activeTag = code">{{ code }} {{ code === 'T1' ? '业务属性' : code === 'T2' ? '经营作用' : code === 'T3' ? '主题域' : code === 'T4' ? '目标客群' : code === 'T5' ? '生活场景' : '用户需求' }}</button></div>
    <div class="card-body tag-content">
      <template v-if="activeTag !== 'T6'">
        <div class="tag-content-head"><div><b>{{ activeTag }} {{ tagNames[activeTag] }}</b><small>{{ tagDescriptions[activeTag] }}</small></div><span class="tag blue">单选字典</span></div>
        <div class="tag-pills"><div v-for="tag in getTagItems(activeTag)" :key="tag.id ?? tag.name" class="pill-edit" :class="{ disabled: !tag.enabled }"><span>{{ tag.name }}</span><button class="mini" type="button" @click="renameTag(activeTag, tag)">改名</button><button class="mini" type="button" @click="toggleTagDisabled(activeTag, tag)">{{ tag.enabled ? '停用' : '启用' }}</button></div><span v-if="getTagItems(activeTag).length === 0" class="taxonomy-empty">暂无标签，请添加</span></div>
        <div v-if="tagAddOpen" class="taxonomy-add inline-add"><input v-model="newTagInputs[activeTag]" class="field-input" type="text" :placeholder="`添加${tagNames[activeTag]}标签`" @keyup.enter.prevent="addTag(activeTag)" /><button class="btn" type="button" :disabled="!newTagInputs[activeTag]?.trim()" @click="addTag(activeTag)">＋ 添加标签</button></div>
        <p class="hint">标签内部 ID 在改名时保持稳定；停用不会物理删除历史标签，仅影响后续新增选题的标签识别。</p>
      </template>
      <div v-else class="banner info-banner tag-t6-note"><span class="ai-mark">AI</span><div><b>T6 用户需求由模型单选识别</b><br />新增选题首次离线标签计算时执行：优先复用与已有 T6 相似度 &gt; 80% 的标签，否则自动新增。运营在本页不直接编辑 T6。</div></div>
    </div>
  </section>
  <section class="card">
    <div class="card-head"><div><h2>配置快照</h2><small>按模块查看历史，恢复只影响当前选择的模块</small></div><div class="tab-switch"><button type="button" :class="{ active: activeModule === 'marketing' }" @click="activeModule = 'marketing'">账号配置</button><button type="button" :class="{ active: activeModule === 'strategy' }" @click="activeModule = 'strategy'">经营策略</button></div></div>
    <div class="table-wrap"><table><thead><tr><th>版本</th><th>生成时间</th><th>配置摘要</th><th>动作</th><th>操作人</th><th>操作</th></tr></thead><tbody>
      <tr v-for="version in versions[activeModule]" :key="version.version"><td><b>V{{ version.version }}</b><span v-if="version.version === versions[activeModule][0]?.version" class="tag green row-tag">当前</span></td><td>{{ version.created_at }}</td><td>{{ activeModule === 'marketing' ? `每周 ${version.config.planning_days.length} 天 · 调度周${['一', '二', '三', '四', '五', '六', '日'][version.config.schedule_day - 1]} ${version.config.schedule_time} · 营销上限 ${version.config.marketing_max} · 热点 ${version.config.hotspot_ratio}%` : `滚动 ${version.config.rolling_posts} 篇 · 五阶段目标与定义` }}</td><td>{{ version.action }}<small v-if="version.source_version">来自 V{{ version.source_version }}</small></td><td>{{ version.created_by }}</td><td><button class="text-btn" type="button" :disabled="busy || version.version === versions[activeModule][0]?.version" @click="restoreVersion(version.version)">恢复此版本</button></td></tr>
      <tr v-if="versions[activeModule].length === 0"><td colspan="6"><div class="empty-state">暂无该模块的配置记录</div></td></tr>
    </tbody></table></div>
  </section>
  <p class="page-footnote">当前有效配置组合版本：V{{ store.configVersion }}<span v-if="store.configUpdatedAt"> · 更新时间：{{ store.configUpdatedAt }}</span>。新批次读取保存后的配置；历史批次维持原结果。</p>
</template>

