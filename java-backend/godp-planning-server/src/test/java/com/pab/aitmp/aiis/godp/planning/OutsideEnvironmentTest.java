package com.pab.aitmp.aiis.godp.planning;

import static org.assertj.core.api.Assertions.assertThat;
import com.pab.aitmp.aiis.godp.planning.server.dev.PlanningDevelopmentApplication;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.ApplicationContext;

/** Default outside profile activates the existing local shell without requiring a database. */
@SpringBootTest(classes=PlanningDevelopmentApplication.class,
    webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties="planning.local-pulse.enabled=false")
class OutsideEnvironmentTest {
  @Autowired ApplicationContext context;
  @Autowired TestRestTemplate http;
  @Test void outsideUsesLocalAdaptersAndReportsTheCanonicalName(){
    assertThat(http.getForObject("/api/plan/service-health",String.class))
        .contains("\"environment\":\"outside\"","\"legacy_enabled\":false");
    assertThat(http.getForEntity("/api/plan/not-a-business-endpoint",String.class).getStatusCodeValue()).isEqualTo(404);
  }
}
