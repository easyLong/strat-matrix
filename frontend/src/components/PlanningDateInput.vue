<script>
import { DatePicker, TimePicker } from 'element-ui';

function dayKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

export default {
  name: 'PlanningDateInput',
  inheritAttrs: false,
  components: { DatePicker, TimePicker },
  props: {
    value: { type: String, default: '' },
    kind: { type: String, default: 'date', validator: value => ['date', 'time'].includes(value) },
    min: { type: String, default: '' },
    max: { type: String, default: '' },
    inputId: { type: String, default: '' },
    placeholder: { type: String, default: '' },
    required: Boolean,
    disabled: Boolean,
  },
  computed: {
    pickerComponent() { return this.kind === 'time' ? 'TimePicker' : 'DatePicker'; },
    displayFormat() { return this.kind === 'time' ? 'HH:mm' : 'yyyy/MM/dd'; },
    valueFormat() { return this.kind === 'time' ? 'HH:mm' : 'yyyy-MM-dd'; },
    resolvedInputId() { return this.inputId || `planning-date-${this._uid}`; },
    pickerOptions() {
      if (this.kind === 'time') return {};
      return { firstDayOfWeek: 1, disabledDate: date => {
        const key = dayKey(date);
        return Boolean((this.min && key < this.min) || (this.max && key > this.max));
      } };
    },
  },
  deactivated() { this.closePicker(); },
  methods: {
    closePicker() {
      if (this.$refs.picker) this.$refs.picker.pickerVisible = false;
    },
    updateValue(value) { this.$emit('input', value || ''); },
    enter() { this.$nextTick(() => this.$emit('enter')); },
  },
};
</script>

<template>
  <component :is="pickerComponent" ref="picker" class="planning-date-input" size="small"
    :value="value || null" :format="displayFormat" :value-format="valueFormat"
    :placeholder="placeholder || (kind === 'time' ? '请选择时间' : '请选择日期')"
    :id="resolvedInputId" :aria-required="String(required)"
    :disabled="disabled" :clearable="!required" :picker-options="pickerOptions"
    popper-class="planning-ui planning-picker-popper" v-bind="$attrs"
    @input="updateValue" @keydown.native.enter="enter" />
</template>
