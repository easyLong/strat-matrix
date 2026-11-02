import { computed, nextTick, onScopeDispose, ref, watch, type Ref } from 'vue';
import type { AccountOption, ManualAccountAvailability } from '../types';
import { buildAccountImportIssueCsv, recognizeAccountImport, type AccountImportRow } from '../ui/accountImport';
export function useManualAccountSelection({ accounts, publishDate, isMarketing, databaseReady, error, notice, fetchAvailability }: {
    accounts: Ref<AccountOption[]>;
    publishDate: Ref<string>;
    isMarketing: Ref<boolean>;
    databaseReady: Ref<boolean>;
    error: Ref<string>;
    notice: Ref<string>;
    fetchAvailability: (date: string) => Promise<ManualAccountAvailability>;
}) {
    const accountListRef = ref<HTMLElement | null>(null);
    const accountSelectionMode = ref<'filter' | 'upload'>('filter');
    const targetCount = ref<number | ''>('');
    const keyword = ref('');
    const accountTypeFilter = ref('');
    const umNoFilter = ref('');
    const organizationFilter = ref('');
    const platformFilter = ref('');
    const lifecycleFilter = ref('');
    const followersMin = ref<number | null>(null);
    const followersMax = ref<number | null>(null);
    const appliedAccountFilters = ref({ keyword: '', accountType: '', umNo: '', organization: '', platform: '', lifecycle: '', followersMin: null as number | null, followersMax: null as number | null });
    const sampledIds = ref<string[]>([]);
    const accountReview = ref(false);
    const importMatchedCount = ref(0);
    const importedAccountIds = ref<string[]>([]);
    const importDataRowCount = ref(0);
    const importDuplicateRows = ref<AccountImportRow[]>([]);
    const importUnmatchedRows = ref<AccountImportRow[]>([]);
    const importPlannedRows = ref<AccountImportRow[]>([]);
    const importIssueDialogOpen = ref(false);
    const importDialogClose = ref<HTMLButtonElement | null>(null);
    const importTrigger = ref<HTMLButtonElement | null>(null);
    const importErrorCount = computed(() => importUnmatchedRows.value.length + importPlannedRows.value.length);
    const hasImportIssues = computed(() => importDuplicateRows.value.length > 0 || importErrorCount.value > 0);
    const plannedAccountIds = ref<string[]>([]);
    const availabilityDate = ref('');
    const availabilityLoading = ref(false);
    const availabilityError = ref('');
    const accountPage = ref(1);
    const accountPageSize = ref(20);
    const plannedAccountTooltip = ref<{
        accountId: string;
        left: number;
        top: number;
    } | null>(null);
    let availabilityRequest = 0;
    const importFileInput = ref<HTMLInputElement | null>(null);
    const availabilityReady = computed(() => isMarketing.value ? databaseReady.value : !!publishDate.value && availabilityDate.value === publishDate.value && !availabilityLoading.value && !availabilityError.value);
    const plannedAccountSet = computed(() => new Set(plannedAccountIds.value));
    const importedAccounts = computed(() => {
        const ids = new Set(importedAccountIds.value);
        return accounts.value.filter(account => ids.has(account.account_id));
    });
    function isAccountPlanned(accountId: string) { return !isMarketing.value && !!publishDate.value && availabilityDate.value === publishDate.value && plannedAccountSet.value.has(accountId); }
    const eligibleAccounts = computed(() => accounts.value.filter(account => {
        const filters = appliedAccountFilters.value;
        const search = filters.keyword.trim().toLocaleLowerCase();
        const accountType = account.account_type || (account.certified === true ? '\u8ba4\u8bc1' : account.certified === false ? '\u975e\u8ba4\u8bc1' : '');
        return (!isMarketing.value || accountType === '认证') && (!search || `${account.account_name} ${account.account_alias} ${account.account_id}`.toLocaleLowerCase().includes(search)) &&
            (!filters.accountType || accountType === filters.accountType) &&
            (!filters.umNo.trim() || (account.um_no || '').toLocaleLowerCase().includes(filters.umNo.trim().toLocaleLowerCase())) &&
            (!filters.organization || account.organization === filters.organization) &&
            (!filters.platform || account.platform === filters.platform) &&
            (!filters.lifecycle || account.lifecycle_stage === filters.lifecycle) &&
            (filters.followersMin === null || (account.followers !== null && account.followers >= filters.followersMin)) &&
            (filters.followersMax === null || (account.followers !== null && account.followers <= filters.followersMax));
    }));
    function applyAccountFilters() {
        appliedAccountFilters.value = { keyword: keyword.value, accountType: accountTypeFilter.value, umNo: umNoFilter.value, organization: organizationFilter.value, platform: platformFilter.value, lifecycle: lifecycleFilter.value, followersMin: followersMin.value, followersMax: followersMax.value };
        accountPage.value = 1;
        applyDefaultAccountSelection();
    }
    const visibleAccounts = computed(() => {
        const pinned = sampledIds.value.map(id => accounts.value.find(item => item.account_id === id)).filter((item): item is AccountOption => !!item);
        const candidates = accountSelectionMode.value === 'filter'
            ? eligibleAccounts.value.filter(item => !sampledIds.value.includes(item.account_id))
            : importedAccounts.value.filter(item => !sampledIds.value.includes(item.account_id));
        return [...pinned, ...candidates].sort((a, b) => {
            const selectedOrder = Number(sampledIds.value.includes(b.account_id)) - Number(sampledIds.value.includes(a.account_id));
            return selectedOrder || (b.followers ?? -1) - (a.followers ?? -1) || a.account_name.localeCompare(b.account_name, 'zh-CN');
        }).filter((item, index, rows) => rows.findIndex(row => row.account_id === item.account_id) === index);
    });
    const pagedAccounts = computed(() => visibleAccounts.value.slice((accountPage.value - 1) * accountPageSize.value, accountPage.value * accountPageSize.value));
    function showPlannedAccountTooltip(accountId: string, event: MouseEvent | FocusEvent) {
        if (!availabilityReady.value || !isAccountPlanned(accountId))
            return;
        const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
        const x = 'clientX' in event ? event.clientX : Math.max(0, rect.left) + 32;
        const y = 'clientY' in event ? event.clientY : rect.bottom;
        const width = Math.min(304, window.innerWidth - 24);
        const height = 72;
        plannedAccountTooltip.value = {
            accountId,
            left: Math.max(12, Math.min(x + 12, window.innerWidth - width - 12)),
            top: Math.max(12, y + height + 14 > window.innerHeight ? y - height - 12 : y + 14),
        };
    }
    const matchingAccounts = computed(() => accountSelectionMode.value === 'upload' ? importedAccounts.value : eligibleAccounts.value);
    const plannedMatchingCount = computed(() => matchingAccounts.value.filter(account => isAccountPlanned(account.account_id)).length);
    const availableMatchingCount = computed(() => availabilityReady.value ? matchingAccounts.value.length - plannedMatchingCount.value : 0);
    const organizationOptions = computed(() => [...new Set(accounts.value.map(item => item.organization).filter(Boolean))].sort());
    const platformOptions = computed(() => [...new Set(accounts.value.map(item => item.platform).filter(Boolean))].sort());
    const lifecycleOptions = computed(() => [...new Set(accounts.value.map(item => item.lifecycle_stage).filter(Boolean))]);
    const selectedAccounts = computed(() => sampledIds.value.map(id => accounts.value.find(item => item.account_id === id)).filter((item): item is AccountOption => !!item));
    const accountSelectionPool = computed(() => availabilityReady.value ? matchingAccounts.value.filter(account => !isAccountPlanned(account.account_id)) : []);
    const allAccountsSelected = computed(() => accountSelectionPool.value.length > 0 && accountSelectionPool.value.every(account => sampledIds.value.includes(account.account_id)));
    const someAccountsSelected = computed(() => !allAccountsSelected.value && accountSelectionPool.value.some(account => sampledIds.value.includes(account.account_id)));
    const targetCountError = computed(() => targetCount.value !== '' && (!Number.isInteger(targetCount.value) || targetCount.value < 1 || targetCount.value > 1000) ? '数量须为 1 至 1000 之间的整数' : '');
    function applyDefaultAccountSelection() {
        if (accountSelectionMode.value !== 'filter')
            return;
        const count = targetCount.value;
        if (count === '' || !Number.isInteger(count) || count < 1 || count > 1000) {
            sampledIds.value = [];
            return;
        }
        const ordered = [...accountSelectionPool.value].sort((a, b) => (b.followers ?? -1) - (a.followers ?? -1));
        sampledIds.value = ordered.slice(0, Math.min(count, ordered.length)).map(item => item.account_id);
    }
    async function loadAccountAvailability(reselect = false): Promise<boolean> {
        const request = ++availabilityRequest;
        const selectedDate = publishDate.value;
        availabilityDate.value = '';
        availabilityError.value = '';
        if (isMarketing.value) {
            availabilityLoading.value = false;
            plannedAccountIds.value = [];
            return databaseReady.value;
        }
        availabilityLoading.value = !!selectedDate && databaseReady.value;
        if (!selectedDate || !databaseReady.value) {
            plannedAccountIds.value = [];
            return false;
        }
        try {
            const result = await fetchAvailability(selectedDate);
            if (request !== availabilityRequest || selectedDate !== publishDate.value)
                return false;
            if (result.publish_date !== selectedDate)
                throw new Error('账号策划日期校验失败，请重试');
            plannedAccountIds.value = result.planned_account_ids;
            availabilityDate.value = selectedDate;
            availabilityLoading.value = false;
            sampledIds.value = sampledIds.value.filter(id => !isAccountPlanned(id));
            if (reselect && accountSelectionMode.value === 'upload')
                sampledIds.value = importedAccountIds.value.filter(id => !isAccountPlanned(id));
            return true;
        }
        catch (exc) {
            if (request === availabilityRequest)
                availabilityError.value = exc instanceof Error ? exc.message : '读取当日策划账号失败';
            return false;
        }
        finally {
            if (request === availabilityRequest)
                availabilityLoading.value = false;
        }
    }
    function toggleAccount(accountId: string, event: Event) {
        const checked = (event.target as HTMLInputElement).checked;
        setAccountSelected(accountId, checked);
    }
    function setAccountSelected(accountId: string, checked: boolean) {
        if (accountReview.value)
            return;
        if (checked && (!availabilityReady.value || isAccountPlanned(accountId)))
            return;
        if (checked && !sampledIds.value.includes(accountId)) {
            error.value = '';
            sampledIds.value = [...sampledIds.value, accountId];
        }
        if (!checked)
            sampledIds.value = sampledIds.value.filter(id => id !== accountId);
        accountReview.value = false;
    }
    function interactiveRowTarget(event: Event) {
        return event.target instanceof Element && Boolean(event.target.closest('input, button, a, select, textarea, label'));
    }
    function toggleAccountRow(accountId: string, event: Event) {
        if (accountReview.value || interactiveRowTarget(event) || !availabilityReady.value || isAccountPlanned(accountId))
            return;
        setAccountSelected(accountId, !sampledIds.value.includes(accountId));
    }
    function selectAllAccounts(event: Event) {
        if (accountReview.value || !availabilityReady.value)
            return;
        const ids = accountSelectionPool.value.map(account => account.account_id);
        sampledIds.value = (event.target as HTMLInputElement).checked ? [...new Set([...sampledIds.value, ...ids])] : sampledIds.value.filter(id => !ids.includes(id));
        accountReview.value = false;
    }
    function setAccountSelectionMode(next: 'filter' | 'upload') {
        accountSelectionMode.value = next;
        error.value = '';
        notice.value = '';
        accountPage.value = 1;
        if (next === 'upload')
            sampledIds.value = availabilityReady.value ? importedAccountIds.value.filter(id => !isAccountPlanned(id)) : [];
    }
    function downloadAccountTemplate() {
        const csv = `\uFEFFUM号,账号ID\r\n`;
        const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
        const link = document.createElement('a');
        link.href = url;
        link.download = '手动策划账号导入模板.csv';
        link.click();
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    function downloadImportIssues() {
        if (!hasImportIssues.value)
            return;
        const csv = buildAccountImportIssueCsv({
            duplicates: importDuplicateRows.value,
            unmatched: importUnmatchedRows.value,
            planned: importPlannedRows.value,
        });
        const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
        const link = document.createElement('a');
        link.href = url;
        link.download = '手动策划账号导入异常结果.csv';
        link.click();
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    async function showImportIssues() {
        importIssueDialogOpen.value = true;
        await nextTick();
        importDialogClose.value?.focus();
    }
    function closeImportIssueDialog() {
        importIssueDialogOpen.value = false;
        importTrigger.value?.focus();
    }
    function importRowLabel(row: AccountImportRow) {
        return [`第 ${row.rowNumber} 行`, row.umNo ? `UM 号 ${row.umNo}` : '', row.accountId ? `账号 ID ${row.accountId}` : ''].filter(Boolean).join(' · ');
    }
    async function importAccountsByIdentifier(file?: File) {
        if (!file)
            return;
        error.value = '';
        notice.value = '';
        try {
            const bytes = await file.arrayBuffer();
            let text = new TextDecoder('utf-8').decode(bytes);
            if (text.includes('\uFFFD'))
                text = new TextDecoder('gb18030').decode(bytes);
            if (!availabilityReady.value && !await loadAccountAvailability()) {
                error.value = '请先确认投放日期和账号策划状态';
                return;
            }
            const result = recognizeAccountImport(text, isMarketing.value ? accounts.value.filter(account => account.account_type === '认证' || (!account.account_type && account.certified === true)) : accounts.value, isMarketing.value ? new Set() : plannedAccountSet.value);
            accountSelectionMode.value = 'upload';
            importedAccountIds.value = result.identifiedIds;
            sampledIds.value = result.selectedIds;
            importDataRowCount.value = result.totalRows;
            targetCount.value = result.totalRows;
            accountPage.value = 1;
            accountReview.value = false;
            importMatchedCount.value = result.selectedIds.length;
            importDuplicateRows.value = result.duplicates;
            importUnmatchedRows.value = result.unmatched;
            importPlannedRows.value = result.planned;
            if (hasImportIssues.value)
                await showImportIssues();
        }
        catch (exc) {
            error.value = exc instanceof Error ? exc.message : '文件读取失败，请使用下载的 CSV 模板填写后再导入';
        }
        finally {
            if (importFileInput.value)
                importFileInput.value.value = '';
        }
    }
    const accountPageCount = computed(() => Math.max(1, Math.ceil(visibleAccounts.value.length / accountPageSize.value)));
    watch([pagedAccounts, publishDate, availabilityReady], () => { plannedAccountTooltip.value = null; }, { flush: 'sync' });
    watch(eligibleAccounts, () => { accountPage.value = 1; }, { flush: 'sync' });
    watch(accountPageSize, () => { accountPage.value = 1; });
    watch(accountPageCount, count => { accountPage.value = Math.min(accountPage.value, count); });
    watch([publishDate, isMarketing, databaseReady], () => {
        sampledIds.value = [];
        accountPage.value = 1;
        accountReview.value = false;
        void loadAccountAvailability(true);
    }, { immediate: true, flush: 'sync' });
    onScopeDispose(() => { availabilityRequest++; });
    function reset() {
        targetCount.value = '';
        sampledIds.value = [];
        accountSelectionMode.value = 'filter';
        accountReview.value = false;
        accountTypeFilter.value = isMarketing.value ? '认证' : '';
        appliedAccountFilters.value = { ...appliedAccountFilters.value, accountType: accountTypeFilter.value };
        importedAccountIds.value = [];
        importMatchedCount.value = 0;
        importDataRowCount.value = 0;
        importDuplicateRows.value = [];
        importUnmatchedRows.value = [];
        importPlannedRows.value = [];
        importIssueDialogOpen.value = false;
    }
    return { sampledIds, accountReview, accountSelectionMode, setAccountSelectionMode, accountPage, availabilityReady, availabilityDate, availabilityLoading, availabilityError, importedAccountIds, isAccountPlanned, plannedAccountSet, plannedAccountIds, targetCount, targetCountError, lifecycleFilter, lifecycleOptions, followersMin, followersMax, accountTypeFilter, organizationFilter, organizationOptions, platformFilter, platformOptions, keyword, umNoFilter, applyAccountFilters, appliedAccountFilters, applyDefaultAccountSelection, accountSelectionPool, matchingAccounts, importedAccounts, eligibleAccounts, downloadAccountTemplate, importFileInput, importAccountsByIdentifier, loadAccountAvailability, availabilityRequest, importDataRowCount, importMatchedCount, importDuplicateRows, importUnmatchedRows, importPlannedRows, hasImportIssues, importErrorCount, showImportIssues, importIssueDialogOpen, importDialogClose, importTrigger, availableMatchingCount, plannedMatchingCount, accountListRef, plannedAccountTooltip, allAccountsSelected, someAccountsSelected, selectAllAccounts, pagedAccounts, visibleAccounts, accountPageSize, toggleAccountRow, interactiveRowTarget, setAccountSelected, showPlannedAccountTooltip, toggleAccount, closeImportIssueDialog, importRowLabel, downloadImportIssues, selectedAccounts, reset };
}
export type ManualAccountSelection = ReturnType<typeof useManualAccountSelection>;
