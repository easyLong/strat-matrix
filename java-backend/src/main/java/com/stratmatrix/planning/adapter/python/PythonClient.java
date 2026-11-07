package com.stratmatrix.planning.adapter.python;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.stratmatrix.planning.context.RequestContexts;
import com.stratmatrix.planning.manual.BusinessException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.springframework.http.*;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.*;

/** Shared HTTP/auth/error boundary. The host supplies its approved RestTemplate. */
public final class PythonClient {
  private final URI base;
  private final String token;
  private final RestTemplate http;

  public PythonClient(URI base, String token, RestTemplate http) {
    if (base == null
        || !java.util.Arrays.asList("http", "https").contains(base.getScheme())
        || base.getHost() == null
        || base.getUserInfo() != null
        || base.getQuery() != null
        || base.getFragment() != null) throw new IllegalArgumentException("Python服务地址无效");
    this.base = base;
    if (token != null && (token.contains("\r") || token.contains("\n") || token.indexOf('\0') >= 0))
      throw new IllegalArgumentException("内部令牌必须为单行");
    this.token = token;
    this.http = java.util.Objects.requireNonNull(http, "planning Python HTTP client");
  }

  public static RestTemplate boundedHttp(int connectMs, int readMs) {
    if (connectMs < 1 || readMs < 1) throw new IllegalArgumentException("HTTP超时必须大于0");
    SimpleClientHttpRequestFactory f =
        new SimpleClientHttpRequestFactory() {
          @Override
          protected void prepareConnection(java.net.HttpURLConnection c, String method)
              throws java.io.IOException {
            super.prepareConnection(c, method);
            c.setInstanceFollowRedirects(false);
          }
        };
    f.setConnectTimeout(connectMs);
    f.setReadTimeout(readMs);
    return new RestTemplate(f);
  }

  public boolean isConfigured() {
    return token != null && !token.trim().isEmpty();
  }

  public Map<String, Object> call(HttpMethod method, String path, Object body) {
    return call(method, path, body, null, 0);
  }

  @SuppressWarnings("unchecked")
  public Map<String, Object> call(
      HttpMethod method, String path, Object body, String actor, int expectedStatus) {
    if (!isConfigured()) throw new IllegalStateException("Python内部执行令牌尚未配置");
    if (path == null
        || !path.startsWith("/api/")
        || path.contains("..")
        || path.contains("%")
        || path.contains("?")
        || path.contains("#")
        || path.contains("\\")
        || path.contains("//")) throw new IllegalArgumentException("Python能力路径无效");
    HttpHeaders headers = new HttpHeaders();
    headers.setContentType(MediaType.APPLICATION_JSON);
    headers.set("X-Integration-Token", token);
    RequestContexts.current()
        .ifPresent(context -> headers.set(RequestContexts.TRACE_HEADER, context.traceId));
    if (actor != null) {
      if (actor.trim().isEmpty()
          || actor.length() > 64
          || actor.contains("\r")
          || actor.contains("\n")) throw new IllegalArgumentException("操作人无效");
      headers.set("X-Operator-Id", actor);
    }
    try {
      URI uri = URI.create(base.toString().replaceAll("/+$", "") + path);
      ResponseEntity<Map> response =
          http.exchange(uri, method, new HttpEntity<>(body, headers), Map.class);
      if (!response.getStatusCode().is2xxSuccessful())
        throw remote(response.getStatusCode(), response.getBody(), response.getHeaders());
      if (expectedStatus > 0 && response.getStatusCodeValue() != expectedStatus)
        throw new BusinessException(502, "Python能力受理状态不符合契约");
      if (response.getBody() == null) throw new BusinessException(502, "Python能力返回为空");
      return response.getBody();
    } catch (HttpStatusCodeException failure) {
      Map detail = null;
      try {
        detail = new ObjectMapper().readValue(failure.getResponseBodyAsByteArray(), Map.class);
      } catch (Exception ignored) {
      }
      throw remote(failure.getStatusCode(), detail, failure.getResponseHeaders());
    } catch (ResourceAccessException unavailable) {
      throw new BusinessException(503, "算法服务暂不可用，请稍后重试");
    } catch (RestClientException invalid) {
      throw new BusinessException(502, "算法服务返回格式不符合契约");
    }
  }

  private RuntimeException remote(HttpStatus status, Map<?, ?> body, HttpHeaders upstream) {
    String message =
        body != null && body.get("detail") instanceof String
            ? (String) body.get("detail")
            : "算法服务请求失败";
    if (message.length() > 500) message = "算法服务请求失败";
    byte[] safe;
    try {
      safe =
          new ObjectMapper()
              .writeValueAsBytes(java.util.Collections.singletonMap("detail", message));
    } catch (Exception ignored) {
      safe = new byte[0];
    }
    // Configuration recovery relies on distinguishing 409/422. Never retain upstream headers/dumps.
    HttpHeaders safeHeaders = new HttpHeaders();
    if (status == HttpStatus.TOO_MANY_REQUESTS) {
      String value = upstream == null ? null : upstream.getFirst(HttpHeaders.RETRY_AFTER);
      int seconds = value != null && value.matches("[0-9]{1,3}") ? Integer.parseInt(value) : 2;
      safeHeaders.set(HttpHeaders.RETRY_AFTER, Integer.toString(Math.max(1, Math.min(120, seconds))));
      safeHeaders.setCacheControl("no-store");
    }
    if (status.is4xxClientError())
      return HttpClientErrorException.create(
          status, message, safeHeaders, safe, StandardCharsets.UTF_8);
    return new BusinessException(502, "算法服务暂不可用，请稍后重试");
  }
}
