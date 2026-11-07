package com.pab.aitmp.aiis.godp.planning.services.content;

import com.pab.aitmp.aiis.godp.planning.api.port.PlanningContentPort;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualContentStatusService;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualRepository;

import com.pab.aitmp.aiis.godp.planning.services.config.BusinessPlanningConfigService;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.*;

@Configuration
@ConditionalOnProperty(name = "planning.manual.enabled", havingValue = "true")
public class ContentCompletionModule {
  @Bean
  public SlotCompletionService slotCompletionService(
      SlotCompletionMapper mapper,
      ManualRepository repo,
      PlanningContentPort source,
      ManualContentStatusService progress) {
    return new SlotCompletionService(mapper, repo, source, progress);
  }

  @Bean
  public MarketingPlacementService marketingPlacementService(
      ManualRepository repo,
      PlanningContentPort source,
      SlotCompletionMapper mapper,
      BusinessPlanningConfigService config) {
    return new MarketingPlacementService(repo, source, mapper, config);
  }
}
