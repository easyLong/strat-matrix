package com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.config;

import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.dev.local.*;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.*;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.host.HostAccess;
import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.ManualPorts;
import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.SourceFacts;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.error.BusinessException;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json;
import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.dev.local.FixtureSourceFacts;
import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.dev.local.LocalPythonAdapter;
import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.AutoScheduleMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.BusinessPlanningConfigMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.ConfigReleaseMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.SlotCompletionMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.ManualMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.PlanningQueryMapper;

import static com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.query.ReadDatabaseFixture;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.tasks.PlanningTaskService;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.tasks.PlanningTaskService.Kind;
import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.dev.LocalJobPulse;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import org.mybatis.spring.*;
import org.springframework.boot.test.util.TestPropertyValues;
import org.springframework.context.annotation.*;
import org.springframework.core.io.ClassPathResource;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.persistence.BusinessMapperSupport;
import org.springframework.http.*;
import org.springframework.mock.http.client.MockClientHttpRequest;
import org.springframework.mock.web.MockServletContext;
import org.springframework.test.web.client.ExpectedCount;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.test.web.client.response.MockRestResponseCreators;
import org.springframework.test.web.servlet.*;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.context.support.AnnotationConfigWebApplicationContext;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

/**
 * All real modules/controllers/MyBatis SQL, isolated H2 and a deterministic HTTP algorithm stub.
 */
class InsideThreePagesAcceptanceTest {
  @Configuration
  @EnableWebMvc
  @Import(PlanningHostConfiguration.class)
  static class Host {
    @Bean
    ReadDatabaseFixture database() throws Exception {
      return new ReadDatabaseFixture(true);
    }

    @Bean("xiangliangBusinessSessions")
    SqlSessionTemplate sessions(ReadDatabaseFixture f) throws Exception {
      SqlSessionFactoryBean factory = new SqlSessionFactoryBean();
      factory.setDataSource(f.ds);
      factory.setMapperLocations(BusinessMapperSupport.businessXml());
      return new SqlSessionTemplate(factory.getObject());
    }

    @Bean("xiangliangBusinessTransactions")
    org.springframework.transaction.PlatformTransactionManager tx(ReadDatabaseFixture f) {
      return new org.springframework.jdbc.datasource.DataSourceTransactionManager(f.ds);
    }

    @Bean("xiangliangPythonHttp")
    RestTemplate http() {
      return new RestTemplate();
    }

    @Bean
    ManualPorts.Actor actor() {
      return () -> "HOST-UM";
    }

    @Bean
    HostAccess access() {
      return request -> {
        if ("yes".equals(request.getHeader("X-Deny"))) throw new BusinessException(403, "没有访问权限");
      };
    }

    @Bean
    com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.SourceFacts facts() {
      return new com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.SourceFacts() {
        public Map<String, Object> accounts(Map<String, Object> q) {
          List<Map<String, Object>> accounts =
              new ArrayList<>(Collections.singletonList(account()));
          if (q.get("account_ids") instanceof List)
            accounts.removeIf(a -> !((List<?>) q.get("account_ids")).contains(a.get("account_id")));
          return page(q, accounts);
        }

        public Map<String, Object> topics(Map<String, Object> q) {
          List<Map<String, Object>> topics =
              new ArrayList<>(Arrays.asList(topic("T1"), topic("T2"), marketingTopic(false), marketingTopic(true)));
          if (q.get("topic_ids") instanceof List)
            topics.removeIf(t -> !((List<?>) q.get("topic_ids")).contains(t.get("topic_id")));
          return page(q, topics);
        }

        public Map<String, Object> marketingContents(Map<String, Object> q) {
          return page(q, Collections.emptyList());
        }

        public Object effectiveMarketing(Map<String, Object> q) {
          return Collections.emptyList();
        }

        public Object productionStatus(Map<String, Object> q) {
          return Collections.emptyList();
        }

        public Object marketingStatus(Map<String, Object> q) {
          return Collections.emptyList();
        }

        public Object approvedDemandContents(Map<String, Object> q) {
          return Collections.emptyList();
        }
      };
    }

