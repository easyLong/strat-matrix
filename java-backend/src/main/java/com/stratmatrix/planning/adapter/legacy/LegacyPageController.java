package com.stratmatrix.planning.adapter.legacy;

import java.io.IOException;
import java.net.SocketTimeoutException;
import java.net.URI;
import java.util.Arrays;
import java.util.List;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpMethod;
import org.springframework.util.StreamUtils;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestTemplate;

/** 仅用于行外迁移期。已迁入Java的接口应从此白名单移除并新增真实业务入口。 */
@RestController
@Profile("local")
@ConditionalOnProperty(name = "planning.legacy.enabled", havingValue = "true")
public class LegacyPageController {
  private static final List<String> REQUEST_HEADERS =
      Arrays.asList("Accept", "Content-Type", "If-Match", "If-None-Match");
  private static final List<String> RESPONSE_HEADERS =
      Arrays.asList(
          "Content-Type",
          "Content-Disposition",
          "Cache-Control",
          "ETag",
          "Last-Modified",
          "Retry-After");
  private final RestTemplate client;
  private final LegacyPythonProperties properties;

  @Value("${planning.history.mode:legacy}")
  private String historyMode;

  @Value("${planning.config-release.enabled:false}")
  private boolean configRelease;

  public LegacyPageController(
      @Qualifier("legacyPythonHttp") RestTemplate client, LegacyPythonProperties properties) {
    this.client = client;
    this.properties = properties;
  }

  @RequestMapping("/api/plan/**")
  public void forward(HttpServletRequest request, HttpServletResponse response) throws IOException {
    String path = request.getRequestURI().substring(request.getContextPath().length());
    String suffix = path.substring(PageRoutes.PREFIX.length());
    if ("business_only".equals(historyMode)
        && suffix.matches(
            "/(items|planning-accounts|planning-cycles|auto-planning/cycles)(/.*)?")) {
      error(response, 410, "历史联合查询已停用，请使用业务库分页查询入口");
      return;
    }
    if (configRelease && suffix.startsWith("/config/modules/")) {
      error(response, 410, "请使用统一配置与历史配置入口");
      return;
    }
    if (!PageRoutes.allows(request.getMethod(), path)) {
      error(response, 404, "页面接口不存在或尚未开放");
      return;
    }
    String query = request.getQueryString();
    URI target =
        URI.create(
            properties.baseUri()
                + PageRoutes.pythonPath(path)
                + (query == null ? "" : "?" + query));
    try {
      client.execute(
          target,
          HttpMethod.valueOf(request.getMethod()),
          outgoing -> {
            for (String header : REQUEST_HEADERS) {
              if (request.getHeader(header) != null)
                outgoing.getHeaders().set(header, request.getHeader(header));
            }
            // Never trust browser-supplied integration tokens or operator headers.
            if (!properties.getIntegrationToken().isEmpty()) {
              outgoing.getHeaders().set("X-Integration-Token", properties.getIntegrationToken());
              outgoing.getHeaders().set("X-Operator-Id", properties.getOperatorId());
            }
            if ("POST".equals(request.getMethod()) || "PUT".equals(request.getMethod())) {
              StreamUtils.copy(request.getInputStream(), outgoing.getBody());
            }
          },
          incoming -> {
            response.setStatus(incoming.getRawStatusCode());
            for (String header : RESPONSE_HEADERS) {
              if (incoming.getHeaders().getFirst(header) != null)
                response.setHeader(header, incoming.getHeaders().getFirst(header));
            }
            StreamUtils.copy(incoming.getBody(), response.getOutputStream());
            return null;
          });
    } catch (ResourceAccessException failure) {
      if (response.isCommitted()) throw failure;
      boolean timeout = failure.getMostSpecificCause() instanceof SocketTimeoutException;
      error(response, timeout ? 504 : 502, timeout ? "Python服务响应超时" : "Python服务暂不可用");
    }
  }

  private void error(HttpServletResponse response, int status, String detail) throws IOException {
    response.reset();
    response.setStatus(status);
    response.setContentType("application/json;charset=UTF-8");
    response.getWriter().write("{\"detail\":\"" + detail + "\"}");
  }
}
