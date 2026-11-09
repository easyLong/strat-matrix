package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual;

import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json;

import static com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json.*;
import static org.junit.jupiter.api.Assertions.*;

import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.dev.PlanningDevelopmentApplication;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.core.io.ClassPathResource;
import org.springframework.http.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/** Opt-in real HTTP test against a separately started Python API, Java uses isolated H2. */
@EnabledIfSystemProperty(named = "manual.live", matches = "true")
@SpringBootTest(
    classes = PlanningDevelopmentApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
      "spring.profiles.active=local",
      "planning.manual.enabled=true",
      "planning.local-pulse.enabled=false",
      "debug=false"
    })
class ManualHttpAcceptanceTest {
  static final String URL =
      "jdbc:h2:mem:manual-http;MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1";

  @DynamicPropertySource
  static void properties(DynamicPropertyRegistry registry) throws Exception {
    Properties p = new Properties();
    try (InputStream in = Files.newInputStream(Paths.get("../run/java-backend.properties"))) {
      p.load(in);
    }
    registry.add("planning.legacy.base-url", () -> "http://127.0.0.1:6932");
    registry.add(
        "planning.legacy.integration-token",
        () -> p.getProperty("planning.legacy.integration-token"));
    registry.add("planning.manual.jdbc-url", () -> URL);
    registry.add("planning.manual.username", () -> "sa");
    registry.add("planning.manual.password", () -> "");
    DriverManagerDataSource ds = new DriverManagerDataSource(URL, "sa", "");
    ResourceDatabasePopulator init =
        new ResourceDatabasePopulator(new ClassPathResource("db/manual-business.sql"));
    init.setSqlScriptEncoding("UTF-8");
    init.execute(ds);
    JdbcTemplate db = new JdbcTemplate(ds);
    db.execute("ALTER TABLE godp_manual_task ALTER COLUMN id RESTART WITH 1000000000000");
    db.execute("ALTER TABLE godp_planning_item ALTER COLUMN id RESTART WITH 1000000000000");
  }

  @Autowired TestRestTemplate http;
  @Autowired ManualPlanningService service;
  @Autowired ManualRepository repository;

  @Test
  void vueContractThroughJavaToPythonAndBack() throws Exception {
    Map<String, Object> input =
        map(
            "task_name",
            "JAVA-HTTP-ACCEPTANCE",
            "content_mode",
            "non_marketing",
            "publish_date",
            "2026-11-23",
            "account_ids",
            Arrays.asList("E2E-ORD-ACCOUNT-001"),
            "target_count",
            1,
            "topic_ids",
            Arrays.asList("E2E-ORD-TOPIC-001"),
            "note",
            "");
    ResponseEntity<Map> preview =
        http.postForEntity("/api/plan/manual-plans/previews", input, Map.class);
    assertEquals(201, preview.getStatusCodeValue(), write(preview.getBody()));
    String code = text(preview.getBody(), "preview_id");
    ResponseEntity<Map> receipt =
        http.postForEntity("/api/plan/manual-plans/previews/" + code + "/submit", null, Map.class);
    assertEquals(202, receipt.getStatusCodeValue(), write(receipt.getBody()));
    long id = number(receipt.getBody(), "id");
    assertTrue(repository.batches().isEmpty());
    for (int i = 0; i < 30; i++) {
      service.advance();
      if (!repository.batches().isEmpty()) break;
      Thread.sleep(200);
    }
    assertEquals(1, repository.batches().size(), write(repository.tasks()));
    ResponseEntity<Map> detail =
        http.postForEntity(
            "/api/plan/query/plans",
            map("mode", "batch", "batch_id", id, "filters", map()),
            Map.class);
    assertEquals(200, detail.getStatusCodeValue(), write(detail.getBody()));
    assertEquals(1, rows(detail.getBody().get("items")).size());
    Map<String, Object> item = rows(detail.getBody().get("items")).get(0);
    assertEquals("E2E-ORD-TOPIC-001", item.get("topic_id"));
    assertTrue(Boolean.TRUE.equals(item.get("allow_replace")));
    ResponseEntity<Map> tasks =
        http.postForEntity(
            "/api/plan/query/manual-tasks",
            map("page", 1, "page_size", 20, "filters", map("batch", "JAVA-HTTP-ACCEPTANCE")),
            Map.class);
    assertEquals(200, tasks.getStatusCodeValue(), write(tasks.getBody()));
    assertEquals(1L, number(tasks.getBody(), "total"));
    assertEquals(id, number(rows(tasks.getBody().get("items")).get(0), "batch_id"));
    assertEquals(200, http.postForEntity("/api/plan/batches/" + id + "/query", map(), Map.class).getStatusCodeValue());
    assertEquals(
        200,
        http.postForEntity("/api/plan/query/period-context", map("batch_id", id), List.class)
            .getStatusCodeValue());
    assertEquals(
        200,
        http.postForEntity(
                "/api/plan/query/accounts",
                map("filters", map("keyword", "E2E-ORD-ACCOUNT-001")),
                Map.class)
            .getStatusCodeValue());
    ResponseEntity<String> csv =
        http.postForEntity(
            "/api/plan/query/export", map("mode", "batch", "batch_id", id), String.class);
    assertEquals(200, csv.getStatusCodeValue());
    assertTrue(csv.getBody().contains("E2E-ORD-TOPIC-001"));
    assertEquals(1, repository.items().size());
  }
}
