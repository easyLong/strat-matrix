package com.stratmatrix.planning.content;

import static com.stratmatrix.planning.manual.Json.*;
import static org.junit.jupiter.api.Assertions.*;

import com.stratmatrix.planning.adapter.local.LocalPlanningContentAdapter;
import com.stratmatrix.planning.manual.*;
import com.stratmatrix.planning.source.SourceFacts;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.*;
import java.util.*;

/** Completes actual V19/Java results; fakes content-owned facts only. */
public final class MixedContentAcceptance {
  public static Map<String, Object> finish(
      ManualRepository repo,
      SlotCompletionMapper slots,
      SourceFacts facts,
      Path fixture,
      long batch,
      String account)
      throws Exception {
    List<Map<String, Object>> items = repo.itemsByBatch(batch);
    List<Map<String, Object>> hot = new ArrayList<>(), marketing = new ArrayList<>();
    for (Map<String, Object> row : items) {
      if ("unassigned".equals(row.get("production_status"))) hot.add(row);
      if ("awaiting_market".equals(row.get("production_status"))) marketing.add(row);
    }
    assertEquals(1, hot.size(), "Mixed acceptance must retain one real hotspot placeholder");
    assertEquals(
        1, marketing.size(), "Mixed acceptance must retain a conversion slot for marketing");
    String date = text(hot.get(0), "publish_date");
    LocalDate day = LocalDate.parse(date);
    Map<String, Object> current =
        read(new String(Files.readAllBytes(fixture), StandardCharsets.UTF_8));
    List<Map<String, Object>> own = new ArrayList<>();
    for (Map<String, Object> row : rows(current.get("topics")))
      if (write(row).contains(account)) own.add(row);
    own.add(
        map(
            "data",
            map(
                "topic_id",
                account + "-HOT",
                "source",
                "热点",
                "topic_type",
                "非营销",
                "title",
                "家庭账单新变化：先核对官方信息",
                "outline",
                "说明变化与查询步骤，不推荐产品。",
                "content_type",
                "热点解读",
                "heat",
                100,
                "available",
                true,
                "updated_at",
                Instant.now().toString(),
                "valid_from",
                day.atStartOfDay().atOffset(ZoneOffset.ofHours(8)).toString(),
                "valid_to",
                day.atTime(23, 59).atOffset(ZoneOffset.ofHours(8)).toString()),
            "local_payload",
            map()));
    ContentBranchScenario.publish(fixture, "topics", account, own);
    Instant approved =
        LocalDate.parse(text(marketing.get(0), "publish_date"))
            .minusDays(1)
            .atStartOfDay(ZoneId.of("Asia/Shanghai"))
            .toInstant();
    ContentBranchScenario.publish(
        fixture,
        "marketing_contents",
        account,
        Collections.singletonList(
            map(
                "content_id",
                "SIM-CONTENT-MARKET-" + batch,
                "account_id",
                account,
                "title",
                "已过审家庭账单服务内容",
                "body",
                "已过审的测试营销正文",
                "approved_at",
                approved.toString())));
    ManualContentStatusService progress =
        new ManualContentStatusService(repo, c -> Collections.emptyList());
    SlotCompletionService completion =
        new SlotCompletionService(slots, repo, new LocalPlanningContentAdapter(facts), progress);
    long after = items.stream().mapToLong(r -> number(r, "id")).min().getAsLong() - 1;
    assertEquals(1, number(completion.marketing(approved.plusSeconds(1), 100, after), "applied"));
    Instant cutoff = day.minusDays(1).atTime(9, 0).atZone(ZoneId.of("Asia/Shanghai")).toInstant();
    assertEquals(0, number(completion.hotspots(cutoff.minusSeconds(86400), 100, after), "applied"));
    assertEquals(1, number(completion.hotspots(cutoff, 100, after), "applied"));
    assertEquals(0, number(completion.hotspots(cutoff.plusSeconds(1), 100, after), "applied"));
    List<Map<String, Object>> completed = repo.itemsByBatch(batch);
    assertTrue(completed.stream().anyMatch(r -> (account + "-HOT").equals(r.get("topic_id"))));
    assertTrue(
        completed.stream()
            .anyMatch(r -> ("SIM-CONTENT-MARKET-" + batch).equals(r.get("content_id"))));
    return map(
        "hotspot_count",
        hot.size(),
        "marketing_count",
        marketing.size(),
        "regular_count",
        items.size() - hot.size() - marketing.size(),
        "hotspot_date",
        date,
        "hotspot_scan_at",
        cutoff.toString(),
        "model_outputs_unchanged",
        true);
  }
}
