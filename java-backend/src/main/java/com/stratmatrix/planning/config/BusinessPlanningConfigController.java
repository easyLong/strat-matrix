package com.stratmatrix.planning.config;

import com.stratmatrix.planning.manual.ManualPorts;
import java.util.Collections;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/** Business settings reads; combined releases are the single write entry when enabled. */
@RestController
@RequestMapping("${planning.api-prefix:/api/plan}/business-config")
@ConditionalOnProperty(name = "planning.business-config.enabled", havingValue = "true")
public class BusinessPlanningConfigController {
  private final BusinessPlanningConfigService service;
  private final ManualPorts.Actor actor;

  @Value("${planning.config-release.enabled:false}")
  private boolean combinedRelease;

  public BusinessPlanningConfigController(
      BusinessPlanningConfigService service, ManualPorts.Actor actor) {
    this.service = service;
    this.actor = actor;
  }

  @GetMapping
  public Object current() {
    return service.current();
  }

  @PutMapping
  public Object save(
      @RequestBody BusinessPlanningConfig config, @RequestParam int expected_version) {
    requireStandaloneWrite();
    return service.save(config, expected_version, actor.current());
  }

  @GetMapping("/versions")
  public Object versions(@RequestParam(defaultValue = "30") int limit) {
    return service.versions(limit);
  }

  @PostMapping("/versions/{version}/restore")
  public Object restore(@PathVariable int version, @RequestParam int expected_version) {
    requireStandaloneWrite();
    return service.restore(version, expected_version, actor.current());
  }

  private void requireStandaloneWrite() {
    if (combinedRelease)
      throw new BusinessPlanningConfigService.ConfigConflict(409, "请通过统一配置保存入口发布配置");
  }

  @ExceptionHandler(BusinessPlanningConfigService.ConfigConflict.class)
  public ResponseEntity<?> conflict(BusinessPlanningConfigService.ConfigConflict exception) {
    return ResponseEntity.status(exception.status)
        .body(Collections.singletonMap("detail", exception.getMessage()));
  }

  @ExceptionHandler(IllegalArgumentException.class)
  public ResponseEntity<?> invalid(IllegalArgumentException exception) {
    return ResponseEntity.status(HttpStatus.UNPROCESSABLE_ENTITY)
        .body(Collections.singletonMap("detail", exception.getMessage()));
  }
}
