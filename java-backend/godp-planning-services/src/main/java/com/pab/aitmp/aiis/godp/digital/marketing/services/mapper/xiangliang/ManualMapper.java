package com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang;

import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.*;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.row.*;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.command.*;

import java.util.List;

import org.apache.ibatis.annotations.Param;

/** MyBatis contract for planning business tables. Bound to the host business database. */
public interface ManualMapper {
  int ping();

  List<String> plannedAccountIds(@Param("date") String date);

  List<String> reservedAccountIds(@Param("date") String date);

  int insertPreview(PreviewInsert values);

  ManualPreviewEntity previewByCode(@Param("code") String code);

  ManualPreviewEntity lockedPreview(@Param("code") String code);

  int insertTask(ManualTaskInsert values);

  ManualTaskEntity taskByPreview(@Param("code") String code);

  ManualTaskEntity taskById(@Param("id") long id);

  ManualTaskEntity lockedTask(@Param("id") long id);

  List<ManualTaskEntity> allTasks();

  List<ManualTaskEntity> pendingTasks();

  List<PlanningItemEntity> contentFlowCandidates(@Param("afterId") long afterId, @Param("limit") int limit);

  int insertMarketingTask(MarketingTaskInsert values);

  ManualMarketingTaskEntity marketingByRequest(@Param("requestId") String requestId);

  ManualMarketingTaskEntity marketingByCode(@Param("taskCode") String taskCode);

  ManualMarketingTaskEntity lockedMarketingTask(@Param("taskCode") String taskCode);

  List<ManualMarketingTaskEntity> allMarketingTasks();

  List<ManualMarketingTaskEntity> unlinkedMarketingTasks(@Param("limit") int limit);

  int attachMarketingBatch(
      @Param("id") long id, @Param("batch") long batch, @Param("count") int count);

  List<ManualMarketingTaskEntity> pendingMarketingTasks(
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

  int reviveReservation(
      @Param("date") String date,
      @Param("accountId") String accountId,
      @Param("taskId") long taskId);

  int markComputing(@Param("id") long id, @Param("time") long time);

  int updateTaskPayload(@Param("id") long id, @Param("payload") String payload, @Param("time") long time);

  int noteRetry(@Param("id") long id, @Param("message") String message, @Param("time") long time);

  int markFailed(@Param("id") long id, @Param("reason") String reason, @Param("time") long time);

  int deleteReservations(@Param("id") long id);

  int markCompleted(@Param("id") long id, @Param("time") long time);

  int insertBatch(
      @Param("id") long id,
      @Param("payload") String payload,
      @Param("time") long time,
      @Param("week") String week);

  PlanningBatchEntity batchById(@Param("id") long id);

  PlanningBatchEntity lockedBatchWrite(@Param("id") long id);

  int insertStagingBatch(@Param("id") long id, @Param("payload") String payload,
      @Param("time") long time, @Param("week") String week);

  int advanceBatchWrite(@Param("id") long id, @Param("cursor") int cursor);

  long stagedItemCount(@Param("id") long id);

  int publishBatch(@Param("id") long id);

  PlanningBatchEntity lockedBatch(@Param("id") long id);

  List<PlanningBatchEntity> allBatchPayloads();

  int updateBatchPayload(
      @Param("id") long id, @Param("payload") String payload, @Param("week") String week);

  int insertItem(PlanningItemInsert values);

  PlanningItemEntity lockedItem(@Param("id") long id);

  List<PlanningItemEntity> allItems();

  List<PlanningItemEntity> itemsByBatch(@Param("batchId") long batchId);

  PlanningItemEntity itemById(@Param("id") long id);

  List<PlanningItemEntity> pendingItems(@Param("afterId") long afterId, @Param("limit") int limit);

  List<PlanningItemEntity> batchItemStatuses(@Param("batchId") long batchId);

  int updateItemVersion(
      @Param("id") long id, @Param("payload") String payload, @Param("version") long version);

  int updateItemContent(
      @Param("id") long id, @Param("status") String status, @Param("payload") String payload);

  List<PlanningAdjustmentEntity> adjustments(@Param("itemId") long itemId);

  int insertAdjustment(AdjustmentInsert values);

  List<TopicUsageRow> completedTopicUsage(@Param("topicIds") List<String> topicIds);
}
