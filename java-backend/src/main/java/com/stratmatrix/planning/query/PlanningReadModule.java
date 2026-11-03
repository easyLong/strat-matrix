package com.stratmatrix.planning.query;

import com.stratmatrix.planning.manual.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.*;

@Configuration
@ConditionalOnProperty(name = "planning.history.mode", havingValue = "business_only")
public class PlanningReadModule {
  @Bean
  public PlanningReadQueries planningReadQueries(
      PlanningQueryMapper mapper, ManualRepository repo, ManualPlanningService manual) {
    return new SqlPlanningReadQueries(mapper, repo, manual);
  }
}
