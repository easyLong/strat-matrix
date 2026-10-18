<script setup lang="ts">
import { computed } from 'vue'
import type { TopicOption } from '../types'
import { topicLabels, type TaxonomyItems } from '../topicTaxonomy'
const props = withDefaults(defineProps<{ topic: TopicOption; items?: TaxonomyItems }>(), { items: () => ({}) })
const labels = computed(() => topicLabels(props.topic, props.items))
const hasLabels = computed(() => props.topic.label_status === '已完成' || props.topic.label_status === 'completed')
</script>
<template>
  <div class="topic-label-details">
    <div class="topic-label-facts"><div><span>业务属性</span><b>{{ labels.business }}</b></div><div><span>适用范围</span><b>{{ labels.scope || '未提供' }}</b></div><div><span>经营作用</span><b>{{ labels.role || '未识别' }}</b></div></div>
    <section class="topic-label-section"><h4>T3 内容主题</h4><div class="topic-label-row"><span>主主题</span><span v-if="labels.primary" class="label-path"><small v-if="labels.primary.path.length > 1">{{ labels.primary.path.slice(0, -1).join(' / ') }} /</small><b>{{ labels.primary.name }}</b></span><span v-else class="label-missing">未识别</span></div><div class="topic-label-row"><span>关联主题</span><div v-if="labels.related.length" class="label-path-list"><span v-for="node in labels.related" :key="node.id" class="label-path" :title="node.path.join(' / ')"><small v-if="node.path.length > 1">{{ node.path.slice(0, -1).join(' / ') }} /</small>{{ node.name }}</span></div><span v-else class="label-missing">{{ hasLabels ? '无' : '未识别' }}</span></div></section>
    <section v-for="section in [{ title: 'T4 目标客群', nodes: labels.audience }, { title: 'T5 使用场景', nodes: labels.scenes }]" :key="section.title" class="topic-label-section"><h4>{{ section.title }}</h4><div v-if="section.nodes.length" class="label-path-list"><span v-for="node in section.nodes" :key="node.id" class="label-path" :title="node.path.join(' / ')"><small v-if="node.path.length > 1">{{ node.path.slice(0, -1).join(' / ') }} /</small>{{ node.name }}</span></div><span v-else class="label-missing">{{ hasLabels ? '未限定' : '未识别' }}</span></section>
    <section class="topic-label-section"><h4>T6 用户需求</h4><p class="topic-core-need" :class="{ 'is-empty': !labels.need }">{{ labels.need || '未识别' }}</p></section>
  </div>
</template>
<style scoped>
.topic-label-facts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;padding:15px 16px;border:1px solid var(--neutral-200);border-radius:8px;background:var(--neutral-50)}.topic-label-facts>div{display:flex;flex-direction:column;gap:7px}.topic-label-facts span,.topic-label-row>span:first-child{color:var(--neutral-400);font-size:12px}.topic-label-facts b{font-size:13px;font-weight:500;overflow-wrap:anywhere}.topic-label-section{padding:18px 0;border-bottom:1px solid var(--neutral-100)}.topic-label-section:last-child{border:0}.topic-label-section h4{margin:0 0 12px;font-size:13px;font-weight:600;color:var(--neutral-800)}.topic-label-row{display:flex;align-items:flex-start;gap:16px;margin-top:10px}.topic-label-row>span:first-child{min-width:48px;line-height:26px}.label-path-list{display:flex;flex-wrap:wrap;gap:7px}.label-path{display:inline-flex;align-items:center;gap:5px;padding:4px 8px;border-radius:5px;background:var(--primary-50);color:var(--primary-600);font-size:12px;line-height:18px;overflow-wrap:anywhere}.label-path small{color:var(--neutral-500);font-size:11px}.label-path b{font-weight:500}.label-missing{color:var(--neutral-400);font-size:12px;line-height:26px}.topic-core-need{margin:0;padding:12px 14px;border-radius:7px;background:var(--neutral-50);color:var(--neutral-700);font-size:13px;line-height:1.8;white-space:pre-wrap;overflow-wrap:anywhere}.topic-core-need.is-empty{color:var(--neutral-400)}
</style>
