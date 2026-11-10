package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.auto;

import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.AutoScheduleMapper;

import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.persistence.SqlRows;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.command.*;

import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.config.*;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.*;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.AutoSchedulePort;
import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.ManualPorts;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.error.BusinessException;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.req.BusinessPlanningConfig;
import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.BusinessPlanningConfigMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.config.BusinessPlanningConfigService;
import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.ManualMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.ManualNewInstallTransition;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.ManualPlanningService;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.ManualQueryService;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.ManualRepository;

import static com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json.*;
import static org.junit.jupiter.api.Assertions.*;

import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.dev.LocalManualBusinessSchema;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.*;
import org.mybatis.spring.SqlSessionFactoryBean;
import org.mybatis.spring.SqlSessionTemplate;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

class AutoScheduleServiceTest {
  AutoScheduleMapper mapper;
  ManualMapper resultMapper;
  com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.PlanningQueryMapper queryMapper;
  ManualRepository results;
  BusinessPlanningConfigService config;
  BusinessPlanningConfig values;
  DataSourceTransactionManager tx;
  AutoResultCommitService commit;
  final Instant due = Instant.parse("2026-11-03T14:00:00Z");

  @BeforeEach
  void setup() throws Exception {
    DriverManagerDataSource ds =
        new DriverManagerDataSource(
            "jdbc:h2:mem:auto-"
                + UUID.randomUUID()
                + ";MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1",
            "sa",
            "");
    LocalManualBusinessSchema.initialize(ds);
    SqlSessionFactoryBean factory = new SqlSessionFactoryBean();
    factory.setDataSource(ds);
    factory.setMapperLocations(
        new ClassPathResource("mapper/xiangliang/BusinessPlanningConfigMapper.xml"),
        new ClassPathResource("mapper/xiangliang/AutoScheduleMapper.xml"),
        new ClassPathResource("mapper/xiangliang/ManualMapper.xml"),
        new ClassPathResource("mapper/xiangliang/PlanningQueryMapper.xml"));
    SqlSessionTemplate sql = new SqlSessionTemplate(factory.getObject());
    tx = new DataSourceTransactionManager(ds);
    resultMapper = sql.getMapper(ManualMapper.class);
    queryMapper = sql.getMapper(com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.PlanningQueryMapper.class);
    results = new ManualRepository(resultMapper, tx);
    mapper = sql.getMapper(AutoScheduleMapper.class);
    commit = new AutoResultCommitService(mapper, results);
    config =
        new BusinessPlanningConfigService(sql.getMapper(BusinessPlanningConfigMapper.class), tx);
    values = new BusinessPlanningConfig();
    values.planning_days = Arrays.asList(1, 3, 5);
    values.schedule_day = 2;
    values.schedule_time = "22:00";
    values.marketing_max = 1;
    values.hotspot_ratio = 20;
    config.save(values, 0, "UM001");
  }

  Map<String, Object> envelope(Map<String, Object> businessConfig) {
    Map<String, Object> account = map("account_id", "A1", "account_name", "测试账号", "um_no", "UM001");
    List<Map<String, Object>> slots = new ArrayList<>();
    for (int i = 0; i < 3; i++)
      slots.add(
          map(
              "slot_id",
              "AUTO-" + i,
              "account_id",
              "A1",
              "publish_date",
              LocalDate.parse("2026-11-09").plusDays(i * 2).toString(),
              "slot_type",
              i == 2 ? "hotspot" : "regular",
              "topic_id",
              i == 2 ? "" : "T" + i,
              "topic_title",
              i == 2 ? "待热点触发" : "选题" + i,
              "topic_type",
              i == 2 ? null : "普通",
              "outline",
              "大纲",
              "content_type",
              "金融科普",
              "content_role",
              "流量",
              "lifecycle_stage",
              "流量增长期"));
    return wrap(
        map(
            "schema_version",
            1,
            "planning_scope",
            "ordinary_only",
            "pipeline_id",
            88,
            "business_config_version",
            1,
            "business_config",
            businessConfig,
            "cycle_start",
            "2026-11-09",
            "cycle_end",
            "2026-11-15",
            "policy_id",
            1,
            "policy_hash",
            repeat('a'),
            "matching_task_id",
            2,
            "matching_result_hash",
            repeat('b'),
            "accounts",
            map("A1", account),
            "slots",
            slots,
            "hotspot_slots",
            1,
            "hotspot_fallbacks",
            map("A1|2026-11-13", map("topic_id", "T3", "title", "兜底选题"))));
  }

