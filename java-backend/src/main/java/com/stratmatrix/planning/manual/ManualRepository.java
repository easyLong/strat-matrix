package com.stratmatrix.planning.manual;

import java.util.*;
import java.util.function.Supplier;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** Business persistence facade; SQL is exclusively defined by the MyBatis mapper. */
public class ManualRepository {
  private final ManualMapper mapper;
  private final TransactionTemplate tx;

  public ManualRepository(ManualMapper mapper, PlatformTransactionManager manager) {
    this.mapper = Objects.requireNonNull(mapper, "business MyBatis mapper");
    this.tx =
        new TransactionTemplate(Objects.requireNonNull(manager, "business transaction manager"));
  }

  public <T> T transaction(Supplier<T> action) {
    return tx.execute(s -> action.get());
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
    mapper.insertPreview(values);
  }

  public Map<String, Object> taskByPreview(String code) {
    return mapper.taskByPreview(code);
  }

  public Map<String, Object> previewByCode(String code) {
    return mapper.previewByCode(code);
  }

  public Map<String, Object> lockedPreview(String code) {
    return mapper.lockedPreview(code);
  }

  public Map<String, Object> taskById(long id) {
    return mapper.taskById(id);
  }

  public Map<String, Object> lockedTask(long id) {
    return mapper.lockedTask(id);
  }

  public Map<String, Object> batchById(long id) {
    return mapper.batchById(id);
  }

  public List<Map<String, Object>> completedTopicUsage(List<String> topicIds) {
    if (topicIds == null || topicIds.isEmpty() || topicIds.size() > 500)
      throw new BusinessException(422, "选题ID数量须为1至500");
    return mapper.completedTopicUsage(topicIds);
  }

  public Map<String, Object> lockedBatch(long id) {
    return mapper.lockedBatch(id);
  }

  public Map<String, Object> lockedItem(long id) {
    return mapper.lockedItem(id);
  }

  public long createTask(String previewCode, String taskCode, String payload, long time) {
    Map<String, Object> values = new HashMap<>();
    values.put("previewCode", previewCode);
    values.put("taskCode", taskCode);
    values.put("payload", payload);
    values.put("time", time);
    mapper.insertTask(values);
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
    mapper.insertItem(values);
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
    mapper.insertAdjustment(values);
    return ((Number) values.get("id")).longValue();
  }

  public List<Map<String, Object>> adjustments(long itemId) {
    List<Map<String, Object>> out = new ArrayList<>();
    for (Map<String, Object> row : mapper.adjustments(itemId)) {
      Map<String, Object> value = Json.read(String.valueOf(row.get("payload")));
      value.put("id", row.get("id"));
      out.add(value);
    }
    return out;
  }

  public List<Map<String, Object>> pendingItems(long afterId, int limit) {
    return mapper.pendingItems(afterId, limit);
  }

  public List<Map<String, Object>> batchItemStatuses(long id) {
    return mapper.batchItemStatuses(id);
  }

  public List<Map<String, Object>> tasks() {
    return mapper.allTasks();
  }

  public List<Map<String, Object>> pending() {
    return mapper.pendingTasks();
  }

  public long saveMarketingTask(Map<String, Object> values) {
    mapper.insertMarketingTask(values);
    return ((Number) values.get("id")).longValue();
  }

  public Map<String, Object> marketingByRequest(String requestId) {
    return mapper.marketingByRequest(requestId);
  }

  public Map<String, Object> marketingByCode(String code) {
    return mapper.marketingByCode(code);
  }

  public Map<String, Object> lockedMarketingTask(String code) {
    return mapper.lockedMarketingTask(code);
  }

  public List<Map<String, Object>> marketingTasks() {
    return mapper.allMarketingTasks();
  }

  public List<Map<String, Object>> unlinkedMarketingTasks(int limit) {
    return mapper.unlinkedMarketingTasks(limit);
  }

  public void attachMarketingBatch(long id, long batch, int count) {
    mapper.attachMarketingBatch(id, batch, count);
  }

  public List<Map<String, Object>> pendingMarketingTasks(long afterId, int limit) {
    return mapper.pendingMarketingTasks(afterId, limit);
  }

  public void updateMarketingProgress(
      long id, String status, int accountCount, int completed, int failed, long reportedAt) {
    mapper.updateMarketingProgress(
        id, status, accountCount, completed, failed, reportedAt, System.currentTimeMillis());
  }

  public List<Map<String, Object>> batches() {
    List<Map<String, Object>> out = new ArrayList<>();
    for (Map<String, Object> row : mapper.allBatchPayloads())
      out.add(Json.read(String.valueOf(row.get("payload"))));
    return out;
  }

  public List<Map<String, Object>> items() {
    return materializeItems(mapper.allItems());
  }

  public List<Map<String, Object>> itemsByBatch(long batchId) {
    return materializeItems(mapper.itemsByBatch(batchId));
  }

  public Map<String, Object> itemById(long id) {
    Map<String, Object> row = mapper.itemById(id);
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
