package com.stratmatrix.planning.adapter.python;

import com.stratmatrix.planning.manual.ManualPorts;
import java.util.Map;
import org.springframework.http.HttpMethod;

/** Idempotent accept/read over frozen inputs; no business-table writes. */
public final class ManualComputePythonClient implements ManualPorts.Computer {
  private final PythonClient python;

  public ManualComputePythonClient(PythonClient python) {
    this.python = python;
  }

  public Map<String, Object> submit(Map<String, Object> input) {
    try {
      return python.call(HttpMethod.POST, "/api/internal/manual-computations", input, null, 202);
    } catch (org.springframework.web.client.HttpClientErrorException invalid) {
      throw new com.stratmatrix.planning.manual.BusinessException(
          invalid.getRawStatusCode(), invalid.getStatusText());
    }
  }
}
