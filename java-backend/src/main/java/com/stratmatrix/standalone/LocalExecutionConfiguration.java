package com.stratmatrix.standalone;

import com.stratmatrix.planning.adapter.legacy.LegacyPythonProperties;
import com.stratmatrix.planning.adapter.python.PythonExecutionClient;
import com.stratmatrix.planning.auto.AutoScheduleService;
import com.stratmatrix.planning.config.ConfigReleaseService;
import com.stratmatrix.planning.content.*;
import com.stratmatrix.planning.manual.ManualContentStatusService;
import com.stratmatrix.planning.manual.ManualPlanningService;
import com.stratmatrix.planning.manual.MarketingTaskService;
import java.io.IOException;
import java.net.HttpURLConnection;
import java.time.Instant;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.web.client.RestTemplate;

/** 仅行外开发模拟宿主调度；驻场不复制本配置，改由客户调度器调用客户端。 */
@Configuration
@Profile("local")
@ConditionalOnProperty(name = "planning.local-pulse.enabled", havingValue = "true")
@EnableScheduling
public class LocalExecutionConfiguration {
  @Bean
  public LocalJobPulse localJobPulse(
      LegacyPythonProperties properties,
      ObjectProvider<ManualPlanningService> manual,
      ObjectProvider<AutoScheduleService> auto,
      ObjectProvider<ConfigReleaseService> configs,
      ObjectProvider<SlotCompletionService> completion,
      ObjectProvider<MarketingPlacementService> placements,
      ObjectProvider<ManualContentStatusService> contentStatus,
      ObjectProvider<MarketingTaskService> marketing,
      org.springframework.core.env.Environment environment) {
    java.util.Map<String, Long> cursors = new java.util.HashMap<>();
    SimpleClientHttpRequestFactory factory =
        new SimpleClientHttpRequestFactory() {
          @Override
          protected void prepareConnection(HttpURLConnection connection, String method)
              throws IOException {
            super.prepareConnection(connection, method);
            connection.setInstanceFollowRedirects(false);
          }
        };
    factory.setConnectTimeout(1000);
    factory.setReadTimeout(3000);
    LocalJobPulse pulse =
        new LocalJobPulse(
            new PythonExecutionClient(
                properties.baseUri(), properties.getIntegrationToken(), new RestTemplate(factory)),
            () -> {
              runPhase(
                  () -> {
                    ConfigReleaseService config = configs.getIfAvailable();
                    if (config != null) config.advancePending();
                  });
              runPhase(
                  () -> {
                    ManualPlanningService service = manual.getIfAvailable();
                    if (service != null) service.advance();
                  });
              runPhase(
                  () -> {
                    SlotCompletionService s = completion.getIfAvailable();
                    if (s != null)
                      advanceCursor(
                          cursors,
                          "hotspot",
                          s.hotspots(Instant.now(), 100, cursors.getOrDefault("hotspot", 0L)));
                  });
              runPhase(
                  () -> {
                    SlotCompletionService s = completion.getIfAvailable();
                    if (s != null)
                      advanceCursor(
                          cursors,
                          "marketing",
                          s.marketing(Instant.now(), 100, cursors.getOrDefault("marketing", 0L)));
                  });
              runPhase(
                  () -> {
                    MarketingPlacementService s = placements.getIfAvailable();
                    if (s != null) s.reconcile(Instant.now(), 100);
                  });
              runPhase(
                  () -> {
                    ManualContentStatusService s = contentStatus.getIfAvailable();
                    if (s != null)
                      advanceCursor(
                          cursors,
                          "content",
                          s.reconcile(100, cursors.getOrDefault("content", 0L)));
                  });
              runPhase(
                  () -> {
                    MarketingTaskService s = marketing.getIfAvailable();
                    if (s != null)
                      advanceCursor(
                          cursors,
                          "marketing-status",
                          s.reconcile(100, cursors.getOrDefault("marketing-status", 0L)));
                  });
            });
    if ("business_only".equals(environment.getProperty("planning.history.mode")))
      pulse.enableJavaBusinessOwnership();
    AutoScheduleService autoService = auto.getIfAvailable();
    if (autoService != null)
      pulse.enableJavaWeekly(
          () -> {
            Instant now = Instant.now();
            autoService.advanceOpen(now);
            autoService.tick(now);
          });
    return pulse;
  }

  private static void runPhase(Runnable action) {
    try {
      action.run();
    } catch (RuntimeException unavailable) {
      org.slf4j.LoggerFactory.getLogger(LocalExecutionConfiguration.class)
          .warn("本地业务推进阶段暂不可用：{}", unavailable.getClass().getSimpleName());
    }
  }

  private static void advanceCursor(
      java.util.Map<String, Long> cursors, String key, java.util.Map<String, Object> result) {
    cursors.put(
        key,
        Boolean.TRUE.equals(result.get("has_more"))
            ? com.stratmatrix.planning.manual.Json.number(result, "next_after_id")
            : 0L);
  }
}
