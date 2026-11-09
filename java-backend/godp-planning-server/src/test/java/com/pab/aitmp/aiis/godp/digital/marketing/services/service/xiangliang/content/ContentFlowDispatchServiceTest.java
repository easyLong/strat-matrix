package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.content;

import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.config.*;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.*;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.ContentFlowWriter;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.error.BusinessException;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.req.BusinessPlanningConfig;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.req.ContentFlowEntry;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.res.ContentFlowReceipt;
import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.BusinessPlanningConfigMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.config.BusinessPlanningConfigService;
import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.ManualMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.ManualRepository;

import static com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json.*;
import static org.junit.jupiter.api.Assertions.*;

import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.dev.LocalManualBusinessSchema;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mybatis.spring.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.*;

class ContentFlowDispatchServiceTest {
  ManualRepository repo;
  BusinessPlanningConfigService config;
  ContentFlowDispatchService service;
  JdbcTemplate contentSql;
  TestWriter writer;
  JdbcTemplate businessSql;
  final Instant now = Instant.parse("2026-11-09T01:00:00Z");

  @BeforeEach
  void setup() throws Exception {
    DriverManagerDataSource business = dataSource("planning");
    LocalManualBusinessSchema.initialize(business);
    businessSql = new JdbcTemplate(business);
    SqlSessionFactoryBean f = new SqlSessionFactoryBean();
    f.setDataSource(business);
    f.setMapperLocations(new ClassPathResource("mapper/xiangliang/ManualMapper.xml"),
        new ClassPathResource("mapper/xiangliang/BusinessPlanningConfigMapper.xml"));
    SqlSessionTemplate sessions = new SqlSessionTemplate(f.getObject());
    DataSourceTransactionManager tx = new DataSourceTransactionManager(business);
    repo = new ManualRepository(sessions.getMapper(ManualMapper.class), tx);
    config = new BusinessPlanningConfigService(sessions.getMapper(BusinessPlanningConfigMapper.class), tx);
    BusinessPlanningConfig initial = rules(3, 0, 1);
    config.save(initial, 0, "test-user");
    repo.saveBatch(1, write(map("cycle_start", "2026-11-09", "cycle_end", "2026-11-15")), now.toEpochMilli());
    // Separate target storage simulates a host write whose commit survives a lost reply.
    contentSql = new JdbcTemplate(dataSource("content"));
    contentSql.execute("CREATE TABLE test_content_flow ("
        + "id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',"
        + "del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',"
        + "created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',"
        + "updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',"
        + "created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',"
        + "updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '修改时间',"
        + "planning_item_id BIGINT UNIQUE NOT NULL COMMENT '策划明细编号',"
        + "result_version INT NOT NULL COMMENT '策划结果版本',"
        + "production_time VARCHAR(40) NOT NULL COMMENT '包含时区的内容生产时间',"
        + "lead_days INT NOT NULL COMMENT '生产提前天数',"
        + "config_version INT NOT NULL COMMENT '生产时间配置版本',"
        + "payload CLOB NOT NULL COMMENT '策划与账号选题完整输入',"
        + "state VARCHAR(16) NOT NULL DEFAULT 'waiting' COMMENT '内容侧执行状态')");
    writer = new TestWriter();
    service = new ContentFlowDispatchService(repo, config, writer);
  }

  private static DriverManagerDataSource dataSource(String name) {
    return new DriverManagerDataSource("jdbc:h2:mem:" + name + UUID.randomUUID()
        + ";MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1", "sa", "");
  }

  private static BusinessPlanningConfig rules(Integer ordinary, Integer marketing, Integer hotspot) {
    BusinessPlanningConfig c = new BusinessPlanningConfig();
    c.planning_days = Arrays.asList(1, 3, 5);
    c.schedule_day = 2; c.schedule_time = "22:00"; c.marketing_max = 1; c.hotspot_ratio = 20;
    c.content_production_lead_days.put("ordinary", ordinary);
    c.content_production_lead_days.put("marketing", marketing);
    c.content_production_lead_days.put("hotspot", hotspot);
    return c;
  }

