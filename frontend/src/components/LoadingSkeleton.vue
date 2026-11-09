<script>
export default {
  props: {
    rows: {
      required: false,
      type: Number,
      default: 6
    }
  },
  data() {
    return {
      visible: false,
      timer: undefined
    };
  },
  mounted() {
    this.timer = setTimeout(() => {
      this.visible = true;
    }, 800);
  },
  beforeDestroy() {
    if (this.timer) clearTimeout(this.timer);
  }
};
</script>
<template>
  <div class="skeleton-list" :class="visible ? 'skeleton-visible' : 'skeleton-pending'" aria-label="正在加载" role="status" aria-busy="true"><div v-for="row in rows" :key="row" class="skeleton-row" aria-hidden="true"><span class="skeleton-bar" /><span class="skeleton-bar" /><span class="skeleton-bar" /></div></div>
</template>
