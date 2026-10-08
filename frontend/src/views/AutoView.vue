<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { usePlanningStore } from '../store'
import type { AutoCycleSummary } from '../types'

const store = usePlanningStore()
const router = useRouter()
const busy = ref(false)
const error = ref('')
const cycles = ref<AutoCycleSummary[]>([])
const historyYear = ref('all')
const historyMonth = ref('all')
const autoBatches = computed(() => store.batches.filter(batch => batch.plan_type === 'auto'))
const activeStatuses = new Set(['已规划', '热点空槽待填充'])
const latest = computed(() => cycles.value.find(cycle => activeStatuses.has(cycle.status)) ?? cycles.value[0])
const latestAutoBatch = computed(() => autoBatches.value.find(batch => batch.cycle_start === latest.value?.cycle_id) ?? autoBatches.value[0])
const latestCaption = computed(() => {
  if (latest.value?.status === '已规划') return '已为下一自然周生成策划结果'
  if (latest.value?.hotspot_pending) return '当前周期仍有待处理的热点槽位'
  return '最近一次已生成的周度策划任务'
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

function statusClass(status: string, failedAccounts = 0) {
  if (status === '已规划') return 'blue'
  return status === '热点空槽待填充' || failedAccounts > 0 ? 'orange' : 'green'
}

function statusLabel(status: string, failedAccounts = 0) {
  if (status === '已规划' || status === '热点空槽待填充') return status
  if (failedAccounts > 0) return '热点空槽待填充'
  return '已完成'
}

async function refresh() {
  busy.value = true
  error.value = ''
  try {
    const [, loaded] = await Promise.all([store.refreshBatches(), api.autoCycles()])
    cycles.value = loaded
  }
  catch (exc) { error.value = exc instanceof Error ? exc.message : '刷新异常' }
  finally { busy.value = false }
}

watch(() => store.databaseReady, ready => { if (ready) void refresh() }, { immediate: true })
onMounted(() => { refreshTimer = window.setInterval(() => { if (store.databaseReady && cycles.value.some(cycle => activeStatuses.has(cycle.status))) void refresh() }, 10000) })
onBeforeUnmount(() => { if (refreshTimer !== undefined) window.clearInterval(refreshTimer) })
</script>

<template>
  <div class="page-head">
    <div><h1>AI自动策划</h1><p>按周查看自动策划运行结果、参与账号和完成状态。</p></div>
    <div class="page-actions"><button class="btn" type="button" :disabled="busy || !store.databaseReady" @click="refresh">{{ busy ? '刷新中…' : '刷新状态' }}</button></div>
  </div>
  <div v-if="error" class="banner error-banner" role="alert">{{ error }}</div>
  <div class="auto-overview-grid">
    <div class="kpi-card"><small>最近策划周期</small><strong class="kpi-text">{{ latest?.cycle_start ?? '暂无' }}</strong><span>{{ latest?.cycle_end ?? '等待首个周期' }}</span></div>
    <div class="kpi-card"><small>参与账号</small><strong>{{ latest?.account_count ?? 0 }}</strong><span>最近周期</span></div>
    <div class="kpi-card"><small>完成状态</small><strong class="kpi-text">{{ latest ? statusLabel(latest.status, latest.failed_accounts) : '暂无运行记录' }}</strong><span>系统按兜底规则完成策划</span></div>
    <div class="kpi-card"><small>热点槽位状态</small><strong class="kpi-text">{{ hotspotStatus }}</strong><span>全部热点提交后本周期才算完成</span></div>
  </div>

  <section class="card">
    <div class="card-head auto-task-head"><div><h2>当前批次</h2><small>{{ latestCaption }}</small></div><div class="auto-state"><span class="pulse" />{{ latest ? statusLabel(latest.status, latest.failed_accounts) : '等待首个周期' }}</div><button v-if="latest" class="text-btn" type="button" @click="openCycle(latest)">查看详情</button></div>
    <div class="card-body"><div v-if="latest" class="auto-current-grid">
      <div class="summary-box"><div class="summary-row"><span>周度调度</span><b>{{ scheduleSummary.trigger }}</b></div><div class="summary-row"><span>每账号槽位</span><b>{{ scheduleSummary.days.split('/').length }} 个（{{ scheduleSummary.days }}）</b></div><div class="summary-row"><span>热点槽位提交</span><b>{{ hotspotStatus }}</b></div></div>
      <div class="summary-box"><div class="summary-row"><span>账号数据</span><b>夜间同步快照</b></div><div class="summary-row"><span>普通槽位</span><b>{{ latest.regular_slots }} 个</b></div><div class="summary-row"><span>营销槽位</span><b>{{ latest.marketing_slots }} 个</b></div></div>
      <div class="summary-box"><div class="summary-row"><span>开始时间</span><b>{{ latestAutoBatch?.created_at || '—' }}</b></div><div class="summary-row"><span>最后更新</span><b>{{ latest.updated_at || '—' }}</b></div><div class="summary-row"><span>批次状态</span><b>{{ statusLabel(latest.status, latest.failed_accounts) }}</b></div><div v-if="latest.allocation_method === 'ordinary_fallback'" class="summary-row"><span>分配方式</span><b>普通选题兜底</b></div></div>
    </div><div v-else class="empty-state">暂无当前自动策划批次</div><div class="banner info-banner auto-hotspot-note"><b>热点槽位：</b>具体热点选题不在本页人工处理；目标槽位前一天 22:00 后，后台任务读取本地最新有效热点并确定具体选题。周期状态按“已规划 → 热点空槽待填充 → 已完成”推进，全部热点槽位提交后本周期才算完成。</div></div>
  </section>

  <section class="card">
    <div class="card-head"><div><h2>自动策划批次记录</h2><small>周度批次作为业务归集容器，不设置统计冻结时间</small></div></div>
    <div class="card-body"><div class="auto-history-toolbar"><select v-model="historyYear"><option value="all">全部年份</option><option v-for="value in historyYears" :key="value" :value="value">{{ value }} 年</option></select><select v-model="historyMonth"><option value="all">全部月份</option><option v-for="value in historyMonths" :key="value" :value="value">{{ value }} 月</option></select><span>最后更新时间：{{ latest?.updated_at || '—' }}</span></div></div>
    <div class="table-wrap"><table><thead><tr><th>策划周期</th><th>参与账号</th><th>普通槽位</th><th>营销槽位</th><th>热点槽位</th><th>完成状态</th><th>更新时间</th><th>操作</th></tr></thead><tbody>
      <tr v-for="cycle in filteredCycles" :key="cycle.cycle_id"><td><b>{{ cycle.cycle_start }} 至 {{ cycle.cycle_end }}</b></td><td>{{ cycle.account_count }}</td><td>{{ cycle.regular_slots }}</td><td>{{ cycle.marketing_slots }}</td><td>{{ cycle.hotspot_submitted }} / {{ cycle.hotspot_slots }}</td><td><span :class="['tag', statusClass(cycle.status, cycle.failed_accounts)]">{{ statusLabel(cycle.status, cycle.failed_accounts) }}</span></td><td>{{ cycle.updated_at }}</td><td><button class="text-btn" type="button" @click="openCycle(cycle)">查看详情</button></td></tr>
      <tr v-if="filteredCycles.length === 0"><td colspan="8"><div class="empty-state">暂无周度运行结果</div></td></tr>
    </tbody></table></div>
  </section>
</template>

