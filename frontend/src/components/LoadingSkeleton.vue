<script lang="ts">
import { defineComponent, type PropType } from '../compat/composition';
import { onBeforeUnmount, onMounted, ref } from '../compat/composition';
export default defineComponent({
    props: { rows: { required: false, type: Number as PropType<number>, default: 6 } },
    setup(props, context) {
        const visible = ref(false);
        let timer: ReturnType<typeof setTimeout> | undefined;
        onMounted(() => {
            timer = setTimeout(() => {
                visible.value = true;
            }, 800);
        });
        onBeforeUnmount(() => {
            if (timer)
                clearTimeout(timer);
        });
        return {
            visible
        };
    }
});
</script>
<template>
  <div class="skeleton-list" :class="visible ? 'skeleton-visible' : 'skeleton-pending'" aria-label="正在加载" role="status" aria-busy="true"><div v-for="row in rows" :key="row" class="skeleton-row" aria-hidden="true"><span class="skeleton-bar" /><span class="skeleton-bar" /><span class="skeleton-bar" /></div></div>
</template>
