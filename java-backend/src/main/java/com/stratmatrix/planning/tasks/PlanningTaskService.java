package com.stratmatrix.planning.tasks;

import static com.stratmatrix.planning.manual.Json.map;

import com.stratmatrix.planning.adapter.python.PythonExecutionClient;
import com.stratmatrix.planning.auto.AutoScheduleService;
import com.stratmatrix.planning.config.ConfigReleaseService;
import com.stratmatrix.planning.content.*;
import com.stratmatrix.planning.manual.*;
import java.time.Instant;
import java.util.*;

/** Bounded one-pass host jobs. No timers, background threads or implicit full-dataset loops. */
public final class PlanningTaskService {
  public enum Kind {
    CONFIGURATION,
    MANUAL,
    AUTOMATIC,
    HOTSPOT,
    MARKETING,
    MARKETING_PLACEMENT,
    CONTENT_STATUS,
    CONTENT_FLOW,
    MARKETING_STATUS,
    ALGORITHM
  }

  private final ConfigReleaseService config;
  private final ManualPlanningService manual;
  private final AutoScheduleService auto;
  private final SlotCompletionService slots;
  private final MarketingPlacementService placement;
  private final ManualContentStatusService content;
  private final MarketingTaskService marketing;
  private final PythonExecutionClient python;
  private final ContentFlowDispatchService contentFlow;

  public PlanningTaskService(
      ConfigReleaseService config,
      ManualPlanningService manual,
      AutoScheduleService auto,
      SlotCompletionService slots,
      MarketingPlacementService placement,
      ManualContentStatusService content,
      MarketingTaskService marketing,
      PythonExecutionClient python) {
    this(config, manual, auto, slots, placement, content, marketing, python, null);
  }

  public PlanningTaskService(
      ConfigReleaseService config, ManualPlanningService manual, AutoScheduleService auto,
      SlotCompletionService slots, MarketingPlacementService placement, ManualContentStatusService content,
      MarketingTaskService marketing, PythonExecutionClient python, ContentFlowDispatchService contentFlow) {
    this.config = config;
    this.manual = manual;
    this.auto = auto;
    this.slots = slots;
    this.placement = placement;
    this.content = content;
    this.marketing = marketing;
    this.python = python;
    this.contentFlow = contentFlow;
  }
  /** Throws on integration failure so host scheduling must not report false success. */
  public Map<String, Object> run(Kind kind, Instant now, int limit, long after) {
    if (kind == null || now == null || limit < 1 || limit > 500 || after < 0)
      throw new IllegalArgumentException("任务参数无效");
    switch (kind) {
      case CONFIGURATION:
        config.advancePending();
        return pass(kind);
      case MANUAL:
        return manual.advancePass();
      case AUTOMATIC:
        List<Map<String, Object>> advanced = auto.advanceOpen(now);
        Map<String, Object> result = auto.tick(now);
        boolean retry =
            advanced.stream().anyMatch(r -> "retry_pending".equals(r.get("status")))
                || "retry_pending".equals(result.get("status"));
        return map(
            "phase",
            kind.name(),
            "status",
            retry ? "retry_required" : "processed",
            "advanced",
            advanced,
            "result",
            result,
            "has_more",
            false,
            "needs_next_tick",
            retry,
            "next_after_id",
            0L);
      case HOTSPOT:
        return slots.hotspots(now, limit, after);
      case MARKETING:
        return slots.marketing(now, limit, after);
      case MARKETING_PLACEMENT:
        return placement.reconcile(now, limit);
      case CONTENT_STATUS:
        return content.reconcile(limit, after);
      case CONTENT_FLOW:
        if (contentFlow == null) throw new BusinessException(503, "内容流水写入尚未接入，请配置宿主写入方法");
        return contentFlow.scan(now, limit, after);
      case MARKETING_STATUS:
        return marketing.reconcile(limit, after);
      case ALGORITHM:
        python.wakeup(Arrays.asList("planning", "manual_compute"));
        return map(
            "phase",
            kind.name(),
            "status",
            "accepted",
            "business_complete",
            false,
            "has_more",
            false);
      default:
        throw new IllegalArgumentException("未知任务类型");
    }
  }

  private Map<String, Object> pass(Kind kind) {
    return map(
        "phase",
        kind.name(),
        "status",
        "processed",
        "business_complete",
        false,
        "has_more",
        false,
        "next_after_id",
        0L);
  }
}
