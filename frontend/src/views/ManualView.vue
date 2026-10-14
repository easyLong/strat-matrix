<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { usePlanningStore } from '../store'
import type { AccountOption, ManualTaskSummary, TopicOption } from '../types'

const store = usePlanningStore()
const router = useRouter()
const tomorrow = new Date()
tomorrow.setDate(tomorrow.getDate() + 1)
const publishDate = ref(`${tomorrow.getFullYear()}-${String(tomorrow.getMonth() + 1).padStart(2, '0')}-${String(tomorrow.getDate()).padStart(2, '0')}`)
const targetCount = ref(30)
const followerRange = ref('')
const platformFilter = ref('')
const accountKeyword = ref('')
const cityFilter = ref('')
const personaFilter = ref('')
const marketingFilter = ref('')
const statusFilter = ref('')
const trendFilter = ref('')
const certifiedFilter = ref('')
const followersMin = ref<number | null>(null)
const followersMax = ref<number | null>(null)
const queried = ref(true)
const sampledIds = ref<string[]>([])
const topicQuery = ref('')
const contentType = ref('')
const selectedTopicIds = ref<string[]>([])
const accounts = ref<AccountOption[]>([])
const topics = ref<TopicOption[]>([])
const note = ref('')
const busy = ref(false)
const error = ref('')
const notice = ref('')
const topicSelectorOpen = ref(false)
const topicDraftIds = ref<string[]>([])

const followerBounds = computed(() => {
  switch (followerRange.value) {
    case 'lt1k': return { min: null, max: 999 }
    case '1k_10k': return { min: 1000, max: 9999 }
    case '10k_100k': return { min: 10000, max: 99999 }
    case '100k_500k': return { min: 100000, max: 499999 }
    case 'gte500k': return { min: 500000, max: null }
    default: return { min: followersMin.value, max: followersMax.value }
  }
})

const eligibleAccounts = computed(() => accounts.value.filter(account =>
  (!accountKeyword.value.trim() || `${account.account_id} ${account.account_name} ${account.account_alias}`.toLowerCase().includes(accountKeyword.value.trim().toLowerCase())) &&
  (!cityFilter.value || account.city === cityFilter.value) &&
  (!personaFilter.value || account.persona === personaFilter.value) &&
  (!marketingFilter.value || account.marketing_eligible === (marketingFilter.value === 'yes')) &&
  (!statusFilter.value || account.status === statusFilter.value) &&
  (!trendFilter.value || account.traffic_trend === trendFilter.value) &&
  (certifiedFilter.value === '' || account.certified === (certifiedFilter.value === 'yes')) &&
  (followerBounds.value.min === null || (account.followers !== null && account.followers >= followerBounds.value.min)) &&
  (followerBounds.value.max === null || (account.followers !== null && account.followers <= followerBounds.value.max)),
))
const cityOptions = computed(() => [...new Set(accounts.value.map(account => account.city).filter(Boolean))])
const personaOptions = computed(() => [...new Set(accounts.value.map(account => account.persona).filter(Boolean))])
const trendOptions = computed(() => ['上升', '平稳', '下滑', '数据不足'])
const statusOptions = computed(() => [...new Set(accounts.value.map(account => account.status).filter(Boolean))])
const shortfall = computed(() => Math.max(0, targetCount.value - eligibleAccounts.value.length))
const selectionReady = computed(() => sampledIds.value.length === targetCount.value)
const sampledAccounts = computed(() => sampledIds.value.map(id => accounts.value.find(account => account.account_id === id)).filter((account): account is AccountOption => !!account))
const contentTypes = computed(() => [...new Set(topics.value.map(topic => topic.content_type).filter(Boolean))])
const filteredTopics = computed(() => topics.value.filter(topic =>
  (!topicQuery.value.trim() || topic.topic_title.includes(topicQuery.value.trim())) &&
  (!contentType.value || topic.content_type === contentType.value),
))
const tasks = ref<ManualTaskSummary[]>([])
let refreshTimer: number | undefined

watch([publishDate, targetCount, followerRange, platformFilter, accountKeyword, cityFilter, personaFilter, marketingFilter, statusFilter, trendFilter, certifiedFilter, followersMin, followersMax], () => {
  queried.value = false
  sampledIds.value = []
})

