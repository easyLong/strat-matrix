package com.stratmatrix.planning.content;

import com.stratmatrix.planning.config.BusinessPlanningConfigService;
import com.stratmatrix.planning.manual.ManualRepository;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.*;

/** Enable after the host provides a real, idempotent content-flow writer. No successful no-op. */
@Configuration
@ConditionalOnProperty(name = "planning.content-flow.enabled", havingValue = "true")
public class ContentFlowModule {
  @Bean
  public ContentFlowDispatchService contentFlowDispatchService(ManualRepository repo,
      BusinessPlanningConfigService config, ContentFlowWriter writer) {
    return new ContentFlowDispatchService(repo, config, writer);
  }
}