  private long item(String suffix, String type, String state) {
    Map<String, Object> p = map("topic_id", "TOPIC-" + suffix, "topic_title", "测试选题", "outline", "大纲",
        "topic_type", type, "content_type", "产品解读", "content_agent", "TEST-AGENT",
        "account_name", "测试账号", "account_snapshot", map("account_id", "A-" + suffix,
            "account_name", "测试账号", "um_no", "TESTUM", "organization", "测试二级分行"));
    return repo.saveItem(1, "SLOT-" + suffix, "A-" + suffix, "2026-11-09", write(p), state);
  }

  private int count() {
    return contentSql.queryForObject("SELECT COUNT(*) FROM test_content_flow", Integer.class);
  }

  @Test
  void writesCompleteResultsAndComputedTimeWhenDueButNeverProducesOrDuplicates() {
    long ordinary = item("NORMAL", "普通", "planned");
    item("MARKETING", "营销", "planned");
    item("HOTSPOT", "热点", "planned");
    Map<String, Object> first = service.scan(now, 100, 0);
    assertEquals(3, object(first.get("outcomes")).get("created"));
    assertEquals(3, count());
    Map<String, Object> record = contentSql.queryForMap("SELECT * FROM test_content_flow WHERE planning_item_id=?", ordinary);
    Map<String, Object> body = read(record.get("payload").toString());
    assertEquals("2026-11-06T00:00+08:00", body.get("production_time"));
    assertEquals("2026-11-09", body.get("publish_date"));
    assertEquals("TESTUM", object(body.get("account_info")).get("um_no"));
    assertEquals("大纲", object(body.get("topic_info")).get("outline"));
    assertEquals("TEST-AGENT", object(body.get("topic_info")).get("content_agent"));
    assertEquals("planned", repo.itemById(ordinary).get("production_status"));
    service.scan(now.plusSeconds(3600), 100, 0);
    service.scan(now.plusSeconds(7200), 100, 0);
    assertEquals(3, count());
    assertEquals(3, writer.calls);
  }

  @Test
  void waitsForEachBeijingProductionDateAndCatchesUpDuringLaterScans() {
    item("NORMAL", "普通", "planned");
    item("MARKETING", "营销", "planned");
    item("HOTSPOT", "热点", "planned");
    Map<String, Object> before = service.scan(Instant.parse("2026-11-05T15:59:59Z"), 100, 0);
    assertEquals(3, object(before.get("outcomes")).get("not_due"));
    assertEquals(0, writer.calls);
    service.scan(Instant.parse("2026-11-05T16:00:00Z"), 100, 0);
    assertEquals(1, count()); // 普通T-3：北京时间11月6日。
    service.scan(Instant.parse("2026-11-07T16:00:00Z"), 100, 0);
    assertEquals(2, count()); // 热点T-1：北京时间11月8日。
    service.scan(Instant.parse("2026-11-10T01:00:00Z"), 100, 0);
    assertEquals(3, count()); // 营销T-0：漏扫后补写，不要求日期恰好相等。
  }

  @Test
  void onlyAssignedPendingItemsQualifyAndUnconfiguredTimingDoesNotBecomeZero() {
    item("EMPTY", "热点", "unassigned");
    item("AWAIT", "普通", "awaiting_market");
    item("DONE", "营销", "generated");
    long missing = item("UNCONFIGURED", "普通", "planned");
    long reference = item("REFERENCE", "营销", "planned");
    Map<String, Object> payload = new LinkedHashMap<>(repo.itemById(reference));
    payload.put("content_id", "APPROVED-CONTENT");
    repo.updateItemContent(reference, "planned", write(payload));
    config.save(rules(null, null, null), 1, "test-user");
    Map<String, Object> report = service.scan(now, 100, 0);
    assertEquals("retry_required", report.get("status"));
    assertEquals(1, object(report.get("outcomes")).get("unconfigured"));
    assertEquals(1, object(report.get("outcomes")).get("existing_content"));
    assertEquals(0, count());
    config.save(rules(2, 0, 1), 2, "test-user");
    service.scan(now, 100, 0);
    assertEquals(1, count());
    assertFalse(object(repo.itemById(missing).get("content_flow_dispatch")).isEmpty());
  }

