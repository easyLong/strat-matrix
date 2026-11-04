package com.stratmatrix.planning.api;

import com.stratmatrix.planning.config.*;
import com.stratmatrix.planning.manual.ManualPlanningController;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.MethodParameter;
import org.springframework.http.*;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.servlet.mvc.method.annotation.ResponseBodyAdvice;

/** JSON page successes only; machine-source DTOs and file/stream responses stay untouched. */
@RestControllerAdvice(
    assignableTypes = {
      ManualPlanningController.class,
      ConfigReleaseController.class,
      BusinessPlanningConfigController.class,
      TagTaxonomyController.class,
      PlanningHealthController.class
    })
public class PlanningApiResponseAdvice implements ResponseBodyAdvice<Object> {
  private final PlanningResponseAdapter adapter;

  public PlanningApiResponseAdvice() {
    this(new PlanningResponseAdapter() {});
  }

  public PlanningApiResponseAdvice(PlanningResponseAdapter adapter) {
    this.adapter = java.util.Objects.requireNonNull(adapter);
  }

  @Autowired
  public PlanningApiResponseAdvice(ObjectProvider<PlanningResponseAdapter> adapters) {
    this(adapters.getIfAvailable(() -> new PlanningResponseAdapter() {}));
  }

  public boolean supports(
      MethodParameter type, Class<? extends HttpMessageConverter<?>> converter) {
    return true;
  }

  public Object beforeBodyWrite(
      Object body,
      MethodParameter type,
      MediaType media,
      Class<? extends HttpMessageConverter<?>> converter,
      org.springframework.http.server.ServerHttpRequest request,
      org.springframework.http.server.ServerHttpResponse response) {
    if (response instanceof org.springframework.http.server.ServletServerHttpResponse
        && ((org.springframework.http.server.ServletServerHttpResponse) response)
                .getServletResponse()
                .getStatus()
            >= 300) return body;
    if (body == null
        || body instanceof byte[]
        || body instanceof String
        || body instanceof org.springframework.core.io.Resource
        || body instanceof java.io.InputStream
        || body
            instanceof org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody
        || !(MediaType.APPLICATION_JSON.isCompatibleWith(media)
            || media.getSubtype().endsWith("+json"))
        || type.getContainingClass() == PlanningApiErrors.class) return body;
    return adapter.success(body);
  }
}
