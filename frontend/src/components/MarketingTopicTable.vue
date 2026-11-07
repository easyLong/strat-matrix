<script lang="ts">
import { defineComponent, type PropType } from '../compat/composition';
import HoverHint from './HoverHint.vue';
import type { TopicOption } from '../types';
import { marketingTopicName, topicValidityLabel } from '../ui/manualTopics';
export default defineComponent({
  components: { HoverHint },
  props: {
    topics: { type: Array as PropType<TopicOption[]>, required: true },
    selectable: { type: Boolean, default: false },
    selectedIds: { type: Array as PropType<string[]>, default: () => [] },
    readonly: { type: Boolean, default: false },
    validityHint: { type:String,default:'' },
  },
  setup(props, { emit }) {
    function select(topic: TopicOption, event: Event) {
      if (!props.selectable || props.readonly) return;
      if (event.type === 'click' && event.target instanceof Element && event.target.closest('input,button,a')) return;
      emit('select', topic.topic_id);
    }
    return { select, emit, marketingTopicName, topicValidityLabel };
  },
});
</script>
<template>
  <table class="marketing-topic-table">
    <thead><tr><th v-if="selectable">选择</th><th>选题 ID</th><th>选题二级分类</th><th>关联活动 ID</th><th>关联活动名称</th><th>所属组织</th><th>关联产品</th><th>产品 ID</th><th><HoverHint v-if="validityHint" :text="validityHint">有效期</HoverHint><template v-else>有效期</template></th></tr></thead>
    <tbody>
      <tr v-for="topic in topics" :key="topic.topic_id" :class="{ selected: selectedIds.includes(topic.topic_id), 'selection-row': selectable }" :tabindex="selectable ? 0 : undefined" :aria-disabled="selectable && readonly || undefined" @click="select(topic, $event)" @keydown.enter.self.prevent="select(topic, $event)" @keydown.space.self.prevent="select(topic, $event)">
        <td v-if="selectable"><input type="radio" name="marketing-topic" :checked="selectedIds.includes(topic.topic_id)" :disabled="readonly" :aria-label="`选择选题 ${marketingTopicName(topic)}`" @change="emit('select', topic.topic_id)" /></td>
        <td>{{ topic.topic_id }}</td><td>{{ topic.content_type || '—' }}</td><td>{{ topic.related_activity_id || '—' }}</td>
        <td><HoverHint :text="topic.related_activity || '—'" :show-icon="false" overflow-only><span class="truncate">{{ topic.related_activity || '—' }}</span></HoverHint></td>
        <td><HoverHint :text="topic.activity_organization || '—'" :show-icon="false" overflow-only><span class="truncate">{{ topic.activity_organization || '—' }}</span></HoverHint></td>
        <td><HoverHint :text="topic.related_product || '—'" :show-icon="false" overflow-only><span class="truncate">{{ topic.related_product || '—' }}</span></HoverHint></td>
        <td>{{ topic.related_product_id || '—' }}</td><td class="validity">{{ topicValidityLabel(topic) }}</td>
      </tr>
      <tr v-if="!topics.length"><td :colspan="selectable ? 9 : 8"><div class="empty-state">没有符合条件的可用选题</div></td></tr>
    </tbody>
  </table>
</template>
<style scoped>
.marketing-topic-table{width:100%;min-width:1080px;border-collapse:collapse}
th{position:sticky;top:0;z-index:1;background:var(--neutral-50);white-space:nowrap}
th,td{padding:12px 10px;text-align:left;font-size:13px;border-bottom:1px solid var(--neutral-100)}
.selection-row{cursor:pointer}.selection-row:hover,.selected{background:var(--primary-50)}
input{accent-color:var(--primary-600)}.truncate{display:block;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.validity{white-space:nowrap;font-size:12px;color:var(--neutral-600)}
</style>
