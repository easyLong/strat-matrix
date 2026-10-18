<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { usePlanningStore } from '../store'
import type { AutoCycleSummary, AutoFailure } from '../types'
import { addCalendarDays, businessMonday, formatBusinessTime, formatDateTime, weeklyTrigger } from '../planningTime'

const store = usePlanningStore()
const router = useRouter()
const busy = ref(false)
const error = ref('')
const exceptionDetails = ref<AutoFailure[]>([])
const exceptionReadError = ref('')
const historicalExceptionCycle = ref<AutoCycleSummary | null>(null)
const historicalExceptionDetails = ref<AutoFailure[]>([])
const historicalExceptionReadError = ref('')
const historicalExceptionBusy = ref(false)
const cycles = ref<AutoCycleSummary[]>([])
const now = ref(Date.now())
const currentMonday = computed(() => businessMonday(now.value))
const historyYear = ref('all')
const historyMonth = ref('all')
const autoBatches = computed(() => store.batches.filter(batch => batch.plan_type === 'auto'))
const latest = computed(() => {
  const ordered = [...cycles.value].sort((a, b) => b.cycle_start.localeCompare(a.cycle_start))
  return ordered.find(cycle => cycle.cycle_start === currentMonday.value)
    ?? ordered.filter(cycle => cycle.cycle_start > currentMonday.value).at(-1)
    ?? ordered[0]
})
const latestAutoBatch = computed(() => autoBatches.value.find(batch => batch.cycle_start === latest.value?.cycle_id))
const latestCaption = computed(() => {
  if (!latest.value) return '等待首个策划周期'
  if (latest.value.has_execution_exception) return '检测到执行异常，请查看原因和更新时间'
  if (latest.value.cycle_start > currentMonday.value) return '策划已生成，等待进入执行周期'
  if (latest.value.cycle_start < currentMonday.value) return '最近一个已有策划记录的周期'
  if (latest.value.hotspot_pending) return '本周执行中，热点槽位按投放日期逐步填充'
  return '本周所有策划槽位已确定'
})
const upcomingPlan = computed(() => {
  const start = addCalendarDays(currentMonday.value, 7)
  const end = addCalendarDays(start, 6)
  const trigger = weeklyTrigger(currentMonday.value, store.config.schedule_day, store.config.schedule_time)
  const cycle = cycles.value.find(item => item.cycle_start === start)
  return { start, end, cycle, trigger: formatBusinessTime(trigger),
    status: cycle?.has_execution_exception ? '执行异常' : cycle ? '已规划' : now.value < trigger ? '待调度' : '等待策划结果',
    hint: cycle?.has_execution_exception ? '下周批次存在执行异常，请查看异常原因和更新时间。'
      : cycle ? '下周策划已生成，进入执行周期后开始填充热点槽位。'
      : now.value < trigger ? '尚未到调度时间，当前尚未生成下周批次。' : '已到调度时间，尚未收到下周策划结果。' }
})
const hotspotStatus = computed(() => {
  if (!latest.value) return '等待批次规划'
  if (latest.value.hotspot_slots === 0) return '无热点槽位'
  if (latest.value.hotspot_pending > 0) return `待填充 ${latest.value.hotspot_pending} 个`
  return `已提交 ${latest.value.hotspot_submitted} 个`
})
const historyYears = computed(() => [...new Set(cycles.value.map(cycle => cycle.cycle_start.slice(0, 4)))])
const historyMonths = computed(() => [...new Set(cycles.value.filter(cycle => historyYear.value === 'all' || cycle.cycle_start.startsWith(historyYear.value)).map(cycle => cycle.cycle_start.slice(5, 7)))])
const filteredCycles = computed(() => cycles.value.filter(cycle =>
  (historyYear.value === 'all' || cycle.cycle_start.startsWith(historyYear.value)) &&
  (historyMonth.value === 'all' || cycle.cycle_start.slice(5, 7) === historyMonth.value),
))
function openCycle(cycle: AutoCycleSummary) {
  const batch = autoBatches.value.find(item => item.cycle_start === cycle.cycle_id)
  if (batch) void router.push({ path: '/results', query: { batch: String(batch.id) } })
}
async function showCycleExceptions(cycle: AutoCycleSummary) {
  historicalExceptionCycle.value = cycle
  historicalExceptionDetails.value = []
  historicalExceptionReadError.value = ''
  historicalExceptionBusy.value = true
  try {
    const details = await api.autoFailures(cycle.cycle_id)
    if (historicalExceptionCycle.value?.cycle_id === cycle.cycle_id) historicalExceptionDetails.value = details
  }
  catch (exc) {
    if (historicalExceptionCycle.value?.cycle_id === cycle.cycle_id) {
      historicalExceptionReadError.value = exc instanceof Error ? exc.message : '异常原因读取失败'
    }
  }
  finally {
    if (historicalExceptionCycle.value?.cycle_id === cycle.cycle_id) historicalExceptionBusy.value = false
  }
}
function closeCycleExceptions() {
  historicalExceptionCycle.value = null
  historicalExceptionDetails.value = []
  historicalExceptionReadError.value = ''
}
const scheduleSummary = computed(() => {
  const labels = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
  const config = store.config
  const days = latest.value?.planning_days ?? config.planning_days
  const triggerDay = latest.value?.schedule_day ?? config.schedule_day
  const triggerTime = latest.value?.schedule_time ?? config.schedule_time
  return {
    days: days.map(day => labels[day - 1]).join('/'),
    trigger: `${labels[triggerDay - 1]} ${triggerTime}`,
  }
})
let refreshTimer: number | undefined