async function loadCatalog() {
  try {
    const [loadedAccounts, loadedTopics] = await Promise.all([api.accounts(), api.topics()])
    accounts.value = loadedAccounts
    topics.value = loadedTopics
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '读取账号和选题失败' }
}
async function loadTasks() {
  try { tasks.value = await api.manualTasks() }
  catch (exc) { error.value = exc instanceof Error ? exc.message : '读取手动任务失败' }
}
watch(() => store.databaseReady, ready => { if (ready) void loadCatalog() }, { immediate: true })
watch(() => store.databaseReady, ready => { if (ready) void loadTasks() }, { immediate: true })
onMounted(() => { refreshTimer = window.setInterval(() => { if (store.databaseReady && tasks.value.some(task => task.status === '执行中')) void loadTasks() }, 2000) })
onBeforeUnmount(() => { if (refreshTimer !== undefined) window.clearInterval(refreshTimer) })

function queryAccounts() {
  error.value = ''
  if (!Number.isInteger(targetCount.value) || targetCount.value < 1 || targetCount.value > 1000) {
    error.value = '本次规划数量应为 1–1000 的整数'
    return
  }
  if (followerBounds.value.min !== null && followerBounds.value.max !== null && followerBounds.value.min > followerBounds.value.max) {
    error.value = '粉丝量下限不能大于上限'
    return
  }
  queried.value = true
  sampledIds.value = []
}

function randomAccounts() {
  if (!queried.value || shortfall.value > 0) return
  const pool = eligibleAccounts.value.map(account => account.account_id)
  for (let index = pool.length - 1; index > 0; index--) {
    const value = new Uint32Array(1)
    crypto.getRandomValues(value)
    const other = value[0] % (index + 1)
    ;[pool[index], pool[other]] = [pool[other], pool[index]]
  }
  sampledIds.value = pool.slice(0, targetCount.value)
  notice.value = `已从 ${eligibleAccounts.value.length} 个符合条件的账号中随机抽取 ${sampledIds.value.length} 个`
}

function toggleSampledAccount(accountId: string, event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  if (checked) {
    if (sampledIds.value.length < targetCount.value && !sampledIds.value.includes(accountId)) {
      sampledIds.value = [...sampledIds.value, accountId]
    }
  } else {
    sampledIds.value = sampledIds.value.filter(id => id !== accountId)
  }
}

function openTopicSelector() {
  topicDraftIds.value = [...selectedTopicIds.value]
  topicSelectorOpen.value = true
}

function confirmTopicSelector() {
  selectedTopicIds.value = [...topicDraftIds.value]
  topicSelectorOpen.value = false
}

function closeTopicSelector() {
  topicSelectorOpen.value = false
}

async function submit() {
  if (!store.databaseReady || !queried.value || !selectionReady.value || !selectedTopicIds.value.length || !publishDate.value || shortfall.value > 0 || busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const preview = await api.previewManual({
      publish_date: publishDate.value,
      account_ids: sampledIds.value,
      topic_ids: selectedTopicIds.value,
      note: note.value.trim(),
      certified: certifiedFilter.value ? certifiedFilter.value === 'yes' : null,
      followers_min: followerBounds.value.min,
      followers_max: followerBounds.value.max,
      city: cityFilter.value || undefined,
      persona: personaFilter.value || undefined,
      keyword: accountKeyword.value.trim() || undefined,
      traffic_trend: trendFilter.value || undefined,
    })
    const task = await api.submitManualPreview(preview.preview_id)
    tasks.value = [task, ...tasks.value.filter(existing => existing.id !== task.id)]
    notice.value = '手动策划已提交，当前状态：进行中'
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '发起手动策划失败' }
  finally { busy.value = false }
}

function taskStatusLabel(status: string) {
  return status === '执行中' ? '进行中' : status
}

function taskStatusClass(status: string) {
  return status.includes('失败') ? 'red' : status === '执行中' || status === '进行中' ? 'orange' : 'green'
}
</script>

