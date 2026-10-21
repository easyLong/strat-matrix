export function reviewRuntime(snapshot) {
  'use strict';
  const originalFetch = window.fetch.bind(window);
  const clone = value => value == null ? value : JSON.parse(JSON.stringify(value));
  const response = (value, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
  const error = (message, status = 400) => response({ detail: message }, status);
  const now = () => new Date().toLocaleString('sv-SE', { timeZone: 'Asia/Shanghai' }).replace(' ', 'T');
  const previews = new Map(), requests = [];
  let nextBatchId = Math.max(0, ...snapshot.batches.map(b => b.id)) + 1;
  const weekStart = value => { const d = new Date(value + 'T12:00:00Z'); d.setUTCDate(d.getUTCDate() - (d.getUTCDay() + 6) % 7); return d.toISOString().slice(0, 10); };
  const allItems = () => Object.values(snapshot.batchDetails).flatMap(batch => batch.items);
  function refreshIndexes() {
    const records = [];
    snapshot.cycleItems = {};
    for (const b of Object.values(snapshot.batchDetails)) for (const item of b.items) {
      const record = { ...item, batch_id: b.id, batch_code: b.batch_code, batch_created_at: b.created_at, plan_type: b.plan_type, cycle_start: b.cycle_start, cycle_end: b.cycle_end };
      records.push(record);
      (snapshot.cycleItems[weekStart(b.cycle_start)] ||= []).push(record);
    }
    // Keep native account-history rows, including history not present in the batch snapshot.
    const byId = new Map(records.map(record => [record.id, record]));
    for (const [accountId, history] of Object.entries(snapshot.accountItems)) {
      const existingIds = new Set(history.map(record => record.id));
      snapshot.accountItems[accountId] = history.map(record => ({ ...record, ...byId.get(record.id) }));
      snapshot.accountItems[accountId].push(...records.filter(record => record.account_id === accountId && !existingIds.has(record.id)));
    }
    for (const record of records) {
      if (!snapshot.accountItems[record.account_id]) snapshot.accountItems[record.account_id] = records.filter(row => row.account_id === record.account_id);
    }
    // Same ordering as /api/items: cycle DESC, batch creation DESC, publish date, item id.
    for (const history of Object.values(snapshot.accountItems)) history.sort((a, b) =>
      b.cycle_start.localeCompare(a.cycle_start) || (b.batch_created_at || '').localeCompare(a.batch_created_at || '') ||
      a.publish_date.localeCompare(b.publish_date) || a.id - b.id);
  }
  function updateCycle(cycleId) {
    const batches = snapshot.batches.filter(b => weekStart(b.cycle_start) === cycleId);
    const rows = batches.flatMap(b => snapshot.batchDetails[b.id]?.items || []);
    const auto = batches.filter(b => b.plan_type === 'auto').flatMap(b => snapshot.batchDetails[b.id]?.items || []);
    const pendingHotspots = auto.filter(i => i.slot_type === 'hotspot' && (!i.topic_id || (i.account_id.startsWith('DEMO-') && [null, 'planned'].includes(i.production_status))));
    const pendingAccounts = new Set(pendingHotspots.map(i => i.account_id));
    const accountIds = new Set(rows.map(i => i.account_id));
    const end = new Date(cycleId + 'T12:00:00Z'); end.setUTCDate(end.getUTCDate() + 6);
    const complete = rows.filter(i => ['generated', 'published'].includes(i.production_status)).length;
    const failed = rows.some(i => i.production_status === 'failed');
    const summary = { cycle_id: cycleId, cycle_start: cycleId, cycle_end: end.toISOString().slice(0, 10),
      batch_count: batches.length, account_count: accountIds.size, auto_item_count: auto.length,
      manual_item_count: rows.length - auto.length, content_count: rows.length,
      regular_slots: auto.filter(i => i.slot_type === 'regular').length,
      marketing_slots: auto.filter(i => i.slot_type === 'marketing_priority').length,
      hotspot_slots: auto.filter(i => i.slot_type === 'hotspot').length,
      topic_uses: rows.filter(i => i.topic_id).length,
      unique_topics: new Set(rows.filter(i => i.topic_id).map(i => (i.topic_type || '普通') + ':' + i.topic_id)).size,
      success_accounts: [...accountIds].filter(id => !pendingAccounts.has(id)).length, failed_accounts: 0,
      planning_status: cycleId > now().slice(0, 10) ? '已规划' : pendingHotspots.length ? '热点空槽待填充' : '已完成',
      content_status: failed ? '生产异常' : complete === rows.length && rows.length ? '已完成' : complete || rows.some(i => i.production_status === 'ready') ? '生产中' : '待生产',
      updated_at: batches.map(b => b.updated_at || b.created_at).sort().at(-1) };
    const index = snapshot.planningCycles.findIndex(c => c.cycle_id === cycleId);
    if (index === -1) snapshot.planningCycles.push(summary); else snapshot.planningCycles[index] = summary;
    snapshot.planningCycles.sort((a, b) => b.cycle_id.localeCompare(a.cycle_id));
  }
  function plannedIds(date) {
    const ids = snapshot.accountAvailability?.[date]?.planned_account_ids || [];
    const committed = Object.values(snapshot.batchDetails).filter(b => b.plan_type === 'manual').flatMap(b => b.items.filter(i => i.publish_date === date).map(i => i.account_id));
    return [...new Set([...ids, ...committed])].sort();
  }
  function saveConfig(config) {
    const previous = snapshot.config;
    snapshot.config = { config: clone(config), version: previous.version + 1, updated_at: now(), is_demo: false };
    snapshot.configVersions.unshift({ version: snapshot.config.version, action: '更新', source_version: previous.version, created_at: now(), created_by: '运营人员', config: clone(config) });
    return snapshot.config;
  }
  function createTask(preview) {
    const id = nextBatchId++;
    const taskId = Math.max(0, ...snapshot.tasks.map(t => t.id)) + 1, timestamp = now();
    const code = `MAN-${preview.publish_date.replace(/-/g, '')}-${String(id).padStart(3, '0')}`;
    let itemId = Math.max(0, ...allItems().map(i => i.id));
    const items = preview.items.map(row => {
      const t = snapshot.topics.find(t => t.topic_id === row.topic_id), a = snapshot.accounts.find(a => a.account_id === row.account_id);
      return { ...row, id: ++itemId, publish_date: preview.publish_date, slot_type: 'manual_extra',
        topic_type: t.topic_type, status: '待生成', slot_id: `REVIEW-SLOT-${itemId}`, production_status: 'planned', publish_status: '未发布',
        allow_replace: true, replace_block_reason: '', result_version: 1, content_type: t.content_type, outline: t.outline,
        lifecycle_stage: a.lifecycle_stage, content_role: t.is_marketing ? '转化' : '流量' };
    });
    const task = { id: taskId, task_code: `REVIEW-TASK-${taskId}`, preview_code: preview.preview_id,
      task_name: preview.task_name, batch_code: '', publish_date: preview.publish_date,
      planned_account_count: new Set(items.map(i => i.account_id)).size, result_count: 0, failure_count: 0,
      topic_count: new Set(items.map(i => i.topic_id)).size, status: '进行中', planning_status: '生成中', content_status: '待生产',
      content_failed_count: 0, content_completed_count: 0, content_total_count: 0, content_completed_account_count: 0,
      failure_reason: '', batch_id: null, last_error: '', created_at: timestamp, created_by: '运营人员', updated_at: timestamp };
    const b = { id, batch_code: code, plan_type: 'manual', status: '生成中', cycle_start: preview.publish_date, cycle_end: preview.publish_date,
      account_count: task.planned_account_count, content_count: items.length, result_count: items.length, completed_count: 0, failed_count: 0,
      topic_count: task.topic_count, note: '', created_at: timestamp, updated_at: timestamp, task_name: task.task_name,
      planning_status: '生成中', content_status: '待生产', content_failed_count: 0, content_completed_count: 0,
      content_total_count: items.length, content_completed_account_count: 0 };
    snapshot.tasks.unshift(task);
    setTimeout(() => {
      Object.assign(task, { status: '已完成', planning_status: '已完成', result_count: items.length, batch_id: id, batch_code: code, content_total_count: items.length, updated_at: now() });
      Object.assign(b, { status: '已完成', planning_status: '已完成', completed_count: task.planned_account_count, updated_at: now() });
      snapshot.batches.unshift(b); snapshot.batchDetails[id] = { ...b, items }; refreshIndexes();
      for (const accountId of new Set(items.map(i => i.account_id))) {
        const a = snapshot.accounts.find(a => a.account_id === accountId);
        let existing = snapshot.planningAccounts.find(a => a.account_id === accountId);
        if (!existing) { existing = { account_id: a.account_id, account_name: a.account_name, account_owner: a.organization, cycle_count: 0, slot_count: 0 }; snapshot.planningAccounts.push(existing); }
        const history = snapshot.accountItems[accountId] || [];
        Object.assign(existing, { slot_count: history.length, cycle_count: new Set(history.map(i => i.cycle_start)).size,
          latest_batch_id: id, latest_cycle_start: preview.publish_date, latest_cycle_updated_at: now(), latest_status: '待生成' });
      }
      refreshIndexes();
      snapshot.planningAccounts.sort((a, b) => (b.latest_cycle_updated_at || '').localeCompare(a.latest_cycle_updated_at || '') || a.account_name.localeCompare(b.account_name, 'zh-CN') || a.account_id.localeCompare(b.account_id));
      updateCycle(weekStart(preview.publish_date));
    }, 1600);
    return task;
  }
  window.fetch = async (input, options = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    const at = url.pathname.indexOf('/api/');
    if (at === -1) return originalFetch(input, options);
    const path = url.pathname.slice(at + 4), query = url.searchParams, method = (options.method || input.method || 'GET').toUpperCase();
    let body = {}; try { body = JSON.parse(options.body || '{}'); } catch { return error('请求内容无效'); }
    requests.push({ path, method });
    if (path === '/health') return response({ service: 'ok', database: 'ok' });
    if (path === '/config' && method === 'GET') return response(clone(snapshot.config));
    if ((path === '/config' || /^\/config\/modules\/(marketing|strategy)$/.test(path)) && method === 'PUT') {
      if (query.has('expected_version') && Number(query.get('expected_version')) !== snapshot.config.version) return error('配置版本已更新，请重新进入编辑', 409);
      return response(clone(saveConfig(body)));
    }
    if ((path === '/config/versions' || /^\/config\/modules\/\w+\/versions$/.test(path)) && method === 'GET') return response(clone(snapshot.configVersions));
    const restore = path.match(/^\/config\/(?:modules\/\w+\/)?versions\/(\d+)\/restore$/);
    if (restore && method === 'POST') {
      if (query.has('expected_version') && Number(query.get('expected_version')) !== snapshot.config.version) return error('配置版本已更新，请重新进入编辑', 409);
      const v = snapshot.configVersions.find(v => v.version === Number(restore[1])); return v ? response(clone(saveConfig(v.config))) : error('配置版本不存在', 404);
    }
    if (path === '/tag-taxonomy' && method === 'GET') return response(clone(snapshot.tags));
    if (path === '/tag-taxonomy' && method === 'PUT') {
      if (body.expected_version !== snapshot.tags.version) return error('标签配置版本已更新，请重新进入编辑', 409);
      const items = clone(body.items), ids = new Map();
      for (const values of Object.values(items)) for (const item of values) {
        const previous = item.id || item.client_id;
        item.id ||= item.client_id || `REVIEW-TAG-${Date.now()}-${ids.size}`;
        if (previous) ids.set(previous, item.id);
      }
      for (const values of Object.values(items)) for (const item of values) if (item.parent_id) item.parent_id = ids.get(item.parent_id) || item.parent_id;
      snapshot.tags.items = items; snapshot.tags.version++;
      snapshot.tags.tags = Object.fromEntries(Object.entries(items).map(([k, values]) => [k, values.filter(t => t.enabled && t.node_type !== 'group').map(t => t.name)]));
      return response(clone(snapshot.tags));
    }
    if (path === '/accounts') return response(clone((query.get('include_disabled') === 'true' ? snapshot.accounts : snapshot.activeAccounts).slice(0, Number(query.get('limit') || 1000))));
    if (path === '/topics') return response(clone(snapshot.topics));
    if (path === '/planning-accounts') return response(clone(snapshot.planningAccounts));
    if (path === '/planning-cycles') return response(clone(snapshot.planningCycles));
    if (path === '/batches') return response(clone(snapshot.batches.filter(b => !query.get('plan_type') || b.plan_type === query.get('plan_type')).slice(0, Number(query.get('limit') || 200))));
    const batch = path.match(/^\/batches\/(\d+)$/);
    if (batch) return snapshot.batchDetails[batch[1]] ? response(clone(snapshot.batchDetails[batch[1]])) : error('未找到该批次', 404);
    const cycle = path.match(/^\/planning-cycles\/(.+)\/items$/);
    if (cycle) return response(clone((snapshot.cycleItems[decodeURIComponent(cycle[1])] || []).slice(0, Number(query.get('limit') || 1000))));
    if (path === '/items') return response(clone(query.get('account') ? snapshot.accountItems[query.get('account')] || [] : Object.values(snapshot.accountItems).flat()));
    const detail = path.match(/^\/topics\/(.+)\/detail$/);
    if (detail) { const t = snapshot.topicDetails[decodeURIComponent(detail[1])]; return t ? response(clone(t)) : error('选题不存在', 404); }
    const replacement = path.match(/^\/items\/(\d+)\/replacement-candidates$/);
    if (replacement) {
      const item = allItems().find(i => i.id === Number(replacement[1]));
      if (!item) return error('未找到该策划', 404);
      if (!item.allow_replace) return error(item.replace_block_reason || '该选题不可替换', 409);
      if (snapshot.replacementCandidates?.[item.id]) return response(clone(snapshot.replacementCandidates[item.id].filter(t => t.topic_id !== item.topic_id)));
      const a = snapshot.accounts.find(a => a.account_id === item.account_id);
      return response(clone(snapshot.topics.filter(t => t.topic_id !== item.topic_id && (!t.is_marketing || a?.marketing_eligible) && (!t.valid_from || t.valid_from.slice(0, 10) <= item.publish_date) && (!t.valid_to || t.valid_to.slice(0, 10) >= item.publish_date))));
    }
    const adjustments = path.match(/^\/items\/(\d+)\/adjustments$/);
    if (adjustments) return response(clone(snapshot.adjustments[adjustments[1]] || []));
    const replace = path.match(/^\/items\/(\d+)\/replace-topic$/);
    if (replace && method === 'POST') {
      const item = allItems().find(i => i.id === Number(replace[1])), topic = snapshot.topics.find(t => t.topic_id === body.new_topic_id);
      if (!item || !topic) return error('未找到策划或选题', 404);
      if (!item.allow_replace || ['ready', '生产中', '生成中'].includes(item.production_status)) return error('内容生产中，选题不可替换', 409);
      if (item.result_version !== body.expected_version) return error('策划结果版本已变化', 409);
      const candidates = snapshot.replacementCandidates?.[item.id];
      if (candidates && !candidates.some(t => t.topic_id === topic.topic_id)) return error('新选题不在该账号的可替换范围内', 422);
      if (candidates) {
        const old = snapshot.topics.find(t => t.topic_id === item.topic_id);
        if (old && !candidates.some(t => t.topic_id === old.topic_id)) candidates.push(clone(old));
        const rank = t => ({ 普通: 0, 营销: 1, 热点: 2 })[t.topic_type] || 0;
        candidates.sort((a, b) => rank(a) - rank(b) || (a.topic_title < b.topic_title ? -1 : a.topic_title > b.topic_title ? 1 : 0));
      }
      const adjustment = { id: Date.now(), item_id: item.id, result_version: item.result_version + 1, adjustment_source: '人工调整', old_topic_id: item.topic_id, old_topic_title: item.topic_title, new_topic_id: topic.topic_id, new_topic_title: topic.topic_title, reason: body.reason || '', created_at: now(), created_by: '运营人员' };
      (snapshot.adjustments[item.id] ||= []).unshift(adjustment);
      Object.assign(item, { topic_id: topic.topic_id, topic_title: topic.topic_title, topic_type: topic.topic_type, content_type: topic.content_type, outline: topic.outline, result_version: item.result_version + 1, production_status: 'planned' });
      refreshIndexes();
      return response({ item: clone(Object.values(snapshot.accountItems).flat().find(i => i.id === item.id)), adjustment });
    }
    if (path === '/manual-plans/tasks') return response(clone(snapshot.tasks));
    if (path === '/manual-plans/account-availability') return response({ publish_date: query.get('publish_date'), planned_account_ids: plannedIds(query.get('publish_date')) });
    if (path === '/manual-plans/previews' && method === 'POST') {
      if (!body.task_name?.trim() || !body.publish_date || !body.account_ids?.length || !body.topic_ids?.length) return error('请完整选择账号与选题');
      if (body.account_ids.some(id => plannedIds(body.publish_date).includes(id))) return error('部分账号当日已完成人工策划，请返回调整');
      const accounts = body.account_ids.map(id => snapshot.accounts.find(a => a.account_id === id)), topics = body.topic_ids.map(id => snapshot.topics.find(t => t.topic_id === id));
      if (accounts.some(a => !a) || topics.some(t => !t)) return error('所选账号或选题已不存在');
      const invalid = accounts.find(a => !topics.some(t => !t.is_marketing || a.marketing_eligible));
      if (invalid) return error(`账号 ${invalid.account_name} 不具备所选营销选题资格`);
      if (topics.some(t => (t.valid_from && t.valid_from.slice(0, 10) > body.publish_date) || (t.valid_to && t.valid_to.slice(0, 10) < body.publish_date))) return error('所选选题不在投放日期有效期内');
      const target = body.target_count || accounts.length;
      if (target > accounts.length) return error('符合条件的账号不足，无法完成本次抽取', 422);
      const preview = { preview_id: `REVIEW-PREV-${Date.now()}`, task_name: body.task_name, publish_date: body.publish_date, expires_at: new Date(Date.now() + 1800000).toISOString(), note: '', items: accounts.slice(0, target).map((a, index) => {
        const compatible = topics.filter(t => !t.is_marketing || a.marketing_eligible), t = compatible[index % compatible.length];
        return { account_id: a.account_id, account_name: a.account_name, topic_id: t.topic_id, topic_title: t.topic_title };
      }) };
      previews.set(preview.preview_id, preview); return response(clone(preview));
    }
    const submit = path.match(/^\/manual-plans\/previews\/(.+)\/submit$/);
    if (submit && method === 'POST') {
      const preview = previews.get(decodeURIComponent(submit[1]));
      if (!preview) return error('预选记录不存在', 404);
      if (preview.items.some(i => plannedIds(preview.publish_date).includes(i.account_id) || snapshot.tasks.some(t => t.publish_date === preview.publish_date && ['执行中', '进行中'].includes(t.status) && previews.get(t.preview_code)?.items.some(p => p.account_id === i.account_id)))) return error('所选账号当日已有人工策划任务，请重新选择', 409);
      return response(clone(createTask(preview)));
    }
    return error(`离线评审尚未实现此操作：${method} ${path}`, 501);
  };
  window.__STRAT_MATRIX_REVIEW__ = { snapshot, requests, originalFetch };
}
