package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.ManualPorts;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.error.BusinessException;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.req.ManualPreviewRequest;

import static com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json.*;
import static org.junit.jupiter.api.Assertions.*;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.util.*;
import java.util.concurrent.*;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.ss.usermodel.WorkbookFactory;
import org.junit.jupiter.api.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;

class ManualClosureTest {
  @Test
  void mixedTimestampFormatsSortByBusinessTime() {
    assertEquals(
        ManualQueryService.timestamp("2026-11-02T10:00:00Z"),
        ManualQueryService.timestamp("2026-11-02T18:00:00"));
  }

  ManualRepository repo;
  JdbcTemplate jdbc;
  ManualPlanningService service;
  Fixture fixture;
  ManualQueryService query;

  @Test
  void releasedReservationsRemainAuditableAndCanBeReusedWithoutAllowingAnActiveDuplicate() {
    repo.reserve("2026-11-20", "AUDIT-A", 101L);
    Long rowId = jdbc.queryForObject("SELECT id FROM godp_manual_reservation", Long.class);
    assertTrue(repo.reserved("2026-11-20").contains("AUDIT-A"));
    assertEquals(1, repo.release(101L));
    assertTrue(repo.reserved("2026-11-20").isEmpty());
    assertEquals(
        "Y", jdbc.queryForObject("SELECT del_flag FROM godp_manual_reservation", String.class));
    repo.reserve("2026-11-20", "AUDIT-A", 102L);
    assertEquals(rowId, jdbc.queryForObject("SELECT id FROM godp_manual_reservation", Long.class));
    assertEquals(
        102L, jdbc.queryForObject("SELECT task_id FROM godp_manual_reservation", Long.class));
    assertThrows(
        org.springframework.dao.DataIntegrityViolationException.class,
        () -> repo.reserve("2026-11-20", "AUDIT-A", 103L));
  }

  @Test
  void deletedPlansCannotLeakIntoDetailListsReportsOrUsageCounts() {
    jdbc.execute(
        "CREATE ALIAS JSON_EXTRACT FOR 'com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.query.ReadDatabaseFixture.extract'");
    jdbc.execute(
        "CREATE ALIAS JSON_UNQUOTE FOR 'com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.query.ReadDatabaseFixture.unquote'");
    task("2026-11-20");
    service.advance();
    assertEquals(2, repo.items().size());
    assertEquals(
        "trusted-actor",
        jdbc.queryForObject("SELECT created_by FROM godp_manual_task", String.class));
    assertNotNull(
        jdbc.queryForObject("SELECT created_time FROM godp_manual_task", java.sql.Timestamp.class));
    jdbc.update("UPDATE godp_planning_item SET del_flag='Y'");
    assertTrue(repo.items().isEmpty());
    assertEquals(0L, number(query.accounts(map("filters", map())), "total"));
    assertTrue(repo.completedTopicUsage(Arrays.asList("T1", "T2")).isEmpty());
  }

  static class Fixture extends ManualTestTransition
      implements ManualPorts.Source, ManualPorts.Computer {
    boolean failNetwork = false, malformed = false;
    int submitted = 0;

    public List<Map<String, Object>> accountOptions(int limit, boolean includeDisabled) {
      return Collections.emptyList();
    }

    public Map<String, Object> topicDetail(String topicId, String topicType) {
      return map("topic_id", topicId);
    }

    public Map<String, Object> snapshot(List<String> a, List<String> t) {
      List<Map<String, Object>> accounts = new ArrayList<>(), topics = new ArrayList<>();
      for (String id : a)
        accounts.add(
            map(
                "account_id",
                id,
                "account_name",
                "账号" + id,
                "um_no",
                "UM" + id,
                "account_type",
                "非认证",
                "platform",
                "小红书",
                "followers",
                60,
                "lifecycle_stage",
                "流量增长期"));
      for (String id : new LinkedHashSet<>(t))
        topics.add(
            map(
                "topic_id",
                id,
                "topic_title",
                "选题" + id,
                "outline",
                "测试大纲",
                "is_marketing",
                false,
                "topic_type",
                "普通",
                "content_type",
                "金融科普",
                "valid_from",
                "2026-01-01",
                "valid_to",
                "2027-12-31"));
      return map("accounts", accounts, "topics", topics, "algorithm_version", "v1");
    }

    public Set<String> historicalPlanned(String date) {
      return Collections.emptySet();
    }

    public Set<String> historicalReserved(String date) {
      return Collections.emptySet();
    }

    public Map<String, Object> sourceAccounts(List<String> accountIds) {
      return map("accounts", Collections.emptyList());
    }

    public List<Map<String, Object>> topicCandidates(int limit) {
      return Collections.emptyList();
    }

    public Map<String, Object> submit(Map<String, Object> input) {
      submitted++;
      if (failNetwork) throw new RuntimeException("offline");
      return map(
          "request_id",
          input.get("request_id"),
          "status",
          "succeeded",
          "result",
          result(input, malformed));
    }
  }

