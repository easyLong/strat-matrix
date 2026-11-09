<script>
import QueryActions from '../QueryActions.vue';
import AccountTypeBadge from '../AccountTypeBadge.vue';
import ListPagination from '../ListPagination.vue';
import LoadingSkeleton from '../LoadingSkeleton.vue';
export default {
  props: {
    selection: {
      required: true,
      type: null
    },
    marketing: {
      required: true,
      type: Boolean
    },
    publishDate: {
      required: true,
      type: String
    },
    busy: {
      required: true,
      type: Boolean
    },
    loading: {
      required: true,
      type: Boolean
    },
    initialized: {
      required: true,
      type: Boolean
    }
  },
  components: {
    QueryActions,
    LoadingSkeleton,
    AccountTypeBadge,
    ListPagination
  },
  computed: {
    isMarketing: {
      get() {
        return this['marketing'];
      },
      set(value) {
        this['marketing'] = value;
      }
    },
    sampledIds: {
      get() {
        return this.selection.sampledIds;
      },
      set(value) {
        this.selection.sampledIds = value;
      }
    },
    accountReview: {
      get() {
        return this.selection.accountReview;
      },
      set(value) {
        this.selection.accountReview = value;
      }
    },
    accountSelectionMode: {
      get() {
        return this.selection.accountSelectionMode;
      },
      set(value) {
        this.selection.accountSelectionMode = value;
      }
    },
    setAccountSelectionMode: {
      get() {
        return this.selection.setAccountSelectionMode;
      },
      set(value) {
        this.selection.setAccountSelectionMode = value;
      }
    },
    accountPage: {
      get() {
        return this.selection.accountPage;
      },
      set(value) {
        this.selection.accountPage = value;
      }
    },
    availabilityReady: {
      get() {
        return this.selection.availabilityReady;
      },
      set(value) {
        this.selection.availabilityReady = value;
      }
    },
    availabilityLoading: {
      get() {
        return this.selection.availabilityLoading;
      },
      set(value) {
        this.selection.availabilityLoading = value;
      }
    },
    isAccountPlanned: {
      get() {
        return this.selection.isAccountPlanned;
      },
      set(value) {
        this.selection.isAccountPlanned = value;
      }
    },
    targetCount: {
      get() {
        return this.selection.targetCount;
      },
      set(value) {
        this.selection.targetCount = value;
      }
    },
    targetCountError: {
      get() {
        return this.selection.targetCountError;
      },
      set(value) {
        this.selection.targetCountError = value;
      }
    },
    lifecycleFilter: {
      get() {
        return this.selection.lifecycleFilter;
      },
      set(value) {
        this.selection.lifecycleFilter = value;
      }
    },
    lifecycleOptions: {
      get() {
        return this.selection.lifecycleOptions;
      },
      set(value) {
        this.selection.lifecycleOptions = value;
      }
    },
    followersMin: {
      get() {
        return this.selection.followersMin;
      },
      set(value) {
        this.selection.followersMin = value;
      }
    },
    followersMax: {
      get() {
        return this.selection.followersMax;
      },
      set(value) {
        this.selection.followersMax = value;
      }
    },
    accountTypeFilter: {
      get() {
        return this.selection.accountTypeFilter;
      },
      set(value) {
        this.selection.accountTypeFilter = value;
      }
    },
    organizationFilter: {
      get() {
        return this.selection.organizationFilter;
      },
      set(value) {
        this.selection.organizationFilter = value;
      }
    },
    organizationOptions: {
      get() {
        return this.selection.organizationOptions;
      },
      set(value) {
        this.selection.organizationOptions = value;
      }
    },
    platformFilter: {
      get() {
        return this.selection.platformFilter;
      },
      set(value) {
        this.selection.platformFilter = value;
      }
    },
    platformOptions: {
      get() {
        return this.selection.platformOptions;
      },
      set(value) {
        this.selection.platformOptions = value;
      }
    },
    keyword: {
      get() {
        return this.selection.keyword;
      },
      set(value) {
        this.selection.keyword = value;
      }
    },
    umNoFilter: {
      get() {
        return this.selection.umNoFilter;
      },
      set(value) {
        this.selection.umNoFilter = value;
      }
    },
    applyAccountFilters: {
      get() {
        return this.selection.applyAccountFilters;
      },
      set(value) {
        this.selection.applyAccountFilters = value;
      }
    },
    accountSelectionPool: {
      get() {
        return this.selection.accountSelectionPool;
      },
      set(value) {
        this.selection.accountSelectionPool = value;
      }
    },
    matchingAccounts: {
      get() {
        return this.selection.matchingAccounts;
      },
      set(value) {
        this.selection.matchingAccounts = value;
      }
    },
    downloadAccountTemplate: {
      get() {
        return this.selection.downloadAccountTemplate;
      },
      set(value) {
        this.selection.downloadAccountTemplate = value;
      }
    },
    importFileInput: {
      get() {
        return this.selection.importFileInput;
      },
      set(value) {
        this.selection.importFileInput = value;
      }
    },
    importAccountsByIdentifier: {
      get() {
        return this.selection.importAccountsByIdentifier;
      },
      set(value) {
        this.selection.importAccountsByIdentifier = value;
      }
    },
    importDataRowCount: {
      get() {
        return this.selection.importDataRowCount;
      },
      set(value) {
        this.selection.importDataRowCount = value;
      }
    },
    importMatchedCount: {
      get() {
        return this.selection.importMatchedCount;
      },
      set(value) {
        this.selection.importMatchedCount = value;
      }
    },
    importDuplicateRows: {
      get() {
        return this.selection.importDuplicateRows;
      },
      set(value) {
        this.selection.importDuplicateRows = value;
      }
    },
    importUnmatchedRows: {
      get() {
        return this.selection.importUnmatchedRows;
      },
      set(value) {
        this.selection.importUnmatchedRows = value;
      }
    },
    importPlannedRows: {
      get() {
        return this.selection.importPlannedRows;
      },
      set(value) {
        this.selection.importPlannedRows = value;
      }
    },
    hasImportIssues: {
      get() {
        return this.selection.hasImportIssues;
      },
      set(value) {
        this.selection.hasImportIssues = value;
      }
    },
    importErrorCount: {
      get() {
        return this.selection.importErrorCount;
      },
      set(value) {
        this.selection.importErrorCount = value;
      }
    },
    showImportIssues: {
      get() {
        return this.selection.showImportIssues;
      },
      set(value) {
        this.selection.showImportIssues = value;
      }
    },
    importIssueDialogOpen: {
      get() {
        return this.selection.importIssueDialogOpen;
      },
      set(value) {
        this.selection.importIssueDialogOpen = value;
      }
    },
    importDialogClose: {
      get() {
        return this.selection.importDialogClose;
      },
      set(value) {
        this.selection.importDialogClose = value;
      }
    },
    importTrigger: {
      get() {
        return this.selection.importTrigger;
      },
      set(value) {
        this.selection.importTrigger = value;
      }
    },
    availableMatchingCount: {
      get() {
        return this.selection.availableMatchingCount;
      },
      set(value) {
        this.selection.availableMatchingCount = value;
      }
    },
    plannedMatchingCount: {
      get() {
        return this.selection.plannedMatchingCount;
      },
      set(value) {
        this.selection.plannedMatchingCount = value;
      }
    },
    accountListRef: {
      get() {
        return this.selection.accountListRef;
      },
      set(value) {
        this.selection.accountListRef = value;
      }
    },
    plannedAccountTooltip: {
      get() {
        return this.selection.plannedAccountTooltip;
      },
      set(value) {
        this.selection.plannedAccountTooltip = value;
      }
    },
    allAccountsSelected: {
      get() {
        return this.selection.allAccountsSelected;
      },
      set(value) {
        this.selection.allAccountsSelected = value;
      }
    },
    someAccountsSelected: {
      get() {
        return this.selection.someAccountsSelected;
      },
      set(value) {
        this.selection.someAccountsSelected = value;
      }
    },
    selectAllAccounts: {
      get() {
        return this.selection.selectAllAccounts;
      },
      set(value) {
        this.selection.selectAllAccounts = value;
      }
    },
    pagedAccounts: {
      get() {
        return this.selection.pagedAccounts;
      },
      set(value) {
        this.selection.pagedAccounts = value;
      }
    },
    visibleAccounts: {
      get() {
        return this.selection.visibleAccounts;
      },
      set(value) {
        this.selection.visibleAccounts = value;
      }
    },
    accountPageSize: {
      get() {
        return this.selection.accountPageSize;
      },
      set(value) {
        this.selection.accountPageSize = value;
      }
    },
    toggleAccountRow: {
      get() {
        return this.selection.toggleAccountRow;
      },
      set(value) {
        this.selection.toggleAccountRow = value;
      }
    },
    showPlannedAccountTooltip: {
      get() {
        return this.selection.showPlannedAccountTooltip;
      },
      set(value) {
        this.selection.showPlannedAccountTooltip = value;
      }
    },
    toggleAccount: {
      get() {
        return this.selection.toggleAccount;
      },
      set(value) {
        this.selection.toggleAccount = value;
      }
    },
    closeImportIssueDialog: {
      get() {
        return this.selection.closeImportIssueDialog;
      },
      set(value) {
        this.selection.closeImportIssueDialog = value;
      }
    },
    importRowLabel: {
      get() {
        return this.selection.importRowLabel;
      },
      set(value) {
        this.selection.importRowLabel = value;
      }
    },
    downloadImportIssues: {
      get() {
        return this.selection.downloadImportIssues;
      },
      set(value) {
        this.selection.downloadImportIssues = value;
      }
    },
    importIssueRows() {
      return [...this.importUnmatchedRows.map(row => ({
        ...row,
        tone: 'error',
        kind: '未能识别账号'
      })), ...this.importPlannedRows.map(row => ({
        ...row,
        tone: 'warning',
        kind: '已投放账号'
      })), ...this.importDuplicateRows.map(row => ({
        ...row,
        tone: 'warning',
        kind: '账号重复'
      }))].sort((a, b) => a.rowNumber - b.rowNumber);
    }
  },
  methods: {
    emit(...args) {
      return this.$emit(...args);
    },
    syncSelectionElements() {
      for (const key of ["importFileInput", "importTrigger", "accountListRef", "importDialogClose"]) this.selection[key] = this.$refs[key] || null;
    }
  },
  mounted() {
    this.syncSelectionElements();
  },
  updated() {
    this.syncSelectionElements();
  },
  beforeDestroy() {
    for (const key of ["importFileInput", "importTrigger", "accountListRef", "importDialogClose"]) if (this.selection[key] === this.$refs[key]) this.selection[key] = null;
  }
};
</script>
<template>
<div class="manual-account-step">
    <section key="manual-step-accounts" class="card">
      <div class="card-head"><div><h2>选择账号</h2></div></div>
      <div class="card-body manual-step-body">
        <fieldset class="manual-selection-lock" :disabled="accountReview">
        <div class="manual-account-selection-row">
          <div class="manual-account-selection-heading">账号选择方式</div>
          <div class="manual-selection-modes" role="tablist" aria-label="账号选择方式">
            <button :class="['manual-mode-tab', { active: accountSelectionMode === 'filter' }]" type="button" role="tab" :aria-selected="accountSelectionMode === 'filter'" @click="setAccountSelectionMode('filter')">维度筛选</button>
            <button :class="['manual-mode-tab', { active: accountSelectionMode === 'upload' }]" type="button" role="tab" :aria-selected="accountSelectionMode === 'upload'" @click="setAccountSelectionMode('upload')">模板导入</button>
          </div>
        </div>
        <label v-if="accountSelectionMode === 'filter'" class="field manual-plan-account-count"><span>计划账号数量 <em class="required-mark">✳</em></span><div class="manual-plan-account-input-wrap"><input v-model.number="targetCount" aria-label="计划账号数量" type="number" inputmode="numeric" min="1" max="1000" placeholder="请输入" :aria-invalid="Boolean(targetCountError)" :aria-describedby="targetCountError ? 'manual-target-count-error' : undefined" required /><small v-if="targetCountError" id="manual-target-count-error" class="field-error" role="alert">{{ targetCountError }}</small></div></label>
        <div v-if="accountSelectionMode === 'filter'" class="manual-account-filters query-filter-grid" data-query-filters="standard">
          <label class="field"><span>生命周期</span><select v-model="lifecycleFilter"><option value="">全部</option><option v-for="item in lifecycleOptions" :key="item" :value="item">{{ item }}</option></select></label>
          <label class="field manual-follower-field"><span>粉丝量</span><div class="manual-follower-range"><input v-model.number="followersMin" type="number" inputmode="numeric" min="0" placeholder="起始粉丝量" /><i>至</i><input v-model.number="followersMax" type="number" inputmode="numeric" min="0" placeholder="截止粉丝量" /></div></label>
          <label class="field"><span>账号类型</span><select v-model="accountTypeFilter" :disabled="isMarketing"><option v-if="!isMarketing" value="">全部</option><option value="认证">认证</option><option v-if="!isMarketing" value="非认证">非认证</option></select></label>
          <label class="field"><span>属主组织</span><select v-model="organizationFilter"><option value="">全部</option><option v-for="item in organizationOptions" :key="item" :value="item">{{ item }}</option></select></label>
          <label class="field"><span>平台</span><select v-model="platformFilter"><option value="">全部</option><option v-for="item in platformOptions" :key="item" :value="item">{{ item }}</option></select></label>
          <label class="field"><span>账号 ID 或昵称</span><input v-model="keyword" type="search" placeholder="请输入" /></label>
          <div class="query-filter-tail">
            <label class="field"><span>属主 UM 号</span><input v-model="umNoFilter" type="search" placeholder="请输入" /></label>
            <QueryActions @query="applyAccountFilters" @clear="lifecycleFilter=''; followersMin=null; followersMax=null; accountTypeFilter=''; organizationFilter=''; platformFilter=''; keyword=''; umNoFilter=''" />
          </div>
        </div>
        <div v-else class="manual-upload-panel">
          <div class="manual-upload-heading"><span class="upload-template-icon" aria-hidden="true">↥</span><div><b>上传账号模板</b><small>支持属主 UM 号或账号 ID</small></div></div>
          <div class="manual-upload-actions"><button class="btn" type="button" @click="downloadAccountTemplate">下载导入模板</button><input ref="importFileInput" class="manual-file-input" type="file" accept=".csv,text/csv" @change="importAccountsByIdentifier($event.target.files?.[0])" /><button ref="importTrigger" class="btn primary" type="button" @click="importFileInput?.click()">上传并识别</button></div>
          <div v-if="importDataRowCount" class="manual-import-result">
            <span>导入 <b>{{ importDataRowCount }}</b></span><span>成功 <b>{{ importMatchedCount }}</b></span><span>重复 <b>{{ importDuplicateRows.length }}</b></span><span>异常 <b>{{ importErrorCount }}</b></span>
            <button v-if="hasImportIssues" class="text-btn" type="button" @click="showImportIssues">查看识别结果</button>
          </div>
        </div>
        <div class="manual-account-list-meta"><div class="manual-account-counts"><b>共 {{ matchingAccounts.length }} 个结果</b><template v-if="availabilityReady"><span>可策划 <strong>{{ availableMatchingCount }}</strong></span><span v-if="!isMarketing" class="manual-planned-count">当日已策划 <strong>{{ plannedMatchingCount }}</strong></span></template><span v-else>{{ availabilityLoading ? '查询当日策划状态中…' : '待选择投放日期并查询' }}</span></div></div>
        <LoadingSkeleton v-if="loading || !initialized" /><div v-else ref="accountListRef" class="table-wrap manual-account-table" @scroll="plannedAccountTooltip = null"><table><thead><tr><th><input type="checkbox" aria-label="全选当前筛选下的可策划账号（跨页）" :checked="allAccountsSelected" :indeterminate="someAccountsSelected" :disabled="!availabilityReady || !accountSelectionPool.length" @change="selectAllAccounts" /></th><th>账号类型</th><th>属主 UM 号</th><th>账号昵称</th><th>账号 ID</th><th>属主组织</th><th>平台</th><th>生命周期</th><th>粉丝数</th></tr></thead><tbody>
          <tr v-for="account in pagedAccounts" :key="account.account_id" :class="{ selected: sampledIds.includes(account.account_id), 'already-planned': isAccountPlanned(account.account_id) }" class="selection-row" tabindex="0" @click="toggleAccountRow(account.account_id, $event)" @keydown.enter.self.prevent="toggleAccountRow(account.account_id, $event)" @keydown.space.self.prevent="toggleAccountRow(account.account_id, $event)" :aria-disabled="!availabilityReady || isAccountPlanned(account.account_id) || undefined" :aria-describedby="plannedAccountTooltip?.accountId === account.account_id ? 'manual-planned-account-tooltip' : undefined" @mouseenter="showPlannedAccountTooltip(account.account_id, $event)" @mousemove="showPlannedAccountTooltip(account.account_id, $event)" @mouseleave="plannedAccountTooltip = null" @focusin="showPlannedAccountTooltip(account.account_id, $event)" @focusout="plannedAccountTooltip = null"><td><input type="checkbox" :checked="sampledIds.includes(account.account_id)" :disabled="!availabilityReady || isAccountPlanned(account.account_id)" :aria-label="`选择账号 ${account.account_name}`" @change="toggleAccount(account.account_id, $event)" /></td><td><AccountTypeBadge :type="account.account_type || (account.certified === true ? '认证' : account.certified === false ? '非认证' : '—')" /></td><td>{{ account.um_no || '—' }}</td><td><b>{{ account.account_name }}</b></td><td :title="account.account_id || undefined">{{ account.account_id || '—' }}</td><td>{{ account.organization || '—' }}</td><td>{{ account.platform || '—' }}</td><td>{{ account.lifecycle_stage || '—' }}</td><td>{{ account.followers?.toLocaleString() ?? '—' }}</td></tr>
          <tr v-if="visibleAccounts.length === 0"><td colspan="9"><div class="empty-state">{{ accountSelectionMode === 'upload' ? '请上传账号模板' : '没有符合条件的账号' }}</div></td></tr>
        </tbody></table></div>
        <ListPagination :show-total="false" :page.sync="accountPage" :page-size.sync="accountPageSize" :total="visibleAccounts.length" unit="个账号" :page-size-options="[20, 50, 100]" class="manual-account-pagination" />
        </fieldset>
        <div class="footer-actions manual-step-actions">
          <div v-if="accountReview" class="manual-step-review" role="status">
            <span class="manual-step-review-icon" aria-hidden="true">✓</span>
            <strong>计划账号数 <em>{{ targetCount }}</em> 个，实际选择 <em>{{ sampledIds.length }}</em> 个</strong>
            <span v-if="Number(targetCount) !== sampledIds.length" class="manual-count-difference">{{ sampledIds.length < Number(targetCount) ? '未达计划' : '超出计划' }} {{ Math.abs(Number(targetCount) - sampledIds.length) }} 个</span>
            <button class="btn" type="button" @click="accountReview = false">返回调整</button><button class="btn primary" type="button" @click="emit('next')">下一步</button>
          </div>
          <button v-else class="btn primary" type="button" :disabled="!sampledIds.length || !availabilityReady || busy" @click="emit('save')">{{ availabilityLoading ? '查询中…' : '保存' }}</button>
        </div>
      </div>
    </section>


  <BodyPortal>
    <Transition name="manual-planned-tooltip">
      <div v-if="plannedAccountTooltip" id="manual-planned-account-tooltip" class="manual-planned-tooltip" role="tooltip" :style="{ left: `${plannedAccountTooltip.left}px`, top: `${plannedAccountTooltip.top}px` }">
        <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><circle cx="10" cy="10" r="7.3" stroke="currentColor" stroke-width="1.4" /><path d="M10 9v4m0-7v.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" /></svg>
        <span>{{ publishDate }} 已手动策划，不可重复选择</span>
      </div>
    </Transition>
  </BodyPortal>

  <BodyPortal>
    <div v-if="importIssueDialogOpen" class="manual-eligibility-mask" @click.self="closeImportIssueDialog" @keydown.esc.stop="closeImportIssueDialog">
      <section class="manual-eligibility-dialog manual-import-dialog" role="dialog" aria-modal="true" aria-labelledby="manual-import-title">
        <header class="manual-import-dialog-head"><h2 id="manual-import-title">部分账号识别异常</h2><button class="icon-btn" type="button" aria-label="关闭识别结果" @click="closeImportIssueDialog">×</button></header>
        <div class="manual-import-metrics">
          <div><small>导入</small><strong>{{ importDataRowCount }}</strong></div>
          <div><small>成功</small><strong class="success">{{ importMatchedCount }}</strong></div>
          <div><small>重复</small><strong>{{ importDuplicateRows.length }}</strong></div>
          <div><small>异常</small><strong class="warning">{{ importErrorCount }}</strong></div>
        </div>
        <div class="manual-import-details table-wrap">
          <table class="manual-import-issues-table"><thead><tr><th>属主 UM 号／账号 ID</th><th>异常原因</th><th>行数</th></tr></thead><tbody><tr v-for="row in importIssueRows" :key="`${row.rowNumber}-${row.kind}`"><td :title="row.umNo || row.accountId">{{ row.umNo || row.accountId || '—' }}</td><td><span :title="row.reason" :class="['import-issue-kind',row.tone]">{{ row.kind }}</span></td><td>第 {{ row.rowNumber }} 行</td></tr></tbody></table>
        </div>
        <div class="manual-eligibility-actions"><button class="btn" type="button" @click="downloadImportIssues">下载异常结果</button><button ref="importDialogClose" class="btn primary" type="button" @click="closeImportIssueDialog">关闭</button></div>
      </section>
    </div>
  </BodyPortal>

