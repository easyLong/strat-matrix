package com.stratmatrix.planning.adapter.python;

import static com.stratmatrix.planning.manual.Json.*;

import com.stratmatrix.planning.manual.BusinessException;
import java.net.URI;
import java.util.*;
import org.springframework.http.*;
import org.springframework.web.client.RestTemplate;

/**
 * Sends Java facts to Python for algorithm-owned lifecycle/labels; never asks Python to fetch
 * facts.
 */
public final class CatalogProjectionPythonClient {
  private final RestTemplate http;
  private final URI base;
  private final String token;

  public CatalogProjectionPythonClient(RestTemplate http, URI base, String token) {
    this.http = http;
    this.base = base;
    this.token = token;
  }

  public Map<String, Object> project(
      List<Map<String, Object>> accounts, List<Map<String, Object>> topics, boolean availableOnly) {
    HttpHeaders h = new HttpHeaders();
    h.setContentType(MediaType.APPLICATION_JSON);
    h.set("X-Integration-Token", token);
    Map<String, Object> body =
        map("accounts", accounts, "topics", topics, "available_only", availableOnly);
    ResponseEntity<Map> result =
        http.exchange(
            base.resolve("/api/internal/catalog-projection"),
            HttpMethod.POST,
            new HttpEntity<>(body, h),
            Map.class);
    Map response = result.getBody();
    if (!result.getStatusCode().is2xxSuccessful())
      throw new BusinessException(result.getStatusCodeValue(), "算法资料投影暂不可用，请检查算法服务与配置");
    if (response == null || !response.containsKey("algorithm_version"))
      throw new IllegalStateException("算法资料投影返回不完整");
    return object(response);
  }
}
