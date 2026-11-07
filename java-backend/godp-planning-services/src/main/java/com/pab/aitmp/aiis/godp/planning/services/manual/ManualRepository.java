package com.pab.aitmp.aiis.godp.planning.services.manual;

import com.pab.aitmp.aiis.godp.planning.services.persistence.SqlRows;
import com.pab.aitmp.aiis.godp.planning.entity.command.*;

import com.pab.aitmp.aiis.godp.planning.entity.error.BusinessException;
import com.pab.aitmp.aiis.godp.planning.entity.support.Json;

import java.util.*;
import java.util.function.Supplier;
import com.pab.aitmp.aiis.godp.planning.api.port.BusinessTransactions;
import com.pab.aitmp.aiis.godp.planning.services.persistence.IsolatedBusinessTransactions;
import org.springframework.transaction.PlatformTransactionManager;

/** Business persistence facade; SQL is exclusively defined by the MyBatis mapper. */
public class ManualRepository {
  private final ManualMapper mapper;
  private final BusinessTransactions tx;

  public ManualRepository(ManualMapper mapper, PlatformTransactionManager manager) {
    this(mapper,new IsolatedBusinessTransactions(manager));
  }

  public ManualRepository(ManualMapper mapper, BusinessTransactions transactions) {
    this.mapper = Objects.requireNonNull(mapper, "business MyBatis mapper");
    this.tx = Objects.requireNonNull(transactions, "business transaction boundary");
  }

  public <T> T transaction(Supplier<T> action) {
    return tx.required(action);
  }

  public Set<String> plannedAccountIds(String date) {
    return new HashSet<>(mapper.plannedAccountIds(date));
  }

  public Set<String> reserved(String date) {
    return new HashSet<>(mapper.reservedAccountIds(date));
  }

  public void savePreview(
      String code, String payload, long expiresAt, String createdBy, long time) {
    Map<String, Object> values = new HashMap<>();
    values.put("code", code);
    values.put("payload", payload);
    values.put("expiresAt", expiresAt);
    values.put("createdBy", createdBy);
    values.put("createdAt", time);
    SqlRows.insert(values, PreviewInsert.class, mapper::insertPreview);
  }

  public Map<String, Object> taskByPreview(String code) {
    return SqlRows.one(mapper.taskByPreview(code));
  }

  public Map<String, Object> previewByCode(String code) {
    return SqlRows.one(mapper.previewByCode(code));
  }

  public Map<String, Object> lockedPreview(String code) {
    return SqlRows.one(mapper.lockedPreview(code));
  }

  public Map<String, Object> taskById(long id) {
    return SqlRows.one(mapper.taskById(id));
  }

  public Map<String, Object> lockedTask(long id) {
    return SqlRows.one(mapper.lockedTask(id));
  }

  public Map<String, Object> batchById(long id) {
    return SqlRows.one(mapper.batchById(id));
  }

  public Map<String, Object> lockedBatchWrite(long id) { return SqlRows.one(mapper.lockedBatchWrite(id)); }

  public void saveStagingBatch(long id, String payload, long time) {
    mapper.insertStagingBatch(id, payload, time, week(Json.text(Json.read(payload), "cycle_start")));
  }

  public void advanceBatchWrite(long id, int cursor) {
    if (mapper.advanceBatchWrite(id, cursor) != 1) throw new IllegalStateException("批次写入游标更新失败");
  }

  public long stagedItemCount(long id) { return mapper.stagedItemCount(id); }

  public void publishBatch(long id) {
    if (mapper.publishBatch(id) != 1) throw new IllegalStateException("批次发布状态变化");
  }

  public List<Map<String, Object>> completedTopicUsage(List<String> topicIds) {
    if (topicIds == null || topicIds.isEmpty() || topicIds.size() > 500)
      throw new BusinessException(422, "选题ID数量须为1至500");
    return SqlRows.list(mapper.completedTopicUsage(topicIds));
  }

  public Map<String, Object> lockedBatch(long id) {
    return SqlRows.one(mapper.lockedBatch(id));
  }

  public Map<String, Object> lockedItem(long id) {
    return SqlRows.one(mapper.lockedItem(id));
  }

  public long createTask(String previewCode, String taskCode, String payload, long time) {
    Map<String, Object> values = new HashMap<>();
    values.put("previewCode", previewCode);
    values.put("taskCode", taskCode);
    values.put("payload", payload);
    values.put("time", time);
    SqlRows.insert(values, ManualTaskInsert.class, mapper::insertTask);
    return ((Number) values.get("id")).longValue();
  }

