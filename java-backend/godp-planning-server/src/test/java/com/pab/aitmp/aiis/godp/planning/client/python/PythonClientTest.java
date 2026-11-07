package com.pab.aitmp.aiis.godp.planning.client.python;

import com.pab.aitmp.aiis.godp.planning.api.context.*;

import com.pab.aitmp.aiis.godp.planning.api.context.RequestContexts;
import com.pab.aitmp.aiis.godp.planning.entity.context.PlanningRequestContext;
import com.pab.aitmp.aiis.godp.planning.server.web.PlanningApiErrors;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

import com.pab.aitmp.aiis.godp.planning.entity.error.BusinessException;
import java.net.URI;
import java.util.Collections;
import org.junit.jupiter.api.Test;
import org.springframework.http.*;
import org.springframework.test.web.client.*;
import org.springframework.web.client.*;

class PythonClientTest {
  @Test
  void propagatesOnlyTrustedRequestTraceAndDoesNotRetainItAcrossCalls() {
    RestTemplate http = new RestTemplate();
    MockRestServiceServer server = MockRestServiceServer.createServer(http);
    server
        .expect(requestTo("http://python.test/api/health"))
        .andExpect(header("X-Request-Id", "trusted-trace"))
        .andExpect(headerDoesNotExist("X-Organization-Codes"))
        .andRespond(withSuccess("{}", MediaType.APPLICATION_JSON));
    server
        .expect(requestTo("http://python.test/api/health"))
        .andExpect(headerDoesNotExist("X-Request-Id"))
        .andRespond(withSuccess("{}", MediaType.APPLICATION_JSON));
    PythonClient client = new PythonClient(URI.create("http://python.test"), "token", http);
    try (RequestContexts.Scope ignored =
        RequestContexts.open(
            new PlanningRequestContext(
                "UM1",
                PlanningRequestContext.Scope.ORGANIZATIONS,
                Collections.singleton("ORG2"),
                "trusted-trace"))) {
      client.call(HttpMethod.GET, "/api/health", null);
    }
    client.call(HttpMethod.GET, "/api/health", null);
    server.verify();
  }

  @Test
  void preservesContextPathAndTrustedIdentityWithoutLeakingHeaders() {
    RestTemplate http = new RestTemplate();
    MockRestServiceServer server = MockRestServiceServer.createServer(http);
    HttpHeaders privateHeaders = new HttpHeaders();
    privateHeaders.add("X-Private", "secret");
    server
        .expect(requestTo("http://python.test/engine/api/tag-taxonomy"))
        .andExpect(header("X-Integration-Token", "server-token"))
        .andExpect(header("X-Operator-Id", "HOST-UM"))
        .andRespond(
            withStatus(HttpStatus.CONFLICT)
                .headers(privateHeaders)
                .contentType(MediaType.APPLICATION_JSON)
                .body("{\"detail\":\"stale version\"}"));
    PythonClient client =
        new PythonClient(URI.create("http://python.test/engine/"), "server-token", http);
    HttpClientErrorException error =
        assertThrows(
            HttpClientErrorException.class,
            () ->
                client.call(
                    HttpMethod.PUT, "/api/tag-taxonomy", Collections.emptyMap(), "HOST-UM", 200));
    assertEquals(409, error.getRawStatusCode());
    assertEquals("stale version", error.getStatusText());
    assertFalse(error.getResponseHeaders().containsKey("X-Private"));
    server.verify();
    assertThrows(
        IllegalArgumentException.class, () -> client.call(HttpMethod.GET, "/api/../secret", null));
    assertThrows(
        IllegalArgumentException.class,
        () -> client.call(HttpMethod.PUT, "/api/tag-taxonomy", null, "bad\r\nactor", 200));
  }

  @Test
  void badResponseTimeoutAndUnavailableHaveSafeStableSemantics() {
    for (HttpStatus status : new HttpStatus[] {HttpStatus.FOUND, HttpStatus.SERVICE_UNAVAILABLE}) {
      RestTemplate http = new RestTemplate();
      MockRestServiceServer server = MockRestServiceServer.createServer(http);
      server
          .expect(anything())
          .andRespond(withStatus(status).contentType(MediaType.APPLICATION_JSON).body("{}"));
      assertEquals(
          502,
          assertThrows(
                  BusinessException.class,
                  () ->
                      new PythonClient(URI.create("http://python.test"), "token", http)
                          .call(HttpMethod.GET, "/api/health", null))
              .status);
    }
    RestTemplate http = new RestTemplate();
    MockRestServiceServer server = MockRestServiceServer.createServer(http);
    server
        .expect(anything())
        .andRespond(
            request -> {
              throw new java.net.SocketTimeoutException("private endpoint/secret");
            });
    BusinessException error =
        assertThrows(
            BusinessException.class,
            () ->
                new PythonClient(URI.create("http://python.test"), "token", http)
                    .call(HttpMethod.GET, "/api/health", null));
    assertEquals(503, error.status);
    assertFalse(error.getMessage().contains("secret"));
  }

  @Test
  void capacityRejectionSurvivesJavaWithOnlySafeRetryHeaders() {
    RestTemplate http = new RestTemplate();
    MockRestServiceServer server = MockRestServiceServer.createServer(http);
    HttpHeaders headers = new HttpHeaders();
    headers.set("Retry-After", "999");
    headers.set("X-Private", "secret");
    server.expect(anything()).andRespond(withStatus(HttpStatus.TOO_MANY_REQUESTS)
        .headers(headers).contentType(MediaType.APPLICATION_JSON).body("{\"detail\":\"模型服务繁忙\"}"));
    PythonClient client = new PythonClient(URI.create("http://python.test"), "token", http);
    HttpClientErrorException error = assertThrows(HttpClientErrorException.class,
        () -> client.call(HttpMethod.POST, "/api/internal/topic-label-model", Collections.emptyMap()));
    assertEquals(429, error.getRawStatusCode());
    assertEquals("120", error.getResponseHeaders().getFirst("Retry-After"));
    assertFalse(error.getResponseHeaders().containsKey("X-Private"));
    ResponseEntity<?> response = new com.pab.aitmp.aiis.godp.planning.server.web.PlanningApiErrors().upstream(error);
    assertEquals(429, response.getStatusCodeValue());
    assertEquals("120", response.getHeaders().getFirst("Retry-After"));
    server.verify();
  }

  @Test
  void manualUsesSameClientAndRequiresAcceptance() {
    RestTemplate http = new RestTemplate();
    MockRestServiceServer server = MockRestServiceServer.createServer(http);
    server
        .expect(requestTo("http://python.test/api/internal/manual-computations"))
        .andRespond(withSuccess("{\"status\":\"pending\"}", MediaType.APPLICATION_JSON));
    ManualComputePythonClient client =
        new ManualComputePythonClient(
            new PythonClient(URI.create("http://python.test"), "token", http));
    assertEquals(
        502,
        assertThrows(BusinessException.class, () -> client.submit(Collections.emptyMap())).status);
    assertThrows(
        IllegalStateException.class,
        () ->
            new PythonClient(URI.create("http://python.test"), "", http)
                .call(HttpMethod.GET, "/api/health", null));
  }
}
