<script lang="ts">
import Vue from 'vue'

/** Keep overlays outside scrolling/overflow containers; Vue owns their lifecycle. */
export default Vue.extend({
  name: 'BodyPortal',
  mounted() { document.body.appendChild(this.$el) },
  beforeDestroy() { this.$el.parentNode?.removeChild(this.$el) },
})
</script>
<template><div class="planning-body-portal"><slot /></div></template>
<style>.planning-body-portal { display: contents; }</style>
