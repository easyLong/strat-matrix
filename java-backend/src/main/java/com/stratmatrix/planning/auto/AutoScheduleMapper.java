package com.stratmatrix.planning.auto;

import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Param;

/** MyBatis persistence contract for Java-owned automatic planning triggers. */
public interface AutoScheduleMapper {
  Map<String, Object> byId(@Param("id") long id);

  Map<String, Object> byCycle(@Param("cycleStart") String cycleStart);

  Map<String, Object> lockedById(@Param("id") long id);

  List<Map<String, Object>> openTasks();

  int insert(Map<String, Object> values);

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
