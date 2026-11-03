package com.stratmatrix.planning.adapter.python;

import java.net.URI;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestTemplate;

/** 服务端专用唤醒客户端，供宿主Job调用，不经页面通配入口开放。 */
public class PythonExecutionClient {
    private final URI baseUri;
    private final String token;
    private final RestTemplate http;
    private static final List<String> JOBS = Arrays.asList("manual", "planning", "weekly", "hotspot");

    public PythonExecutionClient(URI baseUri, String token, RestTemplate http) {
        this.baseUri = baseUri;
        this.token = token;
        this.http = http;
    }

    public boolean isConfigured() { return token != null && !token.trim().isEmpty(); }

    public void wakeup(List<String> jobs) {
        if (!isConfigured()) throw new IllegalStateException("Python内部执行令牌尚未配置");
        if (jobs.isEmpty() || jobs.size() > 4 || !JOBS.containsAll(jobs)) {
            throw new IllegalArgumentException("未知后台执行类型");
        }
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.set("X-Integration-Token", token);
        ResponseEntity<Map<String, Object>> response = http.exchange(
                baseUri.resolve("/api/internal/wakeup"), HttpMethod.POST,
                new HttpEntity<>(Collections.singletonMap("jobs", jobs), headers),
                new ParameterizedTypeReference<Map<String, Object>>() { });
        Map<String, Object> receipt = response.getBody();
        if (response.getStatusCodeValue() != 202 || receipt == null || !"accepted".equals(receipt.get("status"))) {
            throw new IllegalStateException("Python未确认执行信号受理");
        }
        List<Object> acknowledged = new ArrayList<>();
        for (String field : Arrays.asList("accepted_jobs", "coalesced_jobs")) {
            Object value = receipt.get(field);
            if (!(value instanceof List)) throw new IllegalStateException("Python受理结果字段不完整");
            acknowledged.addAll((List<?>) value);
        }
        if (!acknowledged.containsAll(jobs)) throw new IllegalStateException("Python未确认全部执行类型");
    }
}
