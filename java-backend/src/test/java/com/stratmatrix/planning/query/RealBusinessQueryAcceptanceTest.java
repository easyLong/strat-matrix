package com.stratmatrix.planning.query;

import static com.stratmatrix.planning.manual.Json.*;
import static org.junit.jupiter.api.Assertions.*;

import com.stratmatrix.planning.manual.*;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.mybatis.spring.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.*;

/** Read-only acceptance against deployed MySQL; no Python bridge or bank API is constructed. */
@EnabledIfSystemProperty(named = "planning.real-acceptance-properties", matches = ".+")
class RealBusinessQueryAcceptanceTest {
  @Test
  void businessDatabaseAloneSupportsPagesStatisticsHistoryAndExports() throws Exception {
    Properties p = new Properties();
    try (InputStream in =
        Files.newInputStream(
            Paths.get(System.getProperty("planning.real-acceptance-properties")))) {
      p.load(in);
    }
    DriverManagerDataSource ds =
        new DriverManagerDataSource(
            p.getProperty("planning.manual.jdbc-url"),
            p.getProperty("planning.manual.username"),
            p.getProperty("planning.manual.password"));
    SqlSessionFactoryBean f = new SqlSessionFactoryBean();
    f.setDataSource(ds);
    f.setMapperLocations(
        new ClassPathResource("mapper/ManualMapper.xml"),
        new ClassPathResource("mapper/PlanningQueryMapper.xml"));
    SqlSessionTemplate sql = new SqlSessionTemplate(f.getObject());
    ManualRepository repo =
        new ManualRepository(
            sql.getMapper(ManualMapper.class), new DataSourceTransactionManager(ds));
    ManualPorts.Source source = org.mockito.Mockito.mock(ManualPorts.Source.class);
    ManualPlanningService manual =
        new ManualPlanningService(
            repo,
            source,
            input -> {
              throw new AssertionError("Query must not calculate");
            },
            () -> "acceptance");
    SqlPlanningReadQueries reads =
        new SqlPlanningReadQueries(sql.getMapper(PlanningQueryMapper.class), repo, manual);
    JdbcTemplate jdbc = new JdbcTemplate(ds);
    List<Map<String, Object>> all = reads.records(map("mode", "all"));
    assertEquals(
        jdbc.queryForObject("SELECT COUNT(*) FROM godp_planning_item", Long.class).longValue(),
        all.size());
    Map<String, Object> first = reads.accounts(map("page_size", 20)),
        second = reads.accounts(map("page_size", 20, "page", 2));
    Set<String> ids = new HashSet<>();
    for (Map<String, Object> a : rows(first.get("items")))
      assertTrue(ids.add(text(a, "account_id")));
    for (Map<String, Object> a : rows(second.get("items")))
      assertTrue(ids.add(text(a, "account_id")));
    assertEquals(
        jdbc.queryForObject("SELECT COUNT(DISTINCT account_id) FROM godp_planning_item", Long.class)
            .longValue(),
        number(first, "total"));
    long latestBatch = jdbc.queryForObject("SELECT MAX(id) FROM godp_planning_batch", Long.class);
    Map<String, Object> plans =
        reads.plans(map("mode", "batch", "batch_id", latestBatch, "page_size", 1));
    assertFalse(rows(plans.get("items")).isEmpty());
    Map<String, Object> periods = reads.periods(map("page_size", 200));
    assertEquals(
        jdbc.queryForObject(
                "SELECT COUNT(DISTINCT week_start) FROM godp_planning_batch", Long.class)
            .longValue(),
        number(periods, "total"));
    for (Map<String, Object> period : rows(periods.get("items"))) {
      String week = text(period, "cycleStart");
      long distinct =
          jdbc.queryForObject(
              "SELECT COUNT(DISTINCT i.account_id) FROM godp_planning_item i JOIN godp_planning_batch b ON b.id=i.batch_id WHERE b.week_start=?",
              Long.class,
              week);
      if (distinct > 0) assertEquals(distinct, number(period, "accountCount"));
    }
    List<Map<String, Object>> failures = reads.failures(map("mode", "all"));
    assertEquals(
        jdbc.queryForObject("SELECT COUNT(*) FROM godp_planning_failure", Long.class).longValue(),
        failures.size());
    String archived =
        jdbc.queryForObject(
            "SELECT JSON_UNQUOTE(JSON_EXTRACT(payload,'$.task_code')) FROM godp_planning_task_archive WHERE JSON_UNQUOTE(JSON_EXTRACT(payload,'$.content_mode'))='marketing' LIMIT 1",
            String.class);
    assertNotNull(reads.archivedTask(archived).get("task"));
    Long operationItem =
        jdbc.queryForObject(
            "SELECT item_id FROM godp_planning_adjustment ORDER BY id DESC LIMIT 1", Long.class);
    assertFalse(reads.latestOperations(Collections.singletonList(operationItem)).isEmpty());
    Map<String, Object> tasks = reads.tasks(map("page_size", 20));
    assertTrue(number(tasks, "total") >= 52);
    org.mockito.Mockito.verifyNoInteractions(source);
    Map<String, Object> report =
        map(
            "status",
            "passed",
            "items",
            all.size(),
            "accounts",
            first.get("total"),
            "periods",
            periods.get("total"),
            "tasks",
            tasks.get("total"),
            "failure_accounts",
            failures.size(),
            "python_historical_requests",
            0,
            "duplicate_page_accounts",
            0);
    Files.write(
        Paths.get("../run/business-query-acceptance-20261103.json"),
        write(report).getBytes(StandardCharsets.UTF_8));
    System.out.println("Business-only query acceptance passed: " + write(report));
  }
}
