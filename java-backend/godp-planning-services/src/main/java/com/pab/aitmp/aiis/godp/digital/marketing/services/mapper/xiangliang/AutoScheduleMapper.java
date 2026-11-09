package com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang;

import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.*;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.row.*;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.command.*;

import java.util.List;

import org.apache.ibatis.annotations.Param;

/** MyBatis persistence contract for Java-owned automatic planning triggers. */
public interface AutoScheduleMapper {
  AutoPlanningTaskEntity byId(@Param("id") long id);

  AutoPlanningTaskEntity byCycle(@Param("cycleStart") String cycleStart);

  AutoPlanningTaskEntity lockedById(@Param("id") long id);

  List<AutoPlanningTaskEntity> openTasks();

  int insert(AutoTaskInsert values);

  int accepted(
      @Param("id") long id,
      @Param("pipelineId") Long pipelineId,
      @Param("legacyBatchId") Long legacyBatchId,
      @Param("status") String status,
      @Param("time") long time);

  int failedAttempt(@Param("id") long id, @Param("error") String error, @Param("time") long time);

  int finish(
      @Param("id") long id,
      @Param("status") String status,
      @Param("legacyBatchId") Long legacyBatchId,
      @Param("error") String error,
      @Param("time") long time);

  int committed(
      @Param("id") long id,
      @Param("batchId") long batchId,
      @Param("hash") String hash,
      @Param("time") long time);

  int acknowledged(
      @Param("id") long id,
      @Param("hash") String hash,
      @Param("batchId") long batchId,
      @Param("time") long time);

  int resultError(@Param("id") long id, @Param("error") String error, @Param("time") long time);
}
