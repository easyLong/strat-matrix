package com.pab.aitmp.aiis.godp.planning.services.tasks;

import com.pab.aitmp.aiis.godp.planning.services.content.ContentFlowDispatchService;
import com.pab.aitmp.aiis.godp.planning.services.content.MarketingPlacementService;
import com.pab.aitmp.aiis.godp.planning.services.content.SlotCompletionService;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualContentStatusService;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualPlanningService;
import com.pab.aitmp.aiis.godp.planning.services.manual.MarketingTaskService;

import com.pab.aitmp.aiis.godp.planning.client.python.PythonExecutionClient;
import com.pab.aitmp.aiis.godp.planning.services.auto.AutoScheduleService;
import com.pab.aitmp.aiis.godp.planning.services.config.ConfigReleaseService;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.*;

@Configuration
@ConditionalOnProperty(name = "planning.tasks.enabled", havingValue = "true")
public class PlanningTaskModule {
  @Bean public ManualTaskAdvanceHandler manualTaskAdvanceHandler(PlanningTaskService tasks) { return new ManualTaskAdvanceHandler(tasks); }
  @Bean public AutoScheduleHandler autoScheduleHandler(PlanningTaskService tasks) { return new AutoScheduleHandler(tasks); }
  @Bean public ContentCompletionHandler contentCompletionHandler(PlanningTaskService tasks) { return new ContentCompletionHandler(tasks); }
  @Bean public HotspotCheckHandler hotspotCheckHandler(PlanningTaskService tasks) { return new HotspotCheckHandler(tasks); }
  @Bean
  public PlanningTaskService planningTasks(
      ConfigReleaseService config,
      ManualPlanningService manual,
      AutoScheduleService auto,
      SlotCompletionService slots,
      MarketingPlacementService placement,
      ManualContentStatusService content,
      MarketingTaskService marketing,
      PythonExecutionClient python,
      org.springframework.beans.factory.ObjectProvider<ContentFlowDispatchService> contentFlow) {
    return new PlanningTaskService(
        config, manual, auto, slots, placement, content, marketing, python, contentFlow.getIfAvailable());
  }
}
