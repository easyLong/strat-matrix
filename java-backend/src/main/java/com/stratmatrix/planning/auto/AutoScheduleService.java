package com.stratmatrix.planning.auto;

import com.stratmatrix.planning.config.BusinessPlanningConfig;
import com.stratmatrix.planning.config.BusinessPlanningConfigService;
import com.stratmatrix.planning.manual.Json;
import java.time.*;
import java.time.temporal.TemporalAdjusters;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.dao.DuplicateKeyException;

/** Java decides when the next weekly business task is due and records each attempt durably. */
public class AutoScheduleService {
  private static final ZoneId BUSINESS_ZONE = ZoneId.of("Asia/Shanghai");
  private final BusinessPlanningConfigService config;
  private final AutoScheduleMapper mapper;
  private final AutoSchedulePort algorithm;
  private final AutoResultCommitService commit;

  public AutoScheduleService(
      BusinessPlanningConfigService config,
      AutoScheduleMapper mapper,
      AutoSchedulePort algorithm,
      AutoResultCommitService commit) {
    this.config = config;
    this.mapper = mapper;
    this.algorithm = algorithm;
    this.commit = commit;
  }

  public static LocalDate dueCycle(Instant instant, BusinessPlanningConfig settings) {
    if (instant == null || settings == null) throw new IllegalArgumentException("调度时间或业务配置不能为空");
    settings.validate();
    ZonedDateTime local = instant.atZone(BUSINESS_ZONE);
    LocalDate monday = local.toLocalDate().with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
    LocalDate triggerDate = monday.plusDays(settings.schedule_day - 1);
    ZonedDateTime trigger =
        ZonedDateTime.of(triggerDate, LocalTime.parse(settings.schedule_time), BUSINESS_ZONE);
    return local.isBefore(trigger) ? null : monday.plusWeeks(1);
  }

  public Map<String, Object> tick(Instant instant) {
    BusinessPlanningConfigService.Result current = config.current();
    LocalDate cycle = dueCycle(instant, current.config);
    if (cycle == null) return response("waiting", null);
    String start = cycle.toString();
    Map<String, Object> task = mapper.byCycle(start);
    if (task == null) {
      Map<String, Object> values = new HashMap<>();
      values.put("cycleStart", start);
      values.put("cycleEnd", cycle.plusDays(6).toString());
      values.put("configVersion", current.version);
      values.put("configJson", Json.write(current.config));
      values.put("time", instant.toEpochMilli());
      try {
        mapper.insert(values);
      } catch (DuplicateKeyException anotherHostWon) {
        /* read winner */
      }
      task = mapper.byCycle(start);
      if (task == null) throw new IllegalStateException("自动策划任务未能持久化");
    }
    return advance(task, cycle, instant);
  }

  /** Continue older tasks even when a later configuration changes the weekly trigger time. */
  public List<Map<String, Object>> advanceOpen(Instant instant) {
    List<Map<String, Object>> results = new ArrayList<>();
    for (Map<String, Object> task : mapper.openTasks()) {
      LocalDate cycle = LocalDate.parse(String.valueOf(task.get("cycle_start")));
      try {
        results.add(advance(task, cycle, instant));
      } catch (RuntimeException error) {
        Map<String, Object> failed = response("retry_pending", task);
        failed.put("error_type", error.getClass().getSimpleName());
        results.add(failed);
      }
    }
    return results;
  }