  static Map<String, Object> result(Map<String, Object> input, boolean malformed) {
    List<Map<String, Object>> items = new ArrayList<>();
    for (Map<String, Object> a : rows(input.get("accounts")))
      items.add(
          map(
              "account_id",
              a.get("account_id"),
              "topic_id",
              malformed ? "not-selected" : rows(input.get("topics")).get(0).get("topic_id"),
              "lifecycle_stage",
              a.get("lifecycle_stage")));
    return map("algorithm_version", input.get("algorithm_version"), "items", items);
  }

  @BeforeEach
  void setup() {
    DriverManagerDataSource ds =
        new DriverManagerDataSource(
            "jdbc:h2:mem:"
                + UUID.randomUUID()
                + ";MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1",
            "sa",
            "");
    ResourceDatabasePopulator scripts =
        new ResourceDatabasePopulator(new ClassPathResource("db/manual-business.sql"));
    scripts.setSqlScriptEncoding("UTF-8");
    scripts.execute(ds);
    repo = new ManualRepository(ManualTestMapper.bind(ds), new DataSourceTransactionManager(ds));
    jdbc = new JdbcTemplate(ds);
    jdbc.execute("ALTER TABLE godp_manual_task ALTER COLUMN id RESTART WITH 1000000000000");
    jdbc.execute("ALTER TABLE godp_planning_item ALTER COLUMN id RESTART WITH 1000000000000");
    fixture = new Fixture();
    service = new ManualPlanningService(repo, fixture, fixture, () -> "trusted-actor");
    query = new ManualQueryService(repo, service, fixture, fixture);
  }

  ManualPreviewRequest request(String date) {
    ManualPreviewRequest q = new ManualPreviewRequest();
    q.task_name = "普通人工验收";
    q.publish_date = LocalDate.parse(date);
    q.account_ids = Arrays.asList("A1", "A2");
    q.topic_ids = Arrays.asList("T1", "T2");
    q.target_count = 2;
    return q;
  }

  Map<String, Object> task(String date) {
    return service.submit(text(service.preview(request(date)), "preview_id"));
  }

  @Test
  void exportsExcelWithTopicFieldsAndKeepsCsvCompatibility() throws Exception {
    Map<String, Object> created = task("2026-11-18");
    service.advance();
    ManualExportService exporter =
        new ManualExportService(
            query, new ManualItemService(repo, fixture, () -> "trusted-actor"), fixture);
    Map<String, Object> scope = map("mode", "batch", "batch_id", created.get("id"));
    Map<String, Object> excelScope = new LinkedHashMap<>(scope);
    excelScope.put("format", "xlsx");
    byte[] excel = exporter.export(excelScope);
    try (Workbook workbook = WorkbookFactory.create(new ByteArrayInputStream(excel))) {
      assertEquals("策划明细", workbook.getSheetAt(0).getSheetName());
      assertEquals("选题ID", workbook.getSheetAt(0).getRow(0).getCell(5).getStringCellValue());
      assertEquals(3, workbook.getSheetAt(0).getPhysicalNumberOfRows());
      assertTrue(workbook.getSheetAt(0).getRow(1).getCell(5).getStringCellValue().startsWith("T"));
    }
    assertTrue(new String(exporter.export(scope), StandardCharsets.UTF_8).contains("T1"));
  }

  @Test
  void acceptedTaskIsDurableAndCompletionIsIdempotent() {
    Map<String, Object> task = task("2026-11-16");
    long id = number(task, "id");
    assertEquals("执行中", task.get("status"));
    assertEquals(0, fixture.submitted);
    assertTrue(repo.batches().isEmpty());
    assertTrue(service.unavailable("2026-11-16").isEmpty()); // UI only greys completed planning.
    // Construct a new service as if the process restarted after acceptance.
    service = new ManualPlanningService(repo, fixture, fixture, () -> "trusted-actor");
    service.advance();
    service.advance();
    assertEquals(1, repo.batches().size());
    assertEquals(2, repo.items().size());
    assertEquals("completed", repo.tasks().get(0).get("status"));
    assertEquals(id, number(repo.batches().get(0), "id"));
    assertEquals(2, service.unavailable("2026-11-16").size());
    assertEquals(
        2,
        rows(query.plans(map("mode", "batch", "batch_id", id, "filters", map())).get("items"))
            .size());
    assertEquals(
        2L,
        number(
            object(query.plans(map("mode", "batch", "batch_id", id)).get("summary")), "accounts"));
    assertEquals(1L, number(query.tasks(map("filters", map())), "total"));
    assertEquals(2L, number(query.accounts(map("filters", map())), "total"));
    assertEquals(1L, number(query.periods(map("filters", map())), "total"));
    assertEquals("trusted-actor", service.taskView(repo.tasks().get(0)).get("created_by"));
  }