  @Test
  void lostReplyRetriesSameFlowAndKeepsOriginalTimeWhenConfigurationChanges() {
    long id = item("LOST", "普通", "planned");
    writer.loseNextReply = true;
    assertEquals("retry_required", service.scan(now, 100, 0).get("status"));
    assertEquals(1, count());
    assertTrue(object(repo.itemById(id).get("content_flow_dispatch")).isEmpty());
    config.save(rules(5, 0, 1), 1, "test-user");
    Map<String, Object> report = service.scan(now, 100, 0);
    assertEquals(1, object(report.get("outcomes")).get("already_present"));
    Map<String, Object> receipt = object(repo.itemById(id).get("content_flow_dispatch"));
    assertEquals(3, receipt.get("production_lead_days"));
    assertEquals(1, receipt.get("configuration_version"));
    assertEquals("2026-11-06T00:00+08:00", receipt.get("production_time"));
    assertEquals(1, count());
  }

  @Test
  void replacementUpdatesWaitingFlowInPlaceAndNeverOverwritesProducingContent() {
    long id = item("REPLACE", "普通", "planned");
    service.scan(now, 100, 0);
    Map<String, Object> payload = new LinkedHashMap<>(repo.itemById(id));
    payload.put("topic_id", "REPLACED-TOPIC");
    repo.updateItemVersion(id, write(payload), 2);
    assertEquals(1, object(service.scan(now, 100, 0).get("outcomes")).get("updated"));
    assertEquals(1, count());
    assertEquals(2, contentSql.queryForObject("SELECT result_version FROM test_content_flow", Integer.class));
    contentSql.update("UPDATE test_content_flow SET state='producing'");
    payload = new LinkedHashMap<>(repo.itemById(id));
    payload.put("topic_id", "LATE-TOPIC");
    repo.updateItemVersion(id, write(payload), 3);
    assertEquals("retry_required", service.scan(now, 100, 0).get("status"));
    assertEquals(2, contentSql.queryForObject("SELECT result_version FROM test_content_flow", Integer.class));
  }

  @Test
  void paginationIsBoundedAndDeletedOrRunningRowsAreNotDispatched() {
    item("PAGE1", "普通", "planned");
    item("PAGE2", "普通", "planned");
    long running = item("RUNNING", "普通", "planned");
    repo.updateItemContent(running, "ready", write(repo.itemById(running)));
    Map<String, Object> page = service.scan(now, 1, 0);
    assertEquals(true, page.get("has_more"));
    service.scan(now, 1, number(page, "next_after_id"));
    assertEquals(2, count());
    assertEquals(422, assertThrows(BusinessException.class, () -> service.scan(now, 0, 0)).status);
  }

  final class TestWriter implements ContentFlowWriter {
    int calls;
    boolean loseNextReply;

    public ContentFlowReceipt upsert(ContentFlowEntry entry) {
      calls++;
      List<Map<String, Object>> rows = contentSql.queryForList(
          "SELECT * FROM test_content_flow WHERE planning_item_id=?", entry.planningItemId);
      ContentFlowReceipt.Outcome outcome;
      if (rows.isEmpty()) {
        contentSql.update("INSERT INTO test_content_flow(planning_item_id,result_version,production_time,lead_days,config_version,payload) VALUES(?,?,?,?,?,?)",
            entry.planningItemId, entry.resultVersion, entry.productionTime.toString(), entry.productionLeadDays,
            entry.configurationVersion, write(entry.toMap()));
        outcome = ContentFlowReceipt.Outcome.CREATED;
      } else {
        Map<String, Object> old = rows.get(0);
        int oldVersion = ((Number) old.get("result_version")).intValue();
        if (oldVersion > entry.resultVersion || oldVersion < entry.resultVersion && !"waiting".equals(old.get("state")))
          throw new BusinessException(409, "内容流水版本变化或已开始生产");
        outcome = oldVersion == entry.resultVersion ? ContentFlowReceipt.Outcome.ALREADY_PRESENT : ContentFlowReceipt.Outcome.UPDATED;
        if (outcome == ContentFlowReceipt.Outcome.UPDATED)
          contentSql.update("UPDATE test_content_flow SET result_version=?,production_time=?,lead_days=?,config_version=?,payload=? WHERE planning_item_id=?",
              entry.resultVersion, entry.productionTime.toString(), entry.productionLeadDays, entry.configurationVersion,
              write(entry.toMap()), entry.planningItemId);
      }
      if (loseNextReply) { loseNextReply = false; throw new IllegalStateException("Accepted but reply lost"); }
      Map<String, Object> row = contentSql.queryForMap("SELECT * FROM test_content_flow WHERE planning_item_id=?", entry.planningItemId);
      return new ContentFlowReceipt(row.get("id").toString(), entry.planningItemId,
          ((Number) row.get("result_version")).intValue(), OffsetDateTime.parse(row.get("production_time").toString()),
          ((Number) row.get("lead_days")).intValue(), ((Number) row.get("config_version")).intValue(), outcome);
    }
  }