    private Map<String, Object> page(Map<String, Object> q, List<Map<String, Object>> items) {
      int page = ((Number) q.getOrDefault("page_no", 1)).intValue(),
          size = ((Number) q.getOrDefault("page_size", 100)).intValue();
      int start = (int) Math.min(items.size(), (long) (page - 1) * size);
      return map(
          "items",
          items.subList(start, Math.min(items.size(), start + size)),
          "total",
          items.size(),
          "page_no",
          page,
          "page_size",
          size);
    }
  }

  static Map<String, Object> account() {
    return map(
        "account_id",
        "A1",
        "account_name",
        "现场模拟账号",
        "um_no",
        "UM1",
        "organization",
        "深圳二级分行",
        "platform",
        "抖音",
        "account_type",
        "认证",
        "followers",
        100,
        "lifecycle_stage",
        "流量增长期");
  }

  static Map<String, Object> topic(String id) {
    return map(
        "topic_id",
        id,
        "title",
        "选题" + id,
        "topic_title",
        "选题" + id,
        "outline",
        "测试大纲",
        "content_type",
        "金融科普",
        "topic_type",
        "普通",
        "is_marketing",
        false,
        "valid_from",
        "2026-01-01",
        "valid_to",
        "2027-12-31");
  }

  static Map<String, Object> marketingTopic(boolean product) {
    Map<String, Object> row = topic(product ? "M-PRODUCT" : "M-ACTIVITY");
    row.put("is_marketing", true);
    row.put("topic_type", "营销");
    row.put("title", "");
    row.put("topic_title", "");
    row.put("outline", "");
    row.put("content_type", product ? "银行产品类" : "活动类");
    if (product) {
      row.put("related_product", "测试银行产品");
      row.put("related_product_id", "PRODUCT-001");
    } else {
      row.put("related_activity", "测试营销活动");
      row.put("related_activity_id", "ACTIVITY-001");
      row.put("activity_organization", "测试二级分行");
    }
    return row;
  }

  static Map<String, Object> taxonomy() {
    Map<String, Object> items = new LinkedHashMap<>();
    for (int i = 1; i <= 5; i++)
      items.put(
          "T" + i,
          Collections.singletonList(
              map(
                  "id",
                  "tag" + i,
                  "name",
                  i == 1 ? "非营销" : i == 2 ? "流量" : "标签" + i,
                  "enabled",
                  true)));
    return items;
  }

  static Map<String, Object> config() {
    String[] names = {"冷启动期", "流量增长期", "转化试探期", "转化放大期", "稳定经营期"};
    int[] weights = {80, 70, 50, 30, 50};
    List<Map<String, Object>> targets = new ArrayList<>(), rules = new ArrayList<>();
    for (int i = 0; i < 5; i++)
      targets.add(map("name", names[i], "traffic", weights[i], "conversion", 100 - weights[i]));
    int[] boundaries = {0, 50, 100, 200, 500};
    for (int i = 4; i > 0; i--)
      rules.add(
          map(
              "name",
              names[i],
              "catchAll",
              false,
              "condition_mode",
              "grouped",
              "conditions",
              Collections.singletonList(
                  map(
                      "field",
                      "followers_count",
                      "operator",
                      "gte",
                      "value",
                      boundaries[i],
                      "join",
                      "AND"))));
    rules.add(map("name", names[0], "catchAll", true, "conditions", Collections.emptyList()));
    return map(
        "planning_days",
        Arrays.asList(1, 3, 5),
        "schedule_day",
        2,
        "schedule_time",
        "22:00",
        "marketing_max",
        3,
        "hotspot_ratio",
        20,
        "rolling_posts",
        10,
        "lifecycle_rules",
        rules,
        "stage_targets",
        targets);
  }

  static class Algorithm {
    Map<String, Object> config = config();
    int version = 1;
    int tags = 1;
    Map<String, Map<String, Object>> jobs = new HashMap<>();
    final AtomicBoolean down = new AtomicBoolean();
    String taxonomyActor;

