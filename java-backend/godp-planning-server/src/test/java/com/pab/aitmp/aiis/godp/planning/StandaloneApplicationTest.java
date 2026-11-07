package com.pab.aitmp.aiis.godp.planning;

import com.pab.aitmp.aiis.godp.planning.server.dev.PlanningDevelopmentApplication;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.ApplicationContext;
import com.pab.aitmp.aiis.godp.planning.server.dev.LocalJobPulse;
import static org.assertj.core.api.Assertions.assertThat;

/** 不依赖数据库、Python或行内包即可启动Java开发壳。 */
@SpringBootTest(classes = PlanningDevelopmentApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.profiles.active=host-test")
class StandaloneApplicationTest {
    @Autowired private TestRestTemplate http;
    @Autowired private ApplicationContext context;

    @Test
    void startsWithoutLegacyAdapterAndDoesNotExposeOldBusinessRoutes() {
        assertThat(context.getBeansOfType(LocalJobPulse.class)).isEmpty();
        assertThat(http.getForObject("/api/plan/service-health", String.class))
                .contains("strat-matrix-java", "\"legacy_enabled\":false");
        assertThat(http.getForEntity("/api/plan/config", String.class).getStatusCodeValue()).isEqualTo(404);
    }
}
