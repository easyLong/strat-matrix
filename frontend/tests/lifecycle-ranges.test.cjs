const assert = require('node:assert/strict')
const { it:test } = require('mocha')
const path = require('node:path')
const { load, Vue } = require('./helpers/vue2-loader.cjs')
const ranges = load(path.resolve(__dirname,'../src/ui/lifecycleRanges.js'))
const { lifecycleGroups } = load(path.resolve(__dirname,'../src/ui/lifecycleRules.js'))
const condition = (operator,value,join='AND',field='followers_count') => ({field,operator,value,join})
const rule = conditions => ({name:'测试阶段',catchAll:false,condition_mode:'grouped',conditions})

test('grouped summaries pair range bounds, preserve inclusion and display independent AND/OR groups', async () => {
  const Component=load(path.resolve(__dirname,'../src/components/config/LifecycleRuleSummary.vue')).default
  const stage=rule([condition('gte',100),condition('lt',500),condition('gte',5,'AND','valid_content_count'),condition('gte',15,'OR','rolling_interaction_count')])
  const before=JSON.stringify(stage)
  const html=await require('vue-server-renderer').createRenderer().renderToString(new Vue({render:h=>h(Component,{props:{rule:stage,rules:[stage]}})}))
  assert.equal((html.match(/class="summary-condition-group"/g)||[]).length,2)
  assert.match(html,/100（含）～500（不含） 人/)
  assert.match(html,/summary-and[^>]*>且/)
  assert.match(html,/summary-or[^>]*>或/)
  assert.equal(JSON.stringify(stage),before)
})

test('legacy summaries distribute the shared AND condition across OR groups without editing the source', () => {
  const Component=load(path.resolve(__dirname,'../src/components/config/LifecycleRuleSummary.vue')).default
  const stage={...rule([condition('gte',50),condition('gte',10,'OR','rolling_interaction_count'),condition('gte',5,'AND','valid_content_count')]),condition_mode:undefined}
  const before=JSON.stringify(stage)
  const state=new Vue({ ...Component, propsData:{rule:stage,rules:[stage]} })
  assert.deepEqual(state.groups.map(group=>group.map(item=>item.label)),[['粉丝数','有效内容数'],['滚动篇均互动数','有效内容数']])
  assert.equal(JSON.stringify(stage),before)
  state.$destroy()
})

test('an unfinished summary never exposes NaN and the fallback stage keeps its existing rule', () => {
  const Component=load(path.resolve(__dirname,'../src/components/config/LifecycleRuleSummary.vue')).default
  const stage=rule([condition('gte',NaN)])
  const unfinished=new Vue({ ...Component, propsData:{rule:stage,rules:[stage]} })
  assert.equal(unfinished.groups[0][0].range,'≥ 待填写 人')
  unfinished.$destroy()
  const fallback={name:'冷启动期',catchAll:true,conditions:[]}
  const growth={...rule([condition('gte',50),condition('gte',5,'OR','valid_content_count')]),name:'流量增长期'}
  const state=new Vue({ ...Component, propsData:{rule:fallback,rules:[growth,fallback]} })
  assert.deepEqual(state.groups,[])
  assert.equal(state.fallback,'粉丝数 < 50 人 或 有效内容数 < 5 篇；未命中其他阶段时也归入此阶段')
  state.$destroy()
})

test('the actual stage editor renders existing thresholds and range labels without changing their values', async () => {
  const Component=load(path.resolve(__dirname,'../src/components/config/LifecycleRulesEditor.vue')).default
  const stage=rule([condition('gte',500),condition('lt',800)])
  const before=JSON.stringify(stage)
  const html=await require('vue-server-renderer').createRenderer().renderToString(new Vue({render:h=>h(Component,{props:{value:[stage]}})}))
  assert.match(html,/value="500"/)
  assert.match(html,/value="800"/)
  assert.match(html,/起始值（含）/)
  assert.match(html,/截止值（不含）/)
  assert.equal(JSON.stringify(stage),before)
})

test('range presentation pairs only the same metric in one group and leaves source comparisons untouched', () => {
  const stage=rule([condition('gt',50),condition('lte',100),condition('eq',5,'AND','valid_content_count'),condition('lt',10,'OR')])
  const before=JSON.stringify(stage)
  const groups=lifecycleGroups(stage)
  assert.deepEqual(ranges.lifecycleRangeRows(groups[0]),[{field:'followers_count',lower:0,upper:1},{field:'valid_content_count',exact:2}])
  assert.deepEqual(ranges.lifecycleRangeRows(groups[1]),[{field:'followers_count',upper:0}])
  assert.equal(JSON.stringify(stage),before)
})

test('range editing retains strict bounds, other metrics and OR group boundaries using existing payload fields', () => {
  const stage=rule([condition('gt',50),condition('gte',5,'OR','valid_content_count')])
  ranges.updateLifecycleBound(stage,0,ranges.lifecycleRangeRows(lifecycleGroups(stage)[0])[0],'upper','100')
  assert.deepEqual(stage.conditions,[condition('gt',50),condition('lte',100),condition('gte',5,'OR','valid_content_count')])
  let row=ranges.lifecycleRangeRows(lifecycleGroups(stage)[0])[0]
  ranges.updateLifecycleBound(stage,0,row,'lower','60')
  assert.equal(stage.conditions[0].operator,'gt')
  row=ranges.lifecycleRangeRows(lifecycleGroups(stage)[0])[0]
  ranges.updateLifecycleBound(stage,0,row,'upper','')
  assert.deepEqual(stage.conditions,[condition('gt',60),condition('gte',5,'OR','valid_content_count')])
})

test('empty or contradictory ranges block saving and deleting a range never removes the last condition', () => {
  const stage=rule([condition('gt',50),condition('lt',51)])
  assert.equal(ranges.lifecycleRangesValid([stage]),false)
  stage.conditions[1].value=52
  assert.equal(ranges.lifecycleRangesValid([stage]),true)
  const row=ranges.lifecycleRangeRows(stage.conditions)[0]
  ranges.removeLifecycleRange(stage,0,row)
  assert.equal(stage.conditions.length,2)
  ranges.updateLifecycleBound(stage,0,row,'upper','')
  ranges.updateLifecycleBound(stage,0,ranges.lifecycleRangeRows(stage.conditions)[0],'lower','')
  assert.equal(ranges.lifecycleRangesValid([stage]),false)
  ranges.updateLifecycleBound(stage,0,ranges.lifecycleRangeRows(stage.conditions)[0],'lower','0')
  assert.equal(ranges.lifecycleRangesValid([stage]),true)
})

test('removing a two-sided range preserves remaining groups and field changes update both bounds', () => {
  const stage=rule([condition('gte',50),condition('lte',100),condition('gte',5,'OR','valid_content_count')])
  let row=ranges.lifecycleRangeRows(lifecycleGroups(stage)[0])[0]
  ranges.updateLifecycleRangeField(stage,0,row,'rolling_interaction_count')
  assert.ok(stage.conditions.slice(0,2).every(item=>item.field==='rolling_interaction_count'))
  row=ranges.lifecycleRangeRows(lifecycleGroups(stage)[0])[0]
  ranges.removeLifecycleRange(stage,0,row)
  assert.deepEqual(stage.conditions,[condition('gte',5,'AND','valid_content_count')])
})
