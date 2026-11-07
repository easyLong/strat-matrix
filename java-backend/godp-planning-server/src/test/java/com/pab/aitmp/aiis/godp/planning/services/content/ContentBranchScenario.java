package com.pab.aitmp.aiis.godp.planning.services.content;

import com.pab.aitmp.aiis.godp.planning.server.dev.local.*;
import com.pab.aitmp.aiis.godp.planning.services.config.*;
import com.pab.aitmp.aiis.godp.planning.services.manual.*;

import com.pab.aitmp.aiis.godp.planning.api.port.ManualPorts;
import com.pab.aitmp.aiis.godp.planning.api.port.PlanningContentPort;
import com.pab.aitmp.aiis.godp.planning.entity.support.Json;
import com.pab.aitmp.aiis.godp.planning.entity.vo.req.MarketingTaskRequest;
import com.pab.aitmp.aiis.godp.planning.server.dev.local.FixtureContentObservations;
import com.pab.aitmp.aiis.godp.planning.server.dev.local.LocalPlanningContentAdapter;
import com.pab.aitmp.aiis.godp.planning.services.config.BusinessPlanningConfigService;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualContentStatusService;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualRepository;
import com.pab.aitmp.aiis.godp.planning.services.manual.MarketingTaskService;
import com.pab.aitmp.aiis.godp.planning.services.manual.TopicUsageService;

import static com.pab.aitmp.aiis.godp.planning.entity.support.Json.*;
import static org.junit.jupiter.api.Assertions.*;

import com.pab.aitmp.aiis.godp.planning.api.port.SourceFacts;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.*;
import java.util.*;

/**
 * Shared isolated/live scenario. Seeds only test formal rows; never claims to run V19 or real
 * content.
 */
public final class ContentBranchScenario {
  private final ManualRepository repo;
  private final SlotCompletionMapper slots;
  private final SourceFacts facts;
  private final ManualPorts.Source catalog;
  private final Path fixture;
  private final String prefix;
  private final LocalDate cycle;
  private final long batch;
  private final List<String> cases = new ArrayList<>();

  public ContentBranchScenario(
      ManualRepository repo,
      SlotCompletionMapper slots,
      SourceFacts facts,
      ManualPorts.Source catalog,
      Path fixture,
      String prefix,
      LocalDate cycle,
      long batch) {
    this.repo = repo;
    this.slots = slots;
    this.facts = facts;
    this.catalog = catalog;
    this.fixture = fixture;
    this.prefix = prefix;
    this.cycle = cycle;
    this.batch = batch;
  }

  public static void publish(
      Path file, String collection, String prefix, List<Map<String, Object>> own) throws Exception {
    byte[] before = Files.readAllBytes(file);
    Map<String, Object> document = read(new String(before, StandardCharsets.UTF_8));
    List<Map<String, Object>> all = new ArrayList<>();
    Set<String> taskCodes = new HashSet<>();
    if (collection.equals("marketing_results"))
      for (Map<String, Object> row : own) taskCodes.add(text(row, "task_code"));
    for (Map<String, Object> row : rows(document.get(collection)))
      if (!write(row).contains(prefix) && !taskCodes.contains(text(row, "task_code"))) all.add(row);
    all.addAll(own);
    document.put(collection, all);
    Path temp = Files.createTempFile(file.getParent(), "content-acceptance-", ".tmp");
    try {
      Files.write(temp, write(document).getBytes(StandardCharsets.UTF_8));
      if (!Arrays.equals(before, Files.readAllBytes(file)))
        throw new IllegalStateException("Source facts changed concurrently");
      Files.move(temp, file, StandardCopyOption.REPLACE_EXISTING);
    } finally {
      Files.deleteIfExists(temp);
    }
  }

