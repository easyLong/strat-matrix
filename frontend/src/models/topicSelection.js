import Vue from "vue";
import { beijingDate, manualTopicTooltip, marketingTopicName, topicValidOn } from '../ui/manualTopics';
export function createTopicSelection(owner) {
  return new Vue({
    data() {
      return {
        topicListRef: null,
        topicFiltersExpanded: true,
        selectedTopicIds: [],
        topicIdFilter: '',
        topicQuery: '',
        topicTypeFilter: null,
        contentType: '',
        relatedProduct: '',
        relatedActivity: '',
        relatedHotspot: '',
        appliedTopicFilters: null,
        topicPage: 1,
        topicPageSize: 20,
        topicTooltip: manualTopicTooltip
      };
    },
    computed: {
      today: {
        get() {
          return owner.today;
        },
        set(value) {
          owner.today = value;
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
      topicReview: {
        get() {
          return owner.topicReview;
        },
        set(value) {
          owner.topicReview = value;
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
      isMarketing: {
        get() {
          return owner.isMarketing;
        },
        set(value) {
          owner.isMarketing = value;
        }
      },
      topics: {
        get() {
          return owner.topics;
        },
        set(value) {
          owner.topics = value;
        }
      },
      contentTypes() {
        return [...new Set(this.topics.map(item => item.content_type).filter(Boolean))].sort();
      },
      relatedProducts() {
        return [...new Set(this.topics.map(item => item.related_product).filter(Boolean))].sort();
      },
      relatedActivities() {
        return [...new Set(this.topics.map(item => item.related_activity).filter(Boolean))].sort();
      },
      relatedHotspots() {
        return [...new Set(this.topics.map(item => item.related_hotspot).filter(Boolean))].sort();
      },
      referenceDate() {
        return this.isMarketing ? this.today : this.publishDate;
      },
      eligibleTopics() {
        return this.topics.filter(topic => topic.is_marketing === this.isMarketing && !['停用', '已停用', '不可用'].includes(topic.status) && topicValidOn(topic, this.referenceDate));
      },
      validityHint() {
        return this.isMarketing ? `仅支持选择当前日期（${this.referenceDate}）在有效期内的营销选题。` : `仅支持选择投放日期（${this.referenceDate || '未选择'}）在有效期内的非营销选题。`;
      },
      filteredTopics() {
        return this.eligibleTopics.filter(topic => (!this.appliedTopicFilters.topicId.trim() || topic.topic_id === this.appliedTopicFilters.topicId.trim()) && (!this.appliedTopicFilters.query.trim() || (this.isMarketing ? marketingTopicName(topic) : topic.topic_title).toLocaleLowerCase().includes(this.appliedTopicFilters.query.trim().toLocaleLowerCase())) && (!this.appliedTopicFilters.contentType || topic.content_type === this.appliedTopicFilters.contentType) && (!this.appliedTopicFilters.product || topic.related_product === this.appliedTopicFilters.product) && (!this.appliedTopicFilters.activity || topic.related_activity === this.appliedTopicFilters.activity) && (!this.appliedTopicFilters.hotspot || topic.related_hotspot === this.appliedTopicFilters.hotspot));
      },
      topicPageCount() {
        return Math.max(1, Math.ceil(this.filteredTopics.length / this.topicPageSize));
      },
      pagedTopics() {
        return this.filteredTopics.slice((this.topicPage - 1) * this.topicPageSize, this.topicPage * this.topicPageSize);
      },
      selectedTopics() {
        return this.selectedTopicIds.map(id => this.topics.find(item => item.topic_id === id)).filter(item => !!item);
      },
      selectionValid() {
        return this.selectedTopicIds.length > 0 && this.selectedTopicIds.every(id => this.eligibleTopics.some(topic => topic.topic_id === id));
      }
    },
    methods: {
      applyTopicFilters() {
        if (this.topicReview) return;
        this.topicTypeFilter = this.isMarketing ? 'marketing' : 'non_marketing';
        this.appliedTopicFilters = {
          topicId: this.topicIdFilter,
          query: this.topicQuery,
          topicType: this.topicTypeFilter,
          contentType: this.contentType,
          product: this.relatedProduct,
          activity: this.relatedActivity,
          hotspot: this.relatedHotspot
        };
        this.topicPage = 1;
      },
      toggleTopicRow(topicId, event) {
        if (this.interactiveRowTarget(event)) return;
        if (this.isMarketing) {
          this.setTopicSelected(topicId, true);
          return;
        }
        this.setTopicSelected(topicId, !this.selectedTopicIds.includes(topicId));
      },
      setTopicSelected(topicId, checked) {
        if (this.topicReview) return;
        if (checked && !this.eligibleTopics.some(topic => topic.topic_id === topicId)) {
          this.error = '该选题类型或有效期不符合本次策划要求，请重新选择';
          return;
        }
        if (this.isMarketing) {
          this.selectedTopicIds = checked ? [topicId] : [];
          this.error = '';
          return;
        }
        if (checked) {
          if (this.selectedTopicIds.includes(topicId) || this.selectedTopicIds.length >= 100) return;
          this.selectedTopicIds = [...this.selectedTopicIds, topicId];
        } else {
          this.selectedTopicIds = this.selectedTopicIds.filter(id => id !== topicId);
        }
        this.error = '';
      },
      removeTopic(index) {
        if (this.topicReview) return;
        this.selectedTopicIds = this.selectedTopicIds.filter((_, itemIndex) => itemIndex !== index);
        this.topicReview = false;
      },
      validateSelection() {
        this.today = beijingDate();
        if (this.selectionValid) return true;
        this.error = '所选选题已不符合类型或有效期要求，请返回选择选题';
        this.topicReview = false;
        return false;
      },
      interactiveRowTarget(event) {
        return event.target instanceof Element && Boolean(event.target.closest('input, button, a, select, textarea, label'));
      },
      reset() {
        this.selectedTopicIds = [];
        this.topicIdFilter = '';
        this.topicQuery = '';
        this.contentType = '';
        this.relatedProduct = '';
        this.relatedActivity = '';
        this.relatedHotspot = '';
        this.topicTypeFilter = this.isMarketing ? 'marketing' : 'non_marketing';
        this.appliedTopicFilters = {
          topicId: '',
          query: '',
          topicType: this.topicTypeFilter,
          contentType: '',
          product: '',
          activity: '',
          hotspot: ''
        };
        this.topicFiltersExpanded = true;
        this.topicPage = 1;
      }
    },
    created() {
      this.topicTypeFilter = this.isMarketing ? 'marketing' : 'non_marketing';
      this.appliedTopicFilters = {
        topicId: '',
        query: '',
        topicType: this.topicTypeFilter,
        contentType: '',
        product: '',
        activity: '',
        hotspot: ''
      };
      this.$watch(() => this.eligibleTopics, available => {
        const retained = this.selectedTopicIds.filter(id => available.some(topic => topic.topic_id === id));
        if (retained.length !== this.selectedTopicIds.length) {
          this.selectedTopicIds = retained;
          this.topicReview = false;
          this.error = '部分已选选题不符合当前类型或日期的有效期要求，已移除，请重新确认';
        }
      }, {
        sync: true
      });
      this.$watch(() => this.topicPageSize, () => {
        this.topicPage = 1;
      });
      this.$watch(() => this.topicPageCount, count => {
        this.topicPage = Math.min(this.topicPage, count);
      });
    }
  });
}