<template>
  <div class="page-head"><div><h1>手动策划</h1></div></div>
  <div v-if="error" class="banner error-banner" role="alert">{{ error }}</div>
  <div v-if="notice" class="banner success-banner" role="status">{{ notice }}</div>

  <section class="card">
    <div class="card-head"><div><h2>1. 本次策划规划数量</h2></div></div>
    <div class="card-body">
      <div class="manual-quantity-row">
        <label class="field"><span>计划账号数量 <em>*</em></span><div class="number-control"><button class="btn" type="button" @click="targetCount = Math.max(1, targetCount - 1)">−</button><input v-model.number="targetCount" type="number" min="1" max="1000" /><button class="btn" type="button" @click="targetCount = Math.min(1000, targetCount + 1)">＋</button></div></label>
        <span class="unit">个账号</span>
      </div>
    </div>
  </section>

  <section class="card">
    <div class="card-head"><div><h2>2. 筛选账号</h2></div><button class="btn" type="button" @click="certifiedFilter = ''; followerRange = ''; trendFilter = ''; queried = false; sampledIds = []">重置筛选</button></div>
    <div class="card-body">
      <div class="manual-filter-grid">
        <label class="field"><span>投放日期 <em>*</em></span><input v-model="publishDate" type="date" /></label>
        <label class="field"><span>认证状态</span><select v-model="certifiedFilter"><option value="">全部</option><option value="yes">已认证</option><option value="no">未认证</option></select></label>
        <label class="field"><span>粉丝量</span><select v-model="followerRange"><option value="">全部</option><option value="lt1k">千粉以下</option><option value="1k_10k">1千–1万</option><option value="10k_100k">1万–10万</option><option value="100k_500k">10万–50万</option><option value="gte500k">50万以上</option></select></label>
        <label class="field"><span>流量趋势</span><select v-model="trendFilter"><option value="">全部</option><option v-for="value in trendOptions" :key="value" :value="value">{{ value }}</option></select></label>
        <div class="manual-filter-action"><button class="btn primary" type="button" :disabled="busy || !store.databaseReady || !publishDate" @click="queryAccounts">查询账号</button></div>
      </div>
      <div v-if="queried" class="selection-summary manual-selection-summary">
        <div class="manual-summary-stat"><span>筛选命中</span><b>{{ eligibleAccounts.length }} <small>个账号</small></b></div>
        <div class="manual-summary-stat"><span>规划数量</span><b>{{ targetCount }} <small>个账号</small></b></div>
        <div :class="['manual-summary-stat', shortfall > 0 ? 'danger' : 'success']"><span>数量状态</span><b>{{ shortfall > 0 ? `还差 ${shortfall} 个` : '数量充足' }}</b></div>
        <div class="manual-summary-stat"><span>当前已选</span><b>{{ sampledIds.length }} <small>/ {{ targetCount }}</small></b></div>
        <button class="btn primary manual-random-button" type="button" :disabled="busy || shortfall > 0" @click="randomAccounts">{{ sampledIds.length ? '重新随机选取' : '随机选取' }} {{ targetCount }} 个</button>
      </div>
      <p v-if="queried && shortfall > 0" class="inline-error">筛选账号不足，还差 {{ shortfall }} 个，请调整筛选条件或规划数量。</p>
      <div v-if="queried" class="manual-account-list-head"><b>筛选结果</b><span>已选 {{ sampledIds.length }} / {{ targetCount }} 个账号</span></div>
      <div v-if="queried" class="table-wrap manual-account-table"><table><thead><tr><th></th><th>账号</th><th>认证状态</th><th>粉丝量</th><th>流量趋势</th><th>本次投放日期</th></tr></thead><tbody><tr v-for="account in eligibleAccounts" :key="account.account_id"><td><input type="checkbox" :checked="sampledIds.includes(account.account_id)" :disabled="busy || (!sampledIds.includes(account.account_id) && sampledIds.length >= targetCount)" @change="toggleSampledAccount(account.account_id, $event)" /></td><td><b>{{ account.account_name }}</b><small>{{ account.account_alias ? `${account.account_alias} · ` : '' }}{{ account.account_id }}</small></td><td><span :class="['tag', account.certified ? 'blue' : 'gray']">{{ account.certified ? '已认证' : '未认证' }}</span></td><td>{{ account.followers ?? '—' }}</td><td>{{ account.traffic_trend || '—' }}</td><td><span class="tag blue">{{ publishDate }}</span></td></tr><tr v-if="eligibleAccounts.length === 0"><td colspan="6"><div class="empty-state">当前筛选条件下暂无账号</div></td></tr></tbody></table></div>
    </div>
  </section>

  <section class="card">
    <div class="card-head"><div><div class="card-title"><h2>3. 选择选题</h2></div></div><button class="btn primary" type="button" @click="openTopicSelector">＋ 选择选题</button></div>
    <div class="card-body">
      <div class="topic-selection-summary"><div><b>已选 {{ selectedTopicIds.length }} 个选题</b></div><button class="btn" type="button" :disabled="!selectedTopicIds.length" @click="selectedTopicIds = []">清空已选</button></div>
      <div v-if="selectedTopicIds.length" class="topic-picked"><div v-for="topicId in selectedTopicIds" :key="topicId" class="topic-pick-card"><span class="tag blue">{{ topics.find(topic => topic.topic_id === topicId)?.content_type || '选题' }}</span><div><b>{{ topics.find(topic => topic.topic_id === topicId)?.topic_title || topicId }}</b><small>{{ topics.find(topic => topic.topic_id === topicId)?.outline || '暂无选题大纲' }}</small></div><button class="remove-topic" type="button" title="移除" @click="selectedTopicIds = selectedTopicIds.filter(id => id !== topicId)">×</button></div></div>
      <div v-else class="empty-state">尚未选择选题，请点击“选择选题”。</div>
    </div>
  </section>

  <section class="card">
    <div class="card-body">
      <label class="field manual-note-field"><span>备注（可选）</span><input v-model="note" type="text" maxlength="500" /></label>
      <div class="footer-actions"><button class="btn primary" type="button" :disabled="busy || !store.databaseReady || !queried || !selectionReady || shortfall > 0 || !selectedTopicIds.length || !publishDate" @click="submit">{{ busy ? '正在提交…' : '生成手动策划' }}</button></div>
    </div>
  </section>

  <section class="card">
    <div class="card-head"><div><h2>最近手动策划任务</h2></div><button class="btn" type="button" :disabled="busy || !store.databaseReady" @click="loadTasks">刷新任务</button></div>
    <div class="table-wrap"><table><thead><tr><th>发起时间</th><th>操作人</th><th>投放日期</th><th>规划账号数</th><th>成功结果</th><th>失败结果</th><th>选题数</th><th>状态</th><th>最后更新时间</th><th>操作</th></tr></thead><tbody><tr v-for="task in tasks" :key="task.id"><td>{{ task.created_at }}</td><td>{{ task.created_by }}</td><td>{{ task.publish_date }}</td><td>{{ task.planned_account_count }}</td><td>{{ task.result_count }}</td><td>{{ task.failure_count }}</td><td>{{ task.topic_count }}</td><td><span :class="['tag', taskStatusClass(task.status)]">{{ taskStatusLabel(task.status) }}</span><small v-if="task.failure_reason">{{ task.failure_reason }}</small></td><td>{{ task.updated_at }}</td><td><button v-if="task.batch_id" class="text-btn" type="button" @click="router.push({ path: '/results', query: { batch: String(task.batch_id), plan_type: 'manual' } })">查看结果</button><span v-else>—</span></td></tr><tr v-if="tasks.length === 0"><td colspan="10"><div class="empty-state">暂无手动策划任务</div></td></tr></tbody></table></div>
  </section>

  <div v-if="topicSelectorOpen" class="drawer-mask show" @click.self="closeTopicSelector"><div class="drawer topic-selector-modal"><div class="drawer-head"><div><div class="drawer-title">选择选题</div></div><button class="drawer-close" type="button" @click="closeTopicSelector">×</button></div><div class="drawer-body"><div class="catalog-filters"><input v-model="topicQuery" type="search" /><select v-model="contentType"><option value="">全部内容类型</option><option v-for="value in contentTypes" :key="value" :value="value">{{ value }}</option></select></div><div class="topic-result-meta"><span>搜索结果 <b>{{ filteredTopics.length }}</b> 个</span><span class="muted">已选择 <b>{{ topicDraftIds.length }}</b> 个</span></div><div class="topic-selector-list"><label v-for="topic in filteredTopics" :key="topic.topic_id" class="topic-check"><input v-model="topicDraftIds" type="checkbox" :value="topic.topic_id" /><span><b>{{ topic.topic_title }}</b><small>{{ topic.content_type || '暂无内容类型' }}<template v-if="topic.outline"> · {{ topic.outline }}</template></small></span></label><div v-if="filteredTopics.length === 0" class="empty-state">没有符合条件的可用选题</div></div></div><div class="drawer-foot"><button class="btn" type="button" @click="closeTopicSelector">取消</button><button class="btn primary" type="button" @click="confirmTopicSelector">确认选择</button></div></div></div>
</template>