  public static void prepare(Path file, String prefix, LocalDate cycle) throws Exception {
    List<Map<String, Object>> accounts = new ArrayList<>(),
        topics = new ArrayList<>(),
        marketing = new ArrayList<>(),
        placements = new ArrayList<>();
    for (String suffix : Arrays.asList("A", "B", "C", "D", "E"))
      accounts.add(
          map(
              "data",
              map(
                  "account_id",
                  prefix + "-" + suffix,
                  "nickname",
                  "营销热点验收账号" + suffix,
                  "owner_um",
                  "TESTBRANCH" + suffix,
                  "organization",
                  "测试分行/测试二级分行",
                  "platform",
                  "小红书",
                  "account_type",
                  Arrays.asList("A", "E").contains(suffix) ? "认证" : "非认证",
                  "eligible",
                  true,
                  "followers",
                  20,
                  "updated_at",
                  Instant.now().toString(),
                  "persona",
                  "家庭生活分享者",
                  "gender",
                  "女",
                  "interests",
                  Arrays.asList("家庭生活", "金融科普"),
                  "expression_style",
                  "通俗自然",
                  "interactions",
                  Collections.emptyList()),
              "local_payload",
              map()));
    for (String suffix : Arrays.asList("NORMAL", "FALLBACK", "MARKETING", "HOT", "EXPIRED")) {
      boolean hot = suffix.equals("HOT") || suffix.equals("EXPIRED");
      topics.add(
          map(
              "data",
              map(
                  "topic_id",
                  prefix + "-" + suffix,
                  "source",
                  hot ? "热点" : "普通",
                  "topic_type",
                  suffix.equals("MARKETING") ? "营销" : "非营销",
                  "title",
                  "验收选题 " + suffix,
                  "outline",
                  "测试用完整选题大纲",
                  "content_type",
                  hot ? "热点解读" : suffix.equals("MARKETING") ? "产品营销" : "金融科普",
                  "heat",
                  90,
                  "available",
                  true,
                  "updated_at",
                  Instant.now().toString(),
                  "valid_from",
                  hot
                      ? cycle
                          .plusDays(suffix.equals("HOT") ? 2 : 1)
                          .atTime(12, 0)
                          .atOffset(ZoneOffset.ofHours(8))
                          .toString()
                      : Instant.now().minusSeconds(86400).toString(),
                  "valid_to",
                  cycle
                      .plusDays(suffix.equals("EXPIRED") ? 1 : 10)
                      .atTime(23, 59)
                      .atOffset(ZoneOffset.ofHours(8))
                      .toString()),
              "local_payload",
              map()));
    }
    for (String kind : Arrays.asList("EXISTING", "OLDER", "NEWER", "E-BLOCK"))
      marketing.add(
          map(
              "content_id",
              prefix + "-" + kind,
              "account_id",
              prefix + (kind.equals("E-BLOCK") ? "-E" : "-A"),
              "title",
              "营销内容 " + kind,
              "body",
              "审核通过的测试正文",
              "approved_at",
              cycle
                  .minusDays(kind.equals("NEWER") ? 1 : 2)
                  .atTime(10, 0)
                  .atOffset(ZoneOffset.ofHours(8))
                  .toString()));
    placements.add(
        map(
            "placement_id",
            prefix + "-P-A",
            "account_id",
            prefix + "-A",
            "content_id",
            prefix + "-EXISTING",
            "publish_date",
            cycle.toString()));
    placements.add(
        map(
            "placement_id",
            prefix + "-P-E",
            "account_id",
            prefix + "-E",
            "content_id",
            prefix + "-E-BLOCK",
            "publish_date",
            cycle.toString()));
    publish(file, "accounts", prefix, accounts);
    publish(file, "topics", prefix, topics);
    publish(file, "marketing_contents", prefix, marketing);
    publish(file, "placements", prefix, placements);
  }

  private String id(String suffix) {
    return prefix + "-" + suffix;
  }

  private Map<String, Object> account(String suffix) {
    List<Map<String, Object>> rows =
        rows(catalog.sourceAccounts(Collections.singletonList(id(suffix))).get("accounts"));
    assertEquals(1, rows.size());
    return rows.get(0);
  }

