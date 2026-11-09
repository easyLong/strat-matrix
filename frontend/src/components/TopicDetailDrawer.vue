<script>
import { bindPageActivity } from "../services/pageActivity";
import { api } from '../api';
import TopicLabelDetails from './TopicLabelDetails.vue';
export default {
  props: {
    topic: {
      required: true,
      type: null
    },
    items: {
      required: true,
      type: null
    }
  },
  components: {
    TopicLabelDetails
  },
  data() {
    return {
      loaded: null,
      loading: false,
      error: '',
      returnFocus: document.activeElement instanceof HTMLElement ? document.activeElement : null,
      requestId: 0,
      drawerActive: null
    };
  },
  computed: {
    panel: {
      cache: false,
      get() {
        return this.$refs.panel || null;
      }
    },
    detail() {
      return this.loaded ?? this.topic;
    }
  },
  methods: {
    keyboard(event) {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        this.$emit('close');
        return;
      }
      if (event.key !== 'Tab') return;
      const nodes = this.panel?.querySelectorAll('button:not(:disabled), a[href], input:not(:disabled), [tabindex="0"]');
      if (!nodes?.length) return;
      const first = nodes[0],
        last = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    },
    emit(...args) {
      return this.$emit(...args);
    }
  },
  created() {
    this.$watch(() => [this.topic.topic_id, this.topic.topic_type], async () => {
      const request = ++this.requestId;
      this.loaded = null;
      this.error = '';
      this.loading = true;
      try {
        const row = await api.topicDetail(this.topic.topic_id, this.topic.topic_type);
        if (request === this.requestId) this.loaded = row;
      } catch (exc) {
        if (request === this.requestId) this.error = exc instanceof Error ? exc.message : '读取选题详情失败';
      } finally {
        if (request === this.requestId) this.loading = false;
      }
    }, {
      immediate: true
    });
    this.drawerActive = bindPageActivity(this, async () => {
      document.addEventListener('keydown', this.keyboard, true);
      await this.$nextTick();
      if (this.drawerActive.active) this.panel?.querySelector('button')?.focus();
    }, () => {
      document.removeEventListener('keydown', this.keyboard, true);
      if (this.returnFocus?.isConnected && this.returnFocus.getClientRects().length) this.returnFocus.focus({
        preventScroll: true
      });
    });
  },
  beforeDestroy() {
    this.requestId++;
  }
};
</script>
<template>
  <BodyPortal><div class="drawer-mask topic-detail-mask" @click.self="emit('close')"><aside ref="panel" class="drawer topic-detail-drawer" role="dialog" aria-modal="true" aria-label="选题详情"><div class="drawer-head"><h2>选题详情</h2><button class="icon-btn" type="button" aria-label="关闭选题详情" @click="emit('close')">×</button></div><div class="drawer-body">

    <div class="topic-detail-heading"><h3 class="topic-identity-inline"><span>{{ detail.topic_title || '—' }}</span><span class="topic-identity-separator">-</span><span>{{ detail.topic_id || '—' }}</span></h3><div class="topic-detail-meta"><span>{{ detail.content_type || '未设置选题二级分类' }}</span><span>{{ detail.is_marketing ? '营销' : '非营销' }}</span><span v-if="detail.label_status">{{ detail.label_status }}</span></div></div>
    <section class="topic-detail-outline"><h4>选题大纲</h4><p>{{ detail.outline || '暂无选题大纲' }}</p></section>
    <div class="topic-detail-validity"><span>有效期</span><b>{{ detail.valid_from?.slice(0, 10) || '不限' }} 至 {{ detail.valid_to?.slice(0, 10) || '不限' }}</b></div>
    <div v-if="error" class="banner error-banner" role="alert">{{ error }}</div><div v-if="loading" class="topic-detail-loading" role="status">正在读取标签…</div><TopicLabelDetails v-else :topic="detail" :items="items" />
  </div></aside></div></BodyPortal>
</template>
<style scoped>
.topic-detail-mask{z-index:100}.topic-detail-drawer{width:min(680px,96vw)}.topic-detail-drawer .drawer-body{overflow-y:auto;overscroll-behavior:contain}.topic-detail-heading{padding-bottom:18px}.topic-detail-id{font-size:12px;color:var(--neutral-400)}.topic-detail-heading h3{margin:8px 0 12px;font-size:19px;line-height:1.5}.topic-detail-meta{display:flex;gap:14px;color:var(--neutral-500);font-size:12px}.topic-detail-outline{padding:16px;border:1px solid var(--neutral-200);border-radius:8px;margin-bottom:16px}.topic-detail-outline h4{margin:0 0 9px;font-size:13px}.topic-detail-outline p{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;line-height:1.8;color:var(--neutral-600)}.topic-detail-validity{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0 0 20px;font-size:12px}.topic-detail-validity>span{color:var(--neutral-400)}.topic-detail-validity>b{color:var(--neutral-600);font-weight:400}.topic-detail-loading{padding:24px;color:var(--neutral-400);font-size:13px}
</style>