function statusClass(status: string | null, hasExecutionException = false) {
  if (hasExecutionException) return 'red'
  if (status === '已规划') return 'blue'
  if (status === '热点空槽待填充') return 'orange'
  return status === '已完成' ? 'green' : 'gray'
}

function statusLabel(status: string | null, hasExecutionException = false) {
  if (hasExecutionException) return '执行异常'
  if (status === '已规划' || status === '热点空槽待填充' || status === '已完成') return status
  return '状态待确认'
}

async function refresh() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const [, loaded] = await Promise.all([store.refreshBatches(), api.autoCycles()])
    cycles.value = loaded
    exceptionDetails.value = []
    exceptionReadError.value = ''
    if (latest.value?.has_execution_exception) {
      try { exceptionDetails.value = await api.autoFailures(latest.value.cycle_id) }
      catch (exc) { exceptionReadError.value = exc instanceof Error ? exc.message : '异常原因读取失败' }
    }
  }
  catch (exc) { error.value = exc instanceof Error ? exc.message : '刷新异常' }
  finally { busy.value = false }
}

watch(() => store.databaseReady, ready => { if (ready) void refresh() }, { immediate: true })
onMounted(() => { refreshTimer = window.setInterval(() => {
  now.value = Date.now()
  if (store.databaseReady) void refresh()
}, 10000) })
onBeforeUnmount(() => { if (refreshTimer !== undefined) window.clearInterval(refreshTimer) })
</script>