  @Test
  void duplicateSubmitAndAccountDateReservation() {
    String code = text(service.preview(request("2026-11-16")), "preview_id");
    long id = number(service.submit(code), "id");
    assertEquals(id, number(service.submit(code), "id"));
    assertEquals(
        409,
        assertThrows(BusinessException.class, () -> service.preview(request("2026-11-16"))).status);
    assertEquals(1, repo.tasks().size());
  }

  @Test
  void twoPreviewsCannotCreateDuplicateAccountDateTasks() throws Exception {
    String a = text(service.preview(request("2026-11-16")), "preview_id"),
        b = text(service.preview(request("2026-11-16")), "preview_id");
    ExecutorService pool = Executors.newFixedThreadPool(2);
    try {
      List<Future<Boolean>> jobs =
          pool.invokeAll(
              Arrays.asList(
                  () -> {
                    try {
                      service.submit(a);
                      return true;
                    } catch (BusinessException e) {
                      assertEquals(409, e.status);
                      return false;
                    }
                  },
                  () -> {
                    try {
                      service.submit(b);
                      return true;
                    } catch (BusinessException e) {
                      assertEquals(409, e.status);
                      return false;
                    }
                  }));
      assertNotEquals(jobs.get(0).get(), jobs.get(1).get());
      assertEquals(1, repo.tasks().size());
      assertEquals(2, repo.reserved("2026-11-16").size());
    } finally {
      pool.shutdownNow();
    }
  }

  @Test
  void networkFailureRetriesSameDurableTask() {
    task("2026-11-16");
    fixture.failNetwork = true;
    service.advance();
    assertTrue(repo.items().isEmpty());
    assertEquals("pending", repo.tasks().get(0).get("status"));
    fixture.failNetwork = false;
    service.advance();
    assertEquals(1, repo.batches().size());
  }

  @Test
  void invalidResultFailsWithoutPartialBusinessRowsAndReleasesReservation() {
    task("2026-11-16");
    fixture.malformed = true;
    service.advance();
    assertEquals("failed", repo.tasks().get(0).get("status"));
    assertTrue(repo.batches().isEmpty());
    assertTrue(repo.items().isEmpty());
    assertTrue(repo.reserved("2026-11-16").isEmpty());
  }

  @Test
  void expiredPreviewAndTopicValidityAreRejected() {
    String p = text(service.preview(request("2026-11-16")), "preview_id");
    jdbc.update("UPDATE godp_manual_preview SET expires_at=0 WHERE preview_code=?", p);
    assertEquals(409, assertThrows(BusinessException.class, () -> service.submit(p)).status);
    assertEquals(
        422,
        assertThrows(BusinessException.class, () -> service.preview(request("2028-01-01"))).status);
  }

  @Test
  void replacementHonorsStateVersionAndRecordsAudit() {
    task("2026-11-16");
    service.advance();
    long id = number(repo.items().get(0), "id");
    ManualItemService items = new ManualItemService(repo, fixture, () -> "operator");
    items.replace(id, map("new_topic_id", "T3", "expected_version", 1));
    assertEquals("T3", repo.items().get(0).get("topic_id"));
    assertEquals(1, items.adjustments(id).size());
    assertEquals(
        409,
        assertThrows(
                BusinessException.class,
                () -> items.replace(id, map("new_topic_id", "T2", "expected_version", 1)))
            .status);
    jdbc.update("UPDATE godp_planning_item SET content_status='generated' WHERE id=?", id);
    assertEquals(
        409,
        assertThrows(
                BusinessException.class,
                () -> items.replace(id, map("new_topic_id", "T2", "expected_version", 2)))
            .status);
  }

