package com.stratmatrix.planning.manual;

import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Param;

/** MyBatis contract for planning business tables. Bound to the host business database. */
public interface ManualMapper {
  List<String> plannedAccountIds(@Param("date") String date);

  List<String> reservedAccountIds(@Param("date") String date);

  int insertPreview(Map<String, Object> values);

  Map<String, Object> previewByCode(@Param("code") String code);

  Map<String, Object> lockedPreview(@Param("code") String code);

  int insertTask(Map<String, Object> values);

  Map<String, Object> taskByPreview(@Param("code") String code);

  Map<String, Object> taskById(@Param("id") long id);

  Map<String, Object> lockedTask(@Param("id") long id);

  List<Map<String, Object>> allTasks();

  List<Map<String, Object>> pendingTasks();

  int insertMarketingTask(Map<String, Object> values);

  Map<String, Object> marketingByRequest(@Param("requestId") String requestId);

  Map<String, Object> marketingByCode(@Param("taskCode") String taskCode);

  Map<String, Object> lockedMarketingTask(@Param("taskCode") String taskCode);

  List<Map<String, Object>> allMarketingTasks();

  List<Map<String, Object>> unlinkedMarketingTasks(@Param("limit") int limit);

  int attachMarketingBatch(
      @Param("id") long id, @Param("batch") long batch, @Param("count") int count);

  List<Map<String, Object>> pendingMarketingTasks(
      @Param("afterId") long afterId, @Param("limit") int limit);

  int updateMarketingProgress(
      @Param("id") long id,
      @Param("status") String status,
      @Param("accountCount") int accountCount,
      @Param("completed") int completed,
      @Param("failed") int failed,
      @Param("reportedAt") long reportedAt,
      @Param("updatedAt") long updatedAt);

  int insertReservation(
      @Param("date") String date,
      @Param("accountId") String accountId,
      @Param("taskId") long taskId);

  int markComputing(@Param("id") long id, @Param("time") long time);

  int noteRetry(@Param("id") long id, @Param("message") String message, @Param("time") long time);

  int markFailed(@Param("id") long id, @Param("reason") String reason, @Param("time") long time);

  int deleteReservations(@Param("id") long id);

  int markCompleted(@Param("id") long id, @Param("time") long time);

  int insertBatch(
      @Param("id") long id,
      @Param("payload") String payload,
      @Param("time") long time,
      @Param("week") String week);

  Map<String, Object> batchById(@Param("id") long id);

  Map<String, Object> lockedBatch(@Param("id") long id);

  List<Map<String, Object>> allBatchPayloads();

  int updateBatchPayload(
      @Param("id") long id, @Param("payload") String payload, @Param("week") String week);

  int insertItem(Map<String, Object> values);

  Map<String, Object> lockedItem(@Param("id") long id);

  List<Map<String, Object>> allItems();

  List<Map<String, Object>> itemsByBatch(@Param("batchId") long batchId);

  Map<String, Object> itemById(@Param("id") long id);

  List<Map<String, Object>> pendingItems(@Param("afterId") long afterId, @Param("limit") int limit);

  List<Map<String, Object>> batchItemStatuses(@Param("batchId") long batchId);

  int updateItemVersion(
      @Param("id") long id, @Param("payload") String payload, @Param("version") long version);

  int updateItemContent(
      @Param("id") long id, @Param("status") String status, @Param("payload") String payload);

  List<Map<String, Object>> adjustments(@Param("itemId") long itemId);

  int insertAdjustment(Map<String, Object> values);
}
