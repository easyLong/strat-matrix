package com.stratmatrix.planning.tasks;

import com.stratmatrix.planning.adapter.python.PythonExecutionClient;
import com.stratmatrix.planning.auto.AutoScheduleService;
import com.stratmatrix.planning.config.ConfigReleaseService;
import com.stratmatrix.planning.content.*;
import com.stratmatrix.planning.manual.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.*;

@Configuration
@ConditionalOnProperty(name = "planning.tasks.enabled", havingValue = "true")
public class PlanningTaskModule {
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
