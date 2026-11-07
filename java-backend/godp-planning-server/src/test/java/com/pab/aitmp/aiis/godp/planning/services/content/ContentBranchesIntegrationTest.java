package com.pab.aitmp.aiis.godp.planning.services.content;

import com.pab.aitmp.aiis.godp.planning.server.dev.local.*;
import com.pab.aitmp.aiis.godp.planning.services.config.*;
import com.pab.aitmp.aiis.godp.planning.services.manual.*;

import com.pab.aitmp.aiis.godp.planning.api.port.ManualPorts;
import com.pab.aitmp.aiis.godp.planning.api.port.PlanningContentPort;
import com.pab.aitmp.aiis.godp.planning.entity.error.BusinessException;
import com.pab.aitmp.aiis.godp.planning.entity.support.Json;
import com.pab.aitmp.aiis.godp.planning.entity.vo.req.BusinessPlanningConfig;
import com.pab.aitmp.aiis.godp.planning.server.dev.local.FixtureSourceFacts;
import com.pab.aitmp.aiis.godp.planning.server.dev.local.LocalPlanningContentAdapter;
import com.pab.aitmp.aiis.godp.planning.server.dev.local.OutsideSourceAdapter;
import com.pab.aitmp.aiis.godp.planning.services.manual.AccountSnapshotView;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualContentStatusService;

import static com.pab.aitmp.aiis.godp.planning.entity.support.Json.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.pab.aitmp.aiis.godp.planning.client.python.CatalogProjectionPythonClient;
import com.pab.aitmp.aiis.godp.planning.services.query.ReadDatabaseFixture;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.http.*;
import org.springframework.web.client.RestTemplate;

class ContentBranchesIntegrationTest {
  @TempDir Path directory;

  public static ManualPorts.Source catalog(FixtureSourceFacts facts) {
    RestTemplate http = mock(RestTemplate.class);
    when(http.exchange(
            any(java.net.URI.class), eq(HttpMethod.POST), any(HttpEntity.class), eq(Map.class)))
        .thenAnswer(
            call -> {
              Map<String, Object> request = object(((HttpEntity<?>) call.getArgument(2)).getBody());
              List<Map<String, Object>> accounts = new ArrayList<>(), topics = new ArrayList<>();
              for (Map<String, Object> raw : rows(request.get("accounts"))) {
                Map<String, Object> a = AccountSnapshotView.from(map("source_payload", raw));
                a.put("lifecycle_stage", "冷启动期");
                accounts.add(a);
              }
              for (Map<String, Object> raw : rows(request.get("topics")))
                topics.add(
                    map(
                        "topic_id",
                        raw.get("topic_id"),
                        "topic_title",
                        raw.get("title"),
                        "outline",
                        raw.get("outline"),
                        "is_marketing",
                        "营销".equals(raw.get("topic_type")),
                        "valid_from",
                        raw.get("valid_from"),
                        "valid_to",
                        raw.get("valid_to")));
              return ResponseEntity.ok(
                  map(
                      "accounts",
                      accounts,
                      "topics",
                      topics,
                      "algorithm_version",
                      "isolated-projection-stub"));
            });
    return new OutsideSourceAdapter(
        facts,
        new CatalogProjectionPythonClient(
            http, java.net.URI.create("http://localhost:1"), "test-token"));
  }

  @Test
  void completeContentBranchesThroughProductionMappersAndFixtureProviders() throws Exception {
    ReadDatabaseFixture db = new ReadDatabaseFixture();
    BusinessPlanningConfig config = new BusinessPlanningConfig();
    config.planning_days = Arrays.asList(1, 3, 5);
    config.marketing_max = 3;
    config.hotspot_ratio = 20;
    config.schedule_day = 2;
    config.schedule_time = "22:00";
    db.business.save(config, 0, "test");
    Path file = directory.resolve("facts.json");
    Files.write(file, "{\"accounts\":[],\"topics\":[]}".getBytes(StandardCharsets.UTF_8));
    String prefix = "E2E-BRANCH-UNIT";
    LocalDate cycle = LocalDate.of(2030, 1, 7);
    ContentBranchScenario.prepare(file, prefix, cycle);
    FixtureSourceFacts facts = new FixtureSourceFacts(file);
    Map<String, Object> report =
        new ContentBranchScenario(
                db.repo, db.slots, facts, catalog(facts), file, prefix, cycle, 9001)
            .run(db.business);
    assertEquals("passed", report.get("status"));
    assertEquals(5, rows(report.get("auto_items")).size());
    assertEquals(2, rows(report.get("manual_items")).size());
  }

