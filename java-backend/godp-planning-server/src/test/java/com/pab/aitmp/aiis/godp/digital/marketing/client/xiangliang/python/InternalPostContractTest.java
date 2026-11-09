package com.pab.aitmp.aiis.godp.digital.marketing.client.xiangliang.python;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.req.ConfigurationDocument;
import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.controller.TagTaxonomyController;
import java.net.URI;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

class InternalPostContractTest {
  @Test
  void configurationAndTaxonomyUseProtectedPostWithTrustedActor() throws Exception {
    RestTemplate http = new RestTemplate();
    MockRestServiceServer server = MockRestServiceServer.createServer(http);
    server.expect(requestTo("http://python.test/api/internal/algorithm-config/query"))
        .andExpect(method(HttpMethod.POST)).andExpect(header("X-Integration-Token", "test-token"))
        .andExpect(content().json("{}"))
        .andRespond(withSuccess("{\"version\":3}", MediaType.APPLICATION_JSON));
    server.expect(requestTo("http://python.test/api/tag-taxonomy/query"))
        .andExpect(method(HttpMethod.POST)).andExpect(header("X-Integration-Token", "test-token"))
        .andExpect(content().json("{}"))
        .andRespond(withSuccess("{\"version\":2}", MediaType.APPLICATION_JSON));
    server.expect(requestTo("http://python.test/api/tag-taxonomy/save"))
        .andExpect(method(HttpMethod.POST)).andExpect(header("X-Integration-Token", "test-token"))
        .andExpect(header("X-Operator-Id", "HOST-UM"))
        .andExpect(content().json("{\"expected_version\":2,\"items\":{}}"))
        .andRespond(withSuccess("{\"version\":3}", MediaType.APPLICATION_JSON));
    PythonClient client = new PythonClient(URI.create("http://python.test"), "test-token", http);
    assertEquals(3, new AlgorithmConfigPythonClient(client).current().get("version"));
    TagTaxonomyController taxonomy = new TagTaxonomyController(client, () -> "HOST-UM");
    taxonomy.read();
    taxonomy.save(new ConfigurationDocument(new ObjectMapper().readTree(
        "{\"expected_version\":2,\"items\":{}}")));
    server.verify();
  }
}
