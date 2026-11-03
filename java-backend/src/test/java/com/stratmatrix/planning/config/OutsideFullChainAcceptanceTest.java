package com.stratmatrix.planning.config;

import static com.stratmatrix.planning.manual.Json.*;
import static org.junit.jupiter.api.Assertions.*;

import com.stratmatrix.planning.adapter.python.*;
import com.stratmatrix.planning.auto.*;
import com.stratmatrix.planning.manual.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
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

/**
 * Real dual-DB/model acceptance using the daily Java source facade, simulated clock and content.
 */
@EnabledIfSystemProperty(named = "planning.full-chain-properties", matches = ".+")
class OutsideFullChainAcceptanceTest {
  @Test
  void completeOrdinaryCycleThroughJavaFactsAndProductionStateQueries() throws Exception {
    Properties p = new Properties();
    try (InputStream in =
        Files.newInputStream(Paths.get(System.getProperty("planning.full-chain-properties")))) {
      p.load(in);
    }
    Path out = Paths.get(p.getProperty("acceptance.output"));
    String token = p.getProperty("planning.legacy.integration-token");
    Files.write(
        out.resolve("java-ready.json"), write(map("ready", true)).getBytes(StandardCharsets.UTF_8));
    DriverManagerDataSource ds =
        new DriverManagerDataSource(
            p.getProperty("planning.manual.jdbc-url"),
            p.getProperty("planning.manual.username"),
            p.getProperty("planning.manual.password"));
    DataSourceTransactionManager tx = new DataSourceTransactionManager(ds);
    SqlSessionFactoryBean f = new SqlSessionFactoryBean();
    f.setDataSource(ds);
    f.setMapperLocations(
        new ClassPathResource("mapper/ManualMapper.xml"),
        new ClassPathResource("mapper/AutoScheduleMapper.xml"),
        new ClassPathResource("mapper/BusinessPlanningConfigMapper.xml"));
    SqlSessionTemplate sql = new SqlSessionTemplate(f.getObject());
    ManualRepository repo = new ManualRepository(sql.getMapper(ManualMapper.class), tx);
    TopicUsageService usage = new TopicUsageService(repo);
    AutoScheduleMapper tasks = sql.getMapper(AutoScheduleMapper.class);
    BusinessPlanningConfig testConfig = new BusinessPlanningConfig();
    testConfig.planning_days = Arrays.asList(1, 3, 5);
    testConfig.schedule_day = 2;
    testConfig.schedule_time = "22:00";
    testConfig.marketing_max = 0;
    testConfig.hotspot_ratio = 0;
    // A test-owned immutable configuration; never save over the page configuration.
    BusinessPlanningConfigService config =
        new BusinessPlanningConfigService(sql.getMapper(BusinessPlanningConfigMapper.class), tx) {
          @Override
          public Result current() {
            return new Result(1, "acceptance-fixture", testConfig);
          }
        };
    SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
    requestFactory.setConnectTimeout(2000);
    requestFactory.setReadTimeout(15000);
    RestTemplate http = new RestTemplate(requestFactory);
    URI python = URI.create(p.getProperty("planning.legacy.base-url"));
    long waitUntil = System.currentTimeMillis() + 60000;
    while (true) {
      try {
        http.getForObject(python + "/api/health", Map.class);
        break;
      } catch (RuntimeException unavailable) {
        if (System.currentTimeMillis() > waitUntil) throw unavailable;
        Thread.sleep(500);
      }
    }
    org.springframework.http.HttpHeaders headers = new org.springframework.http.HttpHeaders();
    headers.setContentType(org.springframework.http.MediaType.APPLICATION_JSON);
    headers.set("X-Integration-Token", token);
    Map page =
        http.exchange(
                python + "/__acceptance/source-preflight",
                org.springframework.http.HttpMethod.GET,
                new org.springframework.http.HttpEntity<>(headers),
                Map.class)
            .getBody();
    assertEquals(1, ((Number) page.get("account_count")).intValue());
    assertEquals(12, ((Number) page.get("topic_count")).intValue());
    assertEquals(5, ((Number) page.get("page_items")).intValue());
    AutoSchedulePythonClient client = new AutoSchedulePythonClient(python, token, http);
    int[] acknowledgements = {0};
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
            Map<String, Object> result = client.acknowledge(id, hash, batch);
            if (acknowledgements[0]++ == 0) {
              try {
                Files.write(
                    out.resolve("lost-ack-observed.json"),
                    write(map("actual_python_acknowledgement", true, "business_batch_id", batch))
                        .getBytes(StandardCharsets.UTF_8));
              } catch (IOException error) {
                throw new IllegalStateException(error);
              }
              throw new IllegalStateException("acceptance lost acknowledgement response");
            }
            return result;
          }
        };
    AutoScheduleService scheduler =
        new AutoScheduleService(config, tasks, algorithm, new AutoResultCommitService(tasks, repo));
    Instant trigger = Instant.parse(p.getProperty("acceptance.trigger"));
    LocalDate cycle = AutoScheduleService.dueCycle(trigger, testConfig);
    if (!Boolean.parseBoolean(p.getProperty("acceptance.resume", "false")))
      assertNull(tasks.byCycle(cycle.toString()), "Acceptance cycle already occupied");
    try {
      scheduler.tick(trigger);
    } catch (RuntimeException lostResponse) {
      if (!"待确认".equals(tasks.byCycle(cycle.toString()).get("status"))) throw lostResponse;
    }
    PythonExecutionClient executor = new PythonExecutionClient(python, token, http);
    boolean previousAckLoss = Files.exists(out.resolve("lost-ack-observed.json"));
    if (!previousAckLoss && Boolean.parseBoolean(p.getProperty("acceptance.resume", "false"))) {
      try (java.util.stream.Stream<Path> logs = Files.list(out)) {
        previousAckLoss =
            logs.filter(x -> x.getFileName().toString().startsWith("java.log."))
                .anyMatch(
                    x -> {
                      try {
                        return new String(Files.readAllBytes(x), StandardCharsets.UTF_8)
                            .contains("acceptance lost acknowledgement response");
                      } catch (IOException error) {
                        return false;
                      }
                    });
      }
    }
    Map<String, Object> task = null;
    boolean pendingAck =
        previousAckLoss || "待确认".equals(tasks.byCycle(cycle.toString()).get("status"));
    long deadline =
        System.currentTimeMillis()
            + Integer.parseInt(p.getProperty("acceptance.timeout-seconds", "900")) * 1000L;
    while (System.currentTimeMillis() < deadline) {
      executor.wakeup(Collections.singletonList("planning"));
      scheduler.advanceOpen(trigger.plusSeconds(acknowledgements[0] + 1));
      task = tasks.byCycle(cycle.toString());
      pendingAck |= "待确认".equals(task.get("status"));
      Files.write(
          out.resolve("progress.json"),
          write(
                  map(
                      "status",
                      task.get("status"),
                      "pipeline_id",
                      task.get("pipeline_id"),
                      "error",
                      task.get("last_error")))
              .getBytes(StandardCharsets.UTF_8));
      assertNotEquals("策划失败", task.get("status"));
      if ("已完成".equals(task.get("status"))) break;
      Thread.sleep(2000);
    }
    assertEquals("已完成", task.get("status"));
    assertTrue(pendingAck);
    long batch = number(task, "business_batch_id"), pipeline = number(task, "pipeline_id");
    List<Map<String, Object>> items = repo.itemsByBatch(batch);
    assertEquals(3, items.size());
    Set<Long> ids = new HashSet<>();
    for (Map<String, Object> item : items) ids.add(number(item, "id"));
    assertEquals("succeeded", client.status(pipeline).get("status"));
    List<String> topicIds = new ArrayList<>();
    for (Map<String, Object> item : items) topicIds.add(text(item, "topic_id"));
    assertTrue(
        rows(usage.query(map("topic_ids", topicIds)).get("topic_results")).stream()
            .allMatch(r -> number(r, "official_use_count") == 0));
    List<String> states = new ArrayList<>();
    states.add("待生产");
    Map<Long, ManualPorts.ContentObservation> observations = new HashMap<>();
    ManualContentStatusService content =
        new ManualContentStatusService(
            repo,
            candidates -> {
              List<ManualPorts.ContentObservation> result = new ArrayList<>();
              for (ManualPorts.ContentCandidate c : candidates)
                if (observations.containsKey(c.itemId)) result.add(observations.get(c.itemId));
              return result;
            });
    long stamp = System.currentTimeMillis();
    for (String state : Arrays.asList("生产中", "已完成")) {
      for (Map<String, Object> item : items) {
        long id = number(item, "id");
        observations.put(
            id,
            new ManualPorts.ContentObservation(
                id,
                (int) number(item, "result_version"),
                state,
                "已完成".equals(state) ? "SIM-CONTENT-" + id : null,
                ++stamp,
                "SIM-TASK-" + id,
                ""));
      }
      long after = 0;
      while (true) {
        Map<String, Object> result = content.reconcile(200, after);
        after = number(result, "next_after_id");
        if (!Boolean.TRUE.equals(result.get("has_more"))) break;
      }
      states.add(state);
      for (long id : ids)
        assertEquals(
            "已完成".equals(state) ? "generated" : "ready", repo.lockedItem(id).get("content_status"));
    }
    Map<String, Object> completedBatch = read(text(repo.batchById(batch), "payload"));
    assertEquals(1, number(completedBatch, "content_completed_account_count"));
    assertEquals(3, number(completedBatch, "content_completed_count"));
    Map<String, Object> usageAfter = usage.query(map("topic_ids", topicIds));
    assertTrue(
        rows(usageAfter.get("topic_results")).stream()
            .allMatch(r -> number(r, "official_use_count") == 1));
    content.reconcile(200, 0);
    assertEquals(
        write(usageAfter.get("topic_results")),
        write(usage.query(map("topic_ids", topicIds)).get("topic_results")));
    scheduler.tick(trigger.plusSeconds(800));
    assertEquals(3, repo.itemsByBatch(batch).size());
    Map<String, Object> report =
        map(
            "status",
            "passed",
            "cycle_start",
            cycle.toString(),
            "account_id",
            p.getProperty("acceptance.account-id"),
            "business_batch_id",
            batch,
            "pipeline_id",
            pipeline,
            "slot_count",
            3,
            "account_count",
            1,
            "content_states",
            states,
            "content_completed_account_count",
            1,
            "content_completed_count",
            3,
            "java_source",
            p.getProperty("acceptance.java-source"),
            "lost_ack_recovered",
            pendingAck,
            "duplicate_results",
            0,
            "business_configuration",
            "test-owned snapshot; live page config unchanged",
            "model_mode",
            "real_configured_models",
            "mock_content",
            true,
            "topic_usage",
            usageAfter,
            "items",
            repo.itemsByBatch(batch));
    Files.write(out.resolve("business.json"), write(report).getBytes(StandardCharsets.UTF_8));
  }
}
