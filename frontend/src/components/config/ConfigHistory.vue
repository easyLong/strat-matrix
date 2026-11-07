<script lang="ts">
import DialogTitle from '../../components/DialogTitle.vue';
import { defineComponent, type PropType } from '../../compat/composition';
import { computed, toRef } from '../../compat/composition';
import { canPlanning } from '../../host/runtime';
import { formatDateTime } from '../../planningTime';
import { lifecycleRuleSummary } from '../../ui/lifecycleRules';
import { canRestoreConfig, configDetailRows, configHistorySummary, configVersionNumber } from '../../ui/configHistory';
import type { ConfigVersionSummary } from '../../types';
export default defineComponent({
    props: { versions: { required: true, type: Array as PropType<ConfigVersionSummary[]> },
        disabled: { required: true, type: Boolean as PropType<boolean> },
        detail: { required: true, type: null as unknown as PropType<ConfigVersionSummary | null> } },
    setup(props, context) {
        const versions = toRef(props, 'versions');
        const versionDetail = computed({
            get: () => props.detail,
            set: value => emit('update:detail', value)
        });
        const emit = context.emit;
        const displayVersionNumber = (version: ConfigVersionSummary) => configVersionNumber(version, versions.value);
        function showVersionDetail(version: ConfigVersionSummary) {
            versionDetail.value = version;
        }
        const versionDetailRows = computed(() => versionDetail.value ? configDetailRows(versionDetail.value.config) : []);
        const versionPrevious = computed(() => {
            if (!versionDetail.value)
                return null;
            const index = versions.value.findIndex(item => item.version === versionDetail.value?.version);
            return index >= 0 ? versions.value[index + 1] ?? null : null;
        });
        const versionChanges = computed(() => {
            if (!versionDetail.value || !versionPrevious.value)
                return [];
            const current = configDetailRows(versionDetail.value.config);
            const previous = new Map(configDetailRows(versionPrevious.value.config).map(row => [row.key, row.value]));
            return current.flatMap(row => {
                const oldValue = previous.get(row.key);
                return oldValue === row.value ? [] : [{
                        ...row,
                        oldValue: oldValue ?? '无',
                        newValue: row.value
                    }];
            });
        });
        return {
            canPlanning,
            formatDateTime,
            lifecycleRuleSummary,
            canRestoreConfig,
            configHistorySummary,
            versionDetail,
            emit,
            displayVersionNumber,
            showVersionDetail,
            versionDetailRows,
            versionPrevious,
            versionChanges
        };
    },
    components: {DialogTitle}
});
</script>
<template>
<div class="vue2-component-root">
  <section class="card">
    <div class="table-wrap"><table><thead><tr><th>版本</th><th>生成时间</th><th>配置摘要</th><th>操作人</th><th>操作</th></tr></thead><tbody>
      <tr v-for="version in versions" :key="version.version"><td><b>V{{ displayVersionNumber(version) }}</b><span v-if="version.version === versions[0]?.version" class="tag green row-tag">当前</span></td><td>{{ formatDateTime(version.created_at) }}</td><td>{{ configHistorySummary(version.config) }}</td><td>{{ version.created_by }}</td><td><div class="page-actions"><button class="text-btn" type="button" @click="showVersionDetail(version)">查看详情</button><button v-if="version.version !== versions[0]?.version && canPlanning('config.restore')" class="text-btn" type="button" :disabled="disabled || !canRestoreConfig(version.config)" :title="canRestoreConfig(version.config) ? undefined : '该版本未记录完整配置，仅支持查看'" @click="emit('restore',version)">恢复此版本</button></div></td></tr>
      <tr v-if="versions.length === 0"><td colspan="5"><div class="empty-state">暂无配置记录</div></td></tr>
    </tbody></table></div>
  </section>

  <div v-if="versionDetail" class="drawer-mask show" @click.self="versionDetail = null">
    <aside class="drawer" role="dialog" aria-modal="true" :aria-label="`总配置版本 V${versionDetail.version} 详情`">
      <div class="drawer-head"><DialogTitle :title="`V${displayVersionNumber(versionDetail)} 配置详情`" :context="formatDateTime(versionDetail.created_at)" /><button class="icon-btn" type="button" aria-label="关闭" @click="versionDetail = null">×</button></div>
      <div class="drawer-body">

        <h3>修改摘要</h3>
        <p v-if="versionPrevious" class="muted">与总配置 V{{ displayVersionNumber(versionPrevious) }} 对比</p>
        <div v-if="versionPrevious && versionChanges.length" class="table-wrap"><table><thead><tr><th>配置项</th><th>原值</th><th>新值</th></tr></thead><tbody><tr v-for="change in versionChanges" :key="change.key"><td>{{ change.label }}</td><td>{{ change.oldValue }}</td><td>{{ change.newValue }}</td></tr></tbody></table></div>
        <div v-else class="detail-note">{{ versionPrevious ? '该版本与上一版本配置内容相同。' : '没有更早的模块版本可供比较。' }}</div>
        <h3>完整配置</h3>
        <div class="config-version-group">
          <b>策划内容配置</b>
          <div class="table-wrap"><table><tbody><tr v-for="row in versionDetailRows.filter(item => item.group === '策划内容配置')" :key="row.key"><th>{{ row.label }}</th><td>{{ row.value }}</td></tr></tbody></table></div>
        </div>
        <div class="config-version-group">
          <b>策划规则配置</b>
          <div class="table-wrap"><table><thead><tr><th>生命周期阶段判定</th><th>进入条件</th></tr></thead><tbody>
            <tr v-for="rule in versionDetail.config.lifecycle_rules ?? []" :key="rule.name"><td><b>{{ rule.name }}</b></td><td>{{ lifecycleRuleSummary(rule, versionDetail.config.lifecycle_rules ?? []) }}</td></tr>
            <tr v-if="!versionDetail.config.lifecycle_rules?.length"><td colspan="2">未记录</td></tr>
          </tbody></table></div>
          <div class="table-wrap"><table><thead><tr><th>阶段经营目标</th><th>流量目标</th><th>转化目标</th></tr></thead><tbody>
            <tr v-for="stage in versionDetail.config.stage_targets ?? []" :key="stage.name"><td><b>{{ stage.name }}</b></td><td>{{ stage.traffic }}%</td><td>{{ stage.conversion }}%</td></tr>
            <tr v-if="!versionDetail.config.stage_targets?.length"><td colspan="3">未记录</td></tr>
          </tbody></table></div>
          <div class="detail-note">滚动统计窗口：{{ versionDetail.config.rolling_posts == null ? '未记录' : `${versionDetail.config.rolling_posts} 篇` }}</div>
        </div>
      </div>
      <div class="drawer-foot"><button class="btn" type="button" @click="versionDetail = null">关闭</button></div>
    </aside>
  </div>

</div>
</template>
<style scoped>


</style>
