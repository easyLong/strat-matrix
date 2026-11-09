package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.source.bank;

import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.source.*;

import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json;
import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.controller.SourceFactsController;
import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.web.PlanningApiErrors;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.source.SourceCatalogAdapter;

import static com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.mock;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.pab.aitmp.aiis.godp.digital.marketing.client.xiangliang.python.CatalogProjectionPythonClient;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.ManualRepository;
import java.net.URI;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.mock.http.client.MockClientHttpRequest;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.client.RestTemplate;

class BankSourceIntegrationTest {
  private MockMvc controller(BankSourceQueries queries) {
    return MockMvcBuilders.standaloneSetup(
            new SourceFactsController(
                new BankSourceFacts(queries), mock(ManualRepository.class), "test-token"))
        .setControllerAdvice(new com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.web.PlanningApiErrors())
        .build();
  }

  private MockHttpServletRequestBuilder query(String capability, String body) {
    return post("/api/plan/internal/source/" + capability + "/query")
        .contentType(MediaType.APPLICATION_JSON)
        .content(body);
  }

  @Test
  void internalHttpFacadeEnforcesIdentityAndExposesActionableContractErrors() throws Exception {
    BankSourceFactsTest.Reader reader = new BankSourceFactsTest.Reader();
    MockMvc mvc = controller(reader);
    mvc.perform(query("accounts", "{}")).andExpect(status().isUnauthorized());
    assertEquals(0, reader.calls.get());
    mvc.perform(
            query("accounts", "{\"page_size\":501}").header("X-Integration-Token", "test-token"))
        .andExpect(status().isUnprocessableEntity());
    mvc.perform(query("accounts", "{}").header("X-Integration-Token", "test-token"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.total").value(1))
        .andExpect(jsonPath("$.items[0].nickname").value("契约测试账号"))
        .andExpect(jsonPath("$.items[0].private_column").doesNotExist());
    reader.accountRows.get(0).put("可参与策划", false);
    mvc.perform(query("accounts", "{}").header("X-Integration-Token", "test-token"))
        .andExpect(status().isBadGateway());
    controller(new BankSourceQueries() {})
        .perform(query("accounts", "{}").header("X-Integration-Token", "test-token"))
        .andExpect(status().isServiceUnavailable())
        .andExpect(jsonPath("$.detail").exists());
    controller(
            new BankSourceQueries() {
              public BankSourceContracts.PageRows accounts(BankSourceContracts.Accounts q) {
                throw new IllegalStateException("private service configuration");
              }
            })
        .perform(query("accounts", "{}").header("X-Integration-Token", "test-token"))
        .andExpect(status().isServiceUnavailable())
        .andExpect(jsonPath("$.detail").value("行内资料查询暂不可用，请检查资料接入配置"));
  }

  @Test
  void bankFactsAreProjectedByExistingPythonCapabilityWithoutLeakingSourceColumns() {
    RestTemplate http = new RestTemplate();
    MockRestServiceServer server = MockRestServiceServer.createServer(http);
    BankSourceFacts facts = new BankSourceFacts(new BankSourceFactsTest.Reader());
    server
        .expect(requestTo("http://algorithm/api/internal/catalog-projection"))
        .andExpect(header("X-Integration-Token", "test-token"))
        .andExpect(
            request -> {
              Map<String, Object> body = read(((MockClientHttpRequest) request).getBodyAsString());
              Map<String, Object> account = rows(body.get("accounts")).get(0);
              assertEquals("A1", account.get("account_id"));
              assertEquals("UM001", account.get("owner_um"));
              assertFalse(account.containsKey("private_column"));
              assertFalse(account.containsKey("lifecycle_stage"));
              assertEquals("T1", rows(body.get("topics")).get(0).get("topic_id"));
            })
        .andRespond(
            withSuccess(
                write(
                    map(
                        "algorithm_version",
                        "v19",
                        "accounts",
                        Collections.singletonList(
                            map("account_id", "A1", "lifecycle_stage", "流量增长期")),
                        "topics",
                        Collections.singletonList(map("topic_id", "T1")))),
                MediaType.APPLICATION_JSON));
    SourceCatalogAdapter source =
        new SourceCatalogAdapter(
            facts,
            new CatalogProjectionPythonClient(http, URI.create("http://algorithm"), "test-token"));
    Map<String, Object> result =
        source.snapshot(Collections.singletonList("A1"), Collections.singletonList("T1"));
    assertEquals("流量增长期", rows(result.get("accounts")).get(0).get("lifecycle_stage"));
    server.verify();
  }
}
