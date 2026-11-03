package com.stratmatrix.planning.adapter.local;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import com.stratmatrix.planning.adapter.legacy.LegacyPythonProperties;
import com.stratmatrix.planning.manual.Json;
import java.util.Collections;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

class LocalPythonAdapterTest {
  @Test
  void transitionMethodsOwnLegacyPathsOutsideBusinessModule() {
    RestTemplate http = new RestTemplate();
    MockRestServiceServer server = MockRestServiceServer.createServer(http);
    LegacyPythonProperties properties = new LegacyPythonProperties();
    properties.setBaseUrl("http://127.0.0.1:6930");
    LocalPythonAdapter bridge = new LocalPythonAdapter(http, properties);
    server.expect(requestTo("http://127.0.0.1:6930/api/query/plans"))
        .andRespond(withSuccess("{\"items\":[],\"total\":0}", MediaType.APPLICATION_JSON));
    server.expect(requestTo("http://127.0.0.1:6930/api/topics?limit=10"))
        .andRespond(withSuccess("[]", MediaType.APPLICATION_JSON));
    assertEquals(0, Json.number(bridge.queryPage("plans", Json.map()), "total"));
    assertEquals(Collections.emptyList(), bridge.topicCandidates(10));
    assertThrows(IllegalArgumentException.class,
        () -> bridge.queryPage("internal-admin", Json.map()));
    server.verify();
  }

  @Test
  void pageCatalogPreservesAccountScopeAndTopicType() {
    RestTemplate http = new RestTemplate();
    MockRestServiceServer server = MockRestServiceServer.createServer(http);
    LegacyPythonProperties properties = new LegacyPythonProperties();
    properties.setBaseUrl("http://127.0.0.1:6930");
    LocalPythonAdapter bridge = new LocalPythonAdapter(http, properties);
    server.expect(requestTo("http://127.0.0.1:6930/api/accounts?limit=10&include_disabled=true"))
        .andRespond(withSuccess("[{\"account_id\":\"A1\"}]", MediaType.APPLICATION_JSON));
    server.expect(requestTo("http://127.0.0.1:6930/api/topics/T1/detail?topic_type=%E8%90%A5%E9%94%80"))
        .andRespond(withSuccess("{\"topic_id\":\"T1\"}", MediaType.APPLICATION_JSON));
    assertEquals("A1", bridge.accountOptions(10, true).get(0).get("account_id"));
    assertEquals("T1", bridge.topicDetail("T1", "\u8425\u9500").get("topic_id"));
    server.verify();
  }
}
