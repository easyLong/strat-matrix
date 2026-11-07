package com.pab.aitmp.aiis.godp.planning.client.python;

import com.pab.aitmp.aiis.godp.planning.entity.support.Json;

import static com.pab.aitmp.aiis.godp.planning.entity.support.Json.map;

import java.net.URI;
import java.util.*;
import org.springframework.http.HttpMethod;
import org.springframework.web.client.RestTemplate;

public final class CatalogProjectionPythonClient {
  private final PythonClient python;

  public CatalogProjectionPythonClient(PythonClient python) {
    this.python = python;
  }

  public CatalogProjectionPythonClient(RestTemplate http, URI base, String token) {
    this(new PythonClient(base, token, http));
  }

  public Map<String, Object> project(
      List<Map<String, Object>> accounts, List<Map<String, Object>> topics, boolean availableOnly) {
    Map<String, Object> result =
        python.call(
            HttpMethod.POST,
            "/api/internal/catalog-projection",
            map("accounts", accounts, "topics", topics, "available_only", availableOnly));
    if (!result.containsKey("algorithm_version")) throw new IllegalStateException("算法资料投影返回不完整");
    return result;
  }
}
