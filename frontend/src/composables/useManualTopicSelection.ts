import { computed, ref, watch, type Ref } from '../compat/composition';
import type { TopicOption } from '../types';
import { beijingDate, manualTopicTooltip, marketingTopicName, topicValidOn } from '../ui/manualTopics';
export function useManualTopicSelection({ topics, isMarketing, publishDate, topicReview, error, today = ref(beijingDate()) }: {
    topics: Ref<TopicOption[]>;
    isMarketing: Ref<boolean>;
    publishDate: Ref<string>;
    topicReview: Ref<boolean>;
    error: Ref<string>;
    today?: Ref<string>;
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
        topicTypeFilter.value = isMarketing.value ? 'marketing' : 'non_marketing';
        appliedTopicFilters.value = { topicId: topicIdFilter.value, query: topicQuery.value, topicType: topicTypeFilter.value, contentType: contentType.value, product: relatedProduct.value, activity: relatedActivity.value, hotspot: relatedHotspot.value };
        topicPage.value = 1;
    }
    const contentTypes = computed(() => [...new Set(topics.value.map(item => item.content_type).filter(Boolean))].sort());
    const relatedProducts = computed(() => [...new Set(topics.value.map(item => item.related_product).filter(Boolean))].sort());
    const relatedActivities = computed(() => [...new Set(topics.value.map(item => item.related_activity).filter(Boolean))].sort());
    const relatedHotspots = computed(() => [...new Set(topics.value.map(item => item.related_hotspot).filter(Boolean))].sort());
    const referenceDate = computed(() => isMarketing.value ? today.value : publishDate.value);
    const eligibleTopics = computed(() => topics.value.filter(topic => topic.is_marketing === isMarketing.value &&
        !['停用', '已停用', '不可用'].includes(topic.status) && topicValidOn(topic, referenceDate.value)));
    const validityHint = computed(() => isMarketing.value
        ? `仅支持选择当前日期（${referenceDate.value}）在有效期内的营销选题。`
        : `仅支持选择投放日期（${referenceDate.value || '未选择'}）在有效期内的非营销选题。`);
    const filteredTopics = computed(() => eligibleTopics.value.filter(topic =>
        (!appliedTopicFilters.value.topicId.trim() || topic.topic_id === appliedTopicFilters.value.topicId.trim()) &&
        (!appliedTopicFilters.value.query.trim() || (isMarketing.value ? marketingTopicName(topic) : topic.topic_title).toLocaleLowerCase().includes(appliedTopicFilters.value.query.trim().toLocaleLowerCase())) &&
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
        if (checked && !eligibleTopics.value.some(topic => topic.topic_id === topicId)) {
            error.value = '该选题类型或有效期不符合本次策划要求，请重新选择';
            return;
        }
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
    const topicTooltip = manualTopicTooltip;
    const selectionValid = computed(() => selectedTopicIds.value.length > 0 && selectedTopicIds.value.every(id => eligibleTopics.value.some(topic => topic.topic_id === id)));
    function validateSelection() {
        today.value = beijingDate();
        if (selectionValid.value) return true;
        error.value = '所选选题已不符合类型或有效期要求，请返回选择选题';
        topicReview.value = false;
        return false;
    }
    watch(eligibleTopics, available => {
        const retained = selectedTopicIds.value.filter(id => available.some(topic => topic.topic_id === id));
        if (retained.length !== selectedTopicIds.value.length) {
            selectedTopicIds.value = retained;
            topicReview.value = false;
            error.value = '部分已选选题不符合当前类型或日期的有效期要求，已移除，请重新确认';
        }
    }, { flush: 'sync' });
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
    return { topicListRef, topicFiltersExpanded, selectedTopicIds, topicIdFilter, topicQuery, topicTypeFilter, contentType, relatedProduct, relatedActivity, relatedHotspot, appliedTopicFilters, topicPage, topicPageSize, contentTypes, relatedProducts, relatedActivities, relatedHotspots, filteredTopics, topicPageCount, pagedTopics, selectedTopics, validityHint, selectionValid, validateSelection, applyTopicFilters, toggleTopicRow, setTopicSelected, removeTopic, topicTooltip, reset };
}
export type ManualTopicSelection = ReturnType<typeof useManualTopicSelection>;
