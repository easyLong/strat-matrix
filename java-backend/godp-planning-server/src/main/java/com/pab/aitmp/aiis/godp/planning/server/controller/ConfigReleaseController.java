package com.pab.aitmp.aiis.godp.planning.server.controller;

import com.pab.aitmp.aiis.godp.planning.api.host.PlanningPermission;

import com.pab.aitmp.aiis.godp.planning.entity.vo.req.ConfigSaveRequest;
import com.pab.aitmp.aiis.godp.planning.entity.vo.req.ConfigRestoreRequest;
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

  @PostMapping("/query")
  @PlanningPermission({"config.view","manual.view","results.view"})
  public Object current() {
    return service.current();
  }

  @PostMapping("/save")
  @PlanningPermission("config.edit")
  public Object save(@Valid @RequestBody ConfigSaveRequest request) {
    return service.save(request.config.values(), request.expectedVersion, actor.current());
  }

  @PostMapping("/versions/query")
  public Object versions(@Valid @RequestBody CatalogQueryRequest request) {
    return service.versions(request.limitOr(30));
  }

  @PostMapping("/versions/{version}/restore")
  @PlanningPermission("config.restore")
  public Object restore(@PathVariable int version, @Valid @RequestBody ConfigRestoreRequest request) {
    return service.restore(version, request.expectedVersion, actor.current());
  }
}
