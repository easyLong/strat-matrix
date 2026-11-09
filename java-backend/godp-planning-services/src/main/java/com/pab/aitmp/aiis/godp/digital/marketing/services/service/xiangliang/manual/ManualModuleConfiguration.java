package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual;

import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.ManualMapper;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.ManualPorts;
import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.PlanningReadQueries;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.BusinessTransactions;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.persistence.DeclarativeBusinessTransactions;

/** Stable service wiring. Local development and the host supply only the ports and database. */
@Configuration("xiangliangManualModuleConfiguration")
@EnableTransactionManagement
@ConditionalOnProperty(name = "planning.manual.enabled", havingValue = "true")
public class ManualModuleConfiguration {
  @Bean(name = "xiangliangBusinessTransactionBoundary")
  public BusinessTransactions businessTransactions() { return new DeclarativeBusinessTransactions(); }
  @Bean(name="xiangliangManualRepository")
  public ManualRepository manualRepository(ManualMapper mapper, BusinessTransactions transactions) {
    return new ManualRepository(mapper, transactions);
  }

  @Bean(name="xiangliangManualPlanningService")
  public ManualPlanningService manualPlanningService(
      ManualRepository repository,
      ManualPorts.Source source,
      ManualPorts.Computer computer,
      ManualPorts.Actor actor) {
    return new ManualPlanningService(repository, source, computer, actor);
  }

  @Bean(name="xiangliangManualQueryService")
  public ManualQueryService manualQueryService(
      ManualRepository repository,
      ManualPlanningService service,
      ManualPorts.Source source,
      ManualPorts.Transition transition,
      MarketingTaskService marketing,
      org.springframework.beans.factory.ObjectProvider<
              com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.PlanningReadQueries>
          reads) {
    return new ManualQueryService(
        repository, service, source, transition, marketing, reads.getIfAvailable());
  }

  @Bean(name="xiangliangMarketingTaskService")
  public MarketingTaskService marketingTaskService(
      ManualRepository repository,
      ManualPorts.Source source,
      ManualPorts.Actor actor,
      ManualPorts.MarketingStatusSource statusSource) {
    return new MarketingTaskService(repository, source, actor, statusSource);
  }

  @Bean(name="xiangliangManualItemService")
  public ManualItemService manualItemService(
      ManualRepository repository, ManualPorts.Source source, ManualPorts.Actor actor) {
    return new ManualItemService(repository, source, actor);
  }

  @Bean(name="xiangliangManualContentStatusService")
  public ManualContentStatusService manualContentStatusService(
      ManualRepository repository, ManualPorts.ContentStatusSource source) {
    return new ManualContentStatusService(repository, source);
  }

  @Bean(name="xiangliangManualExportService")
  public ManualExportService manualExportService(
      ManualQueryService queries, ManualItemService items, ManualPorts.Transition transition,
      org.springframework.beans.factory.ObjectProvider<com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.PlanningSpreadsheetWriter> writers) {
    return new ManualExportService(queries, items, transition, writers.getIfAvailable(
        com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.export.PoiPlanningSpreadsheetWriter::new));
  }
}
