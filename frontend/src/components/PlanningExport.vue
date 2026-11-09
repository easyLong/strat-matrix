<script>
import DialogTitle from './DialogTitle.vue';
import DateRangeFields from './DateRangeFields.vue';
import { canPlanning } from '../host/runtime';
import { requestBlob } from '../api/http';
export default {
  props: {
    accounts: {
      required: false,
      type: Array
    },
    batches: {
      required: false,
      type: Array
    },
    inline: {
      required: false,
      type: Boolean
    },
    filename: {
      required: false,
      type: String
    },
    scope: {
      required: false,
      type: null
    },
    accountDates: {
      required: false,
      type: Boolean
    }
  },
  components: {
    DialogTitle,
    DateRangeFields
  },
  data() {
    return {
      opened: false,
      start: '',
      end: '',
      busy: false,
      error: ''
    };
  },
  computed: {
    canPlanning() {
      return canPlanning;
    }
  },
  methods: {
    async download() {
      this.error = '';
      if ((this.accounts || this.accountDates) && (!this.start || !this.end || this.start > this.end)) {
        this.error = '请选择有效的开始时间和截止时间';
        return;
      }
      this.busy = true;
      try {
        const scope = this.scope || {
          mode: 'all',
          page: 1,
          page_size: 200,
          filters: {},
          account_ids: this.accounts,
          batch_ids: this.accounts ? undefined : (this.batches || []).map(b => b.id)
        };
        const response = await requestBlob('/query/export', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            ...scope,
            format: 'xlsx',
            filters: {
              ...scope.filters,
              ...(this.accounts || this.accountDates ? {
                start: this.start,
                end: this.end
              } : {})
            }
          })
        });
        const data = response.data;
        const url = URL.createObjectURL(data);
        const link = document.createElement('a');
        link.href = url;
        const extension = String(response.headers['content-type'] || data.type).includes('spreadsheetml.sheet') ? 'xlsx' : 'csv';
        const filename = this.filename || `${this.accounts || this.accountDates ? '账号' : '时间'}策划明细.xlsx`;
        link.download = /\.(csv|xlsx)$/i.test(filename) ? filename.replace(/\.(csv|xlsx)$/i, `.${extension}`) : `${filename}.${extension}`;
        link.click();
        URL.revokeObjectURL(url);
        this.opened = false;
      } catch (exc) {
        this.error = exc instanceof Error ? exc.message : '导出失败，请重试';
      } finally {
        this.busy = false;
      }
    }
  }
};
</script>

<template>
<div class="vue2-component-root">
  <button v-if="canPlanning('results.export')" type="button" :class="inline ? 'text-btn' : 'btn'" @click="opened = true">导出报表</button>
  <BodyPortal>
    <div v-if="opened" class="export-mask" @click.self="!busy && (opened = false)">
      <section class="export-dialog" role="dialog" aria-modal="true" aria-labelledby="export-title">

        <DialogTitle id="export-title" title="导出策划明细" />
        <div v-if="accounts || accountDates" class="export-dates"><DateRangeFields :start.sync="start" :end.sync="end" /></div>
        <p v-if="error" class="export-error" role="alert">{{ error }}</p>
        <div class="export-actions"><button class="btn" type="button" :disabled="busy" @click="opened = false">取消</button><button class="btn primary" type="button" :disabled="busy" @click="download">{{ busy ? '导出中…' : '确认导出' }}</button></div>
      </section>
    </div>
  </BodyPortal>
</div>
</template>

<style scoped>
.export-mask{position:fixed;inset:0;z-index:300;background:var(--mask);display:flex;align-items:center;justify-content:center}.export-dialog{box-sizing:border-box;width:min(440px,calc(100vw - 24px));padding:24px;background:var(--surface);border-radius:4px;box-shadow:var(--shadow-4)}h3{margin:0 0 20px}.export-dates{display:flex;gap:16px}.export-dates label{display:flex;flex:1;min-width:0;flex-direction:column;gap:8px;color:var(--neutral-600);font-size:13px}.export-dates input{width:100%;height:32px;box-sizing:border-box;padding:0 8px;border:1px solid var(--neutral-200);border-radius:4px;color:var(--neutral-900);font:inherit}.export-dates input:focus{outline:none;border-color:var(--primary-600);box-shadow:var(--focus-ring)}.export-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:24px}.export-error{color:var(--danger);font-size:13px}@media(max-width:400px){.export-dates{flex-direction:column;gap:12px}}
</style>
