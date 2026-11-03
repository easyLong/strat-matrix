package com.stratmatrix.planning.adapter.local;

import static com.stratmatrix.planning.manual.Json.*;

import com.stratmatrix.planning.adapter.legacy.LegacyPythonProperties;
import com.stratmatrix.planning.manual.BusinessException;
import com.stratmatrix.planning.manual.ManualPorts;
import java.net.URI;
import java.util.*;
import org.springframework.http.*;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestTemplate;

/**
 * Local bridge for source facts, algorithm calls and old-business transition methods. Onsite
 * replaces these ports with bank Java queries and approved internal algorithm calls.
 */
public class LocalPythonAdapter
    implements ManualPorts.Source, ManualPorts.Computer, ManualPorts.Transition {
  private final RestTemplate http;
  private final LegacyPythonProperties config;
  private final RestTemplate computeHttp;
  private final boolean historyEnabled;

  public LocalPythonAdapter(RestTemplate http, LegacyPythonProperties config) {
    this(http, config, true);
  }

  public LocalPythonAdapter(
      RestTemplate http, LegacyPythonProperties config, boolean historyEnabled) {
    this.http = http;
    this.config = config;
    this.historyEnabled = historyEnabled;
    SimpleClientHttpRequestFactory factory =
        new SimpleClientHttpRequestFactory() {
          @Override
          protected void prepareConnection(java.net.HttpURLConnection c, String method)
              throws java.io.IOException {
            super.prepareConnection(c, method);
            c.setInstanceFollowRedirects(false);
          }
        };
    factory.setConnectTimeout(1000);
    factory.setReadTimeout(3000);
    RestTemplate bounded = new RestTemplate(factory);
    bounded.setErrorHandler(http.getErrorHandler());
    this.computeHttp = bounded;
  }

  public Object call(String method, String path, Object body) {
    return exchange(http, method, path, body);
  }

  public Map<String, Object> queryPage(String view, Map<String, Object> query) {
    if (!Arrays.asList("manual-tasks", "plans", "accounts", "periods").contains(view))
      throw new IllegalArgumentException("未知过渡查询视图");
    return object(call("POST", "/api/query/" + view, query));
  }

  public Map<String, Object> sourceAccounts(List<String> accountIds) {
    return object(
        call(
            "POST",
            "/api/internal/manual-source",
            map("account_ids", accountIds, "topic_ids", Collections.emptyList())));
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

  public List<Map<String, Object>> topicCandidates(int limit) {
    return rows(call("GET", "/api/topics?limit=" + limit, null));
  }

  public List<Map<String, Object>> accountOptions(int limit, boolean includeDisabled) {
    return rows(
        call("GET", "/api/accounts?limit=" + limit + "&include_disabled=" + includeDisabled, null));
  }

  public Map<String, Object> topicDetail(String topicId, String topicType) {
    try {
      String id = java.net.URLEncoder.encode(topicId, "UTF-8").replace("+", "%20");
      String suffix =
          topicType == null || topicType.isEmpty()
              ? ""
              : "?topic_type=" + java.net.URLEncoder.encode(topicType, "UTF-8").replace("+", "%20");
      return object(call("GET", "/api/topics/" + id + "/detail" + suffix, null));
    } catch (java.io.UnsupportedEncodingException impossible) {
      throw new IllegalStateException(impossible);
    }
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

  public Map<String, Object> snapshot(List<String> accounts, List<String> topics) {
    return object(
        call(
            "POST",
            "/api/internal/manual-source",
            map("account_ids", accounts, "topic_ids", topics)));
  }

  @SuppressWarnings("unchecked")
  public Set<String> historicalPlanned(String date) {
    if (!historyEnabled) return Collections.emptySet();
    Map<String, Object> response =
        object(call("GET", "/api/manual-plans/account-availability?publish_date=" + date, null));
    return new HashSet<>((List<String>) response.get("planned_account_ids"));
  }

  public Map<String, Object> submit(Map<String, Object> input) {
    return object(exchange(computeHttp, "POST", "/api/internal/manual-computations", input));
  }

  @SuppressWarnings("unchecked")
  public Set<String> historicalReserved(String date) {
    if (!historyEnabled) return Collections.emptySet();
    Map<String, Object> response =
        object(call("GET", "/api/internal/manual-source/availability?publish_date=" + date, null));
    return new HashSet<>((List<String>) response.get("blocked_account_ids"));
  }
}
