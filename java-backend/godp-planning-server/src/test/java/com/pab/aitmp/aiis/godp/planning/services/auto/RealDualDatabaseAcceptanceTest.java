package com.pab.aitmp.aiis.godp.planning.services.auto;

import com.pab.aitmp.aiis.godp.planning.services.persistence.SqlRows;
import com.pab.aitmp.aiis.godp.planning.entity.command.*;

import com.pab.aitmp.aiis.godp.planning.client.python.*;
import com.pab.aitmp.aiis.godp.planning.services.config.*;
import com.pab.aitmp.aiis.godp.planning.services.manual.*;

import com.pab.aitmp.aiis.godp.planning.api.port.AutoSchedulePort;
import com.pab.aitmp.aiis.godp.planning.client.python.AutoSchedulePythonClient;
import com.pab.aitmp.aiis.godp.planning.client.python.PythonExecutionClient;
import com.pab.aitmp.aiis.godp.planning.entity.support.Json;
import com.pab.aitmp.aiis.godp.planning.services.config.BusinessPlanningConfigMapper;
import com.pab.aitmp.aiis.godp.planning.services.config.BusinessPlanningConfigService;
import com.pab.aitmp.aiis.godp.planning.services.config.ConfigReleaseMapper;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualMapper;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualRepository;

import static com.pab.aitmp.aiis.godp.planning.entity.support.Json.*;
import static org.junit.jupiter.api.Assertions.*;

import java.io.InputStream;
import java.net.URI;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.mybatis.spring.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.jdbc.datasource.*;
import org.springframework.web.client.RestTemplate;

/** Explicit real database/model acceptance. Run only with a local private properties file. */
@EnabledIfSystemProperty(named = "planning.real-acceptance-properties", matches = ".+")
class RealDualDatabaseAcceptanceTest {
  @Test
  void javaBusinessAndPythonAlgorithmCompleteOneCycleWithLostAckRecovery() throws Exception {
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
        new ClassPathResource("mapper/AutoScheduleMapper.xml"),
        new ClassPathResource("mapper/BusinessPlanningConfigMapper.xml"),
        new ClassPathResource("mapper/ConfigReleaseMapper.xml"));
    SqlSessionTemplate sql = new SqlSessionTemplate(f.getObject());
    DataSourceTransactionManager tx = new DataSourceTransactionManager(ds);
    ManualRepository results = new ManualRepository(sql.getMapper(ManualMapper.class), tx);
    AutoScheduleMapper tasks = sql.getMapper(AutoScheduleMapper.class);
    BusinessPlanningConfigService config =
        new BusinessPlanningConfigService(
            sql.getMapper(BusinessPlanningConfigMapper.class),
            tx,
            sql.getMapper(ConfigReleaseMapper.class));
    SimpleClientHttpRequestFactory requests = new SimpleClientHttpRequestFactory();
    requests.setConnectTimeout(3000);
    requests.setReadTimeout(15000);
    RestTemplate http = new RestTemplate(requests);
    URI base = URI.create(p.getProperty("planning.legacy.base-url"));
    String token = p.getProperty("planning.legacy.integration-token");
    AutoSchedulePythonClient client = new AutoSchedulePythonClient(base, token, http);
    int[] confirmations = {0};
    AutoSchedulePort algorithm =
        new AutoSchedulePort() {
          public Map<String, Object> start(LocalDate c, int v, Map<String, Object> b) {
            return client.start(c, v, b);
          }

          public Map<String, Object> status(long id) {
            return client.status(id);
          }

          public Map<String, Object> proposal(long id, int v, Map<String, Object> b) {
            return client.proposal(id, v, b);
          }

          public Map<String, Object> acknowledge(long id, String hash, long batch) {
            Map<String, Object> receipt = client.acknowledge(id, hash, batch);
            if (confirmations[0]++ == 0)
              throw new IllegalStateException(
                  "acceptance: response lost after actual Python acknowledgement");
            return receipt;
          }
        };
    AutoScheduleService service =
        new AutoScheduleService(
            config, tasks, algorithm, new AutoResultCommitService(tasks, results));
    Instant trigger =
        Instant.parse(System.getProperty("planning.acceptance-instant", "2026-11-03T14:00:00Z"));
    service.tick(trigger);
    LocalDate cycle = AutoScheduleService.dueCycle(trigger, config.current().config);
    assertNotNull(cycle);
    PythonExecutionClient executor = new PythonExecutionClient(base, token, http);
    boolean observedPendingAck = false;
    Map<String, Object> task = null;
    for (int i = 0; i < 180; i++) {
      task = SqlRows.one(tasks.byCycle(cycle.toString()));
      if ("已完成".equals(task.get("status"))) break;
      assertNotEquals("旧结果已存在", task.get("status"), "验收周期已有旧正式批次，请选择未占用周期");
      assertNotEquals("策划失败", task.get("status"));
      executor.wakeup(Collections.singletonList("planning"));
      service.advanceOpen(trigger.plusSeconds(i + 1));
      task = SqlRows.one(tasks.byCycle(cycle.toString()));
      observedPendingAck |= "待确认".equals(task.get("status"));
      if (!"已完成".equals(task.get("status"))) Thread.sleep(2000);
    }
    assertEquals("已完成", task.get("status"));
    assertTrue(observedPendingAck);
    long batch = number(task, "business_batch_id"), pipeline = number(task, "pipeline_id");
    List<Map<String, Object>> items = results.itemsByBatch(batch);
    assertFalse(items.isEmpty());
    assertEquals("succeeded", client.status(pipeline).get("status"));
    assertEquals(batch, number(client.status(pipeline), "production_batch_id"));
    int count = items.size();
    service.tick(trigger.plusSeconds(400));
    assertEquals(count, results.itemsByBatch(batch).size());
    Map<String, Object> report =
        map(
            "status",
            "passed",
            "cycle_start",
            cycle.toString(),
            "scheduler_instant",
            trigger.toString(),
            "business_batch_id",
            batch,
            "pipeline_id",
            pipeline,
            "slot_count",
            count,
            "account_count",
            items.stream().map(r -> r.get("account_id")).distinct().count(),
            "business_config_version",
            task.get("business_config_version"),
            "business_config",
            read(text(task, "business_config_json")),
            "actual_python_confirmation",
            true,
            "lost_ack_recovered",
            observedPendingAck,
            "duplicate_results",
            0);
    Path output =
        Paths.get(
            System.getProperty(
                "planning.acceptance-report", "../run/dual-db-acceptance-20261103.json"));
    Files.createDirectories(output.toAbsolutePath().getParent());
    Files.write(output, write(report).getBytes(java.nio.charset.StandardCharsets.UTF_8));
    System.out.println(
        "Dual database acceptance passed: batch="
            + batch
            + ", pipeline="
            + pipeline
            + ", slots="
            + count);
  }
}
