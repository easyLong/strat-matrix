package com.pab.aitmp.aiis.godp.planning.server.controller;

import com.pab.aitmp.aiis.godp.planning.api.host.PlanningPermission;

import com.pab.aitmp.aiis.godp.planning.entity.vo.req.BusinessPlanningConfig;
import com.pab.aitmp.aiis.godp.planning.services.config.BusinessPlanningConfigService;

import com.pab.aitmp.aiis.godp.planning.api.context.RequestContexts;
import com.pab.aitmp.aiis.godp.planning.api.port.ManualPorts;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.*;

/** Business settings reads; combined releases are the single write entry when enabled. */
@RestController
@RequestMapping("${planning.api-prefix:/api/plan}/business-config")
@ConditionalOnProperty(name = "planning.business-config.enabled", havingValue = "true")
@PlanningPermission("config.view")
public class BusinessPlanningConfigController {
  private final BusinessPlanningConfigService service;
  private final ManualPorts.Actor actor;

  @Value("${planning.config-release.enabled:false}")
  private boolean combinedRelease;

  public BusinessPlanningConfigController(
      BusinessPlanningConfigService service, ManualPorts.Actor actor) {
    this.service = service;
    this.actor = RequestContexts.actor(actor);
  }

  @GetMapping
  public Object current() {
    return service.current();
  }

  @PutMapping
  @PlanningPermission("config.edit")
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
  @PlanningPermission("config.restore")
  public Object restore(@PathVariable int version, @RequestParam int expected_version) {
    requireStandaloneWrite();
    return service.restore(version, expected_version, actor.current());
  }

  private void requireStandaloneWrite() {
    if (combinedRelease)
      throw new BusinessPlanningConfigService.ConfigConflict(409, "请通过统一配置保存入口发布配置");
  }
}
