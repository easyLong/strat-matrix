package com.pab.aitmp.aiis.godp.planning.server.controller;

import com.pab.aitmp.aiis.godp.planning.api.host.PlanningPermission;

import com.pab.aitmp.aiis.godp.planning.entity.vo.req.ConfigurationDocument;

import com.pab.aitmp.aiis.godp.planning.entity.error.BusinessException;

import com.pab.aitmp.aiis.godp.planning.client.python.PythonClient;
import com.pab.aitmp.aiis.godp.planning.api.context.RequestContexts;
import com.pab.aitmp.aiis.godp.planning.api.port.ManualPorts;
import java.util.Map;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpMethod;
import org.springframework.web.bind.annotation.*;

/** Java owns the page boundary; Python remains authoritative for taxonomy and version checks. */
@RestController
@RequestMapping("${planning.api-prefix:/api/plan}/tag-taxonomy")
@ConditionalOnProperty(name = "planning.manual.enabled", havingValue = "true")
@PlanningPermission("config.view")
public class TagTaxonomyController {
  private final PythonClient python;
  private final ManualPorts.Actor actor;

  public TagTaxonomyController(PythonClient python, ManualPorts.Actor actor) {
    this.python = python;
    this.actor = RequestContexts.actor(actor);
  }

  @GetMapping
  @PlanningPermission({"config.view","manual.view","results.view"})
  public Object read() {
    return python.call(HttpMethod.GET, "/api/tag-taxonomy", null);
  }

  @PutMapping
  @PlanningPermission("config.edit")
  public Object save(@RequestBody ConfigurationDocument body) {
    String operator = actor.current();
    if (operator == null || operator.trim().isEmpty())
      throw new com.pab.aitmp.aiis.godp.planning.entity.error.BusinessException(401, "当前操作人未登录");
    return python.call(HttpMethod.PUT, "/api/tag-taxonomy", body.values(), operator, 200);
  }

  @PostMapping("/query") @PlanningPermission({"config.view","manual.view","results.view"}) public Object query() { return read(); }
  @PostMapping("/save") @PlanningPermission("config.edit") public Object saveDocument(@RequestBody ConfigurationDocument body) { return save(body); }
}
