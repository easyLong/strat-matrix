<script>
import HoverHint from './HoverHint.vue';
import AccountTypeBadge from './AccountTypeBadge.vue';
import ListPagination from './ListPagination.vue';
import MarketingTopicTable from './MarketingTopicTable.vue';
export default {
  props: {
    accounts: {
      required: true,
      type: Array
    },
    topics: {
      required: true,
      type: Array
    },
    marketing: {
      required: true,
      type: Boolean
    }
  },
  components: {
    HoverHint,
    AccountTypeBadge,
    ListPagination,
    MarketingTopicTable
  },
  data() {
    return {
      submitAccountPage: 1,
      submitTopicPage: 1,
      submitAccountPageSize: 10,
      submitTopicPageSize: 10
    };
  },
  computed: {
    selectedAccounts() {
      return this.accounts;
    },
    selectedTopics() {
      return this.topics;
    },
    isMarketing() {
      return this.marketing;
    },
    submitAccountsPage() {
      return this.accounts.slice((this.submitAccountPage - 1) * this.submitAccountPageSize, this.submitAccountPage * this.submitAccountPageSize);
    },
    submitTopicsPage() {
      return this.topics.slice((this.submitTopicPage - 1) * this.submitTopicPageSize, this.submitTopicPage * this.submitTopicPageSize);
    }
  },
  created() {
    this.$watch(() => this.accounts, () => {
      this.submitAccountPage = 1;
    });
    this.$watch(() => this.topics, () => {
      this.submitTopicPage = 1;
    });
    this.$watch(() => this.submitAccountPageSize, () => {
      this.submitAccountPage = 1;
    });
    this.$watch(() => this.submitTopicPageSize, () => {
      this.submitTopicPage = 1;
    });
  }
};
</script>

<template>
<div class="manual-submit-groups">
          <section v-if="!isMarketing" class="manual-submit-group">
            <div class="manual-submit-group-head"><h3>本次策划账号</h3><span>{{ selectedAccounts.length }} 个</span></div>
            <div class="manual-submit-items manual-submit-table">
              <table class="manual-submit-account-table">
                <colgroup><col style="width:42%" /><col style="width:35%" /><col style="width:23%" /></colgroup>
                <thead><tr><th>账号昵称</th><th>账号ID</th><th>账号类型</th></tr></thead>
                <tbody><tr v-for="account in submitAccountsPage" :key="account.account_id">
                  <td><HoverHint :text="account.account_name" :show-icon="false" overflow-only class="manual-submit-tooltip"><span class="manual-submit-truncate account-name">{{ account.account_name }}</span></HoverHint></td>
                  <td><HoverHint :text="account.account_id || '—'" :show-icon="false" overflow-only class="manual-submit-tooltip"><span class="manual-submit-truncate identifier">{{ account.account_id || '—' }}</span></HoverHint></td>
                  <td><AccountTypeBadge :type="account.account_type || (account.certified === true ? '认证' : account.certified === false ? '非认证' : '')" /></td>
                </tr></tbody>
              </table>
            </div>
            <ListPagination :page.sync="submitAccountPage" :page-size.sync="submitAccountPageSize" :total="selectedAccounts.length" unit="个账号" :page-size-options="[10, 20, 50]" class="manual-submit-pagination" />
          </section>
          <section class="manual-submit-group" :class="{ 'manual-marketing-topic-group': isMarketing }">
            <div class="manual-submit-group-head"><h3>本次使用选题</h3><span>{{ selectedTopics.length }} 个</span></div>
            <div class="manual-submit-items manual-submit-table">
              <MarketingTopicTable v-if="isMarketing" :topics="submitTopicsPage" />
              <table v-else class="manual-submit-topic-table" data-native-confirm="true">
                <colgroup><col style="width:21%" /><col style="width:27%" /><col style="width:34%" /><col style="width:18%" /></colgroup>
                <thead><tr><th>选题 ID</th><th>选题标题</th><th>选题大纲</th><th>选题二级分类</th></tr></thead>
                <tbody><tr v-for="topic in submitTopicsPage" :key="topic.topic_id">
                  <td><HoverHint :text="topic.topic_id" :show-icon="false" overflow-only class="manual-submit-tooltip"><span class="manual-submit-truncate identifier">{{ topic.topic_id }}</span></HoverHint></td>
                  <td><HoverHint :text="topic.topic_title" :show-icon="false" overflow-only class="manual-submit-tooltip"><span class="manual-submit-truncate topic-title">{{ topic.topic_title }}</span></HoverHint></td>
                  <td><HoverHint :text="topic.outline || '暂无选题大纲'" :show-icon="false" overflow-only class="manual-submit-tooltip"><span class="manual-submit-truncate topic-outline">{{ topic.outline || '暂无选题大纲' }}</span></HoverHint></td>
                  <td><HoverHint :text="topic.content_type || '—'" :show-icon="false" overflow-only class="manual-submit-tooltip"><span class="manual-submit-truncate">{{ topic.content_type || '—' }}</span></HoverHint></td>
                </tr></tbody>
              </table>
            </div>
            <ListPagination :page.sync="submitTopicPage" :page-size.sync="submitTopicPageSize" :total="selectedTopics.length" unit="个选题" :page-size-options="[10, 20, 50]" class="manual-submit-pagination" />
          </section>
        </div>
</template>
<style scoped>
.manual-submit-summary{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.manual-submit-summary>div{display:flex;flex-direction:column;gap:6px;padding:14px;border:1px solid var(--neutral-200);border-radius:8px}
.manual-submit-summary span,.manual-submit-group-head h3{color:var(--neutral-400);font-size:12px}
.manual-submit-groups{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:18px}
.manual-submit-group{min-width:0;padding:14px;border:1px solid var(--neutral-200);border-radius:9px;background:var(--surface)}
.manual-submit-group-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:9px}
.manual-submit-group-head h3{margin:0;color:var(--neutral-700);font-size:13px}
.manual-submit-group-head>span{color:var(--primary-600);font-size:12px;font-weight:600}
.manual-submit-items{height:300px;overflow-y:scroll;scrollbar-gutter:stable}
.manual-submit-pagination{margin-top:10px}
.manual-marketing-topic-group{grid-column:1/-1}
.manual-submit-table{overflow:auto;border:1px solid var(--neutral-200);border-radius:6px}
.manual-submit-table table{width:100%;min-width:0;table-layout:fixed}
.manual-submit-table .marketing-topic-table{min-width:1080px;table-layout:auto}
.manual-submit-table th,.manual-submit-table td{padding:10px 8px;text-align:left;font-size:12px}
.manual-submit-table th{position:sticky;top:0;z-index:1;background:var(--neutral-50);white-space:nowrap}
.manual-submit-table ::v-deep .manual-submit-tooltip{width:100%;min-width:0;text-align:left;font-size:12px;color:var(--neutral-700)}
.manual-submit-truncate{display:block;min-width:0;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.manual-submit-truncate.account-name,.manual-submit-truncate.topic-title{font-weight:500;color:var(--neutral-800)}
.manual-submit-truncate.identifier{font-variant-numeric:tabular-nums;color:var(--neutral-500)}
.manual-submit-truncate.topic-outline{color:var(--neutral-600)}
@media(max-width:900px){.manual-submit-groups{grid-template-columns:1fr}}
@media(max-width:580px){.manual-account-filters,.manual-topic-filters,.manual-submit-summary{grid-template-columns:1fr}}
</style>
