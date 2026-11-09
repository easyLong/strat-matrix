package com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.config;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;
import com.pab.aitmp.aiis.godp.digital.marketing.client.xiangliang.config.AtomicPythonSettings;
import com.pab.aitmp.aiis.godp.digital.marketing.client.xiangliang.python.PythonClient;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.req.PythonEndpoint;
import java.net.URI;
import org.junit.jupiter.api.Test;
import org.springframework.http.*;
import org.springframework.web.client.RestTemplate;
import org.springframework.test.web.client.MockRestServiceServer;

class PythonRuntimeSettingsTest {
  @Test void hostCanAtomicallyChangeEndpointAndCredentialWithoutRebuildingServices() {
    RestTemplate http=new RestTemplate();
    MockRestServiceServer server=MockRestServiceServer.createServer(http);
    server.expect(requestTo("http://first.example/api/health")).andExpect(header("X-Integration-Token","test-first"))
        .andRespond(withSuccess("{\"database\":\"ok\"}",MediaType.APPLICATION_JSON));
    server.expect(requestTo("http://second.example/api/health")).andExpect(header("X-Integration-Token","test-second"))
        .andRespond(withSuccess("{\"database\":\"ok\"}",MediaType.APPLICATION_JSON));
    AtomicPythonSettings settings=new AtomicPythonSettings(new PythonEndpoint(URI.create("http://first.example"),"test-first"));
    PythonClient client=new PythonClient(settings,http);
    client.call(HttpMethod.GET,"/api/health",null);
    settings.replace(new PythonEndpoint(URI.create("http://second.example"),"test-second"));
    client.call(HttpMethod.GET,"/api/health",null);
    server.verify();
    assertThrows(IllegalArgumentException.class,() -> new PythonEndpoint(URI.create("file:///tmp/x"),"secret"));
  }
}
