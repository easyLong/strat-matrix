package com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.controller;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.host.PlanningPermission;

import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.req.BusinessConfigSaveRequest;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.req.CatalogQueryRequest;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.req.ConfigRestoreRequest;
import javax.validation.Valid;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.config.BusinessPlanningConfigService;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.context.RequestContexts;
import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.ManualPorts;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.*;

/** Business settings reads; combined releases are the single write entry when enabled. */
@RestController("xiangliangBusinessPlanningConfigController")
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

  @PostMapping("/query")
  public Object current() {
    return service.current();
  }

  @PostMapping("/save")
  @PlanningPermission("config.edit")
  public Object save(@Valid @RequestBody BusinessConfigSaveRequest request) {
    requireStandaloneWrite();
    return service.save(request.config, request.expectedVersion, actor.current());
  }

  @PostMapping("/versions/query")
  public Object versions(@Valid @RequestBody CatalogQueryRequest request) {
    return service.versions(request.limitOr(30));
  }

  @PostMapping("/versions/{version}/restore")
  @PlanningPermission("config.restore")
  public Object restore(@PathVariable int version, @Valid @RequestBody ConfigRestoreRequest request) {
    requireStandaloneWrite();
    return service.restore(version, request.expectedVersion, actor.current());
  }

  private void requireStandaloneWrite() {
    if (combinedRelease)
      throw new BusinessPlanningConfigService.ConfigConflict(409, "请通过统一配置保存入口发布配置");
  }
}
