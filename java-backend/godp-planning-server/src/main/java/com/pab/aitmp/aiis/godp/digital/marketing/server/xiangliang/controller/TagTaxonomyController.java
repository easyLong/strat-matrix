package com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.controller;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.host.PlanningPermission;

import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.req.ConfigurationDocument;

import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.error.BusinessException;

import com.pab.aitmp.aiis.godp.digital.marketing.client.xiangliang.python.PythonClient;
import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.context.RequestContexts;
import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.ManualPorts;
import java.util.Map;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpMethod;
import org.springframework.web.bind.annotation.*;

/** Java owns the page boundary; Python remains authoritative for taxonomy and version checks. */
@RestController("xiangliangTagTaxonomyController")
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

  @PostMapping("/query")
  @PlanningPermission({"config.view","manual.view","results.view"})
  public Object read() {
    return python.call(HttpMethod.POST, "/api/tag-taxonomy/query", java.util.Collections.emptyMap());
  }

  @PostMapping("/save")
  @PlanningPermission("config.edit")
  public Object save(@RequestBody ConfigurationDocument body) {
    String operator = actor.current();
    if (operator == null || operator.trim().isEmpty())
      throw new com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.error.BusinessException(401, "当前操作人未登录");
    return python.call(HttpMethod.POST, "/api/tag-taxonomy/save", body.values(), operator, 200);
  }

}