  @Test
  void contentObservationUpdatesResultAndTaskWithoutStartingProduction() {
    Map<String, Object> accepted = task("2026-11-16");
    service.advance();
    long itemId = number(repo.items().get(0), "id");
    ManualPorts.ContentObservation[] observation = {
      new ManualPorts.ContentObservation(itemId, 1, "生产中", "", 1000L, "P1", "")
    };
    ManualContentStatusService states =
        new ManualContentStatusService(
            repo, candidates -> Collections.singletonList(observation[0]));
    assertEquals(1L, number(states.reconcile(20), "applied"));
    assertEquals("ready", repo.items().get(0).get("production_status"));
    assertEquals(
        409,
        assertThrows(
                BusinessException.class,
                () ->
                    new ManualItemService(repo, fixture, () -> "operator")
                        .replace(itemId, map("new_topic_id", "T2", "expected_version", 1)))
            .status);
    assertEquals("生成中", service.taskView(repo.tasks().get(0)).get("content_status"));
    assertEquals(1L, number(query.tasks(map("filters", map("contentStatus", "生成中"))), "total"));

    observation[0] = new ManualPorts.ContentObservation(itemId, 1, "待生产", "", 2000L, "P1", "");
    assertEquals(1L, number(states.reconcile(20), "stale"));
    observation[0] = new ManualPorts.ContentObservation(itemId, 1, "已完成", "C1", 3000L, "P1", "");
    assertEquals(1L, number(states.reconcile(20), "applied"));
    assertEquals("generated", repo.items().get(0).get("production_status"));
    assertEquals("C1", repo.items().get(0).get("content_id"));
    assertEquals(1L, number(service.taskView(repo.tasks().get(0)), "content_completed_count"));
    assertEquals(1L, number(query.batch(number(accepted, "id")), "content_completed_count"));
    assertEquals(
        0L,
        number(
            new ManualContentStatusService(repo, candidates -> Collections.emptyList())
                .reconcile(20),
            "applied"));
  }

  @Test
  void sameAccountCanHaveSeveralSlotsAndCountsAsCompleteOnlyWhenAllAreGenerated() {
    Map<String, Object> accepted = task("2026-11-16");
    service.advance();
    Map<String, Object> first = repo.items().get(0);
    long firstId = number(first, "id"), batchId = number(accepted, "id");
    String accountId = text(first, "account_id");
    Map<String, Object> extra = new LinkedHashMap<>(first);
    extra.put("slot_id", "EXTRA-" + batchId + "-" + accountId);
    extra.put("publish_date", "2026-11-18");
    long extraId =
        repo.saveItem(
            batchId, text(extra, "slot_id"), accountId, text(extra, "publish_date"), write(extra));
    assertEquals(3, repo.items().size());
    assertEquals(3, rows(query.batch(batchId).get("items")).size());
    assertEquals(
        3,
        rows(query.plans(map("mode", "batch", "batch_id", batchId, "unit", "records")).get("items"))
            .size());
    assertEquals(3, query.exportRecords(map("mode", "batch", "batch_id", batchId)).size());
    assertThrows(
        org.springframework.dao.DuplicateKeyException.class,
        () ->
            repo.saveItem(batchId, text(extra, "slot_id"), accountId, "2026-11-20", write(extra)));

    final ManualPorts.ContentObservation[] observation = {
      new ManualPorts.ContentObservation(firstId, 1, "已完成", "C1", 1000L, "P1", "")
    };
    ManualContentStatusService states =
        new ManualContentStatusService(
            repo, candidates -> Collections.singletonList(observation[0]));
    states.reconcile(20);
    assertEquals(0L, number(query.batch(batchId), "content_completed_account_count"));
    observation[0] = new ManualPorts.ContentObservation(extraId, 1, "已完成", "C2", 2000L, "P2", "");
    states.reconcile(20);
    assertEquals(1L, number(query.batch(batchId), "content_completed_account_count"));
  }

  @Test
  void paginationIsAppliedAfterMergeAndGrouping() {
    task("2026-11-16");
    service.advance();
    task("2026-11-17");
    service.advance();
    Map<String, Object> page = query.tasks(map("page", 2, "page_size", 1, "filters", map()));
    assertEquals(2L, number(page, "total"));
    assertEquals("2026-11-16", rows(page.get("items")).get(0).get("publish_date"));
    Map<String, Object> plans =
        query.plans(map("mode", "account", "account_id", "A1", "page", 1, "page_size", 1));
    assertEquals(1L, number(plans, "total"));
    assertEquals(2, rows(plans.get("items")).size());
    assertEquals(2L, number(query.periodsAll(map()).get(0), "accountCount"));
    assertEquals(0L, number(query.tasks(map("filters", map("batch", "missing"))), "total"));
  }
}