  static String repeat(char c) {
    char[] chars = new char[64];
    Arrays.fill(chars, c);
    return new String(chars);
  }

  static Map<String, Object> wrap(Map<String, Object> p) {
    String raw = write(p);
    return map(
        "schema_version",
        1,
        "proposal_json",
        raw,
        "proposal_hash",
        AutoProposalValidator.sha256(raw));
  }

  @Test
  void commitsOnceAndRecoversLostAcknowledgementWithoutReadingProposalAgain() {
    int[] calls = {0, 0, 0};
    AutoSchedulePort algorithm =
        new AutoSchedulePort() {
          public Map<String, Object> start(
              LocalDate cycle, int version, Map<String, Object> frozen) {
            assertEquals(1, version);
            assertEquals(2, frozen.get("schedule_day"));
            if (calls[0]++ == 0) throw new IllegalStateException("offline");
            return map("status", "created", "pipeline_id", 88, "commit_owner", "java");
          }

          public Map<String, Object> status(long id) {
            return map(
                "status",
                "waiting",
                "commit_owner",
                "java",
                "active_stages",
                Collections.singletonList("result_commit"));
          }

          public Map<String, Object> proposal(long id, int version, Map<String, Object> frozen) {
            calls[1]++;
            assertEquals(1, version);
            assertEquals(2, frozen.get("schedule_day"));
            return envelope(frozen);
          }

          public Map<String, Object> acknowledge(long pipeline, String hash, long batch) {
            assertNotNull(results.batchById(batch));
            assertEquals(3, results.itemsByBatch(batch).size());
            if (calls[2]++ == 0)
              throw new IllegalStateException("reply lost after Python accepted");
            return map(
                "status",
                "accepted",
                "pipeline_id",
                pipeline,
                "proposal_hash",
                hash,
                "business_batch_id",
                batch,
                "reused",
                true);
          }
        };
    AutoScheduleService service = new AutoScheduleService(config, mapper, algorithm, commit);
    assertEquals("waiting", service.tick(due.minusSeconds(1)).get("status"));
    assertThrows(IllegalStateException.class, () -> service.tick(due));
    assertEquals("accepted", service.tick(due.plusSeconds(10)).get("status"));
    values.schedule_day = 4;
    config.save(values, 1, "UM002");
    assertEquals("retry_pending", service.advanceOpen(due.plusSeconds(20)).get(0).get("status"));
    Map<String, Object> task = SqlRows.one(mapper.byCycle("2026-11-09"));
    long id = number(task, "id");
    assertEquals("待确认", task.get("status"));
    assertEquals(id, number(task, "business_batch_id"));
    assertEquals(1, number(task, "confirmation_attempts"));
    assertEquals(1, results.batches().size());
    assertEquals(3, results.itemsByBatch(id).size());
    assertEquals(
        1, results.itemsByBatch(id).stream().filter(s -> "待定题".equals(s.get("status"))).count());
    assertTrue(results.plannedAccountIds("2026-11-09").isEmpty());
    ManualPorts.Source source = org.mockito.Mockito.mock(ManualPorts.Source.class);
    ManualQueryService queries =
        new ManualQueryService(
            results,
            new ManualPlanningService(results, source, input -> map(), () -> "UM001"),
            source,
            new ManualNewInstallTransition());
    assertEquals(3, rows(queries.batch(id).get("items")).size());
    Map<String, Object> view =
        queries.plans(map("mode", "batch", "batch_id", id, "unit", "records"));
    assertEquals(3, rows(view.get("items")).size());
    assertEquals(1, number(object(view.get("summary")), "accounts"));
    assertEquals(2, number(object(view.get("summary")), "topics"));
    assertEquals("completed", service.advanceOpen(due.plusSeconds(30)).get(0).get("status"));
    assertEquals("已完成", SqlRows.one(mapper.byCycle("2026-11-09")).get("status"));
    assertEquals(1, calls[1]);
    assertEquals(2, calls[2]);
    assertEquals("reused", service.tick(Instant.parse("2026-11-05T14:00:00Z")).get("status"));
  }

  Map<String, Object> computingTask() {
    SqlRows.insert(
        map(
            "cycleStart",
            "2026-11-09",
            "cycleEnd",
            "2026-11-15",
            "configVersion",
            1,
            "configJson",
            write(values),
            "time",
            due.toEpochMilli()), AutoTaskInsert.class, mapper::insert);
    Map<String, Object> task = SqlRows.one(mapper.byCycle("2026-11-09"));
    mapper.accepted(number(task, "id"), 88L, null, "计算中", due.toEpochMilli());
    return SqlRows.one(mapper.byCycle("2026-11-09"));
  }