<template>
  <div class="page-head">
    <div><h1>AI自动策划</h1></div>
  </div>
  <div v-if="error" class="banner error-banner" role="alert">{{ error }}</div>
  <div class="auto-overview-grid">
    <div class="kpi-card"><small>当前策划周期</small><strong class="kpi-text">{{ latest?.cycle_start ?? '暂无' }}</strong><span>{{ latest?.cycle_end ?? '等待首个周期' }}</span></div>
    <div class="kpi-card"><small>参与账号</small><strong>{{ latest?.account_count ?? 0 }}</strong></div>
    <div class="kpi-card"><small>周期状态</small><strong class="kpi-text">{{ latest ? statusLabel(latest.status, latest.has_execution_exception) : '暂无运行记录' }}</strong></div>
    <div class="kpi-card"><small>热点槽位状态</small><strong class="kpi-text">{{ hotspotStatus }}</strong></div>
  </div>

  <section class="card">
    <div class="card-head"><div><h2>下周策划调度</h2><small>{{ upcomingPlan.start }} 至 {{ upcomingPlan.end }}</small></div><span :class="['tag', upcomingPlan.cycle?.has_execution_exception ? 'red' : upcomingPlan.cycle ? 'blue' : 'gray']">{{ upcomingPlan.status }}</span></div>
    <div class="card-body auto-schedule-row"><div><b>{{ upcomingPlan.trigger }}</b></div><button v-if="upcomingPlan.cycle?.has_execution_exception" class="text-btn" type="button" @click="showCycleExceptions(upcomingPlan.cycle)">查看异常</button><button v-else-if="upcomingPlan.cycle" class="text-btn" type="button" @click="openCycle(upcomingPlan.cycle)">查看详情</button></div>
  </section>

  <section class="card">
    <div class="card-head auto-task-head"><div><h2>当前批次</h2></div><div class="auto-state"><span class="pulse" />{{ latest ? statusLabel(latest.status, latest.has_execution_exception) : '等待首个周期' }}</div><button v-if="latest" class="text-btn" type="button" @click="openCycle(latest)">查看详情</button></div>
    <div class="card-body"><div v-if="latest" class="auto-current-grid">
      <div class="summary-box"><div class="summary-row"><span>周度调度</span><b>{{ scheduleSummary.trigger }}</b></div><div class="summary-row"><span>每账号槽位</span><b>{{ scheduleSummary.days.split('/').length }} 个（{{ scheduleSummary.days }}）</b></div><div class="summary-row"><span>热点槽位提交</span><b>{{ hotspotStatus }}</b></div></div>
      <div class="summary-box"><div class="summary-row"><span>总槽位</span><b>{{ latest.regular_slots + latest.marketing_slots + latest.hotspot_slots }} 个</b></div><div class="summary-row"><span>普通槽位</span><b>{{ latest.regular_slots }} 个</b></div><div class="summary-row"><span>营销槽位</span><b>{{ latest.marketing_slots }} 个</b></div></div>
      <div class="summary-box"><div class="summary-row"><span>开始时间</span><b>{{ formatDateTime(latestAutoBatch?.created_at) }}</b></div><div class="summary-row"><span>最后更新</span><b>{{ formatDateTime(latest.updated_at) }}</b></div><div class="summary-row"><span>基础规划完成账号</span><b v-if="latest.has_execution_exception">待核对</b><b v-else>{{ latest.base_planning_complete_accounts }} / {{ latest.account_count }}</b></div><div class="summary-row"><span>全部选题确定账号</span><b v-if="latest.has_execution_exception">待核对</b><b v-else>{{ latest.all_topics_determined_accounts }} / {{ latest.account_count }}</b></div><div class="summary-row"><span>周期状态</span><b>{{ statusLabel(latest.status, latest.has_execution_exception) }}</b></div><div v-if="latest.allocation_method === 'ordinary_fallback' || latest.allocation_method === 'rule_fallback'" class="summary-row"><span>分配方式</span><b>{{ latest.allocation_method === 'rule_fallback' ? '热点/营销规则 + 普通兜底' : '普通选题兜底' }}</b></div></div>
    </div><div v-else class="empty-state">暂无当前自动策划批次</div>
    <div v-if="latest?.has_execution_exception" class="banner error-banner auto-exception-note"><b>检测到策划执行异常。</b>更新时间：{{ formatDateTime(latest.updated_at) }}<div v-if="exceptionReadError" class="auto-exception-item">异常明细读取失败：{{ exceptionReadError }}</div><div v-else-if="exceptionDetails.length === 0" class="auto-exception-item">当前接口没有返回账号级明细，请查看服务日志。</div><div v-for="(item, index) in exceptionDetails" :key="`${item.batch_code}-${item.account_id ?? index}`" class="auto-exception-item">{{ item.batch_code }} · {{ item.account_name }}<template v-if="item.account_id">（{{ item.account_id }}）</template>：{{ item.reason }}</div></div>
    </div>
  </section>

  <section class="card">
    <div class="card-head"><div><h2>自动策划批次记录</h2></div></div>
    <div class="card-body"><div class="auto-history-toolbar"><select v-model="historyYear"><option value="all">全部年份</option><option v-for="value in historyYears" :key="value" :value="value">{{ value }} 年</option></select><select v-model="historyMonth"><option value="all">全部月份</option><option v-for="value in historyMonths" :key="value" :value="value">{{ value }} 月</option></select><span>最后更新时间：{{ formatDateTime(latest?.updated_at) }}</span></div></div>
    <div v-if="historicalExceptionCycle" class="banner error-banner auto-exception-note"><b>{{ historicalExceptionCycle.cycle_start }} 至 {{ historicalExceptionCycle.cycle_end }} 存在策划执行异常。</b>更新时间：{{ formatDateTime(historicalExceptionCycle.updated_at) }}<div v-if="historicalExceptionBusy" class="auto-exception-item">正在读取异常明细…</div><div v-else-if="historicalExceptionReadError" class="auto-exception-item">异常明细读取失败：{{ historicalExceptionReadError }}</div><div v-else-if="historicalExceptionDetails.length === 0" class="auto-exception-item">当前接口没有返回账号级明细，请查看服务日志。</div><div v-for="(item, index) in historicalExceptionDetails" :key="`${item.batch_code}-${item.account_id ?? index}`" class="auto-exception-item">{{ item.batch_code }} · {{ item.account_name }}<template v-if="item.account_id">（{{ item.account_id }}）</template>：{{ item.reason }}</div><button class="text-btn" type="button" @click="closeCycleExceptions">收起异常详情</button></div>
    <div class="table-wrap"><table><thead><tr><th>策划周期</th><th>参与账号</th><th>普通槽位</th><th>营销槽位</th><th>热点槽位</th><th>周期状态</th><th>更新时间</th><th>操作</th></tr></thead><tbody>
      <tr v-for="cycle in filteredCycles" :key="cycle.cycle_id"><td><b>{{ cycle.cycle_start }} 至 {{ cycle.cycle_end }}</b></td><td>{{ cycle.account_count }}</td><td>{{ cycle.regular_slots }}</td><td>{{ cycle.marketing_slots }}</td><td>{{ cycle.hotspot_submitted }} / {{ cycle.hotspot_slots }}</td><td><span :class="['tag', statusClass(cycle.status, cycle.has_execution_exception)]">{{ statusLabel(cycle.status, cycle.has_execution_exception) }}</span></td><td>{{ formatDateTime(cycle.updated_at) }}</td><td><button v-if="cycle.has_execution_exception" class="text-btn" type="button" @click="showCycleExceptions(cycle)">查看异常</button><button class="text-btn" type="button" @click="openCycle(cycle)">查看详情</button></td></tr>
      <tr v-if="filteredCycles.length === 0"><td colspan="8"><div class="empty-state">暂无周度运行结果</div></td></tr>
    </tbody></table></div>
  </section>
</template>

<style scoped>
.auto-schedule-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.auto-schedule-row p { margin: 5px 0 0; color: var(--neutral-500); font-size: 13px; }
.auto-exception-note { margin: 0 18px 18px; }
.auto-exception-item { margin-top: 6px; overflow-wrap: anywhere; }
.auto-exception-note > .text-btn { color: var(--danger-hover); margin-top: 8px; }
</style>

