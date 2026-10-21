<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AccountTypeBadge from '../components/AccountTypeBadge.vue'
import HoverHint from '../components/HoverHint.vue'
import ListPagination from '../components/ListPagination.vue'
import LoadingSkeleton from '../components/LoadingSkeleton.vue'
import ManualTaskTable from '../components/ManualTaskTable.vue'
import ContentFlowDrawer from '../components/ContentFlowDrawer.vue'
import { useDebouncedFields } from '../composables/useDebouncedFields'
import { api } from '../api'
import { usePlanningStore } from '../store'
import type { AccountOption, ManualTaskSummary, TopicOption } from '../types'

const store = usePlanningStore()
const router = useRouter()
const mode = ref<'list' | 'create'>('list')
const step = ref(1)
const stepperRef = ref<HTMLElement | null>(null)
const accountListRef = ref<HTMLElement | null>(null)
const topicListRef = ref<HTMLElement | null>(null)
const accountSelectionMode = ref<'filter' | 'upload'>('filter')
const taskName = ref('')
const publishDate = ref('')
const targetCount = ref<number | ''>('')
const keyword = ref('')
const accountTypeFilter = ref('')
const umNoFilter = ref('')
const organizationFilter = ref('')
const platformFilter = ref('')
const businessLineFilter = ref('')
const cityFilter = ref('')
const lifecycleFilter = ref('')
const followersMin = ref<number | null>(null)
const followersMax = ref<number | null>(null)
const appliedAccountFilters = ref({ keyword: '', accountType: '', umNo: '', organization: '', platform: '', businessLine: '', city: '', lifecycle: '', followersMin: null as number | null, followersMax: null as number | null })
const accounts = ref<AccountOption[]>([])
const topics = ref<TopicOption[]>([])
const topicFiltersExpanded = ref(false)
const tasks = ref<ManualTaskSummary[]>([])
const productionBusy = ref(false)
const contentFlowBatchId = ref<number | null>(null)
const sampledIds = ref<string[]>([])
const selectedTopicIds = ref<string[]>([])
const topicIdFilter = ref('')
const topicQuery = ref('')
const topicMarketingFilter = ref('')
const contentType = ref('')
const relatedProduct = ref('')
const relatedActivity = ref('')
const relatedHotspot = ref('')
const appliedTopicFilters = ref({ topicId: '', query: '', marketing: '', contentType: '', product: '', activity: '', hotspot: '' })
const topicPage = ref(1)
const topicPageSize = ref(20)
const submitAccountPage = ref(1)
const submitTopicPage = ref(1)
const submitAccountPageSize = ref(10)
const submitTopicPageSize = ref(10)
const busy = ref(false)
const tasksLoading = ref(false)
const catalogLoading = ref(false)
const { terms: searchTerms, flush: flushSearch } = useDebouncedFields({ keyword, umNoFilter, topicIdFilter, topicQuery })
const error = ref('')
const notice = ref('')
const eligibilityNotice = ref('')
const accountReview = ref(false)
const topicReview = ref(false)
const importMatchedCount = ref(0)
const importedAccountIds = ref<string[]>([])
const importUnknownUmNos = ref<string[]>([])
const plannedAccountIds = ref<string[]>([])
const availabilityDate = ref('')
const availabilityLoading = ref(false)
const availabilityError = ref('')
const accountPage = ref(1)
const accountPageSize = ref(20)
const plannedAccountTooltip = ref<{ accountId: string; left: number; top: number } | null>(null)
let availabilityRequest = 0
const importFileInput = ref<HTMLInputElement | null>(null)
let refreshTimer: number | undefined
const availabilityReady = computed(() => !!publishDate.value && availabilityDate.value === publishDate.value && !availabilityLoading.value && !availabilityError.value)
const plannedAccountSet = computed(() => new Set(plannedAccountIds.value))
const importedAccounts = computed(() => {
  const ids = new Set(importedAccountIds.value)
  return accounts.value.filter(account => ids.has(account.account_id))
})
function isAccountPlanned(accountId: string) { return !!publishDate.value && availabilityDate.value === publishDate.value && plannedAccountSet.value.has(accountId) }

