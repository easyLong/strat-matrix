package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.query;

import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.PlanningQueryMapper;

import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.config.*;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.content.*;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.*;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.ManualPorts;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json;
import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.BusinessPlanningConfigMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.config.BusinessPlanningConfigService;
import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.SlotCompletionMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.ManualMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.ManualPlanningService;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.ManualRepository;

import static com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json.*;

import com.fasterxml.jackson.databind.*;
import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.dev.LocalManualBusinessSchema;
import java.util.*;
import org.mybatis.spring.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.*;

/** Test-only JSON functions run the production table projections against H2, without views. */
public final class ReadDatabaseFixture {
  private static final ObjectMapper JSON = new ObjectMapper();

  public static String extract(String raw, String path) throws Exception {
    if (raw == null) return null;
    JsonNode node = JSON.readTree(raw);
    for (String part : path.substring(2).split("\\.")) {
      node = node.get(part);
      if (node == null) return null;
    }
    return JSON.writeValueAsString(node);
  }

  public static String unquote(String raw) throws Exception {
    if (raw == null) return null;
    JsonNode node = JSON.readTree(raw);
    return node.isTextual() ? node.asText() : raw;
  }

  public final DriverManagerDataSource ds;
  public final JdbcTemplate jdbc;
  public final ManualRepository repo;
  public final PlanningQueryMapper queries;
  public final SlotCompletionMapper slots;
  public final BusinessPlanningConfigService business;
  public final SqlPlanningReadQueries reads;

  public ReadDatabaseFixture() throws Exception {
    this(false);
  }

  public ReadDatabaseFixture(boolean runtimePrivilegesOnly) throws Exception {
    ds =
        new DriverManagerDataSource(
            "jdbc:h2:mem:read-"
                + UUID.randomUUID()
                + ";MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1",
            "sa",
            "");
    LocalManualBusinessSchema.initialize(ds);
    jdbc = new JdbcTemplate(ds);
    jdbc.execute(
        "CREATE ALIAS JSON_EXTRACT FOR 'com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.query.ReadDatabaseFixture.extract'");
    jdbc.execute(
        "CREATE ALIAS JSON_UNQUOTE FOR 'com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.query.ReadDatabaseFixture.unquote'");
    if (jdbc.queryForObject("SELECT COUNT(*) FROM information_schema.views WHERE table_schema='public'", Integer.class) != 0)
      throw new IllegalStateException("Acceptance database must not contain views");
    if (runtimePrivilegesOnly) {
      // Simulated DBA installation above; the application below gets DML only.
      jdbc.execute("CREATE USER planning_runtime PASSWORD 'test-only'");
      for (String table : jdbc.queryForList(
          "SELECT table_name FROM information_schema.tables WHERE table_schema='public'", String.class))
        jdbc.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON \"" + table + "\" TO planning_runtime");
      // H2 URL settings themselves require ADMIN; the DBA already applied them.
      ds.setUrl(ds.getUrl().split(";")[0]);
      ds.setUsername("planning_runtime");
      ds.setPassword("test-only");
    }
    SqlSessionFactoryBean f = new SqlSessionFactoryBean();
    f.setDataSource(ds);
    f.setMapperLocations(
        new ClassPathResource("mapper/xiangliang/ManualMapper.xml"),
        new ClassPathResource("mapper/xiangliang/PlanningQueryMapper.xml"),
        new ClassPathResource("mapper/xiangliang/SlotCompletionMapper.xml"),
        new ClassPathResource("mapper/xiangliang/BusinessPlanningConfigMapper.xml"));
    SqlSessionTemplate sql = new SqlSessionTemplate(f.getObject());
    repo =
        new ManualRepository(
            sql.getMapper(ManualMapper.class), new DataSourceTransactionManager(ds));
    queries = sql.getMapper(PlanningQueryMapper.class);
    slots = sql.getMapper(SlotCompletionMapper.class);
    business =
        new BusinessPlanningConfigService(
            sql.getMapper(BusinessPlanningConfigMapper.class),
            new DataSourceTransactionManager(ds));
    ManualPorts.Source source = org.mockito.Mockito.mock(ManualPorts.Source.class);
    reads =
        new SqlPlanningReadQueries(
            queries, repo, new ManualPlanningService(repo, source, input -> map(), () -> "UM1"));
  }

  public void batch(long id, String type, String date) {
    repo.saveBatch(
        id,
        write(
            map(
                "id",
                id,
                "plan_type",
                type,
                "batch_code",
                "B" + id,
                "task_name",
                "批次" + id,
                "cycle_start",
                date,
                "cycle_end",
                date,
                "created_at",
                "2026-11-02T08:00:00Z",
                "updated_at",
                "2026-11-02T08:00:00Z",
                "account_count",
                2,
                "completed_count",
                2,
                "failed_count",
                0)),
        id * 1000);
  }

  public long item(
      long batch, String account, String date, String state, String type, String topic) {
    return repo.saveItem(
        batch,
        UUID.randomUUID().toString(),
        account,
        date,
        write(
            map(
                "batch_id",
                batch,
                "batch_code",
                "B" + batch,
                "plan_type",
                batch == 2 ? "manual" : "auto",
                "cycle_start",
                "2026-11-02",
                "cycle_end",
                "2026-11-08",
                "account_id",
                account,
                "account_name",
                "账号" + account,
                "account_snapshot",
                map(
                    "account_id",
                    account,
                    "account_name",
                    "账号" + account,
                    "um_no",
                    "UM" + account,
                    "platform",
                    "抖音",
                    "organization",
                    "深圳二级分行",
                    "account_type",
                    "认证",
                    "followers",
                    100),
                "publish_date",
                date,
                "slot_id",
                UUID.randomUUID().toString(),
                "slot_type",
                type,
                "topic_id",
                topic,
                "topic_title",
                "选题" + topic,
                "outline",
                "大纲",
                "content_role",
                "转化",
                "lifecycle_stage",
                "流量增长期",
                "content_type",
                "金融科普",
                "topic_type",
                "普通",
                "hotspot_fallback",
                map(
                    "topic_id",
                    "FALLBACK",
                    "title",
                    "普通兜底",
                    "outline",
                    "兜底大纲",
                    "content_type",
                    "金融科普"))),
        state);
  }
}
