package com.stratmatrix.planning.manual;

import static com.stratmatrix.planning.manual.Json.*;
import static org.junit.jupiter.api.Assertions.*;

import com.stratmatrix.standalone.LocalManualBusinessSchema;
import java.util.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

class MarketingTaskServiceTest {
  ManualRepository repo;
  MarketingTaskService service;
  ManualQueryService query;
  List<ManualPorts.MarketingObservation> observations;

  @BeforeEach
  void setup() {
    DriverManagerDataSource ds = new DriverManagerDataSource(
        "jdbc:h2:mem:marketing-" + UUID.randomUUID()
            + ";MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1", "sa", "");
    LocalManualBusinessSchema.initialize(ds);
    repo = new ManualRepository(ManualTestMapper.bind(ds), new DataSourceTransactionManager(ds));
    ManualPorts.Source source = new ManualPorts.Source() {
      public List<Map<String, Object>> accountOptions(int limit, boolean includeDisabled) {
        return Collections.emptyList();
      }
      public Map<String, Object> topicDetail(String topicId, String topicType) {
        return map("topic_id", topicId);
      }
      public Map<String, Object> snapshot(List<String> accounts, List<String> topics) {
        return map("accounts", Collections.emptyList(), "topics", topics.get(0).equals("MISSING")
            ? Collections.emptyList() : Collections.singletonList(map(
                "topic_id", topics.get(0), "topic_title", "营销测试选题",
                "outline", "选题大纲", "is_marketing", true)));
      }
      public Map<String, Object> sourceAccounts(List<String> ids) { return map("accounts", Collections.emptyList()); }
      public List<Map<String, Object>> topicCandidates(int limit) { return Collections.emptyList(); }
      public Set<String> historicalPlanned(String date) { return Collections.emptySet(); }
      public Set<String> historicalReserved(String date) { return Collections.emptySet(); }
    };
    observations = new ArrayList<>();
    service = new MarketingTaskService(repo, source, () -> "UM100",
        codes -> new ArrayList<>(observations));
    ManualPlanningService manual = new ManualPlanningService(repo, source, input -> map(), () -> "UM100");
    query = new ManualQueryService(repo, manual, source, new ManualTestTransition(), service);
  }

  private MarketingTaskRequest request(String topicId) {
    MarketingTaskRequest request = new MarketingTaskRequest();
    request.request_id = UUID.randomUUID();
    request.task_name = "  营销需求  ";
    request.topic_id = topicId;
    request.allocation_count = 3;
    return request;
  }

  @Test
  void createsIdempotentUndatedTaskAndKeepsTopicSnapshot() {
    MarketingTaskRequest input = request("T1");
    Map<String, Object> created = service.create(input);
    assertEquals("待分配", created.get("status"));
    assertEquals("marketing", created.get("content_mode"));
    assertEquals(3L, number(created, "allocation_count"));
    assertEquals("UM100", created.get("created_by"));
    assertEquals(created.get("task_code"), service.create(input).get("task_code"));
    assertEquals(1, service.all().size());
    Map<String, Object> detail = service.detail(text(created, "task_code"));
    assertEquals("T1", rows(detail.get("topics")).get(0).get("topic_id"));
    assertTrue(rows(detail.get("accounts")).isEmpty());
    assertEquals(1L, number(query.tasks(map("filters", map())), "total"));
    assertEquals(1L, number(query.tasks(map("filters", map("contentStatus", "待分配"))), "total"));
    assertEquals(0L, number(query.tasks(map("filters", map("dateStart", "2026-11-01"))), "total"));
    input.allocation_count = 4;
    assertEquals(409, assertThrows(BusinessException.class, () -> service.create(input)).status);
    assertEquals(409, assertThrows(BusinessException.class,
        () -> service.create(request("MISSING"))).status);
  }

  @Test
  void appliesOnlyValidNewerContentProgressAndNeverStartsProduction() {
    Map<String, Object> task = service.create(request("T2"));
    String code = text(task, "task_code");
    observations.add(new ManualPorts.MarketingObservation(code, "生产中", 2, 1, 0, 1000));
    assertEquals(1L, number(service.reconcile(20, 0), "applied"));
    assertEquals(1L, number(object(service.detail(code).get("task")),
        "content_completed_count"));
    assertEquals(0L, number(service.reconcile(20, 0), "applied"));
    observations.set(0, new ManualPorts.MarketingObservation(code, "已完成", 2, 2, 0, 2000));
    assertEquals(502, assertThrows(BusinessException.class,
        () -> service.reconcile(20, 0)).status);
    observations.set(0, new ManualPorts.MarketingObservation(code, "已完成", 2, 3, 0, 3000));
    assertEquals(1L, number(service.reconcile(20, 0), "applied"));
    assertEquals("已完成", object(service.detail(code).get("task")).get("content_status"));
    assertEquals(0L, number(service.reconcile(20, 0), "applied"));
  }
}
