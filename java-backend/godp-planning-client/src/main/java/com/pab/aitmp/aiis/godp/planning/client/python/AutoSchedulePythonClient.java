package com.pab.aitmp.aiis.godp.planning.client.python;

import com.pab.aitmp.aiis.godp.planning.entity.support.Json;

import static com.pab.aitmp.aiis.godp.planning.entity.support.Json.map;

import com.pab.aitmp.aiis.godp.planning.api.port.AutoSchedulePort;
import java.net.URI;
import java.time.LocalDate;
import java.util.Map;
import org.springframework.http.HttpMethod;
import org.springframework.web.client.RestTemplate;

public class AutoSchedulePythonClient implements AutoSchedulePort {
  private final PythonClient python;

  public AutoSchedulePythonClient(PythonClient python) {
    this.python = python;
  }

  public AutoSchedulePythonClient(URI base, String token, RestTemplate http) {
    this(new PythonClient(base, token, http));
  }

  public Map<String, Object> start(LocalDate cycle, int version, Map<String, Object> config) {
    return python.call(
        HttpMethod.POST,
        "/api/internal/auto-planning/start",
        map(
            "cycle_start",
            cycle.toString(),
            "business_config_version",
            version,
            "business_config",
            config));
  }

  private String pipeline(long id) {
    if (id < 1) throw new IllegalArgumentException("Pipeline编号无效");
    return "/api/internal/planning-pipelines/" + id;
  }

  public Map<String, Object> status(long id) {
    return python.call(HttpMethod.POST, pipeline(id) + "/query", map());
  }

  public Map<String, Object> proposal(long id, int version, Map<String, Object> config) {
    if (version < 1 || config == null) throw new IllegalArgumentException("业务配置无效");
    return python.call(
        HttpMethod.POST,
        pipeline(id) + "/proposal",
        map("business_config_version", version, "business_config", config));
  }

  public Map<String, Object> acknowledge(long id, String hash, long batch) {
    if (batch < 1 || hash == null || !hash.matches("[a-f0-9]{64}"))
      throw new IllegalArgumentException("算法确认凭证无效");
    return python.call(
        HttpMethod.POST,
        pipeline(id) + "/acknowledgement",
        map("proposal_hash", hash, "business_batch_id", batch));
  }
}