    void bind(RestTemplate http) {
      MockRestServiceServer server = MockRestServiceServer.bindTo(http).build();
      server
          .expect(
              ExpectedCount.manyTimes(),
              request ->
                  assertEquals("test-token", request.getHeaders().getFirst("X-Integration-Token")))
          .andRespond(
              request -> {
                String path = request.getURI().getPath();
                assertEquals(path.equals("/api/health") ? HttpMethod.GET : HttpMethod.POST,
                    request.getMethod(), "正式Java到Python业务调用必须使用POST");
                String raw = ((MockClientHttpRequest) request).getBodyAsString();
                Map<String, Object> body = raw.isEmpty() ? map() : read(raw);
                if (down.get())
                  return MockRestResponseCreators.withStatus(HttpStatus.SERVICE_UNAVAILABLE)
                      .body("unavailable")
                      .createResponse(request);
                Map<String, Object> result;
                HttpStatus status = HttpStatus.OK;
                if (path.equals("/api/health")) result = map("service", "ok", "database", "ok");
                else if (path.equals("/api/internal/algorithm-config/query"))
                  result = map("version", version, "config", config);
                else if (path.equals("/api/internal/algorithm-config/commands")) {
                  assertEquals(version, number(body, "expected_version"));
                  config.putAll(object(body.get("algorithm_config")));
                  version++;
                  result = map("version", version, "config", config);
                } else if (path.equals("/api/tag-taxonomy/query") || path.equals("/api/tag-taxonomy/save")) {
                  if (path.endsWith("/save")) {
                    taxonomyActor = request.getHeaders().getFirst("X-Operator-Id");
                    if (number(body, "expected_version") != tags)
                      return MockRestResponseCreators.withStatus(HttpStatus.CONFLICT)
                          .contentType(MediaType.APPLICATION_JSON)
                          .body(write(map("detail", "标签版本冲突")))
                          .createResponse(request);
                    tags++;
                  }
                  result = map("version", tags, "items", taxonomy());
                } else if (path.equals("/api/internal/catalog-projection"))
                  result =
                      map(
                          "accounts",
                          body.get("accounts"),
                          "topics",
                          body.get("topics"),
                          "algorithm_version",
                          "v" + version);
                else if (path.equals("/api/internal/manual-computations")) {
                  status = HttpStatus.ACCEPTED;
                  String id = text(body, "request_id");
                  boolean existing = jobs.containsKey(id);
                  jobs.putIfAbsent(id, body);
                  result =
                      map(
                          "request_id",
                          id,
                          "status",
                          existing ? "succeeded" : "pending",
                          "result",
                          existing
                              ? map(
                                  "algorithm_version",
                                  body.get("algorithm_version"),
                                  "items",
                                  Collections.singletonList(
                                      map(
                                          "account_id",
                                          "A1",
                                          "topic_id",
                                          "T1",
                                          "lifecycle_stage",
                                          "流量增长期")))
                              : null);
                } else if (path.equals("/api/internal/wakeup")) {
                  status = HttpStatus.ACCEPTED;
                  result =
                      map(
                          "status",
                          "accepted",
                          "accepted_jobs",
                          body.get("jobs"),
                          "coalesced_jobs",
                          Collections.emptyList());
                } else throw new AssertionError("Unexpected algorithm path: " + path);
                return MockRestResponseCreators.withStatus(status)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(write(result))
                    .createResponse(request);
              });
    }
  }

  static Map<String, Object> json(MvcResult r) throws Exception {
    return read(r.getResponse().getContentAsString(java.nio.charset.StandardCharsets.UTF_8));
  }

  static org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder query(
      String view, Map<String, Object> body) {
    return post("/api/plan/query/" + view)
        .contentType(MediaType.APPLICATION_JSON)
        .content(write(body));
  }

