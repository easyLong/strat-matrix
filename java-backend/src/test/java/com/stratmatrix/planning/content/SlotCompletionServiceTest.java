package com.stratmatrix.planning.content;

import static com.stratmatrix.planning.manual.Json.*;
import static org.junit.jupiter.api.Assertions.*;

import com.stratmatrix.planning.config.*;
import com.stratmatrix.planning.manual.*;
import com.stratmatrix.planning.query.ReadDatabaseFixture;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class SlotCompletionServiceTest {
  static class Facts implements PlanningContentPort {
    List<Map<String, Object>> hot = new ArrayList<>(),
        approved = new ArrayList<>(),
        demand = new ArrayList<>();

    public List<Map<String, Object>> hotspots(Instant at) {
      return hot;
    }

    public List<Map<String, Object>> approvedMarketing(String a) {
      return approved;
    }

    public List<Map<String, Object>> effectiveMarketing(String a, LocalDate d) {
      return Collections.emptyList();
    }

    public List<Map<String, Object>> approvedDemandContents(String task) {
      return demand;
    }
  }

  @Test
  void hotspotTMinusOneClaimsOnceThenUsesFrozenFallback() throws Exception {
    ReadDatabaseFixture f = new ReadDatabaseFixture();
    f.batch(1, "auto", "2026-11-02");
    f.item(1, "A", "2026-11-04", "unassigned", "hotspot", "");
    f.item(1, "B", "2026-11-04", "unassigned", "hotspot", "");
    Facts facts = new Facts();
    facts.hot.add(map("topic_id", "HOT", "title", "热点", "outline", "热点大纲", "content_type", "热点解读"));
    SlotCompletionService service =
        new SlotCompletionService(
            f.slots,
            f.repo,
            facts,
            new ManualContentStatusService(f.repo, c -> Collections.emptyList()));
    assertEquals(
        0, number(service.hotspots(Instant.parse("2026-11-02T15:59:59Z"), 100, 0), "applied"));
    assertEquals(
        2, number(service.hotspots(Instant.parse("2026-11-02T16:00:00Z"), 100, 0), "applied"));
    List<Map<String, Object>> items = f.repo.itemsByBatch(1);
    assertEquals(1, items.stream().filter(i -> "HOT".equals(i.get("topic_id"))).count());
    assertEquals(1, items.stream().filter(i -> "FALLBACK".equals(i.get("topic_id"))).count());
    assertTrue(items.stream().allMatch(i -> "planned".equals(i.get("production_status"))));
    assertEquals(
        0, number(service.hotspots(Instant.parse("2026-11-03T14:01:00Z"), 100, 0), "applied"));
  }

  @Test
  void autoMarketingReferencesEffectiveContentAndOldestApprovedWithoutGenerating()
      throws Exception {
    ReadDatabaseFixture f = new ReadDatabaseFixture();
    f.batch(1, "auto", "2026-11-02");
    f.item(1, "A", "2026-11-04", "awaiting_market", "marketing_priority", "N1");
    f.item(1, "A", "2026-11-06", "awaiting_market", "marketing_priority", "N2");
    Facts facts =
        new Facts() {
          @Override
          public List<Map<String, Object>> effectiveMarketing(String a, LocalDate d) {
            return d.toString().equals("2026-11-04")
                ? Collections.singletonList(
                    map(
                        "content_id",
                        "EXISTING",
                        "account_id",
                        a,
                        "publish_date",
                        d.toString(),
                        "title",
                        "当日有效营销",
                        "body",
                        "正文"))
                : Collections.emptyList();
          }
        };
    facts.approved.add(
        map(
            "content_id",
            "NEWER",
            "account_id",
            "A",
            "title",
            "新过审",
            "body",
            "正文",
            "approved_at",
            "2026-11-02T10:00:00+08:00"));
    facts.approved.add(
        map(
            "content_id",
            "OLDER",
            "account_id",
            "A",
            "title",
            "先过审",
            "body",
            "正文",
            "approved_at",
            "2026-11-01T10:00:00+08:00"));
    SlotCompletionService service =
        new SlotCompletionService(
            f.slots,
            f.repo,
            facts,
            new ManualContentStatusService(f.repo, c -> Collections.emptyList()));
    assertEquals(
        2, number(service.marketing(Instant.parse("2026-11-03T14:00:00Z"), 100, 0), "applied"));
    Set<String> contents = new HashSet<>();
    for (Map<String, Object> item : f.repo.itemsByBatch(1)) {
      contents.add(text(item, "content_id"));
      assertEquals("generated", item.get("production_status"));
      assertEquals(false, item.get("allow_replace"));
    }
    assertEquals(new HashSet<>(Arrays.asList("EXISTING", "OLDER")), contents);
    assertEquals(
        0, number(service.marketing(Instant.parse("2026-11-03T14:01:00Z"), 100, 0), "applied"));
  }

  @Test
  void manualMarketingAssignsPublishDatesOnlyAfterApprovalAndDoesNotDuplicate() throws Exception {
    ReadDatabaseFixture f = new ReadDatabaseFixture();
    BusinessPlanningConfig config = new BusinessPlanningConfig();
    config.planning_days = Arrays.asList(1, 3, 5);
    config.schedule_day = 2;
    config.schedule_time = "22:00";
    config.marketing_max = 3;
    config.hotspot_ratio = 20;
    f.business.save(config, 0, "UM1");
    f.repo.saveMarketingTask(
        map(
            "taskCode",
            "DEMAND-1",
            "requestId",
            UUID.randomUUID().toString(),
            "requestHash",
            "a",
            "taskName",
            "营销任务",
            "topicId",
            "M1",
            "allocationCount",
            2,
            "topicSnapshot",
            "{}",
            "createdBy",
            "UM1",
            "createdAt",
            1));
    Facts facts = new Facts();
    Map<String, Object> account =
        map("account_id", "A", "account_name", "认证账号", "account_type", "认证");
    for (int i = 1; i <= 2; i++)
      facts.demand.add(
          map(
              "content_id",
              "C" + i,
              "account_id",
              "A",
              "account_snapshot",
              account,
              "title",
              "营销" + i,
              "body",
              "正文",
              "approved_at",
              "2026-11-02T10:00:00+08:00"));
    MarketingPlacementService service =
        new MarketingPlacementService(f.repo, facts, f.slots, f.business);
    assertEquals(
        2, number(service.reconcile(Instant.parse("2026-11-03T02:00:00Z"), 100), "applied"));
    Map<String, Object> task = f.repo.marketingByCode("DEMAND-1");
    assertEquals(2, number(task, "linked_count"));
    List<Map<String, Object>> items = f.repo.itemsByBatch(number(task, "batch_id"));
    Set<String> dates = new HashSet<>();
    for (Map<String, Object> item : items) dates.add(text(item, "publish_date"));
    assertEquals(new HashSet<>(Arrays.asList("2026-11-04", "2026-11-06")), dates);
    service.reconcile(Instant.parse("2026-11-03T03:00:00Z"), 100);
    assertEquals(2, f.repo.itemsByBatch(number(task, "batch_id")).size());
  }
}