  @Test
  void rollsBackAllRowsOnSlotFailureThenCommitsIdempotently() {
    long id = number(computingTask(), "id");
    Map<String, Object> proposal = envelope(read(write(values)));
    ManualRepository failing =
        new ManualRepository(resultMapper, tx) {
          int writes;

          @Override
          public long saveItem(
              long batch, String slot, String account, String date, String payload, String status) {
            if (++writes == 2) throw new IllegalStateException("injected slot failure");
            return super.saveItem(batch, slot, account, date, payload, status);
          }
        };
    assertThrows(
        IllegalStateException.class,
        () -> new AutoResultCommitService(mapper, failing).commit(id, proposal, due));
    assertTrue(results.items().isEmpty());
    assertTrue(results.batches().isEmpty());
    assertEquals("计算中", SqlRows.one(mapper.byCycle("2026-11-09")).get("status"));
    commit.commit(id, proposal, due);
    commit.commit(id, proposal, due);
    assertEquals(1, results.batches().size());
    assertEquals(3, results.items().size());
    assertThrows(
        IllegalStateException.class,
        () -> commit.commit(id, map("proposal_hash", repeat('f')), due));
  }

  @Test
  void reservesMarketingOnlyWithinFrozenAllowanceAndNeverProducesItEarly() {
    long id = number(computingTask(), "id");
    Map<String, Object> proposal = read(text(envelope(read(write(values))), "proposal_json"));
    object(object(proposal.get("accounts")).get("A1")).put("account_type", "认证");
    for (Map<String, Object> slot : rows(proposal.get("slots"))) slot.put("content_role", "转化");
    commit.commit(id, wrap(proposal), due);
    assertEquals(
        1,
        results.itemsByBatch(id).stream()
            .filter(i -> "awaiting_market".equals(i.get("production_status")))
            .count());
    assertEquals(
        1,
        results.itemsByBatch(id).stream()
            .filter(i -> "unassigned".equals(i.get("production_status")))
            .count());
    assertEquals(1, results.pendingItems(0, 100).size());
  }

  @Test
  void rejectsHashAndAccountDateDriftBeforeAnyBusinessWrite() {
    long id = number(computingTask(), "id");
    Map<String, Object> proposal = envelope(read(write(values)));
    proposal.put("proposal_hash", repeat('f'));
    assertThrows(BusinessException.class, () -> commit.commit(id, proposal, due));
    Map<String, Object> p = read(text(proposal, "proposal_json"));
    rows(p.get("slots")).get(1).put("publish_date", "2026-11-09");
    assertThrows(BusinessException.class, () -> commit.commit(id, wrap(p), due));
    assertTrue(results.batches().isEmpty());
    assertTrue(results.items().isEmpty());
  }

  @Test
  void concurrentHostsCommitOneBatch() throws Exception {
    long id = number(computingTask(), "id");
    Map<String, Object> proposal = envelope(read(write(values)));
    java.util.concurrent.ExecutorService pool =
        java.util.concurrent.Executors.newFixedThreadPool(2);
    try {
      java.util.concurrent.CountDownLatch go = new java.util.concurrent.CountDownLatch(1);
      java.util.concurrent.Callable<Map<String, Object>> action =
          () -> {
            go.await();
            return commit.commit(id, proposal, due);
          };
      java.util.concurrent.Future<Map<String, Object>> a = pool.submit(action),
          b = pool.submit(action);
      go.countDown();
      a.get(10, java.util.concurrent.TimeUnit.SECONDS);
      b.get(10, java.util.concurrent.TimeUnit.SECONDS);
      assertEquals(1, results.batches().size());
      assertEquals(3, results.items().size());
      assertEquals("待确认", SqlRows.one(mapper.byCycle("2026-11-09")).get("status"));
    } finally {
      pool.shutdownNow();
    }
  }

