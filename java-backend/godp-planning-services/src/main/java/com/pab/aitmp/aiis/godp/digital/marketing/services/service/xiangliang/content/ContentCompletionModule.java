package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.content;

import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.SlotCompletionMapper;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.PlanningContentPort;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.ManualContentStatusService;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.ManualRepository;

import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.config.BusinessPlanningConfigService;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.*;

@Configuration("xiangliangContentCompletionModule")
@ConditionalOnProperty(name = "planning.manual.enabled", havingValue = "true")
public class ContentCompletionModule {
  @Bean(name="xiangliangSlotCompletionService")
  public SlotCompletionService slotCompletionService(
      SlotCompletionMapper mapper,
      ManualRepository repo,
      PlanningContentPort source,
      ManualContentStatusService progress) {
    return new SlotCompletionService(mapper, repo, source, progress);
  }

  @Bean(name="xiangliangMarketingPlacementService")
  public MarketingPlacementService marketingPlacementService(
      ManualRepository repo,
      PlanningContentPort source,
      SlotCompletionMapper mapper,
      BusinessPlanningConfigService config) {
    return new MarketingPlacementService(repo, source, mapper, config);
  }
}
