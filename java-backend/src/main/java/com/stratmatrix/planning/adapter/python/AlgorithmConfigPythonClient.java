package com.stratmatrix.planning.adapter.python;

import static com.stratmatrix.planning.manual.Json.map;

import com.stratmatrix.planning.config.AlgorithmConfigPort;
import java.net.URI;
import java.util.Map;
import org.springframework.http.HttpMethod;
import org.springframework.web.client.RestTemplate;

public final class AlgorithmConfigPythonClient implements AlgorithmConfigPort {
  private final PythonClient python;

  public AlgorithmConfigPythonClient(PythonClient python) {
    this.python = python;
  }

  public AlgorithmConfigPythonClient(URI base, String token, RestTemplate http) {
    this(new PythonClient(base, token, http));
  }

  public Map<String, Object> current() {
    return python.call(HttpMethod.GET, "/api/internal/algorithm-config", null);
  }

  public Map<String, Object> apply(
      String id, int expected, Map<String, Object> config, String actor) {
    return python.call(
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
