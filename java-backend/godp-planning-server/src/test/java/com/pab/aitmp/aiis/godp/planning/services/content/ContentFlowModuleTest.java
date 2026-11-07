package com.pab.aitmp.aiis.godp.planning.services.content;

import com.pab.aitmp.aiis.godp.planning.api.port.ContentFlowWriter;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.pab.aitmp.aiis.godp.planning.services.config.BusinessPlanningConfigService;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualRepository;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class ContentFlowModuleTest {
  private ApplicationContextRunner context() {
    return new ApplicationContextRunner().withUserConfiguration(ContentFlowModule.class)
        .withBean(ManualRepository.class, () -> mock(ManualRepository.class))
        .withBean(BusinessPlanningConfigService.class, () -> mock(BusinessPlanningConfigService.class));
  }

  @Test
  void disabledFeatureDoesNotRequireAHostWriterAndEnabledFeatureCannotSilentlyDropWrites() {
    context().run(c -> {
      assertNull(c.getStartupFailure());
      assertEquals(0, c.getBeansOfType(ContentFlowDispatchService.class).size());
    });
    context().withPropertyValues("planning.content-flow.enabled=true").run(c ->
        assertNotNull(c.getStartupFailure()));
    context().withPropertyValues("planning.content-flow.enabled=true")
        .withBean(ContentFlowWriter.class, () -> entry -> { throw new IllegalStateException("Test only"); })
        .run(c -> {
          assertNull(c.getStartupFailure());
          assertNotNull(c.getBean(ContentFlowDispatchService.class));
        });
  }
}
