package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.query;

import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.PlanningQueryMapper;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.ManualPorts;
import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.PlanningReadQueries;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.ManualPlanningService;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.ManualRepository;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.*;

@Configuration("xiangliangPlanningReadModule")
@ConditionalOnProperty(name = "planning.history.mode", havingValue = "business_only")
public class PlanningReadModule {
  @Bean(name="xiangliangPlanningReadQueries")
  public PlanningReadQueries planningReadQueries(
      PlanningQueryMapper mapper,
      ManualRepository repo,
      ManualPlanningService manual,
      ManualPorts.Source accountFacts) {
    return new SqlPlanningReadQueries(mapper, repo, manual, accountFacts);
  }
}
