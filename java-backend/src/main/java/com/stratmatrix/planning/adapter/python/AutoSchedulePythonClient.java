package com.stratmatrix.planning.adapter.python;

import com.stratmatrix.planning.auto.AutoSchedulePort;
import java.net.URI;
import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.http.*;
import org.springframework.web.client.RestTemplate;

/** Local/host-replaceable adapter for the protected Python algorithm start capability. */
public class AutoSchedulePythonClient implements AutoSchedulePort {
  private final URI endpoint;
  private final String token;
  private final RestTemplate http;

  public AutoSchedulePythonClient(URI baseUri, String token, RestTemplate http) {
    this.endpoint = baseUri.resolve("/api/internal/auto-planning/start");
    this.token = token;
    this.http = http;
  }

  @SuppressWarnings("unchecked")
  public Map<String, Object> start(
      LocalDate cycleStart, int businessConfigVersion, Map<String, Object> frozenBusinessConfig) {
    if (token == null || token.trim().isEmpty()) throw new IllegalStateException("内部算法请求令牌尚未配置");
    HttpHeaders headers = new HttpHeaders();
    headers.setContentType(MediaType.APPLICATION_JSON);
    headers.set("X-Integration-Token", token);
    ResponseEntity<Map> result =
        http.exchange(
            endpoint,
            HttpMethod.POST,
            new HttpEntity<>(
                com.stratmatrix.planning.manual.Json.map(
                    "cycle_start",
                    cycleStart.toString(),
                    "business_config_version",
                    businessConfigVersion,
                    "business_config",
                    frozenBusinessConfig),
                headers),
            Map.class);
    if (!result.getStatusCode().is2xxSuccessful() || result.getBody() == null)
      throw new IllegalStateException("算法服务未受理自动策划任务");
    return (Map<String, Object>) result.getBody();
  }

  @SuppressWarnings("unchecked")
  public Map<String, Object> status(long pipelineId) {
    if (pipelineId < 1 || token == null || token.trim().isEmpty())
      throw new IllegalArgumentException("Pipeline编号或内部令牌无效");
    HttpHeaders headers = new HttpHeaders();
    headers.set("X-Integration-Token", token);
    ResponseEntity<Map> result =
        http.exchange(
            endpoint.resolve("/api/internal/planning-pipelines/" + pipelineId),
            HttpMethod.GET,
            new HttpEntity<>(headers),
            Map.class);
    if (!result.getStatusCode().is2xxSuccessful() || result.getBody() == null)
      throw new IllegalStateException("算法服务未返回Pipeline状态");
    return (Map<String, Object>) result.getBody();
  }

  @SuppressWarnings("unchecked")
  public Map<String, Object> proposal(
      long pipelineId, int businessConfigVersion, Map<String, Object> frozenBusinessConfig) {
    if (pipelineId < 1
        || businessConfigVersion < 1
        || frozenBusinessConfig == null
        || token == null
        || token.trim().isEmpty()) throw new IllegalArgumentException("Pipeline编号、业务配置或内部令牌无效");
    HttpHeaders headers = new HttpHeaders();
    headers.setContentType(MediaType.APPLICATION_JSON);
    headers.set("X-Integration-Token", token);
    Map<String, Object> body = new LinkedHashMap<>();
    body.put("business_config_version", businessConfigVersion);
    body.put("business_config", frozenBusinessConfig);
    ResponseEntity<Map> result =
        http.exchange(
            endpoint.resolve("/api/internal/planning-pipelines/" + pipelineId + "/proposal"),
            HttpMethod.POST,
            new HttpEntity<>(body, headers),
            Map.class);
    if (!result.getStatusCode().is2xxSuccessful() || result.getBody() == null)
      throw new IllegalStateException("算法服务未返回自动策划提案");
    return (Map<String, Object>) result.getBody();
  }

  @SuppressWarnings("unchecked")
  public Map<String, Object> acknowledge(
      long pipelineId, String proposalHash, long businessBatchId) {
    if (pipelineId < 1
        || businessBatchId < 1
        || proposalHash == null
        || !proposalHash.matches("[a-f0-9]{64}")
        || token == null
        || token.trim().isEmpty()) throw new IllegalArgumentException("算法确认凭证或内部令牌无效");
    HttpHeaders headers = new HttpHeaders();
    headers.setContentType(MediaType.APPLICATION_JSON);
    headers.set("X-Integration-Token", token);
    Map<String, Object> body = new LinkedHashMap<>();
    body.put("proposal_hash", proposalHash);
    body.put("business_batch_id", businessBatchId);
    ResponseEntity<Map> result =
        http.exchange(
            endpoint.resolve("/api/internal/planning-pipelines/" + pipelineId + "/acknowledgement"),
            HttpMethod.POST,
            new HttpEntity<>(body, headers),
            Map.class);
    if (!result.getStatusCode().is2xxSuccessful() || result.getBody() == null)
      throw new IllegalStateException("算法服务未确认业务落库凭证");
    return (Map<String, Object>) result.getBody();
  }
}
