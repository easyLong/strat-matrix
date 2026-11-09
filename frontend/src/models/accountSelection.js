import Vue from "vue";
import { buildAccountImportIssueCsv, recognizeAccountImport } from '../ui/accountImport';
export function createAccountSelection(owner) {
  return new Vue({
    data() {
      return {
        accountListRef: null,
        accountSelectionMode: 'filter',
        targetCount: '',
        keyword: '',
        accountTypeFilter: '',
        umNoFilter: '',
        organizationFilter: '',
        platformFilter: '',
        lifecycleFilter: '',
        followersMin: null,
        followersMax: null,
        appliedAccountFilters: {
          keyword: '',
          accountType: '',
          umNo: '',
          organization: '',
          platform: '',
          lifecycle: '',
          followersMin: null,
          followersMax: null
        },
        sampledIds: [],
        accountReview: false,
        importMatchedCount: 0,
        importedAccountIds: [],
        importDataRowCount: 0,
        importDuplicateRows: [],
        importUnmatchedRows: [],
        importPlannedRows: [],
        importIssueDialogOpen: false,
        importDialogClose: null,
        importTrigger: null,
        plannedAccountIds: [],
        availabilityDate: '',
        availabilityLoading: false,
        availabilityError: '',
        accountPage: 1,
        accountPageSize: 20,
        plannedAccountTooltip: null,
        availabilityRequest: 0,
        importFileInput: null
      };
    },
    computed: {
      fetchAvailability: {
        get() {
          return owner.fetchAvailability;
        },
        set(value) {
          owner.fetchAvailability = value;
        }
      },
      notice: {
        get() {
          return owner.notice;
        },
        set(value) {
          owner.notice = value;
        }
      },
      error: {
        get() {
          return owner.error;
        },
        set(value) {
          owner.error = value;
        }
      },
      databaseReady: {
        get() {
          return owner.store.databaseReady;
        },
        set(value) {
          owner.store.databaseReady = value;
        }
      },
      isMarketing: {
        get() {
          return owner.isMarketing;
        },
        set(value) {
          owner.isMarketing = value;
        }
      },
      publishDate: {
        get() {
          return owner.publishDate;
        },
        set(value) {
          owner.publishDate = value;
        }
      },
      accounts: {
        get() {
          return owner.accounts;
        },
        set(value) {
          owner.accounts = value;
        }
      },
      importErrorCount() {
        return this.importUnmatchedRows.length + this.importPlannedRows.length;
      },
      hasImportIssues() {
        return this.importDuplicateRows.length > 0 || this.importErrorCount > 0;
      },
      availabilityReady() {
        return this.isMarketing ? this.databaseReady : !!this.publishDate && this.availabilityDate === this.publishDate && !this.availabilityLoading && !this.availabilityError;
      },
      plannedAccountSet() {
        return new Set(this.plannedAccountIds);
      },
      importedAccounts() {
        const ids = new Set(this.importedAccountIds);
        return this.accounts.filter(account => ids.has(account.account_id));
      },
      eligibleAccounts() {
        return this.accounts.filter(account => {
          const filters = this.appliedAccountFilters;
          const search = filters.keyword.trim().toLocaleLowerCase();
          const accountType = account.account_type || (account.certified === true ? '\u8ba4\u8bc1' : account.certified === false ? '\u975e\u8ba4\u8bc1' : '');
          return (!this.isMarketing || accountType === '认证') && (!search || `${account.account_name} ${account.account_alias} ${account.account_id}`.toLocaleLowerCase().includes(search)) && (!filters.accountType || accountType === filters.accountType) && (!filters.umNo.trim() || (account.um_no || '').toLocaleLowerCase().includes(filters.umNo.trim().toLocaleLowerCase())) && (!filters.organization || account.organization === filters.organization) && (!filters.platform || account.platform === filters.platform) && (!filters.lifecycle || account.lifecycle_stage === filters.lifecycle) && (filters.followersMin === null || account.followers !== null && account.followers >= filters.followersMin) && (filters.followersMax === null || account.followers !== null && account.followers <= filters.followersMax);
        });
      },
      visibleAccounts() {
        const pinned = this.sampledIds.map(id => this.accounts.find(item => item.account_id === id)).filter(item => !!item);
        const candidates = this.accountSelectionMode === 'filter' ? this.eligibleAccounts.filter(item => !this.sampledIds.includes(item.account_id)) : this.importedAccounts.filter(item => !this.sampledIds.includes(item.account_id));
        return [...pinned, ...candidates].sort((a, b) => {
          const selectedOrder = Number(this.sampledIds.includes(b.account_id)) - Number(this.sampledIds.includes(a.account_id));
          return selectedOrder || (b.followers ?? -1) - (a.followers ?? -1) || a.account_name.localeCompare(b.account_name, 'zh-CN');
        }).filter((item, index, rows) => rows.findIndex(row => row.account_id === item.account_id) === index);
      },
      pagedAccounts() {
        return this.visibleAccounts.slice((this.accountPage - 1) * this.accountPageSize, this.accountPage * this.accountPageSize);
      },
      matchingAccounts() {
        return this.accountSelectionMode === 'upload' ? this.importedAccounts : this.eligibleAccounts;
      },
      plannedMatchingCount() {
        return this.matchingAccounts.filter(account => this.isAccountPlanned(account.account_id)).length;
      },
      availableMatchingCount() {
        return this.availabilityReady ? this.matchingAccounts.length - this.plannedMatchingCount : 0;
      },
      organizationOptions() {
        return [...new Set(this.accounts.map(item => item.organization).filter(Boolean))].sort();
      },
      platformOptions() {
        return [...new Set(this.accounts.map(item => item.platform).filter(Boolean))].sort();
      },
      lifecycleOptions() {
        return [...new Set(this.accounts.map(item => item.lifecycle_stage).filter(Boolean))];
      },
      selectedAccounts() {
        return this.sampledIds.map(id => this.accounts.find(item => item.account_id === id)).filter(item => !!item);
      },
      accountSelectionPool() {
        return this.availabilityReady ? this.matchingAccounts.filter(account => !this.isAccountPlanned(account.account_id)) : [];
      },
      allAccountsSelected() {
        return this.accountSelectionPool.length > 0 && this.accountSelectionPool.every(account => this.sampledIds.includes(account.account_id));
      },
      someAccountsSelected() {
        return !this.allAccountsSelected && this.accountSelectionPool.some(account => this.sampledIds.includes(account.account_id));
      },
      targetCountError() {
        return this.targetCount !== '' && (!Number.isInteger(this.targetCount) || this.targetCount < 1 || this.targetCount > 1000) ? '数量须为 1 至 1000 之间的整数' : '';
      },
      accountPageCount() {
        return Math.max(1, Math.ceil(this.visibleAccounts.length / this.accountPageSize));
      }
    },
    methods: {
      isAccountPlanned(accountId) {
        return !this.isMarketing && !!this.publishDate && this.availabilityDate === this.publishDate && this.plannedAccountSet.has(accountId);
      },
      applyAccountFilters() {
        this.appliedAccountFilters = {
          keyword: this.keyword,
          accountType: this.accountTypeFilter,
          umNo: this.umNoFilter,
          organization: this.organizationFilter,
          platform: this.platformFilter,
          lifecycle: this.lifecycleFilter,
          followersMin: this.followersMin,
          followersMax: this.followersMax
        };
        this.accountPage = 1;
        this.applyDefaultAccountSelection();
      },
      showPlannedAccountTooltip(accountId, event) {
        if (!this.availabilityReady || !this.isAccountPlanned(accountId)) return;
        const rect = event.currentTarget.getBoundingClientRect();
        const x = 'clientX' in event ? event.clientX : Math.max(0, rect.left) + 32;
        const y = 'clientY' in event ? event.clientY : rect.bottom;
        const width = Math.min(304, window.innerWidth - 24);
        const height = 72;
        this.plannedAccountTooltip = {
          accountId,
          left: Math.max(12, Math.min(x + 12, window.innerWidth - width - 12)),
          top: Math.max(12, y + height + 14 > window.innerHeight ? y - height - 12 : y + 14)
        };
      },
      applyDefaultAccountSelection() {
        if (this.accountSelectionMode !== 'filter') return;
        const count = this.targetCount;
        if (count === '' || !Number.isInteger(count) || count < 1 || count > 1000) {
          this.sampledIds = [];
          return;
        }
        const ordered = [...this.accountSelectionPool].sort((a, b) => (b.followers ?? -1) - (a.followers ?? -1));
        this.sampledIds = ordered.slice(0, Math.min(count, ordered.length)).map(item => item.account_id);
      },
      async loadAccountAvailability(reselect = false) {
        const request = ++this.availabilityRequest;
        const selectedDate = this.publishDate;
        this.availabilityDate = '';
        this.availabilityError = '';
        if (this.isMarketing) {
          this.availabilityLoading = false;
          this.plannedAccountIds = [];
          return this.databaseReady;
        }
        this.availabilityLoading = !!selectedDate && this.databaseReady;
        if (!selectedDate || !this.databaseReady) {
          this.plannedAccountIds = [];
          return false;
        }
        try {
          const result = await this.fetchAvailability(selectedDate);
          if (request !== this.availabilityRequest || selectedDate !== this.publishDate) return false;
          if (result.publish_date !== selectedDate) throw new Error('账号策划日期校验失败，请重试');
          this.plannedAccountIds = result.planned_account_ids;
          this.availabilityDate = selectedDate;
          this.availabilityLoading = false;
          this.sampledIds = this.sampledIds.filter(id => !this.isAccountPlanned(id));
          if (reselect && this.accountSelectionMode === 'upload') this.sampledIds = this.importedAccountIds.filter(id => !this.isAccountPlanned(id));
          return true;
        } catch (exc) {
          if (request === this.availabilityRequest) this.availabilityError = exc instanceof Error ? exc.message : '读取当日策划账号失败';
          return false;
        } finally {
          if (request === this.availabilityRequest) this.availabilityLoading = false;
        }
      },
      toggleAccount(accountId, event) {
        const checked = event.target.checked;
        this.setAccountSelected(accountId, checked);
      },
      setAccountSelected(accountId, checked) {
        if (this.accountReview) return;
        if (checked && (!this.availabilityReady || this.isAccountPlanned(accountId))) return;
        if (checked && !this.sampledIds.includes(accountId)) {
          this.error = '';
          this.sampledIds = [...this.sampledIds, accountId];
        }
        if (!checked) this.sampledIds = this.sampledIds.filter(id => id !== accountId);
        this.accountReview = false;
      },
      interactiveRowTarget(event) {
        return event.target instanceof Element && Boolean(event.target.closest('input, button, a, select, textarea, label'));
      },
      toggleAccountRow(accountId, event) {
        if (this.accountReview || this.interactiveRowTarget(event) || !this.availabilityReady || this.isAccountPlanned(accountId)) return;
        this.setAccountSelected(accountId, !this.sampledIds.includes(accountId));
      },
      selectAllAccounts(event) {
        if (this.accountReview || !this.availabilityReady) return;
        const ids = this.accountSelectionPool.map(account => account.account_id);
        this.sampledIds = event.target.checked ? [...new Set([...this.sampledIds, ...ids])] : this.sampledIds.filter(id => !ids.includes(id));
        this.accountReview = false;
      },
      setAccountSelectionMode(next) {
        this.accountSelectionMode = next;
        this.error = '';
        this.notice = '';
        this.accountPage = 1;
        if (next === 'upload') this.sampledIds = this.availabilityReady ? this.importedAccountIds.filter(id => !this.isAccountPlanned(id)) : [];
      },
      downloadAccountTemplate() {
        const csv = `\uFEFFUM号,账号ID\r\n`;
        const url = URL.createObjectURL(new Blob([csv], {
          type: 'text/csv;charset=utf-8'
        }));
        const link = document.createElement('a');
        link.href = url;
        link.download = '手动策划账号导入模板.csv';
        link.click();
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      },
      downloadImportIssues() {
        if (!this.hasImportIssues) return;
        const csv = buildAccountImportIssueCsv({
          duplicates: this.importDuplicateRows,
          unmatched: this.importUnmatchedRows,
          planned: this.importPlannedRows
        });
        const url = URL.createObjectURL(new Blob([csv], {
          type: 'text/csv;charset=utf-8'
        }));
        const link = document.createElement('a');
        link.href = url;
        link.download = '手动策划账号导入异常结果.csv';
        link.click();
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      },
      async showImportIssues() {
        this.importIssueDialogOpen = true;
        await this.$nextTick();
        this.importDialogClose?.focus();
      },
      closeImportIssueDialog() {
        this.importIssueDialogOpen = false;
        this.importTrigger?.focus();
      },
      importRowLabel(row) {
        return [`第 ${row.rowNumber} 行`, row.umNo ? `UM 号 ${row.umNo}` : '', row.accountId ? `账号 ID ${row.accountId}` : ''].filter(Boolean).join(' · ');
      },
      async importAccountsByIdentifier(file) {
        if (!file) return;
        this.error = '';
        this.notice = '';
        try {
          const bytes = await file.arrayBuffer();
          let text = new TextDecoder('utf-8').decode(bytes);
          if (text.includes('\uFFFD')) text = new TextDecoder('gb18030').decode(bytes);
          if (!this.availabilityReady && !(await this.loadAccountAvailability())) {
            this.error = '请先确认投放日期和账号策划状态';
            return;
          }
          const result = recognizeAccountImport(text, this.isMarketing ? this.accounts.filter(account => account.account_type === '认证' || !account.account_type && account.certified === true) : this.accounts, this.isMarketing ? new Set() : this.plannedAccountSet);
          this.accountSelectionMode = 'upload';
          this.importedAccountIds = result.identifiedIds;
          this.sampledIds = result.selectedIds;
          this.importDataRowCount = result.totalRows;
          this.targetCount = result.totalRows;
          this.accountPage = 1;
          this.accountReview = false;
          this.importMatchedCount = result.selectedIds.length;
          this.importDuplicateRows = result.duplicates;
          this.importUnmatchedRows = result.unmatched;
          this.importPlannedRows = result.planned;
          if (this.hasImportIssues) await this.showImportIssues();
        } catch (exc) {
          this.error = exc instanceof Error ? exc.message : '文件读取失败，请使用下载的 CSV 模板填写后再导入';
        } finally {
          if (this.importFileInput) this.importFileInput = '';
        }
      },
      reset() {
        this.targetCount = '';
        this.sampledIds = [];
        this.accountSelectionMode = 'filter';
        this.accountReview = false;
        this.accountTypeFilter = this.isMarketing ? '认证' : '';
        this.appliedAccountFilters = {
          ...this.appliedAccountFilters,
          accountType: this.accountTypeFilter
        };
        this.importedAccountIds = [];
        this.importMatchedCount = 0;
        this.importDataRowCount = 0;
        this.importDuplicateRows = [];
        this.importUnmatchedRows = [];
        this.importPlannedRows = [];
        this.importIssueDialogOpen = false;
      }
    },
    created() {
      this.$watch(() => [this.pagedAccounts, this.publishDate, this.availabilityReady], () => {
        this.plannedAccountTooltip = null;
      }, {
        sync: true
      });
      this.$watch(() => this.eligibleAccounts, () => {
        this.accountPage = 1;
      }, {
        sync: true
      });
      this.$watch(() => this.accountPageSize, () => {
        this.accountPage = 1;
      });
      this.$watch(() => this.accountPageCount, count => {
        this.accountPage = Math.min(this.accountPage, count);
      });
      this.$watch(() => [this.publishDate, this.isMarketing, this.databaseReady], () => {
        this.sampledIds = [];
        this.accountPage = 1;
        this.accountReview = false;
        void this.loadAccountAvailability(true);
      }, {
        immediate: true,
        sync: true
      });
    },
    beforeDestroy() {
      this.availabilityRequest++;
    }
  });
}