  public void reserve(String date, String accountId, long taskId) {
    if (mapper.reviveReservation(date, accountId, taskId) == 0)
      mapper.insertReservation(date, accountId, taskId);
  }

  public int markComputing(long id, long time) {
    return mapper.markComputing(id, time);
  }

  public int noteRetry(long id, String message, long time) {
    return mapper.noteRetry(id, message, time);
  }

  public int markFailed(long id, String reason, long time) {
    return mapper.markFailed(id, reason, time);
  }

  public int release(long id) {
    return mapper.deleteReservations(id);
  }

  public int markCompleted(long id, long time) {
    return mapper.markCompleted(id, time);
  }

  public void saveBatch(long id, String payload, long time) {
    mapper.insertBatch(id, payload, time, week(Json.text(Json.read(payload), "cycle_start")));
  }

  public void updateBatch(long id, String payload) {
    mapper.updateBatchPayload(id, payload, week(Json.text(Json.read(payload), "cycle_start")));
  }

  private static String week(String date) {
    return date == null || date.length() < 10
        ? null
        : java.time.LocalDate.parse(date.substring(0, 10))
            .with(java.time.temporal.TemporalAdjusters.previousOrSame(java.time.DayOfWeek.MONDAY))
            .toString();
  }

  public long saveItem(long batchId, String slotId, String accountId, String date, String payload) {
    return saveItem(batchId, slotId, accountId, date, payload, "planned");
  }

  public long saveItem(
      long batchId,
      String slotId,
      String accountId,
      String date,
      String payload,
      String contentStatus) {
    if (slotId == null || slotId.trim().isEmpty() || slotId.length() > 128)
      throw new IllegalArgumentException("策划槽位编号无效");
    Map<String, Object> values = new HashMap<>();
    values.put("batchId", batchId);
    values.put("slotId", slotId);
    values.put("accountId", accountId);
    values.put("publishDate", date);
    values.put("payload", payload);
    values.put("publishWeek", week(date));
    if (!Arrays.asList("planned", "unassigned", "awaiting_market", "generated")
        .contains(contentStatus)) throw new IllegalArgumentException("新策划内容状态无效");
    values.put("contentStatus", contentStatus);
    SqlRows.insert(values, PlanningItemInsert.class, mapper::insertItem);
    return ((Number) values.get("id")).longValue();
  }

  public int updateItemVersion(long id, String payload, long version) {
    return mapper.updateItemVersion(id, payload, version);
  }

  public int updateItemContent(long id, String status, String payload) {
    return mapper.updateItemContent(id, status, payload);
  }

  public long saveAdjustment(long itemId, String payload) {
    Map<String, Object> values = new HashMap<>();
    values.put("itemId", itemId);
    values.put("payload", payload);
    SqlRows.insert(values, AdjustmentInsert.class, mapper::insertAdjustment);
    return ((Number) values.get("id")).longValue();
  }

  public List<Map<String, Object>> adjustments(long itemId) {
    List<Map<String, Object>> out = new ArrayList<>();
    for (Map<String, Object> row : SqlRows.list(mapper.adjustments(itemId))) {
      Map<String, Object> value = Json.read(String.valueOf(row.get("payload")));
      value.put("id", row.get("id"));
      out.add(value);
    }
    return out;
  }

  public List<Map<String, Object>> pendingItems(long afterId, int limit) {
    return SqlRows.list(mapper.pendingItems(afterId, limit));
  }

  public List<Map<String, Object>> contentFlowCandidates(long afterId, int limit) {
    return SqlRows.list(mapper.contentFlowCandidates(afterId, limit));
  }

  public List<Map<String, Object>> batchItemStatuses(long id) {
    return SqlRows.list(mapper.batchItemStatuses(id));
  }

  public List<Map<String, Object>> tasks() {
    return SqlRows.list(mapper.allTasks());
  }

  public List<Map<String, Object>> pending() {
    return SqlRows.list(mapper.pendingTasks());
  }

  /** Claim immediately before dispatch, so a slow first call cannot expire leases of later rows. */
  public Map<String,Object> claimTask(long id, String owner, long now, long leaseMillis) {
    if(owner==null || owner.isEmpty() || leaseMillis<1000 || leaseMillis>600000)
      throw new IllegalArgumentException("领取参数无效");
    return transaction(() -> {
        Map<String,Object> current=lockedTask(id);
        if(current==null || !Arrays.asList("pending","computing").contains(current.get("status"))) return null;
        Map<String,Object> payload=Json.read(Json.text(current,"payload"));
        Map<String,Object> lease=Json.object(payload.get("execution_lease"));
        if(Json.number(lease,"expires_at")>now) return null;
        payload.put("execution_lease",Json.map("owner",owner,"expires_at",Math.addExact(now,leaseMillis)));
        String frozen=Json.write(payload);
        if(mapper.updateTaskPayload(id,frozen,now)!=1) return null;
        current.put("payload",frozen); return current;
    });
  }

