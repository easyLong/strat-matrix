package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual;

import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.ManualMapper;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.ManualPorts;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.error.BusinessException;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json;
import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.controller.ManualPlanningController;

import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.dev.LocalManualBusinessSchema;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.util.TestPropertyValues;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

/** Host wiring must work with ports and a managed database, without local adapters. */
class ManualHostWiringTest {
  @Test
  void wiresUnchangedBusinessModuleFromHostProvidedPorts() {
    DriverManagerDataSource dataSource = new DriverManagerDataSource(
        "jdbc:h2:mem:host-" + UUID.randomUUID()
            + ";MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1", "sa", "");
    LocalManualBusinessSchema.initialize(dataSource);
    try (AnnotationConfigApplicationContext context = new AnnotationConfigApplicationContext()) {
      TestPropertyValues.of("planning.manual.enabled=true").applyTo(context);
      context.registerBean(ManualMapper.class, () -> ManualTestMapper.bind(dataSource));
      context.registerBean("xiangliangBusinessTransactions", org.springframework.transaction.PlatformTransactionManager.class,
          () -> new DataSourceTransactionManager(dataSource));
      context.registerBean(ManualPorts.Source.class, () -> new ManualPorts.Source() {
        public List<Map<String, Object>> accountOptions(int limit, boolean includeDisabled) {
          return Collections.emptyList();
        }
        public Map<String, Object> topicDetail(String topicId, String topicType) {
          return Json.map("topic_id", topicId);
        }
        public Map<String, Object> snapshot(List<String> accounts, List<String> topics) {
          return Json.map("accounts", Collections.emptyList(), "topics", Collections.emptyList());
        }
        public Set<String> historicalPlanned(String date) { return Collections.emptySet(); }
        public Set<String> historicalReserved(String date) { return Collections.emptySet(); }
        public Map<String, Object> sourceAccounts(List<String> accountIds) {
          return Json.map("accounts", Collections.emptyList());
        }
        public List<Map<String, Object>> topicCandidates(int limit) {
          return Collections.emptyList();
        }
      });
      context.registerBean(ManualPorts.Computer.class, () -> input -> Collections.emptyMap());
      context.registerBean(ManualPorts.Actor.class, () -> () -> "host-user");
      context.registerBean(ManualPorts.Transition.class, ManualNewInstallTransition::new);
      context.registerBean(ManualPorts.ContentStatusSource.class,
          () -> candidates -> Collections.emptyList());
      context.registerBean(ManualPorts.MarketingStatusSource.class,
          () -> taskCodes -> Collections.emptyList());
      // Other suppliers may already use these conventional names in the same host.
      context.registerBean("manualRepository", String.class, () -> "host-repository");
      context.registerBean("manualPlanningService", String.class, () -> "host-service");
      context.registerBean("manualPlanningController", String.class, () -> "host-controller");
      context.register(ManualModuleConfiguration.class, ManualPlanningController.class);
      context.refresh();
      assertEquals("host-repository", context.getBean("manualRepository"));
      assertEquals("host-service", context.getBean("manualPlanningService"));
      assertEquals("host-controller", context.getBean("manualPlanningController"));
      assertSame(context.getBean(ManualRepository.class), context.getBean("xiangliangManualRepository"));
      assertSame(context.getBean(ManualPlanningController.class),
          context.getBean("xiangliangManualPlanningController"));
      com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.BusinessTransactions boundary=context.getBean(
          com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.BusinessTransactions.class);
      assertTrue(org.springframework.aop.support.AopUtils.isAopProxy(boundary));
      org.springframework.jdbc.core.JdbcTemplate jdbc=new org.springframework.jdbc.core.JdbcTemplate(dataSource);
      assertThrows(IllegalStateException.class,() -> boundary.required(() -> {
        jdbc.update("INSERT INTO godp_manual_preview(preview_code,payload,expires_at,created_at) VALUES('ROLLBACK','{}',0,0)");
        throw new IllegalStateException("rollback");
      }));
      assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM godp_manual_preview",Integer.class));
      assertNotNull(context.getBean(ManualRepository.class));
      assertNotNull(context.getBean(ManualPlanningService.class));
      assertNotNull(context.getBean(ManualQueryService.class));
      assertNotNull(context.getBean(ManualItemService.class));
      assertNotNull(context.getBean(ManualContentStatusService.class));
      assertNotNull(context.getBean(MarketingTaskService.class));
      assertNotNull(context.getBean(ManualExportService.class));
      assertEquals("host-user", context.getBean(ManualPorts.Actor.class).current());
      ManualPlanningController page = context.getBean(ManualPlanningController.class);
      com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.req.CatalogQueryRequest query = new com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.req.CatalogQueryRequest();
      query.limit = 20;
      query.topicType = "普通";
      assertEquals(Collections.emptyList(), page.accountsCatalog(query));
      assertEquals(Collections.emptyList(), page.topicsCatalog(query));
      assertEquals("T1", ((Map<?, ?>) page.topicDetail("T1", query)).get("topic_id"));
      query.limit = 1001;
      assertThrows(BusinessException.class, () -> page.topicsCatalog(query));
    }
  }
}
