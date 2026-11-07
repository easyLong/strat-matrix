package com.pab.aitmp.aiis.godp.planning.services.config;

import com.pab.aitmp.aiis.godp.planning.services.persistence.SqlRows;
import com.pab.aitmp.aiis.godp.planning.entity.command.*;

import com.pab.aitmp.aiis.godp.planning.api.port.AlgorithmConfigPort;
import com.pab.aitmp.aiis.godp.planning.entity.support.Json;

import static com.pab.aitmp.aiis.godp.planning.entity.support.Json.*;
import static org.junit.jupiter.api.Assertions.*;

import com.pab.aitmp.aiis.godp.planning.entity.error.BusinessException;
import com.pab.aitmp.aiis.godp.planning.server.dev.LocalManualBusinessSchema;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.mybatis.spring.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.*;
import org.springframework.web.client.ResourceAccessException;

class ConfigReleaseServiceTest {
  @Test
  void lostAlgorithmReplyResumesSameCommandAndPublishesBothConfigurations() throws Exception {
    DriverManagerDataSource ds =
        new DriverManagerDataSource(
            "jdbc:h2:mem:release-"
                + UUID.randomUUID()
                + ";MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1",
            "sa",
            "");
    LocalManualBusinessSchema.initialize(ds);
    SqlSessionFactoryBean f = new SqlSessionFactoryBean();
    f.setDataSource(ds);
    f.setMapperLocations(
        new ClassPathResource("mapper/BusinessPlanningConfigMapper.xml"),
        new ClassPathResource("mapper/ConfigReleaseMapper.xml"));
    SqlSessionTemplate sql = new SqlSessionTemplate(f.getObject());
    ConfigReleaseMapper releases = sql.getMapper(ConfigReleaseMapper.class);
    BusinessConfigDatabase db =
        new BusinessConfigDatabase(
            sql.getMapper(BusinessPlanningConfigMapper.class),
            new DataSourceTransactionManager(ds));
    BusinessPlanningConfigService business =
        new BusinessPlanningConfigService(db.mapper, db.transactionManager, releases);
    Map<String, Object> initial =
        map(
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
            "rolling_window_posts",
            10);
    Map<String, Map<String, Object>> accepted = new HashMap<>();
    int[] count = {0};
    AlgorithmConfigPort algorithm =
        new AlgorithmConfigPort() {
          public Map<String, Object> current() {
            return map("version", 4, "config", initial);
          }

          public Map<String, Object> apply(
              String id, int expected, Map<String, Object> cfg, String actor) {
            assertFalse(cfg.containsKey("content_production_lead_days"));
            if (accepted.containsKey(id)) return accepted.get(id);
            count[0]++;
            Map<String, Object> normalized = new LinkedHashMap<>(initial);
            normalized.putAll(cfg);
            Map<String, Object> result = map("version", expected + 1, "config", normalized);
            accepted.put(id, result);
            if (count[0] == 1) throw new ResourceAccessException("accepted but response lost");
            return result;
          }
        };
    ConfigReleaseService service = new ConfigReleaseService(releases, business, db, algorithm);
    assertEquals(4, number(service.current(), "version"));
    Map<String, Object> changed = new LinkedHashMap<>(initial);
    changed.put("planning_days", Arrays.asList(2, 4));
    changed.put("rolling_window_posts", 15);
    changed.put("content_production_lead_days", map("ordinary", 3, "marketing", 0, "hotspot", 1));
    assertEquals(
        503, assertThrows(BusinessException.class, () -> service.save(changed, 4, "UM001")).status);
    assertNotNull(SqlRows.one(releases.pending()));
    assertThrows(BusinessPlanningConfigService.ConfigConflict.class, () -> business.current());
    assertThrows(BusinessException.class, () -> service.current());
    service.advancePending();
    assertEquals(1, count[0]);
    assertNull(SqlRows.one(releases.pending()));
    assertEquals(5, number(service.current(), "version"));
    assertEquals(Arrays.asList(2, 4), business.current().config.planning_days);
    assertEquals(15, object(service.current().get("config")).get("rolling_window_posts"));
    assertEquals(3, business.current().config.content_production_lead_days.get("ordinary"));
    assertEquals(0, business.current().config.content_production_lead_days.get("marketing"));
    assertEquals(map("ordinary", 3, "marketing", 0, "hotspot", 1), object(service.current().get("config")).get("content_production_lead_days"));
    service.restore(4, 5, "UM002");
    assertEquals(Arrays.asList(1, 3, 5), business.current().config.planning_days);
    assertTrue(business.current().config.content_production_lead_days.isEmpty());
    assertEquals(6, number(service.current(), "version"));
    assertEquals(3, service.versions(30).size());
  }
}
