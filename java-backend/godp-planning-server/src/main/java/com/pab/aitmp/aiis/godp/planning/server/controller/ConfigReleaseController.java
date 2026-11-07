package com.pab.aitmp.aiis.godp.planning.server.controller;

import com.pab.aitmp.aiis.godp.planning.api.host.PlanningPermission;

import com.pab.aitmp.aiis.godp.planning.entity.vo.req.ConfigurationDocument;
import com.pab.aitmp.aiis.godp.planning.entity.vo.req.ConfigSaveRequest;
import com.pab.aitmp.aiis.godp.planning.entity.vo.req.CatalogQueryRequest;
import javax.validation.Valid;

import com.pab.aitmp.aiis.godp.planning.api.port.ManualPorts;
import com.pab.aitmp.aiis.godp.planning.services.config.ConfigReleaseService;

import com.pab.aitmp.aiis.godp.planning.api.context.RequestContexts;
import java.util.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("${planning.api-prefix:/api/plan}/config")
@ConditionalOnProperty(name = "planning.config-release.enabled", havingValue = "true")
@PlanningPermission("config.view")
public class ConfigReleaseController {
  private final ConfigReleaseService service;
  private final ManualPorts.Actor actor;

  public ConfigReleaseController(ConfigReleaseService service, ManualPorts.Actor actor) {
    this.service = service;
    this.actor = RequestContexts.actor(actor);
  }

  @GetMapping
  @PlanningPermission({"config.view","manual.view","results.view"})
  public Object current() {
    return service.current();
  }

  @PutMapping
  @PlanningPermission("config.edit")
  public Object save(@RequestBody ConfigurationDocument config, @RequestParam int expected_version) {
    return service.save(config.values(), expected_version, actor.current());
  }

  @GetMapping("/versions")
  public Object versions(@RequestParam(defaultValue = "30") int limit) {
    return service.versions(limit);
  }

  @PostMapping("/versions/{version}/restore")
  @PlanningPermission("config.restore")
  public Object restore(@PathVariable int version, @RequestParam int expected_version) {
    return service.restore(version, expected_version, actor.current());
  }

  @PostMapping("/query") @PlanningPermission({"config.view","manual.view","results.view"}) public Object queryCurrent() { return current(); }
  @PostMapping("/versions/query") public Object queryVersions(@Valid @RequestBody CatalogQueryRequest q) { return versions(q.limitOr(30)); }
  @PostMapping("/save") @PlanningPermission("config.edit") public Object saveDocument(@Valid @RequestBody ConfigSaveRequest q) { return save(q.config,q.expectedVersion); }
}