  private Map<String, Object> advance(Map<String, Object> task, LocalDate cycle, Instant instant) {
    String start = cycle.toString();
    if ("待确认".equals(task.get("status"))) return confirm(task, instant);
    if ("计算中".equals(task.get("status"))) {
      try {
        long pipelineId = ((Number) task.get("pipeline_id")).longValue();
        Map<String, Object> state = algorithm.status(pipelineId);
        if (state == null) throw new IllegalStateException("算法服务未返回Pipeline状态");
        String phase = String.valueOf(state.get("status"));
        if ("java".equals(state.get("commit_owner"))) {
          if ("waiting".equals(phase)
              && java.util.Collections.singletonList("result_commit")
                  .equals(state.get("active_stages"))) {
            Map<String, Object> proposal =
                algorithm.proposal(
                    pipelineId,
                    ((Number) task.get("business_config_version")).intValue(),
                    Json.read(String.valueOf(task.get("business_config_json"))));
            Map<String, Object> saved = commit.commit(((Number) task.get("id")).longValue(), proposal, instant);
            // One bounded write page per host invocation. Only a fully published
            // batch can be acknowledged to Python.
            return "待确认".equals(saved.get("status"))
                ? confirm(saved, instant) : response("persisting", saved);
          }
          if ("succeeded".equals(phase)) throw new IllegalStateException("算法已确认但Java业务提交凭证缺失");
        }
        if ("succeeded".equals(phase) || "failed".equals(phase) || "cancelled".equals(phase)) {
          String finalState = "succeeded".equals(phase) ? "旧结果已存在" : "策划失败";
          Long batch = positiveId(state.get("production_batch_id"));
          if ("旧结果已存在".equals(finalState) && batch == null)
            throw new IllegalStateException("完成的Pipeline缺少正式批次编号");
          String error = "旧结果已存在".equals(finalState) ? "" : "算法Pipeline" + phase;
          mapper.finish(
              ((Number) task.get("id")).longValue(),
              finalState,
              batch,
              error,
              instant.toEpochMilli());
        }
        return response("reconciled", mapper.byCycle(start));
      } catch (RuntimeException error) {
        if (!"待确认".equals(mapper.byCycle(start).get("status")))
          mapper.resultError(
              ((Number) task.get("id")).longValue(),
              error.getClass().getSimpleName(),
              instant.toEpochMilli());
        throw error;
      }
    }
    if (!"待发起".equals(task.get("status"))) return response("reused", task);
    long id = ((Number) task.get("id")).longValue();
    try {
      Map<String, Object> receipt =
          algorithm.start(
              cycle,
              ((Number) task.get("business_config_version")).intValue(),
              Json.read(String.valueOf(task.get("business_config_json"))));
      if (receipt == null) throw new IllegalStateException("算法服务未返回受理结果");
      if (!"created".equals(receipt.get("status")) && !"reused".equals(receipt.get("status")))
        throw new IllegalStateException("算法服务未确认Pipeline创建或复用");
      Long pipeline = positiveId(receipt.get("pipeline_id"));
      Long oldBatch = positiveId(receipt.get("batch_id"));
      if (pipeline == null && oldBatch == null)
        throw new IllegalStateException("算法服务未返回Pipeline或已有批次编号");
      if (pipeline != null && !"java".equals(receipt.get("commit_owner")))
        throw new IllegalStateException("新算法任务未确认由Java提交正式结果");
      String status = pipeline == null ? "旧结果已存在" : "计算中";
      mapper.accepted(id, pipeline, oldBatch, status, instant.toEpochMilli());
      return response("accepted", mapper.byCycle(start));
    } catch (RuntimeException failure) {
      String message = failure.getClass().getSimpleName();
      mapper.failedAttempt(
          id, message.substring(0, Math.min(message.length(), 500)), instant.toEpochMilli());
      throw failure;
    }
  }

  private Map<String, Object> confirm(Map<String, Object> task, Instant instant) {
    long id = ((Number) task.get("id")).longValue();
    if ("已完成".equals(task.get("status"))) return response("reused", task);
    try {
      long pipeline = ((Number) task.get("pipeline_id")).longValue();
      long batch = ((Number) task.get("business_batch_id")).longValue();
      String hash = String.valueOf(task.get("proposal_hash"));
      Map<String, Object> receipt = algorithm.acknowledge(pipeline, hash, batch);
      if (receipt == null
          || !"accepted".equals(receipt.get("status"))
          || !hash.equals(receipt.get("proposal_hash"))
          || !Long.valueOf(pipeline).equals(positiveId(receipt.get("pipeline_id")))
          || !Long.valueOf(batch).equals(positiveId(receipt.get("business_batch_id"))))
        throw new IllegalStateException("算法服务返回了不匹配的确认凭证");
      mapper.acknowledged(id, hash, batch, instant.toEpochMilli());
      return response("completed", mapper.byCycle(String.valueOf(task.get("cycle_start"))));
    } catch (RuntimeException error) {
      mapper.resultError(id, error.getClass().getSimpleName(), instant.toEpochMilli());
      throw error;
    }
  }

  private static Long positiveId(Object value) {
    if (!(value instanceof Number)) return null;
    long number = ((Number) value).longValue();
    return number > 0 ? number : null;
  }

  private static Map<String, Object> response(String status, Map<String, Object> task) {
    Map<String, Object> result = new HashMap<>();
    result.put("status", status);
    if (task != null) result.put("task", task);
    return result;
  }
}
