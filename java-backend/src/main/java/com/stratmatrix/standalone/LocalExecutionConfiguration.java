package com.stratmatrix.standalone;

import com.stratmatrix.planning.adapter.python.PythonExecutionClient;
import com.stratmatrix.planning.tasks.PlanningTaskService;
import com.stratmatrix.planning.tasks.PlanningTaskService.Kind;
import java.time.Instant;
import java.util.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.*;
import org.springframework.scheduling.annotation.EnableScheduling;

/** Outside timing adapter only. Host jobs invoke the same ordinary task service. */
@Configuration
@Profile("local & !inside")
@ConditionalOnProperty(name = "planning.local-pulse.enabled", havingValue = "true")
@EnableScheduling
public class LocalExecutionConfiguration {
  @Bean
  public LocalJobPulse localJobPulse(PythonExecutionClient python, PlanningTaskService tasks) {
    Map<Kind, Long> cursors = new EnumMap<>(Kind.class);
    LocalDailyHotspotCheck daily =
        new LocalDailyHotspotCheck((now, after) -> tasks.run(Kind.HOTSPOT, now, 100, after));
    LocalJobPulse pulse =
        new LocalJobPulse(
            python,
            () -> {
              for (Kind kind :
                  Arrays.asList(
                      Kind.CONFIGURATION,
                      Kind.MANUAL,
                      Kind.MARKETING,
                      Kind.MARKETING_PLACEMENT,
                      Kind.CONTENT_STATUS,
                      Kind.MARKETING_STATUS)) {
                try {
                  Map<String, Object> result =
                      tasks.run(kind, Instant.now(), 100, cursors.getOrDefault(kind, 0L));
                  cursors.put(
                      kind,
                      Boolean.TRUE.equals(result.get("has_more"))
                          ? com.stratmatrix.planning.manual.Json.number(result, "next_after_id")
                          : 0L);
                  if ("retry_required".equals(result.get("status"))) warn(kind);
                } catch (RuntimeException failure) {
                  warn(kind);
                }
              }
              try {
                daily.run(Instant.now());
              } catch (RuntimeException failure) {
                warn(Kind.HOTSPOT);
              }
            });
    pulse.enableJavaBusinessOwnership();
    pulse.enableJavaWeekly(
        () -> {
          Map<String, Object> result = tasks.run(Kind.AUTOMATIC, Instant.now(), 100, 0);
          if ("retry_required".equals(result.get("status"))) warn(Kind.AUTOMATIC);
        });
    return pulse;
  }

  private static void warn(Kind kind) {
    org.slf4j.LoggerFactory.getLogger(LocalExecutionConfiguration.class).warn("本地任务阶段待重试：{}", kind);
  }
}
