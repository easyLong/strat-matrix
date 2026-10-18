<script setup lang="ts">
defineProps<{ type: string }>()
</script>
<template>
  <span class="account-type-badge" :class="{ certified: type === '认证' }"><svg v-if="type === '认证'" width="12" height="12" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><circle cx="8" cy="8" r="7" /><path d="m4.5 8 2.2 2.2 4.8-4.8" fill="none" stroke="white" stroke-width="1.5" /></svg>{{ type || '—' }}</span>
</template>
