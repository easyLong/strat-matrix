<script lang="ts">
import { defineComponent } from '../compat/composition'
export default defineComponent({ name: 'QueryActions', props: { disabled: Boolean } })
</script>
<template><div class="query-filter-actions"><button class="btn query-small" type="button" :disabled="disabled" @click="$emit('clear')">清空</button><button class="btn primary query-small" type="button" :disabled="disabled" @click="$emit('query')">查询</button></div></template>
<style scoped>.query-small{height:32px;min-height:32px;padding:0 12px;font-size:14px;line-height:20px}</style>
