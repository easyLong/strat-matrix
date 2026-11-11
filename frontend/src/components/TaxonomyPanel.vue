<script>
import { bindPageActivity } from "../services/pageActivity";
import HoverHint from './HoverHint.vue';
import { isLeaf, newTaxonomyItem, tagGroups, tagKey, tagNames } from '../topicTaxonomy';
export default {
  props: {
    modelValue: {
      required: true,
      type: null
    },
    editing: {
      required: false,
      type: Boolean,
      default: false
    },
    disabled: {
      required: false,
      type: Boolean,
      default: false
    }
  },
  components: {
    HoverHint
  },
  model: {
    prop: 'modelValue',
    event: 'update:modelValue'
  },
  data() {
    return {
      active: 'T3',
      collapsed: [],
      groupInput: '',
      leafInputs: {},
      selected: null,
      renameValue: '',
      error: '',
      action: 'menu',
      position: {
        left: '0px',
        top: '0px'
      },
      anchor: null
    };
  },
  computed: {
    popover: {
      cache: false,
      get() {
        return this.$refs.popover || null;
      }
    },
    renameInput: {
      cache: false,
      get() {
        return this.$refs.renameInput || null;
      }
    },
    allGroups() {
      return tagGroups(this.modelValue, this.active, true);
    },
    groups() {
      return this.allGroups.filter(group => group.enabled).map(group => ({
        ...group,
        tags: group.tags.filter(tag => tag.enabled)
      }));
    },
    inactiveGroups() {
      return this.allGroups.map(group => ({
        ...group,
        tags: group.enabled ? group.tags.filter(tag => !tag.enabled) : group.tags
      })).filter(group => !group.enabled || group.tags.length);
    },
    selectedItem() {
      return (this.modelValue[this.active] ?? []).find(item => tagKey(item) === this.selected);
    },
    allCollapsed() {
      return this.groups.length > 0 && this.groups.every(group => this.collapsed.includes(group.id));
    },
    isLeaf() {
      return isLeaf;
    },
    tagKey() {
      return tagKey;
    },
    tagNames() {
      return tagNames;
    }
  },
  methods: {
    commit(items) {
      this.$emit('update:modelValue', {
        ...this.modelValue,
        [this.active]: items
      });
    },
    validateName(value, type, excluded) {
      if (!value || value.length > 80) {
        this.error = '名称需为1至80字';
        return false;
      }
      if ((this.modelValue[this.active] ?? []).some(item => tagKey(item) !== excluded && (item.node_type ?? 'tag') === type && item.name === value)) {
        this.error = type === 'group' ? '分类名称已存在' : '标签名称已存在';
        return false;
      }
      this.error = '';
      return true;
    },
    addGroup() {
      if (!this.editing || this.disabled) return;
      const name = this.groupInput.trim();
      if (!this.validateName(name, 'group')) return;
      this.commit([...(this.modelValue[this.active] ?? []), newTaxonomyItem(name, 'group')]);
      this.groupInput = '';
    },
    addLeaf(groupId) {
      if (!this.editing || this.disabled) return;
      const name = (this.leafInputs[groupId] ?? '').trim();
      if (!this.validateName(name, 'tag')) return;
      this.commit([...(this.modelValue[this.active] ?? []), newTaxonomyItem(name, 'tag', groupId === 'unassigned' ? null : groupId)]);
      this.leafInputs = {
        ...this.leafInputs,
        [groupId]: ''
      };
    },
    closeActions(restoreFocus = false) {
      const previousAnchor = this.anchor;
      this.selected = null;
      this.anchor = null;
      this.error = '';
      if (restoreFocus && previousAnchor?.isConnected) previousAnchor.focus({
        preventScroll: true
      });
    },
    positionActions() {
      if (!this.anchor?.isConnected || !this.popover) return;
      const rect = this.anchor.getBoundingClientRect();
      if (rect.bottom < 0 || rect.top > window.innerHeight) {
        this.closeActions();
        return;
      }
      const width = this.popover.offsetWidth;
      const height = this.popover.offsetHeight;
      const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
      const top = rect.bottom + 6 + height <= window.innerHeight - 8 ? rect.bottom + 6 : Math.max(8, rect.top - height - 6);
      this.position = {
        left: `${left}px`,
        top: `${top}px`
      };
    },
    async select(item, event) {
      if (!item) return;
      if (!this.editing || this.disabled) return;
      if (this.selected === tagKey(item)) {
        this.closeActions();
        return;
      }
      this.anchor = event.currentTarget;
      this.selected = tagKey(item);
      this.action = 'menu';
      this.renameValue = item.name;
      this.error = '';
      await this.$nextTick();
      this.positionActions();
      this.popover?.querySelector('.taxonomy-menu-item')?.focus({
        preventScroll: true
      });
    },
    async editAction(value) {
      this.action = value;
      this.error = '';
      await this.$nextTick();
      this.positionActions();
      if (value === 'rename') {
        this.renameInput?.focus({
          preventScroll: true
        });
        this.renameInput?.select();
      } else this.popover?.querySelector('.taxonomy-menu-item')?.focus({
        preventScroll: true
      });
    },
    saveName() {
      const item = this.selectedItem;
      if (!item || !this.editing || this.disabled) return;
      if (!this.validateName(this.renameValue.trim(), item.node_type ?? 'tag', tagKey(item))) return;
      this.commit(this.modelValue[this.active].map(candidate => tagKey(candidate) === tagKey(item) ? {
        ...candidate,
        name: this.renameValue.trim()
      } : candidate));
      this.closeActions(true);
    },
    toggleEnabled() {
      const item = this.selectedItem;
      if (!item || !this.editing || this.disabled) return;
      const next = this.modelValue[this.active].map(candidate => tagKey(candidate) === tagKey(item) ? {
        ...candidate,
        enabled: !candidate.enabled
      } : candidate);
      if (!tagGroups({
        [this.active]: next
      }, this.active).some(group => group.tags.some(tag => tag.enabled))) {
        this.error = '请至少保留一个启用分类及标签';
        return;
      }
      this.commit(next);
      this.closeActions(true);
    },
    toggleGroup(id) {
      this.closeActions();
      this.collapsed = this.collapsed.includes(id) ? this.collapsed.filter(value => value !== id) : [...this.collapsed, id];
    },
    outsideActions(event) {
      if (!this.selected || !(event.target instanceof Node)) return;
      if (!this.popover?.contains(event.target) && !this.anchor?.contains(event.target)) this.closeActions();
    },
    escapeActions(event) {
      if (this.selected && event.key === 'Escape') {
        event.preventDefault();
        this.closeActions(true);
      }
    },
    toggleAllGroups() {
      this.collapsed = this.allCollapsed ? [] : this.groups.map(group => group.id);
    }
  },
  created() {
    this.$watch(() => [this.active, this.editing, this.disabled], () => {
      this.closeActions();
      this.groupInput = '';
      this.leafInputs = {};
    });
    this.$watch(() => this.selectedItem, item => {
      if (!item && this.selected) this.closeActions();
    });
    this.$watch(() => this.error, async () => {
      await this.$nextTick();
      this.positionActions();
    });
    bindPageActivity(this, () => {
      document.addEventListener('pointerdown', this.outsideActions);
      document.addEventListener('keydown', this.escapeActions);
      window.addEventListener('resize', this.positionActions);
      window.addEventListener('scroll', this.positionActions, true);
    }, () => {
      this.closeActions();
      document.removeEventListener('pointerdown', this.outsideActions);
      document.removeEventListener('keydown', this.escapeActions);
      window.removeEventListener('resize', this.positionActions);
      window.removeEventListener('scroll', this.positionActions, true);
    });
  }
};
</script>
<template>
<div class="vue2-component-root">
  <div class="taxonomy-panel">
    <div class="taxonomy-tabs-row"><div class="taxonomy-tabs" role="tablist" aria-label="标签维度"><button v-for="dimension in ['T1', 'T2', 'T3', 'T4', 'T5']" :key="dimension" type="button" role="tab" :aria-selected="active === dimension" :class="{ active: active === dimension }" @click="active = dimension">{{ dimension }} {{ tagNames[dimension] }}</button></div><HoverHint text="模型生成一条核心需求，可在选题详情查看。">T6 用户需求</HoverHint></div>
    <div v-if="active === 'T1' || active === 'T2'" class="taxonomy-fixed"><span class="taxonomy-fixed-label">{{ active === 'T1' ? '营销属性' : '经营作用' }}</span><div class="taxonomy-pills"><span v-for="item in (modelValue[active] ?? []).filter(isLeaf)" :key="tagKey(item)" class="taxonomy-pill" :class="{ inactive: !item.enabled }">{{ item.name }}</span></div></div>
    <div v-else class="taxonomy-groups" :data-dimension="active"><div v-if="groups.length" class="taxonomy-global-toggle"><button class="text-btn" type="button" :aria-expanded="!allCollapsed" @click="toggleAllGroups">{{ allCollapsed ? '展开全部' : '收起全部' }} <span aria-hidden="true">{{ allCollapsed ? '⌄' : '⌃' }}</span></button></div>
      <section v-for="group in groups" :key="group.id" class="taxonomy-group" :class="{ inactive: !group.enabled }">
        <div class="taxonomy-group-head"><button v-if="editing && group.id !== 'unassigned'" class="taxonomy-group-title" :title="group.name" type="button" :disabled="disabled" aria-haspopup="dialog" :aria-expanded="selected === group.id" @click="select(modelValue[active].find(item => tagKey(item) === group.id), $event)">{{ group.name }}</button><b v-else :title="group.name">{{ group.name }}</b><small v-if="!group.enabled">已停用</small></div>
        <div v-show="!collapsed.includes(group.id)" class="taxonomy-group-body"><div class="taxonomy-pills"><button v-for="tag in group.tags" :key="tagKey(tag)" class="taxonomy-pill" :class="{ inactive: !tag.enabled, selected: selected === tagKey(tag) }" type="button" :disabled="!editing || disabled" :title="`${group.name} / ${tag.name}${!tag.enabled ? ' · 已停用' : ''}`" :aria-haspopup="editing ? 'dialog' : undefined" :aria-expanded="editing ? selected === tagKey(tag) : undefined" @click.stop="select(tag, $event)">{{ tag.name }}</button><span v-if="!group.tags.length && !editing" class="taxonomy-no-tags">暂无标签</span></div><div v-if="editing && group.enabled" class="taxonomy-inline-add"><input v-model="leafInputs[group.id]" type="text" :aria-label="`在${group.name}新增标签`" placeholder="标签名称" maxlength="80" :disabled="disabled" @keydown.enter.prevent="addLeaf(group.id)" /><button type="button" :disabled="disabled || !leafInputs[group.id]?.trim()" @click="addLeaf(group.id)">＋ 添加</button></div></div>
      </section>
      <div v-if="!groups.length && !editing" class="empty-state">暂无标签分类</div>
      <div v-if="editing" class="taxonomy-add-group"><input v-model="groupInput" type="text" aria-label="新增一级分类名称" placeholder="一级分类名称" maxlength="80" :disabled="disabled" @keydown.enter.prevent="addGroup" /><button class="btn" type="button" :disabled="disabled || !groupInput.trim()" @click="addGroup">＋ 添加分类</button></div>
      <details v-if="inactiveGroups.length" :key="active" class="taxonomy-inactive">
        <summary>已停用标签</summary>
        <section v-for="group in inactiveGroups" :key="group.id" class="taxonomy-group" :class="{ inactive: !group.enabled }">
          <div class="taxonomy-group-head"><button v-if="editing && !group.enabled" class="taxonomy-group-title" :title="group.name" type="button" :disabled="disabled" aria-haspopup="dialog" :aria-expanded="selected === group.id" @click="select(modelValue[active].find(item => tagKey(item) === group.id), $event)">{{ group.name }}</button><b v-else :title="group.name">{{ group.name }}</b><small v-if="!group.enabled">已停用</small></div>
          <div class="taxonomy-group-body"><div class="taxonomy-pills"><button v-for="tag in group.tags" :key="tagKey(tag)" class="taxonomy-pill" :class="{ inactive: !tag.enabled, selected: selected === tagKey(tag) }" type="button" :disabled="!editing || disabled || !group.enabled" :title="`${group.name} / ${tag.name}${!tag.enabled ? ' · 已停用' : ''}`" :aria-haspopup="editing && group.enabled ? 'dialog' : undefined" :aria-expanded="editing && group.enabled ? selected === tagKey(tag) : undefined" @click.stop="select(tag, $event)">{{ tag.name }}</button></div></div>
        </section>
      </details>
    </div>
    <p v-if="error && !selectedItem" class="inline-error taxonomy-error" role="alert">{{ error }}</p>
  </div>
  <BodyPortal>
    <section v-if="editing && selectedItem" ref="popover" class="taxonomy-action-popover" :class="{ 'is-form': action !== 'menu' }" :style="position" role="dialog" :aria-label="`${selectedItem.name}操作`">
      <template v-if="action === 'menu'">
        <template v-if="selectedItem.enabled">
          <button class="taxonomy-menu-item" type="button" :disabled="disabled" @click="editAction('rename')">改名</button>
          <button class="taxonomy-menu-item is-danger" type="button" :disabled="disabled" @click="toggleEnabled">停用</button>
        </template>
        <button v-else class="taxonomy-menu-item" type="button" :disabled="disabled" @click="toggleEnabled">启用</button>
      </template>
      <form v-else @submit.prevent="saveName">
        <label class="taxonomy-action-field"><span>名称</span><input ref="renameInput" v-model="renameValue" aria-label="修改名称" maxlength="80" :disabled="disabled" /></label>
        <div class="taxonomy-action-footer"><button class="btn" type="button" @click="editAction('menu')">返回</button><button class="btn primary" type="submit" :disabled="disabled || !renameValue.trim() || renameValue.trim() === selectedItem.name">确认改名</button></div>
      </form>
      <p v-if="error" class="taxonomy-action-error" role="alert">{{ error }}</p>
    </section>
  </BodyPortal>
