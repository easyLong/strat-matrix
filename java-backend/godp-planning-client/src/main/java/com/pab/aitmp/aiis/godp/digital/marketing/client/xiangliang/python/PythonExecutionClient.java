package com.pab.aitmp.aiis.godp.digital.marketing.client.xiangliang.python;

import java.net.URI;
import java.util.*;
import org.springframework.http.HttpMethod;
import org.springframework.web.client.RestTemplate;

/** Host execution signals: acceptance is not business completion. */
public class PythonExecutionClient {
  private final PythonClient python;
  private static final List<String> JOBS =
      Arrays.asList("manual", "planning", "weekly", "hotspot", "manual_compute");

  public PythonExecutionClient(PythonClient python) {
    this.python = python;
  }

  public PythonExecutionClient(URI base, String token, RestTemplate http) {
    this(new PythonClient(base, token, http));
  }

  public boolean isConfigured() {
    return python.isConfigured();
  }

  public void wakeup(List<String> jobs) {
    if (jobs == null
        || jobs.isEmpty()
        || jobs.size() > JOBS.size()
        || !JOBS.containsAll(jobs)
        || new HashSet<>(jobs).size() != jobs.size())
      throw new IllegalArgumentException("未知后台执行类型");
    Map<String, Object> receipt =
        python.call(
            HttpMethod.POST,
            "/api/internal/wakeup",
            Collections.singletonMap("jobs", jobs),
            null,
            202);
    if (!"accepted".equals(receipt.get("status")))
      throw new IllegalStateException("Python未确认执行信号受理");
    List<Object> acknowledged = new ArrayList<>();
    for (String field : Arrays.asList("accepted_jobs", "coalesced_jobs")) {
      Object value = receipt.get(field);
      if (!(value instanceof List)) throw new IllegalStateException("Python受理结果字段不完整");
      acknowledged.addAll((List<?>) value);
    }
    if (!acknowledged.containsAll(jobs)) throw new IllegalStateException("Python未确认全部执行类型");
  }
}
