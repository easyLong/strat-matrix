package com.stratmatrix.planning.api;

import static com.stratmatrix.planning.manual.Json.map;

import com.stratmatrix.planning.adapter.python.PythonClient;
import com.stratmatrix.planning.manual.ManualDatabase;
import java.util.Map;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

/** Page readiness, independent of the legacy proxy and the standalone liveness endpoint. */
@RestController
@RequestMapping("${planning.api-prefix:/api/plan}")
@ConditionalOnProperty(name = "planning.manual.enabled", havingValue = "true")
public class PlanningHealthController {
  private final ManualDatabase database;
  private final PythonClient python;

  public PlanningHealthController(ManualDatabase database, PythonClient python) {
    this.database = database;
    this.python = python;
  }

  @GetMapping("/health")
  public ResponseEntity<?> health() {
    boolean business = false, algorithm = false;
    try {
      business = database.mapper.ping() == 1;
    } catch (RuntimeException unavailable) {
    }
    try {
      Map<String, Object> result = python.call(HttpMethod.GET, "/api/health", null);
      algorithm = "ok".equals(result.get("database"));
    } catch (RuntimeException unavailable) {
    }
    boolean ready = business && algorithm;
    return ResponseEntity.status(ready ? 200 : 503)
        .body(
            map(
                "service",
                ready ? "ok" : "degraded",
                "database",
                business ? "ok" : "unavailable",
                "algorithm",
                algorithm ? "ok" : "unavailable",
                "detail",
                ready ? "" : "业务数据库或算法服务暂不可用"));
  }
}
