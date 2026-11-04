package com.stratmatrix.planning.host;

import org.springframework.boot.context.properties.ConfigurationProperties;

/** Host configuration names; the host chooses its configuration/secret provider. */
@ConfigurationProperties("planning.python")
public class PythonProperties {
  private String baseUrl;
  private String token;

  public String getBaseUrl() {
    return baseUrl;
  }

  public void setBaseUrl(String value) {
    baseUrl = value;
  }

  public String getToken() {
    return token;
  }

  public void setToken(String value) {
    token = value;
  }
}
