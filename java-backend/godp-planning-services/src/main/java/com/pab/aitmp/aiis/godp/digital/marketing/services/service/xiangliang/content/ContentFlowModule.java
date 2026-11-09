package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.content;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.ContentFlowWriter;

import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.config.BusinessPlanningConfigService;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.ManualRepository;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.*;

/** Enable after the host provides a real, idempotent content-flow writer. No successful no-op. */
@Configuration("xiangliangContentFlowModule")
@ConditionalOnProperty(name = "planning.content-flow.enabled", havingValue = "true")
public class ContentFlowModule {
  @Bean(name="xiangliangContentFlowDispatchService")
  public ContentFlowDispatchService contentFlowDispatchService(ManualRepository repo,
      BusinessPlanningConfigService config, ContentFlowWriter writer) {
    return new ContentFlowDispatchService(repo, config, writer);
  }
}