</div>
</template>
<style scoped>

.manual-account-selection-row{margin-bottom:16px}.manual-account-selection-heading{margin-bottom:8px;color:var(--neutral-700);font-size:13px;font-weight:600}.manual-account-selection-row .manual-selection-modes{margin:0}.manual-plan-account-count{display:flex;flex-direction:column;align-items:flex-start;gap:8px;margin-bottom:16px}.manual-plan-account-count>span{flex:none}.manual-plan-account-input-wrap{width:min(240px,100%)}.manual-plan-account-input-wrap input{box-sizing:border-box;width:100%;height:36px;padding:0 10px;border:1px solid var(--neutral-200);border-radius:6px;background:var(--surface);color:var(--neutral-900)}.manual-plan-account-input-wrap small{display:block;margin-top:4px}.manual-upload-panel .manual-import-result{display:flex;align-items:center;flex-wrap:wrap;gap:16px}.manual-import-result>span{color:var(--neutral-600)}.manual-import-dialog{width:min(600px,100%)}.manual-import-dialog-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.manual-import-dialog-head h2{margin:0;font-size:18px}.manual-import-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:20px 0;padding:14px;background:var(--neutral-50);border-radius:8px}.manual-import-metrics small{display:block;color:var(--neutral-500);font-size:12px}.manual-import-metrics strong{display:block;margin-top:6px;color:var(--neutral-800);font-size:22px;font-variant-numeric:tabular-nums}.manual-import-metrics .success{color:var(--success)}.manual-import-metrics .warning{color:var(--processing)}.manual-import-details{max-height: min(360px,45vh);overflow-y:auto}.manual-import-details h3{margin:16px 0 8px;color:var(--neutral-700);font-size:13px}.manual-import-details section:first-child h3{margin-top:0}.manual-import-detail-row{display:grid;gap:4px;padding:10px 0;border-bottom:1px solid var(--neutral-100);overflow-wrap:anywhere}.manual-import-detail-row b{font-size:12px;font-weight:500;color:var(--neutral-700)}.manual-import-detail-row span{font-size:12px;color:var(--neutral-500)}.manual-import-details .manual-import-duplicates{margin-top:12px;font-size:12px;color:var(--neutral-500)}
@media(max-width:580px){.manual-plan-account-input-wrap{min-width:0;flex:1}.manual-import-metrics{gap:8px;padding:10px}.manual-import-metrics strong{font-size:20px}}
.manual-eligibility-mask{position:fixed;inset:0;z-index:100;display:grid;place-items:center;padding:20px;background:var(--mask)}
.manual-eligibility-dialog{width:min(440px,100%);padding:24px;border:1px solid var(--neutral-200);border-radius:16px;background:var(--surface);box-shadow:var(--shadow-4)}
.manual-eligibility-dialog h2{margin:16px 0 8px;color:var(--neutral-900);font-size:18px;line-height:26px}
.manual-eligibility-dialog p{margin:0;color:var(--neutral-600);font-size:14px;line-height:22px}
.manual-eligibility-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:24px}.manual-account-filters{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));align-items:end;gap:12px;margin-bottom:18px}.manual-account-filters .field{min-width:0}.manual-account-filters input,.manual-account-filters select{box-sizing:border-box;width:100%;height:36px;padding:0 10px;border:1px solid var(--neutral-200);border-radius:7px;background:var(--surface);color:var(--neutral-900)}.manual-follower-range{display:flex;align-items:center;gap:8px;height:36px;padding:0 9px;border:1px solid var(--neutral-200);border-radius:7px;background:var(--surface)}.manual-follower-range input{width:50%;min-width:0;height:32px;padding:0;border:0;border-radius:0;outline:0}.manual-follower-range i{color:var(--neutral-400);font-size:12px;font-style:normal;white-space:nowrap}.manual-selection-modes{display:flex;gap:4px;width:max-content;margin:0 0 16px;padding:4px;border-radius:8px;background:var(--neutral-100)}.manual-mode-tab{min-width:104px;padding:8px 14px;border:0;border-radius:6px;background:transparent;color:var(--neutral-500);cursor:pointer}.manual-mode-tab.active{background:var(--surface);color:var(--primary-600);box-shadow:0 1px 3px #1018281a;font-weight:600}.manual-upload-panel{display:grid;grid-template-columns:1fr auto;gap:14px;align-items:center;padding:16px;border:1px dashed var(--neutral-300);border-radius:9px;background:var(--neutral-50)}.manual-upload-panel p{margin:6px 0 0;color:var(--neutral-400);font-size:12px}.manual-upload-actions{display:flex;gap:8px}.manual-file-input{display:none}.manual-import-result{grid-column:1/-1;padding-top:12px;border-top:1px solid var(--neutral-200);color:var(--success);font-size:13px}.manual-import-result span{color:var(--processing)}.manual-account-counts{display:flex;align-items:center;gap:16px;flex-wrap:wrap}.manual-account-counts strong{color:var(--neutral-700);font-weight:600}.manual-account-counts .manual-planned-count,.manual-account-counts .manual-planned-count strong{color:var(--processing)}.manual-account-list-meta{display:flex;justify-content:space-between;align-items:center;margin:0 0 8px;font-size:13px}.manual-account-list-meta span{color:var(--neutral-400);font-size:12px}.manual-account-table{max-height:430px;overflow:auto;border:1px solid var(--neutral-200);border-radius:8px}.manual-account-table table{min-width:1120px}.manual-account-table thead th{position:sticky;top:0;z-index:1;background:var(--neutral-50);white-space:nowrap}.manual-account-table tbody tr:hover,.manual-account-table tbody tr.selected{background:var(--primary-50)}.manual-account-table input{accent-color:var(--primary-600)}.manual-account-table tbody tr.already-planned,.manual-account-table tbody tr.already-planned:hover{background:var(--neutral-50);color:var(--neutral-400);cursor:not-allowed}.manual-account-table tbody tr.already-planned input{pointer-events:none}.manual-account-pagination{margin:14px 0 18px}.manual-step-review{display:flex;align-items:center;gap:10px;flex:1;min-width:0;padding:10px 12px;border:1px solid var(--primary-100);border-radius:8px;background:var(--primary-50)}.manual-step-review-icon{display:grid;place-items:center;flex:none;width:24px;height:24px;border-radius:50%;background:var(--primary-50);color:var(--primary-600);font-size:14px;font-weight:700}.manual-step-review>strong{flex:1;min-width:0;color:var(--neutral-700);font-size:13px;font-weight:500;line-height:1.5}.manual-step-review>strong em{display:inline-block;margin:0 2px;color:var(--primary-600);font-size:20px;font-style:normal;font-weight:700;font-variant-numeric:tabular-nums;line-height:1;vertical-align:-1px}.manual-planned-tooltip{position:fixed;z-index:80;display:flex;align-items:center;gap:8px;width:min(304px,calc(100vw - 24px));padding:10px 12px;border:1px solid #ffffff12;border-radius:8px;background:var(--neutral-950);color:var(--surface);box-shadow:0 6px 20px #11223d26;font-size:12px;line-height:1.6;white-space:nowrap;pointer-events:none}.manual-planned-tooltip svg{flex:none;width:16px;height:16px;color:var(--neutral-300)}.manual-planned-tooltip-enter-active,.manual-planned-tooltip-leave-active{transition:opacity .12s ease}.manual-planned-tooltip-enter,.manual-planned-tooltip-leave-to{opacity:0}
@media(max-width:900px){.manual-account-filters{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:580px){.manual-account-filters,.manual-submit-summary{grid-template-columns:1fr}.manual-step-review{flex-wrap:wrap}.manual-step-review>strong{flex-basis:calc(100% - 36px)}.manual-step-review .btn{flex:1}.manual-upload-panel{grid-template-columns:1fr}.manual-upload-actions{flex-wrap:wrap}}
.manual-account-mode-row{display:flex;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:16px}.manual-account-mode-row>.field{min-width:180px;margin:0}.manual-account-mode-row .manual-selection-modes{align-self:flex-end;margin:0}
@media(max-width:580px){.manual-account-mode-row{align-items:stretch;flex-direction:column;gap:10px}.manual-account-mode-row>.field{min-width:0}.manual-account-mode-row .manual-selection-modes{width:100%}.manual-account-mode-row .manual-mode-tab{flex:1}}
.manual-selection-lock{min-width:0;margin:0;padding:0;border:0}.manual-selection-lock:disabled{opacity:.78}
.manual-step-body{padding-bottom:104px}.manual-step-actions{position:fixed;z-index:35;right:0;bottom:0;left:var(--sidebar-width);display:flex;align-items:center;justify-content:flex-end;min-height:68px;margin:0;padding:12px 32px calc(12px + env(safe-area-inset-bottom));border-top:1px solid var(--neutral-200);background:color-mix(in srgb,var(--surface) 94%,transparent);box-shadow:0 -6px 20px #1018280a;backdrop-filter:blur(10px)}
@media(max-width:780px){.manual-step-actions{padding-right:24px;padding-left:24px}}
@media(max-width:580px){.manual-step-body{padding-bottom:124px}.manual-step-actions{min-height:76px;padding:10px 12px calc(10px + env(safe-area-inset-bottom))}.manual-step-actions .manual-step-review{width:100%;flex-wrap:wrap}.manual-step-actions .manual-step-review>strong{flex-basis:calc(100% - 36px)}.manual-step-actions .manual-step-review .btn{flex:1}}

</style>