</div>
</template>
<style scoped>
.taxonomy-panel{min-width:0}.taxonomy-tabs-row{display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid var(--neutral-200);padding:0 18px}.taxonomy-tabs{display:flex;gap:19px;overflow-x:auto}.taxonomy-tabs button{flex:none;padding:13px 0 11px;border:0;border-bottom:2px solid transparent;background:transparent;color:var(--neutral-500);font-size:13px;font-weight:500;white-space:nowrap}.taxonomy-tabs button.active{color:var(--primary-600);border-bottom-color:var(--primary-600)}.taxonomy-tabs-row ::v-deep .hover-hint{flex:none;font-size:12px;color:var(--neutral-400)}.taxonomy-groups{padding:3px 18px 14px}.taxonomy-group{padding:13px 0;border-bottom:1px solid var(--neutral-100)}.taxonomy-group:last-of-type{border-bottom:0}.taxonomy-group-head{display:flex;align-items:center;gap:6px;margin-bottom:10px;min-height:22px}.taxonomy-group-head>b,.taxonomy-group-title{font-size:13px;font-weight:600;color:var(--neutral-800)}.taxonomy-group-title{padding:0;border:0;background:transparent}.taxonomy-group-title:hover{color:var(--primary-600)}.taxonomy-fold{display:grid;place-items:center;padding:0;width:18px;height:22px;border:0;background:transparent}.taxonomy-fold svg{width:13px;height:13px;fill:none;stroke:var(--neutral-400);stroke-width:1.6;transition:transform .15s}.taxonomy-fold .folded{transform:rotate(-90deg)}.taxonomy-group-head small{color:var(--neutral-400);font-size:11px}.taxonomy-group-body{padding-left:24px}.taxonomy-pills{display:flex;flex-wrap:wrap;gap:7px}.taxonomy-pill{padding:4px 9px;border:1px solid transparent;border-radius:5px;background:var(--primary-50);color:var(--primary-600);font-size:12px;line-height:17px;max-width:100%;overflow-wrap:anywhere}.taxonomy-pill:disabled{opacity:1;cursor:default}.taxonomy-pill:not(:disabled):hover,.taxonomy-pill.selected{border-color:var(--primary-300);background:var(--primary-100)}[data-dimension="T4"] .taxonomy-pill{background:var(--primary-50);color:var(--brand)}[data-dimension="T5"] .taxonomy-pill{background:var(--primary-100);color:var(--brand-auxiliary)}.taxonomy-pill.inactive,.taxonomy-group.inactive .taxonomy-pill{background:var(--neutral-100);color:var(--text-disabled);text-decoration:line-through}.taxonomy-inline-add{display:flex;align-items:center;gap:7px;margin-top:9px;max-width:260px}.taxonomy-inline-add input,.taxonomy-add-group input,.taxonomy-selected-editor input{box-sizing:border-box;min-width:0;height:30px;padding:0 9px;border:1px solid var(--neutral-200);border-radius:5px;background:var(--surface);font:inherit;font-size:12px;color:var(--neutral-800)}.taxonomy-inline-add input{width:150px}.taxonomy-inline-add button{flex:none;padding:4px 7px;border:0;background:transparent;color:var(--primary-600);font-size:12px}.taxonomy-add-group{display:flex;gap:8px;padding-top:15px;border-top:1px solid var(--neutral-200)}.taxonomy-add-group input{height:32px;width:180px}.taxonomy-add-group .btn{height:32px;font-size:12px}.taxonomy-no-tags{color:var(--neutral-400);font-size:12px}.taxonomy-fixed{display:flex;align-items:center;gap:20px;padding:22px 20px}.taxonomy-fixed-label{color:var(--neutral-500);font-size:13px}.taxonomy-selected-editor{display:flex;align-items:center;gap:12px;margin:0 18px 14px;padding:12px;border:1px solid var(--primary-100);border-radius:7px;background:var(--neutral-50)}.taxonomy-selected-editor>div{display:flex;align-items:center;gap:8px}.taxonomy-selected-editor small{color:var(--neutral-400);font-size:11px}.taxonomy-selected-editor b{font-size:12px;max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.taxonomy-selected-editor input{flex:1;max-width:210px}.taxonomy-selected-editor .text-btn{font-size:12px;white-space:nowrap}.taxonomy-state-action{color:var(--neutral-600)}.taxonomy-state-action.danger{color:var(--danger)}.taxonomy-close{margin-left:auto;border:0;background:transparent;color:var(--neutral-400);font-size:20px}.taxonomy-error{padding:0 18px 12px}@media(max-width:720px){.taxonomy-tabs-row{flex-wrap:wrap;gap:0}.taxonomy-selected-editor{flex-wrap:wrap}.taxonomy-tabs{gap:14px}}
.taxonomy-global-toggle{display:flex;justify-content:flex-end;padding-top:8px}.taxonomy-group-body{padding-left:0}
</style>
<style scoped>
.taxonomy-inactive{margin-top:14px;border-top:1px solid var(--neutral-200);padding-top:12px}.taxonomy-inactive summary{cursor:pointer;color:var(--neutral-500);font-size:13px;font-weight:500}.taxonomy-inactive .taxonomy-group:last-child{border-bottom:0}
.taxonomy-pill{min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.taxonomy-group-head .taxonomy-group-title,.taxonomy-group-head>b{min-width:0;max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.taxonomy-action-popover{position:fixed;z-index:70;box-sizing:border-box;width:164px;max-width:calc(100vw - 16px);padding:5px;border:1px solid var(--neutral-200);border-radius:8px;background:var(--surface);box-shadow:var(--shadow-3)}
.taxonomy-action-popover.is-form{width:280px;padding:12px}
.taxonomy-action-head{display:flex;align-items:center;gap:8px;min-height:28px;padding:0 7px 4px;border-bottom:1px solid var(--neutral-100);margin-bottom:4px}
.taxonomy-action-head b{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;font-weight:500;color:var(--neutral-500)}
.taxonomy-action-head .taxonomy-close{flex:none;width:24px;height:24px;padding:0;line-height:24px}
.taxonomy-menu-item{display:flex;align-items:center;width:100%;height:32px;padding:0 9px;border:0;border-radius:5px;background:transparent;color:var(--neutral-600);font:inherit;font-size:12px;text-align:left;cursor:pointer}
.taxonomy-menu-item:hover,.taxonomy-menu-item:focus-visible{background:var(--primary-50);color:var(--primary-600)}
.taxonomy-menu-item.is-danger{color:var(--danger)}
.taxonomy-menu-item.is-danger:hover,.taxonomy-menu-item.is-danger:focus-visible{background:var(--danger-bg);color:var(--danger-hover)}
.taxonomy-action-field{display:flex;flex-direction:column;gap:8px;margin-top:12px;font-size:12px;color:var(--neutral-500)}
.taxonomy-action-field input{box-sizing:border-box;width:100%;min-width:0;height:32px;padding:0 9px;border:1px solid var(--neutral-200);border-radius:6px;color:var(--neutral-900);background:var(--surface);font:inherit;font-size:12px}
.taxonomy-action-footer{display:flex;justify-content:flex-end;gap:8px;margin-top:12px}
.taxonomy-action-footer .btn{min-height:32px;height:32px;padding:0 10px;font-size:12px}
.taxonomy-action-error{margin:8px 4px 3px;font-size:12px;line-height:18px;color:var(--danger)}
</style>