  @Test
  void missingFallbackRollsBackAndUnavailableHotspotsCannotFill() throws Exception {
    ReadDatabaseFixture db = new ReadDatabaseFixture();
    db.batch(1, "auto", "2030-01-07");
    db.item(1, "A", "2030-01-09", "unassigned", "hotspot", "");
    Map<String, Object> current = db.repo.itemsByBatch(1).get(0);
    long id = number(current, "id");
    Map<String, Object> payload = read(text(db.repo.lockedItem(id), "payload"));
    payload.remove("hotspot_fallback");
    db.repo.updateItemVersion(id, write(payload), 1);
    PlanningContentPort source = mock(PlanningContentPort.class);
    when(source.hotspots(any())).thenReturn(Collections.emptyList());
    SlotCompletionService service =
        new SlotCompletionService(
            db.slots,
            db.repo,
            source,
            new ManualContentStatusService(db.repo, c -> Collections.emptyList()));
    assertEquals(
        409,
        assertThrows(
                BusinessException.class,
                () -> service.hotspots(Instant.parse("2030-01-08T14:00:00Z"), 100, 0))
            .status);
    assertEquals("unassigned", db.repo.lockedItem(id).get("content_status"));
    assertTrue(db.repo.adjustments(id).isEmpty());
  }

  @Test
  void manualMarketingRejectsNonCertifiedAllocationWithoutWritingResults() throws Exception {
    ReadDatabaseFixture db = new ReadDatabaseFixture();
    BusinessPlanningConfig config = new BusinessPlanningConfig();
    config.planning_days = Arrays.asList(1, 3, 5);
    config.schedule_day = 2;
    config.schedule_time = "22:00";
    config.marketing_max = 3;
    config.hotspot_ratio = 20;
    db.business.save(config, 0, "test");
    Path file = directory.resolve("invalid-facts.json");
    Files.write(file, "{\"accounts\":[],\"topics\":[]}".getBytes(StandardCharsets.UTF_8));
    String prefix = "E2E-INVALID";
    ContentBranchScenario.prepare(file, prefix, LocalDate.of(2030, 1, 7));
    db.repo.saveMarketingTask(
        map(
            "taskCode",
            "BAD-DEMAND",
            "requestId",
            UUID.randomUUID().toString(),
            "requestHash",
            "a",
            "taskName",
            "bad allocation",
            "topicId",
            prefix + "-MARKETING",
            "allocationCount",
            1,
            "topicSnapshot",
            "{}",
            "createdBy",
            "test",
            "createdAt",
            1));
    ContentBranchScenario.publish(
        file,
        "marketing_allocations",
        prefix,
        Collections.singletonList(
            map(
                "task_code",
                "BAD-DEMAND",
                "account_id",
                prefix + "-B",
                "content_id",
                prefix + "-BAD-C",
                "title",
                "test",
                "body",
                "body",
                "approved_at",
                "2030-01-06T08:00:00Z")));
    MarketingPlacementService service =
        new MarketingPlacementService(
            db.repo,
            new LocalPlanningContentAdapter(new FixtureSourceFacts(file)),
            db.slots,
            db.business);
    assertEquals(
        502,
        assertThrows(
                BusinessException.class,
                () -> service.reconcile(Instant.parse("2030-01-07T02:00:00Z"), 100))
            .status);
    assertNull(db.repo.marketingByCode("BAD-DEMAND").get("batch_id"));
    assertEquals(0, number(db.repo.marketingByCode("BAD-DEMAND"), "linked_count"));
  }
}