  /** Ownership is checked while holding the task row lock, fencing a late prior worker. */
  public void withClaim(long id, String owner, Runnable action) {
    transaction(() -> {
      Map<String,Object> current=lockedTask(id);
      if(current!=null && Arrays.asList("pending","computing").contains(current.get("status"))
          && owner.equals(Json.text(Json.object(Json.read(Json.text(current,"payload")).get("execution_lease")),"owner")))
        action.run();
      return null;
    });
  }

  public void releaseClaim(long id, String owner) {
    withClaim(id,owner,() -> {
      Map<String,Object> current=lockedTask(id);
      Map<String,Object> payload=Json.read(Json.text(current,"payload"));
      payload.remove("execution_lease");
      mapper.updateTaskPayload(id,Json.write(payload),System.currentTimeMillis());
    });
  }

  public long saveMarketingTask(Map<String, Object> values) {
    SqlRows.insert(values, MarketingTaskInsert.class, mapper::insertMarketingTask);
    return ((Number) values.get("id")).longValue();
  }

  public Map<String, Object> marketingByRequest(String requestId) {
    return SqlRows.one(mapper.marketingByRequest(requestId));
  }

  public Map<String, Object> marketingByCode(String code) {
    return SqlRows.one(mapper.marketingByCode(code));
  }

  public Map<String, Object> lockedMarketingTask(String code) {
    return SqlRows.one(mapper.lockedMarketingTask(code));
  }

  public List<Map<String, Object>> marketingTasks() {
    return SqlRows.list(mapper.allMarketingTasks());
  }

  public List<Map<String, Object>> unlinkedMarketingTasks(int limit) {
    return SqlRows.list(mapper.unlinkedMarketingTasks(limit));
  }

  public void attachMarketingBatch(long id, long batch, int count) {
    mapper.attachMarketingBatch(id, batch, count);
  }

  public List<Map<String, Object>> pendingMarketingTasks(long afterId, int limit) {
    return SqlRows.list(mapper.pendingMarketingTasks(afterId, limit));
  }

  public void updateMarketingProgress(
      long id, String status, int accountCount, int completed, int failed, long reportedAt) {
    mapper.updateMarketingProgress(
        id, status, accountCount, completed, failed, reportedAt, System.currentTimeMillis());
  }

  public List<Map<String, Object>> batches() {
    List<Map<String, Object>> out = new ArrayList<>();
    for (Map<String, Object> row : SqlRows.list(mapper.allBatchPayloads()))
      out.add(Json.read(String.valueOf(row.get("payload"))));
    return out;
  }

  public List<Map<String, Object>> items() {
    return materializeItems(SqlRows.list(mapper.allItems()));
  }

  public List<Map<String, Object>> itemsByBatch(long batchId) {
    return materializeItems(SqlRows.list(mapper.itemsByBatch(batchId)));
  }

  public Map<String, Object> itemById(long id) {
    Map<String, Object> row = SqlRows.one(mapper.itemById(id));
    return row == null ? null : materializeItems(Collections.singletonList(row)).get(0);
  }

  public List<Map<String, Object>> materializeItems(List<Map<String, Object>> rows) {
    List<Map<String, Object>> out = new ArrayList<>();
    for (Map<String, Object> r : rows) {
      Map<String, Object> row = Json.read(String.valueOf(r.get("payload")));
      if (row.get("account_snapshot") instanceof Map)
        row.put("account_snapshot", AccountSnapshotView.from(Json.object(row.get("account_snapshot"))));
      row.put("id", r.get("id"));
      row.put("production_status", r.get("content_status"));
      row.put("result_version", r.get("version"));
      boolean replace =
          "planned".equals(r.get("content_status")) && !Json.text(row, "topic_id").isEmpty();
      row.put("allow_replace", replace);
      row.put(
          "replace_block_reason",
          replace ? "" : Json.text(row, "topic_id").isEmpty() ? "热点尚未定题" : "内容已进入生产，不可替换选题");
      out.add(row);
    }
    return out;
  }
}
