package com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.web;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.response.PlanningResponseAdapter;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.error.PlanningValidationException;
import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.controller.SourceFactsController;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.config.BusinessPlanningConfigService;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.config.BusinessPlanningConfigService.ConfigConflict;
import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.context.RequestContexts;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.error.BusinessException;
import java.util.*;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.dao.DataAccessException;
import org.springframework.http.*;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.*;

@org.springframework.stereotype.Component("xiangliangPlanningApiErrors")
@RestControllerAdvice(basePackages = "com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang")
public class PlanningApiErrors {
  private final PlanningResponseAdapter adapter;

  public PlanningApiErrors() {
    this(new PlanningResponseAdapter() {});
  }

  public PlanningApiErrors(PlanningResponseAdapter adapter) {
    this.adapter = Objects.requireNonNull(adapter);
  }

  @Autowired
  public PlanningApiErrors(ObjectProvider<PlanningResponseAdapter> adapters) {
    this(adapters.getIfAvailable(() -> new PlanningResponseAdapter() {}));
  }

  private ResponseEntity<?> render(int status, String code, String message) {
    String trace =
        RequestContexts.current()
            .map(context -> context.traceId)
            .orElseGet(() -> UUID.randomUUID().toString());
    PlanningResponseAdapter target = adapter;
    org.springframework.web.context.request.RequestAttributes attributes =
        org.springframework.web.context.request.RequestContextHolder.getRequestAttributes();
    if (attributes instanceof org.springframework.web.context.request.ServletRequestAttributes) {
      Object handler =
          ((org.springframework.web.context.request.ServletRequestAttributes) attributes)
              .getRequest()
              .getAttribute(
                  org.springframework.web.servlet.HandlerMapping.BEST_MATCHING_HANDLER_ATTRIBUTE);
      if (handler instanceof org.springframework.web.method.HandlerMethod
          && com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.controller.SourceFactsController.class.isAssignableFrom(
              ((org.springframework.web.method.HandlerMethod) handler).getBeanType()))
        target = new PlanningResponseAdapter() {};
    }
    ResponseEntity<?> result =
        target.error(new PlanningResponseAdapter.Failure(status, code, message, trace));
    HttpHeaders headers = new HttpHeaders();
    headers.putAll(result.getHeaders());
    headers.set(RequestContexts.TRACE_HEADER, trace);
    return ResponseEntity.status(result.getStatusCode()).headers(headers).body(result.getBody());
  }

  @ExceptionHandler(BusinessException.class)
  public ResponseEntity<?> business(BusinessException error) {
    return render(error.status, "BUSINESS_ERROR", error.getMessage());
  }

  @ExceptionHandler(ConfigConflict.class)
  public ResponseEntity<?> conflict(ConfigConflict error) {
    return render(error.status, "CONFIG_CONFLICT", error.getMessage());
  }

  @ExceptionHandler(PlanningValidationException.class)
  public ResponseEntity<?> validation(PlanningValidationException error) {
    return render(422, "VALIDATION_ERROR", error.getMessage());
  }

  @ExceptionHandler({
    MethodArgumentNotValidException.class,
    org.springframework.validation.BindException.class
  })
  public ResponseEntity<?> required(Exception error) {
    return render(422, "VALIDATION_ERROR", "请检查必填项和字段格式");
  }

  @ExceptionHandler({
    IllegalArgumentException.class,
    HttpMessageNotReadableException.class,
    MissingServletRequestParameterException.class,
    org.springframework.web.method.annotation.MethodArgumentTypeMismatchException.class
  })
  public ResponseEntity<?> invalid(Exception error) {
    return render(422, "INVALID_ARGUMENT", "请检查请求参数和字段格式");
  }

  @ExceptionHandler(javax.validation.ConstraintViolationException.class)
  public ResponseEntity<?> constraint(Exception error) {
    return render(422, "VALIDATION_ERROR", "请检查必填项和字段格式");
  }

  @ExceptionHandler(org.springframework.web.HttpRequestMethodNotSupportedException.class)
  public ResponseEntity<?> method(Exception error) {
    return render(405, "METHOD_NOT_ALLOWED", "请求方式不支持");
  }

  @ExceptionHandler(org.springframework.web.HttpMediaTypeNotSupportedException.class)
  public ResponseEntity<?> media(Exception error) {
    return render(415, "UNSUPPORTED_MEDIA_TYPE", "请求内容类型不支持");
  }

  @ExceptionHandler(DataAccessException.class)
  public ResponseEntity<?> database(DataAccessException error) {
    return render(503, "DATABASE_UNAVAILABLE", "业务数据库暂不可用");
  }

  @ExceptionHandler(ResourceAccessException.class)
  public ResponseEntity<?> unavailable(ResourceAccessException error) {
    return render(503, "UPSTREAM_UNAVAILABLE", "计算服务暂不可用，请稍后重试");
  }

  @ExceptionHandler(RestClientResponseException.class)
  public ResponseEntity<?> upstream(RestClientResponseException error) {
    if (error.getRawStatusCode() >= 500)
      return render(503, "UPSTREAM_UNAVAILABLE", "计算服务暂不可用，请稍后重试");
    String message = "算法请求校验失败";
    try {
      Object detail =
          new ObjectMapper().readValue(error.getResponseBodyAsByteArray(), Map.class).get("detail");
      if (detail instanceof String && ((String) detail).length() <= 500) message = (String) detail;
    } catch (Exception ignored) {
    }
    ResponseEntity<?> result = render(error.getRawStatusCode(), "UPSTREAM_REJECTED", message);
    if (error.getRawStatusCode() == 429) {
      String value = error.getResponseHeaders() == null ? null : error.getResponseHeaders().getFirst(HttpHeaders.RETRY_AFTER);
      int seconds = value != null && value.matches("[0-9]{1,3}") ? Integer.parseInt(value) : 2;
      HttpHeaders headers = new HttpHeaders();
      headers.putAll(result.getHeaders());
      headers.set(HttpHeaders.RETRY_AFTER, Integer.toString(Math.max(1, Math.min(120, seconds))));
      headers.setCacheControl("no-store");
      return ResponseEntity.status(result.getStatusCode()).headers(headers).body(result.getBody());
    }
    return result;
  }

  @ExceptionHandler(Exception.class)
  public ResponseEntity<?> unexpected(Exception error) {
    return render(500, "INTERNAL_ERROR", "服务处理异常，请联系管理员并提供请求追踪号");
  }
}
