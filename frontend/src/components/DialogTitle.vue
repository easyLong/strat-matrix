<script>
export default {
  name: 'DialogTitle',
  props: {
    title: {
      type: String,
      required: true
    },
    context: {
      type: String,
      default: ''
    }
  }
};
</script>
<template><h2 class="dialog-title-line" :title="context ? `${title} - ${context}` : title"><span>{{ title }}</span><template v-if="context"><span class="dialog-title-separator" aria-hidden="true">-</span><span class="dialog-title-context">{{ context }}</span></template></h2></template>
<style scoped>.dialog-title-line{display:flex;align-items:center;gap:8px;min-width:0;margin:0;font-size:16px;line-height:24px;font-weight:600;color:var(--neutral-900)}.dialog-title-line>span:first-child{flex:none}.dialog-title-separator{flex:none;color:var(--neutral-400);font-weight:400}.dialog-title-context{overflow:hidden;min-width:0;text-overflow:ellipsis;white-space:nowrap;font:inherit}</style>
