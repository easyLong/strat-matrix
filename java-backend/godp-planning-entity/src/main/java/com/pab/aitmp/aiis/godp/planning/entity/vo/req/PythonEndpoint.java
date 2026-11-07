package com.pab.aitmp.aiis.godp.planning.entity.vo.req;

import java.net.URI;
import java.util.Arrays;

/** Immutable service configuration snapshot. Never serialize or log the token. */
public final class PythonEndpoint {
  public final URI baseUrl;
  private final String token;
  public PythonEndpoint(URI baseUrl, String token) {
    if (baseUrl == null || !Arrays.asList("http", "https").contains(baseUrl.getScheme())
        || baseUrl.getHost() == null || baseUrl.getUserInfo() != null
        || baseUrl.getQuery() != null || baseUrl.getFragment() != null)
      throw new IllegalArgumentException("Python服务地址无效");
    if (token != null && (token.contains("\r") || token.contains("\n") || token.indexOf('\0') >= 0))
      throw new IllegalArgumentException("内部令牌必须为单行");
    this.baseUrl=baseUrl; this.token=token;
  }
  public boolean configured() { return token != null && !token.trim().isEmpty(); }
  public String token() { return token; }
}