async function revealStepProgress() {
  await nextTick()
  stepperRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function resetSelectionListScroll(target: 'accounts' | 'topics') {
  await nextTick()
  const list = target === 'accounts' ? accountListRef.value : topicListRef.value
  if (list) {
    list.scrollTop = 0
    list.scrollLeft = 0
  }
}

const eligibleAccounts = computed(() => accounts.value.filter(account => {
  const filters = appliedAccountFilters.value
  const search = filters.keyword.trim().toLocaleLowerCase()
  const accountType = account.account_type || (account.certified === true ? '\u8ba4\u8bc1' : account.certified === false ? '\u975e\u8ba4\u8bc1' : '')
  return (!search || `${account.account_name} ${account.account_alias} ${account.account_id}`.toLocaleLowerCase().includes(search)) &&
    (!filters.accountType || accountType === filters.accountType) &&
    (!filters.umNo.trim() || (account.um_no || '').toLocaleLowerCase().includes(filters.umNo.trim().toLocaleLowerCase())) &&
    (!filters.organization || account.organization === filters.organization) &&
    (!filters.platform || account.platform === filters.platform) &&
    (!filters.businessLine || account.business_line === filters.businessLine) &&
    (!filters.city || account.city === filters.city) &&
    (!filters.lifecycle || account.lifecycle_stage === filters.lifecycle) &&
    (filters.followersMin === null || (account.followers !== null && account.followers >= filters.followersMin)) &&
    (filters.followersMax === null || (account.followers !== null && account.followers <= filters.followersMax))
}))
function applyAccountFilters() {
  flushSearch()
  appliedAccountFilters.value = { keyword: keyword.value, accountType: accountTypeFilter.value, umNo: umNoFilter.value, organization: organizationFilter.value, platform: platformFilter.value, businessLine: businessLineFilter.value, city: cityFilter.value, lifecycle: lifecycleFilter.value, followersMin: followersMin.value, followersMax: followersMax.value }
  accountPage.value = 1
  applyDefaultAccountSelection()
}
function applyTopicFilters() {
  flushSearch()
  appliedTopicFilters.value = { topicId: topicIdFilter.value, query: topicQuery.value, marketing: topicMarketingFilter.value, contentType: contentType.value, product: relatedProduct.value, activity: relatedActivity.value, hotspot: relatedHotspot.value }
  topicPage.value = 1
}
const visibleAccounts = computed(() => {
  const pinned = sampledIds.value.map(id => accounts.value.find(item => item.account_id === id)).filter((item): item is AccountOption => !!item)
  const candidates = accountSelectionMode.value === 'filter'
    ? eligibleAccounts.value.filter(item => !sampledIds.value.includes(item.account_id))
    : importedAccounts.value.filter(item => !sampledIds.value.includes(item.account_id))
  return [...pinned, ...candidates].sort((a, b) => {
  const selectedOrder = Number(sampledIds.value.includes(b.account_id)) - Number(sampledIds.value.includes(a.account_id))
    return selectedOrder || (b.followers ?? -1) - (a.followers ?? -1) || a.account_name.localeCompare(b.account_name, 'zh-CN')
  }).filter((item, index, rows) => rows.findIndex(row => row.account_id === item.account_id) === index)
})
const accountPageCount = computed(() => Math.max(1, Math.ceil(visibleAccounts.value.length / accountPageSize.value)))
const pagedAccounts = computed(() => visibleAccounts.value.slice((accountPage.value - 1) * accountPageSize.value, accountPage.value * accountPageSize.value))
watch([pagedAccounts, publishDate, availabilityReady], () => { plannedAccountTooltip.value = null }, { flush: 'sync' })

function showPlannedAccountTooltip(accountId: string, event: MouseEvent | FocusEvent) {
  if (!availabilityReady.value || !isAccountPlanned(accountId)) return
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const x = 'clientX' in event ? event.clientX : Math.max(0, rect.left) + 32
  const y = 'clientY' in event ? event.clientY : rect.bottom
  const width = Math.min(304, window.innerWidth - 24)
  const height = 72
  plannedAccountTooltip.value = {
    accountId,
    left: Math.max(12, Math.min(x + 12, window.innerWidth - width - 12)),
    top: Math.max(12, y + height + 14 > window.innerHeight ? y - height - 12 : y + 14),
  }
}
const matchingAccounts = computed(() => accountSelectionMode.value === 'upload' ? importedAccounts.value : eligibleAccounts.value)
const plannedMatchingCount = computed(() => matchingAccounts.value.filter(account => isAccountPlanned(account.account_id)).length)
const availableMatchingCount = computed(() => availabilityReady.value ? matchingAccounts.value.length - plannedMatchingCount.value : 0)
const organizationOptions = computed(() => [...new Set(accounts.value.map(item => item.organization).filter(Boolean))].sort())
const platformOptions = computed(() => [...new Set(accounts.value.map(item => item.platform).filter(Boolean))].sort())
const businessLineOptions = computed(() => [...new Set(accounts.value.map(item => item.business_line).filter(Boolean))].sort())
const cityOptions = computed(() => [...new Set(accounts.value.map(item => item.city).filter(Boolean))].sort())
const lifecycleOptions = computed(() => [...new Set(accounts.value.map(item => item.lifecycle_stage).filter(Boolean))])
const contentTypes = computed(() => [...new Set(topics.value.map(item => item.content_type).filter(Boolean))].sort())
const relatedProducts = computed(() => [...new Set(topics.value.map(item => item.related_product).filter(Boolean))].sort())
const relatedActivities = computed(() => [...new Set(topics.value.map(item => item.related_activity).filter(Boolean))].sort())
const relatedHotspots = computed(() => [...new Set(topics.value.map(item => item.related_hotspot).filter(Boolean))].sort())
const filteredTopics = computed(() => topics.value.filter(topic =>
  (!appliedTopicFilters.value.topicId.trim() || topic.topic_id === appliedTopicFilters.value.topicId.trim()) &&
  (!appliedTopicFilters.value.query.trim() || topic.topic_title.toLocaleLowerCase().includes(appliedTopicFilters.value.query.trim().toLocaleLowerCase())) &&
  (!appliedTopicFilters.value.marketing || String(topic.is_marketing) === appliedTopicFilters.value.marketing) &&
  (!appliedTopicFilters.value.contentType || topic.content_type === appliedTopicFilters.value.contentType) &&
  (!appliedTopicFilters.value.product || topic.related_product === appliedTopicFilters.value.product) &&
  (!appliedTopicFilters.value.activity || topic.related_activity === appliedTopicFilters.value.activity) &&
  (!appliedTopicFilters.value.hotspot || topic.related_hotspot === appliedTopicFilters.value.hotspot),
))
const topicPageCount = computed(() => Math.max(1, Math.ceil(filteredTopics.value.length / topicPageSize.value)))
const pagedTopics = computed(() => filteredTopics.value.slice((topicPage.value - 1) * topicPageSize.value, topicPage.value * topicPageSize.value))
const selectedAccounts = computed(() => sampledIds.value.map(id => accounts.value.find(item => item.account_id === id)).filter((item): item is AccountOption => !!item))
const selectedTopics = computed(() => selectedTopicIds.value.map(id => topics.value.find(item => item.topic_id === id)).filter((item): item is TopicOption => !!item))
const submitAccountsPage = computed(() => selectedAccounts.value.slice((submitAccountPage.value - 1) * submitAccountPageSize.value, submitAccountPage.value * submitAccountPageSize.value))
const submitTopicsPage = computed(() => selectedTopics.value.slice((submitTopicPage.value - 1) * submitTopicPageSize.value, submitTopicPage.value * submitTopicPageSize.value))
const accountSelectionPool = computed(() => availabilityReady.value ? matchingAccounts.value.filter(account => !isAccountPlanned(account.account_id)) : [])
const allAccountsSelected = computed(() => accountSelectionPool.value.length > 0 && accountSelectionPool.value.every(account => sampledIds.value.includes(account.account_id)))
const someAccountsSelected = computed(() => !allAccountsSelected.value && accountSelectionPool.value.some(account => sampledIds.value.includes(account.account_id)))
const canSubmit = computed(() => store.databaseReady && availabilityReady.value && !busy.value && taskName.value.trim() !== '' && publishDate.value !== '' && targetCount.value !== '' && Number.isInteger(targetCount.value) && targetCount.value >= 1 && targetCount.value <= 1000 && sampledIds.value.length > 0 && selectedTopicIds.value.length > 0)
const targetCountError = computed(() => targetCount.value !== '' && (!Number.isInteger(targetCount.value) || targetCount.value < 1 || targetCount.value > 1000) ? '数量须为 1 至 1000 之间的整数' : '')

watch(topicPageSize, () => { topicPage.value = 1 })
watch(topicPageCount, count => { topicPage.value = Math.min(topicPage.value, count) })
watch(selectedAccounts, () => { submitAccountPage.value = 1 })
watch(selectedTopics, () => { submitTopicPage.value = 1 })

function applyDefaultAccountSelection() {
  if (accountSelectionMode.value !== 'filter') return
  const count = targetCount.value
  if (count === '' || !Number.isInteger(count) || count < 1 || count > 1000) {
    sampledIds.value = []
    return
  }
  const ordered = [...accountSelectionPool.value].sort((a, b) => (b.followers ?? -1) - (a.followers ?? -1))
  sampledIds.value = ordered.slice(0, Math.min(count, ordered.length)).map(item => item.account_id)
}

watch(eligibleAccounts, () => { accountPage.value = 1 }, { flush: 'sync' })
watch(accountPageSize, () => { accountPage.value = 1 })
watch(accountPageCount, count => { accountPage.value = Math.min(accountPage.value, count) })

watch([publishDate, () => store.databaseReady], () => {
  sampledIds.value = []
  accountPage.value = 1
  accountReview.value = false
  void loadAccountAvailability(true)
}, { immediate: true, flush: 'sync' })

async function loadAccountAvailability(reselect = false): Promise<boolean> {
  const request = ++availabilityRequest
  const selectedDate = publishDate.value
  availabilityDate.value = ''
  availabilityError.value = ''
  availabilityLoading.value = !!selectedDate && store.databaseReady
  if (!selectedDate || !store.databaseReady) {
    plannedAccountIds.value = []
    return false
  }
  try {
    const result = await api.manualAccountAvailability(selectedDate)
    if (request !== availabilityRequest || selectedDate !== publishDate.value) return false
    if (result.publish_date !== selectedDate) throw new Error('账号策划日期校验失败，请重试')
    plannedAccountIds.value = result.planned_account_ids
    availabilityDate.value = selectedDate
    availabilityLoading.value = false
    sampledIds.value = sampledIds.value.filter(id => !isAccountPlanned(id))
    if (reselect) {
      if (accountSelectionMode.value === 'filter') applyDefaultAccountSelection()
      else sampledIds.value = importedAccountIds.value.filter(id => !isAccountPlanned(id))
    }
    return true
  } catch (exc) {
    if (request === availabilityRequest) availabilityError.value = exc instanceof Error ? exc.message : '读取当日策划账号失败'
    return false
  } finally {
    if (request === availabilityRequest) availabilityLoading.value = false
  }
}

async function loadCatalog() {
  catalogLoading.value = true
  try {
    const [accountRows, topicRows] = await Promise.all([api.accounts(), api.topics()])
    accounts.value = accountRows
    topics.value = topicRows
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '读取账号和选题失败' }
  finally { catalogLoading.value = false }
}

async function loadTasks() {
  tasksLoading.value = true
  try {
    const rows = await api.manualTasks()
    tasks.value = rows
    error.value = ''
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '\u8bfb\u53d6\u624b\u52a8\u7b56\u5212\u4efb\u52a1\u5931\u8d25' }
  finally { tasksLoading.value = false }
}

function openTaskDetails(task: ManualTaskSummary) {
  if (!task.batch_id) return
  void router.push({ path: '/results', query: { batch: String(task.batch_id), plan_type: 'manual', from: 'manual' } })
}

async function startTaskProduction(task: ManualTaskSummary) {
  const planningStatus = task.planning_status || task.status
  if (!task.batch_id || !/完成|成功/.test(planningStatus) || !/待生产|待生成|未生成/.test(task.content_status || '')) return
  if (productionBusy.value) return
  productionBusy.value = true
  try { await api.startContentProduction(task.batch_id); await loadTasks() }
  catch (exc) { error.value = exc instanceof Error ? exc.message : '提交内容生产失败' }
  finally { productionBusy.value = false }
}

function openContentFlow(task: ManualTaskSummary) {
  if (!task.batch_id) return
  contentFlowBatchId.value = task.batch_id
}

watch(() => store.databaseReady, ready => {
  if (ready) { void loadCatalog(); void loadTasks() }
}, { immediate: true })
onMounted(() => {
  refreshTimer = window.setInterval(() => {
    if (store.databaseReady && tasks.value.some(task => ['执行中', '进行中'].includes(task.status) || task.content_status === '\u751f\u6210\u4e2d')) void loadTasks()
  }, 3000)
})
onBeforeUnmount(() => {
  if (refreshTimer !== undefined) window.clearInterval(refreshTimer)
})

function startCreate() {
  publishDate.value = ''
  targetCount.value = ''
  step.value = 1
  accountSelectionMode.value = 'filter'
  taskName.value = ''
  sampledIds.value = []
  importMatchedCount.value = 0
  importedAccountIds.value = []
  importUnknownUmNos.value = []
  selectedTopicIds.value = []
  topicIdFilter.value = ''
  topicQuery.value = ''
  topicMarketingFilter.value = ''
  contentType.value = ''
  relatedProduct.value = ''
  relatedActivity.value = ''
  relatedHotspot.value = ''
  topicPage.value = 1
  accountReview.value = false
  topicReview.value = false
  error.value = ''
  notice.value = ''
  eligibilityNotice.value = ''
  mode.value = 'create'
}

function toggleAccount(accountId: string, event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  setAccountSelected(accountId, checked)
}

function setAccountSelected(accountId: string, checked: boolean) {
  if (accountReview.value) return
  if (checked && (!availabilityReady.value || isAccountPlanned(accountId))) return
  if (checked && !sampledIds.value.includes(accountId)) {
    error.value = ''
    sampledIds.value = [...sampledIds.value, accountId]
  }
  if (!checked) sampledIds.value = sampledIds.value.filter(id => id !== accountId)
  accountReview.value = false
}

function interactiveRowTarget(event: Event) {
  return event.target instanceof Element && Boolean(event.target.closest('input, button, a, select, textarea, label'))
}

function toggleAccountRow(accountId: string, event: Event) {
  if (accountReview.value || interactiveRowTarget(event) || !availabilityReady.value || isAccountPlanned(accountId)) return
  setAccountSelected(accountId, !sampledIds.value.includes(accountId))
}

function toggleTopicRow(topicId: string, event: Event) {
  if (interactiveRowTarget(event)) return
  setTopicSelected(topicId, !selectedTopicIds.value.includes(topicId))
}

function setTopicSelected(topicId: string, checked: boolean) {
  if (topicReview.value) return
  if (checked) {
    if (selectedTopicIds.value.includes(topicId) || selectedTopicIds.value.length >= 100) return
    selectedTopicIds.value = [...selectedTopicIds.value, topicId]
  } else {
    selectedTopicIds.value = selectedTopicIds.value.filter(id => id !== topicId)
  }
  error.value = ''
}

function removeTopic(index: number) {
  if (topicReview.value) return
  selectedTopicIds.value = selectedTopicIds.value.filter((_, itemIndex) => itemIndex !== index)
  topicReview.value = false
}

function topicTooltip(topic: TopicOption) {
  const dash = '\u2014'
  const validity = `${topic.valid_from?.slice(0, 10) || dash} - ${topic.valid_to?.slice(0, 10) || dash}`
  return [
    `\u9009\u9898 ID: ${topic.topic_id}`,
    `\u9009\u9898\u6807\u9898: ${topic.topic_title}`,
    `\u9009\u9898\u5927\u7eb2: ${topic.outline || dash}`,
    `\u5185\u5bb9\u7c7b\u578b: ${topic.content_type || dash}`,
    `\u9009\u9898\u7c7b\u578b: ${topic.is_marketing ? '\u8425\u9500' : '\u975e\u8425\u9500'}`,
    `\u5173\u8054\u4ea7\u54c1: ${topic.related_product || dash}`,
    `\u5173\u8054\u6d3b\u52a8: ${topic.related_activity || dash}`,
    `\u5173\u8054\u5c5e\u5730\u70ed\u70b9: ${topic.related_hotspot || dash}`,
    `\u6709\u6548\u671f: ${validity}`,
  ].join('\n')
}

function selectAllAccounts(event: Event) {
  flushSearch()
  if (accountReview.value || !availabilityReady.value) return
  const ids = accountSelectionPool.value.map(account => account.account_id)
  sampledIds.value = (event.target as HTMLInputElement).checked ? [...new Set([...sampledIds.value, ...ids])] : sampledIds.value.filter(id => !ids.includes(id))
  accountReview.value = false
}

function returnToStep(next: number) {
  if (next >= step.value || busy.value) return
  step.value = next
  if (next <= 2) accountReview.value = false
  if (next <= 3) topicReview.value = false
  void revealStepProgress()
}

function setAccountSelectionMode(next: 'filter' | 'upload') {
  accountSelectionMode.value = next
  error.value = ''
  notice.value = ''
  accountPage.value = 1
  if (next === 'upload') sampledIds.value = availabilityReady.value ? importedAccountIds.value.filter(id => !isAccountPlanned(id)) : []
}

function downloadUmTemplate() {
  const csv = `\uFEFFUM号\r\n`
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = '手动策划账号导入模板.csv'
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function parseCsvRows(text: string): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let cell = ''
  let quoted = false
  for (let index = 0; index < text.length; index++) {
    const char = text[index]
    if (char === '"') {
      if (quoted && text[index + 1] === '"') { cell += '"'; index++ }
      else quoted = !quoted
    } else if (char === ',' && !quoted) {
      row.push(cell.trim()); cell = ''
    } else if ((char === '\n' || char === '\r') && !quoted) {
      if (char === '\r' && text[index + 1] === '\n') index++
      row.push(cell.trim()); cell = ''
      if (row.some(value => value !== '')) rows.push(row)
      row = []
    } else cell += char
  }
  row.push(cell.trim())
  if (row.some(value => value !== '')) rows.push(row)
  return rows
}

async function importAccountsByUm(file?: File) {
  if (!file) return
  error.value = ''
  notice.value = ''
  try {
    const bytes = await file.arrayBuffer()
    let text = new TextDecoder('utf-8').decode(bytes)
    if (text.includes('\uFFFD')) text = new TextDecoder('gb18030').decode(bytes)
    const rows = parseCsvRows(text.replace(/^\uFEFF/, ''))
    if (!rows.length) { error.value = '模板中没有可导入的 UM 号'; return }
    const first = rows[0].map(value => value.toLocaleLowerCase())
    const umColumn = first.findIndex(value => value.includes('um号') || value === 'um_no' || value === 'um number')
    const column = umColumn >= 0 ? umColumn : 0
    const start = umColumn >= 0 ? 1 : 0
    const umNos = [...new Set(rows.slice(start).map(row => (row[column] || '').trim()).filter(Boolean))]
    if (!umNos.length) { error.value = '模板中没有可导入的 UM 号'; return }
    const accountsByUm = new Map<string, AccountOption>()
    for (const account of accounts.value) {
      const umNo = account.um_no?.trim().toLocaleLowerCase()
      if (umNo && !accountsByUm.has(umNo)) accountsByUm.set(umNo, account)
    }
    const matched: AccountOption[] = []
    const unknown: string[] = []
    for (const umNo of umNos) {
      const account = accountsByUm.get(umNo.toLocaleLowerCase())
      if (account) matched.push(account)
      else unknown.push(umNo)
    }
    accountSelectionMode.value = 'upload'
    importedAccountIds.value = [...new Set(matched.map(item => item.account_id))]
    sampledIds.value = availabilityReady.value ? importedAccountIds.value.filter(id => !isAccountPlanned(id)) : []
    accountPage.value = 1
    importMatchedCount.value = importedAccountIds.value.length
    importUnknownUmNos.value = unknown
    if (matched.length) notice.value = ''
    else error.value = '没有匹配到账号，请检查 UM 号或确认账号数据已同步'
  } catch {
    error.value = '文件读取失败，请使用下载的 CSV 模板填写后再导入'
  } finally {
    if (importFileInput.value) importFileInput.value.value = ''
  }
}

function savePlanStep() {
  error.value = ''
  if (!taskName.value.trim()) { error.value = '请输入任务名称'; return }
  if (!publishDate.value) { error.value = '请选择投放日期'; return }
  step.value = 2
  void revealStepProgress()
}

async function saveAccountStep() {
  error.value = ''
  if (!taskName.value.trim()) { error.value = '请输入任务名称'; return }
  if (!publishDate.value) { error.value = '请选择投放日期'; return }
  if (targetCount.value === '') { error.value = '请输入计划账号数量'; return }
  if (!Number.isInteger(targetCount.value) || targetCount.value < 1 || targetCount.value > 1000) { error.value = '计划账号数量须为 1 至 1000 之间的整数'; return }
  if (!sampledIds.value.length) { error.value = '请先选择账号'; return }
  if (!await loadAccountAvailability()) return
  if (!sampledIds.value.length) { error.value = '所选账号当日已手动策划，请重新选择'; return }
  accountPage.value = 1
  accountReview.value = true
  void resetSelectionListScroll('accounts')
}

function nextStep() {
  error.value = ''
  if (!selectedTopicIds.value.length) { error.value = '请至少选择一个选题'; return }
  step.value = 4
}

function saveTopicStep() {
  error.value = ''
  if (!selectedTopicIds.value.length) { error.value = '请至少选择一个选题'; return }
  topicPage.value = 1
  topicReview.value = true
  void resetSelectionListScroll('topics')
}

function confirmAccountReview() {
  if (!availabilityReady.value || !sampledIds.value.length) {
    accountReview.value = false
    error.value = '请重新确认可策划账号后再继续'
    return
  }
  accountReview.value = true
  step.value = 3
  void revealStepProgress()
}

function confirmTopicReview() {
  if (!selectedTopicIds.value.length) {
    topicReview.value = false
    error.value = '请选择至少一个选题'
    return
  }
  topicReview.value = true
  step.value = 4
  void revealStepProgress()
}

async function submit() {
  if (!canSubmit.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  eligibilityNotice.value = ''
  try {
    const selectedCount = sampledIds.value.length
    if (!await loadAccountAvailability()) return
    if (sampledIds.value.length !== selectedCount) {
      step.value = 2
      error.value = '部分账号当日已手动策划，已移除，请重新确认账号数量'
      return
    }
    const preview = await api.previewManual({
      task_name: taskName.value.trim(),
      publish_date: publishDate.value,
      account_ids: sampledIds.value,
      target_count: Number(targetCount.value),
      topic_ids: selectedTopicIds.value,
      note: '',
      city: cityFilter.value || undefined,
      keyword: keyword.value.trim() || undefined,
    })
    await api.submitManualPreview(preview.preview_id)
    await loadTasks()
    notice.value = '手动策划已提交，当前状态：生成中'
    mode.value = 'list'
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '提交手动策划失败'
    if (error.value.includes('不具备所选营销选题资格')) eligibilityNotice.value = error.value
  } finally {
    busy.value = false
  }
}

function closeEligibilityNotice(returnToSelection = false) {
  eligibilityNotice.value = ''
  if (returnToSelection) {
    error.value = ''
    accountReview.value = false
    topicReview.value = false
    step.value = 1
    void revealStepProgress()
  }
}
</script>

<template>
  <ContentFlowDrawer v-if="contentFlowBatchId" :batch-id="contentFlowBatchId" @close="contentFlowBatchId = null" @changed="loadTasks" />
  <div class="page-head manual-page-head">
    <div class="manual-head-actions">
      <button v-if="mode === 'create'" class="btn" type="button" @click="mode = 'list'; error = ''">返回任务列表</button>
      <button v-else class="btn primary" type="button" :disabled="!store.databaseReady" @click="startCreate">新建人工策划</button>
    </div>
  </div>
  <div v-if="error" class="banner error-banner" role="alert">{{ error }}</div>
  <div v-if="notice" class="banner success-banner" role="status">{{ notice }}</div>
  <div v-if="availabilityError && mode === 'create'" class="banner error-banner manual-availability-error" role="alert">{{ availabilityError }}</div>

  <section v-if="mode === 'list'" class="card manual-task-card">
    <div class="card-head"><div><h2>策划任务列表</h2></div></div>
    <ManualTaskTable
      :tasks="tasks"
      :loading="tasksLoading"
      :initialized="store.initialized"
      @plan-details="openTaskDetails"
      @generate-content="startTaskProduction"
      @content-flow="openContentFlow"
    />
  </section>

  <template v-else>
    <div ref="stepperRef" class="manual-stepper" aria-label="手动策划流程">
      <button v-for="(label, index) in ['创建策划', '选择账号', '选择选题', '确认策划']" :key="label" :class="['manual-step', { active: step === index + 1, done: step > index + 1 }]" type="button" :disabled="index + 1 > step || busy" :aria-current="step === index + 1 ? 'step' : undefined" @click="returnToStep(index + 1)">
        <span>{{ step > index + 1 ? '✓' : index + 1 }}</span><b>{{ label }}</b>
      </button>
    </div>

    <Transition name="manual-step-change" mode="out-in">
    <section v-if="step === 1" key="manual-step-plan" class="card">
      <div class="card-head"><div><h2>创建策划</h2></div></div>
      <div class="card-body manual-step-body">
        <div class="manual-create-meta">
          <label class="field"><span>任务名称 <em>*</em></span><input v-model="taskName" type="text" maxlength="120" placeholder="请输入任务名称" required /></label>
          <label class="field"><span>投放日期 <em>*</em></span><input v-model="publishDate" type="date" required /></label>
        </div>
        <div class="footer-actions manual-step-actions"><button class="btn primary" type="button" :disabled="busy" @click="savePlanStep">下一步</button></div>
      </div>
    </section>
    <section v-else-if="step === 2" key="manual-step-accounts" class="card">
      <div class="card-head"><div><h2>选择账号</h2></div><span class="manual-selected-count">已选 {{ sampledIds.length }} 个</span></div>
      <div class="card-body manual-step-body">
        <fieldset class="manual-selection-lock" :disabled="accountReview">
        <div class="manual-account-mode-row">
          <label class="field"><span>计划账号数量 <em>*</em></span><input v-model.number="targetCount" type="number" min="1" max="1000" placeholder="请输入计划账号数量" :aria-invalid="Boolean(targetCountError)" :aria-describedby="targetCountError ? 'manual-target-count-error' : undefined" required /><small v-if="targetCountError" id="manual-target-count-error" class="field-error" role="alert">{{ targetCountError }}</small></label>
          <div class="manual-selection-modes" role="tablist" aria-label="账号选择方式">
            <button :class="['manual-mode-tab', { active: accountSelectionMode === 'filter' }]" type="button" role="tab" :aria-selected="accountSelectionMode === 'filter'" @click="setAccountSelectionMode('filter')">筛选选择</button>
            <button :class="['manual-mode-tab', { active: accountSelectionMode === 'upload' }]" type="button" role="tab" :aria-selected="accountSelectionMode === 'upload'" @click="setAccountSelectionMode('upload')">模板导入</button>
          </div>
        </div>
        <div v-if="accountSelectionMode === 'filter'" class="manual-account-filters"><label class="field"><span>&#x751F;&#x547D;&#x5468;&#x671F;</span><select v-model="lifecycleFilter"><option value="">&#x5168;&#x90E8;</option><option v-for="item in lifecycleOptions" :key="item" :value="item">{{ item }}</option></select></label><label class="field manual-follower-field"><span>&#x7C89;&#x4E1D;&#x91CF;</span><div class="manual-follower-range"><input v-model.number="followersMin" type="number" min="0" placeholder="&#x8D77;&#x59CB;&#x7C89;&#x4E1D;&#x91CF;" /><i>&#x81F3;</i><input v-model.number="followersMax" type="number" min="0" placeholder="&#x622A;&#x6B62;&#x7C89;&#x4E1D;&#x91CF;" /></div></label><label class="field"><span>&#x8D26;&#x53F7;&#x7C7B;&#x578B;</span><select v-model="accountTypeFilter"><option value="">&#x5168;&#x90E8;</option><option value="&#x8BA4;&#x8BC1;">&#x8BA4;&#x8BC1;</option><option value="&#x975E;&#x8BA4;&#x8BC1;">&#x975E;&#x8BA4;&#x8BC1;</option></select></label><label class="field"><span>&#x5C5E;&#x4E3B;&#x7EC4;&#x7EC7;</span><select v-model="organizationFilter"><option value="">&#x5168;&#x90E8;</option><option v-for="item in organizationOptions" :key="item" :value="item">{{ item }}</option></select></label><label class="field"><span>&#x5E73;&#x53F0;</span><select v-model="platformFilter"><option value="">&#x5168;&#x90E8;</option><option v-for="item in platformOptions" :key="item" :value="item">{{ item }}</option></select></label><label class="field"><span>&#x4E1A;&#x52A1;&#x7EBF;</span><select v-model="businessLineFilter"><option value="">&#x5168;&#x90E8;</option><option v-for="item in businessLineOptions" :key="item" :value="item">{{ item }}</option></select></label><label class="field"><span>&#x5730;&#x57DF;</span><select v-model="cityFilter"><option value="">&#x5168;&#x90E8;</option><option v-for="item in cityOptions" :key="item" :value="item">{{ item }}</option></select></label><label class="field"><span>&#x8D26;&#x53F7; ID &#x6216;&#x6635;&#x79F0;</span><input v-model="keyword" type="search" placeholder="&#x8F93;&#x5165;&#x8D26;&#x53F7; ID &#x6216;&#x6635;&#x79F0;" /></label><label class="field"><span>&#x5C5E;&#x4E3B; UM &#x53F7;</span><input v-model="umNoFilter" type="search" placeholder="&#x8F93;&#x5165;&#x5C5E;&#x4E3B; UM &#x53F7;" /></label><div class="manual-filter-actions"><button class="btn primary" type="button" @click="applyAccountFilters">&#x67E5;&#x8BE2;</button></div></div>
        <div v-else class="manual-upload-panel">
          <div><b>按 UM 号导入账号</b><p>下载 CSV 模板，填写 UM 号后上传；匹配到的账号会自动勾选。</p></div>
          <div class="manual-upload-actions"><button class="btn" type="button" @click="downloadUmTemplate">下载导入模板</button><input ref="importFileInput" class="manual-file-input" type="file" accept=".csv,text/csv" @change="importAccountsByUm(($event.target as HTMLInputElement).files?.[0])" /><button class="btn primary" type="button" @click="importFileInput?.click()">上传并识别</button></div>
          <div v-if="importMatchedCount || importUnknownUmNos.length" class="manual-import-result"><b>识别成功 {{ importMatchedCount }} 个</b><div v-if="importUnknownUmNos.length"><span>未匹配 UM 号（{{ importUnknownUmNos.length }}）</span><div class="manual-unknown-list">{{ importUnknownUmNos.join('、') }}</div></div></div>
        </div>
        <div class="manual-account-list-meta"><div class="manual-account-counts"><b>{{ accountSelectionMode === 'filter' ? '符合条件' : '导入识别' }} {{ matchingAccounts.length }} 个</b><template v-if="availabilityReady"><span>可策划 <strong>{{ availableMatchingCount }}</strong></span><span class="manual-planned-count">当日已策划 <strong>{{ plannedMatchingCount }}</strong></span><span>已选 <strong>{{ sampledIds.length }}</strong></span></template><span v-else>{{ availabilityLoading ? '查询当日策划状态中…' : '待选择投放日期并查询' }}</span></div></div>
        <LoadingSkeleton v-if="catalogLoading || !store.initialized" /><div v-else ref="accountListRef" class="table-wrap manual-account-table" @scroll="plannedAccountTooltip = null"><table><thead><tr><th><input type="checkbox" aria-label="&#x5168;&#x9009;&#x5F53;&#x524D;&#x7B5B;&#x9009;&#x4E0B;&#x7684;&#x53EF;&#x7B56;&#x5212;&#x8D26;&#x53F7;&#xFF08;&#x8DE8;&#x9875;&#xFF09;" :checked="allAccountsSelected" :indeterminate="someAccountsSelected" :disabled="!availabilityReady || !accountSelectionPool.length" @change="selectAllAccounts" /></th><th>&#x8D26;&#x53F7;&#x7C7B;&#x578B;</th><th>&#x5C5E;&#x4E3B; UM &#x53F7;</th><th>&#x8D26;&#x53F7;&#x6635;&#x79F0;</th><th>&#x8D26;&#x53F7; ID</th><th>&#x5C5E;&#x4E3B;&#x7EC4;&#x7EC7;</th><th>&#x4E1A;&#x52A1;&#x7EBF;</th><th>&#x5E73;&#x53F0;</th><th>&#x5730;&#x57DF;</th><th>&#x751F;&#x547D;&#x5468;&#x671F;</th><th>&#x7C89;&#x4E1D;&#x6570;</th></tr></thead><tbody>
          <tr v-for="account in pagedAccounts" :key="account.account_id" :class="{ selected: sampledIds.includes(account.account_id), 'already-planned': isAccountPlanned(account.account_id) }" class="selection-row" tabindex="0" @click="toggleAccountRow(account.account_id, $event)" @keydown.enter.self.prevent="toggleAccountRow(account.account_id, $event)" @keydown.space.self.prevent="toggleAccountRow(account.account_id, $event)" :aria-disabled="!availabilityReady || isAccountPlanned(account.account_id) || undefined" :aria-describedby="plannedAccountTooltip?.accountId === account.account_id ? 'manual-planned-account-tooltip' : undefined" @mouseenter="showPlannedAccountTooltip(account.account_id, $event)" @mousemove="showPlannedAccountTooltip(account.account_id, $event)" @mouseleave="plannedAccountTooltip = null" @focusin="showPlannedAccountTooltip(account.account_id, $event)" @focusout="plannedAccountTooltip = null"><td><input type="checkbox" :checked="sampledIds.includes(account.account_id)" :disabled="!availabilityReady || isAccountPlanned(account.account_id)" :aria-label="`选择账号 ${account.account_name}`" @change="toggleAccount(account.account_id, $event)" /></td><td><AccountTypeBadge :type="account.account_type || (account.certified === true ? '认证' : account.certified === false ? '非认证' : '—')" /></td><td>{{ account.um_no || '—' }}</td><td><b>{{ account.account_name }}</b></td><td>{{ account.account_id }}</td><td>{{ account.organization || '—' }}</td><td>{{ account.business_line || '\u2014' }}</td><td>{{ account.platform || '—' }}</td><td>{{ account.city || '—' }}</td><td>{{ account.lifecycle_stage || '—' }}</td><td>{{ account.followers?.toLocaleString() ?? '—' }}</td></tr>
          <tr v-if="visibleAccounts.length === 0"><td colspan="11"><div class="empty-state">{{ accountSelectionMode === 'upload' ? '请上传账号模板' : '没有符合条件的账号' }}</div></td></tr>
        </tbody></table></div>
        <ListPagination v-model:page="accountPage" v-model:page-size="accountPageSize" :total="visibleAccounts.length" unit="个账号" :page-size-options="[20, 50, 100]" class="manual-account-pagination" />
        </fieldset>
        <div class="footer-actions manual-step-actions"><div v-if="accountReview" class="manual-step-review" role="status"><span class="manual-step-review-icon" aria-hidden="true">✓</span><strong>&#x8BA1;&#x5212;&#x8D26;&#x53F7;&#x6570; <em>{{ targetCount }}</em> &#x4E2A;&#xFF0C;&#x5B9E;&#x9645;&#x9009;&#x62E9; <em>{{ sampledIds.length }}</em> &#x4E2A;</strong><span v-if="Number(targetCount) !== sampledIds.length" class="manual-count-difference">{{ sampledIds.length < Number(targetCount) ? '未达计划' : '超出计划' }} {{ Math.abs(Number(targetCount) - sampledIds.length) }} 个</span><button class="btn" type="button" @click="accountReview = false">返回调整</button><button class="btn primary" type="button" @click="confirmAccountReview">下一步</button></div><button v-else class="btn primary" type="button" :disabled="!sampledIds.length || !availabilityReady || busy" @click="saveAccountStep">{{ availabilityLoading ? '查询中…' : '保存' }}</button></div>
      </div>
    </section>

    <section v-else-if="step === 3" key="manual-step-topics" class="card manual-topic-step">
      <div class="card-head"><div><h2>选择选题</h2></div><span class="manual-selected-count">已选 {{ selectedTopicIds.length }} 个</span></div>
      <div class="card-body manual-step-body">
        <div class="manual-topic-picker">
          <aside class="manual-topic-picked">
            <div class="manual-topic-picked-head"><b>&#x5DF2;&#x9009;&#x9009;&#x9898;</b><span>{{ selectedTopics.length }} / 100</span></div>
            <div v-if="selectedTopics.length" class="manual-topic-picked-list">
              <article v-for="(topic, index) in selectedTopics" :key="`${index}-${topic.topic_id}`" class="manual-topic-picked-item" tabindex="0" :title="topicTooltip(topic)"><div><small>{{ topic.topic_id }}</small><b>{{ topic.topic_title }}</b><p>{{ topic.outline || '\u6682\u65e0\u9009\u9898\u5927\u7eb2' }}</p><small>{{ topic.content_type || '\u2014' }}</small></div><button class="remove-topic" type="button" :disabled="topicReview" aria-label="&#x79FB;&#x9664;&#x9009;&#x9898;" @click="removeTopic(index)">&#x00D7;</button></article>
            </div>
            <div v-else class="manual-topic-picked-empty">&#x8BF7;&#x4ECE;&#x53F3;&#x4FA7;&#x9009;&#x9898;&#x5E93;&#x6DFB;&#x52A0;</div>
          </aside>
          <section class="manual-topic-picker-available">
            <div class="topic-filters-toggle"><button class="filter-collapse-toggle" type="button" :aria-expanded="topicFiltersExpanded" aria-controls="manual-topic-filters" @click="topicFiltersExpanded = !topicFiltersExpanded">&#x7B5B;&#x9009;&#x6761;&#x4EF6; <span>{{ topicFiltersExpanded ? '\u2303' : '\u2304' }}</span></button></div>
            <div id="manual-topic-filters" v-show="topicFiltersExpanded" class="manual-topic-filters">
              <label class="field"><span class="field-label-with-tip">&#x9009;&#x9898; ID <span class="field-help-tip" tabindex="0" title="&#x8F93;&#x5165;&#x5B8C;&#x6574;&#x9009;&#x9898; ID;&#x8FDB;&#x884C;&#x7CBE;&#x786E;&#x5339;&#x914D;">?</span></span><input v-model="topicIdFilter" type="text" inputmode="text" autocomplete="off" placeholder="&#x8F93;&#x5165;&#x5B8C;&#x6574;&#x9009;&#x9898; ID" /></label>
              <label class="field"><span class="field-label-with-tip">&#x9009;&#x9898;&#x6807;&#x9898; <span class="field-help-tip" tabindex="0" title="&#x8F93;&#x5165;&#x6807;&#x9898;&#x5173;&#x952E;&#x8BCD;;&#x8FDB;&#x884C;&#x6A21;&#x7CCA;&#x641C;&#x7D22;">?</span></span><input v-model="topicQuery" type="search" placeholder="&#x8F93;&#x5165;&#x9009;&#x9898;&#x6807;&#x9898;&#x5173;&#x952E;&#x8BCD;" /></label>
              <label class="field"><span>&#x9009;&#x9898;&#x7C7B;&#x578B;</span><select v-model="topicMarketingFilter"><option value="">&#x5168;&#x90E8;</option><option value="true">&#x8425;&#x9500;</option><option value="false">&#x975E;&#x8425;&#x9500;</option></select></label>
              <label class="field"><span>&#x5185;&#x5BB9;&#x7C7B;&#x578B;</span><select v-model="contentType"><option value="">&#x5168;&#x90E8;</option><option v-for="value in contentTypes" :key="value" :value="value">{{ value }}</option></select></label>
              <label class="field"><span>&#x5173;&#x8054;&#x4EA7;&#x54C1;</span><select v-model="relatedProduct"><option value="">&#x5168;&#x90E8;</option><option v-for="value in relatedProducts" :key="value" :value="value">{{ value }}</option></select></label>
              <label class="field"><span>&#x5173;&#x8054;&#x6D3B;&#x52A8;</span><select v-model="relatedActivity"><option value="">&#x5168;&#x90E8;</option><option v-for="value in relatedActivities" :key="value" :value="value">{{ value }}</option></select></label>
              <label class="field"><span>&#x5173;&#x8054;&#x5C5E;&#x5730;&#x70ED;&#x70B9;</span><select v-model="relatedHotspot"><option value="">&#x5168;&#x90E8;</option><option v-for="value in relatedHotspots" :key="value" :value="value">{{ value }}</option></select></label>
              <button class="btn primary filter-query-inline" type="button" @click="applyTopicFilters">&#x67E5;&#x8BE2;</button>
              <button class="text-btn manual-topic-clear-filters" type="button" @click="topicIdFilter = ''; topicQuery = ''; topicMarketingFilter = ''; contentType = ''; relatedProduct = ''; relatedActivity = ''; relatedHotspot = ''">&#x6E05;&#x7A7A;&#x7B5B;&#x9009;</button>
            </div>
            <div class="manual-topic-list-meta"><b>&#x7B26;&#x5408;&#x6761;&#x4EF6; {{ filteredTopics.length }} &#x4E2A;</b></div>
            <LoadingSkeleton v-if="catalogLoading || !store.initialized" />
            <div v-else ref="topicListRef" class="table-wrap manual-topic-table"><table><thead><tr><th class="manual-topic-checkbox-cell">选择</th><th>&#x9009;&#x9898; ID</th><th>&#x9009;&#x9898;&#x6807;&#x9898;</th><th>&#x9009;&#x9898;&#x5927;&#x7EB2;</th><th>&#x9009;&#x9898;&#x7C7B;&#x578B;</th><th>&#x5185;&#x5BB9;&#x7C7B;&#x578B;</th><th>&#x5173;&#x8054;&#x4EA7;&#x54C1;</th><th>&#x5173;&#x8054;&#x6D3B;&#x52A8;</th><th>&#x5173;&#x8054;&#x5C5E;&#x5730;&#x70ED;&#x70B9;</th><th>&#x6709;&#x6548;&#x671F;</th></tr></thead><tbody>
              <tr v-for="topic in pagedTopics" :key="topic.topic_id" :class="{ selected: selectedTopicIds.includes(topic.topic_id) }" class="selection-row" tabindex="0" :aria-disabled="topicReview || (!selectedTopicIds.includes(topic.topic_id) && selectedTopicIds.length >= 100) || undefined" @click="toggleTopicRow(topic.topic_id, $event)" @keydown.enter.self.prevent="toggleTopicRow(topic.topic_id, $event)" @keydown.space.self.prevent="toggleTopicRow(topic.topic_id, $event)"><td class="manual-topic-checkbox-cell"><input type="checkbox" :checked="selectedTopicIds.includes(topic.topic_id)" :disabled="topicReview || (!selectedTopicIds.includes(topic.topic_id) && selectedTopicIds.length >= 100)" :aria-label="`选择选题 ${topic.topic_title}`" @change="setTopicSelected(topic.topic_id, ($event.target as HTMLInputElement).checked)" /></td><td>{{ topic.topic_id }}</td><td><HoverHint :text="topic.topic_title" :show-icon="false" class="manual-topic-title-tooltip"><span class="manual-topic-title-value">{{ topic.topic_title }}</span></HoverHint></td><td><div class="manual-topic-outline-value" :title="topic.outline || '暂无选题大纲'">{{ topic.outline || '\u6682\u65e0\u9009\u9898\u5927\u7eb2' }}</div></td><td><span class="topic-type-badge" :class="topic.is_marketing ? 'marketing' : 'non-marketing'">{{ topic.is_marketing ? '营销' : '非营销' }}</span></td><td>{{ topic.content_type || '\u2014' }}</td><td>{{ topic.related_product || '\u2014' }}</td><td>{{ topic.related_activity || '\u2014' }}</td><td>{{ topic.related_hotspot || '\u2014' }}</td><td><span class="manual-topic-validity">{{ topic.valid_from ? topic.valid_from.slice(0, 10) : '&#x4E0D;&#x9650;' }}<i>&#x81F3;</i>{{ topic.valid_to ? topic.valid_to.slice(0, 10) : '&#x4E0D;&#x9650;' }}</span></td></tr>
              <tr v-if="filteredTopics.length === 0"><td colspan="10"><div class="empty-state">&#x6CA1;&#x6709;&#x7B26;&#x5408;&#x6761;&#x4EF6;&#x7684;&#x53EF;&#x7528;&#x9009;&#x9898;</div></td></tr>
            </tbody></table></div>
            <ListPagination v-model:page="topicPage" v-model:page-size="topicPageSize" :total="filteredTopics.length" unit="&#x4E2A;&#x9009;&#x9898;" :page-size-options="[20, 50, 100]" class="manual-topic-pagination" />
          </section>
        </div>
        <div class="footer-actions manual-step-actions"><template v-if="topicReview"><div class="manual-step-review" role="status"><span class="manual-step-review-icon" aria-hidden="true">✓</span><strong>本次选择了 <em>{{ selectedTopicIds.length }}</em> 个选题进行策划，如需调整，请返回调整</strong><button class="btn" type="button" @click="topicReview = false">返回调整</button><button class="btn primary" type="button" @click="confirmTopicReview">下一步</button></div></template><template v-else><button class="btn" type="button" @click="returnToStep(2)">上一步</button><button class="btn primary" type="button" :disabled="!selectedTopicIds.length" @click="saveTopicStep">保存</button></template></div>
      </div>
    </section>

    <section v-else key="manual-step-submit" class="card">
      <div class="card-head"><div><h2>确认策划</h2></div></div>
      <div class="card-body manual-step-body">
        <div class="manual-submit-summary">
          <div><span>任务名称</span><b>{{ taskName }}</b></div><div><span>投放日期</span><b>{{ publishDate }}</b></div><div><span>策划账号</span><b class="manual-review-total">{{ selectedAccounts.length }} <small>个</small></b></div><div><span>选题</span><b class="manual-review-total">{{ selectedTopics.length }} <small>个</small></b></div>
        </div>
        <div class="manual-submit-groups">
          <section class="manual-submit-group">
            <div class="manual-submit-group-head"><h3>本次策划账号</h3><span>{{ selectedAccounts.length }} 个</span></div>
            <div class="manual-submit-items manual-submit-table">
              <table class="manual-submit-account-table">
                <colgroup><col style="width:45%" /><col style="width:32%" /><col style="width:23%" /></colgroup>
                <thead><tr><th>账号名称</th><th>属主 UM 号</th><th>账号类型</th></tr></thead>
                <tbody><tr v-for="account in submitAccountsPage" :key="account.account_id">
                  <td><HoverHint :text="account.account_name" :show-icon="false" overflow-only class="manual-submit-tooltip"><span class="manual-submit-truncate account-name">{{ account.account_name }}</span></HoverHint></td>
                  <td><HoverHint :text="account.um_no || '—'" :show-icon="false" overflow-only class="manual-submit-tooltip"><span class="manual-submit-truncate identifier">{{ account.um_no || '—' }}</span></HoverHint></td>
                  <td><AccountTypeBadge :type="account.account_type || (account.certified === true ? '认证' : account.certified === false ? '非认证' : '')" /></td>
                </tr></tbody>
              </table>
            </div>
            <ListPagination v-model:page="submitAccountPage" v-model:page-size="submitAccountPageSize" :total="selectedAccounts.length" unit="个账号" :page-size-options="[10, 20, 50]" class="manual-submit-pagination" />
          </section>
          <section class="manual-submit-group">
            <div class="manual-submit-group-head"><h3>本次使用选题</h3><span>{{ selectedTopics.length }} 个</span></div>
            <div class="manual-submit-items manual-submit-table">
              <table class="manual-submit-topic-table">
                <colgroup><col style="width:21%" /><col style="width:27%" /><col style="width:34%" /><col style="width:18%" /></colgroup>
                <thead><tr><th>选题 ID</th><th>选题标题</th><th>选题大纲</th><th>内容类型</th></tr></thead>
                <tbody><tr v-for="(topic, index) in submitTopicsPage" :key="`${(submitTopicPage - 1) * submitTopicPageSize + index}-${topic.topic_id}`">
                  <td><HoverHint :text="topic.topic_id" :show-icon="false" overflow-only class="manual-submit-tooltip"><span class="manual-submit-truncate identifier">{{ topic.topic_id }}</span></HoverHint></td>
                  <td><HoverHint :text="topic.topic_title" :show-icon="false" overflow-only class="manual-submit-tooltip"><span class="manual-submit-truncate topic-title">{{ topic.topic_title }}</span></HoverHint></td>
                  <td><HoverHint :text="topic.outline || '暂无选题大纲'" :show-icon="false" overflow-only class="manual-submit-tooltip"><span class="manual-submit-truncate topic-outline">{{ topic.outline || '暂无选题大纲' }}</span></HoverHint></td>
                  <td><HoverHint :text="topic.content_type || '—'" :show-icon="false" overflow-only class="manual-submit-tooltip"><span class="manual-submit-truncate">{{ topic.content_type || '—' }}</span></HoverHint></td>
                </tr></tbody>
              </table>
            </div>
            <ListPagination v-model:page="submitTopicPage" v-model:page-size="submitTopicPageSize" :total="selectedTopics.length" unit="个选题" :page-size-options="[10, 20, 50]" class="manual-submit-pagination" />
          </section>
        </div>        <div class="footer-actions manual-step-actions"><button class="btn" type="button" @click="returnToStep(3)">上一步</button><button class="btn primary" type="button" :disabled="!canSubmit" @click="submit"><span v-if="busy" class="loading-spinner" aria-hidden="true" />{{ busy ? '正在提交…' : '提交手动策划' }}</button></div>
      </div>
    </section>
    </Transition>
  </template>

  <Teleport to="body">
    <Transition name="manual-planned-tooltip">
      <div v-if="plannedAccountTooltip" id="manual-planned-account-tooltip" class="manual-planned-tooltip" role="tooltip" :style="{ left: `${plannedAccountTooltip.left}px`, top: `${plannedAccountTooltip.top}px` }">
        <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><circle cx="10" cy="10" r="7.3" stroke="currentColor" stroke-width="1.4" /><path d="M10 9v4m0-7v.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" /></svg>
        <span>{{ publishDate }} 已手动策划，不可重复选择</span>
      </div>
    </Transition>
  </Teleport>

  <Teleport to="body">
    <Transition name="manual-eligibility-modal">
      <div v-if="eligibilityNotice" class="manual-eligibility-mask" @click.self="closeEligibilityNotice()">
        <section class="manual-eligibility-dialog" role="alertdialog" aria-modal="true" aria-labelledby="manual-eligibility-title" aria-describedby="manual-eligibility-description">
          <span class="manual-eligibility-icon" aria-hidden="true">!</span>
          <h2 id="manual-eligibility-title">选题资格不匹配</h2>
          <p id="manual-eligibility-description">{{ eligibilityNotice }}</p>
          <div class="manual-eligibility-actions"><button class="btn" type="button" @click="closeEligibilityNotice()">知道了</button><button class="btn primary" type="button" @click="closeEligibilityNotice(true)">返回修改选择</button></div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.manual-stepper{display:flex;gap:0;align-items:center;min-height:64px;padding:10px 24px;margin-bottom:20px;border:1px solid var(--neutral-200);border-radius:8px;background:var(--neutral-50);scroll-margin-top:88px}
.manual-step{display:flex;flex:1;align-items:center;gap:8px;min-height:44px;padding:0;border:0;background:transparent;color:var(--neutral-400);font-size:14px;font-weight:500;text-align:left}
.manual-step b{font-weight:500}
.manual-step:not(:last-child)::after{content:'';flex:1;height:1px;margin:0 16px;background:var(--neutral-200)}
.manual-step>span{display:grid;place-items:center;flex:none;width:28px;height:28px;border:1px solid var(--neutral-200);border-radius:50%;background:var(--surface);color:var(--neutral-400);font-size:13px;font-variant-numeric:tabular-nums}
.manual-step.active{color:var(--neutral-900)}
.manual-step.active>span{border-color:var(--primary-600);background:var(--primary-600);color:var(--surface)}
.manual-step.done{color:var(--neutral-700)}
.manual-step.done>span{background:var(--primary-50);border-color:var(--primary-200);color:var(--primary-600)}
.manual-step:disabled{opacity:1;cursor:default}
.manual-eligibility-mask{position:fixed;inset:0;z-index:100;display:grid;place-items:center;padding:20px;background:var(--mask)}
.manual-eligibility-dialog{width:min(440px,100%);padding:24px;border:1px solid var(--neutral-200);border-radius:16px;background:var(--surface);box-shadow:var(--shadow-4)}
.manual-eligibility-icon{display:grid;place-items:center;width:36px;height:36px;border-radius:50%;background:var(--danger-bg);color:var(--danger);font-size:18px;font-weight:700}
.manual-eligibility-dialog h2{margin:16px 0 8px;color:var(--neutral-900);font-size:18px;line-height:26px}
.manual-eligibility-dialog p{margin:0;color:var(--neutral-600);font-size:14px;line-height:22px}
.manual-eligibility-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:24px}
.manual-eligibility-modal-enter-active,.manual-eligibility-modal-leave-active{transition:opacity .16s ease}
.manual-eligibility-modal-enter-from,.manual-eligibility-modal-leave-to{opacity:0}
.manual-task-card .card-head{padding:20px 24px}
.manual-task-card table{min-width:1220px}
.manual-task-card th{padding:13px 16px;background:var(--neutral-50);color:var(--neutral-500);font-weight:500}
.manual-task-card td{height:52px;padding:12px 16px;color:var(--neutral-600);font-size:14px;line-height:22px;font-variant-numeric:tabular-nums}
.manual-task-card tbody tr:nth-child(even){background:var(--surface)}
.manual-task-card tbody tr:hover{background:var(--hover-bg)}
.manual-task-card tbody tr.has-failures{background:var(--processing-row)}
.manual-task-card tbody tr.has-failures:hover{background:var(--processing-bg)}
.manual-task-card th:nth-child(n+3):nth-child(-n+6),.manual-task-card td:nth-child(n+3):nth-child(-n+6){text-align:center;white-space:nowrap}
.manual-task-card td:first-child{min-width:150px;max-width:220px;color:var(--neutral-700);font-weight:500;overflow-wrap:anywhere}
.manual-task-card th:last-child,.manual-task-card td:last-child{position:sticky;right:0;min-width:148px;background:var(--surface);box-shadow:-1px 0 0 var(--neutral-200)}
.manual-task-card th:last-child{z-index:2;background:var(--neutral-50)}
.manual-task-card tr:hover td:last-child{background:var(--hover-bg)}
.manual-task-card tr.has-failures td:last-child{background:var(--surface)}
.manual-task-card td:nth-child(2){white-space:nowrap}
.manual-task-card td:nth-child(9),.manual-task-card td:nth-child(10){font-size:13px;line-height:20px;color:var(--neutral-500);white-space:nowrap}
.manual-task-card .page-actions{flex-wrap:nowrap;gap:12px;white-space:nowrap}
.manual-task-card .tag{padding:3px 8px;border-radius:6px;font-size:12px;font-weight:500;white-space:nowrap}
.manual-task-card td:nth-child(8) .tag.gray{padding:0;background:transparent;color:var(--neutral-400);font-weight:400}
.manual-task-card td.manual-task-count{color:var(--neutral-400);font-size:13px;font-weight:400}
.manual-task-card td.manual-task-count.completed{color:var(--success);font-weight:600}
.manual-task-card td.manual-task-count.failed{color:var(--danger);font-weight:600}
.topic-type-badge{display:inline-flex;align-items:center;min-height:22px;padding:1px 7px;border-radius:5px;font-size:12px;line-height:18px;white-space:nowrap}.topic-type-badge.marketing{background:var(--primary-50);color:var(--primary-600)}.topic-type-badge.non-marketing{background:var(--neutral-100);color:var(--neutral-600)}
.manual-page-head{align-items:center}.manual-head-actions{display:flex;align-items:center;gap:8px}.manual-stepper{display:flex;align-items:center;gap:0;margin:0 0 18px;padding:16px 22px;border:1px solid var(--neutral-200);border-radius:10px;background:var(--surface);scroll-margin-top:76px}.manual-step{display:flex;align-items:center;gap:9px;flex:1;color:var(--neutral-400);font-size:13px}.manual-step:not(:last-child)::after{content:'';height:1px;flex:1;margin:0 16px;background:#e5e9f0}.manual-step span{display:grid;place-items:center;width:26px;height:26px;border-radius:50%;background:var(--neutral-100);font-weight:600}.manual-step.active{color:var(--primary-600)}.manual-step.active span,.manual-step.done span{background:var(--primary-600);color:var(--surface)}.manual-step.done{color:var(--neutral-700)}.manual-create-meta{display:flex;align-items:flex-end;gap:12px;flex-wrap:wrap;margin-bottom:18px}.manual-create-meta .field{min-width:180px}.manual-account-filters,.manual-topic-filters{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));align-items:end;gap:12px;margin-bottom:18px}.manual-account-filters .field,.manual-topic-filters .field{min-width:0}.manual-account-filters input,.manual-account-filters select,.manual-topic-filters input,.manual-topic-filters select{box-sizing:border-box;width:100%;height:36px;padding:0 10px;border:1px solid var(--neutral-200);border-radius:7px;background:var(--surface);color:var(--neutral-900)}.manual-follower-range{display:flex;align-items:center;gap:8px;height:36px;padding:0 9px;border:1px solid var(--neutral-200);border-radius:7px;background:var(--surface)}.manual-follower-range input{width:50%;min-width:0;height:32px;padding:0;border:0;border-radius:0;outline:0}.manual-follower-range i,.manual-topic-validity i{color:var(--neutral-400);font-size:12px;font-style:normal;white-space:nowrap}.manual-selection-modes{display:flex;gap:4px;width:max-content;margin:0 0 16px;padding:4px;border-radius:8px;background:var(--neutral-100)}.manual-mode-tab{min-width:104px;padding:8px 14px;border:0;border-radius:6px;background:transparent;color:var(--neutral-500);cursor:pointer}.manual-mode-tab.active{background:var(--surface);color:var(--primary-600);box-shadow:0 1px 3px #1018281a;font-weight:600}.manual-upload-panel{display:grid;grid-template-columns:1fr auto;gap:14px;align-items:center;padding:16px;border:1px dashed var(--neutral-300);border-radius:9px;background:var(--neutral-50)}.manual-upload-panel p{margin:6px 0 0;color:var(--neutral-400);font-size:12px}.manual-upload-actions{display:flex;gap:8px}.manual-file-input{display:none}.manual-import-result{grid-column:1/-1;padding-top:12px;border-top:1px solid var(--neutral-200);color:var(--success);font-size:13px}.manual-import-result span{color:var(--processing)}.manual-unknown-list{margin-top:5px;max-height:90px;overflow:auto;color:var(--processing);font-size:12px;line-height:1.6}.manual-account-counts{display:flex;align-items:center;gap:16px;flex-wrap:wrap}.manual-account-counts strong{color:var(--neutral-700);font-weight:600}.manual-account-counts .manual-planned-count,.manual-account-counts .manual-planned-count strong{color:var(--processing)}.manual-account-list-meta,.manual-topic-list-meta{display:flex;justify-content:space-between;align-items:center;margin:0 0 8px;font-size:13px}.manual-account-list-meta span,.manual-topic-list-meta span{color:var(--neutral-400);font-size:12px}.manual-account-table,.manual-topic-table{max-height:430px;overflow:auto;border:1px solid var(--neutral-200);border-radius:8px}.manual-account-table table{min-width:1120px}.manual-topic-table table{min-width:1160px}.manual-account-table thead th,.manual-topic-table thead th{position:sticky;top:0;z-index:1;background:var(--neutral-50);white-space:nowrap}.manual-account-table tbody tr:hover,.manual-account-table tbody tr.selected,.manual-topic-table tbody tr:hover,.manual-topic-table tbody tr.selected{background:var(--primary-50)}.manual-account-table input,.manual-topic-table input{accent-color:var(--primary-600)}.manual-account-table tbody tr.already-planned,.manual-account-table tbody tr.already-planned:hover{background:var(--neutral-50);color:var(--neutral-400);cursor:not-allowed}.manual-account-table tbody tr.already-planned input{pointer-events:none}.manual-account-pagination,.manual-topic-pagination{margin:14px 0 18px}.manual-topic-outline{display:block;max-width:360px;margin-top:4px;color:var(--neutral-400);font-size:11px;line-height:1.5;white-space:normal}.manual-topic-validity{display:flex;align-items:center;gap:5px;white-space:nowrap;font-size:12px}.manual-step-change-enter-active,.manual-step-change-leave-active{transition:opacity .2s ease,transform .2s ease}.manual-step-change-enter-from{opacity:0;transform:translateY(8px)}.manual-step-change-leave-to{opacity:0;transform:translateY(-5px)}.manual-step-review{display:flex;align-items:center;gap:10px;flex:1;min-width:0;padding:10px 12px;border:1px solid var(--primary-100);border-radius:8px;background:var(--primary-50)}.manual-step-review-icon{display:grid;place-items:center;flex:none;width:24px;height:24px;border-radius:50%;background:var(--primary-50);color:var(--primary-600);font-size:14px;font-weight:700}.manual-step-review>strong{flex:1;min-width:0;color:var(--neutral-700);font-size:13px;font-weight:500;line-height:1.5}.manual-step-review>strong em{display:inline-block;margin:0 2px;color:var(--primary-600);font-size:20px;font-style:normal;font-weight:700;font-variant-numeric:tabular-nums;line-height:1;vertical-align:-1px}.manual-submit-summary{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.manual-submit-summary>div{display:flex;flex-direction:column;gap:6px;padding:14px;border:1px solid var(--neutral-200);border-radius:8px}.manual-submit-summary span,.manual-submit-group-head h3{color:var(--neutral-400);font-size:12px}.manual-submit-groups{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:18px}.manual-submit-group{min-width:0;padding:14px;border:1px solid var(--neutral-200);border-radius:9px;background:var(--surface)}.manual-submit-group-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:9px}.manual-submit-group-head h3{margin:0;color:var(--neutral-700);font-size:13px}.manual-submit-group-head>span{color:var(--primary-600);font-size:12px;font-weight:600}.manual-review-total{color:var(--primary-600);font-size:22px;font-variant-numeric:tabular-nums}.manual-review-total small{font-size:12px;font-weight:500}.manual-review-items{display:flex;flex-direction:column;max-height:300px;overflow:auto;border-top:1px solid var(--neutral-200)}.manual-submit-items{height:300px;overflow-y:scroll;scrollbar-gutter:stable}.manual-submit-pagination{margin-top:10px}.manual-review-item{display:flex;flex-direction:column;gap:4px;padding:9px 2px;border-bottom:1px solid var(--neutral-100)}.manual-review-item:last-child{border-bottom:0}.manual-review-item>b{color:var(--neutral-700);font-size:13px;line-height:1.45;overflow-wrap:anywhere}.manual-review-item>small{color:var(--neutral-400);font-size:11px;line-height:1.4;overflow-wrap:anywhere}.manual-task-card .table-wrap{max-height:calc(100vh - 260px);overflow:auto}.manual-planned-tooltip{position:fixed;z-index:80;display:flex;align-items:center;gap:8px;width:min(304px,calc(100vw - 24px));padding:10px 12px;border:1px solid #ffffff12;border-radius:8px;background:var(--neutral-950);color:var(--surface);box-shadow:0 6px 20px #11223d26;font-size:12px;line-height:1.6;white-space:nowrap;pointer-events:none}.manual-planned-tooltip svg{flex:none;width:16px;height:16px;color:var(--neutral-300)}.manual-planned-tooltip-enter-active,.manual-planned-tooltip-leave-active{transition:opacity .12s ease}.manual-planned-tooltip-enter-from,.manual-planned-tooltip-leave-to{opacity:0}.manual-selected-count{color:var(--primary-600);font-weight:600}.manual-availability-error{display:flex;align-items:center;justify-content:space-between;gap:12px}
@media(max-width:900px){.manual-account-filters,.manual-topic-filters{grid-template-columns:repeat(2,minmax(0,1fr))}.manual-submit-groups{grid-template-columns:1fr}}
@media(max-width:580px){.manual-account-filters,.manual-topic-filters,.manual-submit-summary{grid-template-columns:1fr}.manual-topic-list-meta{align-items:flex-start;gap:6px;flex-direction:column}.manual-stepper{padding:12px;scroll-margin-top:124px}.manual-step{gap:5px;font-size:11px}.manual-step:not(:last-child)::after{margin:0 7px}.manual-step span{width:22px;height:22px}.manual-create-meta{align-items:stretch;flex-direction:column}.manual-create-meta .field{min-width:0}.manual-step-review{flex-wrap:wrap}.manual-step-review>strong{flex-basis:calc(100% - 36px)}.manual-step-review .btn{flex:1}.manual-upload-panel{grid-template-columns:1fr}.manual-upload-actions{flex-wrap:wrap}}
@media(prefers-reduced-motion:reduce){.manual-step-change-enter-active,.manual-step-change-leave-active{transition:none}}
</style>

<style scoped>
.manual-head-actions{margin-left:auto}
.topic-filters-toggle{display:flex;justify-content:flex-end;margin-bottom:12px}.manual-topic-filters .field{width:100%}
.manual-topic-table :deep(.manual-topic-title-tooltip){display:flex;width:100%;min-width:0;color:var(--neutral-800);font-size:13px;font-weight:500;text-align:left;line-height:1.6}
.manual-topic-table :deep(.manual-topic-title-tooltip:hover),.manual-topic-table :deep(.manual-topic-title-tooltip:focus-visible){color:var(--neutral-800);text-decoration:none}
.manual-submit-table{overflow:auto;border:1px solid var(--neutral-200);border-radius:6px}
.manual-submit-table table{width:100%;min-width:0;table-layout:fixed}
.manual-submit-table th,.manual-submit-table td{padding:10px 8px;text-align:left;font-size:12px}
.manual-submit-table th{position:sticky;top:0;z-index:1;background:var(--neutral-50);white-space:nowrap}
.manual-submit-table :deep(.manual-submit-tooltip){width:100%;min-width:0;text-align:left;font-size:12px;color:var(--neutral-700)}
.manual-submit-truncate{display:block;min-width:0;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.manual-submit-truncate.account-name,.manual-submit-truncate.topic-title{font-weight:500;color:var(--neutral-800)}
.manual-submit-truncate.identifier{font-variant-numeric:tabular-nums;color:var(--neutral-500)}
.manual-submit-truncate.topic-outline{color:var(--neutral-600)}
.manual-topic-table table{min-width:1328px}.manual-topic-table .manual-topic-checkbox-cell{width:48px;min-width:48px;padding:0 12px;text-align:center}.manual-topic-checkbox-cell input{vertical-align:middle}.manual-topic-table td:nth-child(3){width:220px;max-width:220px}.manual-topic-table td:nth-child(4){width:300px;max-width:300px}.manual-topic-title-value,.manual-topic-outline-value{display:block;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.manual-topic-outline-value{color:var(--neutral-600);font-size:12px}
.manual-account-mode-row{display:flex;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:16px}.manual-account-mode-row>.field{min-width:180px;margin:0}.manual-account-mode-row .manual-selection-modes{align-self:flex-end;margin:0}
@media(max-width:580px){.manual-account-mode-row{align-items:stretch;flex-direction:column;gap:10px}.manual-account-mode-row>.field{min-width:0}.manual-account-mode-row .manual-selection-modes{width:100%}.manual-account-mode-row .manual-mode-tab{flex:1}}
</style>

<style scoped>
.manual-filter-actions{display:flex;align-self:end;justify-self:start}.manual-topic-filter-actions{grid-column:1/-1;display:flex;justify-content:flex-end;gap:8px}.filter-query-inline{align-self:end;justify-self:start}
.manual-selection-lock{min-width:0;margin:0;padding:0;border:0}.manual-selection-lock:disabled{opacity:.78}.manual-count-difference{flex:none;padding:3px 8px;border-radius:5px;background:#fff4e5;color:#b54708;font-size:12px;font-weight:600}
.manual-topic-picker{display:grid;grid-template-columns:minmax(250px,300px) minmax(0,1fr);gap:16px;align-items:start}.manual-topic-picker-available{min-width:0}.manual-topic-picker-available .manual-topic-pagination{margin-bottom:0}.manual-topic-picked{position:sticky;top:16px;min-width:0;overflow:hidden;border:1px solid var(--neutral-200);border-radius:9px;background:var(--surface)}.manual-topic-picked-head{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:13px 14px;border-bottom:1px solid var(--neutral-100);color:var(--neutral-700);font-size:13px}.manual-topic-picked-head span{color:var(--primary-600);font-size:12px;font-variant-numeric:tabular-nums;font-weight:600}.manual-topic-picked-list{max-height:480px;overflow:auto;padding:0 14px}.manual-topic-picked-item{display:flex;align-items:flex-start;gap:8px;padding:11px 0;border-bottom:1px solid var(--neutral-100)}.manual-topic-picked-item:last-child{border-bottom:0}.manual-topic-picked-item>div{flex:1;min-width:0}.manual-topic-picked-item b{display:block;color:var(--neutral-800);font-size:13px;line-height:1.45;overflow-wrap:anywhere}.manual-topic-picked-item small{display:block;margin-top:4px;color:var(--neutral-400);font-size:11px}.manual-topic-picked-item .remove-topic{flex:none;margin-top:-3px}.manual-topic-picked-empty{display:grid;min-height:110px;place-items:center;color:var(--neutral-400);font-size:12px}
.manual-step-body{padding-bottom:104px}.manual-step-actions{position:fixed;z-index:35;right:0;bottom:0;left:var(--sidebar-width);display:flex;align-items:center;justify-content:flex-end;min-height:68px;margin:0;padding:12px 32px calc(12px + env(safe-area-inset-bottom));border-top:1px solid var(--neutral-200);background:color-mix(in srgb,var(--surface) 94%,transparent);box-shadow:0 -6px 20px #1018280a;backdrop-filter:blur(10px)}
@media(max-width:900px){.manual-topic-picker{grid-template-columns:240px minmax(0,1fr);gap:12px}}
@media(max-width:780px){.manual-step-actions{padding-right:24px;padding-left:24px}}
@media(max-width:700px){.manual-topic-picker{grid-template-columns:1fr}.manual-topic-picked{position:static;grid-row:1}.manual-topic-picked-list{max-height:240px}}
@media(max-width:580px){.manual-step-body{padding-bottom:124px}.manual-step-actions{min-height:76px;padding:10px 12px calc(10px + env(safe-area-inset-bottom))}.manual-step-actions .manual-step-review{width:100%;flex-wrap:wrap}.manual-step-actions .manual-step-review>strong{flex-basis:calc(100% - 36px)}.manual-step-actions .manual-step-review .btn{flex:1}}
</style>