  static String[] insideSettings() {
    return new String[] {
      "planning.host.enabled=true",
      "planning.manual.enabled=true",
      "planning.business-config.enabled=true",
      "planning.config-release.enabled=true",
      "planning.auto-schedule.enabled=true",
      "planning.history.mode=business_only",
      "planning.tasks.enabled=true",
      "planning.source.enabled=true",
      "planning.source.token=test-source-token",
      "planning.python.base-url=http://algorithm.test",
      "planning.python.token=test-token"
    };
  }

  @Test
  void everyRequiredHostBindingFailsClosedWhenMissing() {
    for (String missing :
        Arrays.asList(
            "xiangliangBusinessSessions",
            "xiangliangBusinessTransactions",
            "xiangliangPythonHttp",
            "actor",
            "access",
            "facts")) {
      try (AnnotationConfigWebApplicationContext context =
          new AnnotationConfigWebApplicationContext()) {
        context.setServletContext(new MockServletContext());
        context.getEnvironment().setActiveProfiles("inside");
        TestPropertyValues.of(insideSettings()).applyTo(context);
        context.register(Host.class);
        context.addBeanFactoryPostProcessor(
            factory ->
                ((org.springframework.beans.factory.support.BeanDefinitionRegistry) factory)
                    .removeBeanDefinition(missing));
        assertThrows(org.springframework.beans.BeansException.class, context::refresh, missing);
      }
    }
  }

