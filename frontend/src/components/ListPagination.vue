<script>
export default {
  props: {
    page: {
      required: true,
      type: Number
    },
    pageSize: {
      required: true,
      type: Number
    },
    total: {
      required: true,
      type: Number
    },
    showTotal: {
      type: Boolean,
      default: true
    },
    unit: {
      required: false,
      type: String,
      default: '条'
    },
    pageSizeOptions: {
      required: false,
      type: Array,
      default: () => [10, 20, 50]
    }
  },
  computed: {
    count() {
      return Math.max(1, Math.ceil(this.total / this.pageSize));
    },
    pages() {
      const numbers = new Set([1, this.count]);
      for (let p = Math.max(1, this.page - 1); p <= Math.min(this.count, this.page + 1); p++) numbers.add(p);
      const sorted = [...numbers].sort((a, b) => a - b);
      return sorted.flatMap((page, index) => index && page - sorted[index - 1] > 1 ? [`gap-${page}`, page] : [page]);
    }
  },
  methods: {
    changeSize(event) {
      this.$emit('update:pageSize', Number(event.target.value));
      this.$emit('update:page', 1);
    },
    emit(...args) {
      return this.$emit(...args);
    }
  }
};
</script>
<template>
  <nav class="account-pagination" aria-label="分页">
    <span v-if="showTotal" class="pagination-total">共 {{ total }} {{ unit }}</span>
    <label>每页 <select :value="pageSize" aria-label="每页数量" @change="changeSize"><option v-for="size in pageSizeOptions" :key="size" :value="size">{{ size }}</option></select> {{ unit }}</label>
    <button class="btn" type="button" :disabled="page <= 1" @click="emit('update:page', page - 1)">上一页</button>
    <template v-for="value in pages" ><button :key="(value) + '-0'" v-if="typeof value === 'number'" :class="value === page ? 'current-page' : 'btn pagination-number'" :aria-current="value === page ? 'page' : undefined" :aria-label="`第 ${value} 页`" type="button" @click="emit('update:page', value)">{{ value }}</button><span :key="(value) + '-1'" v-else aria-hidden="true">…</span></template>
    <button class="btn" type="button" :disabled="page >= count" @click="emit('update:page', page + 1)">下一页</button>
  </nav>
</template>
