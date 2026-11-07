package com.pab.aitmp.aiis.godp.planning.services.manual;

import com.pab.aitmp.aiis.godp.planning.api.port.ManualPorts;
import com.pab.aitmp.aiis.godp.planning.api.port.PlanningReadQueries;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import com.pab.aitmp.aiis.godp.planning.api.port.BusinessTransactions;
import com.pab.aitmp.aiis.godp.planning.services.persistence.DeclarativeBusinessTransactions;

/** Stable service wiring. Local development and the host supply only the ports and database. */
@Configuration
@EnableTransactionManagement
@ConditionalOnProperty(name = "planning.manual.enabled", havingValue = "true")
public class ManualModuleConfiguration {
  @Bean public BusinessTransactions businessTransactions() { return new DeclarativeBusinessTransactions(); }
  @Bean
  public ManualRepository manualRepository(ManualMapper mapper, BusinessTransactions transactions) {
    return new ManualRepository(mapper, transactions);
  }

  @Bean
  public ManualPlanningService manualPlanningService(
      ManualRepository repository,
      ManualPorts.Source source,
      ManualPorts.Computer computer,
      ManualPorts.Actor actor) {
    return new ManualPlanningService(repository, source, computer, actor);
  }

  @Bean
  public ManualQueryService manualQueryService(
      ManualRepository repository,
      ManualPlanningService service,
      ManualPorts.Source source,
      ManualPorts.Transition transition,
      MarketingTaskService marketing,
      org.springframework.beans.factory.ObjectProvider<
              com.pab.aitmp.aiis.godp.planning.api.port.PlanningReadQueries>
          reads) {
    return new ManualQueryService(
        repository, service, source, transition, marketing, reads.getIfAvailable());
  }

  @Bean
  public MarketingTaskService marketingTaskService(
      ManualRepository repository,
      ManualPorts.Source source,
      ManualPorts.Actor actor,
      ManualPorts.MarketingStatusSource statusSource) {
    return new MarketingTaskService(repository, source, actor, statusSource);
  }

  @Bean
  public ManualItemService manualItemService(
      ManualRepository repository, ManualPorts.Source source, ManualPorts.Actor actor) {
    return new ManualItemService(repository, source, actor);
  }

  @Bean
  public ManualContentStatusService manualContentStatusService(
      ManualRepository repository, ManualPorts.ContentStatusSource source) {
    return new ManualContentStatusService(repository, source);
  }

  @Bean
  public ManualExportService manualExportService(
      ManualQueryService queries, ManualItemService items, ManualPorts.Transition transition,
      org.springframework.beans.factory.ObjectProvider<com.pab.aitmp.aiis.godp.planning.api.port.PlanningSpreadsheetWriter> writers) {
    return new ManualExportService(queries, items, transition, writers.getIfAvailable(
        com.pab.aitmp.aiis.godp.planning.services.export.PoiPlanningSpreadsheetWriter::new));
  }
}
