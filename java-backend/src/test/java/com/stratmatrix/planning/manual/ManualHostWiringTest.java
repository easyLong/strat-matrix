package com.stratmatrix.planning.manual;

import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import com.stratmatrix.standalone.LocalManualBusinessSchema;
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
      context.registerBean(ManualDatabase.class,
          () -> new ManualDatabase(ManualTestMapper.bind(dataSource),
              new DataSourceTransactionManager(dataSource)));
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
      context.register(ManualModuleConfiguration.class, ManualPlanningController.class);
      context.refresh();
      assertNotNull(context.getBean(ManualRepository.class));
      assertNotNull(context.getBean(ManualPlanningService.class));
      assertNotNull(context.getBean(ManualQueryService.class));
      assertNotNull(context.getBean(ManualItemService.class));
      assertNotNull(context.getBean(ManualContentStatusService.class));
      assertNotNull(context.getBean(MarketingTaskService.class));
      assertNotNull(context.getBean(ManualExportService.class));
      assertEquals("host-user", context.getBean(ManualPorts.Actor.class).current());
      ManualPlanningController page = context.getBean(ManualPlanningController.class);
      assertEquals(Collections.emptyList(), page.accountsCatalog(20, false));
      assertEquals(Collections.emptyList(), page.topicsCatalog(20));
      assertEquals("T1", ((Map<?, ?>) page.topicDetail("T1", "\u666e\u901a")).get("topic_id"));
      assertThrows(BusinessException.class, () -> page.topicsCatalog(1001));
    }
  }
}