  private long item(
      String label, String account, String date, String state, String type, String topic) {
    Map<String, Object> a = account(account);
    return repo.saveItem(
        batch,
        id(label),
        id(account),
        date,
        write(
            map(
                "batch_id",
                batch,
                "batch_code",
                prefix,
                "task_name",
                prefix,
                "plan_type",
                "auto",
                "cycle_start",
                cycle.toString(),
                "cycle_end",
                cycle.plusDays(6).toString(),
                "account_id",
                id(account),
                "account_name",
                a.get("account_name"),
                "account_snapshot",
                a,
                "lifecycle_stage",
                a.get("lifecycle_stage"),
                "publish_date",
                date,
                "slot_id",
                id(label),
                "slot_type",
                type,
                "topic_id",
                topic,
                "topic_title",
                "测试选题",
                "outline",
                "测试大纲",
                "content_type",
                "金融科普",
                "topic_type",
                "普通",
                "content_role",
                "转化",
                "result_version",
                1,
                "status",
                state.equals("unassigned") ? "待定题" : "待生产",
                "production_status",
                state,
                "allow_replace",
                state.equals("planned"),
                "hotspot_fallback",
                map(
                    "topic_id",
                    id("FALLBACK"),
                    "title",
                    "冻结普通兜底",
                    "outline",
                    "冻结的大纲",
                    "content_type",
                    "金融科普"))),
        state);
  }

  private List<Map<String, Object>> observations(List<Long> ids, String status, Instant time) {
    List<Map<String, Object>> out = new ArrayList<>();
    for (long item : ids) {
      Map<String, Object> current = repo.lockedItem(item), payload = read(text(current, "payload"));
      out.add(
          map(
              "slot_id",
              payload.get("slot_id"),
              "version",
              number(current, "version"),
              "status",
              status,
              "content_id",
              status.equals("已完成") ? id("CONTENT-" + item) : null,
              "production_task_id",
              id("PROD-" + item),
              "updated_at",
              time.toString(),
              "error",
              status.equals("生产失败") ? "模拟内容方临时失败" : ""));
    }
    return out;
  }

  private void contentScan(ManualContentStatusService service, long after) {
    long cursor = after;
    for (int n = 0; n < 100; n++) {
      Map<String, Object> r = service.reconcile(100, cursor);
      if (!Boolean.TRUE.equals(r.get("has_more"))) return;
      cursor = number(r, "next_after_id");
    }
    fail("Content scan did not finish");
  }

  private Map<String, Object> usage(List<String> ids) {
    return new TopicUsageService(repo).query(map("topic_ids", ids));
  }

  private void counts(List<String> ids, long count) {
    for (Map<String, Object> row : rows(usage(ids).get("topic_results")))
      assertEquals(count, number(row, "official_use_count"));
  }

