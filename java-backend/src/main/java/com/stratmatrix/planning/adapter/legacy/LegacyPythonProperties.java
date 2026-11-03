package com.stratmatrix.planning.adapter.legacy;

import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

/** 迁移期旧业务适配配置，未来由独立算法客户端替代。 */
@ConfigurationProperties(prefix = "planning.legacy")
public class LegacyPythonProperties {
    private boolean enabled;
    private String baseUrl = "http://127.0.0.1:6930";
    private int connectTimeoutMs = 3000;
    private int readTimeoutMs = 30000;
    private String integrationToken = "";
    private String operatorId = "local-development";

    public URI baseUri() {
        URI uri = URI.create(baseUrl);
        if (!("http".equals(uri.getScheme()) || "https".equals(uri.getScheme()))
                || uri.getHost() == null || uri.getRawUserInfo() != null
                || uri.getRawQuery() != null || uri.getRawFragment() != null
                || !(uri.getRawPath().isEmpty() || "/".equals(uri.getRawPath()))) {
            throw new IllegalArgumentException("Python地址必须为无凭据的HTTP服务根地址");
        }
        return URI.create(baseUrl.replaceAll("/+$", ""));
    }

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean enabled) { this.enabled = enabled; }
    public String getBaseUrl() { return baseUrl; }
    public void setBaseUrl(String baseUrl) { this.baseUrl = baseUrl; }
    public int getConnectTimeoutMs() { return connectTimeoutMs; }
    public void setConnectTimeoutMs(int value) {
        if (value <= 0) throw new IllegalArgumentException("连接超时必须大于0");
        connectTimeoutMs = value;
    }
    public int getReadTimeoutMs() { return readTimeoutMs; }
    public void setReadTimeoutMs(int value) {
        if (value <= 0) throw new IllegalArgumentException("读取超时必须大于0");
        readTimeoutMs = value;
    }
    public String getIntegrationToken() { return integrationToken; }
    public void setIntegrationToken(String value) { integrationToken = singleLine(value); }
    public String getOperatorId() { return operatorId; }
    public void setOperatorId(String value) { operatorId = singleLine(value); }
    private String singleLine(String value) {
        if (value == null || value.indexOf('\r') >= 0 || value.indexOf('\n') >= 0 || value.indexOf('\0') >= 0) {
            throw new IllegalArgumentException("内部请求头配置必须为单行");
        }
        return value;
    }
}
