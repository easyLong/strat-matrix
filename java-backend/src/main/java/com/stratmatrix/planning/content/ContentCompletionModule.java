package com.stratmatrix.planning.content;

import com.stratmatrix.planning.config.BusinessPlanningConfigService;
import com.stratmatrix.planning.manual.*;
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
