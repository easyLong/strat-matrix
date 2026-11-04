package com.stratmatrix.planning.config;

import com.stratmatrix.planning.adapter.python.PythonClient;
import com.stratmatrix.planning.context.RequestContexts;
import com.stratmatrix.planning.manual.ManualPorts;
import java.util.Map;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpMethod;
import org.springframework.web.bind.annotation.*;

/** Java owns the page boundary; Python remains authoritative for taxonomy and version checks. */
@RestController
@RequestMapping("${planning.api-prefix:/api/plan}/tag-taxonomy")
@ConditionalOnProperty(name = "planning.manual.enabled", havingValue = "true")
public class TagTaxonomyController {
  private final PythonClient python;
  private final ManualPorts.Actor actor;

  public TagTaxonomyController(PythonClient python, ManualPorts.Actor actor) {
    this.python = python;
    this.actor = RequestContexts.actor(actor);
  }

  @GetMapping
  public Object read() {
    return python.call(HttpMethod.GET, "/api/tag-taxonomy", null);
  }

  @PutMapping
  public Object save(@RequestBody Map<String, Object> body) {
    String operator = actor.current();
    if (operator == null || operator.trim().isEmpty())
      throw new com.stratmatrix.planning.manual.BusinessException(401, "当前操作人未登录");
    return python.call(HttpMethod.PUT, "/api/tag-taxonomy", body, operator, 200);
  }
}
