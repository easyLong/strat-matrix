package com.stratmatrix.planning.adapter.local;

import static com.stratmatrix.planning.manual.Json.*;

import com.stratmatrix.planning.adapter.legacy.LegacyPythonProperties;
import com.stratmatrix.planning.manual.BusinessException;
import com.stratmatrix.planning.manual.ManualPorts;
import java.net.URI;
import java.util.*;
import org.springframework.http.*;
import org.springframework.web.client.RestTemplate;

/** Local algorithm client and old-business transition only. Raw source facts are Java-owned. */
public class LocalPythonAdapter implements ManualPorts.Transition {
  private final RestTemplate http;
  private final LegacyPythonProperties config;

  public LocalPythonAdapter(RestTemplate http, LegacyPythonProperties config) {
    this.http = http;
    this.config = config;
  }

  public Object call(String method, String path, Object body) {
    return exchange(http, method, path, body);
  }

  public Map<String, Object> queryPage(String view, Map<String, Object> query) {
    if (!Arrays.asList("manual-tasks", "plans", "accounts", "periods").contains(view))
      throw new IllegalArgumentException("未知过渡查询视图");
    return object(call("POST", "/api/query/" + view, query));
  }

  public long resultWatermark() {
    return number(
        object(call("GET", "/api/internal/manual-source/result-watermark", null)), "max_item_id");
  }

  public List<Map<String, Object>> latestOperations(List<Long> itemIds) {
    return rows(
        call("POST", "/api/internal/manual-source/latest-operations", map("item_ids", itemIds)));
  }

  public List<Map<String, Object>> periodContext(Map<String, Object> query) {
    return rows(call("POST", "/api/query/period-context", query));
  }

  public List<Map<String, Object>> batches(int limit, String planType) {
    String path =
        "/api/batches?limit=" + limit + (planType == null ? "" : "&plan_type=" + planType);
    return rows(call("GET", path, null));
  }

  public Object batch(long id) {
    return call("GET", "/api/batches/" + id, null);
  }

  public Object replaceTopic(long id, Map<String, Object> request) {
    return call("POST", "/api/items/" + id + "/replace-topic", request);
  }

  public List<Map<String, Object>> adjustments(long id) {
    return rows(call("GET", "/api/items/" + id + "/adjustments", null));
  }

  public List<Map<String, Object>> replacementCandidates(long id) {
    return rows(call("GET", "/api/items/" + id + "/replacement-candidates", null));
  }

  @Override
  public List<Map<String, Object>> marketingTasks(int limit, int offset) {
    return rows(
        call(
            "GET", "/api/manual-plans/marketing-tasks?limit=" + limit + "&offset=" + offset, null));
  }

  @Override
  public Object marketingTaskDetails(String taskCode) {
    return call("GET", "/api/manual-plans/marketing-tasks/" + taskCode, null);
  }

  private Object exchange(RestTemplate client, String method, String path, Object body) {
    HttpHeaders headers = new HttpHeaders();
    headers.setContentType(MediaType.APPLICATION_JSON);
    headers.set("X-Integration-Token", config.getIntegrationToken());
    headers.set("X-Operator-Id", config.getOperatorId());
    ResponseEntity<Object> response =
        client.exchange(
            URI.create(config.baseUri() + path),
            HttpMethod.valueOf(method),
            new HttpEntity<>(body, headers),
            Object.class);
    if (!response.getStatusCode().is2xxSuccessful()) {
      Object detail = object(response.getBody()).get("detail");
      throw new BusinessException(
          response.getStatusCodeValue(), detail instanceof String ? (String) detail : "上游返回数据校验错误");
    }
    return response.getBody();
  }
}