  @Test
  void independentWriteDoesNotHoldBusinessTransactionOrOverwriteAConcurrentChange() {
    long id = item("CONCURRENT", "普通", "planned");
    ContentFlowWriter independent = entry -> {
      assertFalse(org.springframework.transaction.support.TransactionSynchronizationManager.isActualTransactionActive());
      ContentFlowReceipt receipt = writer.upsert(entry);
      Map<String, Object> changed = new LinkedHashMap<>(repo.itemById(id));
      changed.put("topic_id", "NEW-TOPIC");
      repo.updateItemVersion(id, write(changed), 2);
      return receipt;
    };
    Map<String, Object> result = new ContentFlowDispatchService(repo, config, independent).scan(now, 100, 0);
    assertEquals(1, object(result.get("outcomes")).get("changed"));
    assertEquals("NEW-TOPIC", repo.itemById(id).get("topic_id"));
    assertTrue(object(repo.itemById(id).get("content_flow_dispatch")).isEmpty());
    // Next scan updates the waiting flow to the current version, without duplicates.
    service.scan(now, 100, 0);
    assertEquals(1, count());
    assertEquals(2, contentSql.queryForObject("SELECT result_version FROM test_content_flow", Integer.class));
  }

  @Test
  void sameTransactionWriterRollsBackWithReceiptAndCanRetry() {
    long id = item("ATOMIC", "普通", "planned");
    businessSql.execute("CREATE TABLE test_atomic_flow (planning_item_id BIGINT PRIMARY KEY COMMENT '测试策划明细编号')");
    ContentFlowWriter atomic = new ContentFlowWriter() {
      public TransactionMode transactionMode() { return TransactionMode.SAME_TRANSACTION; }
      public ContentFlowReceipt upsert(ContentFlowEntry entry) {
        assertTrue(org.springframework.transaction.support.TransactionSynchronizationManager.isActualTransactionActive());
        businessSql.update("INSERT INTO test_atomic_flow(planning_item_id) VALUES(?)", entry.planningItemId);
        return new ContentFlowReceipt("TEST-ATOMIC", entry.planningItemId, entry.resultVersion,
            entry.productionTime, entry.productionLeadDays, entry.configurationVersion, ContentFlowReceipt.Outcome.CREATED);
      }
    };
    ManualRepository failing = new ManualRepository(
        org.mockito.Mockito.mock(ManualMapper.class),
        new DataSourceTransactionManager(businessSql.getDataSource())) {
      public List<Map<String, Object>> contentFlowCandidates(long after, int limit) { return repo.contentFlowCandidates(after, limit); }
      public Map<String, Object> lockedItem(long itemId) { return repo.lockedItem(itemId); }
      public int updateItemContent(long itemId, String state, String payload) { throw new IllegalStateException("receipt failed"); }
    };
    assertEquals("retry_required", new ContentFlowDispatchService(failing, config, atomic).scan(now, 100, 0).get("status"));
    assertEquals(0, businessSql.queryForObject("SELECT COUNT(*) FROM test_atomic_flow", Integer.class));
    assertTrue(object(repo.itemById(id).get("content_flow_dispatch")).isEmpty());
    new ContentFlowDispatchService(repo, config, atomic).scan(now, 100, 0);
    assertEquals(1, businessSql.queryForObject("SELECT COUNT(*) FROM test_atomic_flow", Integer.class));
  }
}
