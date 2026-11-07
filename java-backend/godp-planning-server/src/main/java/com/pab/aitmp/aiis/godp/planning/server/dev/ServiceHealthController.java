package com.pab.aitmp.aiis.godp.planning.server.dev;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/** Development shell health endpoint; the host keeps its own health checks. */
@RestController
public class ServiceHealthController {
  private final Environment environment;

  public ServiceHealthController(Environment environment) {
    this.environment = environment;
  }

  @GetMapping("/api/plan/service-health")
  public Map<String, Object> health() {
    Map<String, Object> result = new LinkedHashMap<>();
    result.put("service", "strat-matrix-java");
    result.put("status", "UP");
    result.put("environment", environment.getProperty("planning.environment", "host"));
    boolean manual = environment.getProperty("planning.manual.enabled", Boolean.class, false);
    result.put("migration_stage", manual ? "business-services" : "development-shell");
    result.put("manual_business_enabled", manual);
    result.put(
        "local_scheduler_enabled",
        environment.getProperty("planning.local-pulse.enabled", Boolean.class, false));
    result.put("result_query_mode", environment.getProperty("planning.history.mode", "legacy"));
    result.put(
        "combined_config_enabled",
        environment.getProperty("planning.config-release.enabled", Boolean.class, false));
    result.put(
        "legacy_enabled",
        false);
    return result;
  }
}