  @Test
  void largeResultIsHiddenUntilCompleteAndResumesAfterPageFailure() throws Exception {
    values.hotspot_ratio = 0;
    long id = number(computingTask(), "id");
    Map<String, Object> p = read(text(envelope(read(write(values))), "proposal_json"));
    Map<String, Object> accounts = new LinkedHashMap<>();
    List<Map<String, Object>> slots = new ArrayList<>();
    Map<String, Object> template = rows(p.get("slots")).get(0);
    for (int a = 0; a < 201; a++) {
      String account = "A" + a;
      accounts.put(account, map("account_id", account, "account_name", "测试账号" + a));
      for (int d = 0; d < 3; d++) {
        Map<String, Object> slot = new LinkedHashMap<>(template);
        slot.putAll(map("account_id", account, "slot_id", account + "-" + d,
            "publish_date", LocalDate.parse("2026-11-09").plusDays(d * 2).toString()));
        slots.add(slot);
      }
    }
    p.putAll(map("accounts", accounts, "slots", slots, "hotspot_slots", 0, "hotspot_fallbacks", map()));
    Map<String, Object> proposal = wrap(p);
    assertEquals("计算中", commit.commit(id, proposal, due).get("status"));
    assertTrue(results.batches().isEmpty());
    assertTrue(results.items().isEmpty());
    assertTrue(results.contentFlowCandidates(0, 500).isEmpty());
    assertTrue(results.pendingItems(0, 500).isEmpty());
    assertNull(results.batchById(id));
    assertEquals(500, results.stagedItemCount(id));
    Map<String, Object> stage = results.transaction(() -> results.lockedBatchWrite(id));
    assertEquals(500, number(stage, "write_cursor"));
    org.springframework.jdbc.core.JdbcTemplate jdbc = new org.springframework.jdbc.core.JdbcTemplate(tx.getDataSource());
    jdbc.execute("CREATE ALIAS JSON_EXTRACT FOR 'com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.query.ReadDatabaseFixture.extract'");
    jdbc.execute("CREATE ALIAS JSON_UNQUOTE FOR 'com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.query.ReadDatabaseFixture.unquote'");
    assertEquals(0, jdbc.queryForObject("SELECT COUNT(*) FROM information_schema.views WHERE table_schema='public'", Integer.class));
    com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.command.PlanningQueryCriteria visible =
        SqlRows.criteria(map("limit", 1000));
    assertEquals(0, queryMapper.records(visible).size());
    assertEquals(0, queryMapper.periodCount(visible));
    long hiddenId = jdbc.queryForObject("SELECT MIN(id) FROM godp_planning_item", Long.class);
    assertNull(results.itemById(hiddenId));
    Map<String, Object> drift = read(text(proposal, "proposal_json"));
    rows(drift.get("slots")).get(0).put("topic_title", "变更后的提案");
    assertThrows(IllegalStateException.class, () -> commit.commit(id, wrap(drift), due));
    ManualRepository interrupted = new ManualRepository(resultMapper, tx) {
      public long saveItem(long batch, String slot, String account, String date, String payload, String status) {
        super.saveItem(batch, slot, account, date, payload, status);
        throw new IllegalStateException("interrupted second page");
      }
    };
    assertThrows(IllegalStateException.class,
        () -> new AutoResultCommitService(mapper, interrupted).commit(id, proposal, due.plusSeconds(60)));
    assertEquals(500, results.stagedItemCount(id));
    assertEquals(500, number(results.transaction(() -> results.lockedBatchWrite(id)), "write_cursor"));
    AutoScheduleMapper failedReceipt = org.mockito.Mockito.mock(AutoScheduleMapper.class,
        org.mockito.AdditionalAnswers.delegatesTo(mapper));
    org.mockito.Mockito.doThrow(new IllegalStateException("commit receipt failed")).when(failedReceipt)
        .committed(id, id, text(proposal, "proposal_hash"), due.plusSeconds(90).toEpochMilli());
    assertThrows(IllegalStateException.class,
        () -> new AutoResultCommitService(failedReceipt, results).commit(id, proposal, due.plusSeconds(90)));
    // Publication and task receipt are atomic, including the final page's rows.
    assertEquals(500, results.stagedItemCount(id));
    assertNull(results.batchById(id));
    assertEquals(0, queryMapper.records(visible).size());
    AutoResultCommitService resumed = new AutoResultCommitService(mapper, results);
    assertEquals("待确认", resumed.commit(id, proposal, due.plusSeconds(120)).get("status"));
    assertEquals(603, results.itemsByBatch(id).size());
    assertEquals(603, queryMapper.records(visible).size());
    assertTrue(results.itemsByBatch(id).stream().allMatch(row -> due.toString().equals(row.get("batch_created_at"))));
    resumed.commit(id, proposal, due.plusSeconds(180));
    assertEquals(603, results.stagedItemCount(id));
  }
}
