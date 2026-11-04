package com.stratmatrix.planning.host;

import com.stratmatrix.planning.adapter.python.*;
import com.stratmatrix.planning.api.*;
import com.stratmatrix.planning.auto.*;
import com.stratmatrix.planning.config.*;
import com.stratmatrix.planning.content.*;
import com.stratmatrix.planning.manual.*;
import com.stratmatrix.planning.query.*;
import com.stratmatrix.planning.source.*;
import com.stratmatrix.planning.tasks.*;
import java.net.URI;
import org.mybatis.spring.SqlSessionTemplate;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.*;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.web.client.RestTemplate;

/** Import in the existing host; supply named sessions/transactions/HTTP and three host ports. */
@Configuration
@Profile("inside")
@ConditionalOnProperty(name = "planning.host.enabled", havingValue = "true")
@EnableConfigurationProperties(PythonProperties.class)
@Import({
  ManualModuleConfiguration.class,
  BusinessPlanningConfigModule.class,
  AutoScheduleModule.class,
  ContentCompletionModule.class,
  PlanningReadModule.class,
  PlanningTaskModule.class,
  ManualPlanningController.class,
  ConfigReleaseController.class,
  BusinessPlanningConfigController.class,
  TagTaxonomyController.class,
  PlanningHealthController.class,
  PlanningApiErrors.class,
  PlanningApiResponseAdvice.class,
  SourceFactsController.class,
  HostWebConfiguration.class
})
public class PlanningHostConfiguration {
  @Bean
  public PythonClient planningPythonClient(
      PythonProperties p, @Qualifier("planningPythonHttp") RestTemplate http) {
    if (p.getBaseUrl() == null || p.getToken() == null || p.getToken().trim().isEmpty())
      throw new IllegalStateException("请配置planning.python.base-url及planning.python.token");
    return new PythonClient(URI.create(p.getBaseUrl()), p.getToken(), http);
  }

  @Bean
  public ManualMapper manualMapper(@Qualifier("planningBusinessSessions") SqlSessionTemplate s) {
    return s.getMapper(ManualMapper.class);
  }

  @Bean
  public BusinessPlanningConfigMapper businessPlanningConfigMapper(
      @Qualifier("planningBusinessSessions") SqlSessionTemplate s) {
    return s.getMapper(BusinessPlanningConfigMapper.class);
  }

  @Bean
  public ConfigReleaseMapper configReleaseMapper(
      @Qualifier("planningBusinessSessions") SqlSessionTemplate s) {
    return s.getMapper(ConfigReleaseMapper.class);
  }

  @Bean
  public AutoScheduleMapper autoScheduleMapper(
      @Qualifier("planningBusinessSessions") SqlSessionTemplate s) {
    return s.getMapper(AutoScheduleMapper.class);
  }

  @Bean
  public PlanningQueryMapper planningQueryMapper(
      @Qualifier("planningBusinessSessions") SqlSessionTemplate s) {
    return s.getMapper(PlanningQueryMapper.class);
  }

  @Bean
  public SlotCompletionMapper slotCompletionMapper(
      @Qualifier("planningBusinessSessions") SqlSessionTemplate s) {
    return s.getMapper(SlotCompletionMapper.class);
  }

  @Bean
  public ManualDatabase manualDatabase(
      ManualMapper mapper,
      @Qualifier("planningBusinessTransactions") PlatformTransactionManager tx) {
    return new ManualDatabase(mapper, tx);
  }

  @Bean
  public BusinessConfigDatabase businessConfigDatabase(
      BusinessPlanningConfigMapper mapper,
      @Qualifier("planningBusinessTransactions") PlatformTransactionManager tx) {
    return new BusinessConfigDatabase(mapper, tx);
  }

  @Bean
  public AlgorithmConfigPort algorithmConfigPort(PythonClient python) {
    return new AlgorithmConfigPythonClient(python);
  }

  @Bean
  public AutoSchedulePort autoSchedulePort(PythonClient python) {
    return new AutoSchedulePythonClient(python);
  }

  @Bean
  public ManualPorts.Computer manualComputer(PythonClient python) {
    return new ManualComputePythonClient(python);
  }

  @Bean
  public PythonExecutionClient pythonExecutionClient(PythonClient python) {
    return new PythonExecutionClient(python);
  }

  @Bean
  public ManualPorts.Source sourceCatalog(SourceFacts facts, PythonClient python) {
    return new SourceCatalogAdapter(facts, new CatalogProjectionPythonClient(python));
  }

  @Bean
  public PlanningContentPort planningContent(SourceFacts facts) {
    return new ContentFactsAdapter(facts);
  }

  @Bean
  public ManualPorts.ContentStatusSource contentStatusSource(SourceFacts facts) {
    return new ContentObservations(facts)::content;
  }

  @Bean
  public ManualPorts.MarketingStatusSource marketingStatusSource(SourceFacts facts) {
    return new ContentObservations(facts)::marketing;
  }

  @Bean
  public ManualPorts.Transition planningHistory() {
    return new ManualNewInstallTransition();
  }
}
