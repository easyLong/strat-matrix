<script>
import { createUiId } from "../ui/instanceId";
import { bindPageActivity } from "../services/pageActivity";
export default {
  props: {
    text: {
      required: true,
      type: String
    },
    showIcon: {
      required: false,
      type: Boolean,
      default: true
    },
    overflowOnly: {
      required: false,
      type: Boolean,
      default: false
    }
  },
  inheritAttrs: false,
  data() {
    return {
      tooltipId: createUiId(),
      open: false,
      position: {
        left: '0px',
        top: '0px',
        visibility: 'hidden'
      },
      closeTimer: undefined,
      hovered: false,
      focused: false
    };
  },
  computed: {
    trigger: {
      cache: false,
      get() {
        return this.$refs.trigger || null;
      }
    },
    tooltip: {
      cache: false,
      get() {
        return this.$refs.tooltip || null;
      }
    }
  },
  methods: {
    close() {
      if (this.closeTimer !== undefined) clearTimeout(this.closeTimer);
      this.open = false;
    },
    place() {
      if (!this.open || !this.trigger || !this.tooltip) return;
      const anchor = this.trigger.getBoundingClientRect();
      const box = this.tooltip.getBoundingClientRect();
      const left = Math.max(12, Math.min(anchor.left, window.innerWidth - box.width - 12));
      const below = anchor.bottom + 8;
      const top = below + box.height <= window.innerHeight - 12 ? below : Math.max(12, anchor.top - box.height - 8);
      this.position = {
        left: `${left}px`,
        top: `${top}px`,
        visibility: 'visible'
      };
    },
    async show() {
      if (this.overflowOnly) {
        const content = this.trigger?.firstElementChild;
        if (!content || content.scrollWidth <= content.clientWidth) {
          this.close();
          return;
        }
      }
      if (this.closeTimer !== undefined) clearTimeout(this.closeTimer);
      if (!this.open) this.position.visibility = 'hidden';
      this.open = true;
      await this.$nextTick();
      this.place();
    },
    scheduleClose() {
      if (this.closeTimer !== undefined) clearTimeout(this.closeTimer);
      this.closeTimer = setTimeout(() => {
        if (!this.hovered && !this.focused) this.close();
      }, 120);
    },
    dismissOutside(event) {
      const target = event.target;
      if (target && !this.trigger?.contains(target) && !this.tooltip?.contains(target)) this.close();
    },
    dismissEscape(event) {
      if (event.key === 'Escape') this.close();
    }
  },
  created() {
    bindPageActivity(this, () => {
      document.addEventListener('pointerdown', this.dismissOutside);
      document.addEventListener('keydown', this.dismissEscape);
      window.addEventListener('resize', this.place);
      window.addEventListener('scroll', this.place, true);
    }, () => {
      this.close();
      if (this.closeTimer !== undefined) clearTimeout(this.closeTimer);
      document.removeEventListener('pointerdown', this.dismissOutside);
      document.removeEventListener('keydown', this.dismissEscape);
      window.removeEventListener('resize', this.place);
      window.removeEventListener('scroll', this.place, true);
    });
  }
};
</script>

<template>
<div class="vue2-component-root">
  <button ref="trigger" v-bind="$attrs" type="button" class="hover-hint" :aria-describedby="open ? tooltipId : undefined"
    @mouseenter="hovered = true; show()" @mouseleave="hovered = false; scheduleClose()"
    @focus="focused = true; show()" @blur="focused = false; scheduleClose()" @click="show">
    <slot />
    <span v-if="showIcon" class="field-help-tip" aria-hidden="true">?</span>
  </button>
  <BodyPortal>
    <div v-if="open" :id="tooltipId" ref="tooltip" class="hover-hint-tooltip" :style="position" role="tooltip"
      @mouseenter="hovered = true; show()" @mouseleave="hovered = false; scheduleClose()">{{ text }}</div>
  </BodyPortal>
</div>
</template>

<style scoped>
.hover-hint{display:inline-flex;align-items:center;gap:6px;padding:0;border:0;background:transparent;color:var(--neutral-500);font:inherit;font-size:13px;white-space:nowrap;cursor:help}
.hover-hint:hover,.hover-hint:focus-visible{color:var(--primary-600)}
.hover-hint:focus-visible{outline:2px solid var(--primary-600);outline-offset:3px;border-radius:4px}
.hover-hint .field-help-tip{flex-shrink:0;color:inherit}
.hover-hint-tooltip{position:fixed;z-index:1200;box-sizing:border-box;width:max-content;max-width:min(320px,calc(100vw - 24px));padding:10px 12px;border:1px solid var(--neutral-200);border-radius:8px;background:var(--surface);box-shadow:var(--shadow-3);color:var(--neutral-700);font-size:13px;line-height:20px;white-space:normal;overflow-wrap:anywhere}
</style>

<style scoped>
.hover-hint-tooltip{max-height:min(360px,calc(100vh - 24px));overflow-y:auto;overscroll-behavior:contain;white-space:pre-wrap}
</style>