  @Test
  void allThreePagesWorkWithNoOutsideComponents() throws Exception {
    try (AnnotationConfigWebApplicationContext context =
        new AnnotationConfigWebApplicationContext()) {
      context.setServletContext(new MockServletContext());
      context.getEnvironment().setActiveProfiles("inside");
      TestPropertyValues.of(insideSettings()).applyTo(context);
      context.register(Host.class);
      context.refresh();
      org.springframework.jdbc.core.JdbcTemplate runtimeSql = context.getBean(ReadDatabaseFixture.class).jdbc;
      assertEquals("planning_runtime", runtimeSql.queryForObject("SELECT CURRENT_USER", String.class));
      assertThrows(org.springframework.dao.DataAccessException.class,
          () -> runtimeSql.execute("CREATE TABLE must_not_create(id INT)"));
      assertThrows(org.springframework.dao.DataAccessException.class,
          () -> runtimeSql.execute("ALTER TABLE godp_planning_batch ADD must_not_alter INT"));
      assertTrue(context.getBeansOfType(LocalJobPulse.class).isEmpty());
      assertTrue(context.getBeansOfType(FixtureSourceFacts.class).isEmpty());
      assertTrue(context.getBeansOfType(LocalPythonAdapter.class).isEmpty());
      Algorithm algorithm = new Algorithm();
      algorithm.bind(context.getBean("xiangliangPythonHttp", RestTemplate.class));
      MockMvc mvc = MockMvcBuilders.webAppContextSetup(context).build();
      mvc.perform(get("/api/plan/health"))
          .andExpect(status().isOk())
          .andExpect(jsonPath("$.database").value("ok"));
      mvc.perform(post("/api/plan/config/query").contentType(MediaType.APPLICATION_JSON).content("{}"))
          .andExpect(status().isOk())
          .andExpect(jsonPath("$.version").value(1));
      Map<String, Object> changed = config();
      changed.put("marketing_max", 4);
      mvc.perform(
              post("/api/plan/config/save")
                  .contentType(MediaType.APPLICATION_JSON)
                  .content(write(map("config", changed, "expectedVersion", 1))))
          .andExpect(status().isOk())
          .andExpect(jsonPath("$.version").value(2));
      mvc.perform(post("/api/plan/config/versions/query").contentType(MediaType.APPLICATION_JSON).content("{}"))
          .andExpect(status().isOk())
          .andExpect(jsonPath("$[0].version").value(2));
      mvc.perform(post("/api/plan/config/versions/1/restore").contentType(MediaType.APPLICATION_JSON).content("{\"expectedVersion\":2}"))
          .andExpect(status().isOk())
          .andExpect(jsonPath("$.version").value(3));
      mvc.perform(post("/api/plan/tag-taxonomy/query").contentType(MediaType.APPLICATION_JSON).content("{}")).andExpect(status().isOk());
      mvc.perform(
              post("/api/plan/tag-taxonomy/save")
                  .header("X-Operator-Id", "FORGED")
                  .contentType(MediaType.APPLICATION_JSON)
                  .content(write(map("expected_version", 1, "items", taxonomy()))))
          .andExpect(status().isOk());
      assertEquals("HOST-UM", algorithm.taxonomyActor);
      mvc.perform(
              post("/api/plan/tag-taxonomy/save")
                  .contentType(MediaType.APPLICATION_JSON)
                  .content("{\"expected_version\":1,\"items\":{}}"))
          .andExpect(status().isConflict());
      mvc.perform(post("/api/plan/accounts/query").contentType(MediaType.APPLICATION_JSON).content("{}"))
          .andExpect(status().isOk())
          .andExpect(jsonPath("$[0].account_id").value("A1"));
      mvc.perform(post("/api/plan/topics/query").contentType(MediaType.APPLICATION_JSON).content("{}")).andExpect(status().isOk());
      mvc.perform(post("/api/plan/topics/T1/detail/query").contentType(MediaType.APPLICATION_JSON).content("{}")).andExpect(status().isOk());
      Map<String, Object> input =
          map(
              "content_mode",
              "non_marketing",
              "task_name",
              "行内装配验收",
              "publish_date",
              "2026-11-04",
              "account_ids",
              Collections.singletonList("A1"),
              "target_count",
              1,
              "topic_ids",
              Collections.singletonList("T1"),
              "note",
              "");
      String preview =
          text(
              json(
                  mvc.perform(
                          post("/api/plan/manual-plans/previews")
                              .contentType(MediaType.APPLICATION_JSON)
                              .content(write(input)))
                      .andExpect(status().isCreated())
                      .andReturn()),
              "preview_id");
      Map<String, Object> submitted =
          json(
              mvc.perform(post("/api/plan/manual-plans/previews/" + preview + "/submit"))
                  .andExpect(status().isAccepted())
                  .andReturn());
      mvc.perform(post("/api/plan/manual-plans/previews/" + preview + "/submit"))
          .andExpect(status().isAccepted())
          .andExpect(jsonPath("$.id").value(number(submitted, "id")));
      PlanningTaskService tasks = context.getBean(PlanningTaskService.class);
      Instant now = Instant.parse("2026-11-03T08:00:00Z");
      tasks.run(Kind.MANUAL, now, 100, 0);
      tasks.run(Kind.MANUAL, now, 100, 0);
      Map<String, Object> page =
          json(
              mvc.perform(query("manual-tasks", map("page", 1, "page_size", 10, "filters", map())))
                  .andExpect(status().isOk())
                  .andExpect(jsonPath("$.total").value(1))
                  .andReturn());
      long batch = number(rows(page.get("items")).get(0), "batch_id");
      assertTrue(batch > 0);
      mvc.perform(
              query(
                  "plans",
                  map(
                      "mode",
                      "account",
                      "account_id",
                      "A1",
                      "page",
                      1,
                      "page_size",
                      20,
                      "filters",
                      map("planType", "all", "contentType", "all"))))
          .andExpect(status().isOk())
          .andExpect(jsonPath("$.summary.accounts").value(1));
      mvc.perform(query("accounts", map("page", 1, "page_size", 10, "filters", map())))
          .andExpect(status().isOk())
          .andExpect(jsonPath("$.total").value(1));
      mvc.perform(query("periods", map("page", 1, "page_size", 10, "filters", map())))
          .andExpect(status().isOk())
          .andExpect(jsonPath("$.total").value(1));
      Map<String, Object> plans =
          json(
              mvc.perform(
                      query(
                          "plans",
                          map(
                              "mode",
                              "batch",
                              "batch_id",
                              batch,
                              "page",
                              1,
                              "page_size",
                              10,
                              "filters",
                              map())))
                  .andExpect(status().isOk())
                  .andExpect(jsonPath("$.summary.accounts").value(1))
                  .andReturn());
      long item = number(rows(plans.get("items")).get(0), "id");
      mvc.perform(
              post("/api/plan/items/" + item + "/replace-topic")
                  .contentType(MediaType.APPLICATION_JSON)
                  .content("{\"new_topic_id\":\"T2\",\"expected_version\":1,\"reason\":\"验收替换\"}"))
          .andExpect(status().isOk());
      mvc.perform(post("/api/plan/items/" + item + "/adjustments/query").contentType(MediaType.APPLICATION_JSON).content("{}"))
          .andExpect(status().isOk())
          .andExpect(jsonPath("$[0].new_topic_id").value("T2"));
      mvc.perform(
              query(
                  "export",
                  map("mode", "batch", "batch_id", batch, "format", "csv", "filters", map())))
          .andExpect(status().isOk())
          .andExpect(header().string("Content-Disposition", "attachment; filename=planning.csv"));
      mvc.perform(
              post("/api/plan/manual-plans/marketing-tasks")
                  .contentType(MediaType.APPLICATION_JSON)
                  .content(
                      write(
                          map(
                              "request_id",
                              UUID.randomUUID().toString(),
                              "task_name",
                              "营销需求验收",
                              "topic_id",
                              "M-ACTIVITY",
                              "allocation_count",
                              2))))
          .andExpect(status().isCreated());
      for (Kind kind : Kind.values()) {
        if (kind == Kind.CONTENT_FLOW) {
          assertEquals(503, assertThrows(BusinessException.class, () -> tasks.run(kind, now, 100, 0)).status);
        } else assertNotNull(tasks.run(kind, now, 100, 0));
      }
      mvc.perform(post("/api/plan/config/query").contentType(MediaType.APPLICATION_JSON).content("{}").header("X-Deny", "yes"))
          .andExpect(status().isForbidden());
      mvc.perform(
              post("/api/plan/internal/source/accounts/query")
                  .contentType(MediaType.APPLICATION_JSON)
                  .content("{}"))
          .andExpect(status().isUnauthorized());
      mvc.perform(
              post("/api/plan/internal/source/accounts/query")
                  .header("X-Integration-Token", "test-source-token")
                  .contentType(MediaType.APPLICATION_JSON)
                  .content("{}"))
          .andExpect(status().isOk());
      mvc.perform(post("/api/plan/internal/wakeup")).andExpect(status().isNotFound());
      for (String removed : Arrays.asList(
          "/config", "/config/versions", "/tag-taxonomy", "/accounts", "/topics",
          "/topics/T1/detail", "/manual-plans/account-availability", "/manual-plans/tasks",
          "/manual-plans/marketing-tasks", "/manual-plans/marketing-tasks/OLD-TASK",
          "/batches", "/batches/1", "/items/1/adjustments", "/items/1/replacement-candidates",
          "/business-config", "/business-config/versions")) {
        mvc.perform(get("/api/plan" + removed)).andExpect(result ->
            assertTrue(Arrays.asList(404, 405).contains(result.getResponse().getStatus()), removed));
      }
      for (String removed : Arrays.asList("/config", "/tag-taxonomy", "/business-config")) {
        mvc.perform(put("/api/plan" + removed).contentType(MediaType.APPLICATION_JSON).content("{}"))
            .andExpect(result -> assertTrue(Arrays.asList(404, 405).contains(result.getResponse().getStatus()), removed));
      }
      mvc.perform(post("/api/plan/batches/manual")).andExpect(status().isNotFound());
      mvc.perform(post("/api/plan/config/versions/1/restore").param("expected_version", "3"))
          .andExpect(status().isUnprocessableEntity());
      InsideBrowserBridge.run(mvc);
      algorithm.down.set(true);
      mvc.perform(get("/api/plan/health")).andExpect(status().isServiceUnavailable());
      mvc.perform(query("periods", map("page", 1, "page_size", 10, "filters", map())))
          .andExpect(status().isOk());
    }
  }
}
