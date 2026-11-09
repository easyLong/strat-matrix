package com.pab.aitmp.aiis.godp.planning.client.python;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import java.net.URI;
import java.time.LocalDate;
import java.util.Collections;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

class AutoSchedulePythonClientTest {
  @Test
  void sendsProtectedCycleOnlyToAlgorithmCapability() {
    RestTemplate http = new RestTemplate();
    MockRestServiceServer server = MockRestServiceServer.createServer(http);
    server
        .expect(requestTo("http://127.0.0.1:6930/api/internal/auto-planning/start"))
        .andExpect(method(HttpMethod.POST))
        .andExpect(header("X-Integration-Token", "server-token"))
        .andExpect(
            content()
                .json(
                    "{\"cycle_start\":\"2026-11-09\",\"business_config_version\":1,\"business_config\":{}}"))
        .andRespond(
            withSuccess("{\"status\":\"created\",\"pipeline_id\":88}", MediaType.APPLICATION_JSON));
    server
        .expect(requestTo("http://127.0.0.1:6930/api/internal/planning-pipelines/88/query"))
        .andExpect(method(HttpMethod.POST))
        .andExpect(content().json("{}"))
        .andExpect(header("X-Integration-Token", "server-token"))
        .andRespond(
            withSuccess(
                "{\"status\":\"succeeded\",\"production_batch_id\":77}",
                MediaType.APPLICATION_JSON));
    server
        .expect(requestTo("http://127.0.0.1:6930/api/internal/planning-pipelines/88/proposal"))
        .andExpect(method(HttpMethod.POST))
        .andExpect(header("X-Integration-Token", "server-token"))
        .andExpect(
            content()
                .json("{\"business_config_version\":2,\"business_config\":{\"hotspot_ratio\":20}}"))
        .andRespond(
            withSuccess(
                "{\"schema_version\":1,\"proposal_hash\":\"abc\"}", MediaType.APPLICATION_JSON));
    String hash = String.join("", Collections.nCopies(64, "a"));
    server
        .expect(
            requestTo("http://127.0.0.1:6930/api/internal/planning-pipelines/88/acknowledgement"))
        .andExpect(method(HttpMethod.POST))
        .andExpect(header("X-Integration-Token", "server-token"))
        .andExpect(
            content()
                .json("{\"proposal_hash\":\"" + hash + "\",\"business_batch_id\":2000000000001}"))
        .andRespond(withSuccess("{\"status\":\"accepted\"}", MediaType.APPLICATION_JSON));
    AutoSchedulePythonClient client =
        new AutoSchedulePythonClient(URI.create("http://127.0.0.1:6930"), "server-token", http);
    assertEquals(
        88,
        ((Number)
                client
                    .start(LocalDate.parse("2026-11-09"), 1, Collections.emptyMap())
                    .get("pipeline_id"))
            .intValue());
    assertEquals("succeeded", client.status(88).get("status"));
    assertEquals(
        "abc",
        client.proposal(88, 2, Collections.singletonMap("hotspot_ratio", 20)).get("proposal_hash"));
    assertEquals("accepted", client.acknowledge(88, hash, 2000000000001L).get("status"));
    server.verify();
    assertThrows(
        IllegalStateException.class,
        () ->
            new AutoSchedulePythonClient(URI.create("http://127.0.0.1:6930"), "", http)
                .start(LocalDate.parse("2026-11-09"), 1, Collections.emptyMap()));
  }
}
