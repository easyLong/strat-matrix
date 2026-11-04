<script lang="ts">
import { defineComponent, type PropType } from '../compat/composition';
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from '../compat/composition';
import { RouterLink } from '../compat/router';
import { pageBreadcrumbsKey, type PageBreadcrumb } from '../composables/usePageBreadcrumbs';
export default defineComponent({
    props: { items: { required: false, type: Array as PropType<PageBreadcrumb[]> },
        compact: { required: false, type: Boolean as PropType<boolean> } },
    setup(props, context) {
        const inherited = inject(pageBreadcrumbsKey, computed(() => []));
        const entries = computed(() => props.items ?? inherited.value);
        const navigation = ref<HTMLElement | null>(null);
        let resizeObserver: ResizeObserver | undefined;
        function showCurrentLocation() {
            if (navigation.value)
                navigation.value.scrollLeft = navigation.value.scrollWidth;
        }
        watch(() => entries.value.map(item => item.label).join('>'), async () => {
            await nextTick();
            showCurrentLocation();
        }, {
            immediate: true,
            flush: 'post'
        });
        onMounted(() => {
            resizeObserver = new ResizeObserver(showCurrentLocation);
            if (navigation.value)
                resizeObserver.observe(navigation.value);
        });
        onBeforeUnmount(() => resizeObserver?.disconnect());
        function activate(item: PageBreadcrumb) {
            item.beforeNavigate?.();
            void item.action?.();
        }
        return {
            entries,
            navigation,
            activate
        };
    },
    components: {RouterLink}
});
</script>

<template>
  <nav ref="navigation" class="breadcrumb page-breadcrumb" :class="{ compact }" :aria-label="compact ? '详情位置' : '当前位置'">
    <template v-for="(item, index) in entries" >
      <svg :key="(`${index}-${item.label}`) + '-0'" v-if="index" width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m6 4 4 4-4 4" /></svg>
      <span :key="(`${index}-${item.label}`) + '-1'" v-if="index === entries.length - 1" aria-current="page">{{ item.label }}</span>
      <button :key="(`${index}-${item.label}`) + '-2'" v-else-if="item.action" type="button" @click="activate(item)">{{ item.label }}</button>
      <RouterLink :key="(`${index}-${item.label}`) + '-3'" v-else-if="item.to" :to="item.to" aria-current-value="false" @click.native="activate(item)">{{ item.label }}</RouterLink>
      <span :key="(`${index}-${item.label}`) + '-4'" v-else>{{ item.label }}</span>
    </template>
  </nav>
</template>

<style scoped>
.page-breadcrumb{min-width:0;max-width:100%;overflow-x:auto;white-space:nowrap;scrollbar-width:thin}
.page-breadcrumb>*{flex-shrink:0}
.page-breadcrumb a,.page-breadcrumb button{padding:0;border:0;background:transparent;color:inherit;font:inherit;text-decoration:none;cursor:pointer}
.page-breadcrumb a:hover,.page-breadcrumb button:hover{color:var(--primary-600)}
.page-breadcrumb a:focus-visible,.page-breadcrumb button:focus-visible{outline:2px solid var(--primary-600);outline-offset:2px;border-radius:2px}
.page-breadcrumb [aria-current=page]{color:var(--neutral-600);font-weight:500}
.page-breadcrumb.compact{margin-bottom:16px;font-size:12px}
</style>
