package com.stratmatrix.planning.source;

import static com.stratmatrix.planning.manual.Json.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.stratmatrix.planning.adapter.local.*;
import com.stratmatrix.planning.adapter.python.CatalogProjectionPythonClient;
import com.stratmatrix.planning.manual.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class UnifiedSourceTest {
  @TempDir Path directory;

  private FixtureSourceFacts facts() throws Exception {
    Path file = directory.resolve("facts.json");
    Files.write(
        file,
        write(
                map(
                    "accounts",
                    Arrays.asList(
                        map(
                            "data",
                            map(
                                "account_id",
                                "A2",
                                "eligible",
                                true,
                                "updated_at",
                                "2026-11-03T08:00:00Z")),
                        map(
                            "data",
                            map(
                                "account_id",
                                "A1",
                                "eligible",
                                true,
                                "updated_at",
                                "2026-11-03T16:00:00+08:00")),
                        map(
                            "data",
                            map(
                                "account_id",
                                "A3",
                                "eligible",
                                false,
                                "updated_at",
                                "2026-11-03T08:00:00Z"))),
                    "topics",
                    Arrays.asList(
                        map(
                            "topic_id",
                            "T1",
                            "source",
                            "普通",
                            "topic_type",
                            "非营销",
                            "available",
                            true,
                            "updated_at",
                            "2026-11-03T08:00:00Z",
                            "valid_to",
                            "2026-11-03T12:00:00Z"),
                        map(
                            "topic_id",
                            "T2",
                            "source",
                            "热点",
                            "topic_type",
                            "非营销",
                            "available",
                            true,
                            "updated_at",
                            "2026-11-03T08:00:00Z"))))
            .getBytes(StandardCharsets.UTF_8));
    return new FixtureSourceFacts(file);
  }

  @Test
  void stablePagingQualificationAndHalfOpenTimeRangeMatchPythonContract() throws Exception {
    FixtureSourceFacts f = facts();
    Map<String, Object> q = map("页码", 1, "每页条数", 1);
    assertEquals(2, number(f.accounts(q), "total"));
    assertEquals("A1", rows(f.accounts(q).get("items")).get(0).get("account_id"));
    q.put("页码", 2);
    assertEquals("A2", rows(f.accounts(q).get("items")).get(0).get("account_id"));
    assertEquals(0, number(f.accounts(map("更新结束时间", "2026-11-03T08:00:00Z")), "total"));
    assertEquals(2, number(f.accounts(map("更新开始时间", "2026-11-03T08:00:00Z")), "total"));
    assertEquals(0, number(f.accounts(map("account_ids", Collections.emptyList())), "total"));
    assertThrows(BusinessException.class, () -> f.accounts(map("page_size", 501)));
    assertThrows(
        BusinessException.class,
        () -> new FixtureSourceFacts(directory.resolve("missing")).accounts(map()));
  }

  @Test
  void topicFiltersUseSameSourceTypeAndValiditySemantics() throws Exception {
    FixtureSourceFacts f = facts();
    assertEquals(1, number(f.topics(map("选题来源", "热点", "选题类型", "非营销")), "total"));
    assertEquals(1, number(f.topics(map("有效时点", "2026-11-03T12:00:01Z")), "total"));
    assertEquals(2, number(f.topics(map("有效时点", "2026-11-03T12:00:00Z")), "total"));
  }

  @Test
  void facadeRequiresTokenAndDoesNotDependOnPythonForRawFacts() throws Exception {
    MockMvc mvc =
        MockMvcBuilders.standaloneSetup(
                new SourceFactsController(facts(), mock(ManualRepository.class), "test-token"))
            .setControllerAdvice(new com.stratmatrix.planning.api.PlanningApiErrors())
            .build();
    mvc.perform(
            post("/api/plan/internal/source/accounts/query")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
        .andExpect(status().isUnauthorized());
    mvc.perform(
            post("/api/plan/internal/source/accounts/query")
                .header("X-Integration-Token", "test-token")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
        .andExpect(status().isOk());
    mvc.perform(
            post("/api/plan/internal/source/no-such-capability/query")
                .header("X-Integration-Token", "test-token")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
        .andExpect(status().isNotFound());
  }

  @Test
  void manualSourcePassesJavaFactsToAlgorithmInsteadOfReadingPythonCatalog() throws Exception {
    org.springframework.web.client.RestTemplate http =
        new org.springframework.web.client.RestTemplate();
    org.springframework.test.web.client.MockRestServiceServer server =
        org.springframework.test.web.client.MockRestServiceServer.createServer(http);
    server
        .expect(
            org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo(
                "http://localhost:6930/api/internal/catalog-projection"))
        .andExpect(
            request -> {
              String body =
                  ((org.springframework.mock.http.client.MockClientHttpRequest) request)
                      .getBodyAsString();
              assertTrue(body.contains("A1"));
              assertFalse(body.contains("A2"));
            })
        .andRespond(
            org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess(
                "{\"accounts\":[{\"account_id\":\"A1\"}],\"topics\":[],\"algorithm_version\":\"v1\"}",
                MediaType.APPLICATION_JSON));
    OutsideSourceAdapter source =
        new OutsideSourceAdapter(
            facts(),
            new CatalogProjectionPythonClient(
                http, java.net.URI.create("http://localhost:6930"), "test-token"));
    assertEquals(
        "A1",
        rows(source.sourceAccounts(Collections.singletonList("A1")).get("accounts"))
            .get(0)
            .get("account_id"));
    server.verify();
  }
}
