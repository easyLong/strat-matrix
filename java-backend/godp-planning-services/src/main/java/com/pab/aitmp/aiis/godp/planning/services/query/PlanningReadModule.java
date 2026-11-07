package com.pab.aitmp.aiis.godp.planning.services.query;

import com.pab.aitmp.aiis.godp.planning.api.port.ManualPorts;
import com.pab.aitmp.aiis.godp.planning.api.port.PlanningReadQueries;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualPlanningService;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualRepository;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.*;

@Configuration
@ConditionalOnProperty(name = "planning.history.mode", havingValue = "business_only")
public class PlanningReadModule {
  @Bean
  public PlanningReadQueries planningReadQueries(
      PlanningQueryMapper mapper,
      ManualRepository repo,
      ManualPlanningService manual,
      ManualPorts.Source accountFacts) {
    return new SqlPlanningReadQueries(mapper, repo, manual, accountFacts);
  }
}
