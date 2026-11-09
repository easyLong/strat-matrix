package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.tasks;

import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.content.ContentFlowDispatchService;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.content.MarketingPlacementService;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.content.SlotCompletionService;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.ManualContentStatusService;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.ManualPlanningService;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.MarketingTaskService;

import com.pab.aitmp.aiis.godp.digital.marketing.client.xiangliang.python.PythonExecutionClient;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.auto.AutoScheduleService;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.config.ConfigReleaseService;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.*;

@Configuration("xiangliangPlanningTaskModule")
@ConditionalOnProperty(name = "planning.tasks.enabled", havingValue = "true")
public class PlanningTaskModule {
  @Bean(name="xiangliangManualTaskAdvanceHandler") public ManualTaskAdvanceHandler manualTaskAdvanceHandler(PlanningTaskService tasks) { return new ManualTaskAdvanceHandler(tasks); }
  @Bean(name="xiangliangAutoScheduleHandler") public AutoScheduleHandler autoScheduleHandler(PlanningTaskService tasks) { return new AutoScheduleHandler(tasks); }
  @Bean(name="xiangliangContentCompletionHandler") public ContentCompletionHandler contentCompletionHandler(PlanningTaskService tasks) { return new ContentCompletionHandler(tasks); }
  @Bean(name="xiangliangHotspotCheckHandler") public HotspotCheckHandler hotspotCheckHandler(PlanningTaskService tasks) { return new HotspotCheckHandler(tasks); }
  @Bean(name="xiangliangPlanningTasks")
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
