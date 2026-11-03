package com.stratmatrix.planning.config;

import static com.stratmatrix.planning.manual.Json.*;
import static org.junit.jupiter.api.Assertions.*;

import com.stratmatrix.planning.adapter.local.OutsideSourceAdapter;
import com.stratmatrix.planning.adapter.python.CatalogProjectionPythonClient;
import com.stratmatrix.planning.content.*;
import com.stratmatrix.planning.manual.*;
import com.stratmatrix.planning.source.SourceFacts;
import java.io.*;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.mybatis.spring.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.http.*;
import org.springframework.jdbc.datasource.*;
import org.springframework.web.client.RestTemplate;

/** Explicit live business DB acceptance. Raw facts use the normal daily Java facade. */
@EnabledIfSystemProperty(named = "planning.content-acceptance-properties", matches = ".+")
class OutsideContentBranchesAcceptanceTest {
  @Test
  void contentBranchesAgainstDailyJavaAndRealBusinessDatabase() throws Exception {
    Properties p = new Properties();
    try (InputStream in =
        Files.newInputStream(
            Paths.get(System.getProperty("planning.content-acceptance-properties")))) {
      p.load(in);
    }
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
        new ClassPathResource("mapper/SlotCompletionMapper.xml"),
        new ClassPathResource("mapper/BusinessPlanningConfigMapper.xml"));
    SqlSessionTemplate sql = new SqlSessionTemplate(f.getObject());
    ManualMapper mapper = sql.getMapper(ManualMapper.class);
    assertTrue(
        mapper.unlinkedMarketingTasks(1).isEmpty(),
        "Finish unrelated marketing demands before this acceptance");
    ManualRepository repo = new ManualRepository(mapper, tx);
    RestTemplate http =
        new RestTemplate(new org.springframework.http.client.SimpleClientHttpRequestFactory());
    SourceFacts facts = source(p, http);
    BusinessPlanningConfig test = new BusinessPlanningConfig();
    test.planning_days = Arrays.asList(1, 3, 5);
    test.marketing_max = 3;
    test.hotspot_ratio = 20;
    test.schedule_day = 2;
    test.schedule_time = "22:00";
    BusinessPlanningConfigService rules =
        new BusinessPlanningConfigService(sql.getMapper(BusinessPlanningConfigMapper.class), tx) {
          @Override
          public Result current() {
            return new Result(1, "content-acceptance-snapshot", test);
          }
        };
    Path fixture = Paths.get(p.getProperty("acceptance.fixture"));
    String prefix = p.getProperty("acceptance.prefix");
    LocalDate cycle = LocalDate.parse(p.getProperty("acceptance.cycle"));
    ContentBranchScenario.prepare(fixture, prefix, cycle);
    ManualPorts.Source catalog =
        new OutsideSourceAdapter(
            facts,
            new CatalogProjectionPythonClient(
                http,
                URI.create(p.getProperty("planning.legacy.base-url")),
                p.getProperty("planning.legacy.integration-token")));
    Map<String, Object> report =
        new ContentBranchScenario(
                repo,
                sql.getMapper(SlotCompletionMapper.class),
                facts,
                catalog,
                fixture,
                prefix,
                cycle,
                Long.parseLong(p.getProperty("acceptance.batch-id")))
            .run(rules);
    report.put("java_source", p.getProperty("acceptance.java-source"));
    Files.write(
        Paths.get(p.getProperty("acceptance.output"), "business.json"),
        write(report).getBytes(StandardCharsets.UTF_8));
  }

  static SourceFacts source(Properties p, RestTemplate http) {
    return new SourceFacts() {
      private Object call(String name, Map<String, Object> q) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.set("X-Integration-Token", p.getProperty("acceptance.java-token"));
        return http.exchange(
                URI.create(p.getProperty("acceptance.java-source") + "/" + name + "/query"),
                HttpMethod.POST,
                new HttpEntity<>(q, headers),
                Object.class)
            .getBody();
      }

      public Map<String, Object> accounts(Map<String, Object> q) {
        return object(call("accounts", q));
      }

      public Map<String, Object> topics(Map<String, Object> q) {
        return object(call("topics", q));
      }

      public Map<String, Object> marketingContents(Map<String, Object> q) {
        return object(call("marketing-contents", q));
      }

      public Object effectiveMarketing(Map<String, Object> q) {
        return call("effective-marketing", q);
      }

      public Object productionStatus(Map<String, Object> q) {
        return call("production-status", q);
      }

      public Object marketingStatus(Map<String, Object> q) {
        return call("marketing-status", q);
      }

      public Object approvedDemandContents(Map<String, Object> q) {
        return call("marketing-allocations", q);
      }
    };
  }
}
