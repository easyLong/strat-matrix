package com.stratmatrix.planning.adapter.python;

import static com.stratmatrix.planning.manual.Json.*;

import com.stratmatrix.planning.config.AlgorithmConfigPort;
import java.net.URI;
import java.util.Map;
import org.springframework.http.*;
import org.springframework.web.client.RestTemplate;

public final class AlgorithmConfigPythonClient implements AlgorithmConfigPort {
  private final URI base;
  private final String token;
  private final RestTemplate http;

  public AlgorithmConfigPythonClient(URI base, String token, RestTemplate http) {
    this.base = base;
    this.token = token;
    this.http = http;
  }

  @SuppressWarnings("unchecked")
  private Map<String, Object> call(HttpMethod method, String path, Object body) {
    if (token == null || token.trim().isEmpty()) throw new IllegalStateException("内部令牌未配置");
    HttpHeaders h = new HttpHeaders();
    h.setContentType(MediaType.APPLICATION_JSON);
    h.set("X-Integration-Token", token);
    Map<String, Object> result =
        http.exchange(base.resolve(path), method, new HttpEntity<>(body, h), Map.class).getBody();
    if (result == null) throw new IllegalStateException("算法配置无响应");
    return result;
  }

  public Map<String, Object> current() {
    return call(HttpMethod.GET, "/api/internal/algorithm-config", null);
  }

  public Map<String, Object> apply(
      String id, int expected, Map<String, Object> config, String actor) {
    return call(
        HttpMethod.POST,
        "/api/internal/algorithm-config/commands",
        map(
            "command_id",
            id,
            "expected_version",
            expected,
            "algorithm_config",
            config,
            "actor",
            actor));
  }
}