  public Map<String, Object> run(BusinessPlanningConfigService rules) throws Exception {
    assertNull(repo.batchById(batch));
    Instant monday = cycle.atTime(10, 0).atZone(ZoneId.of("Asia/Shanghai")).toInstant();
    LocalDate wednesday = cycle.plusDays(2);
    repo.saveBatch(
        batch,
        write(
            map(
                "id",
                batch,
                "batch_code",
                prefix,
                "task_name",
                "营销热点衔接验收 " + prefix,
                "plan_type",
                "auto",
                "cycle_start",
                cycle.toString(),
                "cycle_end",
                cycle.plusDays(6).toString(),
                "account_count",
                4,
                "completed_count",
                4,
                "failed_count",
                0,
                "planning_status",
                "已完成",
                "status",
                "已完成",
                "content_count",
                5,
                "content_status",
                "待生产",
                "created_at",
                Instant.now().toString())),
        System.currentTimeMillis());
    long effective =
        item(
            "EFFECTIVE",
            "A",
            cycle.toString(),
            "awaiting_market",
            "marketing_priority",
            id("NORMAL"));
    long oldest =
        item(
            "OLDEST",
            "A",
            wednesday.toString(),
            "awaiting_market",
            "marketing_priority",
            id("NORMAL"));
    long regular =
        item(
            "NO-STOCK",
            "B",
            cycle.plusDays(4).toString(),
            "awaiting_market",
            "marketing_priority",
            id("NORMAL"));
    long h1 = item("HOT-1", "C", wednesday.toString(), "unassigned", "hotspot", "");
    long h2 = item("HOT-2", "D", wednesday.toString(), "unassigned", "hotspot", "");
    long after = Collections.min(Arrays.asList(effective, oldest, regular, h1, h2)) - 1;
    FixtureContentObservations observations = new FixtureContentObservations(facts);
    ManualContentStatusService content =
        new ManualContentStatusService(repo, observations::content);
    PlanningContentPort sources = new LocalPlanningContentAdapter(facts);
    SlotCompletionService completion = new SlotCompletionService(slots, repo, sources, content);
    assertEquals(3, number(completion.marketing(monday, 100, after), "applied"));
    assertEquals(
        id("EXISTING"),
        repo.itemsByBatch(batch).stream()
            .filter(r -> number(r, "id") == effective)
            .findFirst()
            .get()
            .get("content_id"));
    assertEquals(
        id("OLDER"),
        repo.itemsByBatch(batch).stream()
            .filter(r -> number(r, "id") == oldest)
            .findFirst()
            .get()
            .get("content_id"));
    assertEquals("planned", repo.lockedItem(regular).get("content_status"));
    assertEquals(0, number(completion.marketing(monday.plusSeconds(1), 100, after), "applied"));
    cases.add("自动营销：有效投放优先、最早过审优先、无库存回退、重复不引用");
    Instant cutoff = cycle.plusDays(1).atTime(9, 0).atZone(ZoneId.of("Asia/Shanghai")).toInstant();
    assertEquals(0, number(completion.hotspots(cutoff.minusSeconds(86400), 100, after), "applied"));
    assertEquals(2, number(completion.hotspots(cutoff, 100, after), "applied"));
    List<Map<String, Object>> auto = repo.itemsByBatch(batch);
    assertEquals(1, auto.stream().filter(r -> id("HOT").equals(r.get("topic_id"))).count());
    assertEquals(1, auto.stream().filter(r -> id("FALLBACK").equals(r.get("topic_id"))).count());
    assertEquals(0, number(completion.hotspots(cutoff.plusSeconds(1), 100, after), "applied"));
    cases.add("热点：每日只检查明日空槽、次日生效热点、过期排除、普通兜底、重复不补题");
    List<Long> pending = Arrays.asList(regular, h1, h2);
    List<String> used = Arrays.asList(id("NORMAL"), id("HOT"), id("FALLBACK"));
    counts(used, 0);
    contentScan(content, after);
    counts(used, 0);
    Instant stamp = cutoff.plusSeconds(10);
    publish(fixture, "production_results", prefix, observations(pending, "生产中", stamp));
    contentScan(content, after);
    counts(used, 0);
    assertEquals("ready", repo.lockedItem(regular).get("content_status"));
    publish(
        fixture,
        "production_results",
        prefix,
        observations(Collections.singletonList(regular), "生产失败", stamp.plusSeconds(1)));
    contentScan(content, after);
    assertEquals("failed", repo.lockedItem(regular).get("content_status"));
    counts(used, 0);
    publish(
        fixture, "production_results", prefix, observations(pending, "生产中", stamp.plusSeconds(2)));
    contentScan(content, after);
    assertEquals("ready", repo.lockedItem(regular).get("content_status"));
    List<Map<String, Object>> stale =
        observations(Collections.singletonList(h1), "已完成", stamp.plusSeconds(3));
    stale.get(0).put("version", 1);
    publish(fixture, "production_results", prefix, stale);
    contentScan(content, after);
    assertEquals("ready", repo.lockedItem(h1).get("content_status"));
    publish(
        fixture, "production_results", prefix, observations(pending, "已完成", stamp.plusSeconds(4)));
    contentScan(content, after);
    counts(used, 1);
    contentScan(content, after);
    counts(used, 1);
    assertTrue(
        repo.itemsByBatch(batch).stream()
            .allMatch(r -> "generated".equals(r.get("production_status"))));
    assertEquals(
        4, number(read(text(repo.batchById(batch), "payload")), "content_completed_account_count"));
    cases.add("内容：待生产→生产中→失败→重试→完成；旧版本不覆盖；重复不多计");
    MarketingTaskService demand =
        new MarketingTaskService(
            repo, catalog, () -> "OUTSIDE-ACCEPTANCE", observations::marketing);
    MarketingTaskRequest request = new MarketingTaskRequest();
    request.request_id = UUID.randomUUID();
    request.task_name = prefix + " 人工营销";
    request.topic_id = id("MARKETING");
    request.allocation_count = 2;
    Map<String, Object> created = demand.create(request);
    String task = text(created, "task_code");
    assertEquals(task, demand.create(request).get("task_code"));
    assertNull(created.get("batch_id"));
    assertNull(created.get("publish_date"));
    assertTrue(rows(demand.detail(task).get("accounts")).isEmpty());
    List<Map<String, Object>> progress =
        Collections.singletonList(
            map(
                "task_code",
                task,
                "status",
                "生产中",
                "account_count",
                1,
                "completed_count",
                1,
                "failed_count",
                1,
                "updated_at",
                monday.toString()));
    publish(fixture, "marketing_results", prefix, progress);
    assertEquals(1, number(demand.reconcile(100, 0), "applied"));
    progress.get(0).put("failed_count", 0);
    progress.get(0).put("updated_at", monday.plusSeconds(1).toString());
    publish(fixture, "marketing_results", prefix, progress);
    assertEquals(1, number(demand.reconcile(100, 0), "applied"));
    assertEquals(0, number(repo.marketingByCode(task), "content_failed_count"));
    List<Map<String, Object>> allocations = new ArrayList<>();
    for (int i = 1; i <= 2; i++)
      allocations.add(
          map(
              "task_code",
              task,
              "content_id",
              id("MANUAL-C" + i),
              "account_id",
              id("E"),
              "title",
              "已过审营销内容" + i,
              "body",
              "测试营销正文",
              "content_type",
              "产品营销",
              "approved_at",
              monday.plusSeconds(60).toString()));
    publish(fixture, "marketing_allocations", prefix, allocations);
    MarketingPlacementService placement =
        new MarketingPlacementService(repo, sources, slots, rules);
    assertEquals(0, number(placement.reconcile(monday, 100), "applied"));
    assertNull(repo.marketingByCode(task).get("batch_id"));
    // The older +08:00 timestamp sorts after the newer Z timestamp lexically: compare instants.
    allocations
        .get(0)
        .put("approved_at", cycle.atTime(7, 0).atOffset(ZoneOffset.ofHours(8)).toString());
    allocations.get(1).put("approved_at", cycle.atTime(0, 0).atOffset(ZoneOffset.UTC).toString());
    publish(fixture, "marketing_allocations", prefix, allocations);
    assertEquals(2, number(placement.reconcile(monday.plusSeconds(2), 100), "applied"));
    Map<String, Object> completed = repo.marketingByCode(task);
    long manualBatch = number(completed, "batch_id");
    List<Map<String, Object>> manual = repo.itemsByBatch(manualBatch);
    assertEquals(2, manual.size());
    assertEquals("已完成", completed.get("status"));
    assertEquals(
        wednesday.toString(),
        manual.stream()
            .filter(r -> id("MANUAL-C1").equals(r.get("content_id")))
            .findFirst()
            .get()
            .get("publish_date"));
    assertEquals(
        cycle.plusDays(4).toString(),
        manual.stream()
            .filter(r -> id("MANUAL-C2").equals(r.get("content_id")))
            .findFirst()
            .get()
            .get("publish_date"));
    assertEquals(0, number(placement.reconcile(monday.plusSeconds(2), 100), "applied"));
    counts(Collections.singletonList(id("MARKETING")), 2);
    cases.add("人工营销：无账号日期受理、幂等、失败数恢复、过审后分配、日期避让、时区排序和计数");
    return map(
        "status",
        "passed",
        "scope",
        "formal-business-results-to-simulated-content",
        "prefix",
        prefix,
        "cycle_start",
        cycle.toString(),
        "auto_batch_id",
        batch,
        "manual_batch_id",
        manualBatch,
        "marketing_task_code",
        task,
        "account_ids",
        Arrays.asList(id("A"), id("B"), id("C"), id("D"), id("E")),
        "cases",
        cases,
        "auto_items",
        repo.itemsByBatch(batch),
        "manual_items",
        manual,
        "usage",
        usage(Arrays.asList(id("NORMAL"), id("HOT"), id("FALLBACK"), id("MARKETING"))),
        "model_calls",
        0,
        "real_content_system",
        false);
  }
}
