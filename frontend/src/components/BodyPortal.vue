<script lang="ts">
import Vue from 'vue'

/** Keep a stable anchor in Vue's parent tree; only move the inner overlay. */
export default Vue.extend({
  name: 'BodyPortal',
  mounted() { document.body.appendChild(this.$refs.content as HTMLElement) },
  activated() { (this.$refs.content as HTMLElement).style.removeProperty('display') },
  deactivated() { (this.$refs.content as HTMLElement).style.display = 'none' },
  beforeDestroy() {
    const content = this.$refs.content as HTMLElement
    content.parentNode?.removeChild(content)
  },
})
</script>
<template><div class="planning-portal-anchor" hidden><div ref="content" class="planning-ui planning-body-portal"><slot /></div></div></template>
<style scoped>.planning-body-portal { display: contents; }</style>
