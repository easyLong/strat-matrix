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
    assertEquals(0, Json.number(bridge.queryPage("plans", Json.map()), "total"));
    assertThrows(IllegalArgumentException.class,
        () -> bridge.queryPage("internal-admin", Json.map()));
    server.verify();
  }

}
