package com.stratmatrix.planning.api;

import com.stratmatrix.planning.manual.Json;
import org.springframework.http.ResponseEntity;

/** Optional host response binding. Default keeps the existing Vue/Java wire contract. */
public interface PlanningResponseAdapter {
  default Object success(Object body) {
    return body;
  }

  default ResponseEntity<?> error(Failure failure) {
    return ResponseEntity.status(failure.status).body(Json.map("detail", failure.message));
  }

  final class Failure {
    public final int status;
    public final String code, message, traceId;

    public Failure(int status, String code, String message, String traceId) {
      this.status = status;
      this.code = code;
      this.message = message;
      this.traceId = traceId;
    }
  }
}
