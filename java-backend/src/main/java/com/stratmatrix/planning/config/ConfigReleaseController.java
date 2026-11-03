package com.stratmatrix.planning.config;

import com.stratmatrix.planning.manual.*;
import java.util.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("${planning.api-prefix:/api/plan}/config")
@ConditionalOnProperty(name = "planning.config-release.enabled", havingValue = "true")
public class ConfigReleaseController {
  private final ConfigReleaseService service;
  private final ManualPorts.Actor actor;

  public ConfigReleaseController(ConfigReleaseService service, ManualPorts.Actor actor) {
    this.service = service;
    this.actor = actor;
  }

  @GetMapping
  public Object current() {
    return service.current();
  }

  @PutMapping
  public Object save(@RequestBody Map<String, Object> config, @RequestParam int expected_version) {
    return service.save(config, expected_version, actor.current());
  }

  @GetMapping("/versions")
  public Object versions(@RequestParam(defaultValue = "30") int limit) {
    return service.versions(limit);
  }

  @PostMapping("/versions/{version}/restore")
  public Object restore(@PathVariable int version, @RequestParam int expected_version) {
    return service.restore(version, expected_version, actor.current());
  }

  @ExceptionHandler(BusinessException.class)
  public ResponseEntity<?> error(BusinessException e) {
    return ResponseEntity.status(e.status).body(Collections.singletonMap("detail", e.getMessage()));
  }

  @ExceptionHandler(IllegalArgumentException.class)
  public ResponseEntity<?> invalid(IllegalArgumentException e) {
    return ResponseEntity.unprocessableEntity()
        .body(Collections.singletonMap("detail", e.getMessage()));
  }
}
