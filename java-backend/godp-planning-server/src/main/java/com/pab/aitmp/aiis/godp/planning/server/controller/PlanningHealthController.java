package com.pab.aitmp.aiis.godp.planning.server.controller;

import com.pab.aitmp.aiis.godp.planning.entity.support.Json;

import static com.pab.aitmp.aiis.godp.planning.entity.support.Json.map;

import com.pab.aitmp.aiis.godp.planning.client.python.PythonClient;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualMapper;
import java.util.Map;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

/** Page readiness, independent of the legacy proxy and the standalone liveness endpoint. */
@RestController
@RequestMapping("${planning.api-prefix:/api/plan}")
@ConditionalOnProperty(name = "planning.manual.enabled", havingValue = "true")
public class PlanningHealthController {
  private final ManualMapper database;
  private final PythonClient python;

  public PlanningHealthController(ManualMapper database, PythonClient python) {
    this.database = database;
    this.python = python;
  }

  @GetMapping("/health")
  public ResponseEntity<?> health() {
    boolean business = false, algorithm = false;
    try {
      business = database.ping() == 1;
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
