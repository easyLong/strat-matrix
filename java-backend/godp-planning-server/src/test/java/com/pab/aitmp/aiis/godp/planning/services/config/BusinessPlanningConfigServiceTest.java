package com.pab.aitmp.aiis.godp.planning.services.config;

import com.pab.aitmp.aiis.godp.planning.entity.vo.req.BusinessPlanningConfig;

import static org.junit.jupiter.api.Assertions.*;

import com.pab.aitmp.aiis.godp.planning.server.dev.LocalManualBusinessSchema;
import java.util.Arrays;
import java.util.UUID;
import org.apache.ibatis.session.SqlSessionFactory;
import org.junit.jupiter.api.Test;
import org.mybatis.spring.SqlSessionFactoryBean;
import org.mybatis.spring.SqlSessionTemplate;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

class BusinessPlanningConfigServiceTest {
  @Test
  void savesRestoresAndRejectsStaleVersionWithoutChangingCurrentValue() throws Exception {
    DriverManagerDataSource dataSource = new DriverManagerDataSource(
        "jdbc:h2:mem:config-" + UUID.randomUUID()
            + ";MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1", "sa", "");
    LocalManualBusinessSchema.initialize(dataSource);
    SqlSessionFactoryBean factory = new SqlSessionFactoryBean();
    factory.setDataSource(dataSource);
    factory.setMapperLocations(new ClassPathResource("mapper/BusinessPlanningConfigMapper.xml"));
    SqlSessionFactory sessions = factory.getObject();
    BusinessPlanningConfigMapper mapper = new SqlSessionTemplate(sessions)
        .getMapper(BusinessPlanningConfigMapper.class);
    BusinessPlanningConfigService service = new BusinessPlanningConfigService(mapper,
        new DataSourceTransactionManager(dataSource));

    BusinessPlanningConfigService.ConfigConflict uninitialized = assertThrows(
        BusinessPlanningConfigService.ConfigConflict.class, service::current);
    assertEquals(409, uninitialized.status);
    BusinessPlanningConfig first = completeConfig();
    first.planning_days = Arrays.asList(5, 1, 3);
    first.hotspot_ratio = 25;
    first.content_production_lead_days.put("ordinary", 3);
    first.content_production_lead_days.put("marketing", 0);
    first.content_production_lead_days.put("hotspot", 1);
    assertEquals(1, service.save(first, 0, "UM001").version);
    assertEquals(Arrays.asList(1, 3, 5), service.current().config.planning_days);
    assertEquals(first.content_production_lead_days, service.current().config.content_production_lead_days);

    BusinessPlanningConfig second = completeConfig();
    second.marketing_max = 2;
    second.content_production_lead_days.put("hotspot", 2);
    assertEquals(2, service.save(second, 1, "UM002").version);
    BusinessPlanningConfigService.ConfigConflict stale = assertThrows(
        BusinessPlanningConfigService.ConfigConflict.class,
        () -> service.save(first, 1, "UM003"));
    assertEquals(409, stale.status);
    assertEquals(2, service.current().config.marketing_max);

    assertEquals(3, service.restore(1, 2, "UM004").version);
    assertEquals(25, service.current().config.hotspot_ratio);
    assertEquals(first.content_production_lead_days, service.current().config.content_production_lead_days);
    assertEquals("恢复", service.versions(10).get(0).action);
    assertEquals(1, service.versions(10).get(0).source_version);
    assertEquals("UM004", service.versions(10).get(0).created_by);
  }

  @Test
  void rejectsInvalidScheduleBeforePersisting() throws Exception {
    BusinessPlanningConfig invalid = completeConfig();
    invalid.schedule_time = "25:99";
    assertThrows(IllegalArgumentException.class, invalid::validate);
    invalid.schedule_time = "22:00";
    invalid.planning_days = Arrays.asList(1, 1);
    assertThrows(IllegalArgumentException.class, invalid::validate);
    assertThrows(IllegalArgumentException.class, new BusinessPlanningConfig()::validate);
    BusinessPlanningConfig invalidTiming = completeConfig();
    invalidTiming.content_production_lead_days.put("ordinary", -1);
    assertThrows(IllegalArgumentException.class, invalidTiming::validate);
    invalidTiming.content_production_lead_days.put("ordinary", 366);
    assertThrows(IllegalArgumentException.class, invalidTiming::validate);
    invalidTiming.content_production_lead_days.clear();
    invalidTiming.content_production_lead_days.put("unknown", 1);
    assertThrows(IllegalArgumentException.class, invalidTiming::validate);
  }

  private static BusinessPlanningConfig completeConfig() {
    BusinessPlanningConfig config = new BusinessPlanningConfig();
    config.planning_days = Arrays.asList(1, 3, 5);
    config.schedule_day = 2;
    config.schedule_time = "22:00";
    config.marketing_max = 1;
    config.hotspot_ratio = 20;
    return config;
  }
}
