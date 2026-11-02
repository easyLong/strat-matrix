import { computed, ref, watch, type Ref } from 'vue';
import type { TopicOption } from '../types';
export function useManualTopicSelection({ topics, isMarketing, topicReview, error }: {
    topics: Ref<TopicOption[]>;
    isMarketing: Ref<boolean>;
    topicReview: Ref<boolean>;
    error: Ref<string>;
}) {
    const topicListRef = ref<HTMLElement | null>(null);
    const topicFiltersExpanded = ref(true);
    const selectedTopicIds = ref<string[]>([]);
    const topicIdFilter = ref('');
    const topicQuery = ref('');
    const topicTypeFilter = ref<'marketing' | 'non_marketing'>(isMarketing.value ? 'marketing' : 'non_marketing');
    const contentType = ref('');
    const relatedProduct = ref('');
    const relatedActivity = ref('');
    const relatedHotspot = ref('');
    const appliedTopicFilters = ref({ topicId: '', query: '', topicType: topicTypeFilter.value, contentType: '', product: '', activity: '', hotspot: '' });
    const topicPage = ref(1);
    const topicPageSize = ref(20);
    function applyTopicFilters() {
        if (topicReview.value)
            return;
        appliedTopicFilters.value = { topicId: topicIdFilter.value, query: topicQuery.value, topicType: topicTypeFilter.value, contentType: contentType.value, product: relatedProduct.value, activity: relatedActivity.value, hotspot: relatedHotspot.value };
        topicPage.value = 1;
    }
    const contentTypes = computed(() => [...new Set(topics.value.map(item => item.content_type).filter(Boolean))].sort());
    const relatedProducts = computed(() => [...new Set(topics.value.map(item => item.related_product).filter(Boolean))].sort());
    const relatedActivities = computed(() => [...new Set(topics.value.map(item => item.related_activity).filter(Boolean))].sort());
    const relatedHotspots = computed(() => [...new Set(topics.value.map(item => item.related_hotspot).filter(Boolean))].sort());
    const filteredTopics = computed(() => topics.value.filter(topic => (appliedTopicFilters.value.topicType === 'marketing' ? topic.is_marketing : !topic.is_marketing) &&
        (!appliedTopicFilters.value.topicId.trim() || topic.topic_id === appliedTopicFilters.value.topicId.trim()) &&
        (!appliedTopicFilters.value.query.trim() || topic.topic_title.toLocaleLowerCase().includes(appliedTopicFilters.value.query.trim().toLocaleLowerCase())) &&
        (!appliedTopicFilters.value.contentType || topic.content_type === appliedTopicFilters.value.contentType) &&
        (!appliedTopicFilters.value.product || topic.related_product === appliedTopicFilters.value.product) &&
        (!appliedTopicFilters.value.activity || topic.related_activity === appliedTopicFilters.value.activity) &&
        (!appliedTopicFilters.value.hotspot || topic.related_hotspot === appliedTopicFilters.value.hotspot)));
    const topicPageCount = computed(() => Math.max(1, Math.ceil(filteredTopics.value.length / topicPageSize.value)));
    const pagedTopics = computed(() => filteredTopics.value.slice((topicPage.value - 1) * topicPageSize.value, topicPage.value * topicPageSize.value));
    const selectedTopics = computed(() => selectedTopicIds.value.map(id => topics.value.find(item => item.topic_id === id)).filter((item): item is TopicOption => !!item));
    function toggleTopicRow(topicId: string, event: Event) {
        if (interactiveRowTarget(event))
            return;
        if (isMarketing.value) {
            setTopicSelected(topicId, true);
            return;
        }
        setTopicSelected(topicId, !selectedTopicIds.value.includes(topicId));
    }
    function setTopicSelected(topicId: string, checked: boolean) {
        if (topicReview.value)
            return;
        if (isMarketing.value) {
            selectedTopicIds.value = checked ? [topicId] : [];
            error.value = '';
            return;
        }
        if (checked) {
            if (selectedTopicIds.value.includes(topicId) || selectedTopicIds.value.length >= 100)
                return;
            selectedTopicIds.value = [...selectedTopicIds.value, topicId];
        }
        else {
            selectedTopicIds.value = selectedTopicIds.value.filter(id => id !== topicId);
        }
        error.value = '';
    }
    function removeTopic(index: number) {
        if (topicReview.value)
            return;
        selectedTopicIds.value = selectedTopicIds.value.filter((_, itemIndex) => itemIndex !== index);
        topicReview.value = false;
    }
    function topicTooltip(topic: TopicOption) {
        const dash = '\u2014';
        const validity = `${topic.valid_from?.slice(0, 10) || dash} - ${topic.valid_to?.slice(0, 10) || dash}`;
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
        ].join('\n');
    }
    function interactiveRowTarget(event: Event) {
        return event.target instanceof Element && Boolean(event.target.closest('input, button, a, select, textarea, label'));
    }
    function reset() {
        selectedTopicIds.value = [];
        topicIdFilter.value = '';
        topicQuery.value = '';
        contentType.value = '';
        relatedProduct.value = '';
        relatedActivity.value = '';
        relatedHotspot.value = '';
        topicTypeFilter.value = isMarketing.value ? 'marketing' : 'non_marketing';
        appliedTopicFilters.value = { topicId: '', query: '', topicType: topicTypeFilter.value, contentType: '', product: '', activity: '', hotspot: '' };
        topicFiltersExpanded.value = true;
        topicPage.value = 1;
    }
    watch(topicPageSize, () => { topicPage.value = 1; });
    watch(topicPageCount, count => { topicPage.value = Math.min(topicPage.value, count); });
    return { topicListRef, topicFiltersExpanded, selectedTopicIds, topicIdFilter, topicQuery, topicTypeFilter, contentType, relatedProduct, relatedActivity, relatedHotspot, appliedTopicFilters, topicPage, topicPageSize, contentTypes, relatedProducts, relatedActivities, relatedHotspots, filteredTopics, topicPageCount, pagedTopics, selectedTopics, applyTopicFilters, toggleTopicRow, setTopicSelected, removeTopic, topicTooltip, reset };
}
export type ManualTopicSelection = ReturnType<typeof useManualTopicSelection>;
