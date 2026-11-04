package com.stratmatrix.planning.config;

import com.stratmatrix.planning.context.RequestContexts;
import com.stratmatrix.planning.manual.*;
import java.util.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("${planning.api-prefix:/api/plan}/config")
@ConditionalOnProperty(name = "planning.config-release.enabled", havingValue = "true")
public class ConfigReleaseController {
  private final ConfigReleaseService service;
  private final ManualPorts.Actor actor;

  public ConfigReleaseController(ConfigReleaseService service, ManualPorts.Actor actor) {
    this.service = service;
    this.actor = RequestContexts.actor(actor);
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
}
